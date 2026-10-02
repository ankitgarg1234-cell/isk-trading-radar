#!/usr/bin/env python3
from __future__ import annotations
import argparse, bisect, copy, json, math, os, statistics, sys, threading, time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime, time as dt_time, timedelta, timezone
from io import StringIO
from pathlib import Path
from zoneinfo import ZoneInfo
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
# NYSE's published 2024-2026 early-close calendar (equities close at 13:00 ET).
# https://ir.theice.com/press/news-details/2023/NYSE-Group-Announces-2024-2025-and-2026-Holiday-and-Early-Closings-Calendar/default.aspx
EARLY_CLOSE_DATES = frozenset(date.fromisoformat(day) for day in (
    "2024-07-03", "2024-11-29", "2024-12-24", "2025-07-03", "2025-11-28", "2025-12-24",
    "2026-11-27", "2026-12-24",
))


def market_close_at(day):
    """Actual NYSE close for the staged 2024-2026 period, including DST."""
    return datetime.combine(day,dt_time(13 if day in EARLY_CLOSE_DATES else 16),tzinfo=ZoneInfo("America/New_York"))


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
            # SEC companyfacts lacks accepted-at times. Defer the entire
            # filing day rather than admit possibly after-close disclosures.
            if date.fromisoformat(str(r.get("filed"))[:10])>=d:continue
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

_ROW_DATE_CACHE = {}


def _rows_dates(data):
    rows = data.get("rows") or []
    cached = _ROW_DATE_CACHE.get(id(data))
    if cached is None or cached[0] is not data or cached[1] is not rows:
        cached = (data, rows, [r["date"] for r in rows])
        _ROW_DATE_CACHE[id(data)] = cached
    return rows, cached[2]


def split_factor_after(data, d):
    """Undo Yahoo's retrospective split normalization after a given date.

    The staged quote and dividend series use the final share unit. This factor
    reconstructs historical native units; future split metadata changes units
    only and is never passed to the signal as future event evidence.
    """
    factor = 1.0
    for event in data.get("splits") or []:
        if event["date"] > d.isoformat():
            numerator, denominator = sf(event.get("numerator")), sf(event.get("denominator"))
            if numerator and denominator:
                factor *= numerator / denominator
    return factor


def _scaled_row(row, factor):
    out = dict(row)
    for key in ("open", "high", "low", "close"):
        value = sf(row.get(key))
        out[key] = value * factor if value is not None else None
    out["volume"] = (sf(row.get("volume")) or 0.0) / factor
    return out


def row_before(data, d):
    """Latest quote in the share units actually traded on that row's date."""
    rows, dates = _rows_dates(data)
    index = bisect.bisect_right(dates, d.isoformat()) - 1
    if index < 0:
        return None
    row = rows[index]
    return _scaled_row(row, split_factor_after(data, date.fromisoformat(row["date"])))


def next_row(data, d):
    rows, dates = _rows_dates(data)
    index = bisect.bisect_right(dates, d.isoformat())
    if index >= len(rows):
        return None
    row = rows[index]
    return _scaled_row(row, split_factor_after(data, date.fromisoformat(row["date"])))


def price_asof(data, d):
    rows, dates = _rows_dates(data)
    index = bisect.bisect_right(dates, d.isoformat()) - 1
    if index < 0:
        return None
    value = sf(rows[index].get("close"))
    return value * split_factor_after(data, d) if value is not None else None


def hist_asof(data, d, n=270):
    """Past-only history expressed in the decision date's native share unit.

    Earlier splits are already present in cached OHLC. Apply only the inverse
    of normalization for splits *after* the decision, never adjust them twice.
    """
    rows, dates = _rows_dates(data)
    end = bisect.bisect_right(dates, d.isoformat())
    factor = split_factor_after(data, d)
    return [_scaled_row(r, factor) for r in rows[max(0, end - n):end]]

ETF={"Information Technology":"XLK","Communication Services":"XLC","Consumer Discretionary":"XLY","Consumer Staples":"XLP","Financials":"XLF","Health Care":"XLV","Industrials":"XLI","Energy":"XLE","Materials":"XLB","Real Estate":"XLRE","Utilities":"XLU"}

