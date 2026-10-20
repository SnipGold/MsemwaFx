def detect_order_block(candles, bias):
    """Find a recent OB preceding directional displacement; liquidity sweep is not required."""
    if len(candles) < 20:
        return None

    # Search recent closed candles. A displacement candle must close beyond the
    # preceding two-candle structure; the OB is the nearest opposing candle
    # within the preceding four candles.
    start = max(3, len(candles) - 32)
    end = len(candles) - 1

    for signal_index in range(end, start - 1, -1):
        signal = candles[signal_index]
        previous = candles[signal_index - 2:signal_index]
        if len(previous) < 2:
            continue

        if bias == "BULLISH":
            displaced = signal["close"] > max(c["high"] for c in previous)
            opposite = lambda c: c["close"] < c["open"]
        else:
            displaced = signal["close"] < min(c["low"] for c in previous)
            opposite = lambda c: c["close"] > c["open"]

        if not displaced:
            continue

        candidates = [
            (i, candles[i])
            for i in range(max(start, signal_index - 4), signal_index)
            if opposite(candles[i])
        ]
        if not candidates:
            continue

        # Use the most recent opposing candle before the structure break.
        idx, ob = candidates[-1]
        zone_low = float(ob["low"])
        zone_high = float(ob["high"])

        # Include a same-leg FVG when present; FVG is still independently
        # required by the decision engine at signal_index.
        if signal_index >= 2:
            c1 = candles[signal_index - 2]
            c3 = candles[signal_index]
            if bias == "BULLISH" and c1["high"] < c3["low"]:
                zone_low = min(zone_low, float(c1["high"]))
                zone_high = max(zone_high, float(c3["low"]))
            elif bias == "BEARISH" and c1["low"] > c3["high"]:
                zone_low = min(zone_low, float(c3["high"]))
                zone_high = max(zone_high, float(c1["low"]))

        return {
            "type": "BULLISH_OB" if bias == "BULLISH" else "BEARISH_OB",
            "low": zone_low,
            "high": zone_high,
            "index": idx,
            "signal_index": signal_index,
            "sweep": None,
        }

    return None
