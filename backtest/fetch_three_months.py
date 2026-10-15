#!/usr/bin/env python3
"""Download a rolling 90-day M15 dataset from Twelve Data for the sweep backtest.

Requires TWELVEDATA_API_KEY in the environment. Never prints the key.
Requests are paced for the user's 8-credit/minute Twelve Data Basic allowance.
"""
import csv
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

API_KEY = os.getenv("TWELVEDATA_API_KEY")
URL = "https://api.twelvedata.com/time_series"
OUT_DIR = Path("replay_data")
SYMBOLS = {
    "AUDUSD": "AUD/USD",
    "EURJPY": "EUR/JPY",
    "EURUSD": "EUR/USD",
    "GBPUSD": "GBP/USD",
    "NZDUSD": "NZD/USD",
    "USDCAD": "USD/CAD",
    "USDCHF": "USD/CHF",
    "XAUUSD": "XAU/USD",
}
LOOKBACK_DAYS = 90
INTERVAL_DAYS = 30
REQUEST_GAP_SECONDS = 8.2


def fetch_chunk(symbol, start, end):
    params = {
        "symbol": symbol,
        "interval": "15min",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "timezone": "UTC",
        "apikey": API_KEY,
    }
    last_error = "unknown error"
    for attempt in range(3):
        try:
            response = requests.get(URL, params=params, timeout=45)
            if response.status_code == 429:
                last_error = "rate limit exceeded"
                time.sleep(65)
                continue
            response.raise_for_status()
            body = response.text.strip()
            rows = []
            if body.startswith("{") or body.startswith("["):
                payload = response.json()
                if "values" not in payload:
                    last_error = str(payload.get("message", payload.get("code", "no values")))
                    if "credits" in last_error.lower() or "limit" in last_error.lower():
                        time.sleep(65)
                        continue
                    break
                candles = payload["values"]
            else:
                # Twelve Data may return CSV text; parse it without logging the response/key.
                reader = csv.DictReader(body.splitlines())
                candles = []
                for item in reader:
                    normalized = {str(k).strip().lower(): str(v).strip() for k, v in item.items() if k}
                    stamp_key = next((k for k in normalized if k in ("datetime", "date", "time")), None)
                    if not stamp_key:
                        continue
                    candles.append({
                        "datetime": normalized[stamp_key],
                        "open": normalized.get("open"),
                        "high": normalized.get("high"),
                        "low": normalized.get("low"),
                        "close": normalized.get("close"),
                    })
                if not candles:
                    last_error = f"unexpected response (HTTP {response.status_code}, content-type {response.headers.get('content-type', 'unknown')})"
                    if attempt < 2:
                        time.sleep(5 * (attempt + 1))
                        continue
                    break
            for candle in candles:
                stamp = datetime.fromisoformat(str(candle["datetime"]).replace("Z", "+00:00")).replace(tzinfo=None)
                rows.append({
                    "datetime": stamp.strftime("%Y-%m-%d %H:%M:%S"),
                    "open": float(candle["open"]),
                    "high": float(candle["high"]),
                    "low": float(candle["low"]),
                    "close": float(candle["close"]),
                })
            return rows
        except (requests.RequestException, ValueError, KeyError) as exc:
            last_error = str(exc)
            if attempt < 2:
                time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"{symbol} {start}..{end}: {last_error}")


def main():
    if not API_KEY:
        raise SystemExit("Missing TWELVEDATA_API_KEY GitHub Actions secret.")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    end_day = datetime.utcnow().date()
    start_day = end_day - timedelta(days=LOOKBACK_DAYS)
    chunks = []
    cursor = start_day
    while cursor <= end_day:
        chunk_end = min(cursor + timedelta(days=INTERVAL_DAYS - 1), end_day)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)

    print(f"Downloading rolling {LOOKBACK_DAYS}-day M15 history: {start_day} to {end_day} UTC")
    print(f"Symbols: {', '.join(SYMBOLS)}; date chunks per symbol: {len(chunks)}")
    for symbol_code, api_symbol in SYMBOLS.items():
        merged = {}
        for idx, (chunk_start, chunk_end) in enumerate(chunks):
            if idx or symbol_code != next(iter(SYMBOLS)):
                time.sleep(REQUEST_GAP_SECONDS)
            rows = fetch_chunk(api_symbol, chunk_start, chunk_end)
            for row in rows:
                merged[row["datetime"]] = row
            print(f"{symbol_code}: chunk {idx + 1}/{len(chunks)} returned {len(rows)} candles")
        ordered = [merged[key] for key in sorted(merged)]
        if len(ordered) < 1500:
            raise RuntimeError(
                f"{symbol_code}: only {len(ordered)} candles downloaded; refusing to call this a 3-month test."
            )
        path = OUT_DIR / f"{symbol_code}_15min.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["datetime", "open", "high", "low", "close"], delimiter=";")
            writer.writeheader()
            writer.writerows(ordered)
        print(f"{symbol_code}: saved {len(ordered)} unique M15 candles ({ordered[0]['datetime']} to {ordered[-1]['datetime']})")

    print("Historical data download complete.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"DATA DOWNLOAD FAILED: {exc}", file=sys.stderr)
        raise
