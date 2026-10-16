"""Compare ORIGINAL and SWEEP entries at fixed 1:2, 1:3, 1:4, 1:5 targets.

Historical signals are generated using only closed M15 candles. For each
signal, all four target ratios use the same entry and structural stop. If
entry and SL/target are both touched in one OHLC candle, SL is counted first.
This is a research backtest, not a live-trading instruction.
"""
import csv
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone

# Make smc_bot imports work when executed from the workflow's working directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from config import SYMBOLS, M15_OUTPUTSIZE
from modules.timeframes import build_htf
from modules.decision_engine import analyze_pair_diagnostic
from research.original_model import analyze_original

API_KEY = os.getenv("TWELVEDATA_API_KEY")
URL = "https://api.twelvedata.com/time_series"
OUT = os.getenv("BACKTEST_OUTPUT", "../research/original_vs_sweep_results.csv")
STEP = int(os.getenv("BACKTEST_STEP_CANDLES", "4"))
MAX_FORWARD = int(os.getenv("BACKTEST_FORWARD_CANDLES", "96"))
RATIOS = (2, 3, 4, 5)
RISK_FRACTION = float(os.getenv("BACKTEST_RISK_FRACTION", "0.005"))
MAX_DAILY_LOSS_R = float(os.getenv("BACKTEST_MAX_DAILY_LOSS_R", "3.0"))


def candles(symbol):
    if not API_KEY:
        raise RuntimeError("Missing TWELVEDATA_API_KEY secret")
    response = requests.get(URL, params={"symbol": symbol, "interval": "15min",
        "outputsize": M15_OUTPUTSIZE, "timezone": "UTC", "apikey": API_KEY}, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if "values" not in payload:
        raise RuntimeError(f"{symbol}: TwelveData returned {payload.get('message', payload)}")
    rows = []
    for x in reversed(payload["values"]):
        rows.append({"time": x["datetime"], "open": float(x["open"]),
            "high": float(x["high"]), "low": float(x["low"]), "close": float(x["close"])})
    now = datetime.now(timezone.utc)
    return [x for x in rows if datetime.fromisoformat(x["time"]).replace(
        tzinfo=timezone.utc).timestamp() + 900 <= now.timestamp()]


def outcome(setup, future, rr):
    entry, sl = float(setup["entry"]), float(setup["sl"])
    buy = setup["direction"] == "BUY"
    risk = abs(entry - sl)
    if risk <= 0:
        return None, "INVALID_SL"
    target = entry + rr * risk if buy else entry - rr * risk
    entered = False
    for c in future[:MAX_FORWARD]:
        if not entered:
            if c["low"] <= entry <= c["high"]:
                entered = True
            else:
                continue
        hit_sl = c["low"] <= sl if buy else c["high"] >= sl
        hit_target = c["high"] >= target if buy else c["low"] <= target
        if hit_sl:  # Conservative ordering when both boundaries fall in one candle.
            return -1.0, "SL"
        if hit_target:
            return float(rr), f"TP{rr}"
    return 0.0, "NO_RESOLUTION"


def main():
    if not API_KEY:
        raise RuntimeError("TWELVEDATA_API_KEY not configured in GitHub Actions secrets")
    records, rejects = [], defaultdict(int)
    for symbol in SYMBOLS:
        data = candles(symbol)
        print(f"{symbol}: {len(data)} closed M15 candles")
        for end in range(160, len(data) - MAX_FORWARD, STEP):
            history = data[:end]
            h4, h1, m15 = build_htf(history)
            if len(h4) < 10 or len(h1) < 10 or len(m15) < 80:
                continue
            try:
                sweep, _ = analyze_pair_diagnostic(h4, h1, m15, symbol)
            except Exception as exc:
                rejects[("SWEEP", symbol, "ERROR:" + type(exc).__name__)] += 1
                sweep = None
            try:
                original = analyze_original(h4, h1, m15)
            except Exception as exc:
                rejects[("ORIGINAL", symbol, "ERROR:" + type(exc).__name__)] += 1
                original = None
            for model, setup in (("ORIGINAL", original), ("SWEEP", sweep)):
                if not setup:
                    rejects[(model, symbol, "NO_SETUP")] += 1
                    continue
                for rr in RATIOS:
                    result, status = outcome(setup, data[end:], rr)
                    if result is None:
                        rejects[(model, symbol, status)] += 1
                        continue
                    records.append({
                        "symbol": symbol, "model": model, "rr_target": f"1:{rr}",
                        "signal_time": m15[-1]["time"], "direction": setup["direction"],
                        "entry": setup["entry"], "sl": setup["sl"],
                        "target": round(float(setup["entry"]) + (rr * abs(float(setup["entry"]) - float(setup["sl"])) if setup["direction"] == "BUY" else -rr * abs(float(setup["entry"]) - float(setup["sl"]))), 8),
                        "risk_fraction": RISK_FRACTION, "max_daily_loss_R_limit": MAX_DAILY_LOSS_R,
                        "result_R": result, "outcome": status,
                        "signal_fvg": setup.get("fvg", "NONE"),
                        "signal_sweep": setup.get("sweep", "NONE")})
        time.sleep(8)  # Stay within TwelveData Basic rate limits.

    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    fields = ["symbol", "model", "rr_target", "signal_time", "direction", "entry", "sl",
        "target", "risk_fraction", "max_daily_loss_R_limit", "result_R", "outcome",
        "signal_fvg", "signal_sweep"]
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)

    print("\nSUMMARY BY MODEL AND R:R")
    for model in ("ORIGINAL", "SWEEP"):
        for rr in RATIOS:
            rs = [x for x in records if x["model"] == model and x["rr_target"] == f"1:{rr}"]
            wins = sum(x["outcome"] == f"TP{rr}" for x in rs)
            losses = sum(x["outcome"] == "SL" for x in rs)
            unresolved = sum(x["outcome"] == "NO_RESOLUTION" for x in rs)
            resolved = wins + losses
            avg_all = sum(x["result_R"] for x in rs) / len(rs) if rs else 0.0
            expectancy = sum(x["result_R"] for x in rs) / resolved if resolved else 0.0
            win_rate = wins / resolved if resolved else 0.0
            print(f"{model} 1:{rr}: trades={len(rs)}, wins={wins}, losses={losses}, "
                  f"resolved_win_rate={win_rate:.1%}, expectancy_per_resolved_R={expectancy:.3f}, "
                  f"avg_R_including_unresolved={avg_all:.3f}, unresolved={unresolved}")
    print("\nREJECTION COUNTS")
    for (model, symbol, reason), count in sorted(rejects.items()):
        print(f"{model},{symbol},{reason},{count}")
    print(f"CSV: {OUT}")


if __name__ == "__main__":
    main()
