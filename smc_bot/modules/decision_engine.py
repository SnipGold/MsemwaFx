from config import (
    DEFAULT_LOT_SIZE,
    MIN_ATR_SL_MULTIPLIER,
    MIN_SCORE,
    MIN_SPREAD_MULTIPLIER,
    MIN_TP1_RR,
    MIN_TP2_RR,
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
        trs.append(max(
            c["high"] - c["low"],
            abs(c["high"] - prev_close),
            abs(c["low"] - prev_close),
        ))
    return sum(trs) / len(trs)


def _pip_size(symbol):
    if symbol and ("JPY" in symbol or "XAU" in symbol):
        return 0.01
    return 0.0001


def _reference_spread_price(symbol):
    ref_spread_pips = {
        "EUR/USD": 1.4, "EUR/JPY": 1.3, "GBP/USD": 1.6,
        "AUD/USD": 1.6, "USD/CHF": 1.5, "USD/CAD": 1.9,
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
    return fvg if fvg["type"] == expected else None


def _liquidity_levels(candles, entry, direction, min_distance):
    """Return meaningful internal/external liquidity levels beyond entry."""
    levels = []
    start = max(2, len(candles) - 100)
    end = len(candles) - 2

    for i in range(start, end + 1):
        if direction == "BUY":
            if candles[i]["high"] > candles[i-1]["high"] and candles[i]["high"] > candles[i+1]["high"]:
                level = float(candles[i]["high"])
                if level > entry + min_distance:
                    levels.append(("SWING_HIGH", level))
        else:
            if candles[i]["low"] < candles[i-1]["low"] and candles[i]["low"] < candles[i+1]["low"]:
                level = float(candles[i]["low"])
                if level < entry - min_distance:
                    levels.append(("SWING_LOW", level))

    # Equal highs/lows are particularly important liquidity pools.
    tolerance = _pip_size(None) * 2
    for i in range(start, end):
        a = float(candles[i]["high"] if direction == "BUY" else candles[i]["low"])
        for j in range(i + 1, min(end + 1, i + 12)):
            b = float(candles[j]["high"] if direction == "BUY" else candles[j]["low"])
            if abs(a - b) <= tolerance:
                level = max(a, b) if direction == "BUY" else min(a, b)
                if (direction == "BUY" and level > entry + min_distance) or (
                    direction == "SELL" and level < entry - min_distance
                ):
                    levels.append(("EQUAL_LIQUIDITY", level))

    unique = {}
    for kind, level in levels:
        unique[round(level, 6)] = (kind, level)

    return sorted(
        unique.values(),
        key=lambda x: x[1],
        reverse=direction == "SELL",
    )


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
    fvg = _last_aligned_fvg(m15_candles, signal_index, direction)
    if fvg is None:
        return None, "NO ALIGNED FVG"

    sweep = ob["sweep"]
    expected_sweep = "SELL_SIDE_SWEEP" if direction == "BUY" else "BUY_SIDE_SWEEP"
    if sweep["type"] != expected_sweep:
        return None, f"OPPOSING SWEEP ({sweep['type']})"

    zone_low, zone_high = float(ob["low"]), float(ob["high"])
    entry = round((zone_low + zone_high) / 2, 5)
    atr = _atr(m15_candles)
    if atr <= 0:
        return None, "NO M15 ATR"

    if direction == "BUY":
        structural_low = min(zone_low, float(sweep["low"]))
        sl = round(structural_low - atr * MIN_ATR_SL_MULTIPLIER, 5)
    else:
        structural_high = max(zone_high, float(sweep["high"]))
        sl = round(structural_high + atr * MIN_ATR_SL_MULTIPLIER, 5)

    risk = abs(entry - sl)
    pip = _pip_size(symbol)
    risk_pips = risk / pip
    if risk <= 0:
        return None, "INVALID RISK"

    spread_price = _reference_spread_price(symbol)
    min_cost = MIN_SPREAD_MULTIPLIER * spread_price
    if risk < min_cost:
        return None, "RISK TOO SMALL FOR SPREAD"

    recent = m15_candles[max(0, len(m15_candles) - 60):]
    dealing_high = max(c["high"] for c in recent)
    dealing_low = min(c["low"] for c in recent)
    eq = (dealing_high + dealing_low) / 2

    if direction == "BUY" and entry > eq:
        return None, "BUY IN PREMIUM"
    if direction == "SELL" and entry < eq:
        return None, "SELL IN DISCOUNT"

    min_target_distance = max(min_cost, risk * MIN_TP1_RR)
    levels = _liquidity_levels(m15_candles, entry, direction, min_target_distance)

    tp1_kind = tp2_kind = None
    tp1 = tp2 = None
    for kind, level in levels:
        if direction == "BUY":
            rr = (level - entry) / risk
        else:
            rr = (entry - level) / risk
        if tp1 is None and rr >= MIN_TP1_RR:
            tp1, tp1_kind = level, kind
            continue
        if tp1 is not None and rr >= MIN_TP2_RR:
            tp2, tp2_kind = level, kind
            break

    if tp1 is None:
        return None, "NO LIQUIDITY FAR ENOUGH FOR TP1"
    if tp2 is None:
        return None, "NO EXTERNAL LIQUIDITY FOR TP2"

    score = 2
    if h4["event"] in ("BOS", "CHoCH") or h1["event"] in ("BOS", "CHoCH"):
        score += 1
    score += 1  # aligned FVG is a hard gate above
    score += 1  # aligned liquidity sweep is a hard gate above

    if score < MIN_SCORE:
        return None, f"SCORE TOO LOW ({score}/5)"

    tp1_rr = abs(tp1 - entry) / risk
    tp2_rr = abs(tp2 - entry) / risk
    setup = {
        "bias": bias, "direction": direction,
        "entry": entry,
        "entry_low": round(zone_low, 5),
        "entry_high": round(zone_high, 5),
        "sl": sl,
        "tp1": round(tp1, 5),
        "tp2": round(tp2, 5),
        "rr": round(tp1_rr, 2),
        "tp2_rr": round(tp2_rr, 2),
        "score": score, "grade": f"S{score}",
        "event": h1["event"] if h1["event"] != "NONE" else h4["event"],
        "fvg": fvg["type"],
        "sweep": sweep["type"],
        "order_block": ob["type"],
        "signal_index": signal_index,
        "signal_candle": m15_candles[signal_index]["time"],
        "risk_pips": round(risk_pips, 1),
        "lot_size": DEFAULT_LOT_SIZE,
        "atr_pips": round(atr / pip, 1),
        "dealing_eq": round(eq, 5),
        "reference_spread_pips": round(spread_price / pip, 1),
        "tp1_type": tp1_kind,
        "tp2_type": tp2_kind,
    }
    return setup, "QUALIFIED"


def analyze_pair(h4_candles, h1_candles, m15_candles, symbol=None):
    setup, _ = analyze_pair_diagnostic(h4_candles, h1_candles, m15_candles, symbol)
    return setup
