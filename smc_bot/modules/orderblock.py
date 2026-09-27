def detect_order_block(candles, bias):
    if len(candles) < 4:
        return None

    last = candles[-1]

    if bias == "BULLISH":
        for c in reversed(candles[:-1]):
            if c["close"] < c["open"]:
                return {
                    "type": "BULLISH_OB",
                    "high": c["high"],
                    "low": c["low"]
                }

    if bias == "BEARISH":
        for c in reversed(candles[:-1]):
            if c["close"] > c["open"]:
                return {
                    "type": "BEARISH_OB",
                    "high": c["high"],
                    "low": c["low"]
                }

    return None
