"""Opt-in bounded personal-research Yahoo gap diagnostics for GEM's autonomous bot.

Always PROVISIONAL and source-referenced. Fetch only explicitly rejected June
2026 market sessions, persist append-only candidate receipts, never overwrite
Marketstack, adjust corporate actions, mark QA PASS, rank, or send orders.

yfinance relies on Yahoo APIs intended for personal research use. This worker
requires explicit operator opt-in and acknowledgement; it is NOT a licensed
production market-data or broker integration.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os

import psycopg

from gem_data.gem_public_ingest import EXPERIMENT, write_observation
from gem_data.gem_yfinance_gap_research import (
    TARGET_DATES, collect_candidates,
)

PREFIX = "gem-yahoo-personal-attempt-v1-"
RESEARCH_PROVIDER = "YFINANCE_PERSONAL_RESEARCH"
REV = "20261014-v1"


class YahooAutoHold(RuntimeError):
    pass


def _config():
    if (os.getenv("GEM_YFINANCE_PERSONAL_RESEARCH_OPT_IN") != "yes"
            or os.getenv("GEM_YFINANCE_PERSONAL_USE_ACK") != "yes"):
        raise YahooAutoHold("Personal research and Yahoo usage acknowledgement required")
    reader=os.getenv("GEM_READONLY_DATABASE_URL","")
    writer=os.getenv("GEM_INGEST_DATABASE_URL","")
    if (not reader.startswith("postgresql://gem_web_readonly:")
            or not writer.startswith("postgresql://gem_source_ingest_limited:")):
        raise YahooAutoHold("Restricted isolated GEM DB roles required")
    return reader,writer


def _iso_day(now):
    if not isinstance(now,datetime) or now.tzinfo is None:
        raise YahooAutoHold("Timezone-aware attempt required")
    return now.astimezone(timezone.utc).strftime("%Y%m%d")


def pending_worklist(*, reader, now, limit):
    """Read private original vendor gaps and previously reviewed Yahoo candidates.

    Read-only operation. Candidate rows missing or failed Yahoo checks can
    retry once on another UTC day, but never spin indefinitely on rate limits.
    """
    if type(limit) is not int or not 1<=limit<=5:
        raise YahooAutoHold("Research batch limit is 1..5 symbols")
    today=_iso_day(now)
    with psycopg.connect(reader,connect_timeout=6) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SET LOCAL statement_timeout = 12000")
            cur.execute("""
                SELECT DISTINCT ON (metadata->>'ticker')
                    metadata->>'ticker' ticker,metadata->'rejected_reasons' reasons
                FROM gem_source_receipt
                WHERE experiment_id=%s AND source_type='prices'
                  AND provider='MARKETSTACK' AND metadata->>'ticker' IS NOT NULL
                ORDER BY metadata->>'ticker',observed_at DESC,receipt_id DESC
            """,(EXPERIMENT,))
            missing=cur.fetchall()
            cur.execute("""
                SELECT metadata->>'marketstack_ticker',metadata->>'session'
                FROM gem_source_receipt
                WHERE experiment_id=%s AND provider=%s
                  AND source_type='prices'
                  AND metadata->>'research_validation'='GAP_CANDIDATE_ONLY'
            """,(EXPERIMENT,RESEARCH_PROVIDER))
            completed={(ticker,day) for ticker,day in cur.fetchall() if ticker and day}
            cur.execute("""
                SELECT details->>'ticker', details->>'attempt_day'
                FROM gem_source_probe
                WHERE experiment_id=%s AND probe_id LIKE %s
            """,(EXPERIMENT,PREFIX+"%"))
            attempts={}
            for ticker,day in cur.fetchall():
                if ticker and day:
                    attempts.setdefault(ticker,[]).append(day)
    pending={}
    available=0
    held=0
    target=set(TARGET_DATES)
    for ticker,reasons in missing:
        if not isinstance(ticker,str) or not isinstance(reasons,list):
            continue
        days=sorted({entry[0] for entry in reasons
                     if isinstance(entry,list) and len(entry)>=2
                     and entry[0] in target
                     and entry[1]=="missing or invalid vendor field: close"})
        wanted=[d for d in days if (ticker,d) not in completed]
        available+=len(days)-len(wanted)
        if not wanted:
            continue
        prior=attempts.get(ticker,[])
        if len(prior)>=2 or today in prior:
            held+=1
            continue
        if len(pending)<limit:
            pending[ticker]=wanted
    return {"pending":pending,"already_available":available,
            "retry_backoff_symbols":held}


def _reserve_attempt(writer, symbol, day):
    """One idempotent and atomic reservation per ticker per UTC day."""
    key=PREFIX+day+"-"+symbol
    digest=sha256(key.encode()).hexdigest()
    with psycopg.connect(writer,connect_timeout=6) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ WRITE")
            cur.execute("SET LOCAL statement_timeout=7000")
            cur.execute("SELECT pg_advisory_xact_lock(%s)",(20261014003,))
            cur.execute("""
                INSERT INTO gem_source_probe
                    (probe_id,experiment_id,source_type,state,observed_at,
                     diagnostic_hash,sample_count,approved_for_trading,details)
                VALUES (%s,%s,'prices','PARTIAL',%s,%s,0,FALSE,%s::jsonb)
                ON CONFLICT (probe_id) DO NOTHING RETURNING probe_id
            """,(key,EXPERIMENT,datetime.now(timezone.utc),digest,
                 json.dumps({"provider":RESEARCH_PROVIDER,"ticker":symbol,
                             "attempt_day":day,
                             "validation":"PERSONAL_RESEARCH_ATTEMPT_RESERVED",
                             "trading_authorized":False})))
            new=cur.fetchone() is not None
        conn.commit()
    return new


def _store_candidate(writer,candidate,observed):
    ticker=candidate["marketstack_ticker"]
    session=candidate["bar"]["session"]
    raw=json.dumps(candidate["bar"],sort_keys=True,separators=(",",":"),allow_nan=False)
    digest=sha256(raw.encode()).hexdigest()
    if digest!=candidate["normalized_row_sha256"]:
        raise YahooAutoHold("Candidate normalization fingerprint mismatch")
    key="gem-yahoo-research-"+observed.strftime("%Y%m")+"-"+ticker+"-"+session+"-"+digest[:16]
    receipt={
        "receipt_id":key,
        "provider":RESEARCH_PROVIDER,
        "observed_at":observed,
        "source_uri":"https://finance.yahoo.com/quote/"+candidate["yahoo_query_symbol"]+"/history",
        "source_sha256":digest,
        "coverage_status":"UNKNOWN",
        "metadata":{
            "marketstack_ticker":ticker,
            "yahoo_query_symbol":candidate["yahoo_query_symbol"],
            "symbol_alias_used":candidate["symbol_alias_used"],
            "session":session,
            "normalized_bar":candidate["bar"],
            "normalized_row_sha256":digest,
            "raw_http_response_sha256":None,
            "raw_provider_bytes_retained":False,
            "close_adjustment_parity_reviewed":False,
            "source_qa_status":"PENDING_PERSONAL_RESEARCH",
            "adjustment_parity_reviewed":False,
            "research_validation":"GAP_CANDIDATE_ONLY",
            "original_marketstack_untouched":True,
            "trading_approved":False,
            "research_use":"PERSONAL_NONCOMMERCIAL_DIAGNOSTICS_ONLY",
        },
    }
    probe={"probe_id":key+"-probe","source_type":"prices","state":"PARTIAL",
           "observed_at":observed,"diagnostic_hash":digest,"sample_count":1,
           "details":{"provider":RESEARCH_PROVIDER,"ticker":ticker,"session":session,
                      "candidate":"YFINANCE_SOURCE_ONLY_NOT_INDEPENDENT_PRICE_PARITY",
                      "candidate_hash":digest,"not_raw_http_sha":True,
                      "trading_authorized":False}}
    with psycopg.connect(writer,connect_timeout=6) as conn:
        write_observation(conn,receipt,probe)
    return 1


def _record_hold(writer,symbol,day,reason,observed):
    # No raw Yahoo error text, which may contain private URLs or cookies.
    reason=str(reason).split(":")[0][:60]
    digest=sha256((symbol+day+reason).encode()).hexdigest()
    probe={"probe_id":"gem-yahoo-personal-hold-"+day+"-"+symbol+"-"+digest[:12],
           "source_type":"prices","state":"BLOCKED",
           "observed_at":observed,"diagnostic_hash":digest,"sample_count":0,
           "details":{"provider":RESEARCH_PROVIDER,"ticker":symbol,
                      "reason_code":reason,"review_required":True,
                      "trading_authorized":False}}
    with psycopg.connect(writer,connect_timeout=6) as conn:
        write_observation(conn,None,probe)


def research_batch(*,max_tickers=2,now=None,fetch_fn=None):
    """Bounded autonomous personal research; never provider certification.

    No automatic self-approval, no broker connection, and no direct Marketstack
    mutation even when Yahoo observes the otherwise missing date.
    """
    if type(max_tickers) is not int or not 1<=max_tickers<=5:
        raise YahooAutoHold("Max five tickers per research cycle")
    reader,writer=_config()
    now=now or datetime.now(timezone.utc)
    day=_iso_day(now)
    work=pending_worklist(reader=reader,now=now,limit=max_tickers)
    report={"schema":"gem-yahoo-autonomous-personal-research-v1",
            "requested":0,"candidate_bars":0,"held":0,
            "already_available":work["already_available"],
            "retry_backoff_symbols":work["retry_backoff_symbols"],
            "certified":False,"trading_authorized":False}
    if not work["pending"]:
        report["state"]=("NEEDS_REVIEW_OR_NEXT_DAY" if work["retry_backoff_symbols"]
                         else "NO_TARGETED_GAPS_PENDING")
        return report
    for symbol,wanted in work["pending"].items():
        if not _reserve_attempt(writer,symbol,day):
            continue
        report["requested"]+=1
        result=collect_candidates([symbol],wanted_sessions={symbol:wanted},fetch_fn=fetch_fn,now=now)
        for candidate in result["candidates"]:
            report["candidate_bars"]+=_store_candidate(writer,candidate,now)
        for hold in result["holds"]:
            _record_hold(writer,symbol,day,hold["reason"],now)
            report["held"]+=1
    report["state"]="PROVISIONAL_PERSONAL_RESEARCH_ONLY"
    return report
