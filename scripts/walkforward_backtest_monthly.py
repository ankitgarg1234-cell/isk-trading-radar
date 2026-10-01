#!/usr/bin/env python3
from __future__ import annotations
import importlib.util, json, requests, sys, time
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT=Path(__file__).resolve().parents[1]

def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec)
    sys.modules[name]=mod
    spec.loader.exec_module(mod)
    return mod

wf=load_module("wf_monthly_base",ROOT/"scripts"/"walkforward_backtest.py")
def resilient_jget(session,url,params=None,lim=None):
    """Bound historical-data latency: retry briefly, then skip missing source."""
    err=None
    for i in range(3):
        try:
            if lim:lim.wait()
            r=session.get(url,params=params,timeout=(5,12))
            if r.status_code in (429,500,502,503,504):
                raise RuntimeError(f"HTTP {r.status_code}")
            r.raise_for_status()
            return r.json()
        except Exception as e:
            err=e
            time.sleep(0.5*(i+1))
    raise RuntimeError(str(err))

wf.jget=resilient_jget

fast=load_module("wf_monthly_fast",ROOT/"scripts"/"walkforward_backtest_fast.py")
DEEP_LIMIT=40
START=date(2024,1,1);END=date(2026,10,1)

def main():
    cache=wf.Cache(".backtest_cache")
    s=requests.Session();s.headers["User-Agent"]="Mozilla/5.0 ISK monthly walk-forward"
    current,sectors,changes=wf.sp500_history(s)
    members0=wf.members_at(current,changes,START)
    rel=[x for x in changes if START<=date.fromisoformat(x["date"])<=END]
    union=set(members0)|current
    for x in rel:
        if x["added"]:union.add(x["added"])
        if x["removed"]:union.add(x["removed"])
    print("Universe",len(union),flush=True)

    ps=START-timedelta(days=400);pe_=END+timedelta(days=5);market={}
    def fy(sym):
        z=requests.Session();z.headers["User-Agent"]="Mozilla/5.0 ISK monthly walk-forward"
        return sym,wf.yahoo(z,cache,sym,ps,pe_)
    with ThreadPoolExecutor(max_workers=16) as ex:
        fs=[ex.submit(fy,x) for x in sorted(union)]
        for i,f in enumerate(as_completed(fs),1):
            sym,v=f.result()
            if v:market[sym]=v
            if i%100==0:print("Yahoo",i,"/",len(fs),flush=True)

    etfs={}
    for e in set(wf.ETF.values()):
        v=wf.yahoo(s,cache,e,ps,pe_)
        if v:etfs[e]=v
    benchmark=wf.yahoo(s,cache,"^SP500TR",START-timedelta(days=5),END+timedelta(days=2))
    if not benchmark:benchmark=wf.yahoo(s,cache,"SPY",START-timedelta(days=5),END+timedelta(days=2))
    if not benchmark:raise RuntimeError("benchmark unavailable")
    trading=[date.fromisoformat(r["date"]) for r in benchmark["rows"] if START<=date.fromisoformat(r["date"])<=END]
    months=[];key=None
    for d in trading:
        k=(d.year,d.month)
        if k!=key:months.append(d);key=k
        else:months[-1]=d

    bydate=defaultdict(list)
    for x in rel:bydate[date.fromisoformat(x["date"])].append(x)
    members=set(members0);deep_by_date={};candidate_union=set()
    for d in months:
        for cd in sorted([x for x in list(bydate) if x<=d]):
            for x in bydate.pop(cd):
                if x["removed"]:members.discard(x["removed"])
                if x["added"]:members.add(x["added"])
        chosen=fast.choose_deep({x for x in members if x in market},market,d,DEEP_LIMIT)
        deep_by_date[d]=chosen;candidate_union.update(chosen)
    print("Candidate union",len(candidate_union),flush=True)

    lim=wf.Limiter(7);ss=requests.Session();ss.headers.update({"User-Agent":"ISK Trading Radar research https://github.com/ankitgarg1234-cell/isk-trading-radar","Accept":"application/json","Accept-Encoding":"gzip, deflate"})
    tm=wf.ticker_map(ss,cache,lim);fmap={};fdates={}
    def fetch_fact(sym):
        cik=tm.get(sym)
        if not cik:return sym,None
        z=requests.Session();z.headers.update(ss.headers)
        return sym,wf.facts(z,cache,lim,sym,cik)
    syms=sorted(candidate_union)
    with ThreadPoolExecutor(max_workers=6) as ex:
        fs=[ex.submit(fetch_fact,sym) for sym in syms]
        for i,fut in enumerate(as_completed(fs),1):
            sym,f=fut.result()
            if f:
                fmap[sym]=f
                fdates[sym]=wf.filing_dates(f,START-timedelta(days=400),END)
            if i%25==0:print("SEC",i,"/",len(syms),flush=True)
    usable=set(market)&set(fmap);print("Usable",len(usable),flush=True)

    members=set(members0);bydate=defaultdict(list)
    for x in rel:bydate[date.fromisoformat(x["date"])].append(x)
    states=[wf.State("Current model (R/R >=2x)",2.0,False),wf.State("No 2x R/R floor",0.0,False),wf.State("Core-only (R/R >=2x)",2.0,True)]
    for i,d in enumerate(months,1):
        for cd in sorted([x for x in list(bydate) if x<=d]):
            for x in bydate.pop(cd):
                if x["removed"]:members.discard(x["removed"])
                if x["added"]:members.add(x["added"])
        held=set().union(*(set(x.pos) for x in states))
        deep=set(deep_by_date[d])|held;base={}
        for sym in deep:
            if sym not in fmap:continue
            a=wf.analyse(sym,d,market,fmap,fdates,sectors,etfs)
            if a:base[sym]=a
        investable=set(deep_by_date[d])&set(members)&usable
        for st in states:wf.run_state(st,d,base,investable,market)
        print(d,i,"/",len(months),[(x.name,round(wf.equity(x,market,d))) for x in states],flush=True)

    br=wf.bench(benchmark,START,END);res=[wf.stat(x) for x in states]
    for r in res:
        r["alpha_vs_benchmark_total_pct"]=round(r["total_return_pct"]-br["total_return_pct"],2)
        r["cagr_spread_vs_benchmark_pct"]=round(r["cagr_pct"]-br["cagr_pct"],2)
    rep={"generated_at":wf.datetime.now(wf.timezone.utc).isoformat(),"period":{"start":START.isoformat(),"end":END.isoformat()},"methodology":{"mode":"monthly two-stage sensitivity replay","deep_candidates_per_month":DEEP_LIMIT,"starting_capital":wf.STARTING,"trade_cost_bps":wf.COST_BPS,"whole_shares":True,"hard_position_cap_pct":15},"coverage":{"historical_symbols":len(union),"price_symbols":len(market),"deep_candidate_union":len(candidate_union),"sec_symbols":len(fmap),"usable_deep_symbols":len(usable)},"results":res,"benchmark":br,"curves":{x.name:x.curve for x in states},"trades":{x.name:x.trades for x in states}}
    out=ROOT/"backtests/results/walkforward_2024_2026_monthly.json";out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(rep,indent=2))
    md=wf.md(rep).replace("# 2022-2026 Point-in-Time Walk-Forward Backtest","# 2024-2026 Monthly Two-Stage Sensitivity Backtest")
    md+="\n## Monthly sensitivity methodology\n- Full historical S&P membership is cheap-screened monthly.\n- 40 scanner-style candidates plus existing holdings receive full point-in-time SEC analysis.\n- Monthly cadence is a speed/reliability approximation; the weekly run remains the higher-fidelity comparison.\n"
    (ROOT/"backtests/results/walkforward_2024_2026_monthly.md").write_text(md)
    print(md,flush=True)

if __name__=="__main__":main()
