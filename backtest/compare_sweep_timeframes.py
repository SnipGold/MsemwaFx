#!/usr/bin/env python3
"""Compare standalone M15, H1 and H4 liquidity sweep/reclaim systems."""
import csv, importlib.util
from pathlib import Path

spec=importlib.util.spec_from_file_location("base",Path("backtest/liquidity_sweeps_backtest.py"))
base=importlib.util.module_from_spec(spec); spec.loader.exec_module(base)
DATA=Path("replay_data"); OUT=Path("liquidity_sweeps_results")
FRAMES={"M15":("15min",15),"H1":("1h",60),"H4":("4h",240)}
TARGETS=(1.0,2.0,3.0,4.0,5.0)

def main():
    OUT.mkdir(exist_ok=True); summaries=[]; alltrades=[]
    for tf,(suffix,mins) in FRAMES.items():
        for path in sorted(DATA.glob(f"*_{suffix}.csv")):
            symbol=path.name.removesuffix(f"_{suffix}.csv")
            bars=base.load_bars(path)
            if len(bars)<20: print(f"SKIP {symbol} {tf}: only {len(bars)} bars"); continue
            # Keep the maximum holding horizon constant at 24 hours across timeframes.
            base.MAX_HOLD_BARS=max(1,(24*60)//mins)
            signals=base.find_signals(bars,symbol)
            for target in TARGETS:
                trades,skipped=base.simulate_one_target(bars,signals,target)
                row=base.summarize(symbol,target,trades,len(signals),skipped)
                row.update({"timeframe":tf,"data_bars":len(bars),"first_bar":bars[0]["time"].isoformat(sep=" "),"last_bar":bars[-1]["time"].isoformat(sep=" ")})
                summaries.append(row)
                for t in trades: t["timeframe"]=tf
                alltrades.extend(trades)
        print(f"{tf} processing complete.")
    if not summaries: raise SystemExit("No timeframe datasets were available.")
    fields=["timeframe"]+[k for k in summaries[0] if k!="timeframe"]
    with (OUT/"timeframe_comparison.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(summaries)
    tf_order={"M15":0,"H1":1,"H4":2}
    alltrades.sort(key=lambda x:(tf_order.get(x.get("timeframe"),9),x.get("symbol",""),x.get("signal_time",""),x.get("target_R",0)))
    tradefields=list(alltrades[0].keys()) if alltrades else ["timeframe","symbol","signal_time","target_R","outcome","realized_R_gross"]
    with (OUT/"timeframe_trades.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=tradefields);w.writeheader();w.writerows(alltrades)
    print("TIMEFRAME COMPARISON (standalone sweep/reclaim, 24h max hold; costs excluded)")
    for tf in FRAMES:
        for target in TARGETS:
            rs=[r for r in summaries if r["timeframe"]==tf and r["target_R"]==target]
            if not rs: continue
            n=sum(r["trades_taken"] for r in rs); wins=sum(r["wins"] for r in rs)
            net=round(sum(float(r["net_R_gross"]) for r in rs),4)
            positive=sum(float(r["net_R_gross"])>0 for r in rs)
            print(f"{tf} target={target:g}R instruments={len(rs)} trades={n} wins={wins} win_rate={100*wins/n if n else 0:.2f}% net_R={net:.4f} positive_pairs={positive}/{len(rs)}")
    print("No spread, commission, or slippage included. Standalone timeframe sweeps; no cross-timeframe confirmation.")
if __name__=="__main__": main()
