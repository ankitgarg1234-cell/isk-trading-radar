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
import app.portfolio_engine as pe

ORIGINAL_ENTRY_SIGNAL=pe.entry_attention_signal
INVESTABLE={"STRONG BUY","BUY","STARTER BUY"}

def bearish(a):
    n=a.get("news") or {}
    return n.get("label")=="Bearish" and int(n.get("material_events") or 0)>0

def extension_gate(a):
    if a.get("lane_qualified") is not True:return False
    if a.get("lane") not in {"CORE_QUALITY","EXPLOSIVE"}:return False
    if float(a.get("price") or 0)<5:return False
    if bool((a.get("promotion_risk") or {}).get("hard_reject")):return False
    if float(a.get("risk_reward") or 0)<pe.MIN_ENTRY_RISK_REWARD:return False
    if bool((a.get("thesis_assessment") or {}).get("invalidated")):return False
    if a.get("negative_news_override"):return False
    if str(a.get("decision_confidence") or "medium").lower()=="low":return False
    if bearish(a):return False
    return True

def current(a):
    return ORIGINAL_ENTRY_SIGNAL(a)

def breakout(a):
    x=ORIGINAL_ENTRY_SIGNAL(a)
    if x:return x
    if not extension_gate(a):return None
    if str(a.get("entry_zone_status") or "").upper()!="BREAKOUT":return None
    t=a.get("technicals") or {}
    if float(t.get("relative_volume") or 0)<1.5:return None
    if float(a.get("deterministic_score") or 0)<75:return None
    return "BUY"

def value_corridor(a):
    x=ORIGINAL_ENTRY_SIGNAL(a)
    if x:return x
    if not extension_gate(a):return None
    if str(a.get("entry_zone_status") or "").upper()!="VALUE_CORRIDOR":return None
    score=float(a.get("deterministic_score") or 0)
    if score<68:return None
    t=a.get("technicals") or {};price=float(a.get("price") or 0)
    ema20=float(t.get("ema20") or price or 0);rsi=float(t.get("rsi") or 50);ch20=float(t.get("change20_pct") or 0)
    falling=(price<ema20 and ch20<-2) or rsi<40
    if falling:return None
    return "STARTER BUY"

def breakout_and_value(a):
    x=breakout(a)
    if x:return x
    return value_corridor(a)

def near_breakout(a):
    x=breakout_and_value(a)
    if x:return x
    if not extension_gate(a):return None
    if str(a.get("entry_zone_status") or "").upper()!="APPROACHING_BREAKOUT":return None
    score=float(a.get("deterministic_score") or 0)
    if score<70:return None
    price=float(a.get("price") or 0);lv=a.get("levels") or {};bo=float(lv.get("breakout") or 0)
    if not price or not bo or bo<=price:return None
    distance=(bo-price)/price*100
    if distance>2.0:return None
    t=a.get("technicals") or {};ema20=float(t.get("ema20") or price);rsi=float(t.get("rsi") or 50)
    ch20=float(t.get("change20_pct") or 0)
    if price<=ema20 or ch20<=0 or not (45<=rsi<=75):return None
    return "STARTER BUY"

def zone_free_ceiling(a):
    x=ORIGINAL_ENTRY_SIGNAL(a)
    if x:return x
    if not extension_gate(a):return None
    zone=str(a.get("entry_zone_status") or "").upper()
    if zone in {"DO_NOT_CHASE","INVALIDATED"}:return None
    if float(a.get("deterministic_score") or 0)<68:return None
    return "STARTER BUY"

POLICIES=[
    ("Control — current zones",current),
    ("+ Breakout",breakout),
    ("+ Value corridor",value_corridor),
    ("+ Breakout + value corridor",breakout_and_value),
    ("+ Near-breakout confirmation",near_breakout),
    ("Zone-free diagnostic ceiling",zone_free_ceiling),
]

def run_state_with_policy(st,policy,day,analyses,members,market):
    old=pe.entry_attention_signal
    pe.entry_attention_signal=policy
    try:
        wf.run_state(st,day,analyses,members,market)
    finally:
        pe.entry_attention_signal=old

