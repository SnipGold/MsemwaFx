"""Historical comparison harness. Run from smc_bot/ with TWELVEDATA_API_KEY set.

Uses only closed M15 candles and evaluates both models on the same rolling
snapshots. Entries require at least 1:2 planned R:R. Ambiguous OHLC bars are
handled conservatively: stop loss wins if SL and a target are both touched.
"""
import csv
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone

# Ensure imports work when this file is executed by GitHub Actions from smc_bot/.
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


def outcome(setup, future):
    entry, sl, tp1, tp2 = (float(setup[k]) for k in ("entry", "sl", "tp1", "tp2"))
    buy = setup["direction"] == "BUY"
    risk = abs(entry - sl)
    if risk <= 0 or abs(tp1 - entry) / risk < 2.0:
        return None, "REJECT_RR_BELOW_2"
    entered = False
    for c in future[:MAX_FORWARD]:
        hit_entry = c["low"] <= entry <= c["high"]
        if not entered:
            if hit_entry:
                entered = True
            else:
                continue
        hit_sl = c["low"] <= sl if buy else c["high"] >= sl
        hit_tp2 = c["high"] >= tp2 if buy else c["low"] <= tp2
        hit_tp1 = c["high"] >= tp1 if buy else c["low"] <= tp1
        if hit_sl:
            return -1.0, "SL"
        if hit_tp2:
            return abs(tp2 - entry) / risk, "TP2"
        if hit_tp1:
            return abs(tp1 - entry) / risk, "TP1"
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
                sweep, _reason = analyze_pair_diagnostic(h4, h1, m15, symbol)
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
                result, status = outcome(setup, data[end:])
                if result is None:
                    rejects[(model, symbol, status)] += 1
                    continue
                records.append({"symbol": symbol, "model": model, "signal_time": m15[-1]["time"],
                    "direction": setup["direction"], "entry": setup["entry"], "sl": setup["sl"],
                    "tp1": setup["tp1"], "tp2": setup["tp2"], "risk_fraction": RISK_FRACTION,
                    "result_R": result, "outcome": status, "signal_fvg": setup.get("fvg", "NONE"),
                    "signal_sweep": setup.get("sweep", "NONE")})
        time.sleep(8)
    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        fields = ["symbol", "model", "signal_time", "direction", "entry", "sl", "tp1", "tp2",
            "risk_fraction", "result_R", "outcome", "signal_fvg", "signal_sweep"]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)
    print("\nSUMMARY")
    for model in ("ORIGINAL", "SWEEP"):
        rs = [x for x in records if x["model"] == model]
        wins = sum(x["result_R"] > 0 for x in rs)
        losses = sum(x["result_R"] < 0 for x in rs)
        resolved = wins + losses
        avg = sum(x["result_R"] for x in rs) / len(rs) if rs else 0
        if resolved:
            print(f"{model}: trades={len(rs)}, wins={wins}, losses={losses}, win_rate={wins/resolved:.1%}")
        else:
            print(f"{model}: trades={len(rs)}, no resolved outcomes")
        print(f"  average_R_per_record={avg:.3f}; unresolved={sum(x['outcome']=='NO_RESOLUTION' for x in rs)}")
    print("\nREJECTION COUNTS")
    for (model, symbol, reason), count in sorted(rejects.items()):
        print(f"{model},{symbol},{reason},{count}")
    print(f"CSV: {OUT}")


if __name__ == "__main__":
    main()