def analyse(sym,d,market,fmap,fdates,sectors,etfs):
    data=market.get(sym);raw=row_before(data,d) if data else None
    if not raw or raw["date"] != d.isoformat() or not raw.get("close") or float(raw["close"])<5:return None
    h=hist_asof(data,d)
    if len(h)<100:return None
    f=fmap.get(sym)
    if not f:return None
    fundamentals=fundamental(f,d,float(raw["close"]),sectors.get(sym))
    fd=fdates.get(sym,[]);recent=[x for x in fd if timedelta(0)<d-x<=timedelta(days=7)]
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
    entry_target:float|None=None
    entry_stretch_target:float|None=None
    entry_stop:float|None=None
    entry_horizon_days:int|None=None
    entry_plan_version:str|None=None
    original_shares:float=0.0
    profit_taken_shares:float=0.0
    profit_taken_stages:set=field(default_factory=set)
    entry_fees_remaining:float=0.0

    def __post_init__(self):
        if not self.original_shares:
            self.original_shares = self.shares

    def as_position(self):
        return {"shares":self.shares,"avg_cost":self.avg,"account":"Backtest",
                "whole_shares":True,"opened_at":datetime.combine(self.opened,dt_time(9,30),tzinfo=ZoneInfo("America/New_York")),
                "entry_target":self.entry_target,"entry_stretch_target":self.entry_stretch_target,
                "entry_stop":self.entry_stop,"entry_horizon_days":self.entry_horizon_days,
                "entry_plan_version":self.entry_plan_version,"original_shares":self.original_shares,
                "profit_taken_shares":self.profit_taken_shares,"profit_taken_stages":list(self.profit_taken_stages)}


@dataclass
class State:
    name:str;rr:float;core_only:bool;cash:float=STARTING;pos:dict=field(default_factory=dict);trades:list=field(default_factory=list);curve:list=field(default_factory=list);snap:dict=field(default_factory=dict);last:date|None=None
    pending:list=field(default_factory=list)
    rejections:list=field(default_factory=list)
    cash_events:list=field(default_factory=list)
    initial_cash:float|None=None
    harvest_dates:dict=field(default_factory=dict)
    cost_bps:float=field(default_factory=lambda:COST_BPS)

    def __post_init__(self):
        if self.initial_cash is None:
            self.initial_cash = self.cash

def fee(v,cost_bps=None):return abs(v)*(COST_BPS if cost_bps is None else cost_bps)/10000

def corp(st, market, d):
    """Book native-unit corporate actions once, before that session's fills."""
    if st.last is None:
        st.last = d
        return
    events = []
    for sym, position in list(st.pos.items()):
        data = market.get(sym) or {}
        for event in data.get("splits") or []:
            day = date.fromisoformat(event["date"])
            if max(st.last, position.opened) < day <= d:
                events.append((day, 0, sym, event))
        for event in data.get("dividends") or []:
            day = date.fromisoformat(event["date"])
            if max(st.last, position.opened) < day <= d:
                events.append((day, 1, sym, event))
    for day, kind, sym, event in sorted(events, key=lambda x:(x[0],x[1],x[2])):
        position = st.pos.get(sym)
        if position is None:
            continue
        if kind == 0:
            ratio = float(event["numerator"]) / float(event["denominator"])
            before = position.shares
            entitlement = before * ratio
            whole = math.floor(entitlement + 1e-9)
            remainder = max(0.0, entitlement - whole)
            position.shares = whole
            position.avg /= ratio
            position.original_shares *= ratio
            position.profit_taken_shares *= ratio
            for key in ("entry_target", "entry_stretch_target", "entry_stop"):
                value = getattr(position, key)
                if value is not None:
                    setattr(position, key, value / ratio)
            cash_in_lieu = 0.0
            cash_in_lieu_price = None
            if remainder > 1e-9:
                row = row_before(market[sym], day)
                if not row or row["date"] != day.isoformat() or not row.get("open"):
                    raise ValueError(f"Cannot value fractional split entitlement for {sym} on {day}")
                # Actual issuer cash-in-lieu schedules are unavailable. Value
                # fractional entitlements at this session's opening price.
                cash_in_lieu_price = float(row["open"])
                cash_in_lieu = remainder * cash_in_lieu_price
                st.cash += cash_in_lieu
                position.entry_fees_remaining *= whole / entitlement
            st.cash_events.append({"date":day.isoformat(),"symbol":sym,"kind":"SPLIT",
                                   "ratio":ratio,"shares_before":before,"shares_after":whole,
                                   "cash_in_lieu_shares":remainder,"cash_in_lieu_price":cash_in_lieu_price,
                                   "cash":cash_in_lieu})
            if whole == 0:
                st.pos.pop(sym)
        else:
            amount = float(event["amount"]) * split_factor_after(market[sym], day)
            payout = position.shares * amount
            st.cash += payout
            st.cash_events.append({"date":day.isoformat(),"symbol":sym,"kind":"DIVIDEND",
                                   "amount":amount,"shares":position.shares,"cash":payout})
    st.last = d

