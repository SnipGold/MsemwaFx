import csv
from datetime import datetime, timedelta
from statistics import median
from pathlib import Path

ROOT = Path("replay_data")  # historical GBPUSD replay
OUT = Path("replay_results.csv")

def load(path):
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f, delimiter=";"):
            rows.append({
                "time": datetime.fromisoformat(r["datetime"]),
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
            })
    return rows

m15 = load(ROOT / "GBPUSD_15min.csv")
h1 = load(ROOT / "GBPUSD_1h.csv")
h4 = load(ROOT / "GBPUSD_4h.csv")

def atr(rows, i, n=14):
    if i < 1:
        return 0.0
    vals = []
    start = max(1, i-n+1)
    for j in range(start, i+1):
        vals.append(max(rows[j]["high"]-rows[j]["low"],
                        abs(rows[j]["high"]-rows[j-1]["close"]),
                        abs(rows[j]["low"]-rows[j-1]["close"])))
    return sum(vals)/len(vals)

def body(r):
    return abs(r["close"]-r["open"])

def bias_at(rows, t, lookback=12):
    x = [r for r in rows if r["time"] <= t]
    if len(x) < 8:
        return "NEUTRAL"
    x = x[-lookback:]
    recent = x[-4:]
    hi = max(r["high"] for r in recent)
    lo = min(r["low"] for r in recent)
    c = recent[-1]["close"]
    rng = hi - lo
    if rng <= 0:
        return "NEUTRAL"
    pos = (c - lo) / rng
    up = sum(recent[i]["close"] > recent[i-1]["close"] for i in range(1,len(recent)))
    dn = sum(recent[i]["close"] < recent[i-1]["close"] for i in range(1,len(recent)))
    # HTF campaign bias: recent displacement/close location, not just a
    # mechanical HH/LL count. This allows a pullback inside an intact trend.
    if pos >= 0.55 and up >= 2:
        return "BULLISH"
    if pos <= 0.45 and dn >= 2:
        return "BEARISH"
    return "NEUTRAL"

def htf_bias(t):
    a = bias_at(h4, t, 8)
    b = bias_at(h1, t, 12)
    if a == b and a != "NEUTRAL":
        return a
    return "NEUTRAL"

def known_levels(rows, i, direction):
    # Levels visible before the signal only.
    x = rows[max(0, i-96):i]
    if direction == "BUY":
        vals = [r["high"] for r in x]
        return sorted(set(round(v,5) for v in vals if v > rows[i]["close"]))
    vals = [r["low"] for r in x]
    return sorted(set(round(v,5) for v in vals if v < rows[i]["close"]), reverse=True)

def find_setup(i):
    if i < 40:
        return None
    r = m15[i]
    bias = htf_bias(r["time"])
    if bias == "NEUTRAL":
        return None
    look = m15[max(0,i-8):i]
    prior_low = min(x["low"] for x in look)
    prior_high = max(x["high"] for x in look)
    sweep_dir = None
    if bias == "BULLISH" and r["low"] < prior_low and r["close"] > prior_low:
        sweep_dir = "BUY"
    elif bias == "BEARISH" and r["high"] > prior_high and r["close"] < prior_high:
        sweep_dir = "SELL"
    if not sweep_dir:
        return None

    a = atr(m15, i, 14)
    med_body = median(body(x) for x in m15[max(1,i-20):i])
    # Search for displacement on the sweep candle or within the next 3 candles.
    disp = None
    for j in range(i, min(i+4, len(m15))):
        q = m15[j]
        recent = m15[max(0,j-5):j]
        if not recent:
            continue
        if sweep_dir == "BUY":
            broke = q["close"] > max(x["high"] for x in recent)
            strong = q["close"] > q["open"] and body(q) >= max(med_body*1.15, a*0.45)
        else:
            broke = q["close"] < min(x["low"] for x in recent)
            strong = q["close"] < q["open"] and body(q) >= max(med_body*1.15, a*0.45)
        if broke and strong:
            disp = j
            break
    if disp is None:
        return None

    # Structural OB: last opposite candle before displacement, after the sweep.
    ob = None
    for j in range(disp-1, i-1, -1):
        q = m15[j]
        if sweep_dir == "BUY" and q["close"] < q["open"]:
            ob = j
            break
        if sweep_dir == "SELL" and q["close"] > q["open"]:
            ob = j
            break
    if ob is None:
        return None

    zone_low = m15[ob]["low"]
    zone_high = m15[ob]["high"]
    entry = (zone_low + zone_high)/2

    sweep_extreme = r["low"] if sweep_dir == "BUY" else r["high"]
    structural_sl = sweep_extreme - a*0.15 if sweep_dir == "BUY" else sweep_extreme + a*0.15
    risk = entry-structural_sl if sweep_dir == "BUY" else structural_sl-entry
    if risk <= 0 or risk > a*2.5:
        return None

    # Liquidity target known before entry: nearest meaningful prior range extreme.
    levels = known_levels(m15, disp, sweep_dir)
    if not levels:
        return None
    if sweep_dir == "BUY":
        tp2 = next((v for v in levels if v > entry + risk*2.0), None)
        if tp2 is None:
            return None
        tp1_candidates = [v for v in levels if entry < v < tp2]
        tp1 = tp1_candidates[0] if tp1_candidates else entry + risk*1.0
    else:
        tp2 = next((v for v in levels if v < entry - risk*2.0), None)
        if tp2 is None:
            return None
        tp1_candidates = [v for v in levels if tp2 < v < entry]
        tp1 = tp1_candidates[0] if tp1_candidates else entry - risk*1.0

    rr2 = abs(tp2-entry)/risk
    if rr2 < 2.0:
        return None

    return {
        "signal_i": i, "disp_i": disp, "ob_i": ob,
        "time": r["time"], "direction": sweep_dir, "bias": bias,
        "sweep": "SELL_SIDE_SWEEP" if sweep_dir=="BUY" else "BUY_SIDE_SWEEP",
        "entry": entry, "zone_low": zone_low, "zone_high": zone_high,
        "sl": structural_sl, "risk": risk, "tp1": tp1, "tp2": tp2,
        "rr2": rr2, "atr": a
    }

