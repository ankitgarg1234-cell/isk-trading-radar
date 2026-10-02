#!/usr/bin/env python3
from __future__ import annotations
import copy, hashlib, json, math, sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"));sys.path.insert(0,str(ROOT))

import walkforward_backtest as wf
import wf3_offline_valuein as base
import wf3_offline_valuein_daily as daily
import app.analysis_engine as ae
import app.portfolio_engine as pe

ORIG_BUY_LEVELS=ae.buy_levels
ORIG_TARGET_ALLOC=pe.score_target_allocation_pct
MIN_ALLOC=12.0

def _atr(t,price):
    return max(float(t.get("atr") or price*.03),price*.005) if price else 1.0

def _support(t,price,nearest=False):
    e50=float(t.get("ema50") or price)
    low20=float(t.get("low20") or e50)
    if not nearest:
        return min(low20,e50)
    below=[x for x in (low20,e50) if x<price]
    return max(below) if below else min(low20,e50)

def policy_levels(name,t,price):
    lv=ORIG_BUY_LEVELS(t,price)
    if name=="current":
        return lv
    a=_atr(t,price)
    if name=="lower_support_050":
        stop=_support(t,price,False)-.50*a
    elif name=="nearest_support_075":
        stop=_support(t,price,True)-.75*a
    elif name=="nearest_support_050":
        stop=_support(t,price,True)-.50*a
    elif name=="atr_2x":
        stop=price-2.0*a
    else:
        raise ValueError(name)
    # R/R requires a genuine downside level below the decision price.
    stop=max(.01,min(stop,price-.25*a))
    lv=dict(lv);lv["stop"]=round(stop,2)
    return lv

POLICIES=[
    ("Current: lower support -0.75 ATR","current"),
    ("Lower support -0.50 ATR","lower_support_050"),
    ("Nearest support -0.75 ATR","nearest_support_075"),
    ("Nearest support -0.50 ATR","nearest_support_050"),
    ("Pure 2.0 ATR risk","atr_2x"),
]

def build_bundle(sym,asof,market,store,sectors,etfs):
    data=market.get(sym);raw=wf.row_before(data or {},asof)
    if not raw or not raw.get("close") or float(raw["close"])<5:return None
    h=wf.hist_asof(data,asof,270)
    if len(h)<100:return None
    price=float(raw["close"]);fund=store.asof(sym,asof,price)
    rev=[]
    for x in data.get("splits") or []:
        sd=base.d(x.get("date"))
        if sd and asof-timedelta(days=366)<=sd<=asof and float(x.get("numerator") or 0)<float(x.get("denominator") or 0):
            rev.append({"date":x["date"],"ratio":x.get("ratio")})
    return {
        "symbol":sym,"price":price,"previous_close":h[-2]["close"] if len(h)>1 else price,
        "history":h,"fundamentals":fund,"news":store.filing_news(sym,asof),
        "recent_reverse_splits":rev,"strategic_capital":{"events":[]},
        "sector_benchmark":base.sector_bundle(sectors.get(sym),etfs,asof),
    }

def analyse_variant(bundle,key):
    old=ae.buy_levels
    ae.buy_levels=lambda t,p:policy_levels(key,t,p)
    try:
        out=ae.score_bundle(bundle)
    finally:
        ae.buy_levels=old
    out["symbol"]=bundle["symbol"];out["price"]=bundle["price"]
    return out

def target_alloc(score):
    x=ORIG_TARGET_ALLOC(score)
    if x<=0:return 0.0
    return min(15.0,max(MIN_ALLOC,x))

def run_state(st,day,analyses,shortlist,market):
    old=pe.score_target_allocation_pct
    pe.score_target_allocation_pct=target_alloc
    try:
        wf.run_state(st,day,analyses,set(shortlist),market)
    finally:
        pe.score_target_allocation_pct=old
    base.validate(st,analyses)

def future_rows(data,day,limit):
    rs=data.get("rows") or []
    out=[r for r in rs if str(r.get("date") or "")>day.isoformat()]
    return out[:limit]

