import os
import requests

API_KEY = os.getenv("TWELVEDATA_API_KEY")

def get_candles(symbol, interval="15min", outputsize=200):
    url = "https://api.twelvedata.com/time_series"
    r = requests.get(url, params={
        "symbol": symbol,
        "interval": interval,
        "outputsize": outputsize,
        "apikey": API_KEY
    }, timeout=20)

    data = r.json()

    if "values" not in data:
        return []

    candles = []
    for c in reversed(data["values"]):
        candles.append({
            "time": c["datetime"],
            "open": float(c["open"]),
            "high": float(c["high"]),
            "low": float(c["low"]),
            "close": float(c["close"])
        })

    return candles
