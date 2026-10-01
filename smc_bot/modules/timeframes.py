from collections import defaultdict
from datetime import datetime, timezone

def parse_time(value):
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def closed_m15(candles):
    now = datetime.now(timezone.utc).timestamp()
    out = []
    for candle in candles:
        try:
            dt = parse_time(candle["time"])
        except (TypeError, ValueError):
            continue
        if dt.timestamp() + 15 * 60 <= now:
            item = dict(candle)
            item["_dt"] = dt
            out.append(item)
    return out

def _aggregate(group):
    group = sorted(group, key=lambda c: c["_dt"])
    return {"time": group[0]["time"], "open": group[0]["open"],
            "high": max(c["high"] for c in group),
            "low": min(c["low"] for c in group),
            "close": group[-1]["close"]}

def resample_m15(candles, minutes):
    buckets = defaultdict(list)
    for candle in candles:
        dt = candle.get("_dt")
        if dt is None:
            try:
                dt = parse_time(candle["time"])
            except (TypeError, ValueError):
                continue
        total_minutes = dt.hour * 60 + dt.minute
        bucket_minutes = (total_minutes // minutes) * minutes
        bucket = dt.replace(hour=bucket_minutes // 60,
                            minute=bucket_minutes % 60,
                            second=0, microsecond=0)
        buckets[bucket].append(candle)
    expected = minutes // 15
    return [_aggregate(group) for _, group in sorted(buckets.items())
            if len(group) == expected]

def build_htf(m15_candles):
    clean = closed_m15(m15_candles)
    return (resample_m15(clean, 240), resample_m15(clean, 60),
            [{k:v for k,v in c.items() if k != "_dt"} for c in clean])
