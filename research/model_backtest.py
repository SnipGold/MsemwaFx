import pandas as pd, numpy as np, glob, os, math
from collections import defaultdict

PAIRS={"EURUSD":"EUR/USD","EURJPY":"EUR/JPY","GBPUSD":"GBP/USD","AUDUSD":"AUD/USD","USDCHF":"USD/CHF","USDCAD":"USD/CAD","NZDUSD":"NZD/USD"}
MODELS=["SWEEP_CHOCH","EQHL_SWEEP","PDHL_SWEEP","ASIA_SWEEP","TURTLE_SOUP","DISPLACEMENT_FVG","OB_RETEST","BREAKER","IFVG","UNICORN","BOS_FVG","BOS_OB","HTF_ZONE_LTF","PREMIUM_DISCOUNT","SILVER_BULLET"]

def load(code):
    p=f"replay_data/{code}_15min.csv"
    d=pd.read_csv(p,sep=";")
    d["datetime"]=pd.to_datetime(d["datetime"],utc=True)
    d=d.set_index("datetime").sort_index()
    return d.astype(float)

def atr(d,n=14):
    tr=pd.concat([(d.high-d.low),(d.high-d.close.shift()).abs(),(d.low-d.close.shift()).abs()],axis=1).max(axis=1)
    return tr.rolling(n).mean()

def swings(d,n=3):
    hi=d.high.rolling(2*n+1,center=True).max()==d.high
    lo=d.low.rolling(2*n+1,center=True).min()==d.low
    return hi.fillna(False),lo.fillna(False)

def htf(d):
    h1=d.resample("1h").agg({"open":"first","high":"max","low":"min","close":"last"}).dropna()
    h4=d.resample("4h").agg({"open":"first","high":"max","low":"min","close":"last"}).dropna()
    return h1,h4

def bias(x,look=12):
    e=x.close.ewm(span=look,adjust=False).mean()
    return np.where(x.close>e,"BULLISH",np.where(x.close<e,"BEARISH","NEUTRAL"))

def fvg_at(d,i):
    if i<2:return None
    if d.low.iloc[i] > d.high.iloc[i-2]: return ("BULL",d.high.iloc[i-2],d.low.iloc[i])
    if d.high.iloc[i] < d.low.iloc[i-2]: return ("BEAR",d.high.iloc[i],d.low.iloc[i-2])
    return None

def signal(model,d,i):
    if i<25:return None
    row=d.iloc[i]; a=atr(d).iloc[i]
    if not np.isfinite(a) or a<=0:return None
    prior=d.iloc[max(0,i-20):i]
    ph,pl=prior.high.max(),prior.low.min()
    direction=None; level=None
    if model=="SWEEP_CHOCH":
        if row.low<pl and row.close>pl: direction="BUY";level=pl
        elif row.high>ph and row.close<ph: direction="SELL";level=ph
    elif model=="EQHL_SWEEP":
        hs=prior.high.values; ls=prior.low.values
        eh=ph if sum(abs(h-ph)<=a*.15 for h in hs)>=2 else None
        el=pl if sum(abs(l-pl)<=a*.15 for l in ls)>=2 else None
        if el and row.low<el and row.close>el: direction="BUY";level=el
        elif eh and row.high>eh and row.close<eh: direction="SELL";level=eh
    elif model=="PDHL_SWEEP":
        day=d.index[i].floor("D"); x=d[d.index<day].tail(96)
        if len(x):
            dh,dl=x.high.max(),x.low.min()
            if row.low<dl and row.close>dl:direction="BUY";level=dl
            elif row.high>dh and row.close<dh:direction="SELL";level=dh
    elif model=="ASIA_SWEEP":
        day=d.index[i].floor("D"); start=day; end=day+pd.Timedelta(hours=7)
        x=d[(d.index>=start)&(d.index<end)]
        if d.index[i].hour>=7 and len(x):
            ah,al=x.high.max(),x.low.min()
            if row.low<al and row.close>al:direction="BUY";level=al
            elif row.high>ah and row.close<ah:direction="SELL";level=ah
    elif model=="TURTLE_SOUP":
        prev=d[d.index<d.index[i].floor("D")].tail(96)
        if len(prev):
            ph2,pl2=prev.high.max(),prev.low.min()
            if row.high>ph2 and row.close<ph2:direction="SELL";level=ph2
            elif row.low<pl2 and row.close>pl2:direction="BUY";level=pl2
    elif model=="DISPLACEMENT_FVG":
        body=abs(row.close-row.open)
        fv=fvg_at(d,i)
        if body>=a*1.2 and fv:
            direction="BUY" if row.close>row.open and fv[0]=="BULL" else ("SELL" if row.close<row.open and fv[0]=="BEAR" else None)
            level=fv[1] if direction=="BUY" else (fv[2] if direction=="SELL" else None)
    elif model=="OB_RETEST":
        if i<4:return None
        c1=d.iloc[i-1]; c2=d.iloc[i-2]
        if c2.close<c2.open and c1.close>c1.open and c1.close>c2.high:
            if row.low<=c2.high and row.close>c2.open:direction="BUY";level=c2.low
        elif c2.close>c2.open and c1.close<c1.open and c1.close<c2.low:
            if row.high>=c2.low and row.close<c2.open:direction="SELL";level=c2.high
    elif model=="BREAKER":
        if row.close>ph and row.open<ph:direction="BUY";level=ph
        elif row.close<pl and row.open>pl:direction="SELL";level=pl
    elif model=="IFVG":
        fv=fvg_at(d,i)
        if fv and i>=5:
            old=fvg_at(d,i-3)
            if old and old[0]!=fv[0]:
                direction="BUY" if fv[0]=="BULL" else "SELL";level=(fv[1]+fv[2])/2
    elif model=="UNICORN":
        fv=fvg_at(d,i)
        if fv and i>=3:
            c=d.iloc[i-1]
            if fv[0]=="BULL" and c.close>c.open and c.low<=fv[2]:direction="BUY";level=(fv[1]+fv[2])/2
            elif fv[0]=="BEAR" and c.close<c.open and c.high>=fv[1]:direction="SELL";level=(fv[1]+fv[2])/2
    elif model=="BOS_FVG":
        fv=fvg_at(d,i)
        if fv and row.close>ph and fv[0]=="BULL":direction="BUY";level=(fv[1]+fv[2])/2
        elif fv and row.close<pl and fv[0]=="BEAR":direction="SELL";level=(fv[1]+fv[2])/2
    elif model=="BOS_OB":
        if row.close>ph and row.close>row.open:direction="BUY";level=min(row.open,row.close)
        elif row.close<pl and row.close<row.open:direction="SELL";level=max(row.open,row.close)
    elif model=="HTF_ZONE_LTF":
        # H1/H4 directional agreement + LTF rejection at 20-bar extreme
        h1=d.loc[:d.index[i]].resample("1h").agg({"open":"first","high":"max","low":"min","close":"last"}).dropna()
        h4=d.loc[:d.index[i]].resample("4h").agg({"open":"first","high":"max","low":"min","close":"last"}).dropna()
        if len(h1)>20 and len(h4)>10:
            b1="BULLISH" if h1.close.iloc[-1]>h1.close.ewm(span=12,adjust=False).mean().iloc[-1] else "BEARISH"
            b4="BULLISH" if h4.close.iloc[-1]>h4.close.ewm(span=12,adjust=False).mean().iloc[-1] else "BEARISH"
            if b1==b4=="BULLISH" and row.low<=pl+a*.15 and row.close>row.open:direction="BUY";level=pl
            elif b1==b4=="BEARISH" and row.high>=ph-a*.15 and row.close<row.open:direction="SELL";level=ph
    elif model=="PREMIUM_DISCOUNT":
        rng=ph-pl; mid=(ph+pl)/2
        if rng>2*a and row.low<mid and row.close>row.open:direction="BUY";level=pl
        elif rng>2*a and row.high>mid and row.close<row.open:direction="SELL";level=ph
    elif model=="SILVER_BULLET":
        h=d.index[i].hour
        if h in (10,11,14,15,16,17): # UTC London/NY windows
            fv=fvg_at(d,i)
            if fv and fv[0]=="BULL" and row.close>row.open:direction="BUY";level=(fv[1]+fv[2])/2
            elif fv and fv[0]=="BEAR" and row.close<row.open:direction="SELL";level=(fv[1]+fv[2])/2
    if not direction:return None
    # risk stop anchored to recent opposite extreme, capped to 2 ATR
    if direction=="BUY":
        sl=min(pl, row.low-a*.15); risk=row.close-sl
        if risk<=a*.15 or risk>a*3:return None
        tp=row.close+2*risk
    else:
        sl=max(ph, row.high+a*.15); risk=sl-row.close
        if risk<=a*.15 or risk>a*3:return None
        tp=row.close-2*risk
    return direction,row.close,sl,tp

