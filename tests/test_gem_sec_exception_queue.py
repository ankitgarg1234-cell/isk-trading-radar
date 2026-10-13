"""SEC remediation queue and explicit historical decision-date QA tests."""
from datetime import datetime, timezone

import pytest

from gem_data.gem_sec_exception_queue import categorize
from gem_data.sec_fact_audit_worker import qa_as_of, qa_prefix, _key, QAHold


def rows():
    return [
        {"cik":"0000000001","status":"CANDIDATE_COMPLETE_NOT_CERTIFIED",
         "blockers":[],"as_of":"2026-10-12","last_audit":"2026-10-13T10:00:00Z"},
        {"cik":"0000000002","status":"UNKNOWN",
         "blockers":["current_missing_operating_income","prior_missing_operating_income"],
         "as_of":"2026-10-12","last_audit":"2026-10-13T10:00:00Z"},
        {"cik":"0000000003","status":"UNKNOWN",
         "blockers":["current_ambiguous_revenue_tags"],
         "as_of":"2026-10-12","last_audit":"2026-10-13T10:00:00Z"},
    ]


def test_categorize_unknown_without_false_exclusion():
    report=categorize(rows(),captured_at=datetime(2026,10,13,tzinfo=timezone.utc))
    assert report["machine_assessed"]==3
    assert report["candidate_complete_not_certified"]==1
    assert report["unresolved"]==2
    assert report["independently_certified"]==0
    assert report["auto_certification"] is False
    item=next(x for x in report["review_queue"] if x["cik"]=="0000000002")
    assert item["classification"]=="REVIEW_REQUIRED_NOT_A_FINANCIAL_INELIGIBILITY"
    assert item["investment_eligible"] is None
    assert "INLINE_XBRL" in "|".join(item["actions"])
    assert item["sec_filing_lookup"].startswith("https://www.sec.gov/")


def test_queue_missing_blocker_never_certifies():
    inp=[dict(rows()[1],blockers=None)]
    report=categorize(inp)
    assert report["unresolved"]==1
    assert report["review_queue"][0]["blockers"]==[
        "missing_or_malformed_original_filing_evidence"]


def test_queue_rejects_duplicate_ciks():
    with pytest.raises(ValueError):
        categorize(rows()+[rows()[0]])


def test_date_default_preserves_frozen_qa_snapshot(monkeypatch):
    monkeypatch.delenv("GEM_SEC_QA_AS_OF",raising=False)
    assert qa_as_of(observed=datetime(2026,11,2,tzinfo=timezone.utc)).isoformat()=="2026-10-12"


def test_date_roll_forward_requires_explicit_past_cutoff(monkeypatch):
    monkeypatch.setenv("GEM_SEC_QA_AS_OF","2026-10-30")
    asof=qa_as_of(observed=datetime(2026,11,2,tzinfo=timezone.utc))
    assert asof.isoformat()=="2026-10-30"
    assert "20261030" in qa_prefix(asof)
    mock_pair={"submissions":("rid-a","a"*64),"companyfacts":("rid-b","b"*64)}
    from datetime import date
    assert _key("0000000002",mock_pair,date(2026,10,30))!=_key(
        "0000000002",mock_pair,date(2026,10,12))


def test_future_qa_cutoff_fails_closed(monkeypatch):
    monkeypatch.setenv("GEM_SEC_QA_AS_OF","2026-11-02")
    with pytest.raises(QAHold):
        qa_as_of(observed=datetime(2026,11,2,tzinfo=timezone.utc))
    monkeypatch.setenv("GEM_SEC_QA_AS_OF","tomorrow")
    with pytest.raises(QAHold):
        qa_as_of(observed=datetime(2026,11,2,tzinfo=timezone.utc))


def test_opted_in_preliminary_qa_rolls_each_calendar_month(monkeypatch):
    # Rolling machine QA is not itself confirmation of an NYSE signal day.
    monkeypatch.delenv("GEM_SEC_QA_AS_OF",raising=False)
    monkeypatch.setenv("GEM_SEC_QA_AUTO_ROLL","yes")
    assert qa_as_of(observed=datetime(2026,10,20,tzinfo=timezone.utc)).isoformat()=="2026-10-12"
    assert qa_as_of(observed=datetime(2026,11,2,tzinfo=timezone.utc)).isoformat()=="2026-10-31"
    assert qa_as_of(observed=datetime(2026,12,2,tzinfo=timezone.utc)).isoformat()=="2026-11-30"


def test_explicit_review_cutoff_overrides_auto_month_end(monkeypatch):
    monkeypatch.setenv("GEM_SEC_QA_AUTO_ROLL","yes")
    monkeypatch.setenv("GEM_SEC_QA_AS_OF","2026-10-30")
    assert qa_as_of(observed=datetime(2026,11,2,tzinfo=timezone.utc)).isoformat()=="2026-10-30"


def test_original_quarter_filing_separate_from_missing_recognized_facts():
    from gem_data.sec_independent_fact_verify import verify_six_candidates
    from datetime import date
    current="0000831001-26-000045"
    prior="0000831001-25-000045"
    submissions={"filings":{"recent":{
       "form":["10-Q","10-Q"],"accessionNumber":[current,prior],
       "filingDate":["2026-08-06","2025-08-06"],
       "acceptanceDateTime":["2026-08-06T16:00:00","2025-08-06T16:00:00"],
       "reportDate":["2026-06-30","2025-06-30"]}}}
    old={"accn":prior,"form":"10-Q","filed":"2025-08-06",
         "fp":"Q2","start":"2025-04-01","end":"2025-06-30","val":100}
    facts={"facts":{"us-gaap":{
       concept:{"units":{"USD":[old]}}
       for concept in ("Revenues","OperatingIncomeLoss","NetIncomeLoss")}}}
    result=verify_six_candidates(submissions,facts,date(2026,10,12))
    assert result["blockers"]==["fresh_10q_exists_but_standard_facts_unrecognized"]
    assert result["latest_original_10q"]["accession"]==current
    assert result["certified"] is False
