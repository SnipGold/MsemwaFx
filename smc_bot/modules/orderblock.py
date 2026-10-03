def _find_sweep(candles, bias, lookback=32, window=5):
    if len(candles) < window + 3:
        return None

    start = max(window, len(candles) - lookback)
    end = len(candles) - 1

    for i in range(end, start - 1, -1):
        prev = candles[i - window:i]

        if bias == "BULLISH":
            level = min(c["low"] for c in prev)
            if candles[i]["low"] < level and candles[i]["close"] > level:
                return {
                    "type": "SELL_SIDE_SWEEP",
                    "index": i,
                    "level": level,
                    "low": candles[i]["low"],
                }

        else:
            level = max(c["high"] for c in prev)
            if candles[i]["high"] > level and candles[i]["close"] < level:
                return {
                    "type": "BUY_SIDE_SWEEP",
                    "index": i,
                    "level": level,
                    "high": candles[i]["high"],
                }

    return None


def detect_order_block(candles, bias):
    """Find the displacement-origin OB/FVG zone linked to the latest aligned sweep."""
    if len(candles) < 20:
        return None

    sweep = _find_sweep(candles, bias)
    if not sweep:
        return None

    s = sweep["index"]
    end = min(len(candles) - 1, s + 8)
    displacement = None

    for i in range(s + 1, end + 1):
        previous = candles[max(s, i - 2):i]
        if not previous:
            continue

        prev_high = max(c["high"] for c in previous)
        prev_low = min(c["low"] for c in previous)

        if bias == "BULLISH" and candles[i]["close"] > prev_high:
            displacement = i
            break

        if bias == "BEARISH" and candles[i]["close"] < prev_low:
            displacement = i
            break

    if displacement is None:
        return None

    candidates = []
    for i in range(s + 1, displacement):
        c = candles[i]
        if bias == "BULLISH" and c["close"] < c["open"]:
            candidates.append((i, c))
        elif bias == "BEARISH" and c["close"] > c["open"]:
            candidates.append((i, c))

    if not candidates:
        return None

    # Prefer the structural origin near the sweep, not a micro-OB at the top/bottom of the range.
    if bias == "BULLISH":
        idx, ob = min(candidates, key=lambda x: (x[1]["low"], x[0]))
    else:
        idx, ob = max(candidates, key=lambda x: (x[1]["high"], -x[0]))

    zone_low = ob["low"]
    zone_high = ob["high"]

    # Merge the FVG made by the displacement candle when it belongs to the same leg.
    if displacement >= 2:
        c1 = candles[displacement - 2]
        c3 = candles[displacement]

        if bias == "BULLISH" and c1["high"] < c3["low"]:
            zone_low = min(zone_low, c1["high"])
            zone_high = max(zone_high, c3["low"])

        elif bias == "BEARISH" and c1["low"] > c3["high"]:
            zone_low = min(zone_low, c3["high"])
            zone_high = max(zone_high, c1["low"])

    return {
        "type": "BULLISH_OB" if bias == "BULLISH" else "BEARISH_OB",
        "low": zone_low,
        "high": zone_high,
        "index": idx,
        "signal_index": displacement,
        "sweep": sweep,
    }
