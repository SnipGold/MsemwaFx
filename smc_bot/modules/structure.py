def analyze_structure(candles):
    if len(candles) < 6:
        return {"bias": "NEUTRAL", "event": None}

    highs = [c["high"] for c in candles[-6:]]
    lows = [c["low"] for c in candles[-6:]]

    if highs[-1] > highs[-2] and lows[-1] > lows[-2]:
        return {"bias": "BULLISH", "event": "BOS"}

    if highs[-1] < highs[-2] and lows[-1] < lows[-2]:
        return {"bias": "BEARISH", "event": "BOS"}

    if highs[-1] > highs[-2] and lows[-1] < lows[-2]:
        return {"bias": "REVERSAL", "event": "CHoCH"}

    return {"bias": "NEUTRAL", "event": None}
