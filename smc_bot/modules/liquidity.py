def liquidity_sweep(candles):
    if len(candles) < 5:
        return None

    last = candles[-1]
    prev = candles[-5:-1]

    highest = max(c["high"] for c in prev)
    lowest = min(c["low"] for c in prev)

    if last["high"] > highest and last["close"] < highest:
        return {"type": "BUY_SIDE_SWEEP", "level": highest}

    if last["low"] < lowest and last["close"] > lowest:
        return {"type": "SELL_SIDE_SWEEP", "level": lowest}

    return None
