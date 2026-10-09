#!/usr/bin/env python3
"""Independent MA signal scanner: signals only, no trade execution."""
import json, os, time
from datetime import datetime, timezone
from pathlib import Path
import requests

API_KEY = os.getenv("TWELVEDATA_API_KEY", "").strip()
BOT = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT = os.getenv("TELEGRAM_CHAT_ID", "").strip()
SYMBOLS = ["EUR/USD","EUR/JPY","GBP/USD","AUD/USD","USD/CHF","USD/CAD","NZD/USD","USD/JPY"]
OUTPUTSIZE, FAST, SIGNAL, TREND, MAJOR, ATR_PERIOD = 250, 9, 20, 50, 200, 14
ATR_MULTIPLIER, RR = 1.5, 2.0
CAPITAL, RISK_PCT, DAILY_LOSS_PCT = 1000.0, 1.0, 3.0
STATE_PATH = Path("MA_Signal/sent_signals.json")
URL = "https://api.twelvedata.com/time_series"

def ema(values, period):
    if len(values) < period: return []
    alpha = 2.0 / (period + 1.0)
    vals = [sum(values[:period]) / period]
    for value in values[period:]: vals.append(alpha * value + (1-alpha) * vals[-1])
    return [None] * (period-1) + vals

def atr(candles, period=14):
    trs = []
    for i in range(1, len(candles)):
        c, pc = candles[i], candles[i-1]["close"]
        trs.append(max(c["high"]-c["low"], abs(c["high"]-pc), abs(c["low"]-pc)))
    if len(trs) < period: return None
    value = sum(trs[:period])/period
    for tr in trs[period:]: value = (value*(period-1)+tr)/period
    return value

def get_closed_candles(symbol):
    r = requests.get(URL, params={"symbol":symbol,"interval":"1h","outputsize":OUTPUTSIZE,
                                  "timezone":"UTC","apikey":API_KEY}, timeout=30)
    r.raise_for_status()
    payload = r.json()
    if "values" not in payload: raise RuntimeError(payload.get("message","No candle values"))
    rows = list(reversed(payload["values"]))
    candles = [{"time":x["datetime"],"open":float(x["open"]),"high":float(x["high"]),
                "low":float(x["low"]),"close":float(x["close"])} for x in rows]
    # Exclude newest candle because it may still be forming.
    candles = candles[:-1]
    if len(candles) < MAJOR+3: raise RuntimeError(f"Only {len(candles)} closed candles")
    return candles

def make_signal(symbol, candles):
    closes = [c["close"] for c in candles]
    f, s, t, m = ema(closes,FAST), ema(closes,SIGNAL), ema(closes,TREND), ema(closes,MAJOR)
    av = atr(candles,ATR_PERIOD)
    if av is None or any(x is None for x in (f[-1],f[-2],s[-1],s[-2],t[-1],m[-1])): return None
    last = candles[-1]
    buy = f[-2] <= s[-2] and f[-1] > s[-1] and t[-1] > m[-1] and last["close"] > t[-1]
    sell = f[-2] >= s[-2] and f[-1] < s[-1] and t[-1] < m[-1] and last["close"] < t[-1]
    if not (buy or sell): return None
    direction, entry = ("BUY",last["close"]) if buy else ("SELL",last["close"])
    distance = ATR_MULTIPLIER*av
    sl, tp = ((entry-distance,entry+distance*RR) if buy else (entry+distance,entry-distance*RR))
    pip = 0.01 if "JPY" in symbol else 0.0001
    digits = 3 if "JPY" in symbol else 5
    return {"symbol":symbol,"direction":direction,"time":last["time"],"entry":round(entry,digits),
            "sl":round(sl,digits),"tp":round(tp,digits),"risk_pips":round(distance/pip,1),
            "rr":RR,"ema9":round(f[-1],digits),"ema20":round(s[-1],digits),
            "ema50":round(t[-1],digits),"ema200":round(m[-1],digits),"atr14":round(av,digits),
            "capital":CAPITAL,"risk_usd":round(CAPITAL*RISK_PCT/100,2),
            "daily_loss_usd":round(CAPITAL*DAILY_LOSS_PCT/100,2)}

def load_state():
    try: return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError,ValueError,TypeError): return {}

def send(msg):
    if not BOT or not CHAT:
        print("Telegram secrets missing; signal printed only."); return False
    r = requests.post(f"https://api.telegram.org/bot{BOT}/sendMessage",
                      json={"chat_id":CHAT,"text":msg},timeout=20)
    if not r.ok: print(f"Telegram failed: HTTP {r.status_code} {r.text[:200]}")
    return r.ok

def format_msg(x):
    return ("📊 MA SIGNAL — SIGNAL ONLY\n\n"
      f"Pair: {x['symbol']}\nDirection: {x['direction']}\nTimeframe: H1\nClosed candle UTC: {x['time']}\n\n"
      f"Entry reference: {x['entry']}\nStop loss: {x['sl']}\nTake profit: {x['tp']}\n"
      f"Risk distance: {x['risk_pips']} pips\nR:R: 1:{x['rr']}\n\n"
      f"EMA 9: {x['ema9']} | EMA 20: {x['ema20']}\nEMA 50: {x['ema50']} | EMA 200: {x['ema200']}\n"
      f"ATR(14): {x['atr14']}\n\nReference capital: $" + f"{x['capital']:.0f}\n"
      f"Risk budget (1%): $" + f"{x['risk_usd']:.2f}\nDaily loss threshold (3%): $" + f"{x['daily_loss_usd']:.2f}\n\n"
      "Signal only; no order was placed. Check live price, spread, news and position size before trading.")

def main():
    if not API_KEY: raise SystemExit("Missing TWELVEDATA_API_KEY GitHub Actions secret.")
    state, alerts = load_state(), 0
    for i, symbol in enumerate(SYMBOLS):
        print(f"[{i+1}/{len(SYMBOLS)}] {symbol}")
        try:
            x = make_signal(symbol,get_closed_candles(symbol))
            if not x: print("  NO NEW MA CROSSOVER SIGNAL")
            else:
                key = f"{symbol}|{x['direction']}|{x['time']}"
                if key in state: print("  DUPLICATE: already recorded")
                else:
                    msg = format_msg(x); print(msg)
                    if send(msg):
                        state[key] = datetime.now(timezone.utc).isoformat()
                        alerts += 1; print("  TELEGRAM SENT")
                    else: print("  NOT SENT; eligible for retry")
        except Exception as exc: print(f"  ERROR: {type(exc).__name__}: {exc}")
        if i < len(SYMBOLS)-1: time.sleep(9)
    state = dict(list(state.items())[-500:])
    STATE_PATH.parent.mkdir(parents=True,exist_ok=True)
    STATE_PATH.write_text(json.dumps(state,indent=2)+"\n",encoding="utf-8")
    print(f"Scan complete. New Telegram alerts sent: {alerts}")

if __name__ == "__main__": main()
