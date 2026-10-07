import csv
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter

ROOT=Path("replay_data")
OUT=Path("replay_all_results.csv")
SUMMARY=Path("replay_all_summary.csv")

PAIRS={
 "EURUSD":"EUR/USD","EURJPY":"EUR/JPY","GBPUSD":"GBP/USD","AUDUSD":"AUD/USD",
 "USDCHF":"USD/CHF","USDCAD":"USD/CAD","NZDUSD":"NZD/USD",
}

def load(path):
    rows=[]
    with open(path,newline="") as f:
        for r in csv.DictReader(f,delimiter=";"):
            rows.append({"time":datetime.fromisoformat(r["datetime"]),"open":float(r["open"]),
                         "high":float(r["high"]),"low":float(r["low"]),"close":float(r["close"])})
    return sorted(rows,key=lambda x:x["time"])

def atr(rows,i,n=14):
    if i<1:return 0.0
    vals=[]
    for j in range(max(1,i-n+1),i+1):
        vals.append(max(rows[j]["high"]-rows[j]["low"],abs(rows[j]["high"]-rows[j-1]["close"]),abs(rows[j]["low"]-rows[j-1]["close"])))
    return sum(vals)/len(vals)

def bias(rows):
    if len(rows)<12:return "NEUTRAL","NONE"
    recent=rows[-24:]
    hi=max(x["high"] for x in recent); lo=min(x["low"] for x in recent)
    rng=max(hi-lo,1e-12); close=rows[-1]["close"]; pos=(close-lo)/rng
    highs=[];lows=[]
    for i in range(2,len(rows)-2):
        if rows[i]["high"]>rows[i-1]["high"] and rows[i]["high"]>rows[i-2]["high"] and rows[i]["high"]>rows[i+1]["high"] and rows[i]["high"]>rows[i+2]["high"]: highs.append(rows[i]["high"])
        if rows[i]["low"]<rows[i-1]["low"] and rows[i]["low"]<rows[i-2]["low"] and rows[i]["low"]<rows[i+1]["low"] and rows[i]["low"]<rows[i+2]["low"]: lows.append(rows[i]["low"])
    score=(1 if len(highs)>=2 and highs[-1]>highs[-2] else -1 if len(highs)>=2 and highs[-1]<highs[-2] else 0)
    score+=(1 if len(lows)>=2 and lows[-1]>lows[-2] else -1 if len(lows)>=2 and lows[-1]<lows[-2] else 0)
    momentum=close-rows[-1-min(6,len(rows)-1)]["close"]
    threshold=rng*.08
    if highs and close>highs[-1]: return "BULLISH","BOS"
    if lows and close<lows[-1]: return "BEARISH","BOS"
    if score>=2:return "BULLISH","CHoCH" if momentum<0 else "NONE"
    if score<=-2:return "BEARISH","CHoCH" if momentum>0 else "NONE"
    if score==1 and (momentum>threshold or pos>.58):return "BULLISH","CHoCH" if momentum>threshold else "NONE"
    if score==-1 and (momentum<-threshold or pos<.42):return "BEARISH","CHoCH" if momentum<-threshold else "NONE"
    if pos>.62 and momentum>threshold:return "BULLISH","NONE"
    if pos<.38 and momentum<-threshold:return "BEARISH","NONE"
    return "NEUTRAL","NONE"

def closed(rows,t,hours):
    return [x for x in rows if x["time"]+timedelta(hours=hours)<=t]

def state(h1,h4,t):
    a,ae=bias(closed(h4,t,4)); b,be=bias(closed(h1,t,1)); return a,ae,b,be

def pip(symbol):
    return .01 if "JPY" in symbol else .0001

