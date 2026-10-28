#!/usr/bin/env python3
"""Download 90 calendar days of Twelve Data OHLC history for the replay.

Uses <=30-day chunks to stay below the 5,000-bar per-request limit and
paces requests for the configured free-plan rate limit. Requires TWELVEDATA_API_KEY.
"""
import csv
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

ROOT = Path("replay_data")
SYMBOLS = {
    "EURUSD": "EUR/USD", "EURJPY": "EUR/JPY", "GBPUSD": "GBP/USD",
    "AUDUSD": "AUD/USD", "USDCHF": "USD/CHF", "USDCAD": "USD/CAD",
    "NZDUSD": "NZD/USD", "USDJPY": "USD/JPY",
}
INTERVALS = {"15min": "15min", "1h": "1h", "4h": "4h"}
DAYS = 90
CHUNK_DAYS = 30
REQUEST_PAUSE_SECONDS = 9.0
API_URL = "https://api.twelvedata.com/time_series"


def fetch_chunk(session, symbol, interval, start, end, api_key):
    params = {
        "symbol": symbol,
        "interval": interval,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "order": "ASC",
        "outputsize": 5000,
        "format": "JSON",
        "apikey": api_key,
    }
    response = session.get(API_URL, params=params, timeout=45)
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") == "error" or "values" not in payload:
        raise RuntimeError(
            f"Twelve Data error for {symbol} {interval} {start}..{end}: "
            f"{payload.get('message', payload)}"
        )
    rows = []
    for item in payload["values"]:
        rows.append({
            "datetime": datetime.fromisoformat(item["datetime"]).strftime("%Y-%m-%d %H:%M:%S"),
            "open": float(item["open"]), "high": float(item["high"]),
            "low": float(item["low"]), "close": float(item["close"]),
        })
    return rows


def main():
    api_key = os.environ.get("TWELVEDATA_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("Missing TWELVEDATA_API_KEY secret; refusing to run a short-data backtest.")
    end_date = date.today()
    start_date = end_date - timedelta(days=DAYS)
    ROOT.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    request_count = 0

    for code, symbol in SYMBOLS.items():
        for label, interval in INTERVALS.items():
            by_time = {}
            chunk_start = start_date
            while chunk_start < end_date:
                chunk_end = min(chunk_start + timedelta(days=CHUNK_DAYS), end_date)
                if request_count:
                    time.sleep(REQUEST_PAUSE_SECONDS)
                chunk_rows = fetch_chunk(
                    session, symbol, interval, chunk_start, chunk_end, api_key
                )
                request_count += 1
                for row in chunk_rows:
                    by_time[row["datetime"]] = row
                print(
                    f"{symbol} {interval}: {chunk_start}..{chunk_end} "
                    f"received={len(chunk_rows)} unique={len(by_time)}",
                    flush=True,
                )
                chunk_start = chunk_end

            rows = [by_time[key] for key in sorted(by_time)]
            if not rows:
                raise RuntimeError(f"No history returned for {symbol} {interval}")
            path = ROOT / f"{code}_{label}.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle, fieldnames=["datetime", "open", "high", "low", "close"],
                    delimiter=";",
                )
                writer.writeheader()
                writer.writerows(rows)
            print(f"Wrote {path}: {len(rows)} bars, {rows[0]['datetime']} -> {rows[-1]['datetime']}")

    print(f"Downloaded 90-day OHLC history for {len(SYMBOLS)} pairs; API requests={request_count}")


if __name__ == "__main__":
    main()