def equity(st,market,d):
    v=st.cash
    for s,p in st.pos.items():
        price=price_asof(market.get(s) or {},d)
        if price is not None:v+=p.shares*price
    return v

def do_sell(st,s,q,price,d,reason,*,signal_date=None,complete_stages=(),profit_stage=None):
    p=st.pos.get(s)
    if not p:return 0
    q=min(p.shares,math.floor(float(q)+1e-9))
    if q<=0:return 0
    gross=q*price;f=fee(gross,st.cost_bps);entry_fees=p.entry_fees_remaining*q/p.shares
    pnl=q*(price-p.avg)-f-entry_fees;st.cash+=gross-f
    st.trades.append({"date":d.isoformat(),"signal_date":signal_date.isoformat() if signal_date else d.isoformat(),
                      "symbol":s,"side":"SELL","shares":q,"price":price,"pnl":pnl,"gross":gross,"fee":f,
                      "allocated_entry_fees":entry_fees,"reason":reason,"lane":p.lane,"days":(d-p.opened).days,
                      "profit_stage":profit_stage})
    p.entry_fees_remaining-=entry_fees
    if profit_stage in {"BASE","STRETCH"}:
        p.profit_taken_shares+=q
    if profit_stage:
        p.profit_taken_stages.update(complete_stages or [profit_stage])
        st.harvest_dates[s]=d
    p.shares-=q
    if p.shares<=1e-9:st.pos.pop(s,None)
    return q

def do_buy(st,s,q,price,d,reason,lane,rank,*,analysis=None,signal_date=None):
    q=int(q)
    if q<=0:return 0
    maxq=math.floor(st.cash/(price*(1+st.cost_bps/10000)))
    q=min(q,maxq)
    if q<=0:return 0
    gross=q*price;f=fee(gross,st.cost_bps);st.cash-=gross+f
    if s in st.pos:
        p=st.pos[s];tot=p.shares+q;p.avg=(p.avg*p.shares+price*q)/tot;p.shares=tot
        p.original_shares+=q;p.entry_fees_remaining+=f
    else:
        analysis=analysis or {};levels=analysis.get("levels") or {};target_plan=analysis.get("target_plan") or {}
        st.pos[s]=Pos(q,price,d,lane,rank,entry_target=sf(levels.get("target")),
                      entry_stretch_target=sf(target_plan.get("stretch_target") or levels.get("target")),
                      entry_stop=sf(levels.get("stop")),
                      entry_horizon_days=int((analysis.get("holding_horizon") or {}).get("max_days") or 0) or None,
                      entry_plan_version=analysis.get("scoring_version") or ae.SCORING_VERSION,
                      original_shares=q,entry_fees_remaining=f)
    analysis=analysis or {};levels=analysis.get("levels") or {}
    stop,target=sf(levels.get("stop")),sf(levels.get("target"))
    fill_rr=(target-price)/(price-stop) if stop is not None and target is not None and price>stop else None
    st.trades.append({"date":d.isoformat(),"signal_date":signal_date.isoformat() if signal_date else d.isoformat(),
                      "symbol":s,"side":"BUY","shares":q,"price":price,"gross":gross,"fee":f,
                      "reason":reason,"lane":lane,"rank":rank,
                      "entry_stop":stop,"entry_target":target,"fill_risk_reward":fill_rr,
                      "risk_amount":q*(price-stop) if stop is not None else None,
                      "frozen_position_stop":st.pos[s].entry_stop,"frozen_position_target":st.pos[s].entry_target})
    return q

def reliable(a):
    return str(a.get("fundamental_confidence") or "low") in ("medium","high") and float((a.get("fundamentals") or {}).get("marketCap") or 0)>0 and float((a.get("technicals") or {}).get("avg_dollar_volume_20") or 0)>0

