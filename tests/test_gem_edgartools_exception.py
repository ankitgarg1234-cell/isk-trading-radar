"""EdgarTools fallback never fetches broad latest statements or bypasses GEM HOLD."""
import base64
from datetime import date
from hashlib import sha256
import json
from types import SimpleNamespace
import zlib

import pytest

from gem_data.gem_edgartools_exception import (
    SECXBRLHold, plan_filing_exceptions, fetch_filing_xbrl,
)
from gem_data.sec_independent_fact_verify import OFFICIAL_ARCHIVES, VerificationHold

CIK = "0001000000"
SIGNAL = "2026-09-30"


def original_submissions(*, future_amendment=False):
    dates = ["2026-08-01", "2026-08-20" if not future_amendment else "2026-10-02",
             "2026-05-01", "2025-08-01", "2025-05-01"]
    data = {"cik": int(CIK), "filings":{"recent":{
        "form":["10-Q","10-Q/A","10-Q","10-Q","10-Q"],
        "accessionNumber":[
            f"{CIK}-26-000001",f"{CIK}-26-000002",
            f"{CIK}-26-000003",f"{CIK}-25-000001",
            f"{CIK}-25-000003"],
        "filingDate":dates,
        "acceptanceDateTime":[x+"T13:00:00" for x in dates],
        "reportDate":["2026-06-30","2026-06-30","2026-03-31",
                      "2025-06-30","2025-03-31"]
    }}}
    raw=json.dumps(data,sort_keys=True).encode()
    digest=sha256(raw).hexdigest()
    return {"provider":"SEC_ZIP_SUBMISSIONS",
        "source_uri":OFFICIAL_ARCHIVES["submissions"]+"#CIK"+CIK+".json",
        "source_sha256":digest,
        "metadata":{
            "zip_member_name":"CIK"+CIK+".json",
            "archive_url":OFFICIAL_ARCHIVES["submissions"],
            "member_original_sha256":digest,
            "member_uncompressed_bytes":len(raw),
            "source_raw_zlib_base64":base64.b64encode(zlib.compress(raw)).decode(),
        }}


def test_all_original_10qa_versions_planned_before_cutoff():
    report=plan_filing_exceptions(original_submissions(),CIK,SIGNAL)
    assert report["cutoff"]=="2026-09-29"
    assert report["status"]=="PLANNED_UNCERTIFIED"
    assert not report["trading_authorized"]
    current=[x for x in report["filings"] if x["report_period"]=="2026-06-30"]
    assert [x["form"] for x in current]==["10-Q/A","10-Q"]
    assert {x["report_period"] for x in report["filings"]} == {
        "2026-06-30","2026-03-31","2025-06-30","2025-03-31"}


def test_amendment_after_signal_does_not_leak():
    report=plan_filing_exceptions(
        original_submissions(future_amendment=True),CIK,SIGNAL)
    current=[x for x in report["filings"] if x["report_period"]=="2026-06-30"]
    assert len(current)==1
    assert current[0]["form"]=="10-Q"


def test_tampered_sec_original_is_rejected_before_planning():
    receipt=original_submissions()
    receipt["source_sha256"]="0"*64
    with pytest.raises(VerificationHold,match="SHA256"):
        plan_filing_exceptions(receipt,CIK,SIGNAL)


class FakeFrame:
    def __init__(self, rows):
        self.rows=rows
        self.columns=list(rows[0]) if rows else ["concept"]
        self.empty=not rows

    def to_dict(self,orient):
        assert orient=="records"
        return self.rows

    @property
    def iloc(self):
        return self

    def __getitem__(self,positions):
        return FakeFrame([self.rows[i] for i in positions])

    def to_json(self,orient,date_format=None):
        assert orient=="records"
        return json.dumps(self.rows,sort_keys=True)


def filing_loader(accession):
    def frame():
        return FakeFrame([
            {"concept":"us-gaap:Revenues","value":125.0,
             "period":"duration_2026-04-01_2026-06-30",
             "context_ref":"FYQ2","unit":"USD","dimensions":None},
            {"concept":"us-gaap:NetIncomeLoss","value":30.0,
             "period":"duration_2026-04-01_2026-06-30",
             "context_ref":"FYQ2","unit":"USD","dimensions":None},
            {"concept":"acme:TotalOperatingIncome","value":40.0,
             "period":"duration_2026-04-01_2026-06-30",
             "context_ref":"FYQ2","unit":"USD","dimensions":None},
            {"concept":"dei:EntityRegistrantName","value":"ACME",
             "period":"instant_2026-06-30",
             "context_ref":"FYQ2","unit":None,"dimensions":None},
        ])
    return SimpleNamespace(
        accession_number=accession, form="10-Q",cik=int(CIK),
        filing_date="2026-08-01",
        xbrl=lambda:SimpleNamespace(facts=SimpleNamespace(to_dataframe=frame)),
    )


def test_filing_specific_xbrl_preserves_context_and_custom_concepts():
    entry={"cik":CIK,"accession":f"{CIK}-26-000001",
           "form":"10-Q","filed":"2026-08-01",
           "report_period":"2026-06-30",
           "accepted_at":"2026-08-01T13:00:00"}
    report=fetch_filing_xbrl(entry,filing_loader=filing_loader)
    assert report["status"]=="EXTRACTED_FOR_INDEPENDENT_QA_ONLY"
    assert report["parsed_candidate_count"]==3
    assert any(r["concept"]=="acme:TotalOperatingIncome"
               for r in report["parsed_candidate_facts"])
    assert all(r["unit"]=="USD" for r in report["parsed_candidate_facts"])
    assert not report["original_inline_xbrl_context_certified"]
    assert not report["raw_original_xbrl_bytes_sha256_verified"]
    assert not report["quarterly_derivations_certified"]
    assert not report["manual_trading_authorized"]


def test_mismatched_edgartools_accession_fails_closed():
    entry={"cik":CIK,"accession":f"{CIK}-26-000001",
           "form":"10-Q","filed":"2026-08-01",
           "report_period":"2026-06-30",
           "accepted_at":"2026-08-01T13:00:00"}
    def wrong(_):
        filing=filing_loader(entry["accession"])
        filing.form="10-K"
        return filing
    with pytest.raises(SECXBRLHold,match="identity"):
        fetch_filing_xbrl(entry,filing_loader=wrong)
