#!/usr/bin/env python3
"""MsemwaFX SMC walk-forward backtest. No EMA or moving-average signals.

Uses the repository's live decision engine at each completed M15 candle.
H1/H4 candles are filtered to those fully closed at signal time. Entry is a
limit fill at the decision engine's OB midpoint, valid for four M15 bars.
TP1/TP2 are the liquidity objectives produced by that engine (not fixed R).
If SL and a target are touched in the same OHLC bar, SL wins.

Accounting assumptions: 50% exit at TP1 and 50% at TP2; reference spread
from decision_engine plus 0.2 pip slippage per side; 0.5% equity risk/trade;
2% daily realized-loss lock; one open trade per pair. Results are research
estimates, not broker-execution guarantees.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "smc_bot"))

from config import SETUP_EXPIRY_CANDLES  # noqa: E402
from modules.decision_engine import (  # noqa: E402
    analyze_pair_diagnostic,
    _pip_size,
    _reference_spread_price,
)

DATA = ROOT / "replay_data"
OUT = ROOT / "smc_engine_backtest_results"
PAIRS = {"NZDUSD": "NZD/USD", "USDCHF": "USD/CHF"}
RISK_FRACTION = 0.005
DAILY_LOSS_LIMIT = 0.02
SLIPPAGE_PIPS_PER_SIDE = 0.2
MAX_HOLD_BARS = 96
PARTIAL_FRACTION = 0.5


def load(code: str, tf: str) -> pd.DataFrame:
    path = DATA / f"{code}_{tf}.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing candle file: {path}")
    df = pd.read_csv(path, sep=";")
    required = {"datetime", "open", "high", "low", "close"}
    if not required.issubset(df.columns):
        raise ValueError(f"{path}: required columns {sorted(required)}")
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce", utc=True)
    for col in ("open", "high", "low", "close"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = (df.dropna(subset=["datetime", "open", "high", "low", "close"])
            .drop_duplicates("datetime").sort_values("datetime"))
    if ((df["high"] < df[["open", "close", "low"]].max(axis=1)) |
        (df["low"] > df[["open", "close", "high"]].min(axis=1))).any():
        raise ValueError(f"{path}: invalid OHLC candle")
    return df.reset_index(drop=True)


def as_candles(df: pd.DataFrame):
    rows = []
    for r in df.itertuples(index=False):
        rows.append({
            "time": r.datetime.isoformat(),
            "open": float(r.open), "high": float(r.high),
            "low": float(r.low), "close": float(r.close),
        })
    return rows


def closed_htf(df: pd.DataFrame, cutoff: pd.Timestamp, hours: int):
    # CSV timestamps are candle-open times; include only bars closed by cutoff.
    close_times = df["datetime"] + pd.Timedelta(hours=hours)
    return df.loc[close_times <= cutoff].reset_index(drop=True)


def valid_target_order(side: str, entry: float, sl: float,
                       tp1: float, tp2: float,
                       zone_low: float, zone_high: float) -> bool:
    """Reject malformed setups before any fill or P/L calculation."""
    if not (zone_low <= entry <= zone_high):
        return False
    if side == "BUY":
        return sl < entry < tp1 < tp2
    if side == "SELL":
        return tp2 < tp1 < entry < sl
    return False


def fill_entry(bar, entry_price: float) -> bool:
    # Require the candle to trade through the actual midpoint limit price,
    # not merely somewhere inside the wider order-block zone.
    return float(bar.low) <= entry_price <= float(bar.high)


def simulate_trade(m15: pd.DataFrame, signal_i: int, setup: dict,
                   symbol: str, spread_price: float):
    side = setup["direction"]
    planned = float(setup["entry"])
    sl = float(setup["sl"])
    tp1, tp2 = float(setup["tp1"]), float(setup["tp2"])
    zone_low, zone_high = float(setup["entry_low"]), float(setup["entry_high"])
    if not valid_target_order(side, planned, sl, tp1, tp2, zone_low, zone_high):
        return {"outcome": "INVALID_TARGET_ORDER", "fill_i": None,
                "realized_r": 0.0}

    pip = _pip_size(symbol)
    slip = SLIPPAGE_PIPS_PER_SIDE * pip
    # Wait for the midpoint limit price to be touched after the signal candle.
    # Fill is conservatively recorded at the limit price (no favorable gap
    # improvement is assumed).
    fill_i = None
    for j in range(signal_i + 1, min(len(m15), signal_i + 1 + SETUP_EXPIRY_CANDLES)):
        bar = m15.iloc[j]
        if fill_entry(bar, planned):
            fill_i = j
            break
    if fill_i is None:
        return {"outcome": "UNFILLED", "fill_i": None, "realized_r": 0.0,
                "fill_price": None}

    fill_price = planned
    # Risk, target R and time-exit P/L all use the recorded fill price.
    risk = abs(fill_price - sl)
    if risk <= 0:
        return {"outcome": "INVALID", "fill_i": fill_i, "realized_r": 0.0,
                "fill_price": fill_price}

    # Spread is charged once as a full round-trip spread; slippage is charged
    # on entry and exit. These are model assumptions, not broker quotes.
    cost_r = (spread_price + 2 * slip) / risk
    cost_r = (spread_price + 2 * slip) / risk
    end_i = min(len(m15) - 1, fill_i + MAX_HOLD_BARS)
    tp1_hit = False
    tp2_hit = False
    remaining = 1.0
    realized = 0.0
    for j in range(fill_i, end_i + 1):
        bar = m15.iloc[j]
        if side == "BUY":
            stop_hit = float(bar.low) <= sl
            t1_hit = float(bar.high) >= tp1
            t2_hit = float(bar.high) >= tp2
        else:
            stop_hit = float(bar.high) >= sl
            t1_hit = float(bar.low) <= tp1
            t2_hit = float(bar.low) <= tp2

        if stop_hit:
            # OHLC cannot reveal whether target or stop was first within this
            # candle. Apply the conservative SL-first rule and flag the conflict.
            same_bar_conflict = bool(t1_hit or t2_hit)
            realized += remaining * -1.0
            remaining = 0.0
            return {"outcome": "SL" if not tp1_hit else "TP1_THEN_SL",
                    "fill_i": fill_i, "exit_i": j, "fill_price": fill_price,
                    "tp1_hit": tp1_hit, "tp2_hit": tp2_hit,
                    "same_bar_conflict": same_bar_conflict,
                    "same_bar_tp1_touched": bool(t1_hit),
                    "same_bar_tp2_touched": bool(t2_hit),
                    "gross_r": realized, "realized_r": realized - cost_r}
        if t1_hit and not tp1_hit:
            realized += PARTIAL_FRACTION * abs(tp1 - fill_price) / risk
            remaining -= PARTIAL_FRACTION
            tp1_hit = True
        if t2_hit and not tp2_hit:
            # If TP2 is reached, the remaining half exits there.
            realized += remaining * abs(tp2 - fill_price) / risk
            remaining = 0.0
            tp2_hit = True
            return {"outcome": "TP2", "fill_i": fill_i, "exit_i": j,
                    "fill_price": fill_price, "tp1_hit": tp1_hit,
                    "tp2_hit": True, "same_bar_conflict": False,
                    "same_bar_tp1_touched": False,
                    "same_bar_tp2_touched": False,
                    "gross_r": realized, "realized_r": realized - cost_r}

    # Time exit at final close, valued on remaining size.
    close = float(m15.close.iloc[end_i])
    open_r = ((close - fill_price) / risk if side == "BUY"
              else (fill_price - close) / risk)
    realized += remaining * open_r
    return {"outcome": "TP1_TIMEOUT" if tp1_hit else "TIMEOUT",
            "fill_i": fill_i, "exit_i": end_i, "fill_price": fill_price,
            "tp1_hit": tp1_hit, "tp2_hit": tp2_hit,
            "same_bar_conflict": False, "same_bar_tp1_touched": False,
            "same_bar_tp2_touched": False, "gross_r": realized,
            "realized_r": realized - cost_r}


def run_pair(code: str, symbol: str):
    m15 = load(code, "15min")
    h1 = load(code, "1h")
    h4 = load(code, "4h")
    m15_rows = as_candles(m15)
    trades = []
    diagnostics = {}
    equity = 1.0
    day_equity = 1.0
    current_day = None
    next_free_i = 0
    min_i = 80

    for i in range(min_i, len(m15) - 2):
        stamp = m15.loc[i, "datetime"]
        day = stamp.date()
        if day != current_day:
            current_day, day_equity = day, equity
        if i < next_free_i:
            continue
        if (equity - day_equity) / day_equity <= -DAILY_LOSS_LIMIT:
            continue

        signal_close = stamp + pd.Timedelta(minutes=15)
        h1_closed = closed_htf(h1, signal_close, 1)
        h4_closed = closed_htf(h4, signal_close, 4)
        if len(h1_closed) < 12 or len(h4_closed) < 12:
            continue

        # Same rolling M15 history shape as the live scanner's candle window.
        start = max(0, i - 1599)
        m15_window = m15_rows[start:i + 1]
        h1_rows = as_candles(h1_closed.tail(500))
        h4_rows = as_candles(h4_closed.tail(500))
        setup, reason = analyze_pair_diagnostic(h4_rows, h1_rows, m15_window, symbol)
        diagnostics[reason] = diagnostics.get(reason, 0) + 1
        if not setup:
            continue

        # Engine's signal_index is relative to the supplied rolling M15 window.
        signal_local = int(setup["signal_index"])
        signal_age = (len(m15_window) - 1) - signal_local
        if signal_age < 0 or signal_age > SETUP_EXPIRY_CANDLES:
            # Only accept a newly confirmed OB; do not enter a stale zone.
            continue

        result = simulate_trade(m15, i, setup, symbol,
                                _reference_spread_price(symbol))
        if result["outcome"] == "UNFILLED":
            continue
        if result["outcome"] in ("INVALID", "INVALID_TARGET_ORDER"):
            diagnostics[result["outcome"]] = diagnostics.get(result["outcome"], 0) + 1
            continue

        realized_r = float(result["realized_r"])
        pnl_fraction = RISK_FRACTION * realized_r
        equity *= max(0.0, 1.0 + pnl_fraction)
        exit_i = result.get("exit_i", result.get("fill_i", i))
        next_free_i = int(exit_i) + 1
        trades.append({
            "pair": symbol, "signal_time": stamp.isoformat(),
            "direction": setup["direction"], "entry": result["fill_price"],
            "planned_entry": setup["entry"], "fill_price": result["fill_price"],
            "sl": setup["sl"], "tp1": setup["tp1"], "tp2": setup["tp2"],
            "tp1_rr": setup["rr"], "tp2_rr": setup["tp2_rr"],
            "h4_bias": setup["h4_bias"], "h1_bias": setup["h1_bias"],
            "event": setup["event"], "ob": setup["order_block"],
            "fvg": setup["fvg"], "outcome": result["outcome"],
            "tp1_hit": result.get("tp1_hit", False),
            "tp2_hit": result.get("tp2_hit", False),
            "same_bar_conflict": result.get("same_bar_conflict", False),
            "same_bar_tp1_touched": result.get("same_bar_tp1_touched", False),
            "same_bar_tp2_touched": result.get("same_bar_tp2_touched", False),
            "gross_r": result.get("gross_r", 0.0),
            "net_r": realized_r, "equity": equity,
            "risk_fraction": RISK_FRACTION,
        })

    return trades, diagnostics, {
        "pair": symbol, "candles_m15": len(m15),
        "m15_start": m15.datetime.min().isoformat(),
        "m15_end": m15.datetime.max().isoformat(),
        "candles_h1": len(h1), "candles_h4": len(h4),
    }


def summarize(trades: pd.DataFrame):
    if trades.empty:
        return pd.DataFrame([{"trades": 0, "note": "No filled trades"}])
    rows = []
    for pair, g in trades.groupby("pair"):
        wins = int((g.net_r > 0).sum())
        gross_profit = float(g.loc[g.net_r > 0, "net_r"].sum())
        gross_loss = abs(float(g.loc[g.net_r < 0, "net_r"].sum()))
        eq = g.equity.astype(float)
        peak = eq.cummax()
        dd = ((peak - eq) / peak).max() * 100
        rows.append({
            "pair": pair, "trades": len(g), "profitable_trades": wins,
            "loss_trades": int((g.net_r < 0).sum()),
            "win_rate_pct": round(100 * wins / len(g), 2),
            "tp1_hit_pct": round(100 * g.tp1_hit.astype(bool).mean(), 2),
            "tp2_hit_pct": round(100 * g.tp2_hit.astype(bool).mean(), 2),
            "same_bar_conflicts": int(g.same_bar_conflict.astype(bool).sum()),
            "same_bar_conflict_pct": round(
                100 * g.same_bar_conflict.astype(bool).mean(), 2
            ),
            "net_R": round(float(g.net_r.sum()), 2),
            "avg_R": round(float(g.net_r.mean()), 3),
            "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss else None,
            "max_drawdown_pct": round(float(dd), 2),
            "ending_equity_from_1": round(float(eq.iloc[-1]), 4),
        })
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pairs", default="NZDUSD,USDCHF")
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True)
    all_trades, coverage, all_diag = [], [], []
    for code in [x.strip().upper() for x in args.pairs.split(",") if x.strip()]:
        if code not in PAIRS:
            raise ValueError(f"Unsupported pair: {code}")
        trades, diagnostics, cov = run_pair(code, PAIRS[code])
        all_trades.extend(trades)
        coverage.append(cov)
        for reason, count in diagnostics.items():
            all_diag.append({"pair": PAIRS[code], "diagnostic": reason, "bars": count})

    trade_df = pd.DataFrame(all_trades)
    summary = summarize(trade_df)
    pd.DataFrame(coverage).to_csv(OUT / "coverage.csv", index=False)
    pd.DataFrame(all_diag).to_csv(OUT / "diagnostics.csv", index=False)
    trade_df.to_csv(OUT / "trades.csv", index=False)
    summary.to_csv(OUT / "summary.csv", index=False)
    print("MsemwaFX SMC backtest complete — no EMA used.")
    print(summary.to_string(index=False))
    print("\nCoverage:")
    print(pd.DataFrame(coverage).to_string(index=False))
    print(f"\nFiles written to: {OUT}")


if __name__ == "__main__":
    main()
