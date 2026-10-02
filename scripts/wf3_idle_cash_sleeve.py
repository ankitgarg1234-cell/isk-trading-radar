#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"));sys.path.insert(0,str(ROOT))

import walkforward_backtest as wf
import wf3_offline_valuein as base
import wf3_offline_valuein_daily as daily
import app.portfolio_engine as pe

ORIG_TARGET=pe.score_target_allocation_pct
SLEEVE_FRACTIONS=[0.0,0.50,0.75,1.0]
MIN_ALLOC=12.0

def target(score):
    b=ORIG_TARGET(score)
    if b<=0:return 0.0
    return min(15.0,max(b,MIN_ALLOC))

def period_stats(curve,start,end):
    rows=[r for r in curve if start<=base.d(r["date"])<=end]
    first=float(rows[0]["equity"]);last=float(rows[-1]["equity"]);peak=first;dd=0
    for r in rows:
        e=float(r["equity"]);peak=max(peak,e);dd=min(dd,e/peak-1 if peak else 0)
    return {"return_pct":round((last/first-1)*100,2),"max_drawdown_pct":round(dd*100,2),
            "start_equity":round(first,2),"end_equity":round(last,2)}

def benchmark_period(rows,start,end):
    x=[r for r in rows if start<=base.d(r["date"])<=end]
    f=float(x[0]["close"]);l=float(x[-1]["close"]);p=f;dd=0
    for r in x:
        v=float(r["close"]);p=max(p,v);dd=min(dd,v/p-1)
    return {"return_pct":round((l/f-1)*100,2),"max_drawdown_pct":round(dd*100,2)}

