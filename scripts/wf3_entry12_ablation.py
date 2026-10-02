#!/usr/bin/env python3
from __future__ import annotations
import copy,hashlib,json,sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"));sys.path.insert(0,str(ROOT))

import walkforward_backtest as wf
import wf3_offline_valuein as base
import wf3_offline_valuein_daily as daily
import app.portfolio_engine as pe

ORIG_ENTRY=pe.entry_attention_signal
ORIG_TARGET=pe.score_target_allocation_pct
MIN_ALLOC=12.0

def gate(a):
    if a.get("lane_qualified") is not True:return False
    if a.get("lane") not in {"CORE_QUALITY","EXPLOSIVE"}:return False
    if float(a.get("price") or 0)<5:return False
    if bool((a.get("promotion_risk") or {}).get("hard_reject")):return False
    if float(a.get("risk_reward") or 0)<2:return False
    if bool((a.get("thesis_assessment") or {}).get("invalidated")):return False
    if a.get("negative_news_override"):return False
    if str(a.get("decision_confidence") or "medium").lower()=="low":return False
    return True

def current(a):
    return ORIG_ENTRY(a)

def breakout(a):
    x=ORIG_ENTRY(a)
    if x:return x
    if not gate(a):return None
    if str(a.get("entry_zone_status") or "").upper()!="BREAKOUT":return None
    t=a.get("technicals") or {}
    if float(t.get("relative_volume") or 0)<1.5:return None
    if float(a.get("deterministic_score") or 0)<75:return None
    return "BUY"

def value(a):
    x=ORIG_ENTRY(a)
    if x:return x
    if not gate(a):return None
    if str(a.get("entry_zone_status") or "").upper()!="VALUE_CORRIDOR":return None
    if float(a.get("deterministic_score") or 0)<68:return None
    t=a.get("technicals") or {};price=float(a.get("price") or 0)
    ema20=float(t.get("ema20") or price);rsi=float(t.get("rsi") or 50);ch20=float(t.get("change20_pct") or 0)
    if (price<ema20 and ch20<-2) or rsi<40:return None
    return "STARTER BUY"

def breakout_value(a):
    return breakout(a) or value(a)

def near_breakout(a):
    x=breakout_value(a)
    if x:return x
    if not gate(a):return None
    if str(a.get("entry_zone_status") or "").upper()!="APPROACHING_BREAKOUT":return None
    if float(a.get("deterministic_score") or 0)<70:return None
    price=float(a.get("price") or 0);bo=float((a.get("levels") or {}).get("breakout") or 0)
    if not price or not bo or bo<=price:return None
    if (bo-price)/price*100>2:return None
    t=a.get("technicals") or {};ema20=float(t.get("ema20") or price);rsi=float(t.get("rsi") or 50);ch20=float(t.get("change20_pct") or 0)
    if price<=ema20 or ch20<=0 or not 45<=rsi<=75:return None
    return "STARTER BUY"

def trend_continuation(a):
    x=breakout_value(a)
    if x:return x
    if not gate(a):return None
    if float(a.get("deterministic_score") or 0)<68:return None
    zone=str(a.get("entry_zone_status") or "").upper()
    if zone in {"DO_NOT_CHASE","INVALIDATED","DEEP_VALUE"}:return None
    t=a.get("technicals") or {};price=float(a.get("price") or 0)
    ema20=float(t.get("ema20") or price);ema50=float(t.get("ema50") or ema20);rsi=float(t.get("rsi") or 50)
    ch20=float(t.get("change20_pct") or 0);near=float(t.get("near_20d_high") or 0);rv=float(t.get("relative_volume") or 0)
    if not (price>=ema20>=ema50):return None
    if ch20<=0 or not 45<=rsi<=72:return None
    if near<0.90:return None
    if rv<0.8:return None
    return "STARTER BUY"

def zone_free(a):
    x=ORIG_ENTRY(a)
    if x:return x
    if not gate(a):return None
    if float(a.get("deterministic_score") or 0)<68:return None
    if str(a.get("entry_zone_status") or "").upper() in {"DO_NOT_CHASE","INVALIDATED"}:return None
    return "STARTER BUY"

POLICIES=[
 ("Current zones",current),
 ("+ Breakout",breakout),
 ("+ Value corridor",value),
 ("+ Breakout + value",breakout_value),
 ("+ Near-breakout",near_breakout),
 ("+ Trend continuation",trend_continuation),
 ("Zone-free diagnostic",zone_free),
]

def target(score):
    base_pct=ORIG_TARGET(score)
    if base_pct<=0:return 0.0
    return min(15.0,max(MIN_ALLOC,base_pct))

