def _swing_high(c, i):
    return (
        c[i]["high"] > c[i - 1]["high"]
        and c[i]["high"] > c[i - 2]["high"]
        and c[i]["high"] > c[i + 1]["high"]
        and c[i]["high"] > c[i + 2]["high"]
    )


def _swing_low(c, i):
    return (
        c[i]["low"] < c[i - 1]["low"]
        and c[i]["low"] < c[i - 2]["low"]
        and c[i]["low"] < c[i + 1]["low"]
        and c[i]["low"] < c[i + 2]["low"]
    )


def _swings(candles):
    highs = []
    lows = []
    for i in range(2, len(candles) - 2):
        if _swing_high(candles, i):
            highs.append((i, float(candles[i]["high"])))
        if _swing_low(candles, i):
            lows.append((i, float(candles[i]["low"])))
    return highs, lows


def analyze_structure(candles):
    """Return a more robust HTF structure bias.

    The old detector required the last two swing highs AND lows to make a
    perfect HH/HL or LH/LL sequence. That made strong trends look NEUTRAL
    during normal pullbacks. This version combines structural progression,
    confirmed breaks and recent momentum, while remaining conservative.
    """
    if len(candles) < 12:
        return {"bias": "NEUTRAL", "event": "NONE"}

    highs, lows = _swings(candles)
    close = float(candles[-1]["close"])
    recent = candles[-min(24, len(candles)):]
    range_high = max(float(c["high"]) for c in recent)
    range_low = min(float(c["low"]) for c in recent)
    range_size = max(range_high - range_low, 1e-12)

    structural_score = 0
    if len(highs) >= 2:
        if highs[-1][1] > highs[-2][1]:
            structural_score += 1
        elif highs[-1][1] < highs[-2][1]:
            structural_score -= 1

    if len(lows) >= 2:
        if lows[-1][1] > lows[-2][1]:
            structural_score += 1
        elif lows[-1][1] < lows[-2][1]:
            structural_score -= 1

    last_high = highs[-1][1] if highs else None
    last_low = lows[-1][1] if lows else None

    # Confirmed structural break gets priority over a temporary pullback.
    bullish_break = last_high is not None and close > last_high
    bearish_break = last_low is not None and close < last_low

    # Short-term momentum is a tie-breaker when swing progression is mixed.
    lookback = min(6, len(candles) - 1)
    old_close = float(candles[-1 - lookback]["close"])
    momentum = close - old_close
    momentum_threshold = range_size * 0.08

    position = (close - range_low) / range_size

    if bullish_break and not bearish_break:
        bias = "BULLISH"
        event = "BOS"
    elif bearish_break and not bullish_break:
        bias = "BEARISH"
        event = "BOS"
    elif structural_score >= 2:
        bias = "BULLISH"
        event = "CHoCH" if momentum < 0 else "NONE"
    elif structural_score <= -2:
        bias = "BEARISH"
        event = "CHoCH" if momentum > 0 else "NONE"
    elif structural_score == 1:
        # One-sided structure plus supportive momentum keeps the HTF bias
        # during an ordinary pullback instead of flipping to NEUTRAL.
        if momentum > momentum_threshold or position > 0.58:
            bias = "BULLISH"
            event = "CHoCH" if momentum > momentum_threshold else "NONE"
        else:
            bias = "NEUTRAL"
            event = "NONE"
    elif structural_score == -1:
        if momentum < -momentum_threshold or position < 0.42:
            bias = "BEARISH"
            event = "CHoCH" if momentum < -momentum_threshold else "NONE"
        else:
            bias = "NEUTRAL"
            event = "NONE"
    else:
        # No clean two-swing pattern: only classify if price location and
        # momentum agree strongly. Otherwise remain neutral.
        if position > 0.62 and momentum > momentum_threshold:
            bias = "BULLISH"
            event = "NONE"
        elif position < 0.38 and momentum < -momentum_threshold:
            bias = "BEARISH"
            event = "NONE"
        else:
            bias = "NEUTRAL"
            event = "NONE"

    return {
        "bias": bias,
        "event": event,
        "last_swing_high": last_high,
        "last_swing_low": last_low,
        "structural_score": structural_score,
        "momentum": momentum,
        "range_high": range_high,
        "range_low": range_low,
    }
