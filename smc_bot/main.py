import json
import os
import time
from datetime import datetime, timedelta, timezone

from config import M15_OUTPUTSIZE, SENT_TTL, SETUP_EXPIRY_CANDLES, SYMBOLS
from database import save_signal
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
EAT = timezone(timedelta(hours=3), name="EAT")
os.makedirs(CACHE_DIR, exist_ok=True)


def eat_now():
    return datetime.now(timezone.utc).astimezone(EAT)


def eat_stamp():
    return eat_now().strftime("%Y-%m-%d %H:%M:%S EAT")


def cached_m15(symbol):
    path = os.path.join(CACHE_DIR, f"{symbol.replace('/', '_')}_15min.json")
    now = time.time()

    try:
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)
        cache_age = now - float(saved.get("time", 0))
        if saved.get("data") and len(saved["data"]) >= M15_OUTPUTSIZE and cache_age < 900:
            print(f"  [{eat_stamp()}] M15 CACHE_HIT age={cache_age:.1f}s last_candle={saved['data'][-1].get('time', 'UNKNOWN')}")
            return saved["data"]
    except (FileNotFoundError, ValueError, TypeError, OSError):
        pass

    print(f"  [{eat_stamp()}] M15 FETCH_START")
    fetch_started = time.perf_counter()
    data = get_candles(symbol, "15min", M15_OUTPUTSIZE)
    fetch_elapsed = time.perf_counter() - fetch_started
    print(f"  [{eat_stamp()}] M15 FETCH_END duration={fetch_elapsed:.2f}s rows={len(data) if data else 0}")
    if data:
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"time": now, "data": data}, f)
        except OSError:
            pass
    return data


M5_CACHE_TTL = 300
M5_OUTPUTSIZE = 100
M5_DAILY_BUDGET = 32
M5_USAGE_FILE = "m5_usage.json"


def load_m5_usage():
    today = datetime.now(timezone.utc).date().isoformat()
    try:
        with open(M5_USAGE_FILE, encoding="utf-8") as f:
            state = json.load(f)
        if state.get("date") == today:
            return state
    except (FileNotFoundError, ValueError, TypeError, OSError):
        pass
    return {"date": today, "requests": 0}


def save_m5_usage(state):
    try:
        with open(M5_USAGE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except OSError as exc:
        print(f"Could not save M5 credit state: {exc}")


def cached_m5(symbol, usage):
    path = os.path.join(CACHE_DIR, f"{symbol.replace('/', '_')}_5min.json")
    now = time.time()
    try:
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)
        if saved.get("data") and now - float(saved.get("time", 0)) < M5_CACHE_TTL:
            print(f"  M5 CACHE_HIT {symbol}")
            return saved["data"]
    except (FileNotFoundError, ValueError, TypeError, OSError):
        pass

    if int(usage.get("requests", 0)) >= M5_DAILY_BUDGET:
        print(f"  M5 BUDGET_EXHAUSTED {usage['requests']}/{M5_DAILY_BUDGET}")
        return []

    print(f"  M5 FETCH_START {symbol} budget={usage['requests']}/{M5_DAILY_BUDGET}")
    data = get_candles(symbol, "5min", M5_OUTPUTSIZE)
    if data:
        usage["requests"] = int(usage.get("requests", 0)) + 1
        save_m5_usage(usage)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"time": now, "data": data}, f)
        except OSError:
            pass
        print(f"  M5 FETCH_END {symbol} rows={len(data)} budget={usage['requests']}/{M5_DAILY_BUDGET}")
    return data


