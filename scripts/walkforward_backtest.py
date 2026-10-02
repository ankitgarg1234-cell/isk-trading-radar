#!/usr/bin/env python3
from __future__ import annotations
import argparse, bisect, copy, json, math, os, statistics, sys, threading, time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
import pandas as pd
import requests

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import app.analysis_engine as ae
import app.portfolio_engine as pe
from app.analysis_engine import score_bundle, position_action, position_action_plan
from app.portfolio_engine import build_optimizer_plan, suggested_position_size

ae.CREDIBLE_PRIMARY.add("SEC EDGAR")

STARTING=10000.0
COST_BPS=10.0
MIN_RR=2.0
WIKI="https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
WIKI_HISTORY="https://en.wikipedia.org/wiki/Historical_components_of_the_S%26P_500"
YAHOO="https://query1.finance.yahoo.com/v8/finance/chart/"
SEC_TICKERS="https://www.sec.gov/files/company_tickers.json"
SEC_TICKERS_MIRROR="https://raw.githubusercontent.com/Ancalagan/sec-data/main/company_tickers.json"
SEC_FACTS="https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

def sf(v):
    try:return float(v)
    except:return None

def norm(v):
    s=str(v or "").strip().upper()
    return "" if not s or s=="NAN" else s.replace(".","-")

class Cache:
    def __init__(self,p):self.p=Path(p);self.p.mkdir(parents=True,exist_ok=True)
    def _p(self,g,k):
        d=self.p/g;d.mkdir(parents=True,exist_ok=True)
        return d/(k.replace("/","_").replace("^","IDX_")+".json")
    def get(self,g,k):
        p=self._p(g,k)
        try:return json.loads(p.read_text()) if p.exists() else None
        except:return None
    def put(self,g,k,v):self._p(g,k).write_text(json.dumps(v))

class Limiter:
    def __init__(self,rps):self.dt=1/rps;self.lock=threading.Lock();self.n=0.0
    def wait(self):
        with self.lock:
            now=time.monotonic()
            if now<self.n:time.sleep(self.n-now)
            self.n=time.monotonic()+self.dt

def jget(s,url,params=None,lim=None):
    err=None
    for i in range(5):
        try:
            if lim:lim.wait()
            r=s.get(url,params=params,timeout=30)
            if r.status_code in (429,500,502,503,504):raise RuntimeError(str(r.status_code))
            r.raise_for_status();return r.json()
        except Exception as e:
            err=e;time.sleep(min(10,1.5**i))
    raise RuntimeError(str(err))

def flat(df):
    z=df.copy()
    z.columns=[" ".join(dict.fromkeys(str(x) for x in c if str(x)!="nan")) if isinstance(c,tuple) else str(c) for c in z.columns]
    return z

def col(cols,*parts):
    for c in cols:
        q=c.lower()
        if all(p.lower() in q for p in parts):return c
    return None

def sp500_history(s):
    html=s.get(WIKI,headers={"User-Agent":"Mozilla/5.0"},timeout=30).text
    tabs=[flat(x) for x in pd.read_html(StringIO(html))]
    cur=next(x for x in tabs if col(list(x.columns),"symbol") and col(list(x.columns),"gics","sector"))
    sc=col(list(cur.columns),"symbol");gc=col(list(cur.columns),"gics","sector")
    current=set();sectors={}
    for _,r in cur.iterrows():
        t=norm(r.get(sc))
        if t:current.add(t);sectors[t]=str(r.get(gc) or "")
    hist_html=s.get(WIKI_HISTORY,headers={"User-Agent":"Mozilla/5.0"},timeout=30).text
    hist_tabs=[flat(x) for x in pd.read_html(StringIO(hist_html))]
    ch=next(x for x in hist_tabs if col(list(x.columns),"added","ticker") and col(list(x.columns),"removed","ticker"))
    dc=col(list(ch.columns),"date");ac=col(list(ch.columns),"added","ticker");rc=col(list(ch.columns),"removed","ticker")
    changes=[]
    for _,r in ch.iterrows():
        try:d=pd.to_datetime(r.get(dc)).date()
        except:continue
        a=norm(r.get(ac));rem=norm(r.get(rc))
        if a or rem:changes.append({"date":d.isoformat(),"added":a,"removed":rem})
    changes.sort(key=lambda x:x["date"])
    return current,sectors,changes

