#!/usr/bin/env python3
"""Sector-first 2022-2026 backtest of the 2026-10-08 user rule specification.

Independent stock engine: no SEC fundamental gate, no global Top-20,
no 75/25 sleeves. Daily SPY+sector state; monthly ranks; 5-day stop lockout.
Signals after close, trades next open. Prior-close ATR stops enforced intraday.
"""
import bisect, json, math, statistics
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests

import adaptive_entry_policy_backtest as base
import spy_sector_hierarchy_backtest as hist

ROOT=Path(__file__).resolve().parents[1]
OUTJ=ROOT/"backtests/results/sector_first_explicit_2022_2026.json"
OUTM=ROOT/"backtests/results/sector_first_explicit_2022_2026.md"
START=date(2022,1,3)
END=date(2026,9,30)
SECTORS=hist.SECTOR_ETFS
BPS=0.0007

def ema_close(close,window):
    """SMA-seeded continuous close-price EMA with no pre-history lookahead."""
    arr=close.to_numpy(dtype=float)
    out=np.full(len(arr),np.nan)
    a=2/(window+1)
    if len(arr)>=window and np.isfinite(arr[:window]).all():
        out[window-1]=arr[:window].mean()
        for i in range(window,len(arr)):
            out[i]=a*arr[i]+(1-a)*out[i-1] if np.isfinite(arr[i]) else np.nan
    return pd.Series(out,index=close.index)

def features(raw):
    """Output keyed by historical trading date, with no future-return features."""
    mk=base.prepare_market(raw)
    if not mk: return None
    df=pd.DataFrame(mk["rows"]).set_index("date").sort_index()
    if df.index.has_duplicates: raise RuntimeError("duplicate dates in adjusted market input")
    close=df["close"].astype(float)
    tr=df["tr"].astype(float)
    daily=close.pct_change(fill_method=None)
    df["ema50"]=ema_close(close,50)
    df["ema200"]=ema_close(close,200)
    for n in (63,126,252):
        df[f"r{n}"]=tr/tr.shift(n)-1
        df[f"sigma{n}"]=daily.rolling(n,min_periods=n).std(ddof=1)*math.sqrt(252)
    df["score"]=0.5*df["r63"]/df["sigma63"]+0.3*df["r126"]/df["sigma126"]+0.2*df["r252"]/df["sigma252"]
    df["sector_momentum"]=(df["r63"]+df["r126"]+df["r252"])/3
    df["px63"]=close/close.shift(63)-1
    df["r5"]=tr/tr.shift(5)-1
    df["stock_ok"]=(close>df["ema50"])&(close>df["ema200"])&np.isfinite(df["score"])
    return df

def close_level_state(row):
    return bool(row is not None and np.isfinite(row["ema200"]) and row["close"]>row["ema200"])

def sector_allocation(spy_bull, sector_rows):
    """Only confirmed BULL sectors, then max two, fully deterministic.
    Single-sector 50% boundary follows sector permission (>50%).
    In BEAR with >=2 sectors use 50% across Top-2 at 70/30 or 50/50.
    Five-day sector momentum negative reduces single BEAR allocation to 40%.
    """
    eligible=[r for r in sector_rows if r["bull"] and (spy_bull or r["relative63"]>0)]
    eligible.sort(key=lambda x:(-x["momentum"],x["sector"]))
    selected=eligible[:2]
    if not selected:return {}
    if len(selected)==1:
        r=selected[0]
        if spy_bull:
            equity=0.90 if r["breadth"]>0.70 else 0.70
        else:
            equity=0.50 if r["breadth"]>=0.60 and r["r5"]>=0 else 0.40
        return {r["sector"]:equity}
    first,second=selected
    # The user-defined ratio is meaningful only for strictly positive
    # numerator and denominator.  Negative momentum does not cancel ETF/
    # breadth permission; default to the conservative 50/50 split.
    ratio=(first["momentum"]/second["momentum"]
           if first["momentum"]>0 and second["momentum"]>0 else None)
    split=(0.7,0.3) if ratio is not None and ratio>=1.5 else (0.5,0.5)
    equity=1.0 if spy_bull else 0.5
    return {first["sector"]:equity*split[0],second["sector"]:equity*split[1]}