def main():
    prices=base.load_gz(base.PRICE_PATH);funds=base.load_gz(base.FUND_PATH)
    market=prices["market"];etfs=prices["sector_etfs"];sectors=prices["membership"]["sectors"]
    store=base.PITFundamentals(funds)
    start=base.d(prices["period"]["start"]);end=base.d(prices["period"]["end"])
    trading=[base.d(r["date"]) for r in prices["benchmark"]["rows"] if start<=base.d(r["date"])<=end]
    quick=daily.precompute_quick(market)
    members=set(prices["membership"]["start_members"])
    changes=defaultdict(list)
    for x in prices["membership"]["changes"]:changes[base.d(x["date"])].append(x)

    states=[]
    for name,_ in POLICIES:
        states.append(wf.State(name,2.0,False))

    policy_entry_counts={name:0 for name,_ in POLICIES}
    policy_zone_counts={name:defaultdict(int) for name,_ in POLICIES}
    candidate_stats={"analyses":0,"lane":0,"rr2":0}

    for i,day in enumerate(trading,1):
        for cd in sorted([x for x in changes if x<=day]):
            for x in changes.pop(cd):
                if x.get("removed"):members.discard(x["removed"])
                if x.get("added"):members.add(x["added"])
        dayrows={s:r for s,r in quick.get(day.isoformat(),{}).items() if s in members}
        shortlist=daily.choose(dayrows,80)
        held=set().union(*(set(s.pos) for s in states));analyses={}
        for sym in set(shortlist)|held:
            a=base.analyse(sym,day,market,store,sectors,etfs)
            if not a:continue
            analyses[sym]=a
            if sym in shortlist:
                candidate_stats["analyses"]+=1
                if a.get("lane_qualified") is True:
                    candidate_stats["lane"]+=1
                    if float(a.get("risk_reward") or 0)>=2:candidate_stats["rr2"]+=1

        # Count what each policy would newly consider investable before portfolio/ranking effects.
        for name,policy in POLICIES:
            for sym in shortlist:
                a=analyses.get(sym)
                if not a:continue
                sig=policy(copy.deepcopy(a))
                if sig in INVESTABLE:
                    policy_entry_counts[name]+=1
                    policy_zone_counts[name][str(a.get("entry_zone_status") or "UNKNOWN")]+=1

        for st,(name,policy) in zip(states,POLICIES):
            run_state_with_policy(st,policy,day,analyses,set(shortlist),market)
            base.validate(st,analyses)

        if i%75==0 or i==len(trading):
            print("ABLATION",day,i,"/",len(trading),[(s.name,round(wf.equity(s,market,day)),len(s.trades)) for s in states],flush=True)

    benchmark=prices["benchmark"];br=wf.bench(benchmark,trading[0],trading[-1]);results=[];trades={}
    for st in states:
        curve=base.daily_curve(st,market,benchmark,trading[0],trading[-1])
        r=base.stat(st.name,st,curve)
        r["alpha_vs_benchmark_total_pct"]=round(r["total_return_pct"]-br["total_return_pct"],2)
        r["entry_opportunities"]=policy_entry_counts[st.name]
        r["entry_zones"]=dict(policy_zone_counts[st.name])
        r["buy_count"]=sum(1 for t in st.trades if t["side"]=="BUY")
        r["sell_count"]=sum(1 for t in st.trades if t["side"]=="SELL")
        results.append(r);trades[st.name]=st.trades

    out={"version":"wf3-entry-ablation-v1","period":{"start":trading[0].isoformat(),"end":trading[-1].isoformat()},
         "fixed_rules":{"risk_reward_min":2.0,"lane_gates":"unchanged","score_floor":"unchanged except zone-free diagnostic uses existing 68 floor",
                        "position_cap_pct":15,"whole_shares":True,"transaction_cost_bps":wf.COST_BPS,
                        "exit_rule":"thesis/fundamental invalidation only; lane loss alone does not sell"},
         "candidate_stats":candidate_stats,"results":results,"benchmark":br,"trades":trades}
    core={"period":out["period"],"results":results,"benchmark":br,"trades":trades}
    out["deterministic_hash"]=hashlib.sha256(json.dumps(core,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    p=ROOT/"backtests/results/wf3_entry_ablation.json";p.write_text(json.dumps(out,indent=2))
    md=["# WF3 Entry-Timing Ablation","",
        "All variants keep the same PIT data, lane qualification, R/R >=2x, score gates, sizing, costs and thesis-gated exit rule.","",
        "| Variant | End value | Return | CAGR | Max DD | Buys | Sells | Entry opportunities | Alpha vs S&P |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in results:
        md.append(f"| {r['name']} | USD {r['end_value']:,.0f} | {r['total_return_pct']:+.1f}% | {r['cagr_pct']:+.1f}% | {r['max_drawdown_pct']:.1f}% | {r['buy_count']} | {r['sell_count']} | {r['entry_opportunities']} | {r['alpha_vs_benchmark_total_pct']:+.1f} pp |")
    md.append(f"| S&P 500 Total Return | USD {br['end_value']:,.0f} | {br['total_return_pct']:+.1f}% | {br['cagr_pct']:+.1f}% | {br['max_drawdown_pct']:.1f}% | — | — | — | — |")
    md+=["","## Interpretation guide",
         "- Control is the current PRIMARY_BUY / BETTER_BUY entry policy.",
         "- + Breakout adds only the existing production BREAKOUT rule: relative volume >=1.5x and deterministic score >=75.",
         "- + Value corridor adds a starter entry only at score >=68 and only when the falling-risk test is false.",
         "- + Near-breakout adds a starter only within 2% of breakout, score >=70, above EMA20, positive 20-day momentum, RSI 45-75.",
         "- Zone-free diagnostic ceiling is not a proposed strategy. It shows the maximum participation effect of removing entry-zone timing while retaining qualification/RR/score safety gates.",
         "- Historical analyst consensus, broad news and strategic-capital archives remain unavailable and are not backfilled."]
    (ROOT/"backtests/results/wf3_entry_ablation.md").write_text("\n".join(md)+"\n")
    print("ABLATION_RESULT="+json.dumps({"results":results,"benchmark":br,"candidate_stats":candidate_stats,"hash":out["deterministic_hash"]},separators=(",",":")),flush=True)

if __name__=="__main__":main()
