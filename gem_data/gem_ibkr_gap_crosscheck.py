"""Authorized IBKR historical-data read-only GEM gap cross-check.

This is a separate-source verifier for Yahoo provisional June gaps, NOT a
broker trading client or source certifier. Never calls an order endpoint.
Requires an independently configured IBKR Web API SSO data session and
instrument-specific conid mapping on the GEM Render service to run unattended.

Source: https://ibkrcampus.com/docs/web-api/v1/endpoints/market-data/historical-market-data
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import os
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx
import psycopg

from gem_data.gem_public_ingest import EXPERIMENT, write_observation
from gem_data.gem_yfinance_gap_research import TARGET_DATES

PROBE_PREFIX="gem-ibkr-independent-price-check-"
URL="https://api.ibkr.com/v1/api/iserver/marketdata/history"
NY=ZoneInfo("America/New_York")


class IBKRGatewayHold(ValueError):
    pass


def _finite(value,label,*,zero=False):
    if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value):
        raise IBKRGatewayHold("INVALID_"+label.upper())
    if value < 0 if zero else value<=0:
        raise IBKRGatewayHold("INVALID_"+label.upper())
    return float(value)


def normalize_ibkr_history(body, *, expected_dates=TARGET_DATES):
    """Validate IBKR WebAPI daily trades, not assume adjusted-close semantics."""
    if not isinstance(body,dict) or not isinstance(body.get("data"),list):
        raise IBKRGatewayHold("MISSING_IBKR_HISTORY_BARS")
    records=body["data"]
    if not 1<=len(records)<=1000:
        raise IBKRGatewayHold("UNBOUNDED_IBKR_HISTORY")
    if body.get("outsideRth") is True:
        raise IBKRGatewayHold("EXTENDED_HOURS_NOT_DAILY_RTH")
    if (body.get("source") not in (None,"Last","trades")
            or body.get("error") or body.get("mktDataDelay",-1) is None):
        raise IBKRGatewayHold("NOT_TRADE_OHLCV")
    target=set(expected_dates)
    if not target or not target.issubset(TARGET_DATES):
        raise IBKRGatewayHold("UNEXPECTED_TRADING_SESSIONS")
    observations={}
    for row in records:
        if not isinstance(row,dict):
            raise IBKRGatewayHold("INVALID_HISTORY_ROW")
        epoch=row.get("t")
        if isinstance(epoch,bool) or not isinstance(epoch,(int,float)) or not math.isfinite(epoch):
            raise IBKRGatewayHold("INVALID_HISTORY_TIMESTAMP")
        try:
            day=datetime.fromtimestamp(epoch/1000,timezone.utc).astimezone(NY).date().isoformat()
        except (ValueError,OverflowError,OSError):
            raise IBKRGatewayHold("INVALID_HISTORY_TIMESTAMP") from None
        if day not in target:
            continue
        if day in observations:
            raise IBKRGatewayHold("DUPLICATE_IBKR_SESSION")
        result={"session":day}
        for name,label in (("o","open"),("h","high"),("l","low"),
                           ("c","close"),("v","volume")):
            result[label]=_finite(row.get(name),label,zero=label=="volume")
        if (result["high"]<max(result["open"],result["low"],result["close"])
                or result["low"]>min(result["open"],result["high"],result["close"])):
            raise IBKRGatewayHold("INVALID_IBKR_OHLC")
        observations[day]=result
    return observations


def crosscheck_yahoo_ibkr(yahoo,ibkr,*,ticker):
    """Pure machine comparison, explicitly NOT adjusted-price/source approval.

    Close/open/high/low must agree within 0.25%, volume within 5%.
    A discrepancy becomes a source-review hold; it is never averaged away.
    """
    if (not isinstance(ticker,str) or not ticker
            or not isinstance(yahoo,dict) or not isinstance(ibkr,dict)
            or yahoo.get("ticker")!=ticker or yahoo.get("session")!=ibkr.get("session")):
        raise IBKRGatewayHold("INCONSISTENT_HISTORICAL_IDENTITY")
    differences={}
    for name in ("open","high","low","close","volume"):
        a=_finite(yahoo.get(name),name,zero=name=="volume")
        b=_finite(ibkr.get(name),name,zero=name=="volume")
        spread=abs(a-b)
        limit=(max(1.0,.05*max(a,b)) if name=="volume"
               else max(.02,.0025*max(a,b)))
        if spread>limit:
            differences[name]={"relative_difference_pct":round(spread/max(a,b)*100,5)}
    return {
        "schema":"gem-ibkr-yahoo-gap-crosscheck-v1",
        "ticker":ticker,"session":ibkr["session"],
        "state":"PROVISIONAL_TWO_SOURCE_PRICE_MATCH" if not differences else "PROVIDER_DISAGREEMENT_HOLD",
        "discrepancies":differences,
        "independent_market_data_reference":True,
        "frozen_adjusted_close_verified":False,
        "original_marketstack_mutated":False,
        "source_certified":False,"trading_authorized":False,
    }


def _authorization():
    """Fail before any network call unless an authorized IBKR data session is configured."""
    if os.getenv("GEM_IBKR_HISTORICAL_READONLY_ENABLED")!="yes":
        raise IBKRGatewayHold("IBKR_SOURCE_WORKER_NOT_OPTED_IN")
    bearer=os.getenv("GEM_IBKR_READONLY_BEARER","")
    if len(bearer)<20 or any(c.isspace() for c in bearer):
        raise IBKRGatewayHold("AUTHORIZED_IBKR_DATA_SESSION_REQUIRED")
    raw=os.getenv("GEM_IBKR_CONID_MAP_JSON","")
    try:
        mapping=json.loads(raw)
    except (ValueError,TypeError):
        raise IBKRGatewayHold("IBKR_CONTRACT_MAP_REQUIRED") from None
    if (not isinstance(mapping,dict) or not 1<=len(mapping)<=600
            or any(not isinstance(symbol,str) or not symbol
                   or type(conid) is not int or conid<=0
                   for symbol,conid in mapping.items())):
        raise IBKRGatewayHold("INVALID_IBKR_CONTRACT_MAP")
    return bearer,mapping


def _fetch(conid,bearer):
    """Only official GET historical-data endpoint. Never orders or balances."""
    with httpx.Client(timeout=20,follow_redirects=False) as client:
        response=client.get(URL,
             params={"conid":conid,"period":"1y","bar":"1d",
                     "outsideRth":"false","source":"trades"},
             headers={"Authorization":"Bearer "+bearer,
                      "Accept":"application/json"})
    if response.status_code!=200:
        raise IBKRGatewayHold("IBKR_HISTORY_HTTP_"+str(response.status_code))
    if len(response.content)>500_000:
        raise IBKRGatewayHold("IBKR_HISTORY_RESPONSE_OVERSIZED")
    try:
        return response.json(),sha256(response.content).hexdigest()
    except ValueError:
        raise IBKRGatewayHold("IBKR_INVALID_JSON_RESPONSE") from None


def crosscheck_batch(*, max_symbols=2,fetch_fn=None):
    """Read latest Yahoo candidate gaps, append separate noncertifying IBKR probes.

    Only eligible configured conids are requested. A source/terms entitlement
    must be established by operator; this code cannot create a live session.
    """
    if type(max_symbols) is not int or not 1<=max_symbols<=2:
        raise IBKRGatewayHold("MAX_TWO_HISTORICAL_REQUESTS_PER_CYCLE")
    bearer,conids=_authorization()
    reader=os.getenv("GEM_READONLY_DATABASE_URL","")
    writer=os.getenv("GEM_INGEST_DATABASE_URL","")
    if (not reader.startswith("postgresql://gem_web_readonly:")
            or not writer.startswith("postgresql://gem_source_ingest_limited:")):
        raise IBKRGatewayHold("RESTRICTED_GEM_ROLES_REQUIRED")
    with psycopg.connect(reader,connect_timeout=6) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SET LOCAL statement_timeout=12000")
            cur.execute("""
                SELECT DISTINCT ON (metadata->>'marketstack_ticker',metadata->>'session')
                  metadata->>'marketstack_ticker',metadata->>'session',
                  metadata->'normalized_bar',receipt_id
                FROM gem_source_receipt
                WHERE experiment_id=%s AND source_type='prices'
                  AND provider='YFINANCE_PERSONAL_RESEARCH'
                  AND metadata->>'research_validation'='GAP_CANDIDATE_ONLY'
                ORDER BY metadata->>'marketstack_ticker',metadata->>'session',
                         observed_at DESC,receipt_id DESC
            """,(EXPERIMENT,))
            rows=cur.fetchall()
            cur.execute("""
                SELECT details->>'ticker' ticker,details->>'session' session
                FROM gem_source_probe
                WHERE experiment_id=%s AND probe_id LIKE %s
            """,(EXPERIMENT,PROBE_PREFIX+"%"))
            done={(a,b) for a,b in cur.fetchall()}
    candidates={}
    for ticker,session,yahoo,receipt in rows:
        if ticker not in conids or session not in TARGET_DATES or (ticker,session) in done:
            continue
        if not isinstance(yahoo,dict):
            continue
        candidates.setdefault(ticker,[]).append((session,yahoo,receipt))
    requested=0
    agreed=0
    conflicts=0
    held=0
    now=datetime.now(timezone.utc)
    for symbol,requested_days in list(candidates.items())[:max_symbols]:
        try:
            body,digest=(fetch_fn or _fetch)(conids[symbol],bearer)
            bars=normalize_ibkr_history(body,expected_dates=TARGET_DATES)
        except IBKRGatewayHold:
            held+=len(requested_days)
            continue
        requested+=1
        with psycopg.connect(writer,connect_timeout=6) as conn:
            for session,yahoo,receipt_id in requested_days:
                if session not in bars:
                    result={"schema":"gem-ibkr-yahoo-gap-crosscheck-v1",
                            "ticker":symbol,"session":session,
                            "state":"IBKR_SESSION_NOT_AVAILABLE_HOLD",
                            "source_certified":False,"trading_authorized":False}
                    held+=1
                else:
                    try:
                        result=crosscheck_yahoo_ibkr(yahoo,bars[session],ticker=symbol)
                    except IBKRGatewayHold:
                        result={"schema":"gem-ibkr-yahoo-gap-crosscheck-v1",
                                "ticker":symbol,"session":session,
                                "state":"INVALID_CANDIDATE_HOLD",
                                "source_certified":False,"trading_authorized":False}
                    if result["state"]=="PROVISIONAL_TWO_SOURCE_PRICE_MATCH":
                        agreed+=1
                    else:
                        conflicts+=1
                result["ibkr_conid"]=conids[symbol]
                result["ibkr_response_sha256"]=digest
                result["yahoo_candidate_receipt_id"]=receipt_id
                result["raw_ibkr_response_not_retained"]=True
                result["entitlement_not_inferred_from_http_success"]=True
                result["frozen_adjustment_parity_approved"]=False
                raw=json.dumps(result,sort_keys=True,separators=(",",":"))
                evidence=sha256(raw.encode()).hexdigest()
                key=PROBE_PREFIX+sha256((symbol+"|"+session+"|"+receipt_id+"|"+digest).encode()).hexdigest()[:40]
                probe={"probe_id":key,"source_type":"prices","state":"PARTIAL",
                       "observed_at":now,"sample_count":1,"diagnostic_hash":evidence,
                       "details":result}
                write_observation(conn,None,probe)
                conn.commit()
    return {"schema":"gem-ibkr-readonly-crosscheck-progress-v1",
            "requested_symbols":requested,"machine_agreements":agreed,
            "price_conflicts":conflicts,"holds":held,
            "source_certified":False,"trading_authorized":False}
