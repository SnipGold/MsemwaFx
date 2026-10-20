#!/usr/bin/env python3
"""Historical replay: compare selected SMC entry models at 1R-5R.
Uses only committed replay_data M15 candles; no future data for signal decisions.
OHLC same-bar SL/TP is conservatively counted as SL first. Costs excluded.
"""
import csv
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "replay_data"
OUT = ROOT / "smc_backtest_results"
PAIRS = {"EURUSD":"EUR/USD","EURJPY":"EUR/JPY","GBPUSD":"GBP/USD","AUDUSD":"AUD/USD","USDCHF":"USD/CHF","USDCAD":"USD/CAD","NZDUSD":"NZD/USD"}
TARGETS = (1,2,3,4,5)

def load(code):
    p=DATA/f"{code}_15min.csv"
    if not p.exists(): return None
    d=pd.read_csv(p,sep=";")
    d["datetime"]=pd.to_datetime(d["datetime"],errors="coerce")
    d=d.dropna(subset=["datetime"]).drop_duplicates("datetime").sort_values("datetime").set_index("datetime")
    d=d[d.index.dayofweek < 5]
    return d.astype({"open":float,"high":float,"low":float,"close":float})

def atr(d,n=14):
    tr=pd.concat([d.high-d.low,(d.high-d.close.shift()).abs(),(d.low-d.close.shift()).abs()],axis=1).max(axis=1)
    return tr.rolling(n).mean()

def fvg(d,i):
    if i<2:return None
    if d.low.iloc[i]>d.high.iloc[i-2]: return ("BUY",d.high.iloc[i-2],d.low.iloc[i])
    if d.high.iloc[i]<d.low.iloc[i-2]: return ("SELL",d.high.iloc[i],d.low.iloc[i-2])
    return None

def signal(d,i,model):
    if i<30:return None
    row=d.iloc[i]; a=atr(d).iloc[i]
    if not np.isfinite(a) or a<=0:return None
    prior=d.iloc[i-20:i]
    ph,pl=prior.high.max(),prior.low.min()
    direction=None
    fv=fvg(d,i)
    if model=="SWEEP_RECLAIM":
        if row.low<pl and row.close>pl: direction="BUY"
        elif row.high>ph and row.close<ph: direction="SELL"
    elif model=="DISPLACEMENT_FVG":
        body=abs(row.close-row.open)
        if body>=1.2*a and fv:
            if row.close>row.open and fv[0]=="BUY": direction="BUY"
            elif row.close<row.open and fv[0]=="SELL": direction="SELL"
    elif model=="BOS_FVG":
        if fv and row.close>ph and fv[0]=="BUY": direction="BUY"
        elif fv and row.close<pl and fv[0]=="SELL": direction="SELL"
    elif model=="OB_BREAK_RETEST":
        if i>=4:
            c2=d.iloc[i-2]; c1=d.iloc[i-1]
            if c2.close<c2.open and c1.close>c1.open and c1.close>c2.high and row.low<=c2.high and row.close>c2.open: direction="BUY"
            elif c2.close>c2.open and c1.close<c1.open and c1.close<c2.low and row.high>=c2.low and row.close<c2.open: direction="SELL"
    elif model=="TREND_ZONE_REJECTION":
        # Non-sweep baseline: 1h/4h EMA bias must agree, M15 rejects recent 20-bar range edge.
        h1=d.iloc[:i+1].resample("1h").agg({"open":"first","high":"max","low":"min","close":"last"}).dropna()
        h4=d.iloc[:i+1].resample("4h").agg({"open":"first","high":"max","low":"min","close":"last"}).dropna()
        if len(h1)>=12 and len(h4)>=12:
            b1="BUY" if h1.close.iloc[-1]>h1.close.ewm(span=12,adjust=False).mean().iloc[-1] else "SELL"
            b4="BUY" if h4.close.iloc[-1]>h4.close.ewm(span=12,adjust=False).mean().iloc[-1] else "SELL"
            if b1==b4=="BUY" and row.low<=pl+a*.15 and row.close>row.open: direction="BUY"
            elif b1==b4=="SELL" and row.high>=ph-a*.15 and row.close<row.open: direction="SELL"
    if not direction:return None
    # Structural stop beyond the signal candle's opposite wick, bounded by ATR.
    entry=float(row.close)
    sl=float(min(row.low,pl) if direction=="BUY" else max(row.high,ph))
    risk=entry-sl if direction=="BUY" else sl-entry
    if risk<=a*.1 or risk>a*3:return None
    return {"pair":PAIRS[code],"model":model,"time":d.index[i].isoformat(),"side":direction,"entry":entry,"sl":sl,"risk":risk,"index":i}

