#!/usr/bin/env python3
"""Historical backtest for a mechanical interpretation of Liquidity Swings & Sweeps.

This is not a line-for-line execution of the Pine drawing code. It tests confirmed
5-left/2-right swing highs/lows and wick-through/close-back sweep-and-reclaim entries.
Only M15 OHLC data in replay_data is used. Results are gross of spread/commission/slippage.
"""
import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from collections import defaultdict

DATA_DIR = Path("replay_data")
OUT_DIR = Path("liquidity_sweeps_results")
LEFT = 5
RIGHT = 2
MAX_HOLD_BARS = 96  # 24 hours on M15
TARGETS_R = (1.0, 2.0, 3.0)


def parse_time(value):
    return datetime.fromisoformat(value.strip())


def load_bars(path):
    bars = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f, delimiter=";"):
            t = parse_time(row["datetime"])
            # Do not create artificial weekend trades from flat/placeholder candles.
            if t.weekday() >= 5:
                continue
            bars.append({
                "time": t,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
            })
    bars.sort(key=lambda x: x["time"])
    # Keep the last occurrence of a duplicate timestamp.
    by_time = {b["time"]: b for b in bars}
    return [by_time[t] for t in sorted(by_time)]


def pivot_high(bars, j):
    if j < LEFT or j + RIGHT >= len(bars):
        return False
    h = bars[j]["high"]
    return all(h > bars[k]["high"] for k in range(j - LEFT, j)) and all(
        h > bars[k]["high"] for k in range(j + 1, j + RIGHT + 1)
    )


def pivot_low(bars, j):
    if j < LEFT or j + RIGHT >= len(bars):
        return False
    lo = bars[j]["low"]
    return all(lo < bars[k]["low"] for k in range(j - LEFT, j)) and all(
        lo < bars[k]["low"] for k in range(j + 1, j + RIGHT + 1)
    )


def find_signals(bars, symbol):
    # Each level becomes usable only AFTER its right-side confirmation candle closes.
    highs, lows = [], []
    signals = []
    for i, bar in enumerate(bars):
        swept_highs, swept_lows = [], []

        # A swing high swept: price trades above it and closes back below -> SELL.
        still_highs = []
        for level in highs:
            if bar["high"] > level["price"]:
                if bar["close"] < level["price"]:
                    swept_highs.append(level)
            else:
                still_highs.append(level)
        highs = still_highs

        # A swing low swept: price trades below it and closes back above -> BUY.
        still_lows = []
        for level in lows:
            if bar["low"] < level["price"]:
                if bar["close"] > level["price"]:
                    swept_lows.append(level)
            else:
                still_lows.append(level)
        lows = still_lows

        # If one candle sweeps both sides, its direction is ambiguous; do not trade it.
        if bool(swept_highs) != bool(swept_lows):
            side = "SELL" if swept_highs else "BUY"
            pool = swept_highs if swept_highs else swept_lows
            # When several levels are taken together, use the outermost level.
            level = max(pool, key=lambda x: x["price"]) if side == "SELL" else min(
                pool, key=lambda x: x["price"]
            )
            entry = bar["close"]
            stop = bar["high"] if side == "SELL" else bar["low"]
            risk = abs(stop - entry)
            if risk > 0:
                age = max(0.0, (bar["time"] - level["time"]).total_seconds() / 60.0)
                rating = "VERY_STRONG" if age >= 60 else "STRONG" if age >= 15 else "OK" if age >= 5 else "WEAK"
                signals.append({
                    "symbol": symbol,
                    "signal_index": i,
                    "signal_time": bar["time"].isoformat(sep=" "),
                    "direction": side,
                    "swept_level": level["price"],
                    "pivot_time": level["time"].isoformat(sep=" "),
                    "sweep_age_minutes_approx": round(age, 1),
                    "age_rating_approx": rating,
                    "entry": entry,
                    "stop_loss": stop,
                    "risk_price": risk,
                })

        # Confirm pivots at the close of this bar, then allow them from the NEXT bar.
        j = i - RIGHT
        if j >= LEFT:
            if pivot_high(bars, j):
                highs.append({"price": bars[j]["high"], "time": bars[j]["time"]})
            if pivot_low(bars, j):
                lows.append({"price": bars[j]["low"], "time": bars[j]["time"]})
    return signals


