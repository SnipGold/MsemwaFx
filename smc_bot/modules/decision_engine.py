from config import (
    DEFAULT_LOT_SIZE,
    MAX_TP1_PIPS,
    MIN_ATR_SL_MULTIPLIER,
    MIN_SCORE,
    MIN_SPREAD_MULTIPLIER,
    MIN_TP1_PIPS,
)
from modules.structure import analyze_structure
from modules.orderblock import detect_order_block


def _atr(candles, period=14):
    if len(candles) < period + 1:
        return 0.0

    trs = []
    for i in range(len(candles) - period, len(candles)):
        c = candles[i]
        prev_close = candles[i - 1]["close"]
        trs.append(
            max(
                c["high"] - c["low"],
                abs(c["high"] - prev_close),
                abs(c["low"] - prev_close),
            )
        )
    return sum(trs) / len(trs)


def _pip_size(symbol):
    if symbol and ("JPY" in symbol or "XAU" in symbol):
        return 0.01
    return 0.0001


def _reference_spread_price(symbol):
    # HFM Cent indicative minimums; these are reference values, not live spread.
    ref_spread_pips = {
        "EUR/USD": 1.4,
        "EUR/JPY": 1.3,
        "GBP/USD": 1.6,
        "AUD/USD": 1.6,
        "USD/CHF": 1.5,
        "USD/CAD": 1.9,
        "NZD/USD": 1.8,
    }
    if symbol == "XAU/USD":
        return 0.32
    return ref_spread_pips.get(symbol, 1.5) * _pip_size(symbol)


def _last_aligned_fvg(candles, signal_index, direction):
    if signal_index < 2:
        return None

    c1, _, c3 = candles[signal_index - 2:signal_index + 1]
    if c1["high"] < c3["low"]:
        fvg = {"type": "BULLISH_FVG", "low": c1["high"], "high": c3["low"]}
    elif c1["low"] > c3["high"]:
        fvg = {"type": "BEARISH_FVG", "low": c3["high"], "high": c1["low"]}
    else:
        return None

    expected = "BULLISH_FVG" if direction == "BUY" else "BEARISH_FVG"
    return fvg if fvg["type"] == expected else fvg


def _external_liquidity(candles, entry, direction, min_distance):
    candidates = []
    start = max(2, len(candles) - 80)
    end = len(candles) - 2

    for i in range(start, end + 1):
        if direction == "BUY":
            if candles[i]["high"] > candles[i - 1]["high"] and candles[i]["high"] > candles[i + 1]["high"]:
                level = candles[i]["high"]
                if level >= entry + min_distance:
                    candidates.append(level)
        else:
            if candles[i]["low"] < candles[i - 1]["low"] and candles[i]["low"] < candles[i + 1]["low"]:
                level = candles[i]["low"]
                if level <= entry - min_distance:
                    candidates.append(level)

    if candidates:
        return min(candidates) if direction == "BUY" else max(candidates)
    return None


