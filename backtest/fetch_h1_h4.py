#!/usr/bin/env python3
"""Download H1 and H4 candles for the 90-day sweep timeframe comparison."""
import csv, os, sys, time
from datetime import datetime, timedelta
from pathlib import Path
import requests

KEY=os.getenv("TWELVEDATA_API_KEY")
URL="https://api.twelvedata.com/time_series"
SYMBOLS={"AUDUSD":"AUD/USD","EURJPY":"EUR/JPY","EURUSD":"EUR/USD","GBPUSD":"GBP/USD","NZDUSD":"NZD/USD","USDCAD":"USD/CAD","USDCHF":"USD/CHF","XAUUSD":"XAU/USD"}
OUT=Path("replay_data")
INTERVALS={"1h":"1h","4h":"4h"}

def fetch(symbol, interval, start, end):
    params={"symbol":symbol,"interval":interval,"start_date":start.isoformat(),"end_date":end.isoformat(),"timezone":"UTC","apikey":KEY}
    last="unknown response"
    for attempt in range(3):
        try:
            r=requests.get(URL,params=params,timeout=45)
            if r.status_code==429:
                last="rate limit"; time.sleep(65); continue
            r.raise_for_status(); body=r.text.strip()
            if body.startswith("{"):
                p=r.json()
                if "values" not in p:
                    last=str(p.get("message",p.get("code","no values")))
                    if "limit" in last.lower() or "credit" in last.lower(): time.sleep(65); continue
                    break
                vals=p["values"]
            else:
                vals=[]
                for x in csv.DictReader(body.splitlines()):
                    x={str(k).strip().lower():str(v).strip() for k,v in x.items() if k}
                    dt=next((x[k] for k in ("datetime","date","time") if k in x),None)
                    if dt: vals.append({"datetime":dt,"open":x.get("open"),"high":x.get("high"),"low":x.get("low"),"close":x.get("close")})
                if not vals: last="unexpected response"; time.sleep(5*(attempt+1)); continue
            out=[]
            for x in vals:
                dt=datetime.fromisoformat(str(x["datetime"]).replace("Z","+00:00")).replace(tzinfo=None)
                out.append({"datetime":dt.strftime("%Y-%m-%d %H:%M:%S"),"open":float(x["open"]),"high":float(x["high"]),"low":float(x["low"]),"close":float(x["close"])})
            return out
        except Exception as e:
            last=str(e); time.sleep(5*(attempt+1))
    raise RuntimeError(f"{symbol} {interval} {start}..{end}: {last}")

def main():
    if not KEY: raise SystemExit("Missing TWELVEDATA_API_KEY GitHub Actions secret.")
    OUT.mkdir(exist_ok=True)
    end=datetime.utcnow().date(); start=end-timedelta(days=90)
    chunks=[]; d=start
    while d<=end:
        e=min(d+timedelta(days=29),end); chunks.append((d,e)); d=e+timedelta(days=1)
    for sym,api in SYMBOLS.items():
        for interval in INTERVALS:
            merged={}
            for idx,(a,b) in enumerate(chunks):
                time.sleep(8.2)
                for row in fetch(api,interval,a,b): merged[row["datetime"]]=row
                print(f"{sym} {interval}: chunk {idx+1}/{len(chunks)}")
            rows=[merged[k] for k in sorted(merged)]
            if len(rows)<100: raise RuntimeError(f"{sym} {interval}: only {len(rows)} candles")
            path=OUT/f"{sym}_{interval}.csv"
            with path.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["datetime","open","high","low","close"],delimiter=";");w.writeheader();w.writerows(rows)
            print(f"Saved {sym} {interval}: {len(rows)} bars {rows[0]['datetime']}..{rows[-1]['datetime']}")
    print("H1/H4 download complete.")
if __name__=="__main__":
    try: main()
    except Exception as e: print(f"HTF DOWNLOAD FAILED: {e}",file=sys.stderr); raise
