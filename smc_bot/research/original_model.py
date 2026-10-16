"""Legacy pre-sweep-gated model, for offline comparison only."""
from modules.structure import analyze_structure
from modules.fvg import detect_fvg
from modules.liquidity import liquidity_sweep


def _legacy_order_block(candles, bias):
    # Historical detector: latest opposing candle, with no sweep requirement.
    if len(candles) < 4:
        return None
    for i in range(len(candles) - 2, -1, -1):
        c = candles[i]
        if bias == "BULLISH" and c["close"] < c["open"]:
            return {"type": "BULLISH_OB", "high": c["high"], "low": c["low"], "index": i}
        if bias == "BEARISH" and c["close"] > c["open"]:
            return {"type": "BEARISH_OB", "high": c["high"], "low": c["low"], "index": i}
    return None


def analyze_original(h4_candles, h1_candles, m15_candles):
    if not h4_candles or not h1_candles or not m15_candles:
        return None
    h4, h1 = analyze_structure(h4_candles), analyze_structure(h1_candles)
    if h4["bias"] != h1["bias"] or h4["bias"] not in ("BULLISH", "BEARISH"):
        return None
    bias = h4["bias"]
    ob = _legacy_order_block(m15_candles, bias)
    if not ob:
        return None
    fvg, sweep = detect_fvg(m15_candles), liquidity_sweep(m15_candles)
    entry = (float(ob["high"]) + float(ob["low"])) / 2
    if bias == "BULLISH":
        sl, direction = float(ob["low"]), "BUY"
        risk = entry - sl
        tp1, tp2 = entry + 2*risk, entry + 3*risk
    else:
        sl, direction = float(ob["high"]), "SELL"
        risk = sl - entry
        tp1, tp2 = entry - 2*risk, entry - 3*risk
    if risk <= 0:
        return None
    return {"model":"ORIGINAL","bias":bias,"direction":direction,
            "entry":round(entry,5),"sl":round(sl,5),"tp1":round(tp1,5),
            "tp2":round(tp2,5),"rr":2.0,"tp2_rr":3.0,
            "event":h4.get("event","NONE"),"fvg":fvg["type"] if fvg else "NONE",
            "sweep":sweep["type"] if sweep else "NONE","order_block":ob["type"],
            "signal_index":len(m15_candles)-1}
