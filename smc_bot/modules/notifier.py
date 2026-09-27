import os
import requests

BOT = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram(msg):
    if not BOT or not CHAT:
        return
    requests.post(
        f"https://api.telegram.org/bot{BOT}/sendMessage",
        json={"chat_id": CHAT, "text": msg},
        timeout=20
    )

def send_whatsapp(msg):
    provider = os.getenv("WA_PROVIDER")
    phone = os.getenv("WA_PHONE")
    apikey = os.getenv("WA_APIKEY")

    if provider == "callmebot" and phone and apikey:
        requests.get(
            f"https://api.callmebot.com/whatsapp.php?phone={phone}&text={msg}&apikey={apikey}",
            timeout=20
        )
