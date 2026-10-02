#!/usr/bin/env python3
from __future__ import annotations
import copy, hashlib, json, math, sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"));sys.path.insert(0,str(ROOT))

import walkforward_backtest as wf
import wf3_offline_valuein as base
import wf3_offline_valuein_daily as daily
import app.analysis_engine as ae
import app.portfolio_engine as pe

ORIG_ENTRY=pe.entry_attention_signal
ORIG_TARGET=pe.score_target_allocation_pct
THRESHOLDS=[68,66,64,62]
ALLOC_FLOORS=[8.0,10.0,12.0]

def relax_core(a,threshold):
    if threshold>=68:return a
    score=float(a.get("deterministic_score") or 0)
    if score<threshold or score>=68:return a
    blockers=list(a.get("core_blockers") or [])
    other=[b for b in blockers if b!="system conviction < 68"]
    if other:return a
    b=copy.deepcopy(a)
    b["lane"]="CORE_QUALITY";b["lane_label"]="Core Quality Lane";b["lane_qualified"]=True
    b["core_quality_qualified"]=True;b["explosive_qualified"]=False;b["category"]="Core"
    b["core_blockers"]=other
    b["lane_reasons"]=[x for x in (b.get("lane_reasons") or []) if "below 68" not in str(x)]
    return b

def make_entry(threshold):
    def entry(a):
        x=ORIG_ENTRY(a)
        if x:return x
        if a.get("lane_qualified") is not True:return None
        if a.get("lane") not in {"CORE_QUALITY","EXPLOSIVE"}:return None
        if float(a.get("price") or 0)<5:return None
        if bool((a.get("promotion_risk") or {}).get("hard_reject")):return None
        if float(a.get("risk_reward") or 0)<pe.MIN_ENTRY_RISK_REWARD:return None
        if bool((a.get("thesis_assessment") or {}).get("invalidated")):return None
        if a.get("negative_news_override"):return None
        if str(a.get("decision_confidence") or "medium").lower()=="low":return None
        zone=str(a.get("entry_zone_status") or "").upper()
        if zone not in {"PRIMARY_BUY","BETTER_BUY"}:return None
        score=float(a.get("deterministic_score") or 0)
        if score>=threshold:return "STARTER BUY"
        return None
    return entry

def make_target(threshold,floor):
    def target(score):
        s=float(score or 0)
        if s<threshold:return 0.0
        # Preserve existing conviction slope above 68, but allow lower-score
        # experimental candidates to receive only the tested starter floor.
        base_pct=ORIG_TARGET(s)
        if base_pct<=0:base_pct=floor
        return min(15.0,max(base_pct,floor))
    return target

def run_variant(st,threshold,floor,day,analyses,shortlist,market):
    old_entry=pe.entry_attention_signal;old_target=pe.score_target_allocation_pct
    pe.entry_attention_signal=make_entry(threshold)
    pe.score_target_allocation_pct=make_target(threshold,floor)
    try:
        wf.run_state(st,day,analyses,set(shortlist),market)
    finally:
        pe.entry_attention_signal=old_entry;pe.score_target_allocation_pct=old_target

def period_stats(curve,start,end):
    rows=[r for r in curve if start<=base.d(r["date"])<=end]
    if not rows:return {}
    start_eq=float(rows[0]["equity"]);end_eq=float(rows[-1]["equity"])
    peak=start_eq;dd=0
    for r in rows:
        e=float(r["equity"]);peak=max(peak,e);dd=min(dd,e/peak-1 if peak else 0)
    return {"start_equity":round(start_eq,2),"end_equity":round(end_eq,2),
            "return_pct":round((end_eq/start_eq-1)*100,2),"max_drawdown_pct":round(dd*100,2)}

def benchmark_period(data,start,end):
    rows=[r for r in data["rows"] if start<=base.d(r["date"])<=end]
    first=float(rows[0]["close"]);last=float(rows[-1]["close"]);peak=first;dd=0
    for r in rows:
        v=float(r["close"]);peak=max(peak,v);dd=min(dd,v/peak-1)
    return {"return_pct":round((last/first-1)*100,2),"max_drawdown_pct":round(dd*100,2)}

