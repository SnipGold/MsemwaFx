"""Compare ORIGINAL and SWEEP at 1:2, 1:3, 1:4, 1:5 with a 5% daily loss cap.

Daily realized P/L is applied only when a simulated trade resolves. Before each
new signal, the simulator settles all prior trades whose resolution timestamp
has passed, then checks the loss limit for the signal's date. One open position
per symbol/model/target is allowed. Ambiguous OHLC bars count as stop-loss first.
"""
import csv
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone

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
DAILY_LOSS_LIMIT_PCT = float(os.getenv("BACKTEST_DAILY_LOSS_LIMIT_PCT", "5.0"))
MAX_DAILY_LOSS_R = DAILY_LOSS_LIMIT_PCT / (RISK_FRACTION * 100.0)


def parse_time(value):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def candles(symbol):
    if not API_KEY:
        raise RuntimeError("Missing TWELVEDATA_API_KEY")
    response = requests.get(URL, params={"symbol": symbol, "interval": "15min",
        "outputsize": M15_OUTPUTSIZE, "timezone": "UTC", "apikey": API_KEY}, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if "values" not in payload:
        raise RuntimeError(f"{symbol}: TwelveData returned {payload.get('message', payload)}")
    rows = [{"time": x["datetime"], "open": float(x["open"]), "high": float(x["high"]),
             "low": float(x["low"]), "close": float(x["close"])}
            for x in reversed(payload["values"])]
    now = datetime.now(timezone.utc)
    return [x for x in rows if parse_time(x["time"]).timestamp() + 900 <= now.timestamp()]


def outcome(setup, future, rr):
    entry, sl = float(setup["entry"]), float(setup["sl"])
    buy = setup["direction"] == "BUY"
    risk = abs(entry - sl)
    if risk <= 0:
        return None, "INVALID_SL", None
    target = entry + rr * risk if buy else entry - rr * risk
    entered = False
    for offset, c in enumerate(future[:MAX_FORWARD]):
        if not entered:
            if c["low"] <= entry <= c["high"]:
                entered = True
            else:
                continue
        hit_sl = c["low"] <= sl if buy else c["high"] >= sl
        hit_target = c["high"] >= target if buy else c["low"] <= target
        if hit_sl:
            return -1.0, "SL", offset
        if hit_target:
            return float(rr), f"TP{rr}", offset
    return 0.0, "NO_RESOLUTION", min(len(future), MAX_FORWARD) - 1 if future else None


def main():
    if not API_KEY:
        raise RuntimeError("TWELVEDATA_API_KEY not configured in GitHub Actions secrets")
    candidates, rejects, candle_data = [], defaultdict(int), {}
    for symbol in SYMBOLS:
        data = candles(symbol)
        candle_data[symbol] = data
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
                if setup:
                    candidates.append({"symbol": symbol, "model": model, "setup": setup,
                        "signal_time": m15[-1]["time"], "signal_index": end})
                else:
                    rejects[(model, symbol, "NO_SETUP")] += 1
        time.sleep(8)

    records = []
    for model in ("ORIGINAL", "SWEEP"):
        for rr in RATIOS:
            selected = sorted((x for x in candidates if x["model"] == model),
                              key=lambda x: (parse_time(x["signal_time"]), x["symbol"]))
            daily_realized = defaultdict(float)
            busy_until = {}
            seen = set()
            pending = []
            for item in selected:
                signal_dt = parse_time(item["signal_time"])
                # Realize outcomes only once their actual simulated resolution time
                # has occurred. This prevents future losses affecting earlier signals.
                due, pending = ([p for p in pending if p["resolution_dt"] <= signal_dt],
                                [p for p in pending if p["resolution_dt"] > signal_dt])
                for p in due:
                    if p["outcome"] != "NO_RESOLUTION":
                        daily_realized[p["resolution_dt"].date().isoformat()] += p["result_R"]

                setup, symbol = item["setup"], item["symbol"]
                key = (symbol, setup["direction"], item["signal_time"])
                if key in seen:
                    continue
                seen.add(key)
                signal_day = signal_dt.date().isoformat()
                if daily_realized[signal_day] <= -MAX_DAILY_LOSS_R:
                    rejects[(model, symbol, f"DAILY_STOP_1:{rr}")] += 1
                    continue
                if busy_until.get(symbol) and busy_until[symbol] > signal_dt:
                    rejects[(model, symbol, f"POSITION_OPEN_1:{rr}")] += 1
                    continue

                data = candle_data[symbol]
                result, status, offset = outcome(setup, data[item["signal_index"]:], rr)
                if offset is None:
                    continue
                resolution_index = min(item["signal_index"] + offset, len(data) - 1)
                resolution_dt = parse_time(data[resolution_index]["time"])
                busy_until[symbol] = resolution_dt
                risk = abs(float(setup["entry"]) - float(setup["sl"]))
                target = float(setup["entry"]) + (rr * risk if setup["direction"] == "BUY" else -rr * risk)
                row = {"symbol": symbol, "model": model, "rr_target": f"1:{rr}",
                    "signal_time": item["signal_time"], "resolution_time": resolution_dt.isoformat(),
                    "resolution_day": resolution_dt.date().isoformat(), "direction": setup["direction"],
                    "entry": setup["entry"], "sl": setup["sl"], "target": round(target, 8),
                    "risk_fraction": RISK_FRACTION, "daily_loss_limit_pct": DAILY_LOSS_LIMIT_PCT,
                    "daily_loss_limit_R": MAX_DAILY_LOSS_R, "result_R": result, "outcome": status,
                    "signal_fvg": setup.get("fvg", "NONE"), "signal_sweep": setup.get("sweep", "NONE")}
                records.append(row)
                pending.append({"resolution_dt": resolution_dt, "result_R": result, "outcome": status})

            # Flush pending outcomes to keep the event accounting complete.
            for p in sorted(pending, key=lambda x: x["resolution_dt"]):
                if p["outcome"] != "NO_RESOLUTION":
                    daily_realized[p["resolution_dt"].date().isoformat()] += p["result_R"]

    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    fields = ["symbol", "model", "rr_target", "signal_time", "resolution_time", "resolution_day",
        "direction", "entry", "sl", "target", "risk_fraction", "daily_loss_limit_pct",
        "daily_loss_limit_R", "result_R", "outcome", "signal_fvg", "signal_sweep"]
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)

    print(f"DAILY LOSS CAP: {DAILY_LOSS_LIMIT_PCT:.1f}% = {MAX_DAILY_LOSS_R:.1f}R at "
          f"{RISK_FRACTION*100:.2f}% nominal risk per trade.")
    print("Daily loss accounting: realized on resolution timestamp; checked before each later signal.")
    print("SUMMARY BY MODEL AND R:R")
    for model in ("ORIGINAL", "SWEEP"):
        for rr in RATIOS:
            rs = [x for x in records if x["model"] == model and x["rr_target"] == f"1:{rr}"]
            wins = sum(x["outcome"] == f"TP{rr}" for x in rs)
            losses = sum(x["outcome"] == "SL" for x in rs)
            unresolved = sum(x["outcome"] == "NO_RESOLUTION" for x in rs)
            resolved = wins + losses
            total_r = sum(x["result_R"] for x in rs if x["outcome"] != "NO_RESOLUTION")
            expectancy = total_r / resolved if resolved else 0.0
            if resolved:
                print(f"{model} 1:{rr}: trades={len(rs)}, wins={wins}, losses={losses}, "
                      f"resolved_win_rate={wins/resolved:.1%}, expectancy_per_resolved_R={expectancy:.3f}, "
                      f"unresolved={unresolved}")
            else:
                print(f"{model} 1:{rr}: trades={len(rs)}, no resolved outcomes, unresolved={unresolved}")
    print("REJECTION COUNTS")
    for (model, symbol, reason), count in sorted(rejects.items()):
        print(f"{model},{symbol},{reason},{count}")
    print(f"CSV: {OUT}")


if __name__ == "__main__":
    main()
