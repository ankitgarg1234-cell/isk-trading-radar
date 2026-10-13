"""Reconcile original SEC machine evidence without inventing financial metrics.

All inputs are existing source receipts. This is a deterministic independent
triage and candidate QA: no SEC HTTP, no broker actions, no status certification.
Original filing existence, metric mapping, contextual ambiguity, and financial
eligibility must never be collapsed into one success flag.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import re


REVISION = "gem-sec-reconcile-20261013-v1"
CIK_RE = re.compile(r"^[0-9]{10}$")
HASH_RE = re.compile(r"^[a-f0-9]{64}$")
KINDS = ("STANDARD_REVENUE", "STANDARD_OPERATING_INCOME",
         "STANDARD_PARENT_NET_INCOME")


class ReconciliationHold(ValueError):
    pass


def _finite_decimal(value):
    if not isinstance(value, str) or len(value) > 50:
        raise ReconciliationHold("Invalid original numerical fact")
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise ReconciliationHold("Invalid original numerical fact") from None
    if not result.is_finite() or abs(result)>Decimal("1e18"):
        raise ReconciliationHold("Original fact exceeds acceptable number bound")
    return result


def _check_six_originals(document):
    result={}
    accessions=[]
    for period in ("current", "prior"):
        group=document.get(period)
        if not isinstance(group, dict):
            raise ReconciliationHold("Quarter original missing")
        sha=group.get("original_raw_sha256")
        accession=group.get("accession")
        end=group.get("period_end")
        if (not isinstance(sha,str) or not HASH_RE.fullmatch(sha)
            or not isinstance(accession,str)
            or not re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}",accession)
            or not isinstance(end,str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}",end)):
            raise ReconciliationHold("Original SEC source identity missing")
        accessions.append(accession)
        if group.get("ambiguous_standard_concepts"):
            raise ReconciliationHold("Ambiguous original quarter standard contexts")
        facts=group.get("standard_unique_values")
        if not isinstance(facts,dict):
            raise ReconciliationHold("Quarter fact categories missing")
        result[period]={}
        for kind in KINDS:
            values=facts.get(kind)
            if not isinstance(values,list) or len(values)!=1:
                raise ReconciliationHold("Original six fact categories incomplete")
            result[period][kind]=_finite_decimal(values[0])
    if accessions[0]==accessions[1]:
        raise ReconciliationHold("Both annual comparison contexts have one accession")
    return result


def _candidate_performance(values):
    cur,old=values["current"],values["prior"]
    new_revenue=cur["STANDARD_REVENUE"]
    old_revenue=old["STANDARD_REVENUE"]
    old_profit=old["STANDARD_PARENT_NET_INCOME"]
    new_profit=cur["STANDARD_PARENT_NET_INCOME"]
    if new_revenue<=0 or old_revenue<=0:
        raise ReconciliationHold("Revenue denominator nonpositive")
    revenue_growth=(new_revenue/old_revenue-Decimal(1))*100
    margin_change=(cur["STANDARD_OPERATING_INCOME"]/new_revenue
                   -old["STANDARD_OPERATING_INCOME"]/old_revenue)*100
    if old_profit<0:
        profit_growth_candidate=new_profit>0
        profit_reason="NET_INCOME_RECOVERY_CANDIDATE"
    elif old_profit==0:
        profit_growth_candidate=new_profit>0
        profit_reason="ZERO_PRIOR_NET_INCOME_REQUIRES_DEFINITION_CHECK"
    else:
        profit_growth_candidate=(new_profit/old_profit-Decimal(1))*100>20
        profit_reason="POSITIVE_BASE_NET_INCOME_GROWTH_CANDIDATE"
    return {
        "revenue_yoy_pct":round(float(revenue_growth),5),
        "operating_margin_delta_pp":round(float(margin_change),5),
        "revenue_growth_above_20_candidate":revenue_growth>20,
        "operating_margin_improvement_above_3pp_candidate":margin_change>3,
        "net_income_growth_condition_candidate":bool(profit_growth_candidate and new_profit>0),
        "net_income_test_note":profit_reason,
        "financial_screen_candidate_only":True,
        "original_contexts_independently_certified":False,
        "ranking_eligibility_approved":False,
    }


def reconcile_one(cik, machine, source, *, as_of):
    if not isinstance(cik,str) or not CIK_RE.fullmatch(cik):
        raise ReconciliationHold("Invalid CIK")
    if not isinstance(machine,dict) or not isinstance(source,dict):
        raise ReconciliationHold("Original source audit missing")
    if machine.get("as_of")!=as_of or source.get("as_of")!=as_of:
        raise ReconciliationHold("Original evidence decision dates disagree")
    doc=source.get("evidence")
    if not isinstance(doc,dict):
        doc={}
    parsed=bool(isinstance(doc.get("current"),dict)
                and isinstance(doc.get("prior"),dict))
    all_six=doc.get("all_six_standard_category_candidates") is True
    ambiguous=any(
        isinstance(doc.get(q),dict)
        and bool(doc[q].get("ambiguous_standard_concepts"))
        for q in ("current","prior")
    )
    custom=any(
        isinstance(doc.get(q),dict)
        and bool(doc[q].get("issuer_extensions_to_review")
                 or doc[q].get("nonstandard_financial_facts"))
        for q in ("current","prior")
    )
    if all_six:
        values=_check_six_originals(doc)
        code="SIX_FACTS_RECOVERED_CONTEXT_QA_REQUIRED"
        candidate=_candidate_performance(values)
    elif ambiguous:
        code="CONFLICTING_FINANCIAL_CONTEXTS"
        candidate=None
    elif custom:
        code="NONSTANDARD_ACCOUNTING_DEFINITION_REVIEW"
        candidate=None
    elif parsed:
        code="ORIGINAL_QUARTER_FACTS_INCOMPLETE"
        candidate=None
    elif source.get("classification")=="ANNUAL_10K_SUPPLEMENT_ONLY_10Q_DISCREPANCY_OPEN":
        code="ANNUAL_EVIDENCE_ONLY_QUARTERLY_HOLD"
        candidate=None
    elif source.get("classification")=="ORIGINAL_SEC_FILING_RETRIEVAL_HOLD":
        code="SOURCE_RETRIEVAL_HOLD"
        candidate=None
    else:
        code="SOURCE_CONTEXT_UNRESOLVED"
        candidate=None
    return {
        "schema":"gem-sec-machine-reconciliation-v1",
        "cik":cik,"as_of":as_of,
        "resolution_code":code,
        "original_filing_review_completed":parsed or bool(doc.get("original_10k_supplement")),
        "six_original_quarter_fact_candidates":all_six,
        "facts_candidate_metrics":candidate,
        "original_filing_urls":source.get("filing_urls",[])[:3],
        "original_10k_is_supplementary_only":True,
        "machine_original_status":machine.get("fact_status"),
        "machine_original_blockers":machine.get("blockers",[]),
        "source_original_status":source.get("classification"),
        "reconciled_machine_candidate_not_certified":bool(all_six),
        "independently_verified":False,
        "financial_ineligibility_proven":False,
        "eligible_for_ranking":False,
        "requires_further_evidence":True,
        "trade_authorization":False,
    }


def evidence_key(cik, as_of, qa_id, original_id):
    inputs=[REVISION,cik,as_of,qa_id,original_id]
    identity=sha256(json.dumps(inputs,separators=(",",":")).encode()).hexdigest()[:24]
    return "gem-sec-reconcile-"+as_of.replace("-","")+"-"+cik+"-"+identity
