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
from modules.timeframes import build_htf, parse_time\nfrom modules.structure import analyze_structure
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
        if saved.get("data") and now - float(saved.get("time", 0)) < 900:
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
    """Determine entry status from the candle sequence after the signal candle."""
    signal_index = int(setup["signal_index"])
    entry = float(setup["entry"])
    sl = float(setup["sl"])
    tp1 = float(setup["tp1"])

    for candle in m15[signal_index + 1:]:
        hit_entry = _touches(candle, entry)

        if setup["direction"] == "BUY":
            hit_sl = candle["low"] <= sl
            hit_tp1 = candle["high"] >= tp1
        else:
            hit_sl = candle["high"] >= sl
            hit_tp1 = candle["low"] <= tp1

        if hit_entry and hit_sl:
            return "AMBIGUOUS", "Entry and SL were both inside the same M15 candle. No chase."
        if hit_entry:
            return "ENTRY TRIGGERED", "Planned entry was touched after the signal candle."
        if hit_sl:
            return "INVALIDATED", "SL was reached before the planned entry."
        if hit_tp1:
            return "ENTRY MISSED", "Price reached TP1 without a confirmed planned-entry touch."

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
        if not setup:
            print(f"  NO TRADE — {reason}")
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

        # Stable identity: SL/TP can be refined internally, but the same
        # liquidity event must not become a brand-new setup every scan.
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
