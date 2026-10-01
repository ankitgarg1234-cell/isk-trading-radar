#!/usr/bin/env python3
from __future__ import annotations
import argparse, importlib.util, json, math, requests, sys, time
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("wf",ROOT/"scripts"/"walkforward_backtest.py")
wf=importlib.util.module_from_spec(spec)
sys.modules["wf"]=wf
spec.loader.exec_module(wf)

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

DEEP_LIMIT=80

def quick_metrics(data,d):
    h=wf.hist_asof(data,d,30)
    if len(h)<21:return None
    px=float(h[-1]["close"] or 0)
    if px<5:return None
    closes=[float(x["close"]) for x in h if x.get("close") is not None]
    vols=[float(x.get("volume") or 0) for x in h]
    if len(closes)<21:return None
    c5=((px/closes[-6])-1)*100 if len(closes)>=6 and closes[-6] else 0
    c20=((px/closes[-21])-1)*100 if closes[-21] else 0
    base=[v for v in vols[-21:-1] if v>0]
    av=sum(base)/len(base) if base else 0
    rv=(vols[-1]/av) if av else 0
    adv=px*av
    hi=max(closes[-20:])
    near=px/hi if hi else 0
    score=min(max(c5,0),20)*2+min(max(c20,0),40)*.7+min(rv,5)*8+(8 if near>=.98 else 0)+(5 if adv>=20_000_000 else 0)
    return {"symbol":None,"price":px,"change_5_pct":c5,"change_20_pct":c20,"relative_volume":rv,"avg_dollar_volume_20":adv,"near_20d_high":near,"scan_score":score}

