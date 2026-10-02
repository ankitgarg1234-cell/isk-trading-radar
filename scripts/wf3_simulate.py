#!/usr/bin/env python3
from __future__ import annotations
import argparse, gzip, json
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
import scripts.walkforward_backtest as wf

def load_gz(path):
    with gzip.open(path,"rt",encoding="utf-8") as f:return json.load(f)

def validate_state(st):
    if st.cash < -0.01:raise AssertionError(f"negative cash {st.cash}")
    for s,p in st.pos.items():
        if abs(p.shares-round(p.shares))>1e-8:raise AssertionError(f"fractional shares {s}={p.shares}")

def daily_curve(st,market,benchmark,start,end):
    trades=defaultdict(list)
    for t in st.trades:trades[t["date"]].append(t)
    held={};cash=wf.STARTING;curve=[];last=None
    for r in benchmark["rows"]:
        ds=r["date"];d=date.fromisoformat(ds)
        if not (start<=d<=end):continue
        if last is not None:
            for sym,qty in list(held.items()):
                data=market.get(sym) or {}
                for sp in data.get("splits") or []:
                    sd=date.fromisoformat(sp["date"])
                    if last<sd<=d:held[sym]=held.get(sym,0)*(float(sp["numerator"])/float(sp["denominator"]))
                for dv in data.get("dividends") or []:
                    dd=date.fromisoformat(dv["date"])
                    if last<dd<=d:cash+=held.get(sym,0)*float(dv["amount"])
        for t in trades.get(ds,[]):
            gross=float(t["shares"])*float(t["price"]);fee=wf.fee(gross)
            if t["side"]=="BUY":
                cash-=gross+fee;held[t["symbol"]]=held.get(t["symbol"],0)+float(t["shares"])
            else:
                cash+=gross-fee;held[t["symbol"]]=max(0,held.get(t["symbol"],0)-float(t["shares"]))
                if held[t["symbol"]]<=1e-9:held.pop(t["symbol"],None)
        eq=cash
        for sym,qty in held.items():
            rr=wf.row_before(market.get(sym) or {},d)
            if rr and rr.get("close"):eq+=qty*float(rr["close"])
        curve.append({"date":ds,"equity":eq,"cash":cash})
        last=d
    return curve

