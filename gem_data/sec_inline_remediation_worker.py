"""Bounded original SEC 10-Q Inline XBRL remediation for unresolved GEM issuers.

Starts with stored verified SEC submissions ZIP member (not guessed forms).
Fetches original current/prior-year 10-Q HTML from primary sec.gov, checks
accession identity and monetary contexts, appends immutable review evidence.
Never overwrites SEC companyfacts, declares a financial metric equivalent, or
certifies a GEM recommendation. Separate source review is still required.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from hashlib import sha256
import json
import os
import re

import psycopg

from gem_data.gem_public_ingest import EXPERIMENT, write_observation
from gem_data.sec_independent_fact_verify import decode_original_receipt, VerificationHold
from gem_data.sec_fact_audit_worker import qa_as_of
from gem_data.sec_inline_xbrl_evidence import extract_inline_candidates, InlineEvidenceHold
from gem_data.gem_sec_annual_context import select_annual_original, summarize_annual_original
from gem_data.sec_historical_submissions import (historical_fragment_urls, merge_archived_filings, ArchiveHistoryHold)
from gem_data.sec_original_collector import SecOriginalCollector, SourceUnavailable, validate_sec_user_agent

_ACC = re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")
_DOC = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
PREFIX = "gem-sec-inline-review-"
REV = "20261013-v4-historical-submissions"


class InlineReviewHold(ValueError):
    pass


def select_original_filing_pair(submissions, *, cutoff):
    """Choose original latest 10-Q and same fiscal quarter year before.

    Retains the actual report-period date, accession and original file.
    10-Q/A amendments must be reviewed separately by frozen source rules.
    """
    recent = ((submissions.get("filings") or {}).get("recent") or {})
    names = ("form","accessionNumber","filingDate","reportDate","primaryDocument")
    arrays = [recent.get(k) for k in names]
    if any(not isinstance(x,list) for x in arrays) or len({len(x) for x in arrays})!=1:
        raise InlineReviewHold("Original SEC filing index incomplete")
    selected=[]
    for form, accession, filed, report, document in zip(*arrays):
        if form!="10-Q" or not isinstance(accession,str) or not _ACC.fullmatch(accession):
            continue
        if not isinstance(document,str) or not _DOC.fullmatch(document) or document.startswith("."):
            continue
        try:
            filed_day=date.fromisoformat(filed)
            period_end=date.fromisoformat(report)
        except (ValueError, TypeError):
            continue
        if filed_day>=cutoff or period_end>cutoff:
            continue
        selected.append({"accession":accession,"filed":filed,
                         "period_end":report,"primary_document":document})
    if not selected:
        raise InlineReviewHold("No eligible original 10-Q filing at cutoff")
    selected.sort(key=lambda x:(x["period_end"],x["filed"],x["accession"]),reverse=True)
    current=selected[0]
    if (cutoff-date.fromisoformat(current["filed"])).days > 210:
        raise InlineReviewHold("Current financials stale under frozen 210-day rule")
    current_day=date.fromisoformat(current["period_end"])
    prior=[x for x in selected[1:]
           if 310<=(current_day-date.fromisoformat(x["period_end"])).days<=420]
    prior.sort(key=lambda x:abs((current_day-date.fromisoformat(x["period_end"])).days-365))
    if not prior:
        raise InlineReviewHold("Prior year original 10-Q filing missing in recent submissions")
    return current,prior[0]


def original_primary_url(cik, filing):
    return ("https://www.sec.gov/Archives/edgar/data/"
            +str(int(cik))+"/"+filing["accession"].replace("-","")+"/"
            +filing["primary_document"])


def summarize_pair(now, previous):
    """Review *possibilities* for six inputs; never infer concept equivalence.

    Ambiguous direct US GAAP values and custom extension concepts remain
    explicitly unresolved. The standard facts must have undimensioned
    direct-quarter USD contexts ending at the selected filing report date.
    """
    rows={}
    for label, item in (("current",now),("prior",previous)):
        try:
            end=date.fromisoformat(item["period_end"])
        except (KeyError,ValueError,TypeError):
            raise InlineReviewHold("Original report date absent")
        doc=item["evidence"]
        standard={}
        extensions=[]
        for f in doc["candidates"]:
            try:
                duration=(end-date.fromisoformat(f["start"])).days
            except (ValueError,KeyError):
                continue
            if f["end"] != end.isoformat() or not 60<=duration<=125:
                continue
            if f["category"].startswith("STANDARD_"):
                standard.setdefault(f["category"],set()).add(f["amount_usd"])
            elif f["category"]=="ISSUER_EXTENSION_REVIEW_ONLY":
                extensions.append(f["concept"])
        rows[label]={
            "period_end":end.isoformat(),
            "standard_unique_values":{tag:sorted(vals) for tag,vals in standard.items()},
            "issuer_extensions_to_review":sorted(set(extensions))[:35],
            "ambiguous_standard_concepts":[tag for tag,vals in standard.items() if len(vals)>1],
            "direct_quarter_category_count":sum(len(vals)==1 for vals in standard.values()),
            "missing_standard_categories":[category for category in
                ("STANDARD_REVENUE","STANDARD_OPERATING_INCOME",
                 "STANDARD_PARENT_NET_INCOME")
                if category not in standard],
            "issuer_extension_present":bool(extensions),
            "original_raw_sha256":doc["original_raw_sha256"],
            "accession":item["accession"],
        }
    all_standard = all(
        len(rows[label]["standard_unique_values"].get(kind,[]))==1
        for label in ("current","prior")
        for kind in ("STANDARD_REVENUE","STANDARD_OPERATING_INCOME","STANDARD_PARENT_NET_INCOME")
    )
    return {"current":rows["current"],"prior":rows["prior"],
            "all_six_standard_category_candidates":all_standard,
            "status":("SIX_DIRECT_STANDARD_CANDIDATES_NEED_CONTEXT_REVIEW"
                      if all_standard else "ORIGINAL_10Q_EXCEPTION_REVIEW_REQUIRED"),
            "certified":False,"trading_authorized":False}


def _work_items(conn, as_of, limit):
    """Read only receipt keys for the queue; fetch raw bytes for selected CIKs."""
    with conn.cursor() as cur:
        cur.execute("""
            WITH latest AS (
              SELECT DISTINCT ON (substring(details->>'scope' FROM 'CIK ([0-9]{10})'))
                 substring(details->>'scope' FROM 'CIK ([0-9]{10})') AS cik,
                 details->>'fact_status' AS status
              FROM gem_source_probe
              WHERE experiment_id=%s AND source_type='sec'
                AND details->>'scope' LIKE 'Independent automated recomputation for CIK %%'
              ORDER BY substring(details->>'scope' FROM 'CIK ([0-9]{10})'),
                       observed_at DESC,probe_id DESC
            )
            SELECT latest.cik,src.receipt_id
            FROM latest
            JOIN LATERAL (
               SELECT receipt_id
               FROM gem_source_receipt
               WHERE experiment_id=%s AND provider='SEC_ZIP_SUBMISSIONS'
                 AND metadata->>'zip_member_name'='CIK'||latest.cik||'.json'
               ORDER BY observed_at DESC, receipt_id DESC LIMIT 1
            ) AS src ON TRUE
            WHERE latest.status!='CANDIDATE_COMPLETE_NOT_CERTIFIED'
            ORDER BY latest.cik
        """,(EXPERIMENT,EXPERIMENT))
        candidates=cur.fetchall()
        cur.execute("""
            SELECT probe_id FROM gem_source_probe
            WHERE experiment_id=%s AND probe_id LIKE %s
        """,(EXPERIMENT,PREFIX+as_of.strftime("%Y%m%d")+"-%"))
        completed={x[0] for x in cur.fetchall()}
        remaining=[]
        for cik,rid in candidates:
            key=(PREFIX+as_of.strftime("%Y%m%d")+"-"+cik+"-"+REV
                 +"-"+sha256(rid.encode()).hexdigest()[:12])
            today_retry=key+"-retry-"+datetime.now(timezone.utc).strftime("%Y%m%d")
            if key not in completed and today_retry not in completed:
                remaining.append((cik,key,rid))
        priority=os.getenv("GEM_SEC_INLINE_PRIORITY_CIK","").strip()
        if priority and not re.fullmatch(r"[0-9]{10}",priority):
            raise InlineReviewHold("Invalid bounded SEC priority CIK configuration")
        if priority:
            remaining.sort(key=lambda x:(x[0]!=priority,x[0]))
        selected=remaining[:limit]
        ids=[rid for _cik,_key,rid in selected]
        receipts={}
        if ids:
            cur.execute("""
                SELECT receipt_id,provider,source_sha256,source_uri,metadata
                FROM gem_source_receipt
                WHERE experiment_id=%s AND receipt_id=ANY(%s)
            """,(EXPERIMENT,ids))
            receipts={rid:{"provider":provider,"source_sha256":sha,
                           "source_uri":uri,"metadata":metadata}
                      for rid,provider,sha,uri,metadata in cur.fetchall()}
    chosen=[]
    for cik,key,rid in selected:
        if rid not in receipts:
            raise InlineReviewHold("Stored original SEC submissions receipt missing")
        chosen.append((cik,key,receipts[rid]))
    return chosen,len(remaining)


def review_batch(*, max_ciks=2, collector_factory=SecOriginalCollector):
    if type(max_ciks) is not int or not 1<=max_ciks<=6:
        raise InlineReviewHold("Inline XBRL batch capped at 6 issuers")
    read=os.getenv("GEM_READONLY_DATABASE_URL","")
    write=os.getenv("GEM_INGEST_DATABASE_URL","")
    if (not read.startswith("postgresql://gem_web_readonly:")
            or not write.startswith("postgresql://gem_source_ingest_limited:")):
        raise InlineReviewHold("Restricted GEM-only database roles missing")
    agent=validate_sec_user_agent(os.getenv("SEC_USER_AGENT",""))
    now=datetime.now(timezone.utc)
    as_of=qa_as_of(observed=now)
    with psycopg.connect(read,connect_timeout=6) as conn:
        batch,remaining=_work_items(conn,as_of,max_ciks)
    report={"target_cutoff":as_of.isoformat(),"remaining_before":remaining,
            "attempted":0,"original_documents_fetched":0,
            "six_direct_candidates_found":0,"held":[],"certified":0}
    if not batch:
        return report
    with collector_factory(agent,max_bytes=24_000_000) as client:
        for cik,key,receipt in batch:
            evidence = None
            annual_evidence = None
            urls = []
            reason = None
            annual_reason = None
            history_receipts = []
            try:
                submission=decode_original_receipt(receipt,cik,"submissions")
                try:
                    try:
                        current,prior=select_original_filing_pair(submission,cutoff=as_of)
                    except InlineReviewHold as missing_prior:
                        if "Prior year original 10-Q filing missing" not in str(missing_prior):
                            raise
                        fragments=[]
                        for uri in historical_fragment_urls(submission,cik,cutoff=as_of):
                            _,source_bytes=client.get(uri)
                            fragments.append((uri,source_bytes))
                        if not fragments:
                            raise
                        expanded,history_receipts=merge_archived_filings(submission,fragments)
                        current,prior=select_original_filing_pair(expanded,cutoff=as_of)
                    analyzed=[]
                    for filing in (current,prior):
                        url=original_primary_url(cik,filing)
                        _source,raw=client.get(url)
                        urls.append(url)
                        candidate=extract_inline_candidates(raw,cik=cik,
                              accession=filing["accession"],source_uri=url)
                        analyzed.append({**filing,"evidence":candidate})
                        report["original_documents_fetched"]+=1
                    evidence=summarize_pair(*analyzed)
                    if evidence["all_six_standard_category_candidates"]:
                        report["six_direct_candidates_found"]+=1
                except (InlineReviewHold,InlineEvidenceHold,SourceUnavailable,
                        ValueError,TypeError) as exc:
                    reason=type(exc).__name__+":"+str(exc)[:90]
                # Fetch the issuer's original 10-K as separately classified
                # supplementary evidence, including fiscal-Q4 context.
                # This NEVER converts an annual fact into an eligible 10-Q
                # direct-quarter input or bypasses stale/missing-quarter holds.
                annual=select_annual_original(submission,cutoff=as_of)
                if annual is not None:
                    try:
                        url=original_primary_url(cik,annual)
                        _source,raw=client.get(url)
                        urls.append(url)
                        annual_evidence=summarize_annual_original(
                            raw,cik=cik,filing=annual,source_uri=url)
                        report["original_documents_fetched"]+=1
                    except (InlineEvidenceHold,SourceUnavailable,ValueError,
                            TypeError) as exc:
                        annual_reason=type(exc).__name__+":"+str(exc)[:90]
                else:
                    annual_reason="NO_ELIGIBLE_ORIGINAL_10K_AT_CUTOFF"
            except (VerificationHold,InlineReviewHold,ValueError,
                    TypeError) as exc:
                reason=type(exc).__name__+":"+str(exc)[:90]
            if annual_evidence is not None:
                if evidence is None:
                    evidence={
                        "status":"ANNUAL_10K_SUPPLEMENT_ONLY_10Q_DISCREPANCY_OPEN",
                        "all_six_standard_category_candidates":False,
                        "certified":False,"trading_authorized":False,
                    }
                evidence["original_10k_supplement"]=annual_evidence
            if reason is not None:
                report["held"].append({"cik":cik,"reason":reason})
            if annual_reason is not None and annual_reason != "NO_ELIGIBLE_ORIGINAL_10K_AT_CUTOFF":
                report.setdefault("annual_source_holds",[]).append(
                    {"cik":cik,"reason":annual_reason})
            # Network outages may retry on the NEXT UTC day only.
            # Structural/context failures remain blocked until SEC source
            # receipts or the machine signal cutoff change.
            probe_key=(key+"-retry-"+now.strftime("%Y%m%d")
                       if reason and reason.startswith("SourceUnavailable:")
                       else key)
            digest=sha256(json.dumps({
                "cik":cik,"key":probe_key,"evidence":evidence,"reason":reason
            },sort_keys=True).encode()).hexdigest()
            probe={
                "probe_id":probe_key,"source_type":"sec",
                "state":"PARTIAL" if evidence else "BLOCKED",
                "observed_at":now,"diagnostic_hash":digest,
                "sample_count":len(urls),
                "details":{
                    "scope":f"Original 10-Q Inline XBRL remediation for CIK {cik}",
                    "cik":cik,"as_of":as_of.isoformat(),
                    "filing_urls":urls,"classification":(
                        evidence["status"] if evidence else "ORIGINAL_SEC_FILING_RETRIEVAL_HOLD"),
                    "evidence":evidence,"blocker":reason,
                    "annual_10k_source_hold":annual_reason,
                    "original_10k_supplement_collected":annual_evidence is not None,
                    "issuer_source_qa_approved":False,
                    "human_reviewer_approved":False,
                    "certified":False,"trading_authorized":False,
                },
            }
            with psycopg.connect(write,connect_timeout=6) as conn:
                write_observation(conn,None,probe)
            report["attempted"]+=1
    report["remaining_after_estimate"]=max(0,remaining-report["attempted"])
    return report
