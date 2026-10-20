def identify_key_zones(candles, price=None):
    """Estimate nearby demand/supply areas and key swing levels from recent candles."""
    if len(candles) < 10:
        return {"demand": None, "supply": None, "support": None, "resistance": None}
    price = float(price if price is not None else candles[-1]["close"])
    highs, lows = [], []
    start = max(1, len(candles) - 120)
    for i in range(start, len(candles) - 1):
        c, prev, nxt = candles[i], candles[i - 1], candles[i + 1]
        if c["high"] > prev["high"] and c["high"] >= nxt["high"]:
            highs.append(float(c["high"]))
        if c["low"] < prev["low"] and c["low"] <= nxt["low"]:
            lows.append(float(c["low"]))
    below = sorted((x for x in lows if x <= price), reverse=True)
    above = sorted(x for x in highs if x >= price)
    recent = candles[-14:]
    avg_range = sum(float(c["high"]) - float(c["low"]) for c in recent) / len(recent)
    tolerance = max(avg_range * 0.25, abs(price) * 0.00005)

    def make_zone(levels):
        if not levels:
            return None
        anchor = levels[0]
        cluster = [x for x in levels if abs(x - anchor) <= tolerance]
        return {"low": round(min(cluster), 5), "high": round(max(cluster), 5)}

    return {
        "demand": make_zone(below),
        "supply": make_zone(above),
        "support": round(below[0], 5) if below else None,
        "resistance": round(above[0], 5) if above else None,
    }