def _reject(st, order, day, reason):
    st.rejections.append({"date":day.isoformat(),"signal_date":order["signal_date"].isoformat(),
                          "symbol":order["symbol"],"side":order["side"],"shares":order["shares"],"reason":reason})


def _split_order(order, market, fill_day):
    """Translate a pending signal's quantity/anchors to the fill share unit."""
    out = copy.deepcopy(order)
    ratio = 1.0
    for event in (market.get(order["symbol"]) or {}).get("splits") or []:
        if order["signal_date"].isoformat() < event["date"] <= fill_day.isoformat():
            ratio *= float(event["numerator"]) / float(event["denominator"])
    if ratio != 1:
        out["shares"] = math.floor(float(out["shares"]) * ratio + 1e-9)
        analysis = out.get("analysis") or {}
        if analysis.get("price"):
            analysis["price"] /= ratio
        for key, value in list((analysis.get("levels") or {}).items()):
            if isinstance(value, (int, float)):
                analysis["levels"][key] = value / ratio
        for key in ("base_target", "stretch_target"):
            value = (analysis.get("target_plan") or {}).get(key)
            if value is not None:
                analysis["target_plan"][key] = value / ratio
    return out


def advance_state(st, market, d):
    """Execute past pending orders at their own session, never at signal time."""
    if st.last is not None and d < st.last:
        raise ValueError("Replay clock cannot move backwards")
    due = sorted((order for order in st.pending if order["execution_date"] <= d),
                 key=lambda order:(order["execution_date"],0 if order["side"]=="SELL" else 1,order["sequence"]))
    st.pending = [order for order in st.pending if order["execution_date"] > d]
    for execution_day in sorted({order["execution_date"] for order in due}):
        corp(st, market, execution_day)
        for original in (order for order in due if order["execution_date"] == execution_day):
            order = _split_order(original, market, execution_day)
            symbol = order["symbol"]
            row = row_before(market.get(symbol) or {}, execution_day)
            if not row or row["date"] != execution_day.isoformat() or not sf(row.get("open")) or float(row["open"]) <= 0:
                _reject(st, order, execution_day, "Missing executable session open")
                continue
            price = float(row["open"])
            quantity = math.floor(float(order["shares"]) + 1e-9)
            if order["side"] == "SELL":
                position = st.pos.get(symbol)
                if position is None:
                    _reject(st, order, execution_day, "Position already closed")
                    continue
                stage = order.get("profit_stage")
                if stage:
                    quantity = min(quantity, max(0, math.floor(position.shares - 1)))
                    if price * (1 - st.cost_bps / 10000) <= position.avg + position.entry_fees_remaining / position.shares:
                        _reject(st, order, execution_day, "Profit-taking gap would realize a net loss")
                        continue
                filled = do_sell(st, symbol, quantity, price, execution_day, order["reason"],
                                 signal_date=order["signal_date"],complete_stages=order.get("complete_stages") or (),
                                 profit_stage=stage)
            else:
                if st.harvest_dates.get(symbol) == execution_day:
                    _reject(st, order, execution_day, "Cannot re-add on the same session as a profit harvest")
                    continue
                analysis = order.get("analysis") or {}
                levels = analysis.get("levels") or {}
                stop, target = sf(levels.get("stop")), sf(levels.get("target"))
                if order.get("revalidate_rr", True):
                    if stop is None or target is None or not 0 < stop < price < target:
                        _reject(st, order, execution_day, "Opening gap invalidates signal stop/target")
                        continue
                    if (target - price) / (price - stop) + 1e-9 < st.rr:
                        _reject(st, order, execution_day, "Opening R/R below entry floor")
                        continue
                position = st.pos.get(symbol)
                held = position.shares if position else 0
                if order.get("risk_budget") is not None:
                    if stop is None or price <= stop:
                        _reject(st, order, execution_day, "Invalid stop for risk ceiling")
                        continue
                    remaining = max(0.0, float(order["risk_budget"]) - held * (price - stop))
                    quantity = min(quantity, math.floor(remaining / (price - stop) + 1e-9))
                if order.get("position_cap") is not None:
                    remaining = max(0.0, float(order["position_cap"]) - held * price)
                    quantity = min(quantity, math.floor(remaining / price + 1e-9))
                quantity = min(quantity, math.floor((st.cash + 1e-9) / (price * (1 + st.cost_bps / 10000))))
                filled = do_buy(st, symbol, quantity, price, execution_day, order["reason"],
                                order.get("lane") or analysis.get("lane") or "CORE_QUALITY",float(order.get("rank") or 0),
                                analysis=analysis,signal_date=order["signal_date"])
                if filled:
                    st.trades[-1]["portfolio_equity_at_signal"]=order.get("portfolio_equity_at_signal")
                    st.trades[-1]["risk_budget_at_signal"]=order.get("risk_budget")
                    st.trades[-1]["position_cap_at_signal"]=order.get("position_cap")
            if not filled:
                _reject(st, order, execution_day, "No whole shares fit the execution ceilings")
    corp(st, market, d)


