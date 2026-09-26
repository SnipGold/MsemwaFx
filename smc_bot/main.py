import os
import requests

BOT = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT = os.getenv("TELEGRAM_CHAT_ID")
RUN_ONCE = os.getenv("RUN_ONCE")

print("SMC ICT Bot started...")

if not BOT or not CHAT:
    raise SystemExit("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")

msg = (
    "✅ MsemwaFX SMC ICT Bot is ONLINE\n"
    f"RUN_ONCE={RUN_ONCE}"
)

url = f"https://api.telegram.org/bot{BOT}/sendMessage"

r = requests.post(url, json={
    "chat_id": CHAT,
    "text": msg
}, timeout=20)

print(r.text)
