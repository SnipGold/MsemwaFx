#!/usr/bin/env python3
"""MA strategy V2 backtest only; does not place orders."""
import os,time,json,csv
from pathlib import Path
from datetime import datetime,timezone,time as tm
from zoneinfo import ZoneInfo
from collections import defaultdict
import requests
API=os.getenv("TWELVEDATA_API_KEY","").strip(); BOT=os.getenv("TELEGRAM_BOT_TOKEN","").strip(); CHAT=os.getenv("TELEGRAM_CHAT_ID","").strip()
PAIRS=["EUR/USD","EUR/JPY","GBP/USD","AUD/USD","USD/CHF","USD/CAD","NZD/USD","USD/JPY"]; N=5000; START=1000.; RISK=1.; DAILY=3.; RR=2.
ATR_N=14; ADX_MIN=20.; LEFT=3; RIGHT=3; LOOKBACK=50; BUFFER=.10
OUT=Path("MA_Signal/results"); UTC=timezone.utc; LON=ZoneInfo("Europe/London"); NY=ZoneInfo("America/New_York")
def dt(s):
 x=datetime.fromisoformat(s.replace("Z","+00:00")); return x.replace(tzinfo=UTC) if x.tzinfo is None else x.astimezone(UTC)
def ema(v,p):
 if len(v)<p:return [None]*len(v)
 a=2/(p+1); out=[None]*(p-1); z=sum(v[:p])/p; out.append(z)
 for x in v[p:]: z=a*x+(1-a)*z; out.append(z)
 return out
def inds(c):
 n=len(c); tr=[0.]*n; up=[0.]*n; dn=[0.]*n
 for i in range(1,n):
  tr[i]=max(c[i]["h"]-c[i]["l"],abs(c[i]["h"]-c[i-1]["c"]),abs(c[i]["l"]-c[i-1]["c"]))
  u=c[i]["h"]-c[i-1]["h"]; d=c[i-1]["l"]-c[i]["l"]
  up[i]=u if u>d and u>0 else 0.; dn[i]=d if d>u and d>0 else 0.
 atr=[None]*n; su=[None]*n; sd=[None]*n
 if n>ATR_N:
  atr[ATR_N]=sum(tr[1:ATR_N+1])/ATR_N; su[ATR_N]=sum(up[1:ATR_N+1])/ATR_N; sd[ATR_N]=sum(dn[1:ATR_N+1])/ATR_N
  for i in range(ATR_N+1,n):
   atr[i]=(atr[i-1]*(ATR_N-1)+tr[i])/ATR_N; su[i]=(su[i-1]*(ATR_N-1)+up[i])/ATR_N; sd[i]=(sd[i-1]*(ATR_N-1)+dn[i])/ATR_N
 dx=[None]*n; adx=[None]*n
 for i in range(ATR_N,n):
  if atr[i] and atr[i]>0:
   p=100*su[i]/atr[i]; m=100*sd[i]/atr[i]; dx[i]=100*abs(p-m)/(p+m) if p+m else 0.
 first=2*ATR_N-1
 if n>first:
  vals=[v for v in dx[ATR_N:first+1] if v is not None]
  if len(vals)==ATR_N:
   adx[first]=sum(vals)/ATR_N
   for i in range(first+1,n):
    if dx[i] is not None: adx[i]=(adx[i-1]*(ATR_N-1)+dx[i])/ATR_N
 return atr,adx
def get(pair):
 r=requests.get("https://api.twelvedata.com/time_series",params={"symbol":pair,"interval":"1h","outputsize":N,"timezone":"UTC","apikey":API},timeout=45); r.raise_for_status(); j=r.json()
 if "values" not in j: raise RuntimeError(j.get("message","No candle data"))
 c=[{"t":dt(x["datetime"]),"o":float(x["open"]),"h":float(x["high"]),"l":float(x["low"]),"c":float(x["close"])} for x in reversed(j["values"])][:-1]
 if len(c)<1000: raise RuntimeError(f"{pair}: only {len(c)} closed bars")
 return c
def overlap(t):
 l=t.astimezone(LON).time(); n=t.astimezone(NY).time()
 return tm(8)<=l<tm(17) and tm(8)<=n<tm(17)
def swing(c,i,kind):
 end=i-RIGHT; start=max(LEFT,i-LOOKBACK)
 for j in range(end,start-1,-1):
  v=c[j]["l" if kind=="low" else "h"]; arr="l" if kind=="low" else "h"
  a=[c[k][arr] for k in range(j-LEFT,j)]+[c[k][arr] for k in range(j+1,j+RIGHT+1)]
  if (kind=="low" and all(v<x for x in a)) or (kind=="high" and all(v>x for x in a)): return v
 return None