def members_at(current,changes,start):
    m=set(current)
    for x in reversed(changes):
        d=date.fromisoformat(x["date"])
        if d<=start:continue
        if x["added"]:m.discard(x["added"])
        if x["removed"]:m.add(x["removed"])
    return m

def epoch(d):return int(datetime(d.year,d.month,d.day,tzinfo=timezone.utc).timestamp())

def yahoo(s,cache,sym,start,end):
    key=sym+"_"+start.isoformat()+"_"+end.isoformat()
    c=cache.get("yahoo",key)
    if c is not None:return None if c.get("missing") else c
    try:
        data=jget(s,YAHOO+sym,{"period1":epoch(start),"period2":epoch(end+timedelta(days=3)),"interval":"1d","events":"div,splits"})
        r=((data.get("chart") or {}).get("result") or [None])[0]
        if not r:raise RuntimeError("no chart")
        ts=r.get("timestamp") or [];q=((r.get("indicators") or {}).get("quote") or [{}])[0]
        rows=[]
        for i,t in enumerate(ts):
            def a(n):
                x=q.get(n) or [];return x[i] if i<len(x) else None
            if a("close") is None:continue
            rows.append({"date":datetime.fromtimestamp(t,tz=timezone.utc).date().isoformat(),"open":a("open"),"high":a("high"),"low":a("low"),"close":a("close"),"volume":a("volume") or 0})
        ev=r.get("events") or {};spl=[];div=[]
        for x in (ev.get("splits") or {}).values():
            try:
                spl.append({"date":datetime.fromtimestamp(float(x["date"]),tz=timezone.utc).date().isoformat(),"numerator":float(x["numerator"]),"denominator":float(x["denominator"]),"ratio":x.get("splitRatio")})
            except:pass
        for x in (ev.get("dividends") or {}).values():
            try:div.append({"date":datetime.fromtimestamp(float(x["date"]),tz=timezone.utc).date().isoformat(),"amount":float(x["amount"])})
            except:pass
        out={"rows":rows,"splits":sorted(spl,key=lambda x:x["date"]),"dividends":sorted(div,key=lambda x:x["date"])}
        cache.put("yahoo",key,out);return out
    except:
        cache.put("yahoo",key,{"missing":True});return None

def ticker_map(s,cache,lim):
    c=cache.get("sec","tickers")
    if c:return c
    try:
        raw=jget(s,SEC_TICKERS,lim=lim)
        records=list(raw.values())
        out={}
        for x in records:
            t=norm(x.get("ticker"))
            if t:out[t]=f"{int(x['cik_str']):010d}"
    except Exception:
        # GitHub-hosted runners are sometimes blocked by www.sec.gov. This
        # mirror contains only SEC's public ticker/CIK crosswalk; company facts
        # below still come directly from data.sec.gov.
        raw=jget(s,SEC_TICKERS_MIRROR)
        fields=raw.get("fields") or []
        out={}
        for row in raw.get("data") or []:
            x=dict(zip(fields,row))
            t=norm(x.get("ticker"))
            cik=x.get("cik")
            if t and cik is not None:out[t]=f"{int(cik):010d}"
    cache.put("sec","tickers",out);return out

def facts(s,cache,lim,sym,cik):
    c=cache.get("facts",sym+"_"+cik)
    if c is not None:return None if c.get("missing") else c
    try:
        x=jget(s,SEC_FACTS.format(cik=cik),lim=lim);cache.put("facts",sym+"_"+cik,x);return x
    except:
        cache.put("facts",sym+"_"+cik,{"missing":True});return None

def fact(f,ns,tags):
    z=(f.get("facts") or {}).get(ns) or {}
    for t in tags:
        if t in z:return z[t]
    return None

