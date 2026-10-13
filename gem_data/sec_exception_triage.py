"""SEC original filing exception triage for GEMv1.

Companyfacts omits issuer-specific extension taxonomy facts. This module
proposes original Inline XBRL review, never invents missing US-GAAP values or
certifies non-equivalent business metrics. Derived quarterly YTD differences
are candidate facts only, until source contexts and temporal cutoffs pass QA.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import re

CIK = re.compile(r"^[0-9]{10}$")
ACC = re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")
DOC = re.compile(r"^[A-Za-z0-9_.\-]{1,150}$")


class SECRemediationHold(ValueError):
    pass


NEXT_STEP = {
    "missing_operating_income":"INSPECT_ISSUER_INLINE_XBRL_OR_DOCUMENT_STRUCTURAL_INELIGIBILITY",
    "ambiguous_revenue_tags":"RECONCILE_REVENUE_CONCEPTS_AND_CONTEXTS_TO_FROZEN_DEFINITION",
    "missing_net_income":"VERIFY_PARENT_COMPANY_NET_INCOME_IN_ORIGINAL_FILING",
    "missing_revenue":"INSPECT_ISSUER_SPECIFIC_REVENUE_TAG_AND_DIRECT_QUARTER",
    "later_amendment_requires_xbrl":"REVIEW_AMENDMENT_EFFECTIVE_AT_SIGNAL_CUTOFF",
    "quarter_older_than_210_days":"CHECK_NEWER_10Q_OR_MARK_FINANCIALS_STALE",
    "no_eligible_original_10q_usd_quarter_contexts":"CHECK_FILING_FORM_AND_POINT_IN_TIME_AVAILABILITY",
    "prior_year_same_quarter_accession_context_missing":"CHECK_PRIOR_FILING_AND_ALLOWED_DERIVED_QUARTER",
}


def triage(blockers):
    if not isinstance(blockers, list):
        raise SECRemediationHold("Malformed SEC financial exception list")
    tasks = []
    for reason in sorted(set(blockers)):
        if not isinstance(reason,str) or len(reason)>180:
            raise SECRemediationHold("Malformed exception reason")
        action = next((step for kind,step in NEXT_STEP.items() if kind in reason),
                      "REVIEW_ORIGINAL_SEC_ACCESSION_CONTEXT")
        tasks.append({"blocker":reason,"action":action,
                      "automatic_certification":False,
                      "additional_data_source":"SEC_ORIGINAL_10Q_INLINE_XBRL"})
    return tasks


def original_filing_url(cik, accession, primary_document):
    if not (isinstance(cik,str) and CIK.fullmatch(cik)
            and isinstance(accession,str) and ACC.fullmatch(accession)
            and isinstance(primary_document,str) and DOC.fullmatch(primary_document)
            and not primary_document.startswith(".")):
        raise SECRemediationHold("Invalid SEC accession or filing document")
    if accession[:10] == "0000000000":
        raise SECRemediationHold("Invalid SEC accession")
    return ("https://www.sec.gov/Archives/edgar/data/"
            + str(int(cik)) + "/" + accession.replace("-","") + "/" + primary_document)


def quarter_from_ytd(*, current_ytd, prior_ytd, signal_day):
    """Derive Q2/Q3 from a same-taxonomy original-period YTD difference.

    Source format: {value, start, end, filed, accession, unit, concept, form}.
    The result requires original-context review, not a signature/certification.
    """
    try:
        cutoff = date.fromisoformat(signal_day)
        current_end = date.fromisoformat(current_ytd["end"])
        prev_end = date.fromisoformat(prior_ytd["end"])
        current_start = date.fromisoformat(current_ytd["start"])
        prev_start = date.fromisoformat(prior_ytd["start"])
        filed_current = date.fromisoformat(current_ytd["filed"])
        filed_prior = date.fromisoformat(prior_ytd["filed"])
        now = Decimal(str(current_ytd["value"]))
        previous = Decimal(str(prior_ytd["value"]))
    except (ValueError, TypeError, KeyError, InvalidOperation):
        raise SECRemediationHold("Invalid YTD SEC context/number") from None
    if (current_start != prev_start
            or not (60 <= (current_end-prev_end).days <= 125)
            or current_end <= prev_end
            or (current_end-current_start).days < 140
            or filed_current >= cutoff or filed_prior >= cutoff
            or not now.is_finite() or not previous.is_finite()
            or current_ytd.get("concept") != prior_ytd.get("concept")
            or current_ytd.get("unit") != "USD" or prior_ytd.get("unit") != "USD"
            or current_ytd.get("form") != "10-Q" or prior_ytd.get("form") != "10-Q"
            or not ACC.fullmatch(str(current_ytd.get("accession","")))
            or not ACC.fullmatch(str(prior_ytd.get("accession","")))):
        raise SECRemediationHold("YTD quarters not comparable by period, accession or cutoff")
    return {"value_usd":str(now-previous),
            "start_after":prev_end.isoformat(),
            "end":current_end.isoformat(),
            "source_accessions":[prior_ytd["accession"],current_ytd["accession"]],
            "concept":current_ytd["concept"],
            "certified":False,
            "status":"DERIVED_QUARTER_CANDIDATE_REQUIRES_SOURCE_CONTEXT_QA"}