def intraday_stop_fill(open_price, low_price, known_stop):
    """Previous day's stop, gap fill at open, otherwise stop (before trading costs)."""
    if known_stop is None:return None
    if not all(np.isfinite(v) and v>0 for v in (open_price,low_price,known_stop)):
        raise RuntimeError("invalid intraday OHLC/stop")
    if open_price<=known_stop:
        return float(open_price)
    if low_price<=known_stop:
        return float(known_stop)
    return None

def lockout_allows_signal(signal_index, stopped_index):
    """Five full sessions (i+1,...,i+5); signals at i+6 or later."""
    return stopped_index is None or signal_index>=stopped_index+6

class Portfolio:
    def __init__(self,starting=10000.0):
        self.cash=starting
        self.pos={}
        self.stopped={}
        self.trades=[]
        self.costs=0.0
        self.notional=0.0
        self.realized=0.0
        self.daily=[]
        self.signal_log=[]
        self.pending={}
        self.last_allocation=None
        self.below_count=defaultdict(int)
    def trade(self,sym,qty,raw_price,d,reason):
        """Signed whole-share order; sells before buys; commission+slippage."""
        if not qty:return 0
        qty=int(qty)
        if qty<0:
            old=self.pos.get(sym)
            if not old: return 0
            actual=min(-qty,old["qty"])
            px=raw_price*(1-BPS)
            fee=max(1.0,actual*0.005)
            self.cash+=actual*px-fee
            old["qty"]-=actual
            if old["qty"]==0:self.pos.pop(sym)
            qty=-actual
        else:
            px=raw_price*(1+BPS)
            while qty>0 and qty*px+max(1.0,qty*0.005)>self.cash+1e-9:
                qty-=1
            if not qty:return 0
            fee=max(1.0,qty*0.005)
            self.cash-=qty*px+fee
            old=self.pos.get(sym)
            if old:old["qty"]+=qty
            else:self.pos[sym]={"qty":qty,"stop":None}
        self.notional+=abs(qty)*raw_price
        self.costs+=abs(qty)*raw_price*BPS+fee
        self.trades.append({"date":d,"symbol":sym,"side":"BUY" if qty>0 else "SELL",
                            "shares":abs(qty),"unadjusted_exec_price":raw_price,
                            "fill":px,"commission":fee,"reason":reason})
        if self.cash<-1e-6:raise RuntimeError(f"NEGATIVE_CASH {self.cash}")
        return qty

def getrow(frames,sym,d,require=False):
    df=frames.get(sym)
    if df is not None and d in df.index:
        return df.loc[d]
    if require:
        raise RuntimeError(f"MISSING_DAILY_PRICE {sym} {d}")
    return None

def selected_stock_ranks(d,sector,members,sector_map,frames):
    """Top 5 by risk-adjusted stock score; no fundamental or global-rank gate."""
    candidates=[]
    for sym in members:
        if sector_map.get(sym)!=sector:continue
        row=getrow(frames,sym,d)
        if row is None or not row["stock_ok"]:continue
        val=row["score"]
        if np.isfinite(val):
            candidates.append((float(val),sym))
    candidates.sort(key=lambda z:(-z[0],z[1]))
    return [sym for _,sym in candidates[:5]]

def signal_context(d,frames,spy,symbols,members,sector_map):
    """Market and sector signals use only information through close(d)."""
    sr=getrow(frames,spy,d,True)
    spy_bull=close_level_state(sr)
    spy_ret=float(sr["px63"])
    sector_rows=[]
    for sector,etf in SECTORS.items():
        r=getrow(frames,etf,d,True)
        sector_names=[s for s in members if sector_map.get(s)==sector]
        known=0; above=0
        for sym in sector_names:
            q=getrow(frames,sym,d)
            if q is None or not np.isfinite(q["ema200"]):continue
            known+=1
            if q["close"]>q["ema200"]:above+=1
        breadth=above/known if known else 0
        # Fail closed rather than treating missing constituents as breadth bearish.
        if sector_names and known/len(sector_names)<0.80:
            raise RuntimeError(f"INSUFFICIENT_SECTOR_BREADTH {sector} {d} {known}/{len(sector_names)}")
        momentum=float(r["sector_momentum"])
        relative63=float(r["px63"])-spy_ret
        bull=close_level_state(r) and breadth>0.50
        sector_rows.append({"sector":sector,"etf":etf,"momentum":momentum,
            "r5":float(r["r5"]),"breadth":breadth,"breadth_known":known,
            "breadth_total":len(sector_names),"bull":bull,
            "relative63":relative63,"etag":r["close"]>r["ema200"]})
    allocation=sector_allocation(spy_bull,sector_rows)
    return spy_bull,allocation,sector_rows