def prep(c):
 cl=[x["c"] for x in c]; e9,e20,e50,e200=[ema(cl,p) for p in (9,20,50,200)]; atr,adx=inds(c); sig=[None]*len(c)
 for i in range(220,len(c)-1):
  if any(z[i] is None for z in (e9,e20,e50,e200,atr,adx)) or atr[i]<=0 or adx[i]<ADX_MIN: continue
  buy=e9[i-1]<=e20[i-1] and e9[i]>e20[i] and e50[i]>e200[i] and c[i]["c"]>e50[i]
  sell=e9[i-1]>=e20[i-1] and e9[i]<e20[i] and e50[i]<e200[i] and c[i]["c"]<e50[i]
  if not (buy or sell): continue
  side="BUY" if buy else "SELL"; sw=swing(c,i,"low" if buy else "high")
  if sw is None: continue
  sl=sw-BUFFER*atr[i] if buy else sw+BUFFER*atr[i]; ent=c[i+1]["o"]; dist=ent-sl if buy else sl-ent
  if dist<=0 or not overlap(c[i+1]["t"]): continue
  sig[i+1]={"side":side,"signal":c[i]["t"],"entry":ent,"sl":sl,"tp":ent+(RR*dist if buy else -RR*dist),"dist":dist,"swing":sw,"adx":adx[i]}
 return sig
def simulate(data,sigs):
 clock=defaultdict(list)
 for p,cs in data.items():
  for i,x in enumerate(cs):clock[x["t"]].append((p,i))
 eq=peak=START; dd=0.; day=None; dayeq=START; locked=False; lockdays=set(); pos={}; trades=[]
 for ts in sorted(clock):
  d=ts.date().isoformat()
  if d!=day:day=d;dayeq=eq;locked=False
  bars=sorted(clock[ts])
  for p,i in bars:
   if p not in pos:continue
   x=data[p][i]; z=pos[p]; ex=why=None
   if z["side"]=="BUY":
    if x["o"]<=z["sl"]:ex,why=x["o"],"GAP_SL"
    elif x["o"]>=z["tp"]:ex,why=z["tp"],"TP"
    elif x["l"]<=z["sl"]:ex,why=z["sl"],"SL (same-bar conflict resolved as loss)"
    elif x["h"]>=z["tp"]:ex,why=z["tp"],"TP"
    rr=(ex-z["entry"])/z["dist"] if ex is not None else None
   else:
    if x["o"]>=z["sl"]:ex,why=x["o"],"GAP_SL"
    elif x["o"]<=z["tp"]:ex,why=z["tp"],"TP"
    elif x["h"]>=z["sl"]:ex,why=z["sl"],"SL (same-bar conflict resolved as loss)"
    elif x["l"]<=z["tp"]:ex,why=z["tp"],"TP"
    rr=(z["entry"]-ex)/z["dist"] if ex is not None else None
   if ex is not None:
    pnl=rr*z["riskcash"]; eq+=pnl
    trades.append({"pair":p,"side":z["side"],"signal_utc":z["signal"].isoformat(),"entry_utc":z["time"].isoformat(),"exit_utc":ts.isoformat(),"entry":z["entry"],"exit":ex,"sl":z["sl"],"tp":z["tp"],"swing_level":z["swing"],"adx14":z["adx"],"risk_pips":z["dist"]/(.01 if "JPY" in p else .0001),"risk_cash_usd":z["riskcash"],"R":rr,"pnl_usd":pnl,"reason":why,"equity_after":eq})
    del pos[p]; peak=max(peak,eq); dd=max(dd,(peak-eq)/peak*100 if peak else 0)
    if dayeq>0 and (dayeq-eq)/dayeq>=DAILY/100:locked=True;lockdays.add(d)
  for p,i in bars:
   z=sigs[p][i]
   if p in pos or locked or not z:continue
   pos[p]={"side":z["side"],"entry":z["entry"],"sl":z["sl"],"tp":z["tp"],"dist":z["dist"],"riskcash":eq*RISK/100,"time":data[p][i]["t"],"signal":z["signal"],"swing":z["swing"],"adx":z["adx"]}
 return trades,eq,dd,len(pos),sorted(lockdays),min(clock),max(clock)
