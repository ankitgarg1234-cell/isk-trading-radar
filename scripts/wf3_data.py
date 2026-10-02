#!/usr/bin/env python3
from __future__ import annotations
import argparse, gzip, json, time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import requests
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import walkforward_backtest as wf

ETF_SYMBOLS=sorted(set(wf.ETF.values()))
BENCHMARKS=["^SP500TR","SPY"]

def dump_gz(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with gzip.open(path,"wt",encoding="utf-8") as f:json.dump(obj,f,separators=(",",":"))

def cp(root,group,key):
    p=Path(root)/group;p.mkdir(parents=True,exist_ok=True)
    return p/(key.replace("/","_").replace("^","IDX_")+".json")

def cget(root,group,key):
    p=cp(root,group,key)
    try:return json.loads(p.read_text()) if p.exists() else None
    except:return None

def cput(root,group,key,obj):cp(root,group,key).write_text(json.dumps(obj,separators=(",",":")))

def get_json(session,url,params=None,attempts=3,lim=None):
    err=None
    for i in range(attempts):
        try:
            if lim:lim.wait()
            r=session.get(url,params=params,timeout=(5,12))
            if r.status_code in (429,500,502,503,504):raise RuntimeError(f"HTTP {r.status_code}")
            r.raise_for_status();return r.json()
        except Exception as e:
            err=e;time.sleep(.75*(i+1))
    raise RuntimeError(str(err))

def fetch_yahoo(session,cache_root,sym,start,end):
    key=f"{sym}_{start}_{end}";cached=cget(cache_root,"yahoo",key)
    if cached:return cached
    try:
        raw=get_json(session,wf.YAHOO+sym,{"period1":wf.epoch(start),"period2":wf.epoch(end+timedelta(days=3)),"interval":"1d","events":"div,splits"})
        r=((raw.get("chart") or {}).get("result") or [None])[0]
        if not r:return None
        ts=r.get("timestamp") or [];q=((r.get("indicators") or {}).get("quote") or [{}])[0];rows=[]
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
        out={"rows":rows,"splits":sorted(spl,key=lambda z:z["date"]),"dividends":sorted(div,key=lambda z:z["date"])}
        if rows:cput(cache_root,"yahoo",key,out);return out
    except Exception:return None
    return None

def ticker_map(session,cache_root):
    cached=cget(cache_root,"sec","tickers")
    if cached:return cached
    for src in (wf.SEC_TICKERS,wf.SEC_TICKERS_MIRROR):
        try:
            raw=get_json(session,src);out={}
            if "fields" in raw and "data" in raw:
                fields=raw["fields"]
                for row in raw["data"]:
                    x=dict(zip(fields,row));t=wf.norm(x.get("ticker"));cik=x.get("cik")
                    if t and cik is not None:out[t]=f"{int(cik):010d}"
            else:
                for x in raw.values():
                    t=wf.norm(x.get("ticker"));cik=x.get("cik_str")
                    if t and cik is not None:out[t]=f"{int(cik):010d}"
            if out:cput(cache_root,"sec","tickers",out);return out
        except Exception:pass
    raise RuntimeError("SEC ticker map unavailable")

def fetch_fact(session,cache_root,lim,sym,cik):
    key=f"{sym}_{cik}";cached=cget(cache_root,"facts",key)
    if cached:return cached
    try:
        x=get_json(session,wf.SEC_FACTS.format(cik=cik),lim=lim)
        if x and x.get("facts"):cput(cache_root,"facts",key,x);return x
    except Exception:return None
    return None

def quick_metrics(data,d):
    h=wf.hist_asof(data,d,30)
    if len(h)<21:return None
    px=float(h[-1]["close"] or 0)
    if px<5:return None
    c=[float(x["close"]) for x in h];v=[float(x.get("volume") or 0) for x in h]
    c5=((px/c[-6])-1)*100 if len(c)>=6 and c[-6] else 0;c20=((px/c[-21])-1)*100 if c[-21] else 0
    base=[x for x in v[-21:-1] if x>0];av=sum(base)/len(base) if base else 0;rv=v[-1]/av if av else 0
    adv=px*av;near=px/max(c[-20:]);scan=min(max(c5,0),20)*2+min(max(c20,0),40)*.7+min(rv,5)*8+(8 if near>=.98 else 0)+(5 if adv>=20_000_000 else 0)
    return {"c5":c5,"c20":c20,"rv":rv,"adv":adv,"near":near,"scan":scan}

def choose(members,market,d,limit):
    rows=[]
    for s in members:
        q=quick_metrics(market.get(s) or {},d)
        if q:q["symbol"]=s;rows.append(q)
    half=max(1,limit//2)
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

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--start",default="2024-01-01");ap.add_argument("--end",default="2026-10-01")
    ap.add_argument("--deep-limit",type=int,default=80);ap.add_argument("--cache",default=".wf3_cache_v1")
    ap.add_argument("--output",default="backtests/staged/raw_dataset.json.gz");args=ap.parse_args()
    start=date.fromisoformat(args.start);end=date.fromisoformat(args.end);cache=args.cache
    s=requests.Session();s.headers["User-Agent"]="Mozilla/5.0 ISK staged walk-forward"
    err=None
    for i in range(3):
        try:current,sectors,changes=wf.sp500_history(s);err=None;break
        except Exception as e:err=e;time.sleep(i+1)
    if err:raise RuntimeError(f"S&P history failed: {err}")
    members0=wf.members_at(current,changes,start);rel=[x for x in changes if start<=date.fromisoformat(x["date"])<=end];union=set(members0)|current
    for x in rel:
        if x["added"]:union.add(x["added"])
        if x["removed"]:union.add(x["removed"])
    ps=start-timedelta(days=400);pe=end+timedelta(days=5);market={};price_failed=[]
    def fy(sym):
        z=requests.Session();z.headers["User-Agent"]="Mozilla/5.0 ISK staged walk-forward";return sym,fetch_yahoo(z,cache,sym,ps,pe)
    with ThreadPoolExecutor(max_workers=16) as ex:
        fs=[ex.submit(fy,x) for x in sorted(union)]
        for i,f in enumerate(as_completed(fs),1):
            sym,v=f.result()
            if v:market[sym]=v
            else:price_failed.append(sym)
            if i%100==0:print("PRICE",i,"/",len(fs),"ok",len(market),flush=True)
    price_pct=len(market)/max(1,len(union))
    if price_pct<.90:raise RuntimeError(f"price coverage {price_pct:.1%} below 90%")
    etfs={}
    for e in ETF_SYMBOLS:
        v=fetch_yahoo(s,cache,e,ps,pe)
        if v:etfs[e]=v
    benchmark_symbol=None;benchmark=None
    for b in BENCHMARKS:
        benchmark=fetch_yahoo(s,cache,b,start-timedelta(days=5),end+timedelta(days=2))
        if benchmark:benchmark_symbol=b;break
    if not benchmark:raise RuntimeError("benchmark unavailable")
    trading=[date.fromisoformat(r["date"]) for r in benchmark["rows"] if start<=date.fromisoformat(r["date"])<=end];weeks=[];wk=None
    for d in trading:
        k=d.isocalendar()[:2]
        if k!=wk:weeks.append(d);wk=k
        else:weeks[-1]=d
    bydate=defaultdict(list)
    for x in rel:bydate[date.fromisoformat(x["date"])].append(x)
    members=set(members0);pref={};candidate_union=set()
    for i,d in enumerate(weeks,1):
        for cd in sorted([x for x in list(bydate) if x<=d]):
            for x in bydate.pop(cd):
                if x["removed"]:members.discard(x["removed"])
                if x["added"]:members.add(x["added"])
        pick=choose({x for x in members if x in market},market,d,args.deep_limit);pref[d.isoformat()]=pick;candidate_union.update(pick)
        if i%25==0:print("PREFILTER",i,"/",len(weeks),"unique",len(candidate_union),flush=True)
    ss=requests.Session();ss.headers.update({"User-Agent":"ISK Trading Radar research https://github.com/ankitgarg1234-cell/isk-trading-radar","Accept":"application/json","Accept-Encoding":"gzip, deflate"})
    tm=ticker_map(ss,cache);lim=wf.Limiter(7);facts={};sec_failed=[]
    def ff(sym):
        cik=tm.get(sym)
        if not cik:return sym,None
        z=requests.Session();z.headers.update(ss.headers);return sym,fetch_fact(z,cache,lim,sym,cik)
    syms=sorted(candidate_union)
    with ThreadPoolExecutor(max_workers=6) as ex:
        fs=[ex.submit(ff,x) for x in syms]
        for i,f in enumerate(as_completed(fs),1):
            sym,v=f.result()
            if v:facts[sym]=v
            else:sec_failed.append(sym)
            if i%50==0:print("SEC",i,"/",len(fs),"ok",len(facts),flush=True)
    sec_pct=len(facts)/max(1,len(candidate_union))
    if sec_pct<.80:raise RuntimeError(f"SEC coverage {sec_pct:.1%} below 80%")
    out={"version":"wf3-staged-v1","generated_at":datetime.now(timezone.utc).isoformat(),"period":{"start":args.start,"end":args.end},"deep_limit":args.deep_limit,
         "membership":{"start_members":sorted(members0),"changes":rel,"sectors":sectors},"prefilters":pref,"candidate_union":sorted(candidate_union),
         "market":market,"sector_etfs":etfs,"benchmark_symbol":benchmark_symbol,"benchmark":benchmark,"sec_facts":facts,
         "coverage":{"universe":len(union),"price_ok":len(market),"price_pct":round(price_pct*100,2),"candidate_union":len(candidate_union),
                     "sec_ok":len(facts),"sec_pct":round(sec_pct*100,2),"price_failed":price_failed,"sec_failed":sec_failed}}
    dump_gz(args.output,out);print(json.dumps(out["coverage"],indent=2),flush=True)

if __name__=="__main__":main()
