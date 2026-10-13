"""Batch corporate-event *discovery* from stored original SEC submission bytes.

No SEC network requests, no brokerage instructions, no automatic shares/cash
adjustment. An SEC 8-K item is a review lead, not event certification.
Uses existing dedicated GEM-only read and INSERT-only database roles.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
import re

import psycopg

from gem_data.gem_public_ingest import EXPERIMENT, write_observation
from gem_data.sec_independent_fact_verify import decode_original_receipt, VerificationHold
from gem_data.sec_corporate_event_discovery import (
    discover_sec_event_candidates, CorporateEventHold,
)

CIK_MEMBER = re.compile(r"^CIK([0-9]{10})\.json$")


class SECEventScanHold(ValueError):
    pass


def scan_batch(*,max_ciks=5):
    if type(max_ciks) is not int or not 1<=max_ciks<=10:
        raise SECEventScanHold("Corporate event scan batch limited to ten CIKs")
    reader=os.environ.get("GEM_READONLY_DATABASE_URL","")
    writer=os.environ.get("GEM_INGEST_DATABASE_URL","")
    if (not reader.startswith("postgresql://gem_web_readonly:")
            or not writer.startswith("postgresql://gem_source_ingest_limited:")):
        raise SECEventScanHold("Restricted GEM source audit role not configured")
    observed=datetime.now(timezone.utc)
    stamp=observed.strftime("%Y%m%d")
    prefix="gem-sec-corporate-8k-"+stamp+"-"
    with psycopg.connect(reader,connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SET LOCAL statement_timeout=10000")
            cur.execute("""
                SELECT DISTINCT ON (metadata->>'zip_member_name')
                    receipt_id,source_sha256,source_uri,metadata
                FROM gem_source_receipt
                WHERE experiment_id=%s AND provider='SEC_ZIP_SUBMISSIONS'
                ORDER BY metadata->>'zip_member_name',observed_at DESC,receipt_id DESC
            """,(EXPERIMENT,))
            rows=cur.fetchall()
            cur.execute("""
                SELECT probe_id FROM gem_source_probe
                WHERE experiment_id=%s AND probe_id LIKE %s
            """,(EXPERIMENT,prefix+"%"))
            done={row[0] for row in cur.fetchall()}
    remaining=[]
    for rid,digest,uri,metadata in rows:
        found=CIK_MEMBER.fullmatch(metadata.get("zip_member_name",""))
        if not found:
            continue
        cik=found.group(1)
        key=prefix+cik+"-"+sha256((rid+str(digest)).encode()).hexdigest()[:16]
        if key not in done:
            remaining.append((key,cik,rid,digest,uri,metadata))
    selected=remaining[:max_ciks]
    report={"total_source_receipts":len(rows),"remaining_before":len(remaining),
            "scanned":0,"candidate_events":0,"failed":0,"certified_events":0}
    with psycopg.connect(writer,connect_timeout=5) as conn:
        for key,cik,rid,digest,uri,metadata in selected:
            try:
                original=decode_original_receipt(
                    {"provider":"SEC_ZIP_SUBMISSIONS","source_uri":uri,
                     "metadata":metadata,"source_sha256":digest},cik,"submissions")
                discovery=discover_sec_event_candidates(
                    original,cutoff=observed.date().isoformat(),lookback_days=100)
                classification="SEC_8K_CANDIDATE_ONLY"
                events=discovery["event_candidates"]
            except (VerificationHold,CorporateEventHold,ValueError):
                classification="SEC_ORIGINAL_REVIEW_HOLD"
                events=[]
                report["failed"]+=1
            payload={"cik":cik,"receipt_id":rid,"classification":classification,
                     "candidate_count":len(events),
                     "review_queue":events[:10],
                     "more_candidates_not_shown":max(0,len(events)-10),
                     "economic_terms_certified":False,
                     "issuer_or_exchange_action_ledger_complete":False,
                     "trading_authorized":False}
            fingerprint=sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
            probe={"probe_id":key,"source_type":"actions","state":"PARTIAL",
                   "observed_at":observed,"diagnostic_hash":fingerprint,
                   "sample_count":len(events),"details":payload}
            write_observation(conn,None,probe)
            conn.commit()
            report["scanned"]+=1
            report["candidate_events"]+=len(events)
    report["remaining_after"]=len(remaining)-report["scanned"]
    return report