def evaluate(s):
    # Entry must occur after displacement/OB formation; no hindsight entry.
    start = s["disp_i"] + 1
    expiry = min(start + 16, len(m15)-1)
    for j in range(start, expiry+1):
        r = m15[j]
        if s["direction"] == "BUY":
            if r["low"] <= s["sl"]:
                return "INVALIDATED", None, j
            if r["low"] <= s["entry"] <= r["high"]:
                # Once entry occurs, evaluate future candles.
                for k in range(j, min(j+48,len(m15))):
                    q=m15[k]
                    hit_tp2=q["high"]>=s["tp2"]
                    hit_tp1=q["high"]>=s["tp1"]
                    hit_sl=q["low"]<=s["sl"]
                    if hit_sl and (hit_tp2 or hit_tp1):
                        return "AMBIGUOUS", 0.0, k
                    if hit_tp2:
                        return "TP2", s["rr2"], k
                    if hit_tp1:
                        # Keep position open for TP2, but record TP1 milestone.
                        for z in range(k+1, min(k+48,len(m15))):
                            w=m15[z]
                            if w["low"]<=s["sl"]:
                                return "TP1_THEN_SL", 1.0, z
                            if w["high"]>=s["tp2"]:
                                return "TP2_AFTER_TP1", s["rr2"], z
                        return "TP1", 1.0, k
                return "OPEN", None, j
        else:
            if r["high"] >= s["sl"]:
                return "INVALIDATED", None, j
            if r["low"] <= s["entry"] <= r["high"]:
                for k in range(j, min(j+48,len(m15))):
                    q=m15[k]
                    hit_tp2=q["low"]<=s["tp2"]
                    hit_tp1=q["low"]<=s["tp1"]
                    hit_sl=q["high"]>=s["sl"]
                    if hit_sl and (hit_tp2 or hit_tp1):
                        return "AMBIGUOUS", 0.0, k
                    if hit_tp2:
                        return "TP2", s["rr2"], k
                    if hit_tp1:
                        for z in range(k+1, min(k+48,len(m15))):
                            w=m15[z]
                            if w["high"]>=s["sl"]:
                                return "TP1_THEN_SL", 1.0, z
                            if w["low"]<=s["tp2"]:
                                return "TP2_AFTER_TP1", s["rr2"], z
                        return "TP1", 1.0, k
                return "OPEN", None, j
    return "MISSED", None, expiry

results=[]
last_signal=-999
for i in range(40, len(m15)-20):
    r=m15[i]
    # Skip weekend data.
    if r["time"].weekday() >= 5:
        continue
    s=find_setup(i)
    if not s:
        continue
    if i-last_signal < 12:
        continue
    outcome, rr, exit_i = evaluate(s)
    if outcome == "MISSED":
        # Still useful: it was a valid plan but never retraced.
        pass
    results.append({
        "signal_time":s["time"].isoformat(),
        "direction":s["direction"],
        "htf_bias":s["bias"],
        "sweep":s["sweep"],
        "ob_time":m15[s["ob_i"]]["time"].isoformat(),
        "entry":round(s["entry"],5),
        "sl":round(s["sl"],5),
        "risk_pips":round(s["risk"]*10000,1),
        "tp1":round(s["tp1"],5),
        "tp2":round(s["tp2"],5),
        "rr2":round(s["rr2"],2),
        "outcome":outcome,
        "realized_R":"" if rr is None else round(rr,2),
        "exit_time":"" if exit_i is None else m15[exit_i]["time"].isoformat(),
    })
    last_signal=i

with open(OUT,"w",newline="") as f:
    fields=list(results[0].keys()) if results else ["signal_time"]
    w=csv.DictWriter(f,fieldnames=fields)
    w.writeheader(); w.writerows(results)

print("SETUPS",len(results))
from collections import Counter
print("OUTCOMES",dict(Counter(r["outcome"] for r in results)))
print("DATES")
for r in results:
    print(r)
