"""Independent read-only Python machine-QA stages for GEM evidence.

Machine PASS certifies exactly the tested property (SHA integrity, published
source presence or numeric coverage), not source licensing, adjusted-close
parity, original Inline XBRL context, reviewer signoff or broker readiness.

Used by the autonomous release robot. Never changes strategy or source tables.
"""
from __future__ import annotations

from datetime import datetime, timezone
import os

import psycopg

from gem_data.gem_public_ingest import EXPERIMENT


class MachineEvidenceUnavailable(RuntimeError):
    pass


def _stage(key,passed,passed_count,required_count,scope,next_step):
    if any(type(x) is not int or x<0 for x in (passed_count,required_count)):
        raise MachineEvidenceUnavailable("Invalid machine QA count")
    if type(passed) is not bool:
        raise MachineEvidenceUnavailable("Invalid machine QA state")
    return {"key":key,"passed":passed,
            "observed":passed_count,"required":required_count,
            "scope":scope,"next_action":next_step,
            "trading_authorized":False}


def project_machine_qa(integrity,price,sec_audit,*,at=None,ibkr_audit=None):
    """Recomputes narrow machine QA gates; no upgrade of source_approval."""
    at=at or datetime.now(timezone.utc)
    if at.tzinfo is None:
        raise MachineEvidenceUnavailable("Timezone-aware timestamp required")
    if (integrity.get("data_access")!="CONNECTED"
            or price.get("data_access")!="CONNECTED"):
        raise MachineEvidenceUnavailable("Source evidence unavailable")
    collected=price.get("collection") or {}
    receipt=price.get("stored_receipt_audit") or {}
    yahoo=price.get("yahoo_research") or {}
    if not isinstance(sec_audit,dict):
        raise MachineEvidenceUnavailable("SEC QA counts unavailable")
    quantities=(
        collected.get("marketstack_histories_stored"),
        collected.get("security_lines_target"),
        collected.get("histories_with_at_least_127_bars"),
        collected.get("histories_with_rejected_vendor_rows"),
        receipt.get("audited"),receipt.get("integrity_pass"),
        sec_audit.get("paired_issuers"),sec_audit.get("original_sha_pass"),
        sec_audit.get("six_fact_candidate_complete"),
        sec_audit.get("missing_or_ambiguous"),
        yahoo.get("stored_personal_research_candidates",0),
        yahoo.get("targeted_vendor_close_gaps",0),
    )
    if any(type(x) is not int or x<0 for x in quantities):
        raise MachineEvidenceUnavailable("Malformed machine QA counters")
    (histories,target,histories127,bad,audited,good,paired,sha_ok,
     complete,unresolved,yahoo_candidates,gaps)=quantities
    ibkr_audit=ibkr_audit if ibkr_audit is not None else {
        "compared":0,"agreed":0,"conflicts":0}
    if (not isinstance(ibkr_audit,dict) or
            any(type(ibkr_audit.get(k)) is not int or ibkr_audit[k]<0
                for k in ("compared","agreed","conflicts"))):
        raise MachineEvidenceUnavailable("Invalid IBKR reconciliation evidence")
    if (not 480<=target<=600 or target!=integrity.get("membership_security_lines")
            or histories>target or audited>histories or good>audited
            or sha_ok>paired or complete>paired
            or complete+unresolved>paired or yahoo_candidates>gaps
            or ibkr_audit["compared"]>yahoo_candidates
            or ibkr_audit["agreed"]+ibkr_audit["conflicts"]>ibkr_audit["compared"]):
        raise MachineEvidenceUnavailable("Inconsistent evidence universe")
    by={x.get("key"):x for x in integrity.get("sources",[]) if isinstance(x,dict)}
    if set(by)!={"prices","sec","membership","actions","calendar","benchmark"}:
        raise MachineEvidenceUnavailable("Six source categories required")
    def published(key):
        stages=by[key].get("stages") or []
        return bool(stages and stages[0].get("state")=="COMPLETE")
    membership=by["membership"].get("stages") or []
    matched=(len(membership)>=3 and membership[2].get("state")=="COMPLETE"
             and integrity.get("membership_security_lines")==target)
    scan_count=integrity.get("corporate_issuer_scans")
    if type(scan_count) is not int or scan_count<0:
        raise MachineEvidenceUnavailable("Corporate scan count unavailable")
    stages=[
        _stage("current_member_cik_crosscheck",bool(matched),
               target if matched else 0,target,
               "Two current membership sources agree on ticker/CIK, not historical effective dates",
               "Obtain official effective-dated member additions/removals"),
        _stage("marketstack_receipt_sha_ohlc",histories>0 and audited==histories and good==histories,
               good,histories,
               "Byte/hash/nominal OHLC integrity for stored rows; rejects in vendor source still held",
               "Reconcile vendor-rejected close rows and adjusted basis"),
        _stage("complete_vendor_daily_histories",histories==target and histories127==target and bad==0,
               histories127,target,
               "Full history and zero rejected vendor rows; not independent parity",
               "Use authorized independent history to fix market gaps and short listings"),
        _stage("original_sec_member_sha",paired>=500 and sha_ok==paired,
               sha_ok,paired,
               "SEC original ZIP member SHA and CIK identity only, not financial semantic QA",
               "Resolve missing/ambiguous original Inline XBRL contexts"),
        _stage("sec_machine_six_fact_candidate",paired>=500 and complete==paired and unresolved==0,
               complete,paired,
               "Same-quarter original 10-Q machine candidate detection, not reviewer certification",
               "Resolve 184 missing/ambiguous issuer original SEC fact contexts"),
        _stage("issuer_action_discovery",scan_count>=500,scan_count,500,
               "Original SEC issuer event discovery only; not economic terms",
               "Reconcile action effective/ex/pay dates and resulting portfolio ledger"),
        _stage("published_nyse_schedule",published("calendar"),
               int(published("calendar")),1,
               "Published exchange holiday/schedule source only, not completed-session proof",
               "Crosscheck completed RTH bars, exchange disruptions and half days"),
        _stage("published_spy_distribution_schedule",published("benchmark"),
               int(published("benchmark")),1,
               "Official distribution schedule collected, not SPY total-return parity",
               "Recompute SPY OHLCV and cash distributions from independently sourced originals"),
        _stage("yahoo_personal_gap_discovery",gaps>0 and yahoo_candidates==gaps,
               yahoo_candidates,gaps,
               "Personal research candidate coverage only, never nominal/adjusted price certification",
               "Use entitled IBKR or another licensed source to corroborate candidate bars"),
        _stage("ibkr_yahoo_historical_ohlcv_agreement",
               gaps>0 and ibkr_audit["agreed"]==gaps and ibkr_audit["conflicts"]==0,
               ibkr_audit["agreed"],gaps,
               "Nominal OHLCV agreement only; adjustment parity and broker entitlement separate",
               "Connect an entitled read-only IBKR Web API session; verify source provenance and conflicts"),
    ]
    return {"schema":"gem-python-machine-qa-v1",
            "checked_at":at.astimezone(timezone.utc).isoformat(),
            "state":"MACHINE_DIAGNOSTICS_ONLY",
            "machine_checks_passed":sum(g["passed"] for g in stages),
            "machine_checks_total":len(stages),
            "independent_source_approval":False,
            "trading_enabled":False,
            "checks":stages}


