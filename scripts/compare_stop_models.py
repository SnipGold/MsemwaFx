#!/usr/bin/env python3
"""Matched stop-model comparison using the same replay signals and OHLC candles.

The comparison stop is a tighter baseline: the extreme of the six M15 candles
ending at the signal candle, buffered by one ATR(14). Targets and signal list
are held fixed to isolate stop placement; this is NOT a re-optimized strategy.
The replay CSV omits the exact displacement index, so entry fill is approximated
as the first entry-price touch within 16 bars after the recorded signal candle.
"""
import csv
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


def load_candles(path):
    with path.open(newline="", encoding="utf-8") as f:
        return [{
            "time": datetime.fromisoformat(r["datetime"]),
            "open": float(r["open"]), "high": float(r["high"]),
            "low": float(r["low"]), "close": float(r["close"]),
        } for r in csv.DictReader(f, delimiter=";")]


def atr(rows, i, period=14):
    start = max(1, i - period + 1)
    trs = [max(rows[j]["high"] - rows[j]["low"],
               abs(rows[j]["high"] - rows[j - 1]["close"]),
               abs(rows[j]["low"] - rows[j - 1]["close"]))
           for j in range(start, i + 1)]
    return sum(trs) / len(trs) if trs else 0.0


def baseline_stop(rows, signal_i, direction, entry, pip_size):
    """Tighter baseline: six-bar extreme plus a one-ATR buffer."""
    recent = rows[max(0, signal_i - 5):signal_i + 1]
    if not recent:
        return None
    a = atr(rows, signal_i)
    if direction == "BUY":
        stop = min(x["low"] for x in recent) - a
        return stop if stop < entry else None
    stop = max(x["high"] for x in recent) + a
    return stop if stop > entry else None


def evaluate_stop(rows, entry_i, direction, sl, tp1, tp2, horizon=49):
    """OHLC conservative evaluation; simultaneous stop/target is ambiguous."""
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
    """Assume 50% exits at TP1 and 50% at TP2; charge one estimated spread."""
    if risk <= 0:
        return None
    sign = 1 if direction == "BUY" else -1
    r1, r2 = sign * (tp1 - entry) / risk, sign * (tp2 - entry) / risk
    if outcome == "TP2":
        gross = 0.5 * r1 + 0.5 * r2
    elif outcome == "TP1_THEN_SL":
        gross = 0.5 * r1 - 0.5
    elif outcome in ("SL", "SAME_CANDLE_SL_TP_AMBIGUOUS"):
        gross = -1.0
    else:
        return None
    return gross - (spread_pips * pip_size / risk)


def max_drawdown_r(values):
    equity = peak = 0.0
    worst = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return worst


def summarize(rows):
    # Sort by timestamp before building the combined trade-by-trade equity curve.
    ordered = sorted(rows, key=lambda x: x.get("comparison_entry_time") or "")
    closed = [x for x in ordered if x["net_r"] is not None]
    rs = [x["net_r"] for x in closed]
    wins = sum(x > 0 for x in rs)
    return {
        "closed_trades": len(closed), "wins": wins,
        "losses": sum(x <= 0 for x in rs),
        "win_rate_pct": round(100 * wins / len(closed), 2) if closed else 0.0,
        "net_r": round(sum(rs), 3),
        "expectancy_r": round(sum(rs) / len(rs), 3) if rs else 0.0,
        "max_drawdown_r": round(max_drawdown_r(rs), 3),
        "open_or_unresolved": sum(x["net_r"] is None for x in ordered),
    }


def main():
    with RESULTS.open(newline="", encoding="utf-8") as f:
        trades = list(csv.DictReader(f))
    candle_cache, paired = {}, []
    for trade in trades:
        pair = trade["pair"]
        if pair not in PAIRS:
            continue
        code, pip_size, spread_pips = PAIRS[pair]
        if pair not in candle_cache:
            candle_cache[pair] = load_candles(ROOT / f"{code}_15min.csv")
        candles = candle_cache[pair]
        t = datetime.fromisoformat(trade["signal_time"])
        signal_i = next((i for i, c in enumerate(candles) if c["time"] == t), None)
        if signal_i is None:
            paired.append({**trade, "baseline_sl": "", "baseline_outcome": "NO_SIGNAL_CANDLE_MATCH",
                           "comparison_entry_time": "", "structural_net_r": "", "baseline_net_r": ""})
            continue
        direction, entry = trade["direction"], float(trade["entry"])
        structural_sl, tp1, tp2 = float(trade["sl"]), float(trade["tp1"]), float(trade["tp2"])
        entry_i = None
        for j in range(signal_i + 1, min(signal_i + 17, len(candles))):
            bar = candles[j]
            stopped_before_fill = (bar["low"] <= structural_sl if direction == "BUY"
                                   else bar["high"] >= structural_sl)
            if stopped_before_fill:
                break
            if bar["low"] <= entry <= bar["high"]:
                entry_i = j
                break
        if entry_i is None:
            paired.append({**trade, "baseline_sl": "", "baseline_outcome": "NO_FILL_MATCHED",
                           "comparison_entry_time": "", "structural_net_r": "", "baseline_net_r": ""})
            continue

        base_sl = baseline_stop(candles, signal_i, direction, entry, pip_size)
        structural_outcome, _ = evaluate_stop(candles, entry_i, direction, structural_sl, tp1, tp2)
        baseline_outcome, _ = evaluate_stop(candles, entry_i, direction, base_sl, tp1, tp2)
        struct_risk = abs(entry - structural_sl)
        base_risk = abs(entry - base_sl) if base_sl is not None else 0
        struct_r = realized_r(structural_outcome, struct_risk, entry, tp1, tp2,
                              direction, spread_pips, pip_size)
        base_r = realized_r(baseline_outcome, base_risk, entry, tp1, tp2,
                            direction, spread_pips, pip_size) if base_risk else None
        paired.append({
            **trade, "baseline_sl": round(base_sl, 6) if base_sl is not None else "",
            "comparison_entry_time": candles[entry_i]["time"].isoformat(),
            "structural_outcome_replayed": structural_outcome, "baseline_outcome": baseline_outcome,
            "structural_net_r": round(struct_r, 4) if struct_r is not None else "",
            "baseline_net_r": round(base_r, 4) if base_r is not None else "",
        })

    fields = list(dict.fromkeys(k for row in paired for k in row))
    with open("stop_model_comparison.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(paired)

    summaries = []
    for model, key in (("STRUCTURAL_SWING_STOP", "structural_net_r"),
                       ("TIGHT_SIX_BAR_STOP", "baseline_net_r")):
        values = [{"net_r": float(x[key]), "comparison_entry_time": x["comparison_entry_time"]}
                  for x in paired if x.get(key) not in ("", None)]
        summaries.append({"model": model, **summarize(values)})
    with open("stop_model_summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summaries[0].keys())); w.writeheader(); w.writerows(summaries)
    print("MATCHED STOP-MODEL COMPARISON (R includes estimated one-spread round-trip cost)")
    for row in summaries:
        print(row)
    print(f"Signals: {len(trades)}; matched entries: {sum(bool(x.get('comparison_entry_time')) for x in paired)}")
    print("CAVEAT: fixed signals/targets; baseline is six-bar extreme + 1 ATR; entry timing is approximated.")


if __name__ == "__main__":
    main()
