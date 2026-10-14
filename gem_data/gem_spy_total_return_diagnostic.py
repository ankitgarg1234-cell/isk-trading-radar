"""SPY ex-dividend cash-reinvestment math from source-identified price observations.

This is an auditable DIAGNOSTIC, not a certified SPY benchmark.
The user-supplied yf.Ticker('SPY').dividends alone supplies dividend events,
not prices or a return series. Upstream acquisition must retain raw source
evidence and an independently reconciled exchange calendar.
"""
from __future__ import annotations

from datetime import date
from hashlib import sha256
import json
import math


def _amount(value, name, *, positive=False):
    if isinstance(value, bool) or not isinstance(value,(int,float)):
        raise ValueError("Invalid "+name)
    f=float(value)
    if not math.isfinite(f) or (positive and f<=0) or (not positive and f<0):
        raise ValueError("Invalid "+name)
    return f


def provisional_spy_total_return(rows, *, expected_sessions=None):
    """Ex-date convention: index_t=index_(t-1)*(P_t+D_t)/P_(t-1).

    This models immediate ex-date reinvestment; if the benchmark convention
    differs, independent QA must reconcile and explicitly document it.
    Split events are NOT guessed from mixed raw/adjusted prices; fail closed.
    """
    if not isinstance(rows,list) or len(rows)<2 or len(rows)>3000:
        raise ValueError("SPY bars missing or outside bounded range")
    sessions=[]
    accepted=[]
    for bar in rows:
        if not isinstance(bar,dict):
            raise ValueError("Malformed SPY bar")
        raw_day=bar.get("session")
        if not isinstance(raw_day,str):
            raise ValueError("Missing SPY session")
        try:
            if date.fromisoformat(raw_day).isoformat()!=raw_day:
                raise ValueError("Noncanonical SPY date")
        except ValueError as exc:
            raise ValueError("Malformed SPY session") from exc
        price=_amount(bar.get("close"),"SPY raw close",positive=True)
        dividend=_amount(bar.get("dividend",0),"SPY cash dividend")
        split=_amount(bar.get("stock_split",0),"SPY split event")
        if split != 0:
            raise ValueError("SPY split event needs independent share-ratio reconciliation")
        sessions.append(raw_day)
        accepted.append((price,dividend))
    if sessions != sorted(set(sessions)):
        raise ValueError("SPY dates unsorted or duplicated")
    if expected_sessions is not None and sessions != expected_sessions:
        raise ValueError("SPY sessions missing compared with independent calendar")
    index=1.0
    path=[{"session":sessions[0],"total_return_index":1.0,
           "raw_close":accepted[0][0],"cash_dividend":accepted[0][1]}]
    if accepted[0][1]:
        raise ValueError("First SPY session must predate dividend reinvestment")
    for i in range(1,len(sessions)):
        previous_close=accepted[i-1][0]
        close,dividend=accepted[i]
        index*=(close+dividend)/previous_close
        if not math.isfinite(index) or index<=0:
            raise ValueError("Nonfinite cumulative SPY return")
        path.append({"session":sessions[i],
                     "total_return_index":index,"raw_close":close,
                     "cash_dividend":dividend})
    result={"schema":"gem-spy-dividend-reinvestment-diagnostic-v1",
            "start":sessions[0],"end":sessions[-1],
            "observed_sessions":len(sessions),
            "dividend_events":sum(div>0 for _,div in accepted),
            "total_return":index-1.0,
            "reinvestment_convention":"CASH_DIVIDEND_ON_EX_DATE_AT_SAME_SESSION_CLOSE",
            "reported_index":path,
            "raw_vendor_source_certified":False,
            "calendar_certified":False,
            "total_return_benchmark_certified":False,
            "trade_authorized":False}
    result["sha256"]=sha256(json.dumps(
        result,sort_keys=True,separators=(",",":"),allow_nan=False
    ).encode()).hexdigest()
    return result
