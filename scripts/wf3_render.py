#!/usr/bin/env python3
from __future__ import annotations
import copy, gzip, json, math, os, statistics, sys, time, traceback
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
sys.path.insert(0,str(ROOT))
import walkforward_backtest as wf
import app.analysis_engine as ae
import app.portfolio_engine as pe
from app.analysis_engine import score_bundle

ae.CREDIBLE_PRIMARY.add("SEC EDGAR")

START=date(2024,1,1)
END=date(2026,10,1)
DEEP_LIMIT=80
UA="ISK Trading Radar research https://github.com/ankitgarg1234-cell/isk-trading-radar"
FRAME_URL="https://data.sec.gov/api/xbrl/frames/{taxonomy}/{tag}/{unit}/{frame}.json"
TICKER_MIRROR="https://raw.githubusercontent.com/Ancalagan/sec-data/main/company_tickers.json"

DURATION_TAGS=[
    ("us-gaap","RevenueFromContractWithCustomerExcludingAssessedTax","USD"),
    ("us-gaap","Revenues","USD"),
    ("us-gaap","SalesRevenueNet","USD"),
    ("us-gaap","NetIncomeLoss","USD"),
    ("us-gaap","ProfitLoss","USD"),
    ("us-gaap","GrossProfit","USD"),
    ("us-gaap","OperatingIncomeLoss","USD"),
]
INSTANT_TAGS=[
    ("us-gaap","StockholdersEquity","USD"),
    ("us-gaap","StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest","USD"),
    ("us-gaap","LongTermDebtCurrent","USD"),
    ("us-gaap","LongTermDebtNoncurrent","USD"),
    ("us-gaap","LongTermDebt","USD"),
    ("us-gaap","ShortTermBorrowings","USD"),
    ("dei","EntityCommonStockSharesOutstanding","shares"),
]

def get_json(session,url,params=None,attempts=3,lim=None):
    err=None
    for i in range(attempts):
        try:
            if lim:lim.wait()
            r=session.get(url,params=params,timeout=(5,20),headers={"User-Agent":UA,"Accept":"application/json","Accept-Encoding":"gzip, deflate"})
            if r.status_code==404:return None
            if r.status_code in (429,500,502,503,504):raise RuntimeError(f"HTTP {r.status_code}")
            r.raise_for_status();return r.json()
        except Exception as e:
            err=e;time.sleep(.75*(i+1))
    print("FETCH_FAIL",url,type(err).__name__,str(err)[:120],flush=True);return None

def yahoo(session,sym,start,end):
    try:
        raw=get_json(session,wf.YAHOO+sym,{"period1":wf.epoch(start),"period2":wf.epoch(end+timedelta(days=3)),"interval":"1d","events":"div,splits"},attempts=3)
        r=((raw or {}).get("chart") or {}).get("result") or []
        if not r:return None
        r=r[0];ts=r.get("timestamp") or [];q=((r.get("indicators") or {}).get("quote") or [{}])[0]
        rows=[]
        for i,t in enumerate(ts):
            def a(n):
                z=q.get(n) or [];return z[i] if i<len(z) else None
            if a("close") is None:continue
            rows.append({"date":datetime.fromtimestamp(t,tz=timezone.utc).date().isoformat(),"open":a("open"),"high":a("high"),"low":a("low"),"close":a("close"),"volume":a("volume") or 0})
        ev=r.get("events") or {};spl=[];div=[]
        for x in (ev.get("splits") or {}).values():
            try:spl.append({"date":datetime.fromtimestamp(float(x["date"]),tz=timezone.utc).date().isoformat(),"numerator":float(x["numerator"]),"denominator":float(x["denominator"]),"ratio":x.get("splitRatio")})
            except:pass
        for x in (ev.get("dividends") or {}).values():
            try:div.append({"date":datetime.fromtimestamp(float(x["date"]),tz=timezone.utc).date().isoformat(),"amount":float(x["amount"])})
            except:pass
        return {"rows":rows,"splits":sorted(spl,key=lambda x:x["date"]),"dividends":sorted(div,key=lambda x:x["date"])}
    except Exception:return None

