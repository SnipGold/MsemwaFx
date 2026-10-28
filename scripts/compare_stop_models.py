#!/usr/bin/env python3
"""Matched stop-model comparison using the same replay signals and OHLC candles.

The structural outcome is taken from replay_all_results.csv. The comparison
stop is a deliberately tighter baseline: the extreme of the six M15 candles
ending at the signal candle, buffered by one ATR(14). Targets and signal list
are held fixed to isolate stop placement; this is NOT a full re-optimized
strategy comparison. Entry timing is approximated from the recorded signal
time because the replay CSV does not export the exact displacement index.
"""
import csv
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path("replay_data")
RESULTS = Path("replay_all_results.csv")
PAIRS = {
    "EUR/USD": ("EURUSD", 0.0001, 1.4),
    "EUR/JPY": ("EURJPY", 0.01, 1.3),
    "GBP/USD": ("GBPUSD", 0.0001, 1.6),
    "AUD/USD": ("AUDUSD", 0.0001, 1.6),
    "USD/CHF": ("USDCHF", 0.0001, 1.5),
    "USD/CAD": ("USDCAD", 0.0001, 1.9),
    "NZD/USD": ("NZDUSD", 0.0001, 1.8),
    "USD/JPY": ("USDJPY", 0.01, 1.5),
}
CLOSED = {"TP2", "SL", "TP1_THEN_SL", "SAME_CANDLE_SL_TP_AMBIGUOUS"}


def load_candles(path):
    with path.open(newline="", encoding="utf-8") as f:
        rows = []
        for r in csv.DictReader(f, delimiter=";"):
            rows.append({
                "time": datetime.fromisoformat(r["datetime"]),
                "open": float(r["open"]), "high": float(r["high"]),
                "low": float(r["low"]), "close": float(r["close"]),
            })
    return rows


def atr(rows, i, period=14):
    start = max(1, i - period + 1)
    trs = [max(rows[j]["high"] - rows[j]["low"],
               abs(rows[j]["high"] - rows[j - 1]["close"]),
               abs(rows[j]["low"] - rows[j - 1]["close"]))
           for j in range(start, i + 1)]
    return sum(trs) / len(trs) if trs else 0.0


def baseline_stop(rows, signal_i, direction, entry, pip_size):
    """Tighter legacy-style stop: recent six-bar extreme plus ATR buffer."""
    start = max(0, signal_i - 5)
    recent = rows[start:signal_i + 1]
    if not recent:
        return None
    a = atr(rows, signal_i)
    if direction == "BUY":
        stop = min(x["low"] for x in recent) - a
        return stop if stop < entry else None
    stop = max(x["high"] for x in recent) + a
    return stop if stop > entry else None


def evaluate_stop(rows, entry_i, direction, entry, sl, tp1, tp2, horizon=49):
    """OHLC conservative evaluation; ambiguous same-bar stop/target is not a win."""
    if sl is None:
        return "NO_VALID_BASELINE_STOP", None
    end = min(entry_i + horizon, len(rows))
    tp1_hit = False
    for k in range(entry_i, end):
        bar = rows[k]
        stop = bar["low"] <= sl if direction == "BUY" else bar["high"] >= sl
        hit1 = bar["high"] >= tp1 if direction == "BUY" else bar["low"] <= tp1
        hit2 = bar["high"] >= tp2 if direction == "BUY" else bar["low"] <= tp2
        if stop and (hit1 or hit2):
            return "SAME_CANDLE_SL_TP_AMBIGUOUS", k
        if stop:
            return ("TP1_THEN_SL" if tp1_hit else "SL"), k
        if hit2:
            return "TP2", k
        if hit1:
            tp1_hit = True
    return ("TP1_OPEN" if tp1_hit else "OPEN"), end - 1 if end > entry_i else None


def realized_r(outcome, risk, entry, tp1, tp2, direction, spread_pips, pip_size):
    """Assume 50% closes at TP1 and 50% at TP2; spread charged once round-trip."""
    if risk <= 0:
        return None
    sign = 1 if direction == "BUY" else -1
    r1 = sign * (tp1 - entry) / risk
    r2 = sign * (tp2 - entry) / risk
    if outcome == "TP2":
        gross = 0.5 * r1 + 0.5 * r2
    elif outcome == "TP1_THEN_SL":
        gross = 0.5 * r1 - 0.5
    elif outcome in ("SL", "SAME_CANDLE_SL_TP_AMBIGUOUS"):
        gross = -1.0
    else:
        return None
    # Reference spread is a stated estimate, not a broker quote or commission.
    cost_r = spread_pips * pip_size / risk
    return gross - cost_r


def max_drawdown_r(values):
    equity = peak = 0.0
    worst = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return worst


