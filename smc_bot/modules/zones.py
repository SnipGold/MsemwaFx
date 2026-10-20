"""Demand/supply zones and key levels from OHLC candles.

Pure Python; no pandas dependency. Zones are based on confirmed pivot candles,
merged when nearby, and invalidated by a later close through the distal edge.
This is a context/validation module, not a standalone trade-entry signal.
"""
from math import isfinite


def _valid(c):
    try:
        o, h, l, cl = (float(c[k]) for k in ("open", "high", "low", "close"))
    except (KeyError, TypeError, ValueError):
        return False
    return all(isfinite(x) for x in (o, h, l, cl)) and h >= max(o, cl, l) and l <= min(o, cl, h)


def _atr(candles, period=14):
    if len(candles) < 2:
        return 0.0
    tr = []
    for i in range(1, len(candles)):
        c, prev = candles[i], candles[i - 1]
        tr.append(max(float(c["high"]) - float(c["low"]),
                      abs(float(c["high"]) - float(prev["close"])),
                      abs(float(c["low"]) - float(prev["close"]))))
    sample = tr[-period:]
    return sum(sample) / len(sample) if sample else 0.0


def _pivot(candles, i, span, kind):
    c = candles[i]
    if kind == "supply":
        value = float(c["high"])
        return all(value >= float(candles[j]["high"]) for j in range(i-span, i+span+1) if j != i)
    value = float(c["low"])
    return all(value <= float(candles[j]["low"]) for j in range(i-span, i+span+1) if j != i)


def analyze_zones(candles, lookback=160, pivot_span=3, merge_atr=0.25, max_zones=3):
    """Return active demand/supply zones and nearest key levels.

    Input candles must be chronological OHLC dictionaries. A pivot is only
    considered after pivot_span candles have formed to its right, avoiding
    look-ahead in a live scan. Invalid input rows are skipped.
    """
    if not isinstance(candles, (list, tuple)) or pivot_span < 1 or max_zones < 1:
        return {"demand": [], "supply": [], "support": None, "resistance": None, "atr": 0.0}
    data = [c for c in candles[-lookback:] if isinstance(c, dict) and _valid(c)]
    if len(data) < max(2 * pivot_span + 3, 15):
        return {"demand": [], "supply": [], "support": None, "resistance": None, "atr": _atr(data)}
    atr = _atr(data)
    merge_distance = max(atr * merge_atr, 1e-12)
    last_close = float(data[-1]["close"])
    found = {"demand": [], "supply": []}

    for kind in ("demand", "supply"):
        for i in range(pivot_span, len(data) - pivot_span):
            if not _pivot(data, i, pivot_span, kind):
                continue
            c = data[i]
            o, h, l, cl = (float(c[k]) for k in ("open", "high", "low", "close"))
            if kind == "demand":
                low, high = l, min(o, cl)
            else:
                low, high = max(o, cl), h
            # Any later close through the far edge invalidates the zone.
            later = data[i + 1:]
            broken = any(float(x["close"]) < low for x in later) if kind == "demand" else any(float(x["close"]) > high for x in later)
            if broken:
                continue
            touches = sum(
                1 for x in later
                if float(x["low"]) <= high and float(x["high"]) >= low
            )
            age = len(data) - 1 - i
            found[kind].append({
                "low": round(low, 6), "high": round(high, 6),
                "origin_index": i, "age_candles": age, "touches": touches,
                "fresh": touches == 0, "strength": max(1, 3 - min(touches, 2)),
            })

    # Merge overlapping/nearby zones; preserve freshest origin and accumulate touches.
    for kind in ("demand", "supply"):
        merged = []
        for z in sorted(found[kind], key=lambda x: x["low"]):
            match = next((m for m in merged if z["low"] <= m["high"] + merge_distance
                          and z["high"] >= m["low"] - merge_distance), None)
            if match is None:
                merged.append(dict(z))
            else:
                match["low"] = round(min(match["low"], z["low"]), 6)
                match["high"] = round(max(match["high"], z["high"]), 6)
                match["touches"] = max(match["touches"], z["touches"])
                match["age_candles"] = min(match["age_candles"], z["age_candles"])
                match["fresh"] = match["touches"] == 0
                match["strength"] = max(1, 3 - min(match["touches"], 2))
                match["origin_index"] = max(match["origin_index"], z["origin_index"])
        if kind == "demand":
            valid = [z for z in merged if z["low"] <= last_close]
            valid.sort(key=lambda z: (abs(last_close - z["high"]), z["touches"], z["age_candles"]))
        else:
            valid = [z for z in merged if z["high"] >= last_close]
            valid.sort(key=lambda z: (abs(z["low"] - last_close), z["touches"], z["age_candles"]))
        found[kind] = valid[:max_zones]

    support = max((z["high"] for z in found["demand"]), default=None)
    resistance = min((z["low"] for z in found["supply"]), default=None)
    return {
        "demand": found["demand"], "supply": found["supply"],
        "support": round(support, 6) if support is not None else None,
        "resistance": round(resistance, 6) if resistance is not None else None,
        "atr": round(atr, 6),
    }
