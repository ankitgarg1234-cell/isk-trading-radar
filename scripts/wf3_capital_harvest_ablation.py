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

ORIG_TARGET=pe.score_target_allocation_pct
ORIG_SIZER=wf.suggested_position_size

VARIANTS=[
    {"name":"Control — current sizing","min_alloc":0.0,"harvest":False},
    {"name":"5% minimum initial","min_alloc":5.0,"harvest":False},
    {"name":"8% minimum initial","min_alloc":8.0,"harvest":False},
    {"name":"10% minimum initial","min_alloc":10.0,"harvest":False},
    {"name":"12% minimum initial","min_alloc":12.0,"harvest":False},
    {"name":"15% minimum initial","min_alloc":15.0,"harvest":False},
    {"name":"5% minimum + harvest","min_alloc":5.0,"harvest":True},
    {"name":"8% minimum + harvest","min_alloc":8.0,"harvest":True},
    {"name":"10% minimum + harvest","min_alloc":10.0,"harvest":True},
]

def ensure_meta(st):
    if not hasattr(st,"_harvest"):
        st._harvest={}

def position_meta(st,sym):
    ensure_meta(st)
    p=st.pos.get(sym)
    if not p:return None
    m=st._harvest.get(sym)
    if not m:
        m={"original_shares":float(p.shares),"tier25":False,"tier50":False,
           "trail_armed":False,"peak":float(p.avg),"last_seen_shares":float(p.shares)}
        st._harvest[sym]=m
    # Adds enlarge the reference position; profit tiers apply to the enlarged holding.
    if float(p.shares)>float(m.get("last_seen_shares") or 0):
        delta=float(p.shares)-float(m.get("last_seen_shares") or 0)
        m["original_shares"]+=delta
    m["last_seen_shares"]=float(p.shares)
    return m

def execute_harvest(st,day,market):
    ensure_meta(st)
    pending=[]
    for sym,p in list(st.pos.items()):
        m=position_meta(st,sym)
        rr=wf.row_before(market.get(sym) or {},day)
        if not rr or not rr.get("close") or p.avg<=0:continue
        px=float(rr["close"]);gain=(px/p.avg-1)*100
        m["peak"]=max(float(m.get("peak") or px),px)
        if gain>=30:m["trail_armed"]=True

        # Tier quantities are based on original position size, but whole-share
        # execution never sells more than currently held.
        if gain>=25 and not m["tier25"]:
            q=max(1,math.ceil(float(m["original_shares"])*0.25))
            pending.append((sym,q,"HARVEST +25%"))
            m["tier25"]=True
        if gain>=50 and not m["tier50"]:
            q=max(1,math.ceil(float(m["original_shares"])*0.25))
            pending.append((sym,q,"HARVEST +50%"))
            m["tier50"]=True

        # Protect the remaining runner only after +30% has been achieved.
        peak=float(m.get("peak") or px)
        if m.get("trail_armed") and peak>0 and px<=peak*0.85:
            # Avoid duplicate full-exit if a tier sell is already queued today.
            pending.append((sym,float(p.shares),"15% PEAK TRAIL"))
            m["trail_armed"]=False

    # Aggregate same-day sells per symbol and execute at next session open.
    grouped=defaultdict(lambda:{"qty":0.0,"reasons":[]})
    for sym,q,reason in pending:
        grouped[sym]["qty"]+=float(q);grouped[sym]["reasons"].append(reason)
    for sym,g in grouped.items():
        p=st.pos.get(sym)
        if not p:continue
        nr=wf.next_row(market.get(sym) or {},day)
        if not nr or not nr.get("open"):continue
        qty=min(float(p.shares),float(g["qty"]))
        if qty<=0:continue
        wf.do_sell(st,sym,qty,float(nr["open"]),date.fromisoformat(nr["date"])," + ".join(g["reasons"]))
        if sym in st.pos:
            st._harvest[sym]["last_seen_shares"]=float(st.pos[sym].shares)
        else:
            st._harvest.pop(sym,None)

def run_with_variant(st,variant,day,analyses,shortlist,market):
    old_target=pe.score_target_allocation_pct
    floor=float(variant["min_alloc"])
    def target(score):
        base_pct=ORIG_TARGET(score)
        if base_pct<=0:return 0.0
        return min(15.0,max(base_pct,floor))
    pe.score_target_allocation_pct=target
    try:
        if variant["harvest"]:
            execute_harvest(st,day,market)
        wf.run_state(st,day,analyses,set(shortlist),market)
    finally:
        pe.score_target_allocation_pct=old_target

def corrected_daily_curve(st,market,benchmark,start,end):
    # base.daily_curve has already been corrected to treat Yahoo OHLC as
    # split-adjusted; dividends remain credited.
    return base.daily_curve(st,market,benchmark,start,end)

