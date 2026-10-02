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

SCORE_FLOORS=[68,66,64,62]
ALLOC_FLOORS=[8.0,10.0,12.0]

def qualifies_core_at(a,score_floor):
    f=a.get("fundamentals") or {}
    t=a.get("technicals") or {}
    fs=float((a.get("breakdown") or {}).get("Fundamentals") or 0)
    fconf=str(a.get("fundamental_confidence") or "low").lower()
    score=float(a.get("deterministic_score") or 0)
    promotion=a.get("promotion_risk") or {}
    return (
        not bool(promotion.get("hard_reject"))
        and fs>=float(ae.MIN_FUNDAMENTAL_SCORE)
        and fconf in {"medium","high"}
        and score>=score_floor
        and not a.get("negative_news_override")
        and float(t.get("avg_dollar_volume_20") or 0)>=float(ae.CORE_MIN_AVG_DOLLAR_VOLUME)
        and float(f.get("marketCap") or 0)>=float(ae.MIN_MARKET_CAP)
    )

def variant_analysis(a,score_floor):
    x=copy.deepcopy(a)
    # Keep true Explosive qualification untouched. Only relax the Core deterministic
    # score floor while preserving every other Core hard gate.
    if x.get("explosive_qualified") is True:
        return x
    if qualifies_core_at(x,score_floor):
        x["lane"]="CORE_QUALITY"
        x["lane_label"]="Core Quality"
        x["lane_qualified"]=True
        x["core_quality_qualified"]=True
        blockers=[b for b in (x.get("core_blockers") or []) if not str(b).startswith("system conviction")]
        x["core_blockers"]=blockers
    return x

def make_entry_signal(score_floor):
    def signal(a):
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
        if score>=85:return "STRONG BUY"
        if score>=75:return "BUY"
        if score>=score_floor:return "STARTER BUY"
        return None
    return signal

def make_target(score_floor,alloc_floor):
    def target(score):
        s=float(score or 0)
        if s<score_floor:return 0.0
        base_pct=ORIG_TARGET(s)
        return min(15.0,max(float(alloc_floor),float(base_pct)))
    return target

def run_variant(st,score_floor,alloc_floor,day,base_analyses,shortlist,market):
    analyses={s:variant_analysis(a,score_floor) for s,a in base_analyses.items()}
    old_entry=pe.entry_attention_signal
    old_target=pe.score_target_allocation_pct
    pe.entry_attention_signal=make_entry_signal(score_floor)
    pe.score_target_allocation_pct=make_target(score_floor,alloc_floor)
    try:
        wf.run_state(st,day,analyses,set(shortlist),market)
    finally:
        pe.entry_attention_signal=old_entry
        pe.score_target_allocation_pct=old_target
    base.validate(st,analyses)

