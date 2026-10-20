from config import (
    DEFAULT_LOT_SIZE,
    MIN_ATR_SL_MULTIPLIER,
    MIN_RISK_ATR_MULTIPLIER,
    MIN_SCORE,
    MIN_SPREAD_MULTIPLIER,
    MIN_TP1_RR,
    MIN_TP2_RR,
)
from modules.structure import analyze_structure
from modules.orderblock import detect_order_block
from modules.zones import analyze_zones


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
        "NZD/USD": 1.8, "USD/JPY": 1.5,
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


def _liquidity_levels(candles, entry, direction, min_distance, symbol=None):
    levels = []
    start = max(2, len(candles) - 100)
    end = len(candles) - 2
    pip = _pip_size(symbol)

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

    tolerance = pip * 2
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


def _direction_candidates(h4_bias, h1_bias):
    # Candidate directions must use the BUY/SELL vocabulary expected by
    # _build_candidate; HTF bias labels (BULLISH/BEARISH) are not trade directions.
    bias_to_direction = {"BULLISH": "BUY", "BEARISH": "SELL"}
    bullish = "BULLISH"
    bearish = "BEARISH"

    if h4_bias == h1_bias and h4_bias in (bullish, bearish):
        return [bias_to_direction[h4_bias]]

    if h1_bias in (bullish, bearish):
        other = bearish if h1_bias == bullish else bullish
        return [bias_to_direction[h1_bias], bias_to_direction[other]]

    if h4_bias in (bullish, bearish):
        other = bearish if h4_bias == bullish else bullish
        return [bias_to_direction[h4_bias], bias_to_direction[other]]

    return ["BUY", "SELL"]


def _dealing_range(candles, lookback=80, pivot_span=2):
    """Return a dealing range bounded by confirmed H4 swing points.

    A pivot is eligible only after pivot_span candles have closed to its right.
    Return None rather than silently substituting a raw rolling high/low.
    """
    if not isinstance(candles, (list, tuple)) or pivot_span < 1:
        return None
    sample = candles[-lookback:]
    if len(sample) < 2 * pivot_span + 3:
        return None
    highs, lows = [], []
    for i in range(pivot_span, len(sample) - pivot_span):
        hi = float(sample[i]["high"])
        lo = float(sample[i]["low"])
        if all(hi >= float(sample[j]["high"])
               for j in range(i - pivot_span, i + pivot_span + 1) if j != i):
            highs.append((i, hi))
        if all(lo <= float(sample[j]["low"])
               for j in range(i - pivot_span, i + pivot_span + 1) if j != i):
            lows.append((i, lo))
    if not highs or not lows:
        return None
    # Prefer the most recent confirmed swing pair that forms a valid range.
    pairs = [(h, l, max(hi_i, lo_i)) for hi_i, h in highs for lo_i, l in lows if h > l]
    if not pairs:
        return None
    high, low, _ = max(pairs, key=lambda pair: pair[2])
    return {"high": high, "low": low, "equilibrium": (high + low) / 2}


def _price_digits(symbol):
    """Use three decimals for JPY quotes and five for other FX pairs."""
    return 3 if symbol and "JPY" in symbol else 5


def _premium_discount(entry, direction, h4_candles):
    """Classify entry location against the recent H4 range, not noisy M15 range."""
    dealing = _dealing_range(h4_candles)
    if not dealing or dealing["high"] <= dealing["low"]:
        return None, dealing
    if entry == dealing["equilibrium"]:
        return "EQUILIBRIUM", dealing
    if entry > dealing["equilibrium"]:
        return "PREMIUM", dealing
    return "DISCOUNT", dealing


def _structure_confirmed(h4, h1):
    valid_events = {"BOS", "CHoCH", "CHOCH"}
    return h4.get("event") in valid_events or h1.get("event") in valid_events


