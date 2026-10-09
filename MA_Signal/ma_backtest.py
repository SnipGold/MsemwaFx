import os,time,json,csv
from pathlib import Path
from datetime import datetime,timezone
from collections import defaultdict
import requests
API=os.getenv("TWELVEDATA_API_KEY","").strip(); BOT=os.getenv("TELEGRAM_BOT_TOKEN","").strip(); CHAT=os.getenv("TELEGRAM_CHAT_ID","").strip()
PAIRS=["EUR/USD","EUR/JPY","GBP/USD","AUD/USD","USD/CHF","USD/CAD","NZD/USD","USD/JPY"]; N=5000; START=1000.0
OUT=Path("MA_Signal/results")
def dt(s):
 x=datetime.fromisoformat(s.replace("Z","+00:00"));return x.replace(tzinfo=timezone.utc) if x.tzinfo is None else x.astimezone(timezone.utc)
def ema(v,p):
 if len(v)<p:return []
 a=2/(p+1);z=[sum(v[:p])/p]
 for q in v[p:]:z.append(a*q+(1-a)*z[-1])
 return [None]*(p-1)+z
def get(pair):
 r=requests.get("https://api.twelvedata.com/time_series",params={"symbol":pair,"interval":"1h","outputsize":N,"timezone":"UTC","apikey":API},timeout=45);r.raise_for_status();j=r.json()
 if "values" not in j:raise RuntimeError(j.get("message","No candle data"))
 c=[{"t":dt(x["datetime"]),"o":float(x["open"]),"h":float(x["high"]),"l":float(x["low"]),"c":float(x["close"])} for x in reversed(j["values"])][:-1]
 if len(c)<1000:raise RuntimeError(f"{pair}: only {len(c)} closed bars; refusing shallow backtest")
 return c
def prep(c):
 cl=[x["c"] for x in c];f,s,t,m=[ema(cl,p) for p in (9,20,50,200)]
 tr=[None]+[max(c[i]["h"]-c[i]["l"],abs(c[i]["h"]-c[i-1]["c"]),abs(c[i]["l"]-c[i-1]["c"])) for i in range(1,len(c))]
 av=[None]*len(c)
 for i in range(14,len(c)):av[i]=sum(tr[i-13:i+1])/14 if i==14 or av[i-1] is None else (av[i-1]*13+tr[i])/14
 sig=[None]*len(c)
 for i in range(220,len(c)):
  if av[i] is None or any(z is None for z in (f[i-1],f[i],s[i-1],s[i],t[i],m[i])):continue
  if f[i-1]<=s[i-1] and f[i]>s[i] and t[i]>m[i] and c[i]["c"]>t[i]:sig[i]=("BUY",av[i])
  elif f[i-1]>=s[i-1] and f[i]<s[i] and t[i]<m[i] and c[i]["c"]<t[i]:sig[i]=("SELL",av[i])
 return sig
def simulate(data,signals):
 clock=defaultdict(list)
 for p,cs in data.items():
  for i,x in enumerate(cs):clock[x["t"]].append((p,i))
 equity=peak=START;dd=0;day=None;dayeq=START;locked=False;lockdays=set();pos={};trades=[]
 for ts in sorted(clock):
  d=ts.date().isoformat()
  if d!=day:day=d;dayeq=equity;locked=False
  bars=sorted(clock[ts])
  for p,i in bars:
   if p not in pos:continue
   x=data[p][i];z=pos[p];ex=why=None
   if z["side"]=="BUY":
    if x["o"]<=z["sl"]:ex,why=x["o"],"GAP_SL"
    elif x["o"]>=z["tp"]:ex,why=z["tp"],"TP"
    elif x["l"]<=z["sl"]:ex,why=z["sl"],"SL (conservative same-bar rule)"
    elif x["h"]>=z["tp"]:ex,why=z["tp"],"TP"
    rr=(ex-z["entry"])/z["dist"] if ex is not None else None
   else:
    if x["o"]>=z["sl"]:ex,why=x["o"],"GAP_SL"
    elif x["o"]<=z["tp"]:ex,why=z["tp"],"TP"
    elif x["h"]>=z["sl"]:ex,why=z["sl"],"SL (conservative same-bar rule)"
    elif x["l"]<=z["tp"]:ex,why=z["tp"],"TP"
    rr=(z["entry"]-ex)/z["dist"] if ex is not None else None
   if ex is not None:
    pnl=rr*z["riskcash"];equity+=pnl
    trades.append({"pair":p,"side":z["side"],"entry_utc":z["time"].isoformat(),"exit_utc":ts.isoformat(),"entry":z["entry"],"exit":ex,"sl":z["sl"],"tp":z["tp"],"risk_pips":z["dist"]/(.01 if "JPY" in p else .0001),"risk_cash_usd":z["riskcash"],"R":rr,"pnl_usd":pnl,"reason":why,"equity_after":equity})
    del pos[p];peak=max(peak,equity);dd=max(dd,(peak-equity)/peak*100 if peak else 0)
    if (dayeq-equity)/dayeq>=.03:locked=True;lockdays.add(d)
  for p,i in bars:
   if p in pos or i==0 or locked:continue
   sig=signals[p][i-1]
   if not sig:continue
   side,a=sig;x=data[p][i];entry=x["o"];dist=1.5*a
   pos[p]={"side":side,"entry":entry,"sl":entry-dist if side=="BUY" else entry+dist,"tp":entry+2*dist if side=="BUY" else entry-2*dist,"dist":dist,"riskcash":equity*.01,"time":x["t"]}
 return trades,equity,dd,len(pos),len(lockdays),min(clock),max(clock)
