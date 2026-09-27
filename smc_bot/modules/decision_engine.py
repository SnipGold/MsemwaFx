from modules.structure import analyze_structure
from modules.orderblock import detect_order_block
from modules.fvg import detect_fvg
from modules.liquidity import liquidity_sweep

def analyze_pair(h4_candles, h1_candles, m15_candles):
    h4 = analyze_structure(h4_candles)
    h1 = analyze_structure(h1_candles)

    # H4 na H1 lazima zikubaliane
    if h4["bias"] != h1["bias"]:
        return None

    bias = h4["bias"]

    ob = detect_order_block(m15_candles, bias)
    fvg = detect_fvg(m15_candles)
    sweep = liquidity_sweep(m15_candles)

    if not ob:
        return None

    entry = round((ob["high"] + ob["low"]) / 2, 5)

    if bias == "BULLISH":
        sl = round(ob["low"], 5)
        risk = entry - sl
        tp1 = round(entry + risk * 2, 5)
        tp2 = round(entry + risk * 3, 5)
        direction = "BUY"
    else:
        sl = round(ob["high"], 5)
        risk = sl - entry
        tp1 = round(entry - risk * 2, 5)
        tp2 = round(entry - risk * 3, 5)
        direction = "SELL"

    return {
        "bias": bias,
        "direction": direction,
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "rr": "1:2",
        "event": h4["event"],
        "fvg": fvg["type"] if fvg else "NONE",
        "sweep": sweep["type"] if sweep else "NONE",
        "order_block": ob["type"],
    }
