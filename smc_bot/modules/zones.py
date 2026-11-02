"""Demand/supply zones and directionally valid key levels from OHLC candles.

Pure Python; no pandas dependency. Input is normalized to chronological order
when ISO timestamps are available. A support level must be fully below the
latest close; a resistance level must be fully above it. Zones containing the
current price remain zones, but are not mislabeled as support/resistance.
"""
from datetime import datetime, timezone
from math import isfinite


def _valid(c):
    try:
        o, h, l, cl = (float(c[k]) for k in ("open", "high", "low", "close"))
    except (KeyError, TypeError, ValueError):
        return False
    return all(isfinite(x) for x in (o, h, l, cl)) and h >= max(o, cl, l) and l <= min(o, cl, h)


def _chronological(candles):
    """Sort ISO-dated candles oldest-to-newest when every row has a valid time."""
    rows = list(candles)
    dated = []
    for candle in rows:
        if not isinstance(candle, dict) or not candle.get("time"):
            return rows
        try:
            value = str(candle["time"]).replace("Z", "+00:00")
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            dated.append((parsed, candle))
        except (TypeError, ValueError):
            return rows
    return [c for _, c in sorted(dated, key=lambda item: item[0])]


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


def _directional_key_levels(demand, supply, last_close):
    """Never return support above price or resistance below price."""
    below = [z for z in demand if float(z["high"]) <= last_close]
    above = [z for z in supply if float(z["low"]) >= last_close]
    support = max((float(z["high"]) for z in below), default=None)
    resistance = min((float(z["low"]) for z in above), default=None)
    return (
        round(support, 6) if support is not None else None,
        round(resistance, 6) if resistance is not None else None,
    )


def analyze_zones(candles, lookback=160, pivot_span=3, merge_atr=0.25, max_zones=3):
    """Return active demand/supply zones and correctly sided key levels.

    A pivot is only considered after pivot_span candles have formed to its
    right, avoiding look-ahead in a live scan. Invalid input rows are skipped.
    """
    if not isinstance(candles, (list, tuple)) or pivot_span < 1 or max_zones < 1:
        return {"demand": [], "supply": [], "support": None, "resistance": None, "atr": 0.0}
    ordered = _chronological(candles)
    data = [c for c in ordered[-lookback:] if isinstance(c, dict) and _valid(c)]
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
            later = data[i + 1:]
            broken = (
                any(float(x["close"]) < low for x in later)
                if kind == "demand"
                else any(float(x["close"]) > high for x in later)
            )
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
        found[kind] = valid

    support, resistance = _directional_key_levels(
        found["demand"], found["supply"], last_close
    )
    return {
        "demand": found["demand"][:max_zones],
        "supply": found["supply"][:max_zones],
        "support": support,
        "resistance": resistance,
        "current_price": round(last_close, 6),
        "atr": round(atr, 6),
    }