def ents(o,units=("USD",)):
    if not o:return []
    u=o.get("units") or {}
    for x in units:
        if x in u:return list(u[x] or [])
    return list(next(iter(u.values()),[]) or [])

def avail(o,d,units=("USD",)):
    out=[]
    for r in ents(o,units):
        try:
            if date.fromisoformat(str(r.get("filed"))[:10])>d:continue
        except:continue
        if r.get("val") is not None and r.get("end"):out.append(r)
    return out

def days(r):
    try:return (date.fromisoformat(r["end"])-date.fromisoformat(r["start"])).days
    except:return None

def annual(o,d,units=("USD",)):
    k={}
    for r in avail(o,d,units):
        if r.get("form") not in ("10-K","10-K/A","20-F","20-F/A"):continue
        n=days(r)
        if n is not None and not 300<=n<=430:continue
        if r["end"] not in k or str(r.get("filed"))>=str(k[r["end"]].get("filed")):k[r["end"]]=r
    return sorted(k.values(),key=lambda x:x["end"])

def quarter(o,d,units=("USD",)):
    k={}
    for r in avail(o,d,units):
        if r.get("form") not in ("10-Q","10-Q/A"):continue
        n=days(r)
        if n is not None and not 65<=n<=120:continue
        if r["end"] not in k or str(r.get("filed"))>=str(k[r["end"]].get("filed")):k[r["end"]]=r
    return sorted(k.values(),key=lambda x:x["end"])

def instant(o,d,units=("USD",)):
    rs=[r for r in avail(o,d,units) if r.get("form") in ("10-K","10-K/A","10-Q","10-Q/A","20-F","20-F/A","8-K")]
    if not rs:return None
    rs.sort(key=lambda r:(str(r.get("end")),str(r.get("filed"))));return sf(rs[-1].get("val"))

def growth(x):
    if len(x)<2:return None
    a=sf(x[-1]["val"]);b=sf(x[-2]["val"])
    return None if a is None or b in (None,0) else a/b-1

def fundamental(f,d,price,sector):
    revf=fact(f,"us-gaap",("RevenueFromContractWithCustomerExcludingAssessedTax","Revenues","SalesRevenueNet"))
    nif=fact(f,"us-gaap",("NetIncomeLoss","ProfitLoss"));gpf=fact(f,"us-gaap",("GrossProfit",));oif=fact(f,"us-gaap",("OperatingIncomeLoss",))
    eqf=fact(f,"us-gaap",("StockholdersEquity","StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"))
    caf=fact(f,"us-gaap",("AssetsCurrent",));clf=fact(f,"us-gaap",("LiabilitiesCurrent",));ocff=fact(f,"us-gaap",("NetCashProvidedByUsedInOperatingActivities",))
    shf=fact(f,"dei",("EntityCommonStockSharesOutstanding",));wsh=fact(f,"us-gaap",("WeightedAverageNumberOfDilutedSharesOutstanding","WeightedAverageNumberOfSharesOutstandingBasic"))
    dcf=fact(f,"us-gaap",("LongTermDebtAndFinanceLeaseObligationsCurrent","LongTermDebtCurrent","ShortTermBorrowings"))
    dnf=fact(f,"us-gaap",("LongTermDebtAndFinanceLeaseObligationsNoncurrent","LongTermDebtNoncurrent","LongTermDebt"))
    rev=annual(revf,d);ni=annual(nif,d);gp=annual(gpf,d);oi=annual(oif,d);ocf=annual(ocff,d);qr=quarter(revf,d)
    lr=sf(rev[-1]["val"]) if rev else None;lni=sf(ni[-1]["val"]) if ni else None;lgp=sf(gp[-1]["val"]) if gp else None;loi=sf(oi[-1]["val"]) if oi else None;locf=sf(ocf[-1]["val"]) if ocf else None
    eq=instant(eqf,d);ca=instant(caf,d);cl=instant(clf,d);shares=instant(shf,d,("shares",))
    if not shares:
        qs=quarter(wsh,d,("shares",));an=annual(wsh,d,("shares",));src=qs or an;shares=sf(src[-1]["val"]) if src else None
    debt=(instant(dcf,d) or 0)+(instant(dnf,d) or 0)
    return {"revenueGrowth":growth(rev),"earningsGrowth":growth(ni),"quarterlyRevenueGrowth":growth(qr),"totalRevenue":lr,
        "grossMargins":lgp/lr if lgp is not None and lr else None,"operatingMargins":loi/lr if loi is not None and lr else None,
        "returnOnEquity":lni/eq if lni is not None and eq not in (None,0) else None,"debtToEquity":debt/eq*100 if debt and eq not in (None,0) else None,
        "currentRatio":ca/cl if ca is not None and cl not in (None,0) else None,"operatingCashConversion":locf/lni if locf is not None and lni not in (None,0) else None,
        "sharesOutstanding":shares,"marketCap":shares*price if shares and price else None,"sector":sector,"_status":"available","_source":"SEC point-in-time"}

