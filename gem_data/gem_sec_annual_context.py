"""SEC 10-K original document evidence, supplemental to frozen GEMv1 10-Q rules.

An annual 10-K is a useful primary-source diagnostic, including for fiscal
Q4 and issuer custom financial concepts. It is NOT automatically eligible as
a quarterly 10-Q fact, nor as a YTD-derived quarter. This module stores
accession-linked annual fact candidates for independent reconciliation.
"""
from __future__ import annotations
from datetime import date
from collections import Counter
import re

from gem_data.sec_inline_xbrl_evidence import extract_inline_candidates

_ACCESSION=re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")
_FILENAME=re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def select_annual_original(submissions, *, cutoff):
    recent=((submissions.get("filings") or {}).get("recent") or {})
    keys=("form","accessionNumber","filingDate","reportDate","primaryDocument")
    arrays=[recent.get(k) for k in keys]
    if any(not isinstance(v,list) for v in arrays) or len(set(map(len,arrays)))!=1:
        return None
    records=[]
    for form, accn, filed, report, doc in zip(*arrays):
        if form != "10-K" or not isinstance(accn,str) or not _ACCESSION.fullmatch(accn):
            continue
        if not isinstance(doc,str) or not _FILENAME.fullmatch(doc):
            continue
        try:
            filed_day=date.fromisoformat(filed)
            report_day=date.fromisoformat(report)
        except (ValueError,TypeError):
            continue
        if filed_day>cutoff or report_day>cutoff:
            continue
        records.append({"form":"10-K","accession":accn,"filed":filed,
                        "period_end":report,"primary_document":doc})
    if not records:
        return None
    return max(records,key=lambda x:(x["period_end"],x["filed"],x["accession"]))


def summarize_annual_original(raw, *, cik, filing, source_uri):
    document=extract_inline_candidates(raw,cik=cik,
        accession=filing["accession"],source_uri=source_uri)
    year_end=date.fromisoformat(filing["period_end"])
    annual=[]
    shorter=[]
    for fact in document["candidates"]:
        if fact["end"] != year_end.isoformat():
            continue
        days=(year_end-date.fromisoformat(fact["start"])).days
        item={"concept":fact["concept"],"classification":fact["category"],
              "start":fact["start"],"end":fact["end"],
              "value_usd":fact["amount_usd"],"context_days":days}
        if 330<=days<=380:
            annual.append(item)
        elif 60<=days<=125:
            shorter.append(item)
    counts=Counter(item["classification"] for item in annual)
    return {
        "form":"10-K",
        "accession":filing["accession"],
        "filing_date":filing["filed"],
        "report_period":filing["period_end"],
        "original_document_url":source_uri,
        "original_document_sha256":document["original_raw_sha256"],
        "original_bytes":document["original_bytes"],
        "annual_undimensioned_usd_fact_counts":dict(counts),
        "annual_fact_candidates":annual[:45],
        "quarter_length_fact_candidates":shorter[:25],
        "status":"ORIGINAL_ANNUAL_FINANCIAL_EVIDENCE_REVIEW_ONLY",
        "frozen_gem_10q_quarterly_eligibility":False,
        "quarter_derivation_automatically_approved":False,
        "independently_certified":False,
        "next_step":"Reconcile concepts, periods and original 10-Q accession; 10-K may inform review but cannot silently replace 10-Q",
    }