def find_candidate(m15,h1,h4,symbol,i):
    if i<40 or m15[i]["time"].weekday()>=5:return None
    t=m15[i]["time"]; h4b,h4e,h1b,h1e=state(h1,h4,t)
    prior=m15[max(0,i-8):i]; pl=min(x["low"] for x in prior); ph=max(x["high"] for x in prior)
    direction="BUY" if m15[i]["low"]<pl and m15[i]["close"]>pl else "SELL" if m15[i]["high"]>ph and m15[i]["close"]<ph else None
    if not direction:return None
    a=atr(m15,i); med=sum(abs(x["close"]-x["open"]) for x in m15[max(1,i-20):i])/min(20,i)
    disp=None
    for j in range(i,min(i+4,len(m15))):
        prev=m15[max(0,j-5):j]
        if not prev:continue
        if direction=="BUY": strong=m15[j]["close"]>m15[j]["open"] and abs(m15[j]["close"]-m15[j]["open"])>=max(med*1.15,a*.45) and m15[j]["close"]>max(x["high"] for x in prev)
        else: strong=m15[j]["close"]<m15[j]["open"] and abs(m15[j]["close"]-m15[j]["open"])>=max(med*1.15,a*.45) and m15[j]["close"]<min(x["low"] for x in prev)
        if strong:disp=j;break
    if disp is None:return None
    ob=None
    for j in range(disp-1,i-1,-1):
        q=m15[j]
        if direction=="BUY" and q["close"]<q["open"]:ob=j;break
        if direction=="SELL" and q["close"]>q["open"]:ob=j;break
    if ob is None:return None
    zl,zh=m15[ob]["low"],m15[ob]["high"]; entry=(zl+zh)/2
    sweep_ext=m15[i]["low"] if direction=="BUY" else m15[i]["high"]
    sl=sweep_ext-a*.15 if direction=="BUY" else sweep_ext+a*.15
    risk=abs(entry-sl); ps=pip(symbol)
    if risk<=0:return None
    spread_pips={"EUR/USD":1.4,"EUR/JPY":1.3,"GBP/USD":1.6,"AUD/USD":1.6,"USD/CHF":1.5,"USD/CAD":1.9,"NZD/USD":1.8}.get(symbol,1.5)
    minrisk=max(spread_pips*2*ps,a*.35)
    if risk<minrisk:return None
    recent=m15[max(0,i-60):i]; eq=(max(x["high"] for x in recent)+min(x["low"] for x in recent))/2
    if direction=="BUY" and entry>eq:return None
    if direction=="SELL" and entry<eq:return None
    levels=[]; x=m15[max(0,disp-100):disp]
    for j in range(2,len(x)-2):
        if direction=="BUY" and x[j]["high"]>x[j-1]["high"] and x[j]["high"]>x[j+1]["high"] and x[j]["high"]>entry:levels.append(("SWING_HIGH",x[j]["high"]))
        if direction=="SELL" and x[j]["low"]<x[j-1]["low"] and x[j]["low"]<x[j+1]["low"] and x[j]["low"]<entry:levels.append(("SWING_LOW",x[j]["low"]))
    tp1=tp2=None; k1=k2=None
    for kind,v in sorted(levels,key=lambda z:z[1],reverse=direction=="SELL"):
        rr=abs(v-entry)/risk
        if tp1 is None and rr>=1.5:tp1,k1=v,kind
        elif tp1 is not None and rr>=2.0:tp2,k2=v,kind;break
    if tp1 is None or tp2 is None:return None
    wanted="BULLISH" if direction=="BUY" else "BEARISH"
    aligned=h4b==h1b==wanted
    h1confirm=h1b==wanted and h1e in ("BOS","CHoCH")

    # Moderate reversal gate matching the live engine. This keeps
    # liquidity-first behavior without treating every counter-trend reaction
    # as an institutional reversal.
    htf_has_context=h4b in ("BULLISH","BEARISH") or h1b in ("BULLISH","BEARISH")
    reversal_confirmed = (
        (h1b==wanted and h1e in ("BOS","CHoCH"))
        or (h4b=="NEUTRAL" and h1b!=wanted and h1e=="CHoCH")
        or (h4b!=wanted and h4b in ("BULLISH","BEARISH") and h1b=="NEUTRAL" and h4e in ("BOS","CHoCH"))
    )
    early_reversal = htf_has_context and h4b!=wanted and reversal_confirmed
    if aligned:tier,stype="S_TIER","CONTINUATION"
    elif h1confirm:tier,stype="A_CONTINUATION","CONTINUATION"
    elif early_reversal:tier,stype="A_REVERSAL","REVERSAL"
    else:tier,stype="B_SCOUT","SCOUT"
    return {"pair":symbol,"signal_time":t.isoformat(),"direction":direction,"h4_bias":h4b,"h1_bias":h1b,"h1_event":h1e,"tier":tier,"setup_type":stype,"entry":round(entry,6),"sl":round(sl,6),"risk_pips":round(risk/ps,1),"tp1":round(tp1,6),"tp2":round(tp2,6),"tp1_rr":round(abs(tp1-entry)/risk,2),"tp2_rr":round(abs(tp2-entry)/risk,2),"signal_i":i,"disp_i":disp}

