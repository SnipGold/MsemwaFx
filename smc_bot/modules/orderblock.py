def detect_order_block(candles, bias):
    """
    Find a confirmed, relatively fresh order block rather than simply
    taking the nearest opposite-colour candle.

    The old logic selected the most recent opposite candle. That made
    the entry zone move with market price on every 15-minute scan.

    New logic:
      1. Look back through recent M15 candles.
      2. Require an opposite-colour candle.
      3. Require a displacement close through that candle's high/low.
      4. Prefer the most recent candidate that still represents a
         meaningful origin of the move.
    """
    if len(candles) < 12:
        return None

    lookback = min(50, len(candles) - 4)

    for i in range(len(candles) - 4, len(candles) - lookback - 1, -1):
        c = candles[i]

        if bias == "BULLISH" and c["close"] < c["open"]:
            future = candles[i + 1:i + 4]

            # Bullish displacement must close above the OB high.
            if any(x["close"] > c["high"] for x in future):
                return {
                    "type": "BULLISH_OB",
                    "high": c["high"],
                    "low": c["low"],
                    "index": i,
                }

        if bias == "BEARISH" and c["close"] > c["open"]:
            future = candles[i + 1:i + 4]

            # Bearish displacement must close below the OB low.
            if any(x["close"] < c["low"] for x in future):
                return {
                    "type": "BEARISH_OB",
                    "high": c["high"],
                    "low": c["low"],
                    "index": i,
                }

    return None