def filing_dates(f,start,end):
    out=set();us=(f.get("facts") or {}).get("us-gaap") or {}
    for tag in ("RevenueFromContractWithCustomerExcludingAssessedTax","Revenues","SalesRevenueNet","NetIncomeLoss","ProfitLoss"):
        for rs in ((us.get(tag) or {}).get("units") or {}).values():
            for r in rs:
                if r.get("form") not in ("10-Q","10-Q/A","10-K","10-K/A","20-F","20-F/A"):continue
                try:d=date.fromisoformat(str(r.get("filed"))[:10])
                except:continue
                if start<=d<=end:out.add(d)
    return sorted(out)

def row_before(data,d):
    rs=data.get("rows") or [];ds=[r["date"] for r in rs];i=bisect.bisect_right(ds,d.isoformat())-1
    return rs[i] if i>=0 else None

def next_row(data,d):
    rs=data.get("rows") or [];ds=[r["date"] for r in rs];i=bisect.bisect_right(ds,d.isoformat())
    return rs[i] if i<len(rs) else None

def hist_asof(data,d,n=270):
    rs=[r for r in data.get("rows") or [] if r["date"]<=d.isoformat()][-n:];spl=[x for x in data.get("splits") or [] if x["date"]<=d.isoformat()]
    out=[]
    for r in rs:
        rd=date.fromisoformat(r["date"]);fac=1.0
        for x in spl:
            sd=date.fromisoformat(x["date"])
            if rd<sd<=d:fac*=x["denominator"]/x["numerator"]
        out.append({"date":r["date"],"open":sf(r["open"])*fac if sf(r["open"]) is not None else None,"high":sf(r["high"])*fac if sf(r["high"]) is not None else None,
            "low":sf(r["low"])*fac if sf(r["low"]) is not None else None,"close":sf(r["close"])*fac,"volume":(sf(r["volume"]) or 0)/fac if fac else 0})
    return out

ETF={"Information Technology":"XLK","Communication Services":"XLC","Consumer Discretionary":"XLY","Consumer Staples":"XLP","Financials":"XLF","Health Care":"XLV","Industrials":"XLI","Energy":"XLE","Materials":"XLB","Real Estate":"XLRE","Utilities":"XLU"}

def analyse(sym,d,market,fmap,fdates,sectors,etfs):
    data=market.get(sym);raw=row_before(data,d) if data else None
    if not raw or not raw.get("close") or float(raw["close"])<5:return None
    h=hist_asof(data,d)
    if len(h)<100:return None
    f=fmap.get(sym)
    if not f:return None
    fundamentals=fundamental(f,d,float(raw["close"]),sectors.get(sym))
    fd=fdates.get(sym,[]);recent=[x for x in fd if timedelta(0)<=d-x<=timedelta(days=7)]
    news=[]
    if recent:news=[{"title":"SEC earnings filing","publisher":"SEC EDGAR","providerPublishTime":datetime.combine(recent[-1],datetime.min.time(),tzinfo=timezone.utc).timestamp()}]
    sb=None;etf=ETF.get(sectors.get(sym))
    if etf and etf in etfs:
        eh=hist_asof(etfs[etf],d,180)
        if eh:sb={"symbol":etf,"price":eh[-1]["close"],"history":eh}
    rev=[]
    for x in data.get("splits") or []:
        sd=date.fromisoformat(x["date"])
        if d-timedelta(days=366)<=sd<=d and x["numerator"]<x["denominator"]:rev.append({"date":x["date"],"ratio":x.get("ratio")})
    b={"symbol":sym,"price":float(raw["close"]),"previous_close":h[-2]["close"] if len(h)>1 else h[-1]["close"],"history":h,"fundamentals":fundamentals,
       "news":news,"recent_reverse_splits":rev,"strategic_capital":{"events":[]},"sector_benchmark":sb}
    try:
        r=score_bundle(b);r["symbol"]=sym;r["price"]=float(raw["close"]);return r
    except:return None

