"""Batch source-evidence reconciliation for every outstanding GEM SEC CIK.

Read-only original SEC audit and Inline XBRL observations; append-only
classification probes, one immutable result per unique evidence pair.
Noncomparable bank income terms, custom tags and missing facts never become
invented revenue/operating income. No investing or broker permissions.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os

import psycopg

from gem_data.gem_public_ingest import EXPERIMENT, write_observation
from gem_data.gem_sec_reconciliation import (
    ReconciliationHold, evidence_key, reconcile_one,
)
from gem_data.sec_fact_audit_worker import qa_as_of

PREFIX="gem-sec-reconcile-"


class SECReconcileWorkerHold(RuntimeError):
    pass


def _get_pending(conn, *, cutoff, batch_size):
    with conn.cursor() as cur:
        cur.execute("""
            WITH qa AS (
              SELECT DISTINCT ON (substring(details->>'scope' FROM 'CIK ([0-9]{10})'))
                substring(details->>'scope' FROM 'CIK ([0-9]{10})') AS cik,
                probe_id qa_id, details qa_details
              FROM gem_source_probe
              WHERE experiment_id=%s AND source_type='sec'
                AND details->>'scope' LIKE 'Independent automated recomputation for CIK %%'
                AND details->>'as_of'=%s
              ORDER BY substring(details->>'scope' FROM 'CIK ([0-9]{10})'),
                       observed_at DESC, probe_id DESC
            ),
            src AS (
              SELECT DISTINCT ON (details->>'cik')
                details->>'cik' cik, probe_id original_id, details source_details
              FROM gem_source_probe
              WHERE experiment_id=%s AND source_type='sec'
                AND probe_id LIKE 'gem-sec-inline-review-%%'
                AND details->>'as_of'=%s
              ORDER BY details->>'cik',observed_at DESC,probe_id DESC
            )
            SELECT qa.cik,qa.qa_id,qa.qa_details,src.original_id,src.source_details
            FROM qa JOIN src USING(cik)
            WHERE qa.qa_details->>'fact_status'='UNKNOWN'
            ORDER BY qa.cik
        """,(EXPERIMENT,cutoff,EXPERIMENT,cutoff))
        candidates=cur.fetchall()
        cur.execute("""
            SELECT probe_id FROM gem_source_probe
            WHERE experiment_id=%s AND probe_id LIKE %s
        """,(EXPERIMENT,PREFIX+cutoff.replace("-","")+"-%"))
        completed={x[0] for x in cur.fetchall()}
    chosen=[]
    for cik,qa_id,qa,original_id,source in candidates:
        key=evidence_key(cik,cutoff,qa_id,original_id)
        if key not in completed:
            chosen.append((key,cik,qa_id,qa,original_id,source))
    return chosen[:batch_size],len(chosen),len(candidates)


def reconcile_batch(*, max_issuers=25):
    if type(max_issuers) is not int or not 1<=max_issuers<=25:
        raise SECReconcileWorkerHold("SEC reconciliation batch max 25")
    readonly=os.getenv("GEM_READONLY_DATABASE_URL","")
    insert=os.getenv("GEM_INGEST_DATABASE_URL","")
    if not readonly.startswith("postgresql://gem_web_readonly:"):
        raise SECReconcileWorkerHold("GEM read-only database role missing")
    if not insert.startswith("postgresql://gem_source_ingest_limited:"):
        raise SECReconcileWorkerHold("GEM append-only writer role missing")
    observed=datetime.now(timezone.utc)
    cutoff=qa_as_of(observed=observed).isoformat()
    with psycopg.connect(readonly,connect_timeout=6) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute("SET LOCAL statement_timeout=10000")
        queue,remaining,total=_get_pending(conn,cutoff=cutoff,batch_size=max_issuers)
    result={
        "as_of":cutoff,"unresolved_with_original_review":total,
        "remaining_before":remaining,"written":0,
        "categories":{},"held":0,"certified":0,"trading_enabled":False,
    }
    if not queue:
        return result
    with psycopg.connect(insert,connect_timeout=6) as conn:
        for key,cik,qa_id,qa,orig_id,source in queue:
            try:
                resolution=reconcile_one(cik,qa,source,as_of=cutoff)
                resolution["machine_qa_probe_id"]=qa_id
                resolution["original_review_probe_id"]=orig_id
            except (ReconciliationHold,TypeError,ValueError):
                resolution={
                    "schema":"gem-sec-machine-reconciliation-v1",
                    "cik":cik,"as_of":cutoff,
                    "resolution_code":"INCONSISTENT_EVIDENCE_MANUAL_HOLD",
                    "machine_qa_probe_id":qa_id,
                    "original_review_probe_id":orig_id,
                    "reconciled_machine_candidate_not_certified":False,
                    "independently_verified":False,
                    "financial_ineligibility_proven":False,
                    "eligible_for_ranking":False,
                    "trade_authorization":False,
                }
                result["held"]+=1
            category=resolution["resolution_code"]
            result["categories"][category]=result["categories"].get(category,0)+1
            digest=sha256(json.dumps(resolution,sort_keys=True,
                            separators=(",",":")).encode()).hexdigest()
            probe={"probe_id":key,"source_type":"sec","state":"PARTIAL",
                   "observed_at":observed,"diagnostic_hash":digest,
                   "sample_count":int(resolution.get(
                       "six_original_quarter_fact_candidates",False))*6,
                   "details":resolution}
            write_observation(conn,None,probe)
            conn.commit()
            result["written"]+=1
    result["remaining_after_estimate"]=remaining-result["written"]
    return result
