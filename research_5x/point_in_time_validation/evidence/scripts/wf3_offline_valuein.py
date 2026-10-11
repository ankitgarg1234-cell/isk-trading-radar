#!/usr/bin/env python3
from __future__ import annotations
import argparse,copy,gzip,hashlib,json,math,sys
from collections import defaultdict
from datetime import date,datetime,timedelta,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"));sys.path.insert(0,str(ROOT))
import walkforward_backtest as wf
from app.analysis_engine import score_bundle

PRICE_PATH=ROOT/"backtests"/"staged"/"wf3_prices.json.gz"
FUND_PATH=ROOT/"backtests"/"staged"/"wf3_valuein_fundamentals.json.gz"

def load_gz(path):
    with gzip.open(path,"rt",encoding="utf-8") as f:return json.load(f)

def d(s):
    try:return date.fromisoformat(str(s)[:10]) if s else None
    except:return None

def fv(x):
    try:
        if x is None:return None
        y=float(x)
        return y if math.isfinite(y) else None
    except:return None

class PITFundamentals:
    def __init__(self,raw):
        self.by=defaultdict(lambda:defaultdict(list))
        self.filing_dates=defaultdict(set)
        for sym,rows in raw["facts"].items():
            for r in rows:
                rr=dict(r)
                rr["_filing_date"]=d(rr.get("filing_date"))
                rr["_period_start"]=d(rr.get("period_start"))
                rr["_period_end"]=d(rr.get("period_end"))
                rr["_span"]=rr.get("period_span_days")
                if rr["_filing_date"]:
                    self.by[sym][rr["standard_concept"]].append(rr)
                    self.filing_dates[sym].add(rr["_filing_date"])
        for sym in self.by:
            for c in self.by[sym]:
                self.by[sym][c].sort(key=lambda r:(r["_filing_date"],r["_period_end"] or date.min,str(r.get("accepted_at") or "")))

    def eligible(self,sym,concept,asof):
        return [r for r in self.by.get(sym,{}).get(concept,[]) if r["_filing_date"]<=asof]

    @staticmethod
    def _latest_per_period(cands):
        best={}
        for r,val,quality in cands:
            pe=r["_period_end"]
            if not pe:continue
            rank=(r["_filing_date"],str(r.get("accepted_at") or ""),quality)
            if pe not in best or rank>best[pe][0]:best[pe]=(rank,val,r)
        return [(k,v[1],v[2]) for k,v in sorted(best.items())]

    def annual(self,sym,concept,asof):
        c=[]
        for r in self.eligible(sym,concept,asof):
            span=fv(r.get("_span"));form=str(r.get("form_type") or "")
            if not form.startswith("10-K"):continue
            if span is not None and not 300<=span<=430:continue
            val=fv(r.get("numeric_value"))
            if val is not None:c.append((r,val,1))
        return self._latest_per_period(c)

    def quarter(self,sym,concept,asof):
        c=[]
        for r in self.eligible(sym,concept,asof):
            form=str(r.get("form_type") or "")
            if not form.startswith("10-Q"):continue
            span=fv(r.get("_span"));derived=fv(r.get("derived_quarterly_value"));raw=fv(r.get("numeric_value"))
            val=None;quality=0
            if span is not None and 60<=span<=125 and raw is not None:
                val=raw;quality=3
            elif derived is not None:
                val=derived;quality=2
            elif str(r.get("fiscal_period") or "")=="Q1" and raw is not None:
                val=raw;quality=1
            if val is not None:c.append((r,val,quality))
        return self._latest_per_period(c)

    def instant(self,sym,concept,asof):
        rows=self.eligible(sym,concept,asof)
        usable=[r for r in rows if fv(r.get("numeric_value")) is not None and r["_period_end"]]
        if not usable:return None
        r=max(usable,key=lambda z:(z["_period_end"],z["_filing_date"],str(z.get("accepted_at") or "")))
        return fv(r.get("numeric_value"))

    @staticmethod
    def growth(series):
        if len(series)<2:return None
        a=series[-1][1];b=series[-2][1]
        return None if b in (None,0) else a/b-1

    @staticmethod
    def yoy(series):
        if len(series)<2:return None
        pe,val,_=series[-1];cands=[]
        for x in series[:-1]:
            days=(pe-x[0]).days
            if 300<=days<=430:cands.append((abs(days-365),x))
        if not cands:return None
        _,prior=min(cands,key=lambda x:x[0])
        return None if prior[1] in (None,0) else val/prior[1]-1

    @staticmethod
    def same_period_value(series,period):
        for pe,val,_ in reversed(series):
            if pe==period:return val
        return None

    def asof(self,sym,asof,price):
        ar=self.annual(sym,"TotalRevenue",asof);ani=self.annual(sym,"NetIncome",asof)
        qr=self.quarter(sym,"TotalRevenue",asof);qni=self.quarter(sym,"NetIncome",asof)
        qgp=self.quarter(sym,"GrossProfit",asof);qoi=self.quarter(sym,"OperatingIncome",asof)
        agp=self.annual(sym,"GrossProfit",asof);aoi=self.annual(sym,"OperatingIncome",asof)
        equity=self.instant(sym,"StockholdersEquity",asof)
        debt=self.instant(sym,"TotalDebt",asof)
        shares=self.instant(sym,"CommonSharesOutstanding",asof)
        revenue_growth=self.growth(ar);earnings_growth=self.growth(ani);qrg=self.yoy(qr)
        gm=om=None
        if qr:
            pe,rev,_=qr[-1]
            gp=self.same_period_value(qgp,pe);oi=self.same_period_value(qoi,pe)
            gm=gp/rev if gp is not None and rev else None
            om=oi/rev if oi is not None and rev else None
        if gm is None and ar:
            pe,rev,_=ar[-1];gp=self.same_period_value(agp,pe)
            gm=gp/rev if gp is not None and rev else None
        if om is None and ar:
            pe,rev,_=ar[-1];oi=self.same_period_value(aoi,pe)
            om=oi/rev if oi is not None and rev else None
        ni_ttm=None
        if len(qni)>=4:
            latest4=qni[-4:]
            if (latest4[-1][0]-latest4[0][0]).days<=380:ni_ttm=sum(x[1] for x in latest4)
        if ni_ttm is None and ani:ni_ttm=ani[-1][1]
        roe=ni_ttm/equity if ni_ttm is not None and equity not in (None,0) else None
        de=debt/equity*100 if debt is not None and equity not in (None,0) else None
        mcap=shares*price if shares not in (None,0) and price else None
        return {"revenueGrowth":revenue_growth,"earningsGrowth":earnings_growth,
                "quarterlyRevenueGrowth":qrg,"grossMargins":gm,"operatingMargins":om,
                "returnOnEquity":roe,"debtToEquity":de,"sharesOutstanding":shares,
                "marketCap":mcap,"totalRevenue":ar[-1][1] if ar else None,
                "_status":"available","_source":"Valuein PIT fundamentals"}

    def filing_news(self,sym,asof):
        recent=[x for x in self.filing_dates.get(sym,set()) if timedelta(0)<=asof-x<=timedelta(days=7)]
        if not recent:return []
        fd=max(recent)
        return [{"title":"SEC earnings filing","publisher":"SEC EDGAR",
                 "providerPublishTime":datetime.combine(fd,datetime.min.time(),tzinfo=timezone.utc).timestamp()}]

