import json
import os
import time

from config import SYMBOLS, M15_OUTPUTSIZE, SENT_TTL
from modules.decision_engine import analyze_pair
from modules.notifier import format_alert, send_telegram, send_whatsapp
from modules.timeframes import build_htf
from modules.twelvedata import get_candles


CACHE_DIR = "data_cache"
SENT_FILE = "sent.json"
os.makedirs(CACHE_DIR, exist_ok=True)


def cached_m15(symbol):
    path = os.path.join(
        CACHE_DIR,
        f"{symbol.replace('/', '_')}_15min.json",
    )
    now = time.time()

    try:
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)

        if (
            saved.get("data")
            and now - float(saved.get("time", 0)) < 900
        ):
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


def get_entry_status(setup, current_price):
    """
    Manual-entry guard.

    WAIT:
        Price has not reached the planned entry.

    TRIGGERED:
        Price has reached/crossed the entry but has not passed TP1.

    INVALIDATED:
        Price reached the SL side before the planned entry.

    MISSED:
        Price moved beyond TP1 before the user entered.
    """
    entry = float(setup["entry"])
    sl = float(setup["sl"])
    tp1 = float(setup["tp1"])

    if setup["direction"] == "BUY":
        if current_price <= sl:
            return "INVALIDATED", "DO NOT ENTER — price crossed the SL before entry."
        if current_price < entry:
            return "WAIT FOR ENTRY", f"Wait for BUY entry at {entry}."
        if current_price <= tp1:
            return "ENTRY TRIGGERED", "Entry zone reached — manage the planned trade."
        return "ENTRY MISSED", "DO NOT ENTER — price has already moved beyond TP1."

    if current_price >= sl:
        return "INVALIDATED", "DO NOT ENTER — price crossed the SL before entry."
    if current_price > entry:
        return "WAIT FOR ENTRY", f"Wait for SELL entry at {entry}."
    if current_price >= tp1:
        return "ENTRY TRIGGERED", "Entry zone reached — manage the planned trade."
    return "ENTRY MISSED", "DO NOT ENTER — price has already moved beyond TP1."


def run():
    print("MsemwaFx Cloud Scan")

    sent = load_sent()
    now = time.time()

    sent = {
        k: v
        for k, v in sent.items()
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

        setup = analyze_pair(h4, h1, m15)

        if not setup:
            print("  NO TRADE")
            continue

        found += 1

        signal_candle = m15[-1]["time"]
        current_price = round(float(m15[-1]["close"]), 5)

        entry_status, instruction = get_entry_status(
            setup,
            current_price,
        )

        setup_key = "|".join(
            [
                symbol,
                setup["direction"],
                str(setup["entry"]),
                str(setup["sl"]),
                str(setup["tp1"]),
                str(setup["tp2"]),
                setup["grade"],
            ]
        )

        # One notification per setup/status.
        # This allows WAIT -> TRIGGERED -> INVALIDATED/MISSED
        # transitions without repeated spam on every scan.
        alert_key = f"{setup_key}|{entry_status}"

        if alert_key in sent:
            print(f"  DUPLICATE {entry_status}")
            continue

        msg = format_alert(
            symbol,
            setup,
            signal_candle,
            current_price,
            entry_status,
            instruction,
        )

        # Telegram is the primary channel.
        # WhatsApp is sent only after Telegram succeeds.
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
            wa = False
            print(
                f"  ALERT NOT CONFIRMED "
                f"{setup['grade']} {setup['direction']} "
                f"{entry_status} TG=False WA=False"
            )

        if i < len(SYMBOLS):
            time.sleep(8)

    save_sent(sent)

    print(f"Setups found: {found} | New alerts: {alerts}")


if __name__ == "__main__":
    run()