def quick_metrics(data,d):
    h=wf.hist_asof(data,d,30)
    if len(h)<21:return None
    px=float(h[-1]["close"] or 0)
    if px<5:return None
    c=[float(x["close"]) for x in h];v=[float(x.get("volume") or 0) for x in h]
    c5=((px/c[-6])-1)*100 if c[-6] else 0;c20=((px/c[-21])-1)*100 if c[-21] else 0
    base=[x for x in v[-21:-1] if x>0];av=sum(base)/len(base) if base else 0;rv=v[-1]/av if av else 0
    adv=px*av;near=px/max(c[-20:]);scan=min(max(c5,0),20)*2+min(max(c20,0),40)*.7+min(rv,5)*8+(8 if near>=.98 else 0)+(5 if adv>=20_000_000 else 0)
    return {"c5":c5,"c20":c20,"rv":rv,"adv":adv,"near":near,"scan":scan}

def choose(members,market,d,limit=DEEP_LIMIT):
    rows=[]
    for s in members:
        q=quick_metrics(market.get(s) or {},d)
        if q:q["symbol"]=s;rows.append(q)
    half=limit//2
    exp=[r for r in rows if r["adv"]>=20_000_000 and (r["c5"]>=3 or r["c20"]>=7 or r["rv"]>=1.5 or r["near"]>=.985)]
    exp.sort(key=lambda r:r["scan"],reverse=True)
    core=[r for r in rows if r["adv"]>=10_000_000];core.sort(key=lambda r:(r["adv"],r["near"]),reverse=True)
    out=[];seen=set()
    for r in exp[:half]:out.append(r["symbol"]);seen.add(r["symbol"])
    for r in core:
        if r["symbol"] in seen:continue
        out.append(r["symbol"]);seen.add(r["symbol"])
        if len(out)>=limit:break
    return out[:limit]

def ticker_map(session):
    raw=get_json(session,wf.SEC_TICKERS,attempts=2)
    if raw:
        return {wf.norm(x.get("ticker")):int(x["cik_str"]) for x in raw.values() if wf.norm(x.get("ticker")) and x.get("cik_str") is not None}
    raw=get_json(session,TICKER_MIRROR,attempts=3)
    if not raw:raise RuntimeError("ticker map unavailable")
    fields=raw.get("fields") or [];out={}
    for row in raw.get("data") or []:
        x=dict(zip(fields,row));t=wf.norm(x.get("ticker"));cik=x.get("cik")
        if t and cik is not None:out[t]=int(cik)
    return out

def frame_periods():
    duration=[]
    for y in range(2022,2027):
        duration.append(f"CY{y}")
        for q in range(1,5):
            if y==2026 and q>3:continue
            duration.append(f"CY{y}Q{q}")
    instant=[]
    for y in range(2022,2027):
        for q in range(1,5):
            if y==2026 and q>3:continue
            instant.append(f"CY{y}Q{q}I")
    return duration,instant

def fetch_frames(session,candidate_ciks):
    duration,instant=frame_periods();store=defaultdict(lambda:defaultdict(list));lim=wf.Limiter(7)
    jobs=[]
    for tax,tag,unit in DURATION_TAGS:
        for fr in duration:jobs.append((tax,tag,unit,fr))
    for tax,tag,unit in INSTANT_TAGS:
        for fr in instant:jobs.append((tax,tag,unit,fr))
    def one(job):
        tax,tag,unit,fr=job
        url=FRAME_URL.format(taxonomy=tax,tag=tag,unit=unit,frame=fr)
        z=requests.Session();data=get_json(z,url,attempts=2,lim=lim)
        return job,data
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs=[ex.submit(one,j) for j in jobs]
        for i,f in enumerate(as_completed(futs),1):
            (tax,tag,unit,fr),data=f.result()
            for row in ((data or {}).get("data") or []):
                try:cik=int(row.get("cik"))
                except:continue
                if cik not in candidate_ciks:continue
                x=dict(row);x["_tag"]=tag;x["_taxonomy"]=tax;x["_unit"]=unit;store[cik][tag].append(x)
            if i%50==0:print("FRAME",i,"/",len(futs),"ciks",len(store),flush=True)
    return {str(cik):dict(tags) for cik,tags in store.items()}

def available(rows,d):
    out=[]
    for r in rows or []:
        try:
            if date.fromisoformat(str(r.get("filed"))[:10])<=d and r.get("val") is not None and r.get("end"):out.append(r)
        except:pass
    return out

def dur_days(r):
    try:return (date.fromisoformat(r["end"])-date.fromisoformat(r["start"])).days
    except:return None