def sector_bundle(sector,etfs,asof):
    ticker=wf.ETF.get(sector)
    if not ticker or ticker not in etfs:return None
    h=wf.hist_asof(etfs[ticker],asof,180)
    if not h:return None
    return {"symbol":ticker,"price":h[-1]["close"],"history":h}

def analyse(sym,asof,market,store,sectors,etfs):
    data=market.get(sym);raw=wf.row_before(data or {},asof)
    if not raw or not raw.get("close") or float(raw["close"])<5:return None
    h=wf.hist_asof(data,asof,270)
    if len(h)<100:return None
    price=float(raw["close"]);fund=store.asof(sym,asof,price)
    rev=[]
    for x in data.get("splits") or []:
        sd=d(x.get("date"))
        if sd and asof-timedelta(days=366)<=sd<=asof and float(x.get("numerator") or 0)<float(x.get("denominator") or 0):
            rev.append({"date":x["date"],"ratio":x.get("ratio")})
    b={"symbol":sym,"price":price,"previous_close":h[-2]["close"] if len(h)>1 else price,
       "history":h,"fundamentals":fund,"news":store.filing_news(sym,asof),
       "recent_reverse_splits":rev,"strategic_capital":{"events":[]},
       "sector_benchmark":sector_bundle(sectors.get(sym),etfs,asof)}
    try:
        out=score_bundle(b);out["symbol"]=sym;out["price"]=price;return out
    except Exception:return None

def validate(st,analyses):
    if st.cash<-0.01:raise AssertionError(f"negative cash {st.cash}")
    for s,p in st.pos.items():
        if abs(p.shares-round(p.shares))>1e-8:raise AssertionError(f"fractional shares {s}")

