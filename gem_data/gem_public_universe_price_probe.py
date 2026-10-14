"""Yahoo public-source 503-security historical price/volume and r63 *triage*.

Explicit operator-only/CI diagnostic. The stored GEM strategy uses a separate
frozen source/adjustment convention; this NEVER certifies a 2026-09-30 signal,
ranks for trading, or authorizes an order. Current secondary membership != PIT.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from hashlib import sha256
from io import StringIO
import json
import math
import re

from gem_data.gem_nyse_2026_manifest import published_schedule_2026

SOURCE = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/master/data/constituents.csv"
EXISTING_SOURCE_SHA = "a8045f043ea7e68d4254a07470a5e95ca5759ded4656657eac514162e6e82e06"


def parse_membership(raw: bytes):
    import csv
    text = raw.decode("utf-8-sig")
    rows = list(csv.DictReader(StringIO(text)))
    symbols={}
    for row in rows:
        ticker = str(row.get("Symbol") or "").strip().upper()
        cik = str(row.get("CIK") or "").strip()
        if (not re.fullmatch(r"[A-Z0-9.-]{1,16}",ticker) or ticker in symbols
                or not cik.isdigit() or len(cik)>10):
            raise ValueError("Invalid secondary security identity")
        symbols[ticker]=cik.zfill(10)
    if len(symbols)!=503 or len(set(symbols.values()))!=500:
        raise ValueError("Secondary S&P 500 membership count changed; HOLD")
    return symbols


def classify_yahoo_security(ticker, bars, *, signal_day, required_sessions):
    """No silent interpolation or missing-competitor exclusion."""
    base={"ticker":ticker,"r63":None,"nominal_close":None,"adv20":None,
          "eligible_price_liquidity_provisional":False,"certified":False}
    if bars is None or bars.empty:
        return {**base,"status":"MISSING_YAHOO_HISTORY"}
    try:
        by_date={}
        for stamp,bar in bars.iterrows():
            day=stamp.strftime("%Y-%m-%d")
            if day>signal_day:
                continue
            if day in by_date:
                raise ValueError("Duplicate Yahoo sessions")
            by_date[day]=bar
        dates=sorted(by_date)
        if not dates or dates[-1]!=signal_day:
            raise ValueError("Missing month-end vendor close")
        if len(dates)<127:
            raise ValueError("Fewer than 127 historical sessions")
        if dates[-127:]!=required_sessions[-127:]:
            raise ValueError("127-session dates disagree with NYSE schedule")
        window=[by_date[d] for d in dates[-127:]]
        for b in window:
            vals=[float(b[k]) for k in ("Open","High","Low","Close","Adj Close","Volume")]
            if not all(math.isfinite(v) for v in vals):
                raise ValueError("Missing/invalid OHLCV or adjusted close")
            op,hi,lo,cl,adj,vol=vals
            if (min(op,cl,hi,lo,adj)<=0 or vol<0
                    or hi+1e-8<max(op,cl,lo) or lo-1e-8>min(op,cl,hi)):
                raise ValueError("Yahoo daily OHLCV geometric anomaly")
        r63=float(window[-1]["Adj Close"])/float(window[-64]["Adj Close"])-1
        nominal=float(window[-1]["Close"])
        adv20=sum(float(b["Close"])*float(b["Volume"]) for b in window[-20:])/20
    except (ValueError,TypeError,KeyError,IndexError) as exc:
        return {**base,"status":"UNRESOLVED_PRICE_QA",
                "reason":str(exc)[:120]}
    return {**base,"status":"OBSERVED_UNCERTIFIED",
            "r63":r63,"nominal_close":nominal,"adv20":adv20,
            "positive_momentum_preliminary":r63>0,
            "eligible_price_liquidity_provisional":
                r63>0 and nominal>=5 and adv20>=10_000_000,
            "observed_session_count":len(dates)}


def probe_universe(*, signal_day="2026-09-30", asof_day="2026-10-13",
                   max_symbols=503, batch_size=40, raw_fetch=None,
                   quote_fetch=None):
    if signal_day!="2026-09-30" or asof_day!="2026-10-13":
        raise ValueError("Historical diagnostic sessions are pinned")
    if (type(max_symbols) is not int or not 1<=max_symbols<=503
            or type(batch_size) is not int or not 1<=batch_size<=50):
        raise ValueError("Bounded symbol scan required")
    if raw_fetch is None:
        import requests
        def raw_fetch(uri):
            reply=requests.get(uri,timeout=18,headers={"User-Agent":"GEM research read-only source diagnostic"})
            reply.raise_for_status()
            if len(reply.content)>500_000:
                raise ValueError("Membership source too large")
            return reply.content
    raw=raw_fetch(SOURCE)
    if not isinstance(raw,bytes) or len(raw)>500_000:
        raise ValueError("Invalid source bytes")
    symbols=parse_membership(raw)
    assert len(symbols)==503
    source_sha=sha256(raw).hexdigest()
    xny=published_schedule_2026()
    required=[d["session"] for d in xny["sessions"] if d["session"]<=signal_day]
    requested=sorted(symbols)[:max_symbols]
    results=[]
    if quote_fetch is None:
        import yfinance as yf
        def quote_fetch(vendor_symbols):
            return yf.download(
                vendor_symbols, start="2026-03-01",end="2026-10-14",
                auto_adjust=False,actions=True,progress=False,
                group_by="ticker",threads=5,repair=False)
    for first in range(0,len(requested),batch_size):
        batch=requested[first:first+batch_size]
        vendor=[ticker.replace(".","-") for ticker in batch]
        try:
            table=quote_fetch(vendor)
        except Exception as exc:
            for ticker in batch:
                results.append({"ticker":ticker,"status":"VENDOR_BATCH_HOLD",
                                "reason":type(exc).__name__,
                                "certified":False})
            continue
        for ticker,symbol in zip(batch,vendor):
            try:
                if table is None or table.empty:
                    raise ValueError("Empty batch")
                if getattr(table.columns,"nlevels",1)==2:
                    bars=table[symbol]
                else:
                    if len(batch)!=1:
                        raise ValueError("Multi-ticker column schema mismatch")
                    bars=table
                item=classify_yahoo_security(
                    ticker,bars,signal_day=signal_day,
                    required_sessions=required)
            except (KeyError,ValueError,TypeError) as exc:
                item={"ticker":ticker,"status":"VENDOR_SYMBOL_HOLD",
                      "reason":str(exc)[:120],"certified":False}
            item["cik"]=symbols[ticker]
            results.append(item)
    counts=dict(Counter(row["status"] for row in results))
    observed=[r for r in results if r["status"]=="OBSERVED_UNCERTIFIED"]
    pos=[r for r in observed if r["r63"]>0]
    qualified=[r for r in observed if r["eligible_price_liquidity_provisional"]]
    top=sorted(qualified,key=lambda r:(-r["r63"],r["ticker"]))[:20]
    report={
        "schema":"gem-public-universe-provisional-r63-20260930-v1",
        "membership_source":SOURCE,
        "membership_sha256":source_sha,
        "membership_matches_stored_oct13":source_sha==EXISTING_SOURCE_SHA,
        "current_membership_count":len(symbols),
        "current_issuer_count":len(set(symbols.values())),
        "symbols_attempted":len(requested),
        "status_counts":counts,
        "full_history_observed":len(observed),
        "positive_momentum_observed_not_certified":len(pos),
        "price_liquidity_plus_momentum_observed_not_certified":len(qualified),
        "preliminary_price_momentum_top20_not_trading":top,
        "unresolved_symbols":[r for r in results if r["status"]!="OBSERVED_UNCERTIFIED"],
        "signal_day_under_review":signal_day,
        "research_only_retrospective_observation":True,
        "price_source":"YAHOO_FINANCE_OBSERVATIONS_NOT_FROZEN_VENDOR_PARITY",
        "verified_eligible_competitor_set":False,
        "source_certified":False,"financial_screened":False,
        "final_ranking_authorized":False,"trading_authorized":False,
        "broker_orders_sent":0,
    }
    report["report_sha256"]=sha256(json.dumps(
        report,sort_keys=True,separators=(",",":"),allow_nan=False
    ).encode()).hexdigest()
    return report
