#!/usr/bin/env python3
"""More realistic SMC research replay using committed M15/H1/H4 candles.

Signal is known only after the M15 candle closes; entry is the next M15 open.
H1/H4 bias uses only fully closed higher-timeframe candles.
M15 trigger: close breaks a prior 12-bar structure level and the signal candle
forms a directionally aligned three-candle FVG. SL is beyond the recent
structural swing (last 5 completed M15 candles before entry), with a small ATR
buffer. Targets compared: 3R and 4R. No daily loss limit/trade lock. Costs are
excluded. If SL and TP are both touched in one candle, SL is counted first.
Chronological 70/30 in-sample/out-of-sample split. Limited replay coverage means
results are exploratory, not evidence of a profitable live strategy.
"""
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "replay_data"
OUT = ROOT / "smc_backtest_results"
PAIRS = {
    "EURUSD": "EUR/USD", "EURJPY": "EUR/JPY", "GBPUSD": "GBP/USD",
    "AUDUSD": "AUD/USD", "USDCHF": "USD/CHF", "USDCAD": "USD/CAD",
    "NZDUSD": "NZD/USD",
}
TARGETS = (3, 4)
HOLD_BARS = 96
STRUCTURE_LOOKBACK = 12
SL_LOOKBACK = 5
ATR_PERIOD = 14
ATR_BUFFER = 0.10
MIN_RISK_ATR = 0.10
MAX_RISK_ATR = 3.0
IS_FRACTION = 0.70


def load(code, timeframe):
    path = DATA / f"{code}_{timeframe}.csv"
    if not path.exists():
        return None
    d = pd.read_csv(path, sep=";")
    required = {"datetime", "open", "high", "low", "close"}
    if not required.issubset(d.columns):
        raise ValueError(f"{path}: expected columns {sorted(required)}")
    d["datetime"] = pd.to_datetime(d["datetime"], errors="coerce")
    d = d.dropna(subset=["datetime"]).drop_duplicates("datetime").sort_values("datetime")
    for c in ("open", "high", "low", "close"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["open", "high", "low", "close"])
    return d.set_index("datetime").loc[lambda z: z.index.dayofweek < 5]


def atr_series(d, n=ATR_PERIOD):
    prev = d.close.shift(1)
    tr = pd.concat([d.high - d.low, (d.high - prev).abs(), (d.low - prev).abs()], axis=1).max(axis=1)
    return tr.rolling(n, min_periods=n).mean()


def bias_at(htf, cutoff, bar_duration):
    """EMA trend from the latest HTF candle that has fully closed by cutoff."""
    closed = htf.loc[(htf.index + bar_duration) <= cutoff]
    if len(closed) < 20:
        return None
    ema = closed.close.ewm(span=12, adjust=False).mean()
    last = float(closed.close.iloc[-1])
    average = float(ema.iloc[-1])
    if last > average:
        return "BUY"
    if last < average:
        return "SELL"
    return None


def aligned_fvg(d, i, side):
    if i < 2:
        return False
    # Classic 3-candle gap; signal is only confirmed at candle i close.
    if side == "BUY":
        return float(d.low.iloc[i]) > float(d.high.iloc[i - 2])
    return float(d.high.iloc[i]) < float(d.low.iloc[i - 2])


def build_signals(code, m15, h1, h4):
    rows = []
    a = atr_series(m15)
    for i in range(max(STRUCTURE_LOOKBACK, SL_LOOKBACK, ATR_PERIOD) + 2, len(m15) - 1):
        signal_time = m15.index[i]
        signal_close_time = signal_time + pd.Timedelta(minutes=15)
        # Exclude any H1/H4 candle that was still forming when signal candle closed.
        b1 = bias_at(h1, signal_close_time, pd.Timedelta(hours=1))
        b4 = bias_at(h4, signal_close_time, pd.Timedelta(hours=4))
        if not b1 or b1 != b4:
            continue
        side = b1
        row = m15.iloc[i]
        prior = m15.iloc[i-STRUCTURE_LOOKBACK:i]
        if side == "BUY":
            bos = float(row.close) > float(prior.high.max())
        else:
            bos = float(row.close) < float(prior.low.min())
        if not bos or not aligned_fvg(m15, i, side):
            continue
        av = float(a.iloc[i]) if pd.notna(a.iloc[i]) else 0.0
        if av <= 0:
            continue

        # Entry is next bar open, not the signal candle close.
        entry_i = i + 1
        entry = float(m15.open.iloc[entry_i])
        swing = m15.iloc[max(0, i-SL_LOOKBACK+1):i+1]
        if side == "BUY":
            sl = float(swing.low.min()) - av * ATR_BUFFER
            risk = entry - sl
        else:
            sl = float(swing.high.max()) + av * ATR_BUFFER
            risk = sl - entry
        if risk <= av * MIN_RISK_ATR or risk > av * MAX_RISK_ATR:
            continue

        rows.append({
            "pair": PAIRS[code], "code": code, "signal_time": signal_time.isoformat(),
            "entry_time": m15.index[entry_i].isoformat(), "side": side,
            "h4_bias": b4, "h1_bias": b1, "entry": entry, "sl": sl,
            "risk": risk, "signal_index": i, "entry_index": entry_i,
            "signal_close_time": signal_close_time,
        })
    return rows