def annual(rows,d):
    k={}
    for r in available(rows,d):
        if r.get("form") not in ("10-K","10-K/A","20-F","20-F/A"):continue
        n=dur_days(r)
        if n is not None and not 300<=n<=430:continue
        if r["end"] not in k or str(r.get("filed"))>=str(k[r["end"]].get("filed")):k[r["end"]]=r
    return sorted(k.values(),key=lambda x:x["end"])

def quarter(rows,d):
    k={}
    for r in available(rows,d):
        if r.get("form") not in ("10-Q","10-Q/A"):continue
        n=dur_days(r)
        if n is not None and not 65<=n<=120:continue
        if r["end"] not in k or str(r.get("filed"))>=str(k[r["end"]].get("filed")):k[r["end"]]=r
    return sorted(k.values(),key=lambda x:x["end"])

def latest(rows,d):
    rs=available(rows,d)
    if not rs:return None
    rs.sort(key=lambda r:(str(r.get("end")),str(r.get("filed"))))
    try:return float(rs[-1]["val"])
    except:return None

def first_series(tags,names,d,quarterly=False):
    for name in names:
        rs=quarter(tags.get(name),d) if quarterly else annual(tags.get(name),d)
        if rs:return rs
    return []

def growth(rs):
    if len(rs)<2:return None
    try:
        a=float(rs[-1]["val"]);b=float(rs[-2]["val"])
        return None if b==0 else a/b-1
    except:return None