def attribution(st,market,end_day):
    out=[]
    for t in st.trades:
        if t.get("side")!="BUY":continue
        sym=t["symbol"];entry_day=date.fromisoformat(t["date"]);entry=float(t["price"]);qty=float(t["shares"])
        post=[]
        for rr in (market.get(sym) or {}).get("rows") or []:
            rd=date.fromisoformat(rr["date"])
            if entry_day<=rd<=end_day and rr.get("close") is not None:
                post.append((rd,float(rr["close"])))
        if not post:continue
        peak_day,peak=max(post,key=lambda x:x[1]);end_close=post[-1][1]
        out.append({"symbol":sym,"entry_date":t["date"],"entry_price":round(entry,4),"shares":qty,
                    "entry_capital":round(entry*qty,2),"end_return_pct":round((end_close/entry-1)*100,2),
                    "max_runup_pct":round((peak/entry-1)*100,2),"peak_date":peak_day.isoformat()})
    return out

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

    states=[wf.State(v["name"],2.0,False) for v in VARIANTS]
    for st in states:ensure_meta(st)

    for i,day in enumerate(trading,1):
        for cd in sorted([x for x in changes if x<=day]):
            for x in changes.pop(cd):
                if x.get("removed"):members.discard(x["removed"])
                if x.get("added"):members.add(x["added"])
        dayrows={s:r for s,r in quick.get(day.isoformat(),{}).items() if s in members}
        shortlist=daily.choose(dayrows,160)
        held=set().union(*(set(st.pos) for st in states))
        analyses={}
        for sym in set(shortlist)|held:
            a=base.analyse(sym,day,market,store,sectors,etfs)
            if a:analyses[sym]=a

        for st,v in zip(states,VARIANTS):
            run_with_variant(st,v,day,analyses,shortlist,market)
            base.validate(st,analyses)

        if i%75==0 or i==len(trading):
            print("CAPITAL",day,i,"/",len(trading),
                  [(st.name,round(wf.equity(st,market,day)),len(st.pos),round(st.cash)) for st in states],flush=True)

    benchmark=prices["benchmark"];br=wf.bench(benchmark,trading[0],trading[-1])
    results=[];trades={};attrs={};curves={}
    for st,v in zip(states,VARIANTS):
        curve=corrected_daily_curve(st,market,benchmark,trading[0],trading[-1]);curves[st.name]=curve
        r=base.stat(st.name,st,curve)
        r["alpha_vs_benchmark_total_pct"]=round(r["total_return_pct"]-br["total_return_pct"],2)
        r["cagr_spread_vs_benchmark_pct"]=round(r["cagr_pct"]-br["cagr_pct"],2)
        r["buy_count"]=sum(1 for t in st.trades if t["side"]=="BUY")
        r["sell_count"]=sum(1 for t in st.trades if t["side"]=="SELL")
        r["harvest_sell_count"]=sum(1 for t in st.trades if t["side"]=="SELL" and ("HARVEST" in str(t.get("reason")) or "TRAIL" in str(t.get("reason"))))
        cash_pcts=[float(x.get("cash") or 0)/float(x.get("equity") or 1)*100 for x in st.curve if float(x.get("equity") or 0)>0]
        r["average_cash_pct"]=round(sum(cash_pcts)/len(cash_pcts),2) if cash_pcts else None
        r["ending_cash_pct"]=round(st.cash/max(1,wf.equity(st,market,trading[-1]))*100,2)
        r["min_initial_allocation_pct"]=v["min_alloc"];r["harvest_overlay"]=v["harvest"]
        results.append(r);trades[st.name]=st.trades;attrs[st.name]=attribution(st,market,trading[-1])

    out={"version":"wf3-capital-harvest-ablation-v1","period":{"start":trading[0].isoformat(),"end":trading[-1].isoformat()},
         "fixed_selection":{"deep_candidates_daily":160,"lane_rules":"unchanged","entry_rules":"unchanged","min_rr":2.0,
                            "score_rules":"unchanged","thesis_exit_rule":"unchanged","split_accounting":"Yahoo OHLC already split-adjusted; no second share multiplication"},
         "harvest_rule":{"tier1":"+25% -> sell 25% of original shares","tier2":"+50% -> sell another 25% of original shares",
                         "runner_trail":"after +30% achieved, full remaining runner exits 15% below subsequent peak",
                         "execution":"next available session open; whole shares"},
         "results":results,"benchmark":br,"trades":trades,"trade_attribution":attrs,"daily_curves":curves}
    core={"period":out["period"],"results":results,"benchmark":br,"trades":trades}
    out["deterministic_hash"]=hashlib.sha256(json.dumps(core,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    p=ROOT/"backtests/results/wf3_capital_harvest_ablation.json";p.write_text(json.dumps(out,indent=2))
    lines=["# WF3 Capital Deployment + Profit Harvesting Ablation","",
           "Stock selection and entry rules are identical across variants; only target allocation floor and harvesting differ.","",
           "| Variant | End value | Return | CAGR | Max DD | Avg cash | End cash | Buys | Sells | Alpha vs S&P |",
           "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in results:
        lines.append(f"| {r['name']} | USD {r['end_value']:,.0f} | {r['total_return_pct']:+.2f}% | {r['cagr_pct']:+.2f}% | {r['max_drawdown_pct']:.2f}% | {r['average_cash_pct']:.1f}% | {r['ending_cash_pct']:.1f}% | {r['buy_count']} | {r['sell_count']} | {r['alpha_vs_benchmark_total_pct']:+.2f} pp |")
    lines.append(f"| S&P 500 Total Return | USD {br['end_value']:,.0f} | {br['total_return_pct']:+.2f}% | {br['cagr_pct']:+.2f}% | {br['max_drawdown_pct']:.2f}% | — | — | — | — | — |")
    lines+=["","## Notes","- Corrected split accounting is used throughout.",
            "- Minimum-allocation floors can increase target size but never exceed the existing 15% position cap; stop-risk and cash ceilings remain active.",
            "- Profit harvesting is tested as an overlay only; it is not deployed to production by this experiment.",
            "- Historical analyst/news/strategic-capital archives remain omitted rather than backfilled with present-day data."]
    (ROOT/"backtests/results/wf3_capital_harvest_ablation.md").write_text("\n".join(lines)+"\n")
    print("CAPITAL_RESULT="+json.dumps({"results":results,"benchmark":br,"hash":out["deterministic_hash"]},separators=(",",":")),flush=True)

if __name__=="__main__":main()
