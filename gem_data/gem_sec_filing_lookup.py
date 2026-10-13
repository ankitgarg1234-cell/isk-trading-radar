"""Read-only exact SEC filing lookup from the stored original submissions ZIP.

CIK-specific on-demand lookup avoids loading 500 compressed submissions into
the dashboard. Original accession, filed/accepted dates, 10-Q/10-K links and
report periods remain tied to a SHA256-validated SEC original receipt.
Never approves financial semantics or portfolio selections.
"""
from __future__ import annotations

from datetime import date
from urllib.parse import quote
import re
import os

import psycopg

from gem_data.sec_independent_fact_verify import (
    decode_original_receipt, VerificationHold,
)

EXPERIMENT="gem-v1-forward-2026-10"
CIK_RE=re.compile(r"^[0-9]{10}$")
ACCESSION_RE=re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")
DOC_RE=re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class FilingLookupHold(ValueError):
    pass


def summarize_original_filings(submissions, cik, *, as_of=date(2026,10,12)):
    if not CIK_RE.fullmatch(cik):
        raise FilingLookupHold("CIK must contain exactly 10 digits")
    if str(submissions.get("cik")).zfill(10)!=cik:
        raise FilingLookupHold("Original SEC CIK identity mismatch")
    recent=((submissions.get("filings") or {}).get("recent") or {})
    required=("form","accessionNumber","filingDate","reportDate","primaryDocument")
    cols=[recent.get(k) for k in required]
    if any(not isinstance(c,list) for c in cols) or len(set(map(len,cols)))!=1:
        raise FilingLookupHold("Original SEC filings table incomplete")
    accepted_times=recent.get("acceptanceDateTime")
    if not isinstance(accepted_times,list) or len(accepted_times)!=len(cols[0]):
        accepted_times=[None]*len(cols[0])
    records=[]
    for form,accn,filed,report,doc,accepted in zip(*cols,accepted_times):
        if form not in ("10-Q","10-Q/A","10-K","10-K/A"):
            continue
        if not isinstance(accn,str) or not ACCESSION_RE.fullmatch(accn):
            continue
        if not isinstance(doc,str) or not DOC_RE.fullmatch(doc) or doc.startswith("."):
            continue
        try:
            filed_day=date.fromisoformat(filed)
            report_day=date.fromisoformat(report)
        except (ValueError,TypeError):
            continue
        if filed_day>as_of or report_day>as_of:
            continue
        root=(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
              f"{accn.replace('-','')}/")
        record={
            "form":form,"accession":accn,"filed":filed,"report_period":report,
            "age_days_since_report":(as_of-report_day).days,
            "age_days_since_filing":(as_of-filed_day).days,
            "document_url":root+quote(doc,safe=""),
            "ix_viewer_url":("https://www.sec.gov/ix?doc=/Archives/edgar/data/"
                             +cik+"/"+accn.replace("-","")+"/"+quote(doc,safe="")),
            "filing_index_url":root+accn+"-index.htm",
            "accepted_at":accepted if isinstance(accepted,str) else None,
            "source_fact_extraction":"NOT_AUTOMATICALLY_CERTIFIED",
        }
        records.append(record)
    records.sort(key=lambda x:(x["filed"],x["report_period"],x["accession"]),reverse=True)
    latest_q=next((r for r in records if r["form"]=="10-Q"),None)
    latest_k=next((r for r in records if r["form"]=="10-K"),None)
    return {
        "schema":"gem-original-sec-filings-v1",
        "cik":cik,
        "company":submissions.get("name"),
        "as_of":as_of.isoformat(),
        "latest_original_10q":latest_q,
        "latest_original_10k":latest_k,
        "annual_10k_role":"SUPPLEMENTARY_CONTEXT_ONLY_FROZEN_GEM_REQUIRES_10Q",
        "filings":records[:12],
        "original_source_validated":True,
        "financial_facts_certified":False,
        "source_note":"EDGAR filing existence is not proof that the machine verifier identified eligible direct-quarter facts.",
    }


def lookup_filing(cik, *, as_of=date(2026,10,12)):
    if not isinstance(cik,str) or not CIK_RE.fullmatch(cik):
        raise FilingLookupHold("CIK must contain exactly 10 digits")
    url=os.getenv("GEM_READONLY_DATABASE_URL","")
    if not url.startswith("postgresql://gem_web_readonly:"):
        raise FilingLookupHold("GEM read-only database not configured")
    try:
        with psycopg.connect(url,connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute("SET TRANSACTION READ ONLY")
                cur.execute("SET LOCAL statement_timeout=10000")
                cur.execute("""
                    SELECT provider,source_sha256,source_uri,metadata
                    FROM gem_source_receipt
                    WHERE experiment_id=%s AND provider='SEC_ZIP_SUBMISSIONS'
                      AND metadata->>'zip_member_name'=%s
                    ORDER BY collected_at DESC,receipt_id DESC LIMIT 1
                """,(EXPERIMENT,"CIK"+cik+".json"))
                row=cur.fetchone()
                cur.execute("""
                    SELECT details->'evidence' AS evidence, details->>'classification'
                    FROM gem_source_probe
                    WHERE experiment_id=%s AND source_type='sec'
                      AND details->>'cik'=%s
                      AND probe_id LIKE 'gem-sec-inline-review-%%'
                    ORDER BY observed_at DESC, probe_id DESC LIMIT 1
                """,(EXPERIMENT,cik))
                review_row=cur.fetchone()
        if row is None:
            raise FilingLookupHold("Original SEC submissions source not stored for CIK")
        provider,sha,uri,meta=row
        original=decode_original_receipt(
            {"provider":provider,"source_sha256":sha,"source_uri":uri,
             "metadata":meta},cik,"submissions")
        result=summarize_original_filings(original,cik,as_of=as_of)
        result["original_submissions_sha256"]=sha
        if review_row is not None:
            evidence,classification=review_row
            result["original_xbrl_review_status"]=classification
            if isinstance(evidence,dict):
                result["original_10k_extracted_facts"]=evidence.get("original_10k_supplement")
                result["original_10q_six_fact_candidates"]={
                    "current":evidence.get("current"),
                    "prior":evidence.get("prior"),
                    "all_six_standard_category_candidates":evidence.get(
                        "all_six_standard_category_candidates",False),
                    "source_certified":False,
                }
        else:
            result["original_xbrl_review_status"]="NOT_YET_REVIEWED"
            result["original_10k_extracted_facts"]=None
            result["original_10q_six_fact_candidates"]=None
        return result
    except (psycopg.Error,VerificationHold) as exc:
        raise FilingLookupHold("Original SEC submissions cannot be verified") from exc