def _queue(st, market, day, order):
    next_session = next_row(market.get(order["symbol"]) or {}, day)
    order = dict(order, signal_date=day, sequence=len(st.pending))
    if not next_session:
        _reject(st, order, day, "No later session in price cache; signal unfilled")
        return False
    order["execution_date"] = date.fromisoformat(next_session["date"])
    st.pending.append(order)
    return True


def run_state(st,d,base,members,market,*,allocation_policy=None,profit_taking=True):
    """Evaluate close signals and queue fixed quantities for the next open.

    allocation_policy(st, day, ranked_orders, analyses, market) may replace the
    baseline sizer. It returns dictionaries with symbol/shares/analysis/reason
    and optional absolute risk_budget and position_cap dollar ceilings. These
    are research-only policy inputs; this function cannot alter live settings.
    """
    advance_state(st,market,d)
    analyses={}
    decision_at=market_close_at(d)
    for s in sorted(set(members)|set(st.pos)):
        if s not in base:continue
        a=copy.deepcopy(base[s])
        if s in st.snap:a["previous_snapshot"]=st.snap[s]
        position=st.pos.get(s)
        act,why=position_action(a,float(a["price"]),position.as_position() if position else None,decision_at=decision_at)
        a["action"]=act;a["action_reason"]=why
        st.snap[s]={"breakdown":copy.deepcopy(a.get("breakdown") or {}),"deterministic_score":a.get("deterministic_score"),"action":act}
        analyses[s]=a
    selling=set()
    for symbol,position in sorted(st.pos.items()):
        analysis=analyses.get(symbol)
        if not analysis:continue
        action=analysis["action"]
        order=None
        sessions=sum(position.opened.isoformat()<row["date"]<=d.isoformat() for row in market.get(symbol,{}).get("rows") or [])
        if position.lane=="EXPLOSIVE" and analysis.get("lane")!="CORE_QUALITY" and sessions>=20:
            order={"shares":position.shares,"reason":"EXPLOSIVE TIME STOP"}
        elif action=="EXIT":
            order={"shares":position.shares,"reason":"THESIS EXIT"}
        elif action=="REDUCE" or (action=="TAKE PARTIAL PROFIT" and profit_taking):
            plan=position_action_plan(action,analysis,float(analysis["price"]),position.as_position())
            if plan and float(plan.get("suggested_shares") or 0)>0:
                stage=analysis.get("profit_take_stage") if action=="TAKE PARTIAL PROFIT" else None
                order={"shares":plan["suggested_shares"],"reason":action,"profit_stage":stage,
                       "complete_stages":analysis.get("profit_take_complete_stages") or ([stage] if stage else [])}
        if order:
            order.update(symbol=symbol,side="SELL",analysis=analysis)
            if _queue(st,market,d,order):selling.add(symbol)
    old=pe.MIN_ENTRY_RISK_REWARD;pe.MIN_ENTRY_RISK_REWARD=st.rr
    try:
        candidates={s:a for s,a in analyses.items() if s in members or s in st.pos}
        if st.core_only:candidates={s:a for s,a in candidates.items() if s in st.pos or a.get("lane")=="CORE_QUALITY"}
        plan=build_optimizer_plan(candidates,set(st.pos),profile="MEDIUM",visible_limit=20,shortlist_limit=20)
    finally:pe.MIN_ENTRY_RISK_REWARD=old
    orders=[(row,"NEW") for row in plan.get("selected_new") or []]
    orders.extend((row,"ADD") for row in plan.get("visible") or [] if row.get("owned") and row.get("optimizer_action")=="ADD" and float((row.get("analysis") or {}).get("risk_reward") or 0)>=st.rr)
    blocked=selling|{symbol for symbol,day in st.harvest_dates.items() if day==d}|{order["symbol"] for order in st.pending if order["side"]=="BUY"}
    orders=[(row,kind) for row,kind in orders if row["symbol"] not in blocked]
    orders.sort(key=lambda item:(-float(item[0].get("rank_score") or 0),item[0]["symbol"]))
    if allocation_policy:
        sized=allocation_policy(st,d,orders,analyses,market)
    else:
        sized=[];available=st.cash;total=equity(st,market,d)
        for row,kind in orders:
            symbol=row["symbol"];analysis=copy.deepcopy(row["analysis"]);price=float(analysis["price"])
            position=st.pos.get(symbol);existing=position.shares*price if position else 0
            sizing=suggested_position_size(analysis,cash=available,reserve_cash=0,portfolio_value=total,
                                          profile="MEDIUM",fx_rate_to_base=1,existing_value=existing,whole_shares=True)
            shares=min(int(sizing.get("shares") or 0),math.floor((available+1e-9)/(price*(1+st.cost_bps/10000))))
            if shares>0:
                sized.append({"symbol":symbol,"shares":shares,"analysis":analysis,
                              "reason":kind+" "+str(row.get("entry_signal") or row.get("optimizer_action")),
                              "lane":analysis.get("lane"),"rank":float(row.get("rank_score") or 0),
                              "risk_budget":total*pe.RISK_PROFILES["MEDIUM"]["risk_per_trade_pct"]/100,
                              "position_cap":total*float(sizing.get("hard_position_cap_pct") or 15)/100})
                available-=shares*price*(1+st.cost_bps/10000)
    for order in sized:
        if order["symbol"] in blocked or float(order.get("shares") or 0)<=0:continue
        _queue(st,market,d,dict(order,side="BUY",analysis=copy.deepcopy(order["analysis"]),portfolio_equity_at_signal=equity(st,market,d)))
    total=equity(st,market,d)
    values=[position.shares*(price_asof(market.get(symbol) or {},d) or 0) for symbol,position in st.pos.items()]
    stop_risk=sum(position.shares*max(0.0,(price_asof(market.get(symbol) or {},d) or 0)-float(position.entry_stop or 0))
                  for symbol,position in st.pos.items() if position.entry_stop is not None)
    st.curve.append({"date":d.isoformat(),"equity":round(total,2),"cash":round(st.cash,2),"positions":len(st.pos),
                     "largest_position_pct":max(values,default=0.0)/total*100 if total else 0.0,
                     "modeled_stop_risk_pct":stop_risk/total*100 if total else 0.0})

