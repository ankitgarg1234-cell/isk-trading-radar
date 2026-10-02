#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"));sys.path.insert(0,str(ROOT))

import walkforward_backtest as wf
import wf3_offline_valuein as base
import wf3_offline_valuein_daily as daily
import app.analysis_engine as ae
import app.portfolio_engine as pe

def stage_add(stage_sets,name,sym):
    stage_sets[name].add(sym)

def pct(n,d):
    return round(n/d*100,3) if d else 0.0

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--coverage",required=True,choices=["80","160","all"])
    ap.add_argument("--output",required=True)
    args=ap.parse_args()

    prices=base.load_gz(base.PRICE_PATH)
    funds=base.load_gz(base.FUND_PATH)
    market=prices["market"]
    sectors=prices["membership"]["sectors"]
    etfs=prices["sector_etfs"]
    store=base.PITFundamentals(funds)

    start=base.d(prices["period"]["start"]);end=base.d(prices["period"]["end"])
    trading=[base.d(r["date"]) for r in prices["benchmark"]["rows"] if start<=base.d(r["date"])<=end]
    quick=daily.precompute_quick(market)

    members=set(prices["membership"]["start_members"])
    changes=defaultdict(list)
    for x in prices["membership"]["changes"]:
        changes[base.d(x["date"])].append(x)

    state=wf.State(f"Current model — deep {args.coverage}",2.0,False)
    stages=Counter()
    stage_sets=defaultdict(set)
    blockers=Counter()
    day_counts=[]
    all_analysis_errors=0

    for i,day in enumerate(trading,1):
        for cd in sorted([x for x in changes if x<=day]):
            for x in changes.pop(cd):
                if x.get("removed"):members.discard(x["removed"])
                if x.get("added"):members.add(x["added"])

        dayrows={s:r for s,r in quick.get(day.isoformat(),{}).items() if s in members}
        if args.coverage=="all":
            shortlist=sorted(s for s in members if s in market)
        else:
            shortlist=daily.choose(dayrows,int(args.coverage))

        held=set(state.pos)
        analyses={}
        candidate_analyzed=0
        fq=score68=lane=rr2=entry=0

        for sym in set(shortlist)|held:
            try:
                a=base.analyse(sym,day,market,store,sectors,etfs)
            except Exception:
                all_analysis_errors+=1
                continue
            if not a:continue
            analyses[sym]=a
            if sym not in shortlist:continue

            candidate_analyzed+=1
            stages["deep_analyzed"]+=1
            stage_add(stage_sets,"deep_analyzed",sym)

            breakdown=a.get("breakdown") or {}
            fs=float(breakdown.get("Fundamentals") or 0)
            fconf=str(a.get("fundamental_confidence") or "low").lower()
            fundamental_pass=fs>=float(ae.MIN_FUNDAMENTAL_SCORE) and fconf in {"medium","high"}
            if fundamental_pass:
                fq+=1;stages["fundamental_quality_pass"]+=1;stage_add(stage_sets,"fundamental_quality_pass",sym)

            score=float(a.get("deterministic_score") or 0)
            if fundamental_pass and score>=68:
                score68+=1;stages["score68_after_fundamentals"]+=1;stage_add(stage_sets,"score68_after_fundamentals",sym)

            if a.get("lane_qualified") is True:
                lane+=1;stages["lane_qualified"]+=1;stage_add(stage_sets,"lane_qualified",sym)

            if a.get("lane_qualified") is True and float(a.get("risk_reward") or 0)>=2:
                rr2+=1;stages["lane_rr2"]+=1;stage_add(stage_sets,"lane_rr2",sym)
                if pe.entry_attention_signal(a) in pe.INVESTABLE_ENTRY_ACTIONS:
                    entry+=1;stages["investable_entry"]+=1;stage_add(stage_sets,"investable_entry",sym)

            if a.get("lane_qualified") is not True:
                for b in a.get("core_blockers") or []:
                    blockers[str(b)]+=1

        wf.run_state(state,day,analyses,set(shortlist),market)
        base.validate(state,analyses)

        day_counts.append({
            "date":day.isoformat(),"selected_for_deep":len(shortlist),"deep_analyzed":candidate_analyzed,
            "fundamental_quality_pass":fq,"score68_after_fundamentals":score68,
            "lane_qualified":lane,"lane_rr2":rr2,"investable_entry":entry,
            "positions":len(state.pos),"cash":round(state.cash,2)
        })
        if i%75==0 or i==len(trading):
            print("COVERAGE",args.coverage,day,i,"/",len(trading),
                  "equity",round(wf.equity(state,market,day)),
                  "positions",len(state.pos),
                  "funnel",fq,score68,lane,rr2,entry,flush=True)

    benchmark=prices["benchmark"]
    curve=base.daily_curve(state,market,benchmark,trading[0],trading[-1])
    result=base.stat(state.name,state,curve)
    br=wf.bench(benchmark,trading[0],trading[-1])
    result["alpha_vs_benchmark_total_pct"]=round(result["total_return_pct"]-br["total_return_pct"],2)
    result["cagr_spread_vs_benchmark_pct"]=round(result["cagr_pct"]-br["cagr_pct"],2)

    funnel={}
    order=["deep_analyzed","fundamental_quality_pass","score68_after_fundamentals","lane_qualified","lane_rr2","investable_entry"]
    prev=None
    for name in order:
        n=int(stages[name])
        funnel[name]={
            "observations":n,
            "unique_symbols":len(stage_sets[name]),
            "pct_of_deep":pct(n,stages["deep_analyzed"]),
            "pct_of_prior":pct(n,prev) if prev is not None else 100.0,
        }
        prev=n

    # Per-buy attribution: split-adjusted cached prices let us compare each
    # entry to its later peak and end-of-test close without replaying splits.
    attribution=[]
    end_day=trading[-1]
    for t in state.trades:
        if t.get("side")!="BUY":
            continue
        sym=t["symbol"];entry_day=date.fromisoformat(t["date"]);entry=float(t["price"]);qty=float(t["shares"])
        data=market.get(sym) or {};post=[]
        for rr in data.get("rows") or []:
            rd=date.fromisoformat(rr["date"])
            if entry_day<=rd<=end_day and rr.get("close") is not None:
                post.append((rd,float(rr["close"])))
        if not post:
            continue
        end_close=post[-1][1]
        peak_day,peak_close=max(post,key=lambda x:x[1])
        attribution.append({
            "symbol":sym,"entry_date":t["date"],"entry_price":round(entry,4),"shares":qty,
            "entry_capital":round(entry*qty,2),
            "end_close":round(end_close,4),
            "end_return_pct":round((end_close/entry-1)*100,2) if entry else None,
            "peak_close":round(peak_close,4),"peak_date":peak_day.isoformat(),
            "max_runup_pct":round((peak_close/entry-1)*100,2) if entry else None,
            "price_pnl_to_end":round((end_close-entry)*qty,2),
        })

    summary={
        "version":"wf3-coverage-ablation-v2-splitfix",
        "coverage_mode":args.coverage,
        "period":{"start":trading[0].isoformat(),"end":trading[-1].isoformat()},
        "fixed_rules":{
            "fundamental_score_min":float(ae.MIN_FUNDAMENTAL_SCORE),
            "system_score_min":68,
            "min_entry_rr":2.0,
            "lane_rules":"unchanged",
            "entry_rules":"unchanged",
            "whole_shares":True,
            "hard_position_cap_pct":15,
            "transaction_cost_bps":wf.COST_BPS,
            "exit_rule":"thesis/fundamental invalidation only; lane loss alone does not sell",
        },
        "data_coverage":{
            "historical_price_symbols":len(market),
            "pit_fundamental_symbols":int(funds["meta"]["symbols_with_rows"]),
            "pit_usable_fundamental_symbols":int(funds["meta"]["usable_fundamental_symbols"]),
            "pit_usable_pct":float(funds["meta"]["usable_pct"]),
            "analysis_errors":all_analysis_errors,
        },
        "funnel":funnel,
        "top_core_blockers":blockers.most_common(20),
        "average_daily_deep_selected":round(sum(x["selected_for_deep"] for x in day_counts)/len(day_counts),2),
        "average_daily_deep_analyzed":round(sum(x["deep_analyzed"] for x in day_counts)/len(day_counts),2),
        "portfolio_result":result,
        "benchmark":br,
        "trades":state.trades,
        "trade_attribution":attribution,
        "daily_counts":day_counts,
    }
    core={k:summary[k] for k in ["coverage_mode","period","funnel","portfolio_result","benchmark","trades"]}
    summary["deterministic_hash"]=hashlib.sha256(json.dumps(core,sort_keys=True,separators=(",",":")).encode()).hexdigest()

    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(summary,indent=2))
    print("COVERAGE_RESULT="+json.dumps({
        "coverage":args.coverage,"funnel":funnel,"portfolio_result":result,
        "benchmark":br,"top_core_blockers":summary["top_core_blockers"][:8],
        "hash":summary["deterministic_hash"]
    },separators=(",",":")),flush=True)

if __name__=="__main__":
    main()
