#!/usr/bin/env python3
from __future__ import annotations
import argparse, copy, hashlib, json, math, sys
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
ALLOCATIONS=(8.0,10.0,12.0,15.0)
POLICIES=("current","qualified_any_zone")
OVERLAYS=(0.0,0.5,1.0)

def core_requalify(a,score_floor):
    """Backtest-only lower Core conviction floor; all other Core gates stay fixed."""
    x=copy.deepcopy(a)
    score=float(x.get("deterministic_score") or 0)
    if score < score_floor:
        return x
    if x.get("lane_qualified") is True:
        return x
    f=x.get("fundamentals") or {}
    t=x.get("technicals") or {}
    breakdown=x.get("breakdown") or {}
    fs=float(breakdown.get("Fundamentals") or 0)
    fconf=str(x.get("fundamental_confidence") or "low").lower()
    promotion=x.get("promotion_risk") or {}
    market_cap=float(f.get("marketCap") or 0)
    avg_dollar=float(t.get("avg_dollar_volume_20") or 0)
    if (
        not promotion.get("hard_reject")
        and fs >= ae.MIN_FUNDAMENTAL_SCORE
        and fconf in {"medium","high"}
        and not x.get("negative_news_override")
        and avg_dollar >= ae.CORE_MIN_AVG_DOLLAR_VOLUME
        and market_cap >= ae.MIN_MARKET_CAP
    ):
        x["lane"]="CORE_QUALITY"
        x["lane_label"]="Core Quality Lane"
        x["lane_qualified"]=True
        x["core_quality_qualified"]=True
        x["category"]="Core"
        x["core_blockers"]=[b for b in (x.get("core_blockers") or []) if "system conviction" not in str(b).lower()]
        x["lane_reasons"]=[r for r in (x.get("lane_reasons") or []) if "system conviction" not in str(r).lower()]
        x["lane_reasons"].append(f"research score floor {score_floor:.0f} passed; all other Core gates passed")
    return x

def make_entry_signal(score_floor,policy):
    def signal(a):
        if a.get("lane_qualified") is not True:
            return None
        if a.get("lane") not in {"CORE_QUALITY","EXPLOSIVE"}:
            return None
        if float(a.get("price") or 0)<5:
            return None
        if bool((a.get("promotion_risk") or {}).get("hard_reject")):
            return None
        if float(a.get("risk_reward") or 0)<2.0:
            return None
        if bool((a.get("thesis_assessment") or {}).get("invalidated")):
            return None
        if a.get("negative_news_override"):
            return None
        if str(a.get("decision_confidence") or "medium").lower()=="low":
            return None
        score=float(a.get("deterministic_score") or 0)
        if score<score_floor:
            return None
        zone=str(a.get("entry_zone_status") or "").upper()
        if policy=="current":
            if zone not in {"PRIMARY_BUY","BETTER_BUY"}:
                return None
        else:
            if zone in {"DO_NOT_CHASE","INVALIDATED"}:
                return None
        if score>=85:return "STRONG BUY"
        if score>=75:return "BUY"
        return "STARTER BUY"
    return signal

def run_variant(st,score_floor,policy,min_alloc,day,analyses,shortlist,market):
    entry_fn=make_entry_signal(score_floor,policy)
    def alloc_fn(rank_score):
        base_pct=ORIG_TARGET(rank_score)
        # Once a stock has passed the complete qualification + entry gate, it
        # receives at least the tested allocation floor. 15% hard cap remains.
        return min(15.0,max(float(min_alloc),float(base_pct or 0)))
    old_entry=pe.entry_attention_signal
    old_target=pe.score_target_allocation_pct
    pe.entry_attention_signal=entry_fn
    pe.score_target_allocation_pct=alloc_fn
    try:
        wf.run_state(st,day,analyses,set(shortlist),market)
    finally:
        pe.entry_attention_signal=old_entry
        pe.score_target_allocation_pct=old_target

def period_metrics(curve,start,end):
    rows=[r for r in curve if start<=date.fromisoformat(r["date"])<=end]
    if not rows:return None
    first=float(rows[0]["equity"]);last=float(rows[-1]["equity"])
    days=max(1,(date.fromisoformat(rows[-1]["date"])-date.fromisoformat(rows[0]["date"])).days)
    years=days/365.25
    ret=last/first-1
    cagr=(last/first)**(1/years)-1 if first>0 and last>0 else -1
    peak=0.0;dd=0.0
    for r in rows:
        e=float(r["equity"]);peak=max(peak,e)
        if peak:dd=min(dd,e/peak-1)
    avg_cash=sum(float(r.get("cash") or 0)/max(1,float(r["equity"])) for r in rows)/len(rows)
    return {"start_value":round(first,2),"end_value":round(last,2),"total_return_pct":round(ret*100,2),
            "cagr_pct":round(cagr*100,2),"max_drawdown_pct":round(dd*100,2),"average_cash_pct":round(avg_cash*100,2)}

def benchmark_daily_returns(benchmark,start,end):
    rows=[r for r in benchmark["rows"] if start<=date.fromisoformat(r["date"])<=end]
    out={}
    prev=None
    for r in rows:
        px=float(r["close"])
        out[r["date"]]=0.0 if prev in (None,0) else px/prev-1
        prev=px
    return out

