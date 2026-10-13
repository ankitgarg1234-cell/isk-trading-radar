"""GEM standalone verified-calendar and SPY cash-dividend benchmark arithmetic.

Outputs are reconcilable calculations, NOT source certification. Actual
sessions/dividends must be supplied by independently checked data inputs.
"""
from __future__ import annotations
from datetime import date
import math

class BenchmarkCalendarHold(ValueError):pass

def validate_completed_sessions(expected, observations, *, receipt_sha256, completed_through):
    if not isinstance(receipt_sha256,str) or len(receipt_sha256)!=64:
        raise BenchmarkCalendarHold("Exchange-calendar source receipt missing")
    if not isinstance(expected,list) or len(expected)!=len(set(expected)) or expected!=sorted(expected):
        raise BenchmarkCalendarHold("Invalid expected exchange sessions")
    if not isinstance(observations,list):raise BenchmarkCalendarHold("Missing actual completed-session bars")
    by_day={}
    for item in observations:
        day=item.get("session")
        if day in by_day:raise BenchmarkCalendarHold("Duplicated completed-session bar")
        by_day[day]=item
    gaps=[]
    for day in expected:
        if day>completed_through:continue
        bar=by_day.get(day,{})
        if bar.get("final") is not True or not isinstance(bar.get("close"),(float,int)) or not math.isfinite(bar["close"]) or bar["close"]<=0:
            gaps.append(day)
    return {"schema":"gem-calendar-completion-v1","completed_through":completed_through,
            "scheduled_through":sum(day<=completed_through for day in expected),
            "verified_completed":sum(day<=completed_through for day in expected)-len(gaps),
            "missing_or_unfinalized":gaps,"status":"PASS" if not gaps else "HOLD",
            "source_review":"Expected calendar and final-bar provenance require independent confirmation"}

def reconstruct_spy_total_return(bars, dividends, *, prices_reviewed=False, dividends_reviewed=False):
    """Cash dividends recognized on ex-date for reinvested total-return index.

    Pay-date cash timing for a held-share portfolio is a separate accounting
    ledger. This TR reconstruction explicitly uses ex-date distribution
    entitlement, not projected fund distribution calendar dates.
    """
    if not isinstance(bars,list) or len(bars)<2 or not isinstance(dividends,list):
        raise BenchmarkCalendarHold("Two completed SPY prices and dividend amounts required")
    bar_map={};div_map={}
    for row in bars:
        day=row.get("session");close=row.get("close")
        if day in bar_map or not isinstance(close,(float,int)) or not math.isfinite(close) or close<=0:
            raise BenchmarkCalendarHold("Invalid SPY close or duplicate session")
        date.fromisoformat(day);bar_map[day]=float(close)
    days=sorted(bar_map)
    if days!=[r["session"] for r in bars]:raise BenchmarkCalendarHold("Prices out of order")
    for item in dividends:
        day=item.get("ex_date");amount=item.get("amount")
        if day in div_map or day not in bar_map or not isinstance(amount,(int,float)) or not math.isfinite(amount) or amount<0:
            raise BenchmarkCalendarHold("Invalid SPY cash distribution")
        div_map[day]=float(amount)
    nav=1.;curve=[{"session":days[0],"index":nav}]
    for prev,day in zip(days,days[1:]):
        nav*= (bar_map[day]+div_map.get(day,0.))/bar_map[prev]
        curve.append({"session":day,"index":nav})
    return {"schema":"gem-spy-tr-exdate-v1","sessions":len(days),"curve":curve,
            "return_pct":(nav-1)*100,
            "status":"REVIEWED_SOURCE_CALCULATION" if prices_reviewed and dividends_reviewed else "UNVERIFIED_SOURCE_INPUT_HOLD",
            "trading_authorized":False,
            "method":"Close-to-close total return with ex-date cash distribution reinvested"}