def run(frames,calendar,months,members_lookup,sectors_lookup,
        warm_start=None,diagnostic=False):
    st=Portfolio()
    dates=[d for d in calendar if START.isoformat()<=d<=END.isoformat()]
    if not dates: raise RuntimeError("empty trading calendar")
    start_signal=max(d for d in calendar if d<dates[0])
    if warm_start is None or warm_start["date"] != start_signal:
        raise RuntimeError("WARM_START_REQUIRED: provide the preceding trading-day signal")
    st.pending[dates[0]]={"target":warm_start["target"],"reason":"WARM_START"}
    st.last_allocation=warm_start["allocation"]
    st.signal_log.append({"date":start_signal,"spy_bull":warm_start["spy_bull"],
         "sector_alloc":warm_start["allocation"],"sector_breadth":warm_start["sector_breadth"],
         "stocks":sorted(warm_start["target"]),"trigger":"WARM_START"})
    count_events=Counter(); periods=[]
    watch=[]
    for ix,d in enumerate(dates):
        # Ex-date dividends belong ONLY to shares held prior to the ex-date
        # opening. New shares purchased at today's open are not entitled.
        for sym,pos in list(st.pos.items()):
            exrow=getrow(frames,sym,d,True)
            st.cash+=pos["qty"]*float(exrow["dividend"])
        # Previous close instructions execute at this opening.
        plan=st.pending.pop(d,None)
        if plan:
            desired=plan["target"]
            nav_at_open=st.cash
            for sym,pos in list(st.pos.items()):
                nav_at_open+=pos["qty"]*float(getrow(frames,sym,d,True)["open"])
            for sym,pos in list(st.pos.items()):
                px=float(getrow(frames,sym,d,True)["open"])
                want=int(math.floor(nav_at_open*desired.get(sym,0)/px))
                delta=want-pos["qty"]
                if delta<0:
                    st.trade(sym,delta,px,d,plan["reason"])
            for sym,w in sorted(desired.items(),key=lambda z:(-z[1],z[0])):
                px=float(getrow(frames,sym,d,True)["open"])
                have=st.pos[sym]["qty"] if sym in st.pos else 0
                want=int(math.floor(nav_at_open*w/px))
                if want>have:
                    if sym in st.stopped and not lockout_allows_signal(ix-1,st.stopped[sym]):
                        raise RuntimeError("LOCKOUT_BYPASS")
                    amt=st.trade(sym,want-have,px,d,plan["reason"])
                    if amt and st.pos[sym]["stop"] is None:
                        # Entry-day stop computed using known previous-session ATR.
                        df=frames[sym]
                        pidx=df.index.get_loc(d)
                        atr_prev=float(df.iloc[pidx-1]["atr"]) if pidx>0 else math.nan
                        if not np.isfinite(atr_prev) or atr_prev<=0:
                            raise RuntimeError(f"MISSING_PREV_ATR {sym} {d}")
                        st.pos[sym]["stop"]=max(0.001,px-3*atr_prev)
        # Intraday stops: levels known at open, before today's close.
        for sym,pos in list(st.pos.items()):
            row=getrow(frames,sym,d,True)
            stop_px=intraday_stop_fill(float(row["open"]),float(row["low"]),pos["stop"])
            if stop_px is not None:
                st.trade(sym,-pos["qty"],stop_px,d,"ATR_INTRA")
                st.stopped[sym]=ix
                st.below_count.pop(sym,None)
                count_events["ATR_INTRA"]+=1
        nav=st.cash; invested=0
        for sym,pos in st.pos.items():
            row=getrow(frames,sym,d,True)
            nav+=pos["qty"]*float(row["close"])
            invested+=pos["qty"]*float(row["close"])
            if row["close"]<row["ema200"]:st.below_count[sym]+=1
            else:st.below_count[sym]=0
            # Ratchet strictly after intraday execution. Effective tomorrow.
            if np.isfinite(row["atr"]):
                pos["stop"]=max(float(pos["stop"]),float(row["close"])-3*float(row["atr"]))
        st.daily.append({"date":d,"nav":nav,"cash":st.cash,
           "equity_exposure":invested/nav if nav>0 else 0,
           "positions":len(st.pos)})
        # Signal at this close. No intraday state lookahead.
        if d==dates[-1]:continue
        signal_day=d
        calendar_index=calendar.index(d)
        membership_day=date.fromisoformat(d)
        members=members_lookup(membership_day)
        sectormap=sectors_lookup(membership_day)
        spy_bull,allocation,sector_rows=signal_context(d,frames,"SPY",frames.keys(),members,sectormap)
        regime_changed=allocation!=st.last_allocation
        month_end=months.get(d[:7])==d
        rank_by_sector={}
        if allocation and (regime_changed or month_end):
            rank_by_sector={sec:selected_stock_ranks(d,sec,members,sectormap,frames) for sec in allocation}
        fail=[sym for sym in st.pos if st.below_count.get(sym,0)>=2]
        # Daily re-entry after lockout may refill stopped sector slots but
        # should never demote a still-qualified incumbent absent a monthly rotation.
        vacancies=[]
        for sec in allocation:
            if not rank_by_sector.get(sec):
                rank_by_sector[sec]=selected_stock_ranks(d,sec,members,sectormap,frames)
            occupied=[sym for sym in st.pos if sectormap.get(sym)==sec]
            if len(occupied)<5 and any(
                sym not in st.pos and lockout_allows_signal(ix,st.stopped.get(sym))
                for sym in rank_by_sector[sec]):
                vacancies.append(sec)
        if (not regime_changed and not month_end and not fail and not vacancies):
            st.last_allocation=allocation
            continue
        target={}
        for sec,weight in allocation.items():
            top=rank_by_sector[sec]
            if regime_changed or month_end:
                choices=[sym for sym in top
                         if lockout_allows_signal(ix,st.stopped.get(sym))
                         and st.below_count.get(sym,0)<2]
            else:
                # Only refill when the current rank is top 5, without forcing
                # other incumbents out until their monthly demotion.
                incumbents=[sym for sym in st.pos
                            if sectormap.get(sym)==sec and sym not in fail]
                additions=[sym for sym in top
                           if sym not in incumbents
                           and lockout_allows_signal(ix,st.stopped.get(sym))]
                choices=(incumbents+additions)[:5]
            if choices:
                for sym in choices:target[sym]=weight/len(choices)
        reason="MONTHLY" if month_end else ("REGIME" if regime_changed else ("REGIME_FAILURE" if fail else "REENTRY"))
        next_d=dates[ix+1]
        st.pending[next_d]={"target":target,"reason":reason}
        if month_end or regime_changed:
            st.signal_log.append({"date":d,"spy_bull":spy_bull,
                "sector_alloc":allocation,"sector_breadth":{r["sector"]:round(r["breadth"],4) for r in sector_rows},
                "stocks":sorted(target),"trigger":reason})
            count_events[reason]+=1
        st.last_allocation=allocation
    if not st.daily:raise RuntimeError("No NAV output")
    return st