def _build_candidate(h4, h1, h4_candles, h1_candles, m15_candles, direction, symbol):
    """Build a continuation setup without mandatory sweep, displacement, or FVG filters."""
    wanted = "BULLISH" if direction == "BUY" else "BEARISH"
    if h4["bias"] != wanted or h1["bias"] != wanted:
        return None, f"HTF MISALIGNMENT (H4={h4['bias']}, H1={h1['bias']})"

    # Accept BOS or CHoCH on either aligned HTF; reject setups with no structural event.
    if not _structure_confirmed(h4, h1):
        return None, "NO H4/H1 BOS OR CHoCH CONFIRMATION"

    ob = detect_order_block(m15_candles, wanted)
    if not ob:
        return None, f"NO CONFIRMED {wanted} ORDER BLOCK"

    signal_index = int(ob["signal_index"])
    fvg = _last_aligned_fvg(m15_candles, signal_index, direction)
    # FVG is contextual confluence only; its absence must not block an otherwise valid setup.
    zone_low, zone_high = float(ob["low"]), float(ob["high"])
    digits = _price_digits(symbol)
    entry = round((zone_low + zone_high) / 2, digits)
    atr = _atr(m15_candles)
    if atr <= 0:
        return None, "NO M15 ATR"

    # Structural SL uses the OB boundary plus recent swing context, not a liquidity sweep.
    lookback = m15_candles[max(0, signal_index - 5):signal_index + 1]
    if direction == "BUY":
        structural_low = min([zone_low] + [float(c["low"]) for c in lookback])
        sl = round(structural_low - atr * MIN_ATR_SL_MULTIPLIER, digits)
    else:
        structural_high = max([zone_high] + [float(c["high"]) for c in lookback])
        sl = round(structural_high + atr * MIN_ATR_SL_MULTIPLIER, digits)

    risk = abs(entry - sl)
    pip = _pip_size(symbol)
    risk_pips = risk / pip
    if risk <= 0:
        return None, "INVALID RISK"

    spread_price = _reference_spread_price(symbol)
    min_cost = MIN_SPREAD_MULTIPLIER * spread_price
    min_structural_risk = max(min_cost, atr * MIN_RISK_ATR_MULTIPLIER)
    if risk < min_structural_risk:
        return None, "STRUCTURAL RISK TOO SMALL FOR ATR/SPREAD"

    location, dealing = _premium_discount(entry, direction, h4_candles)
    if dealing is None:
        return None, "INSUFFICIENT H4 DEALING RANGE"
    eq = dealing["equilibrium"]
    if entry < dealing["low"] or entry > dealing["high"]:
        return None, (
            f"ENTRY OUTSIDE H4 DEALING RANGE (range {dealing['low']:.{digits}f}-"
            f"{dealing['high']:.{digits}f}; entry={entry:.{digits}f})"
        )
    if direction == "BUY" and location == "PREMIUM":
        return None, (
            f"BUY IN PREMIUM (H4 range {dealing['low']:.5f}-{dealing['high']:.5f}; "
            f"EQ={eq:.5f}; entry={entry:.5f})"
        )
    if direction == "SELL" and location == "DISCOUNT":
        return None, (
            f"SELL IN DISCOUNT (H4 range {dealing['low']:.5f}-{dealing['high']:.5f}; "
            f"EQ={eq:.5f}; entry={entry:.5f})"
        )

    min_target_distance = max(min_cost, risk * MIN_TP1_RR)
    levels = _liquidity_levels(m15_candles, entry, direction, min_target_distance, symbol)
    tp1_kind = tp2_kind = None
    tp1 = tp2 = None
    for kind, level in levels:
        rr = abs(level - entry) / risk
        if tp1 is None and rr >= MIN_TP1_RR:
            tp1, tp1_kind = level, kind
        elif tp1 is not None and rr >= MIN_TP2_RR:
            tp2, tp2_kind = level, kind
            break

    if tp1 is None:
        return None, "NO LIQUIDITY FAR ENOUGH FOR TP1"
    if tp2 is None:
        return None, "NO EXTERNAL LIQUIDITY FOR TP2"
    if direction == "BUY" and not (sl < entry < tp1 < tp2):
        return None, "DIRECTION/LEVEL MISMATCH — BUY requires SL < entry < TP1 < TP2"
    if direction == "SELL" and not (tp2 < tp1 < entry < sl):
        return None, "DIRECTION/LEVEL MISMATCH — SELL requires TP2 < TP1 < entry < SL"

    zones = analyze_zones(m15_candles)
    score = 5 if h4["event"] == "BOS" and h1["event"] == "BOS" else 4
    if score < MIN_SCORE:
        return None, f"SCORE TOO LOW ({score}/5)"
    tp1_rr = abs(tp1 - entry) / risk
    tp2_rr = abs(tp2 - entry) / risk
    setup = {
        "bias": wanted, "h4_bias": h4["bias"], "h1_bias": h1["bias"],
        "direction": direction, "setup_type": "CONTINUATION",
        "entry": entry, "entry_low": round(zone_low, digits), "entry_high": round(zone_high, digits),
        "sl": sl, "tp1": round(tp1, digits), "tp2": round(tp2, digits),
        "rr": round(tp1_rr, 2), "tp2_rr": round(tp2_rr, 2),
        "score": score, "grade": "S5" if score == 5 else "S4",
        "event": h1["event"] if h1["event"] != "NONE" else h4["event"],
        "fvg": fvg["type"] if fvg else "NONE (OPTIONAL)",
        "sweep": "NOT REQUIRED", "order_block": ob["type"],
        "signal_index": signal_index, "signal_candle": m15_candles[signal_index]["time"],
        "risk_pips": round(risk_pips, 1), "lot_size": DEFAULT_LOT_SIZE,
        "atr_pips": round(atr / pip, 1), "dealing_eq": round(eq, 5), "dealing_high": round(dealing["high"], 5), "dealing_low": round(dealing["low"], 5), "entry_location": location,
        "reference_spread_pips": round(spread_price / pip, 1),
        "tp1_type": tp1_kind, "tp2_type": tp2_kind,
        "nearest_demand": zones["demand"][0] if zones["demand"] else None,
        "nearest_supply": zones["supply"][0] if zones["supply"] else None,
        "key_support": zones["support"], "key_resistance": zones["resistance"],
    }
    return setup, "QUALIFIED"


def analyze_pair_diagnostic(h4_candles, h1_candles, m15_candles, symbol=None):
    h4 = analyze_structure(h4_candles)
    h1 = analyze_structure(h1_candles)

    candidates = []
    diagnostics = []
    dealing = _dealing_range(h4_candles)
    if dealing:
        diagnostics.append(
            f"H4 RANGE low={dealing['low']:.5f} high={dealing['high']:.5f} "
            f"EQ={dealing['equilibrium']:.5f}"
        )
    for direction in _direction_candidates(h4["bias"], h1["bias"]):
        setup, reason = _build_candidate(
            h4, h1, h4_candles, h1_candles, m15_candles, direction, symbol
        )
        label = "BULLISH" if direction == "BUY" else "BEARISH"
        diagnostics.append(f"{label}: {reason}")
        if setup:
            candidates.append(setup)

    if not candidates:
        return None, "; ".join(diagnostics)

    candidates.sort(
        key=lambda s: (
            s["score"],
            s["tp2_rr"],
            -s["risk_pips"],
        ),
        reverse=True,
    )
    return candidates[0], "QUALIFIED"


def analyze_pair(h4_candles, h1_candles, m15_candles, symbol=None):
    setup, _ = analyze_pair_diagnostic(h4_candles, h1_candles, m15_candles, symbol)
    return setup
