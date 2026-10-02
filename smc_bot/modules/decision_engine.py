from modules.structure import analyze_structure
from modules.orderblock import detect_order_block
from modules.fvg import detect_fvg
from modules.liquidity import liquidity_sweep


def analyze_pair_diagnostic(h4_candles, h1_candles, m15_candles):
    """Run the existing decision logic and also explain the first rejection reason."""
    h4 = analyze_structure(h4_candles)
    h1 = analyze_structure(h1_candles)

    if h4["bias"] == "NEUTRAL" or h1["bias"] == "NEUTRAL":
        return None, f"HTF NEUTRAL (H4={h4['bias']}, H1={h1['bias']})"

    if h4["bias"] != h1["bias"]:
        return None, f"H4/H1 MISMATCH (H4={h4['bias']}, H1={h1['bias']})"

    bias = h4["bias"]
    ob = detect_order_block(m15_candles, bias)
    fvg = detect_fvg(m15_candles)
    sweep = liquidity_sweep(m15_candles)

    if not ob:
        return None, f"NO {bias} ORDER BLOCK"

    ob_low = float(ob["low"])
    ob_high = float(ob["high"])

    entry = round((ob_high + ob_low) / 2, 5)

    if bias == "BULLISH":
        sl = round(ob_low, 5)
        risk = entry - sl

        if risk <= 0:
            return None, "INVALID RISK (BUY)"

        tp1 = round(entry + risk * 2, 5)
        tp2 = round(entry + risk * 3, 5)
        direction = "BUY"

    else:
        sl = round(ob_high, 5)
        risk = sl - entry

        if risk <= 0:
            return None, "INVALID RISK (SELL)"

        tp1 = round(entry - risk * 2, 5)
        tp2 = round(entry - risk * 3, 5)
        direction = "SELL"

    score = 2

    if h4["event"] in ("BOS", "CHoCH"):
        score += 1

    if fvg:
        score += 1

    if sweep:
        score += 1

    if score < 3:
        return None, f"SCORE TOO LOW ({score}/5)"

    setup = {
        "bias": bias,
        "direction": direction,
        "entry": entry,
        "entry_low": round(ob_low, 5),
        "entry_high": round(ob_high, 5),
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "rr": "1:2",
        "score": score,
        "grade": {3: "M3", 4: "M4", 5: "M5"}[min(score, 5)],
        "event": h4["event"],
        "fvg": fvg["type"] if fvg else "NONE",
        "sweep": sweep["type"] if sweep else "NONE",
        "order_block": ob["type"],
    }

    return setup, "QUALIFIED"


def analyze_pair(h4_candles, h1_candles, m15_candles):
    setup, _ = analyze_pair_diagnostic(h4_candles, h1_candles, m15_candles)
    return setup