def main():
    prices=base.load_gz(base.PRICE_PATH);funds=base.load_gz(base.FUND_PATH)
    market=prices["market"];sectors=prices["membership"]["sectors"];etfs=prices["sector_etfs"]
    store=base.PITFundamentals(funds)
    start=base.d(prices["period"]["start"]);end=base.d(prices["period"]["end"])
    trading=[base.d(r["date"]) for r in prices["benchmark"]["rows"] if start<=base.d(r["date"])<=end]
    quick=daily.precompute_quick(market)
    members=set(prices["membership"]["start_members"])
    changes=defaultdict(list)
    for x in prices["membership"]["changes"]:changes[base.d(x["date"])].append(x)

    configs=[(s,a) for s in SCORE_FLOORS for a in ALLOC_FLOORS]
    states=[]
    for score,alloc in configs:
        states.append(wf.State(f"Score>={score} / min {int(alloc)}%",2.0,False))

    funnel={f"{s}_{int(a)}":{"core":0,"rr2":0,"entry":0} for s,a in configs}

    for i,day in enumerate(trading,1):
        for cd in sorted([x for x in changes if x<=day]):
            for x in changes.pop(cd):
                if x.get("removed"):members.discard(x["removed"])
                if x.get("added"):members.add(x["added"])
        dayrows={s:r for s,r in quick.get(day.isoformat(),{}).items() if s in members}
        shortlist=daily.choose(dayrows,160)
        held=set().union(*(set(st.pos) for st in states))
        base_analyses={}
        for sym in set(shortlist)|held:
            a=base.analyse(sym,day,market,store,sectors,etfs)
            if a:base_analyses[sym]=a

        # Measure opportunity funnel once per score floor (allocation doesn't alter eligibility).
        for score in SCORE_FLOORS:
            sig=make_entry_signal(score)
            key=f"{score}_{int(ALLOC_FLOORS[0])}"
            core=rr2=entry=0
            for sym in shortlist:
                a=base_analyses.get(sym)
                if not a:continue
                va=variant_analysis(a,score)
                if va.get("lane_qualified") is True:
                    core+=1
                    if float(va.get("risk_reward") or 0)>=2:
                        rr2+=1
                        if sig(va) in pe.INVESTABLE_ENTRY_ACTIONS:entry+=1
            for alloc in ALLOC_FLOORS:
                k=f"{score}_{int(alloc)}";funnel[k]["core"]+=core;funnel[k]["rr2"]+=rr2;funnel[k]["entry"]+=entry

        for st,(score,alloc) in zip(states,configs):
            run_variant(st,score,alloc,day,base_analyses,shortlist,market)

        if i%75==0 or i==len(trading):
            print("GRID",day,i,"/",len(trading),
                  [(st.name,round(wf.equity(st,market,day)),len(st.pos),round(st.cash)) for st in states],flush=True)

    benchmark=prices["benchmark"];br=wf.bench(benchmark,trading[0],trading[-1])
    results=[];trades={}
    for st,(score,alloc) in zip(states,configs):
        curve=base.daily_curve(st,market,benchmark,trading[0],trading[-1])
        r=base.stat(st.name,st,curve)
        r["score_floor"]=score;r["min_initial_allocation_pct"]=alloc
        r["alpha_vs_benchmark_total_pct"]=round(r["total_return_pct"]-br["total_return_pct"],2)
        r["cagr_spread_vs_benchmark_pct"]=round(r["cagr_pct"]-br["cagr_pct"],2)
        r["buy_count"]=sum(1 for t in st.trades if t["side"]=="BUY")
        r["sell_count"]=sum(1 for t in st.trades if t["side"]=="SELL")
        cash_pcts=[float(x.get("cash") or 0)/float(x.get("equity") or 1)*100 for x in st.curve if float(x.get("equity") or 0)>0]
        r["average_cash_pct"]=round(sum(cash_pcts)/len(cash_pcts),2) if cash_pcts else None
        r["ending_cash_pct"]=round(st.cash/max(1,wf.equity(st,market,trading[-1]))*100,2)
        r["funnel"]=funnel[f"{score}_{int(alloc)}"]
        r["meets_15pct_dd_target"]=r["max_drawdown_pct"]>=-15.0
        results.append(r);trades[st.name]=st.trades

    # Sort by return for diagnosis only; no production selection is auto-deployed.
    ranked=sorted(results,key=lambda r:r["total_return_pct"],reverse=True)
    out={"version":"wf3-score-sizing-grid-v1","period":{"start":trading[0].isoformat(),"end":trading[-1].isoformat()},
         "fixed_rules":{"deep_candidates_daily":160,"fundamental_floor":float(ae.MIN_FUNDAMENTAL_SCORE),
                        "min_rr":2.0,"entry_zones":"unchanged PRIMARY_BUY/BETTER_BUY",
                        "whole_shares":True,"position_cap_pct":15,"transaction_cost_bps":wf.COST_BPS,
                        "exit_rule":"thesis/fundamental invalidation only; lane loss alone does not sell",
                        "split_accounting":"corrected; Yahoo OHLC already split-adjusted"},
         "grid":{"score_floors":SCORE_FLOORS,"allocation_floors":ALLOC_FLOORS},
         "results":results,"ranked_by_return":ranked,"benchmark":br,"trades":trades}
    core={"period":out["period"],"results":results,"benchmark":br,"trades":trades}
    out["deterministic_hash"]=hashlib.sha256(json.dumps(core,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    p=ROOT/"backtests/results/wf3_score_sizing_grid.json";p.write_text(json.dumps(out,indent=2))
    lines=["# WF3 Score Threshold × Sizing Grid","",
           "All fundamentals, R/R, entry-zone, liquidity, position-cap and exit rules are fixed. Only Core score floor and minimum target allocation vary.","",
           "| Score floor | Min alloc | Return | CAGR | Max DD | Avg cash | Buys | Core obs | R/R>=2 obs | Entry obs | Alpha vs S&P |",
           "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in sorted(results,key=lambda x:(-x["score_floor"],x["min_initial_allocation_pct"])):
        f=r["funnel"]
        lines.append(f"| {r['score_floor']} | {r['min_initial_allocation_pct']:.0f}% | {r['total_return_pct']:+.2f}% | {r['cagr_pct']:+.2f}% | {r['max_drawdown_pct']:.2f}% | {r['average_cash_pct']:.1f}% | {r['buy_count']} | {f['core']} | {f['rr2']} | {f['entry']} | {r['alpha_vs_benchmark_total_pct']:+.2f} pp |")
    lines.append(f"| S&P 500 TR | — | {br['total_return_pct']:+.2f}% | {br['cagr_pct']:+.2f}% | {br['max_drawdown_pct']:.2f}% | — | — | — | — | — | — |")
    lines+=["","## Guardrails",
            "- A higher backtest return alone is not sufficient to deploy a configuration.",
            "- Configurations exceeding 15% max drawdown are flagged as outside the current risk target.",
            "- This is still one historical window; any apparent winner must be validated out-of-sample before production changes."]
    (ROOT/"backtests/results/wf3_score_sizing_grid.md").write_text("\n".join(lines)+"\n")
    print("GRID_RESULT="+json.dumps({"ranked":ranked,"benchmark":br,"hash":out["deterministic_hash"]},separators=(",",":")),flush=True)

if __name__=="__main__":main()