def daily_curve(st,market,benchmark,start,end):
    trades=defaultdict(list)
    for t in st.trades:trades[t["date"]].append(t)
    held={};cash=wf.STARTING;curve=[];last=None
    for r in benchmark["rows"]:
        ds=r["date"];dd=d(ds)
        if not dd or not(start<=dd<=end):continue
        if last is not None:
            for sym in list(held):
                data=market.get(sym) or {}
                # Cached Yahoo OHLC is already split-adjusted; do not
                # multiply replay shares again for split events.
                for dv in data.get("dividends") or []:
                    x=d(dv.get("date"))
                    if x and last<x<=dd:cash+=held[sym]*float(dv["amount"])
        for t in trades.get(ds,[]):
            gross=float(t["shares"])*float(t["price"]);fee=wf.fee(gross)
            if t["side"]=="BUY":
                cash-=gross+fee;held[t["symbol"]]=held.get(t["symbol"],0)+float(t["shares"])
            else:
                cash+=gross-fee;held[t["symbol"]]=max(0,held.get(t["symbol"],0)-float(t["shares"]))
                if held[t["symbol"]]<=1e-9:held.pop(t["symbol"],None)
        eq=cash
        for sym,qty in held.items():
            rr=wf.row_before(market.get(sym) or {},dd)
            if rr and rr.get("close"):eq+=qty*float(rr["close"])
        curve.append({"date":ds,"equity":eq,"cash":cash})
        last=dd
    return curve

def stat(name,st,curve):
    first=wf.STARTING;endv=float(curve[-1]["equity"]);days=(d(curve[-1]["date"])-d(curve[0]["date"])).days;yrs=max(days/365.25,1/365.25)
    ret=endv/first-1;cagr=(endv/first)**(1/yrs)-1 if endv>0 else -1
    peak=0;dd=0;by=defaultdict(list)
    for r in curve:
        e=float(r["equity"]);peak=max(peak,e);dd=min(dd,e/peak-1 if peak else 0);by[d(r["date"]).year].append(e)
    prev=first;annual={}
    for y in sorted(by):
        v=by[y][-1];annual[str(y)]=round((v/prev-1)*100,2);prev=v
    sells=[t for t in st.trades if t["side"]=="SELL"];wins=[t for t in sells if float(t.get("pnl") or 0)>0]
    return {"name":name,"end_value":round(endv,2),"total_return_pct":round(ret*100,2),"cagr_pct":round(cagr*100,2),
            "max_drawdown_pct":round(dd*100,2),"annual_returns_pct":annual,"trade_count":len(st.trades),
            "sell_count":len(sells),"win_rate_pct":round(len(wins)/len(sells)*100,2) if sells else None,
            "average_holding_days":round(sum(float(t.get("days") or 0) for t in sells)/len(sells),1) if sells else None,
            "ending_cash":round(st.cash,2),"open_positions":len(st.pos)}

