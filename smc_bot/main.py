import json
import os
import time
from datetime import datetime, timedelta, timezone

from config import M15_OUTPUTSIZE, SENT_TTL, SETUP_EXPIRY_CANDLES, SYMBOLS
from modules.decision_engine import analyze_pair_diagnostic
from modules.notifier import (
    format_alert,
    format_scout,
    send_telegram,
    send_telegram_scout,
    send_whatsapp,
)
from modules.timeframes import build_htf, parse_time
from modules.structure import analyze_structure
from modules.twelvedata import get_candles

CACHE_DIR = "data_cache"
SENT_FILE = "sent.json"
os.makedirs(CACHE_DIR, exist_ok=True)


def cached_m15(symbol):
    path = os.path.join(CACHE_DIR, f"{symbol.replace('/', '_')}_15min.json")
    now = time.time()

    try:
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)
        if saved.get("data") and len(saved["data"]) >= M15_OUTPUTSIZE and now - float(saved.get("time", 0)) < 900:
            return saved["data"]
    except (FileNotFoundError, ValueError, TypeError, OSError):
        pass

    data = get_candles(symbol, "15min", M15_OUTPUTSIZE)
    if data:
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"time": now, "data": data}, f)
        except OSError:
            pass
    return data


def load_sent():
    try:
        with open(SENT_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError, TypeError, OSError):
        return {}


