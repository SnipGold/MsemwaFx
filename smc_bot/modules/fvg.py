def detect_fvg(candles):
    if len(candles) < 3:
        return None

    c1, c2, c3 = candles[-3:]

    if c1["high"] < c3["low"]:
        return {
            "type": "BULLISH_FVG",
            "top": c3["low"],
            "bottom": c1["high"]
        }

    if c1["low"] > c3["high"]:
        return {
            "type": "BEARISH_FVG",
            "top": c1["low"],
            "bottom": c3["high"]
        }

    return None