def evaluate_m5_entry(setup, candles):
    """Confirm an entry only from a closed M5 candle after the M15 signal."""
    if not candles:
        return False, "NO M5 DATA"
    signal_time = parse_time(setup["signal_candle"])
    now = datetime.now(timezone.utc)
    entry_low = float(setup["entry_low"])
    entry_high = float(setup["entry_high"])
    sl = float(setup["sl"])
    tp1 = float(setup["tp1"]) if setup.get("tp1") is not None else None

    for candle in candles:
        try:
            candle_time = parse_time(candle["time"])
        except (KeyError, TypeError, ValueError):
            continue
        if candle_time <= signal_time or candle_time.timestamp() + 300 > now.timestamp():
            continue

        high, low = float(candle["high"]), float(candle["low"])
        open_price, close = float(candle["open"]), float(candle["close"])
        hit_zone = low <= entry_high and high >= entry_low

        if setup["direction"] == "BUY":
            hit_sl, hit_tp = low <= sl, (tp1 is not None and high >= tp1)
            if not hit_zone and (hit_sl or hit_tp):
                return False, "M5 SETUP INVALIDATED OR ENTRY MISSED"
            if hit_zone and (hit_sl or hit_tp):
                return False, "M5 ENTRY AMBIGUOUS — SL/TP SHARED CANDLE"
            if hit_zone and close > open_price and close > entry_low:
                return True, f"M5 bullish close confirmed in entry zone ({candle['time']})"
        else:
            hit_sl, hit_tp = high >= sl, (tp1 is not None and low <= tp1)
            if not hit_zone and (hit_sl or hit_tp):
                return False, "M5 SETUP INVALIDATED OR ENTRY MISSED"
            if hit_zone and (hit_sl or hit_tp):
                return False, "M5 ENTRY AMBIGUOUS — SL/TP SHARED CANDLE"
            if hit_zone and close < open_price and close < entry_high:
                return True, f"M5 bearish close confirmed in entry zone ({candle['time']})"
    return False, "WAITING FOR CLOSED M5 ENTRY CONFIRMATION"


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
    tp1 = float(setup["tp1"]) if setup.get("tp1") is not None else None
    entered = False

    for candle in m15[signal_index + 1:]:
        hit_entry = _touches(candle, entry)
        if setup["direction"] == "BUY":
            hit_sl = candle["low"] <= sl
            hit_tp1 = tp1 is not None and candle["high"] >= tp1
        else:
            hit_sl = candle["high"] >= sl
            hit_tp1 = tp1 is not None and candle["low"] <= tp1

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
    print(f"[{eat_stamp()}] MsemwaFx Cloud Scan START")

    closed, reason = market_closed_or_near_close()
    if closed:
        print(f"NO NEW SIGNALS — {reason}")
        return

    sent = load_sent()
    m5_usage = load_m5_usage()
    now = time.time()
    sent = {
        k: v for k, v in sent.items()
        if isinstance(v, (int, float)) and now - v < SENT_TTL
    }

    found = 0
    alerts = 0

    for i, symbol in enumerate(SYMBOLS, 1):
        print(f"[{eat_stamp()}] [{i}/{len(SYMBOLS)}] {symbol} SCAN_START")
        candles = cached_m15(symbol)

        if len(candles) < 80:
            print("  NO DATA")
            continue

        print(f"  [{eat_stamp()}] BUILD_HTF_START last_raw_m15={candles[-1].get('time', 'UNKNOWN')}")
        h4, h1, m15 = build_htf(candles)
        print(f"  [{eat_stamp()}] BUILD_HTF_END closed_m15={len(m15)} latest_closed_m15={m15[-1].get('time', 'UNKNOWN') if m15 else 'NONE'} h1={len(h1)} h4={len(h4)}")
        if len(h4) < 10 or len(h1) < 10 or len(m15) < 20:
            print("  INSUFFICIENT DATA")
            continue

        analysis_started = time.perf_counter()
        print(f"  [{eat_stamp()}] ANALYSIS_START")
        setup, reason = analyze_pair_diagnostic(h4, h1, m15, symbol)
        print(f"  [{eat_stamp()}] ANALYSIS_END duration={time.perf_counter() - analysis_started:.3f}s result={'SETUP' if setup else 'NO_SETUP'}")
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

        m5_candles = cached_m5(symbol, m5_usage)
        m5_confirmed, m5_reason = evaluate_m5_entry(setup, m5_candles)
        if m5_confirmed:
            entry_status = "M5 ENTRY CONFIRMED"
            instruction = m5_reason
        elif m5_candles:
            print(f"  M5 MONITOR: {m5_reason}")

        signal_time = parse_time(setup["signal_candle"])
        expiry_time = signal_time + timedelta(minutes=15 * SETUP_EXPIRY_CANDLES)
        setup["generated_at"] = eat_stamp()
        setup["expiry_time"] = expiry_time.astimezone(EAT).strftime("%Y-%m-%d %H:%M EAT")
        signal_candle_eat = signal_time.astimezone(EAT).strftime("%Y-%m-%d %H:%M EAT")
        # Persist every qualified setup in the same database served to the Android app.
        save_signal(symbol, setup, entry_status, instruction)
        print(f"  [{setup['generated_at']}] SIGNAL_GENERATED candle={signal_candle_eat} age={age} M15 bars")

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
            signal_candle_eat,
            current_price,
            entry_status,
            instruction,
        )

        print(f"  [{eat_stamp()}] TELEGRAM_SEND_START")
        telegram_started = time.perf_counter()
        tg = send_telegram(msg)
        print(f"  [{eat_stamp()}] TELEGRAM_SEND_END duration={time.perf_counter() - telegram_started:.2f}s success={tg}")

        if tg:
            print(f"  [{eat_stamp()}] WHATSAPP_SEND_START")
            whatsapp_started = time.perf_counter()
            wa = send_whatsapp(msg)
            print(f"  [{eat_stamp()}] WHATSAPP_SEND_END duration={time.perf_counter() - whatsapp_started:.2f}s success={wa}")
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
    save_m5_usage(m5_usage)
    print(
        f"Setups found: {found} | New alerts: {alerts} | "
        f"M5 credits used today: {m5_usage['requests']}/{M5_DAILY_BUDGET}"
    )


if __name__ == "__main__":
    run()