def stat(st):
    c=st.curve;endv=float(c[-1]["equity"]);yrs=(date.fromisoformat(c[-1]["date"])-date.fromisoformat(c[0]["date"])).days/365.25
    ret=endv/st.initial_cash-1;cagr=(endv/st.initial_cash)**(1/max(yrs,1/365.25))-1;peak=st.initial_cash;dd=0;by=defaultdict(list)
    for r in c:
        e=float(r["equity"]);peak=max(peak,e);dd=min(dd,e/peak-1);by[date.fromisoformat(r["date"]).year].append(r)
    prev=st.initial_cash;annual={}
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
    a += ["","## Limitations","- Point-in-time S&P 500 membership reconstructed from the public constituent/change tables.","- SEC companyfacts has no accepted-at timestamp: facts and filing-catalyst proxies are deferred beyond filing day.","- General historical news, analyst consensus and strategic-capital evidence are unavailable; SEC earnings filings are the only catalyst proxy.","- Weekly close signals execute at their actual next session open. Signal-close whole-share sizing, 15% hard cap and 10 bps transaction costs are applied; opening R/R and execution ceilings are revalidated.","- Historical native share prices/dividends are reconstructed from split-normalized cache and share quantities adjust once on split dates; fractional entitlements assume cash-in-lieu at split-session open.","- Current Model requires R/R >= 2.0x for buys/adds. Falling below 2x later is not itself a sell trigger.","- Historical simulation is not a guarantee of future results."]
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
        for st in states:advance_state(st,mkt,d)
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
