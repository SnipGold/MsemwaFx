def _swing_high(c, i):
    return (
        float(c[i]["high"]) > float(c[i - 1]["high"])
        and float(c[i]["high"]) > float(c[i - 2]["high"])
        and float(c[i]["high"]) > float(c[i + 1]["high"])
        and float(c[i]["high"]) > float(c[i + 2]["high"])
    )


def _swing_low(c, i):
    return (
        float(c[i]["low"]) < float(c[i - 1]["low"])
        and float(c[i]["low"]) < float(c[i - 2]["low"])
        and float(c[i]["low"]) < float(c[i + 1]["low"])
        and float(c[i]["low"]) < float(c[i + 2]["low"])
    )


def _swings(candles):
    highs, lows = [], []
    for i in range(2, len(candles) - 2):
        if _swing_high(candles, i):
            highs.append((i, float(candles[i]["high"])))
        if _swing_low(candles, i):
            lows.append((i, float(candles[i]["low"])))
    return highs, lows


def _atr(candles, period=14):
    if len(candles) < 2:
        return 0.0
    tr = []
    for i in range(1, len(candles)):
        current, previous = candles[i], candles[i - 1]
        tr.append(max(
            float(current["high"]) - float(current["low"]),
            abs(float(current["high"]) - float(previous["close"])),
            abs(float(current["low"]) - float(previous["close"])),
        ))
    sample = tr[-period:]
    return sum(sample) / len(sample) if sample else 0.0


def analyze_structure(candles, lookback=60, break_atr_buffer=0.05):
    """Classify confirmed swing structure; momentum alone never flips HTF bias.

    A counter-trend rally inside a lower-high/lower-low sequence remains
    BEARISH until a confirmed close breaks the latest protected swing high.
    That first counter-trend break is labelled CHoCH and remains NEUTRAL
    (transition pending) until a new HH/HL sequence is established. The
    inverse rule applies to bullish structure.
    """
    if not isinstance(candles, (list, tuple)) or len(candles) < 12:
        return {
            "bias": "NEUTRAL", "event": "NONE", "phase": "INSUFFICIENT_DATA",
            "structural_score": 0, "momentum": 0.0,
            "last_swing_high": None, "last_swing_low": None,
        }

    sample = list(candles[-min(lookback, len(candles)):])
    highs, lows = _swings(sample)
    if len(highs) < 2 or len(lows) < 2:
        return {
            "bias": "NEUTRAL", "event": "NONE", "phase": "INSUFFICIENT_SWINGS",
            "structural_score": 0, "momentum": 0.0,
            "last_swing_high": highs[-1][1] if highs else None,
            "last_swing_low": lows[-1][1] if lows else None,
        }

    previous_high, last_high = highs[-2][1], highs[-1][1]
    previous_low, last_low = lows[-2][1], lows[-1][1]
    close = float(sample[-1]["close"])

    high_rising = last_high > previous_high
    high_falling = last_high < previous_high
    low_rising = last_low > previous_low
    low_falling = last_low < previous_low

    bullish_structure = high_rising and low_rising
    bearish_structure = high_falling and low_falling
    structural_score = int(high_rising) - int(high_falling) + int(low_rising) - int(low_falling)

    atr = _atr(sample)
    buffer = atr * max(0.0, float(break_atr_buffer))
    bullish_break = close > last_high + buffer
    bearish_break = close < last_low - buffer

    lookback_momentum = min(6, len(sample) - 1)
    momentum = close - float(sample[-1 - lookback_momentum]["close"])
    range_high = max(float(c["high"]) for c in sample[-24:])
    range_low = min(float(c["low"]) for c in sample[-24:])

    if bullish_structure:
        if bearish_break:
            bias, event, phase = "NEUTRAL", "CHoCH_BEARISH", "BEARISH_REVERSAL_PENDING"
        else:
            bias = "BULLISH"
            event = "BOS" if bullish_break else "NONE"
            phase = "PULLBACK" if momentum < 0 else "TREND"
    elif bearish_structure:
        if bullish_break:
            bias, event, phase = "NEUTRAL", "CHoCH_BULLISH", "BULLISH_REVERSAL_PENDING"
        else:
            bias = "BEARISH"
            event = "BOS" if bearish_break else "NONE"
            phase = "PULLBACK" if momentum > 0 else "TREND"
    else:
        # Mixed swing progression is a range, not permission to infer trend
        # from candle momentum or price location.
        bias, event, phase = "NEUTRAL", "NONE", "RANGE"
        if bullish_break:
            event, phase = "CHoCH_BULLISH", "BULLISH_BREAKOUT_PENDING"
        elif bearish_break:
            event, phase = "CHoCH_BEARISH", "BEARISH_BREAKOUT_PENDING"

    return {
        "bias": bias,
        "event": event,
        "phase": phase,
        "trend_structure": (
            "BULLISH" if bullish_structure else
            "BEARISH" if bearish_structure else "RANGE"
        ),
        "last_swing_high": last_high,
        "last_swing_low": last_low,
        "previous_swing_high": previous_high,
        "previous_swing_low": previous_low,
        "structural_score": structural_score,
        "momentum": momentum,
        "atr": atr,
        "break_buffer": buffer,
        "range_high": range_high,
        "range_low": range_low,
    }