def outcome(a,day,market):
    price=float(a.get("price") or 0);lv=a.get("levels") or {}
    stop=float(lv.get("stop") or 0);target=float(lv.get("target") or 0)
    if not price or not stop or not target or not stop<price<target:return None
    horizon=20 if a.get("lane")=="EXPLOSIVE" else 60
    rs=future_rows(market.get(a["symbol"]) or {},day,horizon)
    if not rs:return None
    for i,r in enumerate(rs,1):
        lo=float(r.get("low") or r.get("close") or 0);hi=float(r.get("high") or r.get("close") or 0)
        sh=lo<=stop;th=hi>=target
        if sh and th:return {"result":"ambiguous_same_day","sessions":i}
        if sh:return {"result":"stop_first","sessions":i}
        if th:return {"result":"target_first","sessions":i}
    last=float(rs[-1].get("close") or price)
    risk=price-stop
    return {"result":"neither","sessions":len(rs),"horizon_r":(last-price)/risk if risk>0 else None}

def main():
    prices=base.load_gz(base.PRICE_PATH);funds=base.load_gz(base.FUND_PATH)
    market=prices["market"];sectors=prices["membership"]["sectors"];etfs=prices["sector_etfs"]
    store=base.PITFundamentals(funds)
    start=base.d(prices["period"]["start"]);end=base.d(prices["period"]["end"])
    trading=[base.d(r["date"]) for r in prices["benchmark"]["rows"] if start<=base.d(r["date"])<=end][::5]
    quick=daily.precompute_quick(market)
    members=set(prices["membership"]["start_members"]);changes=defaultdict(list)
    for x in prices["membership"]["changes"]:changes[base.d(x["date"])].append(x)

    states={name:wf.State(name,2.0,False) for name,_ in POLICIES}
    diag={name:{"analyses":0,"lane":0,"rr2":0,"entry_opportunities":0,"core_rr2":0,"explosive_rr2":0} for name,_ in POLICIES}
    outs={name:defaultdict(int) for name,_ in POLICIES}
    out_r={name:[] for name,_ in POLICIES}
    last_sample={name:{} for name,_ in POLICIES}

    for i,day in enumerate(trading,1):
        for cd in sorted([x for x in changes if x<=day]):
            for x in changes.pop(cd):
                if x.get("removed"):members.discard(x["removed"])
                if x.get("added"):members.add(x["added"])
        dayrows={s:r for s,r in quick.get(day.isoformat(),{}).items() if s in members}
        shortlist=daily.choose(dayrows,80)
        held=set().union(*(set(st.pos) for st in states.values()))
        symbols=set(shortlist)|held
        bundles={}
        for sym in symbols:
            b=build_bundle(sym,day,market,store,sectors,etfs)
            if b:bundles[sym]=b

        all_analyses={}
        for name,key in POLICIES:
            analyses={}
            for sym,b in bundles.items():
                try:a=analyse_variant(copy.deepcopy(b),key)
                except Exception:continue
                analyses[sym]=a
                if sym in shortlist:
                    d=diag[name];d["analyses"]+=1
                    if a.get("lane_qualified") is True:d["lane"]+=1
                    rr=float(a.get("risk_reward") or 0)
                    if a.get("lane_qualified") is True and rr>=2:
                        d["rr2"]+=1
                        if a.get("lane")=="CORE_QUALITY":d["core_rr2"]+=1
                        if a.get("lane")=="EXPLOSIVE":d["explosive_rr2"]+=1
                    sig=pe.entry_attention_signal(a)
                    if sig in pe.INVESTABLE_ENTRY_ACTIONS:
                        d["entry_opportunities"]+=1
                        # Avoid counting a repeated daily observation of the same symbol
                        # as an independent outcome sample.
                        prev=last_sample[name].get(sym)
                        if prev is None or (day-prev).days>=28:
                            o=outcome(a,day,market)
                            if o:
                                outs[name][o["result"]]+=1
                                if o.get("horizon_r") is not None:out_r[name].append(float(o["horizon_r"]))
                                last_sample[name][sym]=day
            all_analyses[name]=analyses

        for name,_ in POLICIES:
            run_state(states[name],day,all_analyses[name],shortlist,market)

        if i%75==0 or i==len(trading):
            print("STOP_ABLATION",day,i,"/",len(trading),[(n,round(wf.equity(states[n],market,day)),len(states[n].trades)) for n,_ in POLICIES],flush=True)

    br=wf.bench(prices["benchmark"],trading[0],trading[-1])
    results=[]
    for name,_ in POLICIES:
        st=states[name]
        curve=base.daily_curve(st,market,prices["benchmark"],trading[0],trading[-1])
        r=base.stat(name,st,curve)
        cash_pcts=[float(x.get("cash") or 0)/float(x.get("equity") or 1)*100 for x in st.curve if float(x.get("equity") or 0)>0]
        r["average_cash_pct"]=round(sum(cash_pcts)/len(cash_pcts),2) if cash_pcts else None
        r["alpha_vs_benchmark_total_pct"]=round(r["total_return_pct"]-br["total_return_pct"],2)
        r["buy_count"]=sum(1 for t in st.trades if t["side"]=="BUY")
        r["sell_count"]=sum(1 for t in st.trades if t["side"]=="SELL")
        r["diagnostic"]=diag[name]
        oc=dict(outs[name]);total=sum(oc.values())
        r["outcome_samples"]=total
        r["target_first_pct"]=round(oc.get("target_first",0)/total*100,2) if total else None
        r["stop_first_pct"]=round(oc.get("stop_first",0)/total*100,2) if total else None
        r["neither_pct"]=round(oc.get("neither",0)/total*100,2) if total else None
        r["ambiguous_pct"]=round(oc.get("ambiguous_same_day",0)/total*100,2) if total else None
        vals=sorted(out_r[name])
        r["median_horizon_r_when_neither"]=round(vals[len(vals)//2],3) if vals else None
        results.append(r)

    out={
        "version":"wf3-stop-rr-ablation-fast-v1",
        "period":{"start":trading[0].isoformat(),"end":trading[-1].isoformat()},
        "fixed_rules":{"deep_candidates_sampled":80,"min_initial_allocation_pct":12,"min_rr":2.0,
                       "target_formula":"max(52-week closing high, price + 3 ATR) unchanged",
                       "entry_rules":"unchanged","lane_rules":"unchanged","whole_shares":True,
                       "position_cap_pct":15,"transaction_cost_bps":wf.COST_BPS,
                       "stop_is_selection_risk_level_not_forced_exit":"true"},
        "results":results,"benchmark":br,
    }
    core={"period":out["period"],"results":results,"benchmark":br}
    out["deterministic_hash"]=hashlib.sha256(json.dumps(core,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    p=ROOT/"backtests/results/wf3_stop_rr_ablation_fast.json";p.write_text(json.dumps(out,indent=2))
    md=["# WF3 Fast Stop / R-R Formula Ablation","",
        "Fast weekly-sampled directional test. Only the modeled stop formula changes; all other rules are unchanged.","",
        "| Stop policy | Return | CAGR | Max DD | Avg cash | Buys | Lane obs | R/R>=2 obs | Entries | Target-first | Stop-first | Samples |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in results:
        d=r["diagnostic"]
        md.append(f"| {r['name']} | {r['total_return_pct']:+.2f}% | {r['cagr_pct']:+.2f}% | {r['max_drawdown_pct']:.2f}% | {r['average_cash_pct']:.1f}% | {r['buy_count']} | {d['lane']} | {d['rr2']} | {d['entry_opportunities']} | {r['target_first_pct'] if r['target_first_pct'] is not None else '—'}% | {r['stop_first_pct'] if r['stop_first_pct'] is not None else '—'}% | {r['outcome_samples']} |")
    md.append(f"| S&P 500 TR | {br['total_return_pct']:+.2f}% | {br['cagr_pct']:+.2f}% | {br['max_drawdown_pct']:.2f}% | — | — | — | — | — | — | — | — |")
    md+=["","## Interpretation",
         "- Current uses the live production rule: min(20-day lowest close, EMA50) - 0.75 ATR.",
         "- 'Nearest support' uses the higher valid support below price, then the ATR buffer.",
         "- The stop level continues to define modeled downside/R-R only; this experiment does not turn it into a mechanical stop-loss exit.",
         "- Outcome samples use a 28-calendar-day de-duplication per symbol. Explosive outcomes look 20 sessions ahead; Core outcomes 60 sessions.",
         "- Same-day stop+target hits are labeled ambiguous because daily bars cannot identify intraday ordering.",
         "- This is a historical S&P 500 proxy with filing-date-gated PIT fundamentals; it is a comparative model test, not a guarantee."]
    (ROOT/"backtests/results/wf3_stop_rr_ablation_fast.md").write_text("\n".join(md)+"\n")
    print("\n".join(md),flush=True)
    print("STOP_RR_RESULT="+json.dumps({"results":results,"benchmark":br,"hash":out["deterministic_hash"]},separators=(",",":")),flush=True)

if __name__=="__main__":main()