@dataclass
class Pos:
    shares:float;avg:float;opened:date;lane:str;rank:float
@dataclass
class State:
    name:str;rr:float;core_only:bool;cash:float=STARTING;pos:dict=field(default_factory=dict);trades:list=field(default_factory=list);curve:list=field(default_factory=list);snap:dict=field(default_factory=dict);last:date|None=None

def fee(v):return abs(v)*COST_BPS/10000

def corp(st,market,d):
    if st.last is None:st.last=d;return
    for sym,p in list(st.pos.items()):
        data=market.get(sym) or {}
        # Cached Yahoo OHLC is already split-adjusted historically.
        # Applying split events again would double-count corporate actions.
        for x in data.get("dividends") or []:
            dd=date.fromisoformat(x["date"])
            if max(st.last,p.opened-timedelta(days=1))<dd<=d:st.cash+=p.shares*x["amount"]
    st.last=d

def equity(st,market,d):
    v=st.cash
    for s,p in st.pos.items():
        r=row_before(market.get(s) or {},d)
        if r and r.get("close"):v+=p.shares*float(r["close"])
    return v

def do_sell(st,s,q,price,d,reason):
    p=st.pos.get(s)
    if not p:return
    q=min(p.shares,math.floor(float(q)+1e-9))
    if q<=0:return
    gross=q*price;f=fee(gross);pnl=q*(price-p.avg)-f;st.cash+=gross-f
    st.trades.append({"date":d.isoformat(),"symbol":s,"side":"SELL","shares":q,"price":price,"pnl":pnl,"reason":reason,"lane":p.lane,"days":(d-p.opened).days})
    p.shares-=q
    if p.shares<=1e-9:st.pos.pop(s,None)

def do_buy(st,s,q,price,d,reason,lane,rank):
    q=int(q)
    if q<=0:return
    maxq=math.floor(st.cash/(price*(1+COST_BPS/10000)))
    q=min(q,maxq)
    if q<=0:return
    gross=q*price;f=fee(gross);st.cash-=gross+f
    if s in st.pos:
        p=st.pos[s];tot=p.shares+q;p.avg=(p.avg*p.shares+price*q)/tot;p.shares=tot
    else:st.pos[s]=Pos(q,price,d,lane,rank)
    st.trades.append({"date":d.isoformat(),"symbol":s,"side":"BUY","shares":q,"price":price,"reason":reason,"lane":lane,"rank":rank})

def reliable(a):
    return str(a.get("fundamental_confidence") or "low") in ("medium","high") and float((a.get("fundamentals") or {}).get("marketCap") or 0)>0 and float((a.get("technicals") or {}).get("avg_dollar_volume_20") or 0)>0

