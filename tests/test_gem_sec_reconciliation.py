"""GEM SEC all-issuer reconciliation tests, frozen financial rules unchanged."""
from datetime import date
from decimal import Decimal

import pytest
from gem_data.gem_sec_reconciliation import (
    reconcile_one,evidence_key,ReconciliationHold,
)


def review(*,current=None,prior=None,status="ORIGINAL_10Q_EXCEPTION_REVIEW_REQUIRED"):
    return {
        "as_of":"2026-10-12",
        "classification":status,
        "filing_urls":["https://www.sec.gov/Archives/edgar/data/721371/a/cah.htm"],
        "evidence":{
            "all_six_standard_category_candidates":False,
            "current":current if current is not None else {
                "standard_unique_values":{"STANDARD_REVENUE":["12"]},
                "issuer_extensions_to_review":[],"ambiguous_standard_concepts":[]},
            "prior":prior if prior is not None else {
                "standard_unique_values":{"STANDARD_REVENUE":["10"]},
                "issuer_extensions_to_review":[],"ambiguous_standard_concepts":[]},
        },
    }


def quarter(year, rev, operating, income):
    return {
      "original_raw_sha256": "a"*64 if year==2026 else "b"*64,
      "accession":f"0000721371-{str(year)[2:]}-000018",
      "period_end":f"{year}-03-31",
      "standard_unique_values":{
          "STANDARD_REVENUE":[str(rev)],
          "STANDARD_OPERATING_INCOME":[str(operating)],
          "STANDARD_PARENT_NET_INCOME":[str(income)],
      },
      "ambiguous_standard_concepts":[],"issuer_extensions_to_review":[],
    }


def machine():
    return {"as_of":"2026-10-12","fact_status":"UNKNOWN",
            "blockers":["fresh_10q_exists_but_standard_facts_unrecognized"]}


def test_cardinal_original_candidates_do_not_become_certified():
    current=quarter(2026,60940000000,509000000,399000000)
    previous=quarter(2025,54878000000,730000000,506000000)
    source=review(current=current,prior=previous)
    source["evidence"]["all_six_standard_category_candidates"]=True
    result=reconcile_one("0000721371",machine(),source,as_of="2026-10-12")
    assert result["resolution_code"]=="SIX_FACTS_RECOVERED_CONTEXT_QA_REQUIRED"
    assert result["facts_candidate_metrics"]["revenue_growth_above_20_candidate"] is False
    assert result["facts_candidate_metrics"]["revenue_yoy_pct"]==pytest.approx(11.045,abs=0.03)
    assert result["facts_candidate_metrics"]["operating_margin_improvement_above_3pp_candidate"] is False
    assert result["reconciled_machine_candidate_not_certified"] is True
    assert result["eligible_for_ranking"] is False
    assert result["financial_ineligibility_proven"] is False
    assert result["trade_authorization"] is False


def test_bank_extension_never_invents_operating_income():
    source=review()
    source["evidence"]["current"]["issuer_extensions_to_review"]=["c:NetRevenueAfterProvisions"]
    assert reconcile_one("0000831001",machine(),source,as_of="2026-10-12")[
        "resolution_code"]=="NONSTANDARD_ACCOUNTING_DEFINITION_REVIEW"


def test_ambiguity_precedes_custom_tag():
    source=review()
    source["evidence"]["current"]["ambiguous_standard_concepts"]=["STANDARD_REVENUE"]
    source["evidence"]["prior"]["issuer_extensions_to_review"]=["c:NetRevenue"]
    assert reconcile_one("0000831001",machine(),source,as_of="2026-10-12")[
       "resolution_code"]=="CONFLICTING_FINANCIAL_CONTEXTS"


def test_original_incomplete_keeps_hold():
    result=reconcile_one("0000831001",machine(),review(),as_of="2026-10-12")
    assert result["resolution_code"]=="ORIGINAL_QUARTER_FACTS_INCOMPLETE"
    assert result["reconciled_machine_candidate_not_certified"] is False


def test_annual_only_is_never_six_fact():
    source={"as_of":"2026-10-12",
            "classification":"ANNUAL_10K_SUPPLEMENT_ONLY_10Q_DISCREPANCY_OPEN",
            "evidence":{"original_10k_supplement":{"accession":"0000831001-26-000045"}}}
    result=reconcile_one("0000831001",machine(),source,as_of="2026-10-12")
    assert result["resolution_code"]=="ANNUAL_EVIDENCE_ONLY_QUARTERLY_HOLD"
    assert result["eligible_for_ranking"] is False


def test_missing_provenance_fails_closed():
    current=quarter(2026,100,50,30)
    current["original_raw_sha256"]="invalid"
    source=review(current=current,prior=quarter(2025,50,15,5))
    source["evidence"]["all_six_standard_category_candidates"]=True
    with pytest.raises(ReconciliationHold):
        reconcile_one("0000831001",machine(),source,as_of="2026-10-12")


def test_month_end_mismatch_fails_closed():
    with pytest.raises(ReconciliationHold):
        reconcile_one("0000831001",machine(),review(),as_of="2026-10-30")


def test_probes_unique_to_source_and_audit_identity():
    a=evidence_key("0000831001","2026-10-12","qa-id","review-v1")
    assert a!=evidence_key("0000831001","2026-10-12","qa-id","review-v2")
    assert a.startswith("gem-sec-reconcile-20261012-0000831001-")