def summarize(rows):
    closed = [x for x in rows if x["net_r"] is not None]
    rs = [x["net_r"] for x in closed]
    wins = sum(x > 0 for x in rs)
    return {
        "closed_trades": len(closed),
        "wins": wins,
        "losses": sum(x <= 0 for x in rs),
        "win_rate_pct": round(100 * wins / len(closed), 2) if closed else 0.0,
        "net_r": round(sum(rs), 3),
        "expectancy_r": round(sum(rs) / len(rs), 3) if rs else 0.0,
        "max_drawdown_r": round(max_drawdown_r(rs), 3),
        "open_or_unresolved": sum(x["net_r"] is None for x in rows),
    }


def main():
    with RESULTS.open(newline="", encoding="utf-8") as f:
        trades = list(csv.DictReader(f))
    candle_cache = {}
    paired = []
    for trade in trades:
        pair = trade["pair"]
        if pair not in PAIRS:
            continue
        code, pip_size, spread_pips = PAIRS[pair]
        if pair not in candle_cache:
            candle_cache[pair] = load_candles(ROOT / f"{code}_15min.csv")
        candles = candle_cache[pair]
        t = datetime.fromisoformat(trade["signal_time"])
        # Exported signal_time is the liquidity-sweep candle. Use the first
        # matching candle; if absent, omit rather than silently misalign.
        signal_i = next((i for i, c in enumerate(candles) if c["time"] == t), None)
        if signal_i is None:
            paired.append({**trade, "baseline_sl": "", "baseline_outcome": "NO_SIGNAL_CANDLE_MATCH",
                           "structural_net_r": "", "baseline_net_r": ""})
            continue
        direction = trade["direction"]
        entry = float(trade["entry"])
        structural_sl = float(trade["sl"])
        tp1, tp2 = float(trade["tp1"]), float(trade["tp2"])
        # Approximate entry fill after signal, consistent with replay's 16-bar window.
        entry_i = None
        for j in range(signal_i + 1, min(signal_i + 17, len(candles))):
            b = candles[j]
            stopped_before_fill = (b["low"] <= structural_sl if direction == "BUY"
                                   else b["high"] >= structural_sl)
            if stopped_before_fill:
                break
            if b["low"] <= entry <= b["high"]:
                entry_i = j
                break
        if entry_i is None:
            paired.append({**trade, "baseline_sl": "", "baseline_outcome": "NO_FILL_MATCHED",
                           "structural_net_r": "", "baseline_net_r": ""})
            continue
        base_sl = baseline_stop(candles, signal_i, direction, entry, pip_size)
        structural_outcome, _ = evaluate_stop(candles, entry_i, direction, entry,
                                               structural_sl, tp1, tp2)
        baseline_outcome, _ = evaluate_stop(candles, entry_i, direction, entry,
                                             base_sl, tp1, tp2)
        struct_risk = abs(entry - structural_sl)
        base_risk = abs(entry - base_sl) if base_sl is not None else 0
        struct_r = realized_r(structural_outcome, struct_risk, entry, tp1, tp2,
                              direction, spread_pips, pip_size)
        base_r = realized_r(baseline_outcome, base_risk, entry, tp1, tp2,
                            direction, spread_pips, pip_size) if base_risk else None
        paired.append({
            **trade, "baseline_sl": round(base_sl, 6) if base_sl is not None else "",
            "comparison_entry_time": candles[entry_i]["time"].isoformat(),
            "structural_outcome_replayed": structural_outcome,
            "baseline_outcome": baseline_outcome,
            "structural_net_r": round(struct_r, 4) if struct_r is not None else "",
            "baseline_net_r": round(base_r, 4) if base_r is not None else "",
        })

    fields = list(dict.fromkeys(k for row in paired for k in row))
    with open("stop_model_comparison.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(paired)

    by_pair = defaultdict(list)
    for row in paired:
        if row.get("structural_net_r") != "" and row.get("structural_net_r") is not None:
            by_pair[row["pair"]].append({"net_r": float(row["structural_net_r"])})
    baseline_rows = [x for x in paired if x.get("baseline_net_r") not in ("", None)]
    structural_rows = [x for x in paired if x.get("structural_net_r") not in ("", None)]
    summary = []
    for model, key in (("STRUCTURAL_SWING_STOP", "structural_net_r"),
                       ("TIGHT_SIX_BAR_STOP", "baseline_net_r")):
        values = [{"net_r": float(x[key])} for x in paired if x.get(key) not in ("", None)]
        summary.append({"model": model, **summarize(values)})
    with open("stop_model_summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
        w.writeheader()
        w.writerows(summary)
    print("MATCHED STOP-MODEL COMPARISON (R includes estimated one-spread round-trip cost)")
    for row in summary:
        print(row)
    print(f"Trades with baseline outcome: {len(baseline_rows)}; structural R outcomes: {len(structural_rows)}")
    print("CAVEAT: fixed signals/targets; baseline is six-bar extreme + 1 ATR. Not a re-optimized strategy.")


if __name__ == "__main__":
    main()
