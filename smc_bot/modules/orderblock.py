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


def detect_order_block(candles, bias, lookback=32, confirm_bars=8):
    """Find an opposing candle whose zone is followed by a close beyond its edge.

    This does not require a liquidity sweep or a displacement candle. The later
    close confirms the zone's directional relevance; the OB remains a context
    zone, not a standalone entry trigger.
    """
    if len(candles) < 12 or bias not in ("BULLISH", "BEARISH"):
        return None

    start = max(0, len(candles) - lookback - confirm_bars)
    last_confirmed = None
    for i in range(start, len(candles) - 1):
        candle = candles[i]
        if bias == "BULLISH" and float(candle["close"]) >= float(candle["open"]):
            continue
        if bias == "BEARISH" and float(candle["close"]) <= float(candle["open"]):
            continue

        end = min(len(candles), i + confirm_bars + 1)
        later = candles[i + 1:end]
        if bias == "BULLISH":
            confirms = [j for j, c in enumerate(later, start=i+1)
                        if float(c["close"]) > float(candle["high"])]
        else:
            confirms = [j for j, c in enumerate(later, start=i+1)
                        if float(c["close"]) < float(candle["low"])]
        if confirms:
            # Prefer the most recent confirmed opposing candle, not a sweep-specific one.
            signal_index = confirms[-1]
            last_confirmed = {
                "type": "BULLISH_OB" if bias == "BULLISH" else "BEARISH_OB",
                "low": float(candle["low"]),
                "high": float(candle["high"]),
                "index": i,
                "signal_index": signal_index,
                "sweep": None,
            }

    return last_confirmed
