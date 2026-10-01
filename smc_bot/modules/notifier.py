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


def format_alert(
    symbol,
    setup,
    candle_time,
    current_price,
    entry_status,
    instruction,
):
    return (
        f"🚨 *MsemwaFx Institutional Alert*\n\n"
        f"*Pair:* {symbol}\n"
        f"*Direction:* {setup['direction']}\n"
        f"*Grade:* {setup['grade']} / Score {setup['score']}/5\n"
        f"*HTF Bias:* {setup['bias']}\n\n"
        f"📍 *Current Price:* {current_price}\n"
        f"📌 *Entry Zone:* {setup['entry_low']} - {setup['entry_high']}\n"
        f"🎯 *Planned Entry:* {setup['entry']}\n"
        f"*Entry Status:* {entry_status}\n"
        f"*Instruction:* {instruction}\n\n"
        f"🛑 *Stop Loss:* {setup['sl']}\n"
        f"🎯 *TP1:* {setup['tp1']}\n"
        f"🎯 *TP2:* {setup['tp2']}\n"
        f"⚖️ *Risk:Reward:* {setup['rr']}\n\n"
        f"*Structure:* {setup['event']}\n"
        f"*FVG:* {setup['fvg']}\n"
        f"*Sweep:* {setup['sweep']}\n"
        f"*Order Block:* {setup['order_block']}\n"
        f"*Signal Candle:* {candle_time}\n\n"
        f"_MsemwaFx — H4/H1 → M15_"
    )