def run_state(st,d,base,members,market):
    corp(st,market,d);analyses={}
    for s in set(members)|set(st.pos):
        if s not in base:continue
        a=copy.deepcopy(base[s])
        if s in st.snap:a["previous_snapshot"]=st.snap[s]
        p=st.pos.get(s);pd=None if not p else {"shares":p.shares,"avg_cost":p.avg,"account":"Backtest"}
        act,why=position_action(a,float(a["price"]),pd);a["action"]=act;a["action_reason"]=why
        st.snap[s]={"breakdown":copy.deepcopy(a.get("breakdown") or {}),"deterministic_score":a.get("deterministic_score"),"action":act}
        analyses[s]=a
    exits=[]
    for s,p in list(st.pos.items()):
        a=analyses.get(s)
        if not a:continue
        # A holding leaving the current entry lane is NOT itself an exit.
        # Existing positions follow the thesis-gated management rule: technical
        # weakness / loss of lane qualification alone must not trigger a sale.
        if a["action"]=="EXIT":exits.append((s,p.shares,"THESIS EXIT"))
        elif a["action"] in ("REDUCE","TAKE PARTIAL PROFIT"):
            plan=position_action_plan(a["action"],a,float(a["price"]),{"shares":p.shares,"avg_cost":p.avg,"account":"Backtest"})
            if plan and plan.get("quantity"):exits.append((s,plan["quantity"],a["action"]))
        if p.lane=="EXPLOSIVE" and a.get("lane")!="CORE_QUALITY" and (d-p.opened).days>=28:exits.append((s,p.shares,"EXPLOSIVE TIME STOP"))
    for s,q,why in exits:
        nr=next_row(market.get(s) or {},d)
        if nr and nr.get("open"):do_sell(st,s,q,float(nr["open"]),date.fromisoformat(nr["date"]),why)
    old=pe.MIN_ENTRY_RISK_REWARD;pe.MIN_ENTRY_RISK_REWARD=st.rr
    try:
        x={s:a for s,a in analyses.items() if s in members or s in st.pos}
        if st.core_only:x={s:a for s,a in x.items() if s in st.pos or a.get("lane")=="CORE_QUALITY"}
        plan=build_optimizer_plan(x,set(st.pos),profile="MEDIUM",visible_limit=20,shortlist_limit=20)
    finally:pe.MIN_ENTRY_RISK_REWARD=old
    orders=[(r,"NEW") for r in plan.get("selected_new") or []]
    orders += [(r,"ADD") for r in plan.get("visible") or [] if r.get("owned") and r.get("optimizer_action")=="ADD" and float((r.get("analysis") or {}).get("risk_reward") or 0)>=st.rr]
    orders.sort(key=lambda z:float(z[0].get("rank_score") or 0),reverse=True)
    for r,kind in orders:
        s=r["symbol"];nr=next_row(market.get(s) or {},d)
        if not nr or not nr.get("open"):continue
        px=float(nr["open"]);ed=date.fromisoformat(nr["date"]);existing=st.pos.get(s);ev=existing.shares*px if existing else 0
        a=copy.deepcopy(r["analysis"]);a["price"]=px
        size=suggested_position_size(a,cash=st.cash,reserve_cash=0,portfolio_value=max(equity(st,market,d),STARTING),profile="MEDIUM",fx_rate_to_base=1,existing_value=ev,whole_shares=True)
        if int(size.get("shares") or 0)>0:do_buy(st,s,int(size["shares"]),px,ed,kind+" "+str(r.get("entry_signal") or r.get("optimizer_action")),a.get("lane") or "CORE_QUALITY",float(r.get("rank_score") or 0))
    st.curve.append({"date":d.isoformat(),"equity":round(equity(st,market,d),2),"cash":round(st.cash,2),"positions":len(st.pos)})

def stat(st):
    c=st.curve;endv=float(c[-1]["equity"]);yrs=(date.fromisoformat(c[-1]["date"])-date.fromisoformat(c[0]["date"])).days/365.25
    ret=endv/STARTING-1;cagr=(endv/STARTING)**(1/yrs)-1;peak=0;dd=0;by=defaultdict(list)
    for r in c:
        e=float(r["equity"]);peak=max(peak,e);dd=min(dd,e/peak-1);by[date.fromisoformat(r["date"]).year].append(r)
    prev=STARTING;annual={}
    for y in sorted(by):v=float(by[y][-1]["equity"]);annual[str(y)]=v/prev-1;prev=v
    sells=[t for t in st.trades if t["side"]=="SELL"];wins=[t for t in sells if t.get("pnl",0)>0]
    return {"name":st.name,"end_value":round(endv,2),"total_return_pct":round(ret*100,2),"cagr_pct":round(cagr*100,2),"max_drawdown_pct":round(dd*100,2),
        "annual_returns_pct":{k:round(v*100,2) for k,v in annual.items()},"trade_count":len(st.trades),"win_rate_pct":round(len(wins)/len(sells)*100,2) if sells else None,
        "average_holding_days":round(statistics.mean([t["days"] for t in sells]),1) if sells else None,"ending_cash":round(st.cash,2),"open_positions":len(st.pos)}

