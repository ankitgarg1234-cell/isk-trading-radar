"""Discover *possible* corporate events from primary SEC submissions metadata.

SEC 8-K is an authoritative filing source for disclosed mergers, equity
rights and transactions, but not a complete standardized ledger of stock
splits, exchange ex-dates, distribution amounts and payable entitlements.
Discovery yields review tasks, NEVER ledger mutations or order instructions.
"""
from __future__ import annotations

from datetime import date
from hashlib import sha256
import json
import re

from gem_data.sec_exception_triage import original_filing_url

ITEM_TYPES = {
    "1.01":"MATERIAL_AGREEMENT_REVIEW",
    "2.01":"ACQUISITION_DISPOSITION_REVIEW",
    "3.03":"SECURITYHOLDER_RIGHTS_REVIEW",
    "5.03":"CHARTER_SHARE_CHANGE_REVIEW",
    "8.01":"OTHER_CORPORATE_EVENT_REVIEW",
}
ACC = re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")


class CorporateEventHold(ValueError):
    pass


def discover_sec_event_candidates(submissions, *, cutoff, lookback_days=100):
    if not isinstance(submissions,dict) or type(lookback_days) is not int or not 1 <= lookback_days <= 365:
        raise CorporateEventHold("Invalid SEC original submissions input")
    try:
        cik = str(int(submissions["cik"])).zfill(10)
        cutoff_date = date.fromisoformat(cutoff)
        recent = submissions["filings"]["recent"]
        columns = ("form","accessionNumber","filingDate","primaryDocument","items")
        arrays = [recent.get(col) for col in columns]
        if any(not isinstance(arr,list) for arr in arrays) or len(set(map(len,arrays)))!=1:
            raise ValueError()
    except (KeyError,ValueError,TypeError):
        raise CorporateEventHold("Original submissions do not include usable item records") from None
    out=[]
    for form, accession, filed, document, items in zip(*arrays):
        if form not in ("8-K","8-K/A") or not isinstance(items,str):
            continue
        try:
            when=date.fromisoformat(filed)
        except ValueError:
            continue
        if not 0 <= (cutoff_date-when).days <= lookback_days:
            continue
        triggered=sorted(set(items.replace(" ","").split(",")) & set(ITEM_TYPES))
        if not triggered:
            continue
        try:
            uri=original_filing_url(cik,accession,document)
        except (ValueError,TypeError):
            continue
        out.append({"cik":cik,"filing_date":filed,"accession":accession,
                    "filing_url":uri,"items":triggered,
                    "candidate_types":[ITEM_TYPES[item] for item in triggered],
                    "status":"ORIGINAL_FILING_REVIEW_REQUIRED",
                    "economic_terms_verified":False,
                    "split_or_distribution_confirmed":False})
    out.sort(key=lambda x:(x["filing_date"],x["accession"]))
    return {"schema":"gem-sec-corporate-action-discovery-v1",
            "as_of":cutoff,
            "event_candidates":out,
            "count":len(out),
            "completeness":"SEC_8K_DISCOVERY_ONLY_NOT_EXCHANGE_EVENT_LEDGER",
            "dividend_payable_dates_certified":False,
            "portfolio_events_applied":0}