def main():
    prices=base.load_gz(base.PRICE_PATH);funds=base.load_gz(base.FUND_PATH)
    market=prices["market"];sectors=prices["membership"]["sectors"];etfs=prices["sector_etfs"]
    store=base.PITFundamentals(funds)
    start=base.d(prices["period"]["start"]);end=base.d(prices["period"]["end"])
    benchmark=prices["benchmark"];brows=[r for r in benchmark["rows"] if start<=base.d(r["date"])<=end]
    bclose={base.d(r["date"]):float(r["close"]) for r in brows}
    trading=sorted(bclose)
    quick=daily.precompute_quick(market)
    members=set(prices["membership"]["start_members"]);changes=defaultdict(list)
    for x in prices["membership"]["changes"]:changes[base.d(x["date"])].append(x)

    states=[wf.State(f"score>=68/min12/sleeve{int(fr*100)}",2.0,False) for fr in SLEEVE_FRACTIONS]
    prev_day=None
    for i,day in enumerate(trading,1):
        if prev_day is not None:
            br=bclose[day]/bclose[prev_day]-1
            for st,fr in zip(states,SLEEVE_FRACTIONS):
                if fr>0 and st.cash>0:
                    st.cash *= (1.0 + fr*br)
        for cd in sorted([x for x in changes if x<=day]):
            for x in changes.pop(cd):
                if x.get("removed"):members.discard(x["removed"])
                if x.get("added"):members.add(x["added"])
        dayrows={s:r for s,r in quick.get(day.isoformat(),{}).items() if s in members}
        shortlist=daily.choose(dayrows,160)
        held=set().union(*(set(st.pos) for st in states));analyses={}
        for sym in set(shortlist)|held:
            a=base.analyse(sym,day,market,store,sectors,etfs)
            if a:analyses[sym]=a

        old=pe.score_target_allocation_pct;pe.score_target_allocation_pct=target
        try:
            for st in states:
                wf.run_state(st,day,analyses,set(shortlist),market);base.validate(st,analyses)
        finally:
            pe.score_target_allocation_pct=old
        prev_day=day
        if i%75==0 or i==len(trading):
            print("SLEEVE",day,i,"/",len(trading),[(st.name,round(wf.equity(st,market,day)),round(st.cash)) for st in states],flush=True)

    train_start=trading[0];train_end=date(2025,12,31);val_start=date(2026,1,1);val_end=trading[-1]
    results=[]
    for st,fr in zip(states,SLEEVE_FRACTIONS):
        full=wf.stat(st);train=period_stats(st.curve,train_start,train_end);val=period_stats(st.curve,val_start,val_end)
        cash_pct=[float(r["cash"])/max(1,float(r["equity"]))*100 for r in st.curve]
        results.append({"name":st.name,"sleeve_fraction":fr,"full":full,"train":train,"validation":val,
                        "avg_cash_account_pct":round(sum(cash_pct)/len(cash_pct),2),
                        "buy_count":sum(1 for t in st.trades if t["side"]=="BUY"),"trades":st.trades})
    btrain=benchmark_period(brows,train_start,train_end);bval=benchmark_period(brows,val_start,val_end);bfull=wf.bench(benchmark,trading[0],trading[-1])
    eligible=[r for r in results if r["train"]["max_drawdown_pct"]>=-15]
    selected=max(eligible,key=lambda r:r["train"]["return_pct"]) if eligible else None
    out={"version":"wf3-idle-cash-sleeve-v1","period":{"train":[str(train_start),str(train_end)],"validation":[str(val_start),str(val_end)]},
         "fixed":{"score_threshold":68,"min_initial_allocation_pct":12,"deep_candidates":160,"min_rr":2.0,
                  "lane_entry_rules":"unchanged","position_cap_pct":15,"split_accounting":"corrected"},
         "sleeve_definition":{"description":"Synthetic daily S&P Total Return sweep on the selected fraction of otherwise idle cash",
                              "purpose":"diagnostic alpha-overlay test","limitations":"idealized daily liquidity; no sleeve turnover cost; not yet an executable ETF implementation"},
         "results":results,"benchmark":{"train":btrain,"validation":bval,"full":bfull},"selected_on_train":selected}
    core={"results":results,"benchmark":out["benchmark"],"selected":selected["name"] if selected else None}
    out["deterministic_hash"]=hashlib.sha256(json.dumps(core,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    p=ROOT/"backtests/results/wf3_idle_cash_sleeve.json";p.write_text(json.dumps(out,indent=2))
    lines=["# WF3 Idle-Cash S&P Sleeve Walk-Forward","",
           "The stock model is fixed at score>=68, 12% minimum initial allocation and 160-name deep coverage.","",
           "| Idle cash swept to S&P | Train return | Train DD | 2026 return | 2026 DD | Full return |",
           "|---:|---:|---:|---:|---:|---:|"]
    for r in results:
        lines.append(f"| {int(r['sleeve_fraction']*100)}% | {r['train']['return_pct']:+.2f}% | {r['train']['max_drawdown_pct']:.2f}% | {r['validation']['return_pct']:+.2f}% | {r['validation']['max_drawdown_pct']:.2f}% | {r['full']['total_return_pct']:+.2f}% |")
    lines+=["",f"Train S&P: {btrain['return_pct']:+.2f}% / DD {btrain['max_drawdown_pct']:.2f}%",
            f"2026 S&P: {bval['return_pct']:+.2f}% / DD {bval['max_drawdown_pct']:.2f}%"]
    if selected:lines+=["",f"Selected on train under 15% DD: **{selected['name']}**",
                         f"2026 validation: {selected['validation']['return_pct']:+.2f}% vs S&P {bval['return_pct']:+.2f}%."]
    lines+=["","This sleeve is a diagnostic. It is not deployed to production and assumes frictionless daily rebalancing of the idle-cash sleeve."]
    (ROOT/"backtests/results/wf3_idle_cash_sleeve.md").write_text("\n".join(lines)+"\n")
    print("SLEEVE_RESULT="+json.dumps({"results":results,"benchmark":out["benchmark"],"selected":selected,"hash":out["deterministic_hash"]},separators=(",",":")),flush=True)

if __name__=="__main__":main()