def bench(data,start,end):
    rs=[r for r in data["rows"] if start<=date.fromisoformat(r["date"])<=end];first=float(rs[0]["close"]);last=float(rs[-1]["close"])
    yrs=(date.fromisoformat(rs[-1]["date"])-date.fromisoformat(rs[0]["date"])).days/365.25;ret=last/first-1;cagr=(last/first)**(1/yrs)-1;peak=0;dd=0;by=defaultdict(list)
    prev=STARTING
    for r in rs:
        e=STARTING*float(r["close"])/first;peak=max(peak,e);dd=min(dd,e/peak-1);by[date.fromisoformat(r["date"]).year].append(e)
    annual={}
    for y in sorted(by):v=by[y][-1];annual[str(y)]=v/prev-1;prev=v
    return {"name":"S&P 500 Total Return","end_value":round(STARTING*(1+ret),2),"total_return_pct":round(ret*100,2),"cagr_pct":round(cagr*100,2),"max_drawdown_pct":round(dd*100,2),"annual_returns_pct":{k:round(v*100,2) for k,v in annual.items()}}

def md(rep):
    a=["# 2022-2026 Point-in-Time Walk-Forward Backtest","","| Variant | End value | Total return | CAGR | Max DD | Trades | Win rate |","|---|---:|---:|---:|---:|---:|---:|"]
    for r in rep["results"]+[rep["benchmark"]]:
        a.append("| "+r["name"]+" | USD "+format(r["end_value"],",.0f")+" | "+format(r["total_return_pct"],"+.1f")+"% | "+format(r["cagr_pct"],"+.1f")+"% | "+format(r["max_drawdown_pct"],".1f")+"% | "+str(r.get("trade_count","—"))+" | "+("—" if r.get("win_rate_pct") is None else str(r["win_rate_pct"])+"%")+" |")
    a += ["","## Limitations","- Point-in-time S&P 500 membership reconstructed from the public constituent/change tables.","- SEC fundamentals become usable only after filing dates.","- General historical news, analyst consensus and strategic-capital evidence are unavailable; SEC earnings filings are the only catalyst proxy.","- Weekly close signals execute at the next session open. Whole-share sizing, 15% hard cap and 10 bps transaction costs are applied.","- Current Model requires R/R >= 2.0x for buys/adds. Falling below 2x later is not itself a sell trigger.","- Historical simulation is not a guarantee of future results."]
    return "\n".join(a)+"\n"

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--start",default="2022-01-01");ap.add_argument("--end",default="2026-10-01");ap.add_argument("--output",default="backtests/results/walkforward_2022_2026.json");ap.add_argument("--markdown",default="backtests/results/walkforward_2022_2026.md");ap.add_argument("--cache",default=".backtest_cache");args=ap.parse_args()
    start=date.fromisoformat(args.start);end=date.fromisoformat(args.end);cache=Cache(args.cache);s=requests.Session();s.headers["User-Agent"]="Mozilla/5.0 ISK backtest"
    current,sectors,changes=sp500_history(s);members=members_at(current,changes,start);rel=[x for x in changes if start<=date.fromisoformat(x["date"])<=end];union=set(members)|current
    for x in rel:
        if x["added"]:union.add(x["added"])
        if x["removed"]:union.add(x["removed"])
    print("Universe union",len(union),flush=True)
    mkt={};ps=start-timedelta(days=400);pe_=end+timedelta(days=5)
    def fy(sym):
        z=requests.Session();z.headers["User-Agent"]="Mozilla/5.0 ISK backtest";return sym,yahoo(z,cache,sym,ps,pe_)
    with ThreadPoolExecutor(max_workers=10) as ex:
        fs=[ex.submit(fy,x) for x in sorted(union)]
        for i,f in enumerate(as_completed(fs),1):
            sym,v=f.result()
            if v:mkt[sym]=v
            if i%50==0:print("Yahoo",i,"/",len(fs),flush=True)
    etfs={}
    for e in ETF.values():
        if e not in etfs:
            v=yahoo(s,cache,e,ps,pe_)
            if v:etfs[e]=v
    b=yahoo(s,cache,"^SP500TR",start-timedelta(days=5),end+timedelta(days=2))
    if not b:
        b=yahoo(s,cache,"SPY",start-timedelta(days=5),end+timedelta(days=2))
    lim=Limiter(5);ss=requests.Session();ss.headers.update({
        "User-Agent":os.getenv("SEC_USER_AGENT","ISK Trading Radar research https://github.com/ankitgarg1234-cell/isk-trading-radar"),
        "Accept-Encoding":"gzip, deflate",
        "Accept":"application/json",
    });tm=ticker_map(ss,cache,lim);fmap={};fdates={}
    for i,sym in enumerate(sorted(union),1):
        cik=tm.get(sym)
        if cik:
            f=facts(ss,cache,lim,sym,cik)
            if f:fmap[sym]=f;fdates[sym]=filing_dates(f,start-timedelta(days=400),end)
        if i%50==0:print("SEC",i,"/",len(union),flush=True)
    usable=set(mkt)&set(fmap);print("Usable",len(usable),flush=True)
    trading=[date.fromisoformat(r["date"]) for r in b["rows"] if start<=date.fromisoformat(r["date"])<=end]
    weeks=[];lastweek=None
    for d in trading:
        key=d.isocalendar()[:2]
        if key!=lastweek:
            weeks.append(d);lastweek=key
        else:weeks[-1]=d
    bydate=defaultdict(list)
    for x in rel:bydate[date.fromisoformat(x["date"])].append(x)
    states=[State("Current model (R/R >=2x)",2.0,False),State("No 2x R/R floor",0.0,False),State("Core-only (R/R >=2x)",2.0,True)]
    for i,d in enumerate(weeks,1):
        for cd in sorted([x for x in list(bydate) if x<=d]):
            for x in bydate.pop(cd):
                if x["removed"]:members.discard(x["removed"])
                if x["added"]:members.add(x["added"])
        mem={x for x in members if x in usable};held=set().union(*(set(x.pos) for x in states));base={}
        for sym in mem|held:
            a=analyse(sym,d,mkt,fmap,fdates,sectors,etfs)
            if a:base[sym]=a
        for st in states:run_state(st,d,base,mem,mkt)
        if i%20==0 or i==len(weeks):print(d,i,"/",len(weeks),[(x.name,round(equity(x,mkt,d))) for x in states],flush=True)
    br=bench(b,start,end);res=[stat(x) for x in states]
    for r in res:r["alpha_vs_benchmark_total_pct"]=round(r["total_return_pct"]-br["total_return_pct"],2);r["cagr_spread_vs_benchmark_pct"]=round(r["cagr_pct"]-br["cagr_pct"],2)
    rep={"generated_at":datetime.now(timezone.utc).isoformat(),"period":{"start":args.start,"end":args.end},"coverage":{"historical_symbols":len(union),"price_symbols":len(mkt),"sec_symbols":len(fmap),"usable_symbols":len(usable)},"results":res,"benchmark":br,"curves":{x.name:x.curve for x in states},"trades":{x.name:x.trades for x in states}}
    op=Path(args.output);op.parent.mkdir(parents=True,exist_ok=True);op.write_text(json.dumps(rep,indent=2));mp=Path(args.markdown);mp.parent.mkdir(parents=True,exist_ok=True);mp.write_text(md(rep));print(md(rep),flush=True)

if __name__=="__main__":main()
