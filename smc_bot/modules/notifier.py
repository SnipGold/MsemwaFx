import os
import requests

BOT = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT = os.getenv("TELEGRAM_CHAT_ID")


def send_telegram(msg):
    if not BOT or not CHAT:
        print("Telegram credentials missing.")
        return False

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{BOT}/sendMessage",
            json={
                "chat_id": CHAT,
                "text": msg,
                "parse_mode": "Markdown",
            },
            timeout=20,
        )
        print(f"Telegram HTTP {r.status_code}")
        if r.status_code != 200:
            print(r.text[:300])
        return r.status_code == 200
    except requests.RequestException as exc:
        print(f"Telegram failed: {exc}")
        return False


def send_whatsapp(msg):
    provider = (os.getenv("WA_PROVIDER") or "").strip().lower()
    phone = os.getenv("WA_PHONE")
    apikey = os.getenv("WA_APIKEY")

    if provider != "callmebot" or not phone or not apikey:
        return False

    try:
        r = requests.get(
            "https://api.callmebot.com/whatsapp.php",
            params={
                "phone": phone,
                "text": msg,
                "apikey": apikey,
            },
            timeout=20,
        )
        print(f"WhatsApp HTTP {r.status_code}")
        return r.status_code == 200
    except requests.RequestException as exc:
        print(f"WhatsApp failed: {exc}")
        return False


def format_alert(symbol, setup, candle_time, current_price, entry_status, instruction):
    return (
        f"🚨 *MsemwaFx Institutional Alert*\n\n"
        f"*Pair:* {symbol}\n"
        f"*Direction:* {setup['direction']}\n"
        f"*Grade:* {setup['grade']} / Score {setup['score']}/5\n"
        f"*Timeframe:* M15 execution\n"
        f"*H4 Bias:* {setup.get('h4_bias', 'UNKNOWN')}\n"
        f"*H1 Bias:* {setup.get('h1_bias', 'UNKNOWN')}\n\n"
        f"📍 *Current Price:* {current_price}\n"
        f"📌 *Entry Zone:* {setup['entry_low']} - {setup['entry_high']}\n"
        f"🎯 *Planned Entry:* {setup['entry']}\n"
        f"*Entry Status:* {entry_status}\n"
        f"*Instruction:* {instruction}\n"
        f"⏳ *Expiry:* {setup['expiry_time']}\n\n"
        f"🛑 *Stop Loss:* {setup['sl']}\n"
        f"📏 *Risk:* {setup['risk_pips']} pips\n"
        f"📦 *Lot Size:* {setup['lot_size']:.2f}\n"
        f"🎯 *TP1:* {setup['tp1']}\n"
        f"🎯 *TP2:* {setup['tp2']}\n"
        f"⚖️ *Projected R:R:* {setup['rr']}\n\n"
        f"*Structure:* {setup['event']}\n"
        f"*FVG:* {setup['fvg']}\n"
        f"*Sweep:* {setup['sweep']}\n"
        f"*Order Block:* {setup['order_block']}\n"
        f"*Signal Candle:* {candle_time}\n\n"
        f"_MsemwaFx — H4/H1 → M15_"
    )


def send_telegram_scout(msg):
    bot = os.getenv("TELEGRAM_SCOUT_BOT_TOKEN")
    chat = os.getenv("TELEGRAM_CHAT_ID")

    if not bot or not chat:
        print("Scout Telegram credentials missing.")
        return False

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{bot}/sendMessage",
            json={
                "chat_id": chat,
                "text": msg,
                "parse_mode": "Markdown",
            },
            timeout=20,
        )
        print(f"Scout Telegram HTTP {r.status_code}")
        if r.status_code != 200:
            print(r.text[:300])
        return r.status_code == 200
    except requests.RequestException as exc:
        print(f"Scout Telegram failed: {exc}")
        return False


def format_scout(symbol, h4, h1, current_price, m15_time):
    direction = "BUY" if h4["bias"] == "BULLISH" else "SELL"
    return (
        f"👀 *MsemwaFx Scout — Setup Developing*\n\n"
        f"*Pair:* {symbol}\n"
        f"*Watch Direction:* {direction}\n"
        f"*H4 Bias:* {h4['bias']}\n"
        f"*H4 Structure:* {h4.get('event', 'NONE')}\n"
        f"*H1 Bias:* {h1['bias']}\n"
        f"*H1 Structure:* {h1.get('event', 'NONE')}\n\n"
        f"📍 *Current Price:* {current_price}\n"
        f"⏱️ *M15 Candle:* {m15_time}\n\n"
        f"*Status:* WATCH — waiting for M15 liquidity sweep, displacement and valid OB/FVG.\n"
        f"*Action:* Do not enter from Scout alert. Wait for Institutional confirmation.\n\n"
        f"_MsemwaFx Scout — H4/H1 → M15_"
    )