def summary(st):
    daily=st.daily
    starting=10000
    prev=starting
    years={}
    for year in sorted({r["date"][:4] for r in daily}):
        vals=[r["nav"] for r in daily if r["date"].startswith(year)]
        years[year]=100*(vals[-1]/prev-1)
        prev=vals[-1]
    peak=starting;mdd=0
    for v in daily:
        peak=max(peak,v["nav"])
        mdd=min(mdd,v["nav"]/peak-1)
    n_years=(date.fromisoformat(daily[-1]["date"])-date.fromisoformat(daily[0]["date"])).days/365.25
    return {"annual_return_pct":years,"end_value":prev,"cagr_pct":100*((prev/starting)**(1/n_years)-1),
       "max_dd_pct":100*mdd,"avg_exposure_pct":100*statistics.mean(x["equity_exposure"] for x in daily),
       "trade_count":len(st.trades),"costs":st.costs,
       "turnover_x":st.notional/starting/n_years}

def main():
    # Load Yahoo OHLC plus dividends, historical S&P constituents, and PIT GICS.
    cache=base.Cache(ROOT/".backtest_cache")
    web=requests.Session()
    web.headers["User-Agent"]="Mozilla/5.0 ISK sector-first historical research"
    current,_,changes=base.sp500_history(web)
    base_members=base.members_at(current,changes,date(2021,12,31))
    universe=set(current)|set(base_members)
    for ch in changes:
        if "2021-11-01"<=ch["date"]<=END.isoformat():
            universe|={x for x in (ch["added"],ch["removed"]) if x}
    universe|={"SPY"}|set(SECTORS.values())
    raw={}
    def fetch(sym):
        ses=requests.Session();ses.headers["User-Agent"]="Mozilla/5.0 sector research"
        return sym,base.yahoo(ses,cache,sym,base.DATA_START,base.DATA_END)
    with ThreadPoolExecutor(max_workers=12) as ex:
        futures={ex.submit(fetch,s):s for s in sorted(universe)}
        for f in as_completed(futures):
            sym,v=f.result()
            if v:raw[sym]=v
    frames={sym:x for sym,v in raw.items() if (x:=features(v)) is not None}
    if not all(x in frames for x in ("SPY",*SECTORS.values())):
        raise RuntimeError("sector ETF / SPY missing data")
    calendar=[x for x in frames["SPY"].index if
              "2021-12-01"<=x<=END.isoformat()]
    trading_dates=[x for x in calendar if START.isoformat()<=x<=END.isoformat()]
    months={}
    for d in trading_dates:months[d[:7]]=d
    wiki=requests.Session()
    wiki.headers["User-Agent"]="Mozilla/5.0 sector PIT study"
    pit_history=hist.load_pit_sector_history(wiki)
    membership_cache={};sector_cache={}
    def members_at(d):
        key=d.isoformat()
        if key not in membership_cache:
            membership_cache[key]=base.members_at(current,changes,d)
        return membership_cache[key]
    def sectors_at(d):
        key=d.isoformat()
        if key not in sector_cache:
            sector_cache[key]=hist.pit_sector_snapshot(pit_history,d)["sectors"]
        return sector_cache[key]
    # Warm start at 2021-12-31, execute targets on 2022-01-03.
    pre=calendar[calendar.index(trading_dates[0])-1]
    spy_bull,allocation,sect=signal_context(pre,frames,"SPY",frames.keys(),
              members_at(date.fromisoformat(pre)),sectors_at(date.fromisoformat(pre)))
    initial={}
    for sec,w in allocation.items():
        selected=selected_stock_ranks(pre,sec,members_at(date.fromisoformat(pre)),sectors_at(date.fromisoformat(pre)),frames)
        for sym in selected:
            initial[sym]=w/len(selected)
    # Warm start state enters run before the first open.
    st=run_with_warm_start(frames,calendar,months,members_at,sectors_at,
                           pre,spy_bull,allocation,sect,initial)
    sm=summary(st)
    result={"strategy":"Sector-first explicit v1","rules":{
      "sector_permission":"ETF split-adjusted Close > continuous EMA200(close) AND PIT breadth >50%",
      "breadth_denominator":"historical constituent count with observed 200-session EMA; missing coverage below 80% fails closed",
      "spy":"split-adjusted close > EMA200 close",
      "sector_momentum":"mean 63/126/252 total-return",
      "relative63":"63d price return sector minus SPY > 0 for BEAR overrides",
      "sector_allocation":"top2; momentum ratio >=1.5 70/30 else 50/50; single 90% (>70 breadth) or 70% (50-70); BEAR 50% max / 40% weaker single; cash 0%",
      "stock_score":"0.5 r63/sigma63 + 0.3 r126/sigma126 + 0.2 r252/sigma252 with sample 252 annualized daily volatility",
      "stocks":"top5 per sector, close > EMA50 & EMA200, equal within sector",
      "rebalancing":"monthly close->next open, daily sector/SPY state transitions->next open; daily reentry only on vacancy",
      "atr":"Wilder 14, trailing stop prev close minus 3xATR, intraday low gap/open handling, 7bp adverse fill",
      "lockout":"5 full trading sessions, earliest new signal day >= stopped_index+6",
      "regime_failure":"two closes below stock EMA200 => sell next open",
      "universe":"reconstructed historical S&P constituents and prior-dated historical GICS",
      "no_sec_fundamentals":True,
      "no_75_25_sleeves":True,
      "cash_yield":0.0
    },"metrics":sm,"initial_signal":pre,"initial_allocation":allocation,
      "monthly_signals":[x for x in st.signal_log if x["date"]==months.get(x["date"][:7])],
      "trades":st.trades,"daily":st.daily}
    OUTJ.parent.mkdir(parents=True,exist_ok=True)
    OUTJ.write_text(json.dumps(result,indent=2))
    lines=["# Explicit sector-first strategy (2022–Sep 2026)","",
      "Independent new strategy; NOT the original frozen 75/25 engine or its replication. Using point-in-time historical constituent mappings and price-only stock criteria (no SEC fundamentals).",
      "",
      "| Year | Return |","|---|---:|"]
    for year,pct in sm["annual_return_pct"].items():
        lines.append(f"| {year} | {pct:+.2f}% |")
    lines+=["","| Metric | Result |","|---|---:|",
      f"| CAGR | {sm['cagr_pct']:.2f}% |", f"| Max drawdown | {sm['max_dd_pct']:.2f}% |",
      f"| Avg equity exposure | {sm['avg_exposure_pct']:.2f}% |",
      f"| Ending NAV ($10,000) | \${sm['end_value']:,.2f} |",
      f"| Trades | {sm['trade_count']} |",f"| Costs | \${sm['costs']:,.2f} |",
      "","## 2022 monthly sector decisions","",
      "| Date | SPY BULL | Sector allocation |","|---|---|---|"]
    for x in result["monthly_signals"]:
        if x["date"].startswith("2022-"):
            desc=", ".join(f"{sec}: {w*100:.0f}%" for sec,w in x["sector_alloc"].items()) or "Cash"
            lines.append(f"| {x['date']} | {x['spy_bull']} | {desc} |")
    lines+=["","## Execution and interpretation",
      "- Daily and monthly decisions are computed from same-day close, executed next available session open.",
      "- Intraday trailing stops use the *previous day's* stop, with gap-open adjustment.",
      "- In SPY BEAR with two qualifying sectors, allocation is capped at 50% and split 70/30 or 50/50 among Top-2.",
      "- Sector breadth is strict >50%, resolving the 50% boundary overlap in favor of the original permission definition.",
      "- If either Top-2 sector momentum is non-positive, the 1.5x ratio is undefined; use a conservative 50/50 split.",
      "- Financials are not special-cased; unlike prior reconstructed experiments, no SEC fundamental gate is applied.",
      "- No guarantee of +16.4% in 2022: this is the mechanically executed strategy, not the manually authored monthly P&L path.",
      "- Historical S&P membership and GICS source completeness, raw Yahoo corporate actions, and financing assumptions remain research-quality, not institutional-grade certified." ]
    OUTM.write_text("\n".join(lines)+"\n")
    print(OUTM.read_text())

def run_with_warm_start(frames,calendar,months,members_lookup,sectors_lookup,
                        pre,spy_bull,allocation,sector_rows,initial):
    """Execute the preceding December signal on the first January open."""
    warm={"date":pre,"spy_bull":spy_bull,"allocation":allocation,
          "sector_breadth":{r["sector"]:round(r["breadth"],4) for r in sector_rows},
          "target":initial}
    return run(frames,calendar,months,members_lookup,sectors_lookup,warm_start=warm)

if __name__=="__main__":main()