def run(prices,funds,smoke=False):
    market=prices["market"];etfs=prices["sector_etfs"];sectors=prices["membership"]["sectors"]
    pref={d(k):v for k,v in prices["prefilters"].items()};weeks=sorted(x for x in pref if x)
    if smoke:weeks=weeks[:12]
    store=PITFundamentals(funds)
    states=[wf.State("Current model (R/R >=2x)",2.0,False),
            wf.State("No 2x R/R floor",0.0,False),
            wf.State("Core-only (R/R >=2x)",2.0,True)]
    for i,day in enumerate(weeks,1):
        shortlist=pref[day][:20] if smoke else pref[day]
        held=set().union(*(set(x.pos) for x in states));base={}
        for sym in set(shortlist)|held:
            a=analyse(sym,day,market,store,sectors,etfs)
            if a:base[sym]=a
        for st in states:
            wf.run_state(st,day,base,set(shortlist),market);validate(st,base)
        if i%10==0 or i==len(weeks):
            print("WF3_OFFLINE",day,i,"/",len(weeks),[(s.name,round(wf.equity(s,market,day))) for s in states],flush=True)
    return weeks,states

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--smoke",action="store_true")
    ap.add_argument("--output",default="backtests/results/walkforward_2024_2026_valuein.json")
    ap.add_argument("--markdown",default="backtests/results/walkforward_2024_2026_valuein.md")
    args=ap.parse_args();prices=load_gz(PRICE_PATH);funds=load_gz(FUND_PATH)
    weeks,states=run(prices,funds,args.smoke)
    if args.smoke:
        print("WF3_SMOKE_PASS",sum(len(s.trades) for s in states),flush=True);return
    benchmark=prices["benchmark"];results=[];curves={}
    for st in states:
        curve=daily_curve(st,prices["market"],benchmark,weeks[0],weeks[-1]);curves[st.name]=curve;results.append(stat(st.name,st,curve))
    br=wf.bench(benchmark,weeks[0],weeks[-1])
    for r in results:
        r["alpha_vs_benchmark_total_pct"]=round(r["total_return_pct"]-br["total_return_pct"],2)
        r["cagr_spread_vs_benchmark_pct"]=round(r["cagr_pct"]-br["cagr_pct"],2)
    rep={"version":"wf3-valuein-offline-v1","period":{"start":weeks[0].isoformat(),"end":weeks[-1].isoformat()},
         "methodology":{"decision_frequency":"weekly close","execution":"next session open","starting_capital":wf.STARTING,
                        "transaction_cost_bps":wf.COST_BPS,"whole_shares":True,"max_position_pct":15,
                        "fundamentals":"Valuein PIT sample filtered by filing_date","price_data":"cached Yahoo daily history",
                        "min_entry_rr":2.0},
         "coverage":{"price":prices["coverage"],"fundamentals":{k:v for k,v in funds["meta"].items() if k!="coverage"}},
         "results":results,"benchmark":br,"trades":{s.name:s.trades for s in states},"daily_curves":curves}
    core={"period":rep["period"],"results":results,"benchmark":br,"trades":rep["trades"]}
    rep["deterministic_hash"]=hashlib.sha256(json.dumps(core,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(rep,indent=2))
    lines=["# 2024–2026 Point-in-Time Walk-Forward Backtest","",
           f"Period: {rep['period']['start']} to {rep['period']['end']}  ",
           f"Starting capital: USD {wf.STARTING:,.0f}  ",
           f"Deterministic run hash: {rep['deterministic_hash']}","",
           "| Variant | End value | Total return | CAGR | Max DD | Trades | Win rate | Alpha vs S&P |",
           "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in results:
        wr="—" if r["win_rate_pct"] is None else f"{r['win_rate_pct']:.1f}%"
        lines.append(f"| {r['name']} | USD {r['end_value']:,.0f} | {r['total_return_pct']:+.1f}% | {r['cagr_pct']:+.1f}% | {r['max_drawdown_pct']:.1f}% | {r['trade_count']} | {wr} | {r['alpha_vs_benchmark_total_pct']:+.1f} pp |")
    lines.append(f"| {br['name']} | USD {br['end_value']:,.0f} | {br['total_return_pct']:+.1f}% | {br['cagr_pct']:+.1f}% | {br['max_drawdown_pct']:.1f}% | — | — | — |")
    years=sorted(br["annual_returns_pct"]);lines+=["","## Annual returns","","| Variant | "+" | ".join(years)+" |","|---|"+"|".join(["---:"]*len(years))+"|"]
    for r in results+[br]:lines.append("| "+r["name"]+" | "+" | ".join(f"{r.get('annual_returns_pct',{}).get(y,0):+.1f}%" for y in years)+" |")
    lines+=["","## Data / integrity notes",
            f"- Historical price coverage: {prices['coverage']['price_pct']:.2f}% of the reconstructed 2024–2026 S&P universe.",
            f"- PIT fundamental coverage: {funds['meta']['usable_pct']:.2f}% of scanner candidate symbols.",
            "- Fundamental facts are admitted only when filing_date <= decision date; no current analyst consensus or current fundamentals are backfilled into historical dates.",
            "- Historical general-news and strategic-capital archives are omitted; 10-K/10-Q filing dates serve only as a conservative earnings-catalyst proxy.",
            "- The full historical S&P universe is cheap-screened weekly; up to 80 scanner-style candidates plus current holdings receive deep analysis.",
            "- Signals are generated at weekly close and orders execute at the next available session open.",
            "- Whole shares, current score-based sizing, 15% hard position cap, 10 bps transaction costs, Core/Explosive lane gates and R/R >=2x buy/add floor are applied.",
            "- Existing holdings are not sold merely because R/R later falls below 2x.",
            "- Sector ETF mapping uses the cached sector classification available in the historical-universe build; sector reclassifications are a minor residual limitation.",
            "- Historical simulation is not a guarantee of future performance."]
    Path(args.markdown).write_text("\n".join(lines)+"\n")
    print("WF3_RESULT_JSON="+json.dumps({"results":results,"benchmark":br,"hash":rep["deterministic_hash"]},separators=(",",":")),flush=True)

if __name__=="__main__":main()