def overlay_curve(active_curve,benchmark,overlay_fraction):
    """Put a fraction of otherwise-idle cash into the benchmark sleeve.

    Active stock trades remain unchanged. Benchmark-sleeve gains are retained in
    the liquid sleeve but deliberately are not fed back into active position
    sizing, making the overlay comparison conservative.
    """
    if overlay_fraction<=0:
        return [dict(r) for r in active_curve]
    if not active_curve:return []
    start=date.fromisoformat(active_curve[0]["date"]);end=date.fromisoformat(active_curve[-1]["date"])
    brets=benchmark_daily_returns(benchmark,start,end)
    out=[]
    prev_active_cash=None
    liquid=None
    for r in active_curve:
        acash=float(r.get("cash") or 0);aeq=float(r["equity"]);stock_value=aeq-acash
        if liquid is None:
            liquid=acash
        else:
            br=float(brets.get(r["date"],0))
            liquid *= (1 + overlay_fraction*br)
            liquid += acash-float(prev_active_cash)
        eq=stock_value+liquid
        out.append({"date":r["date"],"equity":round(eq,6),"cash":round(liquid,6)})
        prev_active_cash=acash
    return out

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--score-floor",type=float,required=True);ap.add_argument("--output",required=True)
    args=ap.parse_args();score_floor=float(args.score_floor)
    prices=base.load_gz(base.PRICE_PATH);funds=base.load_gz(base.FUND_PATH)
    market=prices["market"];sectors=prices["membership"]["sectors"];etfs=prices["sector_etfs"]
    store=base.PITFundamentals(funds)
    start=base.d(prices["period"]["start"]);end=base.d(prices["period"]["end"])
    trading=[base.d(r["date"]) for r in prices["benchmark"]["rows"] if start<=base.d(r["date"])<=end]
    quick=daily.precompute_quick(market)
    members=set(prices["membership"]["start_members"]);changes=defaultdict(list)
    for x in prices["membership"]["changes"]:changes[base.d(x["date"])].append(x)

    configs=[]
    for policy in POLICIES:
        for alloc in ALLOCATIONS:
            name=f"score{score_floor:.0f}|{policy}|alloc{alloc:.0f}"
            configs.append({"name":name,"policy":policy,"allocation":alloc,"state":wf.State(name,2.0,False)})

    for i,day in enumerate(trading,1):
        for cd in sorted([x for x in changes if x<=day]):
            for x in changes.pop(cd):
                if x.get("removed"):members.discard(x["removed"])
                if x.get("added"):members.add(x["added"])
        dayrows={s:r for s,r in quick.get(day.isoformat(),{}).items() if s in members}
        shortlist=daily.choose(dayrows,160)
        held=set().union(*(set(c["state"].pos) for c in configs))
        raw={}
        for sym in set(shortlist)|held:
            a=base.analyse(sym,day,market,store,sectors,etfs)
            if a:raw[sym]=a

        # Threshold-transformed analyses are common to every policy/allocation in this job.
        analyses={s:core_requalify(a,score_floor) for s,a in raw.items()}
        for cfg in configs:
            run_variant(cfg["state"],score_floor,cfg["policy"],cfg["allocation"],day,analyses,shortlist,market)
            base.validate(cfg["state"],analyses)

        if i%100==0 or i==len(trading):
            print("OPT",score_floor,day,i,"/",len(trading),
                  [(c["policy"],c["allocation"],round(wf.equity(c["state"],market,day)),len(c["state"].pos)) for c in configs],flush=True)

    TRAIN_START=date(2024,1,2);TRAIN_END=date(2025,12,31)
    HOLD_START=date(2026,1,1);HOLD_END=trading[-1]
    benchmark=prices["benchmark"]
    btrain=wf.bench(benchmark,TRAIN_START,TRAIN_END);bhold=wf.bench(benchmark,HOLD_START,HOLD_END);bfull=wf.bench(benchmark,trading[0],trading[-1])
    results=[]
    for cfg in configs:
        st=cfg["state"]
        active=base.daily_curve(st,market,benchmark,trading[0],trading[-1])
        for overlay in OVERLAYS:
            curve=overlay_curve(active,benchmark,overlay)
            train=period_metrics(curve,TRAIN_START,TRAIN_END);hold=period_metrics(curve,HOLD_START,HOLD_END);full=period_metrics(curve,trading[0],trading[-1])
            train["alpha_pct"]=round(train["total_return_pct"]-btrain["total_return_pct"],2)
            hold["alpha_pct"]=round(hold["total_return_pct"]-bhold["total_return_pct"],2)
            full["alpha_pct"]=round(full["total_return_pct"]-bfull["total_return_pct"],2)
            results.append({
                "score_floor":score_floor,"entry_policy":cfg["policy"],"min_allocation_pct":cfg["allocation"],
                "idle_cash_sp500_pct":int(overlay*100),
                "train":train,"holdout":hold,"full":full,
                "trade_count":len(st.trades),"buy_count":sum(1 for t in st.trades if t["side"]=="BUY"),
                "sell_count":sum(1 for t in st.trades if t["side"]=="SELL"),
            })

    out={"version":"wf3-walkforward-opt-v1","score_floor":score_floor,
         "selection_rule":"rank on 2024-2025 only; 2026 is untouched holdout",
         "fixed":{"deep_candidates":160,"min_rr":2.0,"fundamental_floor":ae.MIN_FUNDAMENTAL_SCORE,
                  "profit_harvest":"none","max_position_pct":15,"transaction_cost_bps":wf.COST_BPS,
                  "exit_rule":"thesis/fundamental invalidation only"},
         "benchmark":{"train":btrain,"holdout":bhold,"full":bfull},"results":results}
    core={"score_floor":score_floor,"results":results,"benchmark":out["benchmark"]}
    out["hash"]=hashlib.sha256(json.dumps(core,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    p=Path(args.output);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(out,indent=2))
    print("OPT_RESULT="+json.dumps({"score_floor":score_floor,"hash":out["hash"],
          "top_train":sorted(results,key=lambda x:(x["train"]["max_drawdown_pct"]>=-15,x["train"]["alpha_pct"]),reverse=True)[:5]},separators=(",",":")),flush=True)

if __name__=="__main__":main()