def main():
 if not API:raise SystemExit("Missing TWELVEDATA_API_KEY secret")
 data={};sig={}
 for i,p in enumerate(PAIRS):
  print(f"Fetch {i+1}/8 {p}");data[p]=get(p);sig[p]=prep(data[p]);print("closed bars",len(data[p]))
  if i<7:time.sleep(9)
 trades,eq,dd,open_n,lockdays,start,end=simulate(data,sig);r=[x["R"] for x in trades];w=[x for x in r if x>0];l=[x for x in r if x<0]
 pf=sum(w)/abs(sum(l)) if l and sum(l) else None;streak=mx=0
 for x in r:streak=streak+1 if x<0 else 0;mx=max(mx,streak)
 costs={}
 for cost in (0,1,1.5,2):
  net=[x["R"]-cost/x["risk_pips"] for x in trades if x["risk_pips"]>0]
  costs[str(cost)]={"assumed_cost_pips":cost,"total_R":round(sum(net),2),"avg_R":round(sum(net)/len(net),3) if net else 0,"win_rate_pct":round(sum(x>0 for x in net)/len(net)*100,2) if net else 0}
 per={}
 for p in PAIRS:
  q=[x for x in trades if x["pair"]==p];per[p]={"trades":len(q),"win_rate_pct":round(sum(x["R"]>0 for x in q)/len(q)*100,2) if q else 0,"total_R":round(sum(x["R"] for x in q),2),"avg_R":round(sum(x["R"] for x in q)/len(q),3) if q else 0}
 report={"period_start_utc":start.isoformat(),"period_end_utc":end.isoformat(),"closed_bars_per_pair":{p:len(data[p]) for p in PAIRS},"starting_capital_usd":START,"ending_gross_equity_usd":round(eq,2),"gross_return_pct":round((eq/START-1)*100,2),"max_realized_drawdown_pct":round(dd,2),"closed_trades":len(r),"open_positions_at_end":open_n,"win_rate_pct":round(len(w)/len(r)*100,2) if r else 0,"average_R":round(sum(r)/len(r),3) if r else 0,"total_R":round(sum(r),2),"profit_factor":round(pf,3) if pf is not None else None,"max_consecutive_losses":mx,"daily_lockout_days":lockdays,"cost_sensitivity":costs,"per_pair":per,"limitations":"Gross ignores spread, commission, slippage and swaps. Cost scenarios are assumed, not measured HFM Cent costs. Daily limit blocks new entries after 3% realized daily loss, does not close existing positions. OHLC not tick-level; SL counted first on same-candle conflict."}
 OUT.mkdir(parents=True,exist_ok=True);(OUT/"summary.json").write_text(json.dumps(report,indent=2)+"\n")
 with (OUT/"trades.csv").open("w",newline="") as f:
  cols=list(trades[0]) if trades else ["pair","side","entry_utc","exit_utc","entry","exit","sl","tp","risk_pips","risk_cash_usd","R","pnl_usd","reason","equity_after"];z=csv.DictWriter(f,fieldnames=cols);z.writeheader();z.writerows(trades)
 msg=("📊 MA STRATEGY BACKTEST H1\n"+f"Period UTC: {start:%Y-%m-%d} to {end:%Y-%m-%d}\n"+f"Pairs: 8 | Trades: {len(r)} | Win rate: {report['win_rate_pct']}%\n"+f"Avg R: {report['average_R']} | Total R: {report['total_R']} | PF: {report['profit_factor']}\n"+f"Gross equity from USD 1000: USD {report['ending_gross_equity_usd']} | Return: {report['gross_return_pct']}%\n"+f"Max realized DD: {report['max_realized_drawdown_pct']}% | Max loss streak: {mx}\n"+f"Estimated total R at assumed 1.5-pip cost: {costs['1.5']['total_R']}\n\nGross excludes spread/slippage/commission. Cost is scenario only, not measured HFM spread. No trades placed.")
 print(msg);print("PER_PAIR",json.dumps(per))
 sent=False
 if BOT and CHAT:
  res=requests.post("https://api.telegram.org/bot"+BOT+"/sendMessage",json={"chat_id":CHAT,"text":msg},timeout=25)
  sent=res.ok;print("TELEGRAM_REPORT_SENT" if sent else "TELEGRAM_SEND_FAILED "+str(res.status_code)+" "+res.text[:200])
 else:print("TELEGRAM_NOT_CONFIGURED: missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
 (OUT/"telegram_status.txt").write_text("sent\n" if sent else "not_sent_check_secrets\n")
 gs=os.getenv("GITHUB_STEP_SUMMARY")
 if gs:
  with open(gs,"a") as f:
   f.write("# MA Strategy Backtest\n\n")
   for k in ("period_start_utc","period_end_utc","closed_trades","win_rate_pct","average_R","total_R","profit_factor","ending_gross_equity_usd","gross_return_pct","max_realized_drawdown_pct","max_consecutive_losses"):f.write(f"- {k}: {report.get(k)}\n")
   f.write(f"- Estimated total R at assumed 1.5-pip cost: {costs['1.5']['total_R']}\n\nSee artifact summary.json and trades.csv. Gross excludes costs.\n")
 print("BACKTEST_COMPLETE")
if __name__=="__main__":main()