def main():
 if not API:raise SystemExit("Missing TWELVEDATA_API_KEY secret")
 data={}; sigs={}
 for i,p in enumerate(PAIRS):
  print(f"Fetch {i+1}/8 {p}");data[p]=get(p);sigs[p]=prep(data[p]);print("closed bars",len(data[p]),"eligible entries",sum(x is not None for x in sigs[p]))
  if i<7:time.sleep(9)
 trades,eq,dd,op,lockdays,start,end=simulate(data,sigs); rs=[x["R"] for x in trades]; wins=[x for x in rs if x>0]; losses=[x for x in rs if x<0]; pf=sum(wins)/abs(sum(losses)) if losses and sum(losses) else None
 streak=mx=0
 for x in rs:streak=streak+1 if x<0 else 0;mx=max(mx,streak)
 costs={}; 
 for cost in (0,1,1.5,2):
  net=[x["R"]-cost/x["risk_pips"] for x in trades if x["risk_pips"]>0]; costs[str(cost)]={"assumed_cost_pips":cost,"total_R":round(sum(net),2),"avg_R":round(sum(net)/len(net),3) if net else 0,"win_rate_pct":round(sum(x>0 for x in net)/len(net)*100,2) if net else 0}
 per={}
 for p in PAIRS:
  q=[x for x in trades if x["pair"]==p]; per[p]={"trades":len(q),"win_rate_pct":round(sum(x["R"]>0 for x in q)/len(q)*100,2) if q else 0,"total_R":round(sum(x["R"] for x in q),2),"avg_R":round(sum(x["R"] for x in q)/len(q),3) if q else 0}
 report={"strategy_version":"MA v2 swing SL + ADX filter + London/New York overlap","rules":{"entry":"H1 EMA9/20 crossover; EMA50/200 trend filter; close beyond EMA50 in trend direction","sideways_filter":"ADX(14) >= 20","stop_loss":"latest confirmed 3-left/3-right swing in previous 50 bars, buffered by 0.10 ATR(14)","take_profit":"2R based on actual swing-stop distance","session":"both London and New York local sessions 08:00-17:00; timezone/DST aware","capital_usd":START,"risk_per_trade_pct":RISK,"daily_loss_threshold_pct":DAILY},"period_start_utc":start.isoformat(),"period_end_utc":end.isoformat(),"closed_bars_per_pair":{p:len(data[p]) for p in PAIRS},"starting_capital_usd":START,"ending_gross_equity_usd":round(eq,2),"gross_return_pct":round((eq/START-1)*100,2),"max_realized_drawdown_pct":round(dd,2),"closed_trades":len(rs),"open_positions_at_end":op,"win_rate_pct":round(sum(x>0 for x in rs)/len(rs)*100,2) if rs else 0,"average_R":round(sum(rs)/len(rs),3) if rs else 0,"total_R":round(sum(rs),2),"profit_factor":round(pf,3) if pf is not None else None,"max_consecutive_losses":mx,"daily_lockout_days":lockdays,"cost_sensitivity":costs,"per_pair":per,"limitations":"Gross excludes actual spread, commission, swaps and slippage. Cost scenarios are assumptions. Daily loss lockout blocks new entries only. OHLC simulation resolves same-bar SL/TP conflict as SL. Historical test is not a profit guarantee."}
 OUT.mkdir(parents=True,exist_ok=True);(OUT/"summary.json").write_text(json.dumps(report,indent=2)+"\n")
 cols=["pair","side","signal_utc","entry_utc","exit_utc","entry","exit","sl","tp","swing_level","adx14","risk_pips","risk_cash_usd","R","pnl_usd","reason","equity_after"]
 with (OUT/"trades.csv").open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(trades)
 msg=("📊 MA STRATEGY V2 BACKTEST\nRules: swing SL + ADX(14)>=20 + London/NY overlap\n"+f"Period UTC: {start:%Y-%m-%d} to {end:%Y-%m-%d}\nPairs: 8 | Trades: {len(rs)} | Win rate: {report['win_rate_pct']}%\nAvg R: {report['average_R']} | Total R: {report['total_R']} | PF: {report['profit_factor']}\nGross equity from USD 1000: USD {report['ending_gross_equity_usd']} | Return: {report['gross_return_pct']}%\nMax realized DD: {report['max_realized_drawdown_pct']}% | Max loss streak: {mx}\nAssumed 1.5-pip cost scenario total R: {costs['1.5']['total_R']}\n\nNo orders placed. Gross excludes actual trading costs.")
 print(msg);print("PER_PAIR",json.dumps(per)); sent=False
 if BOT and CHAT:
  try:
   r=requests.post("https://api.telegram.org/bot"+BOT+"/sendMessage",json={"chat_id":CHAT,"text":msg},timeout=25);sent=r.ok;print("TELEGRAM_REPORT_SENT" if sent else f"TELEGRAM_SEND_FAILED HTTP {r.status_code}")
  except Exception as e:print("TELEGRAM_SEND_FAILED",repr(e))
 else:print("TELEGRAM_NOT_CONFIGURED")
 (OUT/"telegram_status.txt").write_text("sent\n" if sent else "not_sent_check_secrets\n")
 gs=os.getenv("GITHUB_STEP_SUMMARY")
 if gs:
  with open(gs,"a") as f:
   f.write("# MA Strategy V2 Backtest\n\n")
   for k in ("period_start_utc","period_end_utc","closed_trades","win_rate_pct","average_R","total_R","profit_factor","ending_gross_equity_usd","gross_return_pct","max_realized_drawdown_pct","max_consecutive_losses"):f.write(f"- {k}: {report.get(k)}\n")
   f.write(f"- Assumed 1.5-pip cost scenario total R: {costs['1.5']['total_R']}\n\nSee summary.json and trades.csv artifacts.\n")
 print("BACKTEST_V2_COMPLETE")
if __name__=="__main__":main()