def main():
    prices=base.load_gz(base.PRICE_PATH);funds=base.load_gz(base.FUND_PATH)
    market=prices["market"];sectors=prices["membership"]["sectors"];etfs=prices["sector_etfs"]
    store=base.PITFundamentals(funds)
    start=base.d(prices["period"]["start"]);end=base.d(prices["period"]["end"])
    trading=[base.d(r["date"]) for r in prices["benchmark"]["rows"] if start<=base.d(r["date"])<=end]
    quick=daily.precompute_quick(market)
    members=set(prices["membership"]["start_members"]);changes=defaultdict(list)
    for x in prices["membership"]["changes"]:changes[base.d(x["date"])].append(x)

    configs=[];states=[]
    for t in THRESHOLDS:
        for f in ALLOC_FLOORS:
            configs.append({"threshold":t,"floor":f,"name":f"score>={t} / min {int(f)}%"})
            states.append(wf.State(configs[-1]["name"],2.0,False))

    for i,day in enumerate(trading,1):
        for cd in sorted([x for x in changes if x<=day]):
            for x in changes.pop(cd):
                if x.get("removed"):members.discard(x["removed"])
                if x.get("added"):members.add(x["added"])
        rows={s:r for s,r in quick.get(day.isoformat(),{}).items() if s in members}
        shortlist=daily.choose(rows,160)
        held=set().union(*(set(st.pos) for st in states))
        raw={}
        for sym in set(shortlist)|held:
            a=base.analyse(sym,day,market,store,sectors,etfs)
            if a:raw[sym]=a
        adjusted={}
        for t in THRESHOLDS:
            adjusted[t]={s:relax_core(a,t) for s,a in raw.items()}
        for st,cfg in zip(states,configs):
            run_variant(st,cfg["threshold"],cfg["floor"],day,adjusted[cfg["threshold"]],shortlist,market)
            base.validate(st,adjusted[cfg["threshold"]])
        if i%75==0 or i==len(trading):
            print("GRID",day,i,"/",len(trading),[(s.name,round(wf.equity(s,market,day)),len(s.pos)) for s in states],flush=True)

    benchmark=prices["benchmark"]
    train_start=trading[0];train_end=date(2025,12,31);val_start=date(2026,1,1);val_end=trading[-1]
    btrain=benchmark_period(benchmark,train_start,train_end);bval=benchmark_period(benchmark,val_start,val_end)
    results=[]
    for st,cfg in zip(states,configs):
        curve=base.daily_curve(st,market,benchmark,trading[0],trading[-1])
        full=base.stat(st.name,st,curve);train=period_stats(curve,train_start,train_end);val=period_stats(curve,val_start,val_end)
        buys=[t for t in st.trades if t["side"]=="BUY"];sells=[t for t in st.trades if t["side"]=="SELL"]
        cash_pcts=[float(r.get("cash") or 0)/max(1,float(r.get("equity") or 1))*100 for r in st.curve]
        results.append({**cfg,"full":full,"train":train,"validation":val,"buy_count":len(buys),"sell_count":len(sells),
                        "average_cash_pct":round(sum(cash_pcts)/len(cash_pcts),2) if cash_pcts else None,
                        "trades":st.trades})

    # Select only on 2024-2025. Risk target remains <=15% train drawdown.
    eligible=[r for r in results if r["train"].get("max_drawdown_pct",0)>=-15]
    selected=max(eligible,key=lambda r:(r["train"].get("return_pct",-999),-r["average_cash_pct"])) if eligible else None
    out={"version":"wf3-score-sizing-walkforward-v1","period":{"full":[str(trading[0]),str(trading[-1])],
          "train":[str(train_start),str(train_end)],"validation":[str(val_start),str(val_end)]},
         "fixed":{"deep_candidates":160,"min_rr":2.0,"fundamental_floor":14.0,"entry_zones":"unchanged",
                  "split_accounting":"corrected","thesis_exit_rule":"unchanged","position_cap_pct":15},
         "benchmark":{"train":btrain,"validation":bval,"full":wf.bench(benchmark,trading[0],trading[-1])},
         "results":results,"selected_on_train":selected}
    core={"period":out["period"],"results":results,"benchmark":out["benchmark"],"selected":selected["name"] if selected else None}
    out["deterministic_hash"]=hashlib.sha256(json.dumps(core,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    p=ROOT/"backtests/results/wf3_score_sizing_walkforward.json";p.write_text(json.dumps(out,indent=2))
    lines=["# WF3 Score Threshold × Sizing Walk-Forward","",
           "2024–2025 selects the configuration; 2026 is untouched validation.","",
           "| Config | Train return | Train DD | 2026 return | 2026 DD | Full return | Avg cash | Buys |",
           "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in results:
        lines.append(f"| {r['name']} | {r['train']['return_pct']:+.2f}% | {r['train']['max_drawdown_pct']:.2f}% | {r['validation']['return_pct']:+.2f}% | {r['validation']['max_drawdown_pct']:.2f}% | {r['full']['total_return_pct']:+.2f}% | {r['average_cash_pct']:.1f}% | {r['buy_count']} |")
    lines+=["",f"Train benchmark: {btrain['return_pct']:+.2f}% (DD {btrain['max_drawdown_pct']:.2f}%)",
            f"2026 benchmark: {bval['return_pct']:+.2f}% (DD {bval['max_drawdown_pct']:.2f}%)"]
    if selected:
        lines+=["",f"**Selected on train:** {selected['name']}",
                f"Train {selected['train']['return_pct']:+.2f}% → 2026 validation {selected['validation']['return_pct']:+.2f}%."]
    lines+=["","No configuration is selected using 2026 performance."]
    (ROOT/"backtests/results/wf3_score_sizing_walkforward.md").write_text("\n".join(lines)+"\n")
    print("GRID_RESULT="+json.dumps({"selected":selected,"benchmark":out["benchmark"],"hash":out["deterministic_hash"]},separators=(",",":")),flush=True)

if __name__=="__main__":main()