def evaluate(m15,s):
    for j in range(s["disp_i"]+1,min(s["disp_i"]+17,len(m15))):
        r=m15[j]
        if (s["direction"]=="BUY" and r["low"]<=s["sl"]) or (s["direction"]=="SELL" and r["high"]>=s["sl"]):return "INVALIDATED",j
        if r["low"]<=s["entry"]<=r["high"]:break
    else:return "MISSED",min(s["disp_i"]+16,len(m15)-1)
    for k in range(j,min(j+49,len(m15))):
        q=m15[k]
        hit2=q["high"]>=s["tp2"] if s["direction"]=="BUY" else q["low"]<=s["tp2"]
        hit1=q["high"]>=s["tp1"] if s["direction"]=="BUY" else q["low"]<=s["tp1"]
        sl=q["low"]<=s["sl"] if s["direction"]=="BUY" else q["high"]>=s["sl"]
        if sl and hit1:return "TP1_THEN_SL",k
        if hit2:return "TP2",k
    return "OPEN",j

all_results=[]; summaries=[]
for code,symbol in PAIRS.items():
    try:
        m15=load(ROOT/f"{code}_15min.csv");h1=load(ROOT/f"{code}_1h.csv");h4=load(ROOT/f"{code}_4h.csv")
    except Exception as e:
        summaries.append({"pair":symbol,"liquidity_events":0,"institutional_setups":0,"entries":0,"missed":0,"invalidated":0,"tp2_wins":0,"tp1_then_sl":0,"error":str(e)});continue
    events=0; setups=0; entries=0; missed=0; invalidated=0; tp2=0; tpsl=0; last=-99
    for i in range(40,len(m15)-20):
        s=find_candidate(m15,h1,h4,symbol,i)
        if not s or i-last<4:continue
        last=i; events+=1
        outcome,exit_i=evaluate(m15,s)
        if s["tier"] not in ("S_TIER","A_CONTINUATION","A_REVERSAL"):continue
        setups+=1
        if outcome in ("TP2","TP1_THEN_SL","OPEN"):entries+=1
        if outcome=="MISSED":missed+=1
        elif outcome=="INVALIDATED":invalidated+=1
        elif outcome=="TP2":tp2+=1
        elif outcome=="TP1_THEN_SL":tpsl+=1
        all_results.append({k:v for k,v in s.items() if k not in ("signal_i","disp_i")}|{"outcome":outcome,"exit_time":"" if exit_i is None else m15[exit_i]["time"].isoformat()})
    summaries.append({"pair":symbol,"liquidity_events":events,"institutional_setups":setups,"entries":entries,"missed":missed,"invalidated":invalidated,"tp2_wins":tp2,"tp1_then_sl":tpsl,"error":""})

with open(OUT,"w",newline="") as f:
    fields=list(all_results[0].keys()) if all_results else ["pair"];w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(all_results)
with open(SUMMARY,"w",newline="") as f:
    fields=list(summaries[0].keys());w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(summaries)

# noise-reduced seven-pair replay v2
print("7-PAIR REPLAY")
for x in summaries:print(x)
print("TOTAL LIQUIDITY EVENTS",sum(int(x["liquidity_events"]) for x in summaries))
print("TOTAL INSTITUTIONAL SETUPS",sum(int(x["institutional_setups"]) for x in summaries))
print("TOTAL ENTRIES",sum(int(x["entries"]) for x in summaries))
