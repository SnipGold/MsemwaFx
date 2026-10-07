import csv
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter

ROOT = Path("replay_data")  # GBPUSD liquidity-first replay
OUT = Path("replay_results.csv")
CANDIDATES_OUT = Path("replay_candidates.csv")

def load(path):
    rows=[]
    with open(path,newline="") as f:
        for r in csv.DictReader(f,delimiter=";"):
            rows.append({
                "time":datetime.fromisoformat(r["datetime"]),
                "open":float(r["open"]),"high":float(r["high"]),
                "low":float(r["low"]),"close":float(r["close"]),
            })
    return sorted(rows,key=lambda x:x["time"])

m15=load(ROOT/"GBPUSD_15min.csv")
h1=load(ROOT/"GBPUSD_1h.csv")
h4=load(ROOT/"GBPUSD_4h.csv")

def atr(rows,i,n=14):
    if i<1:return 0.0
    vals=[]
    for j in range(max(1,i-n+1),i+1):
        vals.append(max(rows[j]["high"]-rows[j]["low"],
                        abs(rows[j]["high"]-rows[j-1]["close"]),
                        abs(rows[j]["low"]-rows[j-1]["close"])))
    return sum(vals)/len(vals)

def structure_bias(rows):
    if len(rows)<12:return "NEUTRAL","NONE"
    highs=[];lows=[]
    for i in range(2,len(rows)-2):
        if rows[i]["high"]>rows[i-1]["high"] and rows[i]["high"]>rows[i-2]["high"] and rows[i]["high"]>rows[i+1]["high"] and rows[i]["high"]>rows[i+2]["high"]:
            highs.append((i,rows[i]["high"]))
        if rows[i]["low"]<rows[i-1]["low"] and rows[i]["low"]<rows[i-2]["low"] and rows[i]["low"]<rows[i+1]["low"] and rows[i]["low"]<rows[i+2]["low"]:
            lows.append((i,rows[i]["low"]))
    recent=rows[-24:]
    hi=max(x["high"] for x in recent);lo=min(x["low"] for x in recent)
    rng=max(hi-lo,1e-12);close=rows[-1]["close"]
    score=0
    if len(highs)>=2: score += 1 if highs[-1][1]>highs[-2][1] else -1
    if len(lows)>=2: score += 1 if lows[-1][1]>lows[-2][1] else -1
    last_high=highs[-1][1] if highs else None
    last_low=lows[-1][1] if lows else None
    bull=last_high is not None and close>last_high
    bear=last_low is not None and close<last_low
    look=min(6,len(rows)-1)
    momentum=close-rows[-1-look]["close"]
    threshold=rng*.08
    pos=(close-lo)/rng
    if bull and not bear:return "BULLISH","BOS"
    if bear and not bull:return "BEARISH","BOS"
    if score>=2:return "BULLISH","CHoCH" if momentum<0 else "NONE"
    if score<=-2:return "BEARISH","CHoCH" if momentum>0 else "NONE"
    if score==1 and (momentum>threshold or pos>.58):return "BULLISH","CHoCH" if momentum>threshold else "NONE"
    if score==-1 and (momentum<-threshold or pos<.42):return "BEARISH","CHoCH" if momentum<-threshold else "NONE"
    if pos>.62 and momentum>threshold:return "BULLISH","NONE"
    if pos<.38 and momentum<-threshold:return "BEARISH","NONE"
    return "NEUTRAL","NONE"

def closed_before(rows,t,duration_hours):
    # A HTF candle is usable only after it has fully closed.
    return [r for r in rows if r["time"]+timedelta(hours=duration_hours)<=t]

def htf_state(t):
    a=closed_before(h4,t,4);b=closed_before(h1,t,1)
    hb,he=structure_bias(a);ib,ie=structure_bias(b)
    return hb,he,ib,ie

def body(r):return abs(r["close"]-r["open"])

def levels_before(i,direction,entry):
    x=m15[max(0,i-100):i]
    vals=[]
    # Swing liquidity
    for j in range(2,len(x)-2):
        if direction=="BUY" and x[j]["high"]>x[j-1]["high"] and x[j]["high"]>x[j+1]["high"]:
            v=x[j]["high"]
            if v>entry:vals.append(("SWING_HIGH",v))
        if direction=="SELL" and x[j]["low"]<x[j-1]["low"] and x[j]["low"]<x[j+1]["low"]:
            v=x[j]["low"]
            if v<entry:vals.append(("SWING_LOW",v))
    # Equal liquidity
    tol=.0002
    for j in range(max(0,len(x)-80),len(x)-1):
        for k in range(j+1,min(len(x),j+12)):
            a=x[j]["high"] if direction=="BUY" else x[j]["low"]
            b=x[k]["high"] if direction=="BUY" else x[k]["low"]
            if abs(a-b)<=tol:
                v=max(a,b) if direction=="BUY" else min(a,b)
                if (direction=="BUY" and v>entry) or (direction=="SELL" and v<entry):
                    vals.append(("EQUAL_LIQUIDITY",v))
    uniq={}
    for kind,v in vals:uniq[round(v,5)]=(kind,v)
    return sorted(uniq.values(),key=lambda z:z[1],reverse=direction=="SELL")