def fundamental(tags,d,price):
    rev=first_series(tags,("RevenueFromContractWithCustomerExcludingAssessedTax","Revenues","SalesRevenueNet"),d)
    qrev=first_series(tags,("RevenueFromContractWithCustomerExcludingAssessedTax","Revenues","SalesRevenueNet"),d,True)
    ni=first_series(tags,("NetIncomeLoss","ProfitLoss"),d)
    gp=first_series(tags,("GrossProfit",),d);oi=first_series(tags,("OperatingIncomeLoss",),d)
    lr=float(rev[-1]["val"]) if rev else None;lni=float(ni[-1]["val"]) if ni else None
    lgp=float(gp[-1]["val"]) if gp else None;loi=float(oi[-1]["val"]) if oi else None
    eq=latest(tags.get("StockholdersEquity"),d)
    if eq is None:eq=latest(tags.get("StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),d)
    dcur=latest(tags.get("LongTermDebtCurrent"),d)
    if dcur is None:dcur=latest(tags.get("ShortTermBorrowings"),d)
    dnon=latest(tags.get("LongTermDebtNoncurrent"),d)
    if dnon is None:dnon=latest(tags.get("LongTermDebt"),d)
    debt=(dcur or 0)+(dnon or 0)
    shares=latest(tags.get("EntityCommonStockSharesOutstanding"),d)
    return {"revenueGrowth":growth(rev),"earningsGrowth":growth(ni),"quarterlyRevenueGrowth":growth(qrev),"totalRevenue":lr,
            "grossMargins":lgp/lr if lgp is not None and lr else None,"operatingMargins":loi/lr if loi is not None and lr else None,
            "returnOnEquity":lni/eq if lni is not None and eq not in (None,0) else None,
            "debtToEquity":debt/eq*100 if debt and eq not in (None,0) else None,
            "sharesOutstanding":shares,"marketCap":shares*price if shares and price else None,
            "_status":"available","_source":"SEC XBRL frames point-in-time"}

def recent_filing_news(tags,d):
    dates=[]
    for n in ("RevenueFromContractWithCustomerExcludingAssessedTax","Revenues","SalesRevenueNet","NetIncomeLoss","ProfitLoss"):
        for r in available(tags.get(n),d):
            try:
                fd=date.fromisoformat(str(r["filed"])[:10])
                if timedelta(0)<=d-fd<=timedelta(days=7):dates.append(fd)
            except:pass
    if not dates:return []
    fd=max(dates)
    return [{"title":"SEC earnings filing","publisher":"SEC EDGAR","providerPublishTime":datetime.combine(fd,datetime.min.time(),tzinfo=timezone.utc).timestamp()}]

def analyse(sym,d,market,frames,cikmap,sectors,etfs):
    data=market.get(sym);raw=wf.row_before(data or {},d)
    if not raw or not raw.get("close") or float(raw["close"])<5:return None
    hist=wf.hist_asof(data,d)
    if len(hist)<100:return None
    cik=cikmap.get(sym);tags=frames.get(str(cik)) if cik is not None else None
    if not tags:return None
    f=fundamental(tags,d,float(raw["close"]));sector=sectors.get(sym);sb=None;etf=wf.ETF.get(sector)
    if etf and etf in etfs:
        eh=wf.hist_asof(etfs[etf],d,180)
        if eh:sb={"symbol":etf,"price":eh[-1]["close"],"history":eh}
    rev=[]
    for x in data.get("splits") or []:
        sd=date.fromisoformat(x["date"])
        if d-timedelta(days=366)<=sd<=d and x["numerator"]<x["denominator"]:rev.append({"date":x["date"],"ratio":x.get("ratio")})
    bundle={"symbol":sym,"price":float(raw["close"]),"previous_close":hist[-2]["close"] if len(hist)>1 else hist[-1]["close"],
            "history":hist,"fundamentals":f,"news":recent_filing_news(tags,d),"recent_reverse_splits":rev,
            "strategic_capital":{"events":[]},"sector_benchmark":sb}
    try:
        out=score_bundle(bundle);out["symbol"]=sym;out["price"]=float(raw["close"]);return out
    except Exception:return None

def validate(st):
    if st.cash<-0.01:raise AssertionError(f"negative cash {st.cash}")
    for s,p in st.pos.items():
        if abs(p.shares-round(p.shares))>1e-8:raise AssertionError(f"fractional shares {s}")

def daily_curve(st,market,benchmark,start,end):
    trades=defaultdict(list)
    for t in st.trades:trades[t["date"]].append(t)
    held={};cash=wf.STARTING;curve=[];last=None
    for r in benchmark["rows"]:
        ds=r["date"];d=date.fromisoformat(ds)
        if not(start<=d<=end):continue
        if last is not None:
            for sym in list(held):
                data=market.get(sym) or {}
                for sp in data.get("splits") or []:
                    sd=date.fromisoformat(sp["date"])
                    if last<sd<=d:held[sym]*=float(sp["numerator"])/float(sp["denominator"])
                for dv in data.get("dividends") or []:
                    dd=date.fromisoformat(dv["date"])
                    if last<dd<=d:cash+=held[sym]*float(dv["amount"])
        for t in trades.get(ds,[]):
            gross=float(t["shares"])*float(t["price"]);fee=wf.fee(gross)
            if t["side"]=="BUY":cash-=gross+fee;held[t["symbol"]]=held.get(t["symbol"],0)+float(t["shares"])
            else:
                cash+=gross-fee;held[t["symbol"]]=max(0,held.get(t["symbol"],0)-float(t["shares"]))
                if held[t["symbol"]]<=1e-9:held.pop(t["symbol"],None)
        eq=cash
        for sym,qty in held.items():
            rr=wf.row_before(market.get(sym) or {},d)
            if rr and rr.get("close"):eq+=qty*float(rr["close"])
        curve.append({"date":ds,"equity":eq})
        last=d
    return curve

def stats(name,st,curve):
    endv=float(curve[-1]["equity"]);days=(date.fromisoformat(curve[-1]["date"])-date.fromisoformat(curve[0]["date"])).days;yrs=max(days/365.25,1/365.25)
    ret=endv/wf.STARTING-1;cagr=(endv/wf.STARTING)**(1/yrs)-1;peak=0;dd=0;by=defaultdict(list)
    for r in curve:
        e=r["equity"];peak=max(peak,e);dd=min(dd,e/peak-1);by[date.fromisoformat(r["date"]).year].append(e)
    prev=wf.STARTING;annual={}
    for y in sorted(by):v=by[y][-1];annual[str(y)]=round((v/prev-1)*100,2);prev=v
    sells=[t for t in st.trades if t["side"]=="SELL"];wins=[t for t in sells if float(t.get("pnl") or 0)>0]
    return {"name":name,"end_value":round(endv,2),"total_return_pct":round(ret*100,2),"cagr_pct":round(cagr*100,2),
            "max_drawdown_pct":round(dd*100,2),"annual_returns_pct":annual,"trade_count":len(st.trades),
            "win_rate_pct":round(len(wins)/len(sells)*100,2) if sells else None,"ending_cash":round(st.cash,2),"open_positions":len(st.pos)}

def main():
    dataset_path=ROOT/"backtests"/"staged"/"wf3_prices.json.gz"
    if not dataset_path.exists():
        raise RuntimeError(f"cached historical price dataset missing: {dataset_path}")
    with gzip.open(dataset_path,"rt",encoding="utf-8") as fh:
        ds=json.load(fh)
    START_DS=date.fromisoformat(ds["period"]["start"]);END_DS=date.fromisoformat(ds["period"]["end"])
    if START_DS != START or END_DS != END:
        raise RuntimeError(f"cached dataset period {START_DS}..{END_DS} does not match runner {START}..{END}")
    market=ds["market"];etfs=ds["sector_etfs"];benchmark=ds["benchmark"];benchmark_symbol=ds["benchmark_symbol"]
    sectors=ds["membership"]["sectors"];members0=set(ds["membership"]["start_members"]);rel=ds["membership"]["changes"]
    shortlists={date.fromisoformat(k):v for k,v in ds["prefilters"].items()}
    weeks=sorted(shortlists)
    candidate_union=set(ds["candidate_union"])
    union=set(market)
    print("WF3_CACHED_PRICES",json.dumps(ds.get("coverage") or {},separators=(",",":")),flush=True)
    sess=requests.Session()
    print("WF3_PHASE frames candidates",len(candidate_union),flush=True)
    cikmap=ticker_map(sess);candidate_ciks={cikmap[s] for s in candidate_union if s in cikmap}
    frames=fetch_frames(sess,candidate_ciks)
    frame_cov=sum(1 for s in candidate_union if str(cikmap.get(s,"")) in frames)/max(1,len(candidate_union))
    print("WF3_FRAME_COVERAGE",round(frame_cov*100,2),len(frames),flush=True)
    if frame_cov<.70:raise RuntimeError(f"frame coverage {frame_cov:.1%} below 70%")

    # Smoke: first 12 weeks, 20 candidates.
    smoke=[wf.State("Current model (R/R >=2x)",2.0,False),wf.State("No 2x R/R floor",0.0,False),wf.State("Core-only (R/R >=2x)",2.0,True)]
    for d in weeks[:12]:
        invest=set(shortlists[d][:20]);held=set().union(*(set(x.pos) for x in smoke));base={}
        for sym in invest|held:
            a=analyse(sym,d,market,frames,cikmap,sectors,etfs)
            if a:base[sym]=a
        for st in smoke:wf.run_state(st,d,base,invest,market);validate(st)
    print("WF3_SMOKE_PASS",sum(len(x.trades) for x in smoke),flush=True)

    states=[wf.State("Current model (R/R >=2x)",2.0,False),wf.State("No 2x R/R floor",0.0,False),wf.State("Core-only (R/R >=2x)",2.0,True)]
    for i,d in enumerate(weeks,1):
        invest=set(shortlists[d]);held=set().union(*(set(x.pos) for x in states));base={}
        for sym in invest|held:
            a=analyse(sym,d,market,frames,cikmap,sectors,etfs)
            if a:base[sym]=a
        for st in states:wf.run_state(st,d,base,invest,market);validate(st)
        if i%20==0 or i==len(weeks):print("WF3_SIM",d.isoformat(),i,len(weeks),[(x.name,round(wf.equity(x,market,d))) for x in states],flush=True)
    br=wf.bench(benchmark,weeks[0],weeks[-1]);results=[]
    for st in states:
        curve=daily_curve(st,market,benchmark,weeks[0],weeks[-1]);r=stats(st.name,st,curve)
        r["alpha_vs_benchmark_total_pct"]=round(r["total_return_pct"]-br["total_return_pct"],2);results.append(r)
    summary={"period":{"start":weeks[0].isoformat(),"end":weeks[-1].isoformat()},"benchmark_symbol":benchmark_symbol,
             "coverage":{"universe":len(union),"price_symbols":len(market),"candidate_union":len(candidate_union),"frame_coverage_pct":round(frame_cov*100,2)},
             "results":results,"benchmark":br}
    print("WF3_RESULT_JSON="+json.dumps(summary,separators=(",",":")),flush=True)

try:
    main()
except Exception as e:
    print("WF3_FAILED",type(e).__name__,str(e),flush=True);traceback.print_exc()
