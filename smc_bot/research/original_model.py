"""Legacy/original entry model preserved for offline comparison only.

This intentionally reproduces the pre-sweep-gated decision logic. Do not import
this module into the live scanner. Risk controls should be applied by the
backtest/execution harness before any simulated order is accepted.
"""
from modules.structure import analyze_structure
from modules.orderblock import detect_order_block
from modules.fvg import detect_fvg
from modules.liquidity import liquidity_sweep


def analyze_original(h4_candles, h1_candles, m15_candles):
    """Return a legacy-style setup, or None.

    Original logic: H4/H1 bias must agree; an OB is required; FVG and sweep
    are recorded as context, not mandatory entry gates. Targets are 2R/3R.
    """
    if not h4_candles or not h1_candles or not m15_candles:
        return None

    h4 = analyze_structure(h4_candles)
    h1 = analyze_structure(h1_candles)
    if h4["bias"] != h1["bias"]:
        return None

    bias = h4["bias"]
    if bias not in ("BULLISH", "BEARISH"):
        return None

    ob = detect_order_block(m15_candles, bias)
    if not ob:
        return None

    fvg = detect_fvg(m15_candles)
    sweep = liquidity_sweep(m15_candles)
    entry = (float(ob["high"]) + float(ob["low"])) / 2

    if bias == "BULLISH":
        sl = float(ob["low"])
        risk = entry - sl
        direction = "BUY"
        tp1, tp2 = entry + 2 * risk, entry + 3 * risk
    else:
        sl = float(ob["high"])
        risk = sl - entry
        direction = "SELL"
        tp1, tp2 = entry - 2 * risk, entry - 3 * risk

    if risk <= 0:
        return None

    return {
        "model": "ORIGINAL",
        "bias": bias,
        "direction": direction,
        "entry": round(entry, 5),
        "sl": round(sl, 5),
        "tp1": round(tp1, 5),
        "tp2": round(tp2, 5),
        "rr": 2.0,
        "tp2_rr": 3.0,
        "event": h4.get("event", "NONE"),
        "fvg": fvg["type"] if fvg else "NONE",
        "sweep": sweep["type"] if sweep else "NONE",
        "order_block": ob["type"],
    }
