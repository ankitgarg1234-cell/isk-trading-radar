"""Original SEC revenue-only pre-screen never creates an investment approval."""
from gem_data.gem_sec_gate_triage import preliminary_revenue_gate


def period(year, revenue):
    return {
      "period_end":f"{year}-03-31",
      "accession":f"0000721371-{str(year)[2:]}-000018",
      "original_raw_sha256": ("a" if year==2026 else "b")*64,
      "standard_unique_values":{"STANDARD_REVENUE":[str(revenue)]},
      "ambiguous_standard_concepts":["STANDARD_OPERATING_INCOME"],
    }


def test_frozen_twenty_percent_threshold_is_strict():
    doc={"current":period(2026,120),"prior":period(2025,100)}
    result=preliminary_revenue_gate(doc,as_of="2026-10-12")
    assert result["provisional_revenue_gate_fail"] is True
    assert result["financial_ineligibility_certified"] is False
    assert result["eligible_for_ranking"] is False


def test_cardinal_revenue_recovers_a_potential_gate_fail_without_operating_fact():
    report=preliminary_revenue_gate(
       {"current":period(2026,60940000000),
        "prior":period(2025,54878000000)},as_of="2026-10-12")
    assert report["provisional_revenue_gate_fail"] is True
    assert report["revenue_growth_pct_candidate"]>11
    assert report["current_original_sha256"]=="a"*64


def test_positive_revenue_growth_over_threshold_may_not_be_called_eligible():
    report=preliminary_revenue_gate(
       {"current":period(2026,130),"prior":period(2025,100)},
       as_of="2026-10-12")
    assert report["provisional_revenue_gate_fail"] is False
    assert report["eligible_for_ranking"] is False


def test_ambiguous_revenue_cannot_silently_fail_company():
    doc={"current":period(2026,110),"prior":period(2025,100)}
    doc["current"]["ambiguous_standard_concepts"]=["STANDARD_REVENUE"]
    assert preliminary_revenue_gate(doc,as_of="2026-10-12")[
        "status"]=="CANNOT_DETERMINE_FROM_ORIGINAL_QUARTERS"


def test_missing_or_unauthenticated_originals_are_held():
    doc={"current":period(2026,110),"prior":period(2025,100)}
    doc["current"]["original_raw_sha256"]="not-a-source-hash"
    assert preliminary_revenue_gate(doc,as_of="2026-10-12")[
        "provisional_revenue_gate_fail"] is False


def test_future_and_mismatched_periods_are_held():
    doc={"current":period(2026,110),"prior":period(2025,100)}
    assert preliminary_revenue_gate(doc,as_of="2026-01-01")[
        "status"]=="CANNOT_DETERMINE_FROM_ORIGINAL_QUARTERS"
    doc["prior"]["period_end"]="2025-11-30"
    assert preliminary_revenue_gate(doc,as_of="2026-10-12")[
        "provisional_revenue_gate_fail"] is False