def candidate_at(i):
    if i<40 or m15[i]["time"].weekday()>=5:return None
    t=m15[i]["time"]
    h4b,h4e,h1b,h1e=htf_state(t)
    # First detect liquidity event without using future HTF information.
    look=m15[max(0,i-8):i]
    pl=min(x["low"] for x in look);ph=max(x["high"] for x in look)
    direction=None;sweep=None
    if m15[i]["low"]<pl and m15[i]["close"]>pl:
        direction="BUY";sweep="SELL_SIDE_SWEEP"
    elif m15[i]["high"]>ph and m15[i]["close"]<ph:
        direction="SELL";sweep="BUY_SIDE_SWEEP"
    if not direction:return None

    a=atr(m15,i)
    med=sum(body(x) for x in m15[max(1,i-20):i])/min(20,i)
    disp=None
    for j in range(i,min(i+4,len(m15))):
        prev=m15[max(0,j-5):j]
        if not prev:continue
        if direction=="BUY":
            broke=m15[j]["close"]>max(x["high"] for x in prev)
            strong=m15[j]["close"]>m15[j]["open"] and body(m15[j])>=max(med*1.15,a*.45)
        else:
            broke=m15[j]["close"]<min(x["low"] for x in prev)
            strong=m15[j]["close"]<m15[j]["open"] and body(m15[j])>=max(med*1.15,a*.45)
        if broke and strong:disp=j;break
    if disp is None:return None

    ob=None
    for j in range(disp-1,i-1,-1):
        q=m15[j]
        if direction=="BUY" and q["close"]<q["open"]:ob=j;break
        if direction=="SELL" and q["close"]>q["open"]:ob=j;break
    if ob is None:return None

    zl=m15[ob]["low"];zh=m15[ob]["high"];entry=(zl+zh)/2
    sweep_ext=m15[i]["low"] if direction=="BUY" else m15[i]["high"]
    sl=sweep_ext-a*.15 if direction=="BUY" else sweep_ext+a*.15
    risk=entry-sl if direction=="BUY" else sl-entry
    if risk<=0 or risk>a*2.5:return None

    # Premium/discount based on the visible M15 dealing range.
    recent=m15[max(0,i-60):i]
    eq=(max(x["high"] for x in recent)+min(x["low"] for x in recent))/2
    if direction=="BUY" and entry>eq:return None
    if direction=="SELL" and entry<eq:return None

    levels=levels_before(disp,direction,entry)
    tp1=tp2=None;tp1kind=tp2kind=None
    for kind,v in levels:
        rr=abs(v-entry)/risk
        if tp1 is None and rr>=1.5:
            tp1,tp1kind=v,kind
        elif tp1 is not None and rr>=2.0:
            tp2,tp2kind=v,kind;break
    if tp1 is None or tp2 is None:return None

    wanted="BULLISH" if direction=="BUY" else "BEARISH"
    # Liquidity-first classification: HTF alignment is a quality tier, not a
    # mandatory gate. A setup can become executable after an H1 CHoCH/BOS while
    # H4 is still neutral or transitioning.
    h1_confirm = h1b==wanted and h1e in ("BOS","CHoCH")
    h4_support = h4b==wanted
    htf_aligned = h4b==h1b==wanted

    # The displacement candle itself already proves a local structure break:
    # it closes beyond the previous 5 M15 highs/lows. Use that as the early
    # reversal confirmation instead of waiting for H1 to flip.
    disp_bar = m15[disp]
    disp_prev = m15[max(0,disp-5):disp]
    m15_shift = bool(disp_prev) and (
        (direction=="BUY" and disp_bar["close"]>max(x["high"] for x in disp_prev))
        or
        (direction=="SELL" and disp_bar["close"]<min(x["low"] for x in disp_prev))
    )

    # Continuation: HTF/H1 direction agrees with the liquidity reaction.
    continuation = h1_confirm and (h4b in (wanted, "NEUTRAL"))

    # Reversal: the old HTF direction is opposite (or still neutral), but
    # liquidity was swept and M15 has already displaced through local structure.
    reversal = m15_shift and h4b in (
        "NEUTRAL",
        "BEARISH" if wanted=="BULLISH" else "BULLISH",
    )

    if htf_aligned:
        tier="S_TIER_INSTITUTIONAL"
        setup_type="CONTINUATION"
    elif continuation:
        tier="A_TIER_CONTINUATION"
        setup_type="CONTINUATION"
    elif reversal and h1e in ("BOS","CHoCH"):
        tier="A_TIER_REVERSAL"
        setup_type="REVERSAL"
    else:
        tier="B_TIER_SCOUT"
        setup_type="SCOUT"
    return {
        "signal_time":t.isoformat(),"direction":direction,"h4_bias":h4b,
        "h1_bias":h1b,"h4_event":h4e,"h1_event":h1e,
        "tier":tier,"setup_type":setup_type,"sweep":sweep,"displacement_time":m15[disp]["time"].isoformat(),
        "ob_time":m15[ob]["time"].isoformat(),"entry":round(entry,5),
        "sl":round(sl,5),"risk_pips":round(risk*10000,1),
        "tp1":round(tp1,5),"tp2":round(tp2,5),
        "tp1_rr":round(abs(tp1-entry)/risk,2),"tp2_rr":round(abs(tp2-entry)/risk,2),
        "tp1_liquidity":tp1kind,"tp2_liquidity":tp2kind,
        "signal_i":i,"disp_i":disp,"ob_i":ob
    }