def simulate(d,sig,target):
    i=sig["index"]; side=sig["side"]; entry=sig["entry"]; sl=sig["sl"]; risk=sig["risk"]
    tp=entry+target*risk if side=="BUY" else entry-target*risk
    end=min(len(d)-1,i+96)
    for j in range(i+1,end+1):
        b=d.iloc[j]
        stop=(b.low<=sl if side=="BUY" else b.high>=sl)
        take=(b.high>=tp if side=="BUY" else b.low<=tp)
        if stop: return -1.0,"SL",j-i
        if take: return float(target),"TP",j-i
    close=float(d.close.iloc[end])
    r=(close-entry)/risk if side=="BUY" else (entry-close)/risk
    return float(r),"TIMEOUT",end-i

def main():
    OUT.mkdir(exist_ok=True)
    trades=[]
    models=("SWEEP_RECLAIM","DISPLACEMENT_FVG","BOS_FVG","OB_BREAK_RETEST","TREND_ZONE_REJECTION")
    for code in PAIRS:
        d=load(code)
        if d is None or len(d)<100: continue
        for model in models:
            active_until=-1
            signals=[]
            for i in range(30,len(d)-1):
                if i<=active_until: continue
                s=signal(d,i,model)
                if s:
                    signals.append(s)
                    # each target gets own independent simulation below; signal generation independent of target
                    active_until=i+1
            for target in TARGETS:
                next_free=-1
                for s in signals:
                    if s["index"]<=next_free: continue
                    r,outcome,held=simulate(d,s,target)
                    trades.append({k:v for k,v in s.items() if k!="index"}|{"target_R":target,"outcome":outcome,"realized_R":round(r,4),"bars_held":held})
                    next_free=s["index"]+held
    t=pd.DataFrame(trades)
    t.to_csv(OUT/"trades.csv",index=False)
    summaries=[]
    if len(t):
        for (model,target),g in t.groupby(["model","target_R"]):
            wins=int((g.outcome=="TP").sum()); losses=int((g.outcome=="SL").sum()); n=len(g)
            eq=g.realized_R.cumsum(); dd=(eq.cummax()-eq).max() if n else 0
            summaries.append({"model":model,"target_R":int(target),"trades":n,"wins":wins,"losses":losses,"timeouts":int((g.outcome=="TIMEOUT").sum()),"win_rate_pct":round(100*wins/n,2) if n else 0,"net_R":round(g.realized_R.sum(),2),"avg_R":round(g.realized_R.mean(),3) if n else 0,"max_drawdown_R":round(float(dd),2),"pairs":int(g.pair.nunique())})
    summary=pd.DataFrame(summaries).sort_values(["target_R","net_R"],ascending=[True,False])
    summary.to_csv(OUT/"summary.csv",index=False)
    print("DATA COVERAGE")
    for p in sorted(DATA.glob("*_15min.csv")):
        d=load(p.name.removesuffix("_15min.csv"))
        if d is not None: print(f"{p.stem}: {len(d)} bars, {d.index.min()} -> {d.index.max()}")
    print("\nSUMMARY (gross, costs excluded, max hold 24h; timeout exits at close)")
    print(summary.to_string(index=False) if len(summary) else "NO TRADES")
    print(f"\nTOTAL TRADE-ROWS: {len(t)}")

if __name__=="__main__": main()
