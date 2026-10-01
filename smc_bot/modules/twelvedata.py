import os
import time
import requests

API_KEY = os.getenv("TWELVEDATA_API_KEY")
URL = "https://api.twelvedata.com/time_series"


def get_candles(symbol, interval="15min", outputsize=400):
    if not API_KEY:
        print("ERROR: TWELVEDATA_API_KEY is missing.")
        return []

    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": outputsize,
        "timezone": "UTC",
        "apikey": API_KEY,
    }

    for attempt in range(2):
        try:
            r = requests.get(URL, params=params, timeout=30)

            if r.status_code == 429:
                if attempt == 0:
                    print(f"{symbol} {interval}: rate limited; waiting 65s...")
                    time.sleep(65)
                    continue
                print(f"{symbol} {interval}: rate limit still active.")
                return []

            if r.status_code >= 500:
                if attempt == 0:
                    time.sleep(10)
                    continue
                print(f"{symbol} {interval}: server error {r.status_code}.")
                return []

            r.raise_for_status()
            data = r.json()

            if "values" not in data:
                print(f"{symbol} {interval}: {data.get('message', 'no values')}")
                return []

            candles = []
            for c in reversed(data["values"]):
                candles.append({
                    "time": c["datetime"],
                    "open": float(c["open"]),
                    "high": float(c["high"]),
                    "low": float(c["low"]),
                    "close": float(c["close"]),
                })

            return candles

        except (requests.RequestException, ValueError) as exc:
            if attempt == 0:
                time.sleep(5)
            else:
                print(f"{symbol} {interval}: request failed: {exc}")

    return []