def simulate(m15, sig, target_r):
    i = sig["entry_index"]
    side, entry, sl, risk = sig["side"], sig["entry"], sig["sl"], sig["risk"]
    tp = entry + target_r * risk if side == "BUY" else entry - target_r * risk
    end = min(len(m15) - 1, i + HOLD_BARS)
    for j in range(i, end + 1):
        bar = m15.iloc[j]
        stop = float(bar.low) <= sl if side == "BUY" else float(bar.high) >= sl
        take = float(bar.high) >= tp if side == "BUY" else float(bar.low) <= tp
        if stop:  # conservative if both touched within the same OHLC candle
            return -1.0, "SL", j - i
        if take:
            return float(target_r), "TP", j - i
    close = float(m15.close.iloc[end])
    r = (close - entry) / risk if side == "BUY" else (entry - close) / risk
    return float(r), "TIMEOUT", end - i


def summarize(trades, group_fields):
    out = []
    if trades.empty:
        return pd.DataFrame(columns=list(group_fields) + [
            "trades", "wins", "losses", "timeouts", "win_rate_pct", "net_R",
            "avg_R", "max_drawdown_R", "pairs"
        ])
    for keys, g in trades.groupby(list(group_fields), dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        wins = int((g.outcome == "TP").sum())
        losses = int((g.outcome == "SL").sum())
        eq = g.realized_R.cumsum()
        dd = float((eq.cummax() - eq).max()) if len(g) else 0.0
        row = dict(zip(group_fields, keys))
        row.update({
            "trades": len(g), "wins": wins, "losses": losses,
            "timeouts": int((g.outcome == "TIMEOUT").sum()),
            "win_rate_pct": round(100 * wins / len(g), 2) if len(g) else 0.0,
            "net_R": round(float(g.realized_R.sum()), 2),
            "avg_R": round(float(g.realized_R.mean()), 3) if len(g) else 0.0,
            "max_drawdown_R": round(dd, 2),
            "pairs": int(g.pair.nunique()),
        })
        out.append(row)
    return pd.DataFrame(out)


def main():
    OUT.mkdir(exist_ok=True)
    coverage, signals, all_trades = [], [], []
    datasets = {}
    for code in PAIRS:
        m15, h1, h4 = (load(code, tf) for tf in ("15min", "1h", "4h"))
        if m15 is None or h1 is None or h4 is None:
            coverage.append({"pair": PAIRS[code], "status": "MISSING M15/H1/H4 data"})
            continue
        datasets[code] = (m15, h1, h4)
        coverage.append({
            "pair": PAIRS[code], "m15_bars": len(m15), "h1_bars": len(h1), "h4_bars": len(h4),
            "start": m15.index.min().isoformat(), "end": m15.index.max().isoformat(),
        })
        pair_signals = build_signals(code, m15, h1, h4)
        signals.extend([{k: v for k, v in s.items() if k not in ("signal_index", "entry_index", "signal_close_time")} for s in pair_signals])
        split_index = int(len(m15) * IS_FRACTION)
        split_time = m15.index[split_index] if split_index < len(m15) else m15.index[-1]
        for target in TARGETS:
            next_free = -1
            for s in pair_signals:
                if s["entry_index"] <= next_free:
                    continue
                r, outcome, held = simulate(m15, s, target)
                period = "IN_SAMPLE" if pd.Timestamp(s["entry_time"]) < split_time else "OUT_OF_SAMPLE"
                all_trades.append({
                    **{k: v for k, v in s.items() if k not in ("signal_index", "entry_index", "signal_close_time")},
                    "target_R": target, "period": period, "outcome": outcome,
                    "realized_R": round(r, 4), "bars_held": held,
                })
                next_free = s["entry_index"] + max(held, 1)

    pd.DataFrame(coverage).to_csv(OUT / "coverage.csv", index=False)
    pd.DataFrame(signals).to_csv(OUT / "signals.csv", index=False)
    trades = pd.DataFrame(all_trades)
    trades.to_csv(OUT / "trades.csv", index=False)
    if len(trades):
        summary = summarize(trades, ["target_R", "period"])
        summary.to_csv(OUT / "summary.csv", index=False)
        by_pair = summarize(trades, ["target_R", "period", "pair"])
        by_pair.to_csv(OUT / "pair_summary.csv", index=False)
    else:
        summary = summarize(trades, ["target_R", "period"])
        summary.to_csv(OUT / "summary.csv", index=False)
        summarize(trades, ["target_R", "period", "pair"]).to_csv(OUT / "pair_summary.csv", index=False)

    print("COVERAGE (available committed data only)")
    print(pd.DataFrame(coverage).to_string(index=False))
    print("\nRESULTS: next-bar-open entries, aligned closed H4/H1 EMA bias, M15 BOS + FVG, structural SL; costs excluded")
    print(summary.to_string(index=False) if len(summary) else "NO QUALIFIED TRADES")
    print(f"\nSignals: {len(signals)} | Trade rows (targets and periods): {len(trades)}")
    print("No daily loss lock. This replay uses only the date range shown in coverage.csv; no external historical data is fetched.")


if __name__ == "__main__":
    main()
