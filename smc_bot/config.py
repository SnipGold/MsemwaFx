SYMBOLS = [
    "EUR/USD",
    "EUR/JPY",
    "GBP/USD",
    "AUD/USD",
    "USD/CHF",
    "USD/CAD",
    "XAU/USD",
    "NZD/USD",
]

LTF = "15min"
M15_OUTPUTSIZE = 400
MIN_RR = 2.0
SENT_TTL = 24 * 3600

KILL_ZONES = {
    "ASIAN": ("00:00", "03:30"),
    "LONDON": ("07:00", "10:00"),
    "NEW_YORK": ("13:30", "16:00"),
}