def simulate_one_target(bars, signals, target_r):
    trades = []
    next_available = -1
    skipped_overlap = 0
    for signal in signals:
        i = signal["signal_index"]
        if i <= next_available:
            skipped_overlap += 1
            continue
        side = signal["direction"]
        entry = signal["entry"]
        sl = signal["stop_loss"]
        risk = signal["risk_price"]
        tp = entry - target_r * risk if side == "SELL" else entry + target_r * risk
        outcome, exit_i, exit_price, realized_r = "TIMEOUT", min(i + MAX_HOLD_BARS, len(bars) - 1), bars[min(i + MAX_HOLD_BARS, len(bars) - 1)]["close"], 0.0

        last_i = min(i + MAX_HOLD_BARS, len(bars) - 1)
        for j in range(i + 1, last_i + 1):
            b = bars[j]
            if side == "BUY":
                stop_hit = b["low"] <= sl
                target_hit = b["high"] >= tp
            else:
                stop_hit = b["high"] >= sl
                target_hit = b["low"] <= tp
            # Conservative OHLC assumption: if both touched in one candle, count SL first.
            if stop_hit:
                outcome, exit_i, exit_price, realized_r = "LOSS", j, sl, -1.0
                break
            if target_hit:
                outcome, exit_i, exit_price, realized_r = "WIN", j, tp, target_r
                break
        else:
            close = bars[exit_i]["close"]
            realized_r = ((close - entry) / risk) if side == "BUY" else ((entry - close) / risk)
            outcome = "TIMEOUT"

        row = dict(signal)
        row.update({
            "target_R": target_r,
            "take_profit": tp,
            "exit_time": bars[exit_i]["time"].isoformat(sep=" "),
            "exit_price": round(exit_price, 8),
            "outcome": outcome,
            "realized_R_gross": round(realized_r, 4),
            "bars_held": exit_i - i,
        })
        for key in ("entry", "stop_loss", "swept_level", "risk_price", "take_profit"):
            row[key] = round(row[key], 8)
        trades.append(row)
        next_available = exit_i
    return trades, skipped_overlap


def max_drawdown_r(values):
    equity = peak = max_dd = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return round(max_dd, 4)


def summarize(symbol, target_r, trades, raw_signals, skipped):
    values = [float(t["realized_R_gross"]) for t in trades]
    wins = sum(t["outcome"] == "WIN" for t in trades)
    losses = sum(t["outcome"] == "LOSS" for t in trades)
    timeouts = sum(t["outcome"] == "TIMEOUT" for t in trades)
    gross_profit = sum(v for v in values if v > 0)
    gross_loss = abs(sum(v for v in values if v < 0))
    return {
        "symbol": symbol,
        "target_R": target_r,
        "data_bars": "",
        "raw_sweep_signals": raw_signals,
        "trades_taken": len(trades),
        "skipped_overlapping_signals": skipped,
        "wins": wins,
        "losses": losses,
        "timeouts": timeouts,
        "win_rate_pct_of_trades": round(100 * wins / len(trades), 2) if trades else 0.0,
        "net_R_gross": round(sum(values), 4),
        "average_R_per_trade_gross": round(sum(values) / len(values), 4) if values else 0.0,
        "profit_factor_gross": round(gross_profit / gross_loss, 4) if gross_loss else ("INF" if gross_profit else 0.0),
        "max_drawdown_R": max_drawdown_r(values),
        "spread_commission_slippage_included": "NO",
    }


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    trade_rows, summary_rows = [], []
    data_files = sorted(DATA_DIR.glob("*_15min.csv"))
    if not data_files:
        raise SystemExit(f"No M15 CSV files found under {DATA_DIR}")

    for path in data_files:
        symbol = path.name.removesuffix("_15min.csv")
        bars = load_bars(path)
        if len(bars) < LEFT + RIGHT + 10:
            continue
        signals = find_signals(bars, symbol)
        for target_r in TARGETS_R:
            trades, skipped = simulate_one_target(bars, signals, target_r)
            summary = summarize(symbol, target_r, trades, len(signals), skipped)
            summary["data_bars"] = len(bars)
            summary["first_bar"] = bars[0]["time"].isoformat(sep=" ")
            summary["last_bar"] = bars[-1]["time"].isoformat(sep=" ")
            summary_rows.append(summary)
            trade_rows.extend(trades)

    fields = list(summary_rows[0].keys()) if summary_rows else []
    with (OUT_DIR / "summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(summary_rows)
    trade_fields = list(trade_rows[0].keys()) if trade_rows else [
        "symbol", "signal_time", "direction", "entry", "stop_loss", "take_profit",
        "target_R", "outcome", "realized_R_gross"
    ]
    with (OUT_DIR / "trades.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=trade_fields)
        w.writeheader()
        w.writerows(trade_rows)

    print("LIQUIDITY SWINGS & SWEEPS — M15 BACKTEST")
    print(f"Swing sensitivity: left={LEFT}, right={RIGHT}; max holding={MAX_HOLD_BARS} bars")
    print("Entry: sweep and reclaim candle close; SL: sweep candle extreme; targets: 1R and 2R")
    print("No look-ahead; one open trade per instrument per target; SL wins same-bar TP/SL ties.")
    print("Gross results: spread, commissions and slippage excluded.")
    for row in summary_rows:
        print(row)
    for target_r in TARGETS_R:
        subset = [r for r in summary_rows if r["target_R"] == target_r]
        total_n = sum(r["trades_taken"] for r in subset)
        total_wins = sum(r["wins"] for r in subset)
        net_r = sum(r["net_R_gross"] for r in subset)
        print(f"TOTAL target={target_r}R: instruments={len(subset)}, trades={total_n}, "
              f"wins={total_wins}, win_rate={100*total_wins/total_n if total_n else 0:.2f}%, "
              f"net_R_gross={net_r:.4f}")


if __name__ == "__main__":
    main()