def save_sent(data):
    try:
        with open(SENT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError as exc:
        print(f"Could not save state: {exc}")


def market_closed_or_near_close(now=None):
    """Conservative UTC guard: no new setups Saturday, early Sunday or late Friday."""
    now = now or datetime.now(timezone.utc)
    weekday = now.weekday()
    minutes = now.hour * 60 + now.minute

    if weekday == 5:
        return True, "MARKET CLOSED (SATURDAY)"
    if weekday == 6 and minutes < 21 * 60 + 15:
        return True, "MARKET CLOSED (SUNDAY PRE-OPEN)"
    if weekday == 4 and minutes >= 20 * 60:
        return True, "NEAR FRIDAY CLOSE"
    return False, ""


def _touches(candle, level):
    return candle["low"] <= level <= candle["high"]


def evaluate_entry_path(setup, m15):
    """Replay candles after the signal and report the latest valid trade state.

    Never report an old entry touch as currently triggered if later candles
    already reached SL or TP1. Intrabar order is unknown when key levels share
    the same M15 candle, so those cases are marked ambiguous.
    """
    signal_index = int(setup["signal_index"])
    entry = float(setup["entry"])
    sl = float(setup["sl"])
    tp1 = float(setup["tp1"])
    entered = False

    for candle in m15[signal_index + 1:]:
        hit_entry = _touches(candle, entry)
        if setup["direction"] == "BUY":
            hit_sl = candle["low"] <= sl
            hit_tp1 = candle["high"] >= tp1
        else:
            hit_sl = candle["high"] >= sl
            hit_tp1 = candle["low"] <= tp1

        if not entered:
            if hit_entry and (hit_sl or hit_tp1):
                return "AMBIGUOUS", "Entry and SL/TP1 share an M15 candle; intrabar order is unknown."
            if hit_sl:
                return "INVALIDATED", "SL was reached before the planned entry."
            if hit_tp1:
                return "ENTRY MISSED", "Price reached TP1 before the planned entry."
            if hit_entry:
                entered = True
            continue

        if hit_sl and hit_tp1:
            return "AMBIGUOUS", "SL and TP1 share an M15 candle after entry; intrabar order is unknown."
        if hit_sl:
            return "STOPPED OUT", "Entry was touched, then SL was reached. Do not enter now."
        if hit_tp1:
            return "TP1 HIT", "Entry was touched and TP1 was later reached. Do not chase."

    if entered:
        return "ENTRY TRIGGERED", "Entry was touched and no later SL/TP1 event was found."
    return "WAIT FOR ENTRY", f"Wait for the planned {setup['direction']} entry at {setup['entry']}."


def setup_fresh(setup, m15):
    signal_index = int(setup["signal_index"])
    age = len(m15) - 1 - signal_index
    return age <= SETUP_EXPIRY_CANDLES, age


def run():
    print("MsemwaFx Cloud Scan")

    closed, reason = market_closed_or_near_close()
    if closed:
        print(f"NO NEW SIGNALS — {reason}")
        return

    sent = load_sent()
    now = time.time()
    sent = {
        k: v for k, v in sent.items()
        if isinstance(v, (int, float)) and now - v < SENT_TTL
    }

    found = 0
    alerts = 0

    for i, symbol in enumerate(SYMBOLS, 1):
        print(f"[{i}/{len(SYMBOLS)}] {symbol}")
        candles = cached_m15(symbol)

        if len(candles) < 80:
            print("  NO DATA")
            continue

        h4, h1, m15 = build_htf(candles)
        if len(h4) < 10 or len(h1) < 10 or len(m15) < 20:
            print("  INSUFFICIENT DATA")
            continue

        setup, reason = analyze_pair_diagnostic(h4, h1, m15, symbol)
        # Print the same H4 dealing range used by the decision engine for auditability.
        h4_range = h4[-20:]
        if h4_range:
            range_high = max(float(c["high"]) for c in h4_range)
            range_low = min(float(c["low"]) for c in h4_range)
            equilibrium = (range_high + range_low) / 2
            print(
                f"  H4 DEALING RANGE: low={range_low:.5f} high={range_high:.5f} "
                f"EQ={equilibrium:.5f} | last H4 close={float(h4[-1]['close']):.5f}"
            )
        if not setup:
            print(f"  NO TRADE — {reason}")

            # Scout is an early-warning channel, independent of the confirmed
            # trade pipeline. Only alert when H4/H1 agree directionally and
            # at least one HTF has a confirmed BOS/CHoCH. Never treat this as entry.
            h4_state = analyze_structure(h4)
            h1_state = analyze_structure(h1)
            aligned_bias = h4_state.get("bias")
            valid_events = {"BOS", "CHoCH", "CHOCH"}
            scout_ready = (
                aligned_bias in {"BULLISH", "BEARISH"}
                and h1_state.get("bias") == aligned_bias
                and (
                    h4_state.get("event") in valid_events
                    or h1_state.get("event") in valid_events
                )
            )
            if scout_ready:
                scout_direction = "BUY" if aligned_bias == "BULLISH" else "SELL"
                scout_key = "|".join([
                    "SCOUT", symbol, scout_direction,
                    str(h4_state.get("event", "NONE")),
                    str(h1_state.get("event", "NONE")),
                ])
                if scout_key not in sent:
                    current_price = round(float(m15[-1]["close"]), 3 if "JPY" in symbol else 5)
                    scout_msg = format_scout(
                        symbol, h4_state, h1_state, current_price,
                        m15[-1].get("time", "unknown"), reason,
                    )
                    if send_telegram_scout(scout_msg):
                        sent[scout_key] = time.time()
                        alerts += 1
                        print(f"  SCOUT ALERT {scout_direction} TG=True")
                    else:
                        print(f"  SCOUT ALERT NOT CONFIRMED {scout_direction} TG=False")
                else:
                    print(f"  SCOUT DUPLICATE {scout_direction}")
            else:
                print(
                    "  SCOUT SKIPPED — requires aligned directional H4/H1 bias "
                    "and a confirmed BOS/CHoCH on H4 or H1"
                )
            if i < len(SYMBOLS):
                time.sleep(8)
            continue

        fresh, age = setup_fresh(setup, m15)
        if not fresh:
            print(
                f"  STALE SETUP — signal age {age} M15 candles > "
                f"{SETUP_EXPIRY_CANDLES}"
            )
            continue

        found += 1
        current_price = round(float(m15[-1]["close"]), 5)
        entry_status, instruction = evaluate_entry_path(setup, m15)

        signal_time = parse_time(setup["signal_candle"])
        expiry_time = signal_time + timedelta(minutes=15 * SETUP_EXPIRY_CANDLES)
        setup["expiry_time"] = expiry_time.strftime("%Y-%m-%d %H:%M UTC")

        setup_key = "|".join([
            symbol,
            setup["direction"],
            str(setup["signal_candle"]),
            str(setup["entry"]),
        ])
        alert_key = f"{setup_key}|{entry_status}"

        if alert_key in sent:
            print(f"  DUPLICATE {entry_status}")
            continue

        msg = format_alert(
            symbol,
            setup,
            setup["signal_candle"],
            current_price,
            entry_status,
            instruction,
        )

        tg = send_telegram(msg)

        if tg:
            wa = send_whatsapp(msg)
            sent[alert_key] = time.time()
            alerts += 1
            print(
                f"  ALERT {setup['grade']} {setup['direction']} "
                f"{entry_status} TG=True WA={wa}"
            )
        else:
            print(
                f"  ALERT NOT CONFIRMED {setup['grade']} "
                f"{setup['direction']} {entry_status} TG=False WA=False"
            )

        if i < len(SYMBOLS):
            time.sleep(8)

    save_sent(sent)
    print(f"Setups found: {found} | New alerts: {alerts}")


if __name__ == "__main__":
    run()