def stat(name,st,curve):
    first=wf.STARTING;endv=float(curve[-1]["equity"])
    days=(date.fromisoformat(curve[-1]["date"])-date.fromisoformat(curve[0]["date"])).days;yrs=max(days/365.25,1/365.25)
    ret=endv/first-1;cagr=(endv/first)**(1/yrs)-1 if endv>0 else -1
    peak=0;dd=0;by=defaultdict(list)
    for r in curve:
        e=float(r["equity"]);peak=max(peak,e);dd=min(dd,e/peak-1 if peak else 0);by[date.fromisoformat(r["date"]).year].append(e)
    prev=first;annual={}
    for y in sorted(by):
        v=by[y][-1];annual[str(y)]=v/prev-1;prev=v
    sells=[t for t in st.trades if t["side"]=="SELL"];wins=[t for t in sells if float(t.get("pnl") or 0)>0]
    avg_days=(sum(float(t.get("days") or 0) for t in sells)/len(sells)) if sells else None
    return {"name":name,"end_value":round(endv,2),"total_return_pct":round(ret*100,2),"cagr_pct":round(cagr*100,2),
            "max_drawdown_pct":round(dd*100,2),"annual_returns_pct":{k:round(v*100,2) for k,v in annual.items()},
            "trade_count":len(st.trades),"sell_count":len(sells),"win_rate_pct":round(len(wins)/len(sells)*100,2) if sells else None,
            "average_holding_days":round(avg_days,1) if avg_days is not None else None,"ending_cash":round(st.cash,2),"open_positions":len(st.pos)}

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--dataset",required=True);ap.add_argument("--snapshots",nargs="+",required=True)
    ap.add_argument("--output",required=True);ap.add_argument("--markdown",required=True);ap.add_argument("--smoke",action="store_true")
    args=ap.parse_args();ds=load_gz(args.dataset);snaps={}
    for p in args.snapshots:snaps.update(load_gz(p)["snapshots"])
    dates=sorted(date.fromisoformat(x) for x in snaps)
    if not dates:raise RuntimeError("No snapshot dates")
    states=[wf.State("Current model (R/R >=2x)",2.0,False),wf.State("No 2x R/R floor",0.0,False),wf.State("Core-only (R/R >=2x)",2.0,True)]
    market=ds["market"]
    for i,d in enumerate(dates,1):
        row=snaps[d.isoformat()];base=row["analyses"];investable=set(row["investable"])
        for st in states:
            wf.run_state(st,d,base,investable,market);validate_state(st)
        if i%10==0 or i==len(dates):print(d,i,"/",len(dates),[(s.name,round(wf.equity(s,market,d))) for s in states],flush=True)
    if args.smoke:print("SMOKE PASS trades",sum(len(s.trades) for s in states),flush=True)
    start=dates[0];end=dates[-1];benchmark=ds["benchmark"];br=wf.bench(benchmark,start,end)
    results=[];daily={}
    for st in states:
        c=daily_curve(st,market,benchmark,start,end);daily[st.name]=c;results.append(stat(st.name,st,c))
    for r in results:
        r["alpha_vs_benchmark_total_pct"]=round(r["total_return_pct"]-br["total_return_pct"],2)
        r["cagr_spread_vs_benchmark_pct"]=round(r["cagr_pct"]-br["cagr_pct"],2)
    rep={"generated_at":datetime.now(timezone.utc).isoformat(),"period":{"start":start.isoformat(),"end":end.isoformat()},
         "methodology":{"mode":"staged weekly point-in-time two-stage replay","starting_capital":wf.STARTING,"trade_cost_bps":wf.COST_BPS,
                        "whole_shares":True,"hard_position_cap_pct":15,"min_rr_current":2.0,"benchmark_symbol":ds["benchmark_symbol"]},
         "coverage":ds["coverage"],"results":results,"benchmark":br,"weekly_curves":{s.name:s.curve for s in states},
         "daily_curves":daily,"trades":{s.name:s.trades for s in states}}
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(rep,indent=2))
    lines=["# 2024–2026 Staged Walk-Forward Backtest","",f"Period: {start} to {end}",f"Benchmark: {ds['benchmark_symbol']}","",
           "| Variant | End value | Total return | CAGR | Max DD | Trades | Win rate | Alpha vs benchmark |",
           "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in results:
        wr="—" if r["win_rate_pct"] is None else f"{r['win_rate_pct']:.1f}%"
        lines.append(f"| {r['name']} | USD {r['end_value']:,.0f} | {r['total_return_pct']:+.1f}% | {r['cagr_pct']:+.1f}% | {r['max_drawdown_pct']:.1f}% | {r['trade_count']} | {wr} | {r['alpha_vs_benchmark_total_pct']:+.1f} pp |")
    lines.append(f"| {br['name']} | USD {br['end_value']:,.0f} | {br['total_return_pct']:+.1f}% | {br['cagr_pct']:+.1f}% | {br['max_drawdown_pct']:.1f}% | — | — | — |")
    years=sorted(br["annual_returns_pct"]);lines+=["","## Annual returns","","| Variant | "+" | ".join(years)+" |","|---|"+"|".join(["---:"]*len(years))+"|"]
    for r in results+[br]:lines.append("| "+r["name"]+" | "+" | ".join(f"{r.get('annual_returns_pct',{}).get(y,0):+.1f}%" for y in years)+" |")
    lines+=["","## Integrity / limitations",
            "- Historical S&P 500 membership is reconstructed point-in-time from public constituent-change tables.",
            "- The historical universe is cheap-screened first; only scanner-selected names plus potential holdings receive deep SEC/fundamental analysis.",
            "- SEC fundamentals become usable only after their filing date. General historical analyst/news/strategic-capital archives are omitted rather than backfilled with present-day information.",
            "- Signals are evaluated at weekly closes and orders execute at the next available session open.",
            "- Whole shares, current score sizing, 15% hard position cap, 10 bps transaction costs and R/R >=2x buy/add floor are enforced.",
            "- Falling below 2x after entry is not by itself an exit trigger.",
            "- Historical simulation is not a guarantee of future performance."]
    Path(args.markdown).write_text("\n".join(lines)+"\n");print("\n".join(lines),flush=True)

if __name__=="__main__":main()
