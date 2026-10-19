"""Bounded customer-token Massive stocks EOD raw-price fallback.

Massive aggregate bars default to split-adjusted. We explicitly request
adjusted=false and NEVER treat raw aggregates as frozen adjusted returns.
No polling, unattended subscription usage or broker connectivity.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from hashlib import sha256
import math
import os
import re

import httpx

_TICKER = re.compile(r"^[A-Z0-9.-]{1,15}$")
_ENDPOINT = "https://api.massive.com/v2/aggs/ticker"


class MassiveDataHold(ValueError):
    pass


def massive_raw_eod_observation(ticker, start, end, *, token=None, client=None):
    if not isinstance(ticker,str) or not _TICKER.fullmatch(ticker):
        raise MassiveDataHold("Bad ticker")
    if type(start) is not date or type(end) is not date or start>end or end>date.today():
        raise MassiveDataHold("Invalid/future request dates")
    if (end-start).days>1100:
        raise MassiveDataHold("One-shot history request too large")
    secret=(token if token is not None else os.environ.get("MASSIVE_API_KEY","")).strip()
    if not secret:
        raise MassiveDataHold("MASSIVE_API_KEY not configured")
    owns=client is None
    connection=client or httpx.Client(timeout=20, follow_redirects=False)
    try:
        try:
            response=connection.get(
                f"{_ENDPOINT}/{ticker}/range/1/day/{start.isoformat()}/{end.isoformat()}",
                headers={"Authorization":"Bearer "+secret,"Accept":"application/json"},
                params={"adjusted":"false","sort":"asc","limit":"5000"},
            )
            if response.status_code!=200 or len(response.content)>5_000_000:
                raise MassiveDataHold("Massive HTTP/size limit HOLD")
            raw=response.content
            obj=response.json()
        except (httpx.HTTPError,ValueError):
            raise MassiveDataHold("Massive EOD request/JSON failed") from None
    finally:
        if owns:connection.close()
    if not isinstance(obj,dict) or obj.get("status") not in ("OK","DELAYED"):
        raise MassiveDataHold("Unexpected Massive result status")
    bars=obj.get("results")
    if not isinstance(bars,list) or not bars or len(bars)>1000 or obj.get("next_url"):
        raise MassiveDataHold("Missing/incomplete/unbounded Massive results")
    if "resultsCount" in obj and obj["resultsCount"] != len(bars):
        raise MassiveDataHold("Inconsistent Massive result count")
    if "queryCount" in obj and obj["queryCount"] < len(bars):
        raise MassiveDataHold("Inconsistent Massive query count")
    normalized=[]
    seen=set()
    for b in bars:
        if not isinstance(b,dict) or type(b.get("t")) not in (int,float):
            raise MassiveDataHold("Malformed aggregate")
        try:
            session=datetime.fromtimestamp(b["t"]/1000,timezone.utc).date()
        except (ValueError,OverflowError,OSError):
            raise MassiveDataHold("Invalid aggregate epoch") from None
        if not start<=session<=end or session in seen:
            raise MassiveDataHold("Duplicate/out-of-window aggregate")
        seen.add(session)
        row={}
        for provider_key,field in (("o","open"),("h","high"),("l","low"),("c","close"),("v","volume")):
            val=b.get(provider_key)
            if (type(val) not in (int,float) or not math.isfinite(val)
                    or (val<0 if field=="volume" else val<=0)):
                raise MassiveDataHold("Invalid nominal "+field)
            row[field]=float(val)
        if row["high"]<max(row["open"],row["close"]) or row["low"]>min(row["open"],row["close"]):
            raise MassiveDataHold("Invalid OHLC geometry")
        normalized.append({"ticker":ticker,"session":session.isoformat(),**row})
    normalized.sort(key=lambda x:x["session"])
    return {
        "provider":"MASSIVE", "basis":"NOMINAL_OHLCV",
        "receipt_sha256":sha256(raw).hexdigest(),
        "window":{"from":start.isoformat(),"to":end.isoformat()},
        "bars":normalized,
        "adjustment_request":"adjusted=false",
        "frozen_adjustment_parity_verified":False,
        "trading_approved":False,
        "attribution":"Massive Stocks Aggregates API",
    }