def run_variant(st,policy,day,analyses,shortlist,market):
    old_entry=pe.entry_attention_signal;old_target=pe.score_target_allocation_pct
    pe.entry_attention_signal=policy;pe.score_target_allocation_pct=target
    try:
        wf.run_state(st,day,analyses,set(shortlist),market)
    finally:
        pe.entry_attention_signal=old_entry;pe.score_target_allocation_pct=old_target
    base.validate(st,analyses)

def main():
    prices=base.load_gz(base.PRICE_PATH);funds=base.load_gz(base.FUND_PATH)
    market=prices["market"];sectors=prices["membership"]["sectors"];etfs=prices["sector_etfs"]
    store=base.PITFundamentals(funds)
    start=base.d(prices["period"]["start"]);end=base.d(prices["period"]["end"])
    trading=[base.d(r["date"]) for r in prices["benchmark"]["rows"] if start<=base.d(r["date"])<=end]
    quick=daily.precompute_quick(market)
    members=set(prices["membership"]["start_members"]);changes=defaultdict(list)
    for x in prices["membership"]["changes"]:changes[base.d(x["date"])].append(x)
    states=[wf.State(name,2.0,False) for name,_ in POLICIES]
    opp={name:0 for name,_ in POLICIES}

    for i,day in enumerate(trading,1):
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
        for name,policy in POLICIES:
            for sym in shortlist:
                a=analyses.get(sym)
                if a and policy(a) in pe.INVESTABLE_ENTRY_ACTIONS:opp[name]+=1
        for st,(name,policy) in zip(states,POLICIES):
            run_variant(st,policy,day,analyses,shortlist,market)
        if i%75==0 or i==len(trading):
            print("ENTRY12",day,i,"/",len(trading),[(st.name,round(wf.equity(st,market,day)),len(st.pos),round(st.cash)) for st in states],flush=True)

    br=wf.bench(prices["benchmark"],trading[0],trading[-1]);results=[];trades={}
    for st in states:
        curve=base.daily_curve(st,market,prices["benchmark"],trading[0],trading[-1])
        r=base.stat(st.name,st,curve)
        r["alpha_vs_benchmark_total_pct"]=round(r["total_return_pct"]-br["total_return_pct"],2)
        cash_pcts=[float(x.get("cash") or 0)/float(x.get("equity") or 1)*100 for x in st.curve if float(x.get("equity") or 0)>0]
        r["average_cash_pct"]=round(sum(cash_pcts)/len(cash_pcts),2) if cash_pcts else None
        r["entry_opportunities"]=opp[st.name]
        r["buy_count"]=sum(1 for t in st.trades if t["side"]=="BUY")
        r["sell_count"]=sum(1 for t in st.trades if t["side"]=="SELL")
        r["meets_15pct_dd_target"]=r["max_drawdown_pct"]>=-15
        results.append(r);trades[st.name]=st.trades
    ranked=sorted(results,key=lambda x:x["total_return_pct"],reverse=True)
    out={"version":"wf3-entry12-splitfixed-v1","period":{"start":trading[0].isoformat(),"end":trading[-1].isoformat()},
         "fixed_rules":{"deep_candidates_daily":160,"min_initial_allocation_pct":12,"min_rr":2,
                        "lane_rules":"unchanged","score_floor":68,"position_cap_pct":15,"whole_shares":True,
                        "transaction_cost_bps":wf.COST_BPS,"split_accounting":"corrected"},
         "results":results,"ranked_by_return":ranked,"benchmark":br,"trades":trades}
    core={"period":out["period"],"results":results,"benchmark":br,"trades":trades}
    out["deterministic_hash"]=hashlib.sha256(json.dumps(core,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    p=ROOT/"backtests/results/wf3_entry12_ablation.json";p.write_text(json.dumps(out,indent=2))
    lines=["# WF3 Corrected Entry-Timing Ablation at 12% Initial Allocation","",
           "| Entry policy | Return | CAGR | Max DD | Avg cash | Buys | Opportunities | Alpha vs S&P |",
           "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in results:
        lines.append(f"| {r['name']} | {r['total_return_pct']:+.2f}% | {r['cagr_pct']:+.2f}% | {r['max_drawdown_pct']:.2f}% | {r['average_cash_pct']:.1f}% | {r['buy_count']} | {r['entry_opportunities']} | {r['alpha_vs_benchmark_total_pct']:+.2f} pp |")
    lines.append(f"| S&P 500 TR | {br['total_return_pct']:+.2f}% | {br['cagr_pct']:+.2f}% | {br['max_drawdown_pct']:.2f}% | — | — | — | — |")
    (ROOT/"backtests/results/wf3_entry12_ablation.md").write_text("\n".join(lines)+"\n")
    print("ENTRY12_RESULT="+json.dumps({"ranked":ranked,"benchmark":br,"hash":out["deterministic_hash"]},separators=(",",":")),flush=True)

if __name__=="__main__":main()