def evaluate(s):
    start=s["disp_i"]+1;expiry=min(start+16,len(m15)-1)
    for j in range(start,expiry+1):
        r=m15[j]
        if s["direction"]=="BUY":
            if r["low"]<=s["sl"]:return "INVALIDATED",None,j
            if r["low"]<=s["entry"]<=r["high"]:break
        else:
            if r["high"]>=s["sl"]:return "INVALIDATED",None,j
            if r["low"]<=s["entry"]<=r["high"]:break
    else:return "MISSED",None,expiry
    entry_i=j
    for k in range(entry_i,min(entry_i+48,len(m15))):
        q=m15[k]
        if s["direction"]=="BUY":
            hit2=q["high"]>=s["tp2"];hit1=q["high"]>=s["tp1"];hitsl=q["low"]<=s["sl"]
        else:
            hit2=q["low"]<=s["tp2"];hit1=q["low"]<=s["tp1"];hitsl=q["high"]>=s["sl"]
        if hitsl and (hit2 or hit1):return "AMBIGUOUS",0.0,k
        if hit2:return "TP2",s["tp2_rr"],k
        if hit1:
            for z in range(k+1,min(k+48,len(m15))):
                w=m15[z]
                hitsl=(w["low"]<=s["sl"]) if s["direction"]=="BUY" else (w["high"]>=s["sl"])
                hit2=(w["high"]>=s["tp2"]) if s["direction"]=="BUY" else (w["low"]<=s["tp2"])
                if hitsl:return "TP1_THEN_SL",1.0,z
                if hit2:return "TP2_AFTER_TP1",s["tp2_rr"],z
            return "TP1",1.0,k
    return "OPEN",None,entry_i

candidates=[]
results=[]
last_event=-999
for i in range(40,len(m15)-20):
    s=candidate_at(i)
    if not s:continue
    # Same liquidity event should not generate repeated setups.
    if i-last_event<4:continue
    last_event=i
    outcome,rr,exit_i=evaluate(s)
    candidates.append({k:v for k,v in s.items() if k not in {"signal_i","disp_i","ob_i"}})
    if s["tier"] not in ("S_TIER_INSTITUTIONAL","A_TIER_CONTINUATION","A_TIER_REVERSAL"):continue
    results.append({
        **{k:v for k,v in s.items() if k not in {"signal_i","disp_i","ob_i"}},
        "outcome":outcome,"realized_R":"" if rr is None else round(rr,2),
        "exit_time":"" if exit_i is None else m15[exit_i]["time"].isoformat()
    })

def write(path,rows):
    fields=list(rows[0].keys()) if rows else ["signal_time"]
    with open(path,"w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

write(CANDIDATES_OUT,candidates)
write(OUT,results)

print("LIQUIDITY EVENTS",len(candidates))
print("CANDIDATE TIERS",dict(Counter(x["tier"] for x in candidates)))
print("INSTITUTIONAL SETUPS",len(results))
print("S-TIER",sum(1 for x in results if x["tier"]=="S_TIER_INSTITUTIONAL"))
print("A-TIER CONTINUATION",sum(1 for x in results if x["tier"]=="A_TIER_CONTINUATION"))
print("A-TIER REVERSAL",sum(1 for x in results if x["tier"]=="A_TIER_REVERSAL"))
print("OUTCOMES",dict(Counter(x["outcome"] for x in results)))
print("\nCONFIRMED RESULTS")
for x in results:print(x)