def analyze_pair_diagnostic(h4_candles, h1_candles, m15_candles, symbol=None):
    h4 = analyze_structure(h4_candles)
    h1 = analyze_structure(h1_candles)

    if h4["bias"] == "NEUTRAL" or h1["bias"] == "NEUTRAL":
        return None, f"HTF NEUTRAL (H4={h4['bias']}, H1={h1['bias']})"

    if h4["bias"] != h1["bias"]:
        return None, f"H4/H1 MISMATCH (H4={h4['bias']}, H1={h1['bias']})"

    bias = h4["bias"]
    direction = "BUY" if bias == "BULLISH" else "SELL"

    ob = detect_order_block(m15_candles, bias)
    if not ob:
        return None, f"NO {bias} SWEEP-LEG OB/DISPLACEMENT"

    signal_index = ob["signal_index"]
    if signal_index >= len(m15_candles):
        return None, "INVALID SIGNAL INDEX"

    fvg = _last_aligned_fvg(m15_candles, signal_index, direction)
    if fvg and fvg["type"] != ("BULLISH_FVG" if direction == "BUY" else "BEARISH_FVG"):
        return None, f"OPPOSING FVG ({fvg['type']})"

    sweep = ob["sweep"]
    expected_sweep = "SELL_SIDE_SWEEP" if direction == "BUY" else "BUY_SIDE_SWEEP"
    if sweep["type"] != expected_sweep:
        return None, f"OPPOSING SWEEP ({sweep['type']})"

    zone_low = float(ob["low"])
    zone_high = float(ob["high"])
    entry = round((zone_low + zone_high) / 2, 5)

    atr = _atr(m15_candles)
    if atr <= 0:
        return None, "NO M15 ATR"

    if direction == "BUY":
        structural_low = min(zone_low, float(sweep["low"]))
        sl = round(structural_low - (atr * MIN_ATR_SL_MULTIPLIER), 5)
    else:
        structural_high = max(zone_high, float(sweep["high"]))
        sl = round(structural_high + (atr * MIN_ATR_SL_MULTIPLIER), 5)

    risk = abs(entry - sl)
    if risk <= 0:
        return None, "INVALID RISK"

    pip = _pip_size(symbol)
    risk_pips = risk / pip
    spread_price = _reference_spread_price(symbol)
    min_tp1_distance = max(MIN_TP1_PIPS * pip, MIN_SPREAD_MULTIPLIER * spread_price)
    max_tp1_distance = MAX_TP1_PIPS * pip

    if min_tp1_distance > max_tp1_distance:
        return None, f"TP1 COST FILTER ({min_tp1_distance / pip:.1f} pips > {MAX_TP1_PIPS:g} pips)"

    tp1_distance = min_tp1_distance
    if 4.0 * pip >= min_tp1_distance:
        tp1_distance = 4.0 * pip

    if direction == "BUY":
        tp1 = round(entry + tp1_distance, 5)
    else:
        tp1 = round(entry - tp1_distance, 5)

    tp2 = _external_liquidity(m15_candles, entry, direction, tp1_distance)
    if tp2 is None:
        return None, "NO EXTERNAL LIQUIDITY BEYOND TP1"

    if direction == "BUY" and tp2 <= tp1:
        return None, "TP2 NOT BEYOND TP1"
    if direction == "SELL" and tp2 >= tp1:
        return None, "TP2 NOT BEYOND TP1"

    recent = m15_candles[max(0, len(m15_candles) - 50):]
    dealing_high = max(c["high"] for c in recent)
    dealing_low = min(c["low"] for c in recent)
    eq = (dealing_high + dealing_low) / 2
    retrace_to_origin = ob["index"] >= max(0, len(m15_candles) - 20)

    if direction == "BUY" and entry > eq and not retrace_to_origin:
        return None, "BUY IN PREMIUM WITHOUT ORIGIN RETRACE"
    if direction == "SELL" and entry < eq and not retrace_to_origin:
        return None, "SELL IN DISCOUNT WITHOUT ORIGIN RETRACE"

    score = 2  # H4/H1 alignment
    if h4["event"] in ("BOS", "CHoCH"):
        score += 1
    if fvg and fvg["type"] == ("BULLISH_FVG" if direction == "BUY" else "BEARISH_FVG"):
        score += 1
    if sweep["type"] == expected_sweep:
        score += 1

    if score < MIN_SCORE:
        return None, f"SCORE TOO LOW ({score}/5)"

    setup = {
        "bias": bias,
        "direction": direction,
        "entry": entry,
        "entry_low": round(zone_low, 5),
        "entry_high": round(zone_high, 5),
        "sl": sl,
        "tp1": tp1,
        "tp2": round(tp2, 5),
        "rr": round(abs(tp1 - entry) / risk, 2),
        "score": score,
        "grade": f"S{score}",
        "event": h4["event"],
        "fvg": fvg["type"] if fvg else "NONE",
        "sweep": sweep["type"],
        "order_block": ob["type"],
        "signal_index": signal_index,
        "signal_candle": m15_candles[signal_index]["time"],
        "risk_pips": round(risk_pips, 1),
        "lot_size": DEFAULT_LOT_SIZE,
        "atr_pips": round(atr / pip, 1),
        "dealing_eq": round(eq, 5),
        "reference_spread_pips": round(spread_price / pip, 1),
    }
    return setup, "QUALIFIED"


def analyze_pair(h4_candles, h1_candles, m15_candles, symbol=None):
    setup, _ = analyze_pair_diagnostic(h4_candles, h1_candles, m15_candles, symbol)
    return setup