def read_sec_machine_audit():
    """Latest code/evidence-specific original pair audit per CIK.

    Counting every historic QA probe would falsely imply 1000+ distinct issuers
    from revision reruns. Count only the newest row per verified CIK.
    """
    reader=os.getenv("GEM_READONLY_DATABASE_URL","")
    if not reader.startswith("postgresql://gem_web_readonly:"):
        raise MachineEvidenceUnavailable("Restricted GEM read-only database required")
    try:
        with psycopg.connect(reader,connect_timeout=6) as conn:
            with conn.cursor() as cur:
                cur.execute("SET TRANSACTION READ ONLY")
                cur.execute("SET LOCAL statement_timeout=12000")
                cur.execute("""
                    WITH latest AS (
                      SELECT DISTINCT ON
                          (substring(details->>'scope' FROM 'CIK ([0-9]{10})'))
                        substring(details->>'scope' FROM 'CIK ([0-9]{10})') cik,
                        details
                      FROM gem_source_probe
                      WHERE experiment_id=%s AND source_type='sec'
                        AND probe_id LIKE 'gem-sec-fact-qa-%%'
                        AND details->>'scope' LIKE 'Independent automated recomputation for CIK %%'
                      ORDER BY substring(details->>'scope' FROM 'CIK ([0-9]{10})'),
                               observed_at DESC,probe_id DESC
                    )
                    SELECT COUNT(*) AS paired,
                      COUNT(*) FILTER(WHERE details->>'receipt_integrity'='PASS') AS raw_pass,
                      COUNT(*) FILTER(WHERE details->>'fact_status'='CANDIDATE_COMPLETE_NOT_CERTIFIED') AS six_complete,
                      COUNT(*) FILTER(WHERE details->>'fact_status'='UNKNOWN') AS missing_or_ambiguous
                    FROM latest
                """,(EXPERIMENT,))
                row=cur.fetchone()
    except psycopg.Error:
        raise MachineEvidenceUnavailable("SEC original audit evidence unavailable") from None
    if row is None:
        raise MachineEvidenceUnavailable("SEC original QA query returned no evidence")
    return dict(zip(("paired_issuers","original_sha_pass",
                     "six_fact_candidate_complete","missing_or_ambiguous"),
                    (int(x) for x in row)))


def read_ibkr_machine_crosschecks():
    """Latest append-only IBKR source-agreement states, without promoting QA PASS."""
    reader=os.getenv("GEM_READONLY_DATABASE_URL","")
    if not reader.startswith("postgresql://gem_web_readonly:"):
        raise MachineEvidenceUnavailable("Restricted GEM read-only database required")
    try:
        with psycopg.connect(reader,connect_timeout=6) as conn:
            with conn.cursor() as cur:
                cur.execute("SET TRANSACTION READ ONLY")
                cur.execute("SET LOCAL statement_timeout=8000")
                cur.execute("""
                    WITH latest AS (
                        SELECT DISTINCT ON (details->>'ticker',details->>'session')
                               details
                        FROM gem_source_probe
                        WHERE experiment_id=%s AND source_type='prices'
                          AND probe_id LIKE 'gem-ibkr-independent-price-check-%%'
                        ORDER BY details->>'ticker',details->>'session',
                                 observed_at DESC,probe_id DESC
                    )
                    SELECT COUNT(*),
                           COUNT(*) FILTER(WHERE details->>'state'='PROVISIONAL_TWO_SOURCE_PRICE_MATCH'),
                           COUNT(*) FILTER(WHERE details->>'state'='PROVIDER_DISAGREEMENT_HOLD')
                    FROM latest
                """,(EXPERIMENT,))
                counts=cur.fetchone()
    except psycopg.Error:
        raise MachineEvidenceUnavailable("IBKR second-source evidence unavailable") from None
    if counts is None:
        raise MachineEvidenceUnavailable("Second-source evidence unreadable")
    return dict(zip(("compared","agreed","conflicts"),(int(x) for x in counts)))