def run_pair(code):
    d=load(code); out=[]
    # warmup and no overlapping positions per model
    for model in MODELS:
        active_until=-1
        for i in range(30,len(d)-12):
            if i<=active_until:continue
            s=signal(model,d,i)
            if not s:continue
            direction,entry,sl,tp=s
            outcome=None; r=None; exit_i=None
            for j in range(i+1,min(len(d),i+97)):
                hi,lo=d.high.iloc[j],d.low.iloc[j]
                if direction=="BUY":
                    if lo<=sl: outcome="SL";r=-1;exit_i=j;break
                    if hi>=tp: outcome="TP2";r=2;exit_i=j;break
                else:
                    if hi>=sl: outcome="SL";r=-1;exit_i=j;break
                    if lo<=tp: outcome="TP2";r=2;exit_i=j;break
            if outcome is None: outcome="OPEN";r=0;exit_i=min(len(d)-1,i+96)
            active_until=exit_i
            out.append({"pair":PAIRS[code],"model":model,"signal_time":d.index[i].isoformat(),"direction":direction,"entry":entry,"sl":sl,"tp":tp,"outcome":outcome,"R":r})
    return out

allrows=[]
for code in PAIRS:
    allrows += run_pair(code)
tr=pd.DataFrame(allrows)
os.makedirs("model_backtest_results",exist_ok=True)
tr.to_csv("model_backtest_results/trades.csv",index=False)
rows=[]
for m in MODELS:
    x=tr[tr.model==m]
    wins=(x.outcome=="TP2").sum(); losses=(x.outcome=="SL").sum()
    rs=x.R.sum(); n=len(x)
    eq=x.R.cumsum()
    dd=(eq.cummax()-eq).max() if n else 0
    rows.append({"model":m,"trades":n,"wins":wins,"losses":losses,"win_pct":round(100*wins/n,1) if n else 0,"net_R":round(rs,2),"avg_R":round(rs/n,2) if n else 0,"max_dd_R":round(dd,2),"signals_per_day":round(n/15,2)})
summary=pd.DataFrame(rows).sort_values(["net_R","win_pct"],ascending=False)
summary.to_csv("model_backtest_results/model_summary.csv",index=False)
pair=pd.pivot_table(tr,index="model",columns="pair",values="R",aggfunc=["count","sum"],fill_value=0)
pair.to_csv("model_backtest_results/model_pair_breakdown.csv")
print(summary.to_string(index=False))
print("\nTOTAL TRADES",len(tr),"TOTAL R",round(tr.R.sum(),2))
