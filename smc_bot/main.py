import os
import sys

# Make sure GitHub Actions can find config.py
sys.path.append(os.path.dirname(__file__))

from config import SYMBOLS
from modules.notifier import send_telegram, send_whatsapp

msg = (
    "🤖 MsemwaFx AI Trader v1.0 is ONLINE\n\n"
    f"Pairs: {', '.join(SYMBOLS)}\n\n"
    "SMC/ICT Engine Ready."
)

send_telegram(msg)
send_whatsapp(msg)

print("MsemwaFx AI Trader v1.0 started.")