def choose_deep(members,market,d,limit=DEEP_LIMIT):
    rows=[]
    for s in members:
        data=market.get(s)
        if not data:continue
        q=quick_metrics(data,d)
        if q:q["symbol"]=s;rows.append(q)
    explosive=[
        r for r in rows if r["avg_dollar_volume_20"]>=20_000_000 and (
            r["change_5_pct"]>=3 or r["change_20_pct"]>=7 or r["relative_volume"]>=1.5 or r["near_20d_high"]>=.985
        )
    ]
    explosive.sort(key=lambda r:r["scan_score"],reverse=True)
    core=[r for r in rows if r["avg_dollar_volume_20"]>=10_000_000]
    core.sort(key=lambda r:(r["avg_dollar_volume_20"],r["near_20d_high"]),reverse=True)
    eq=max(1,limit//2);cq=max(1,limit-eq);chosen=[];seen=set()
    for r in explosive[:eq]:
        chosen.append(r["symbol"]);seen.add(r["symbol"])
    for r in core:
        if r["symbol"] in seen:continue
        chosen.append(r["symbol"]);seen.add(r["symbol"])
        if len(chosen)>=eq+cq:break
    if len(chosen)<limit:
        fallback=sorted(rows,key=lambda r:(r["scan_score"],r["avg_dollar_volume_20"]),reverse=True)
        for r in fallback:
            if r["symbol"] in seen or r["avg_dollar_volume_20"]<10_000_000:continue
            chosen.append(r["symbol"]);seen.add(r["symbol"])
            if len(chosen)>=limit:break
    return chosen[:limit]

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--start",default="2024-01-01");ap.add_argument("--end",default="2026-10-01");ap.add_argument("--output",default="backtests/results/walkforward_2024_2026_fast.json");ap.add_argument("--markdown",default="backtests/results/walkforward_2024_2026_fast.md");ap.add_argument("--cache",default=".backtest_cache");args=ap.parse_args()
    start=date.fromisoformat(args.start);end=date.fromisoformat(args.end);cache=wf.Cache(args.cache)
    s=requests.Session();s.headers["User-Agent"]="Mozilla/5.0 ISK fast walk-forward"
    current,sectors,changes=wf.sp500_history(s);members0=wf.members_at(current,changes,start);rel=[x for x in changes if start<=date.fromisoformat(x["date"])<=end]
    union=set(members0)|current
    for x in rel:
        if x["added"]:union.add(x["added"])
        if x["removed"]:union.add(x["removed"])
    print("Universe union",len(union),flush=True)

    ps=start-timedelta(days=400);pe_=end+timedelta(days=5);market={}
    from concurrent.futures import ThreadPoolExecutor,as_completed
    def fy(sym):
        z=requests.Session();z.headers["User-Agent"]="Mozilla/5.0 ISK fast walk-forward";return sym,wf.yahoo(z,cache,sym,ps,pe_)
    with ThreadPoolExecutor(max_workers=12) as ex:
        fs=[ex.submit(fy,x) for x in sorted(union)]
        for i,f in enumerate(as_completed(fs),1):
            sym,v=f.result()
            if v:market[sym]=v
            if i%100==0:print("Yahoo",i,"/",len(fs),flush=True)

    etfs={}
    for e in set(wf.ETF.values()):
        v=wf.yahoo(s,cache,e,ps,pe_)
        if v:etfs[e]=v
    benchmark=wf.yahoo(s,cache,"^SP500TR",start-timedelta(days=5),end+timedelta(days=2))
    if not benchmark:benchmark=wf.yahoo(s,cache,"SPY",start-timedelta(days=5),end+timedelta(days=2))
    if not benchmark:raise RuntimeError("benchmark unavailable")

    trading=[date.fromisoformat(r["date"]) for r in benchmark["rows"] if start<=date.fromisoformat(r["date"])<=end]
    weeks=[];last=None
    for d in trading:
        k=d.isocalendar()[:2]
        if k!=last:weeks.append(d);last=k
        else:weeks[-1]=d

    # Build point-in-time membership + cheap-scan candidate lists first.
    bydate=defaultdict(list)
    for x in rel:bydate[date.fromisoformat(x["date"])].append(x)
    members=set(members0);deep_by_date={};candidate_union=set()
    for i,d in enumerate(weeks,1):
        for cd in sorted([x for x in list(bydate) if x<=d]):
            for x in bydate.pop(cd):
                if x["removed"]:members.discard(x["removed"])
                if x["added"]:members.add(x["added"])
        chosen=choose_deep({x for x in members if x in market},market,d)
        deep_by_date[d]=chosen;candidate_union.update(chosen)
        if i%25==0:print("Prefilter",i,"/",len(weeks),"unique deep",len(candidate_union),flush=True)
    print("SEC candidate union",len(candidate_union),flush=True)

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
                fdates[sym]=wf.filing_dates(f,start-timedelta(days=400),end)
            if i%50==0:print("SEC",i,"/",len(syms),flush=True)
    usable=set(market)&set(fmap);print("Usable deep candidates",len(usable),flush=True)

    # Replay continuous 3-year portfolio. Holdings stay in the deep set even if
    # they later fall outside the weekly discovery shortlist.
    members=set(members0);bydate=defaultdict(list)
    for x in rel:bydate[date.fromisoformat(x["date"])].append(x)
    states=[wf.State("Current model (R/R >=2x)",2.0,False),wf.State("No 2x R/R floor",0.0,False),wf.State("Core-only (R/R >=2x)",2.0,True)]
    for i,d in enumerate(weeks,1):
        for cd in sorted([x for x in list(bydate) if x<=d]):
            for x in bydate.pop(cd):
                if x["removed"]:members.discard(x["removed"])
                if x["added"]:members.add(x["added"])
        held=set().union(*(set(x.pos) for x in states))
        deep=set(deep_by_date[d])|held
        base={}
        for sym in deep:
            if sym not in fmap:continue
            a=wf.analyse(sym,d,market,fmap,fdates,sectors,etfs)
            if a:base[sym]=a
        investable_members=set(deep_by_date[d]) & set(members) & usable
        for st in states:wf.run_state(st,d,base,investable_members,market)
        if i%20==0 or i==len(weeks):print(d,i,"/",len(weeks),[(x.name,round(wf.equity(x,market,d))) for x in states],flush=True)

    br=wf.bench(benchmark,start,end);res=[wf.stat(x) for x in states]
    for r in res:
        r["alpha_vs_benchmark_total_pct"]=round(r["total_return_pct"]-br["total_return_pct"],2)
        r["cagr_spread_vs_benchmark_pct"]=round(r["cagr_pct"]-br["cagr_pct"],2)
    rep={"generated_at":wf.datetime.now(wf.timezone.utc).isoformat(),"period":{"start":args.start,"end":args.end},"methodology":{"mode":"two-stage weekly scanner replay","deep_candidates_per_week":DEEP_LIMIT,"prefilter":"live scanner-style Core liquidity + Explosive momentum/liquidity","starting_capital":wf.STARTING,"trade_cost_bps":wf.COST_BPS,"whole_shares":True,"hard_position_cap_pct":15},"coverage":{"historical_symbols":len(union),"price_symbols":len(market),"deep_candidate_union":len(candidate_union),"sec_symbols":len(fmap),"usable_deep_symbols":len(usable)},"results":res,"benchmark":br,"curves":{x.name:x.curve for x in states},"trades":{x.name:x.trades for x in states}}
    op=Path(args.output);op.parent.mkdir(parents=True,exist_ok=True);op.write_text(json.dumps(rep,indent=2))
    md=wf.md(rep).replace("# 2022-2026 Point-in-Time Walk-Forward Backtest","# 2024-2026 Fast Two-Stage Walk-Forward Backtest")
    md += "\n## Fast-mode methodology\n- The full historical S&P membership is cheap-screened each week.\n- Only the strongest 80 scanner-style candidates plus existing holdings receive full SEC/fundamental analysis.\n- This mirrors the production dashboard's two-stage discovery architecture and materially reduces runtime.\n"
    mp=Path(args.markdown);mp.parent.mkdir(parents=True,exist_ok=True);mp.write_text(md);print(md,flush=True)

if __name__=="__main__":main()
