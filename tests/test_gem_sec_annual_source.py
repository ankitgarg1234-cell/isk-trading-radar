"""SEC 10-K original source integration, annual-vs-quarterly guardrails.

Synthetic original Inline XBRL and a Cardinal Health filing-manifest
fixture; no SEC networking, broker connections or paid vendor requests.
"""
from datetime import date
import pytest

from gem_data.gem_sec_annual_context import (
    select_annual_original, summarize_annual_original,
)
from gem_data.gem_sec_filing_lookup import summarize_original_filings


CIK="0000721371"
K="0000721371-26-000038"
Q="0000721371-26-000018"
URL="https://www.sec.gov/Archives/edgar/data/721371/000072137126000038/cah-20260630.htm"


def submissions():
    return {"cik":721371,"name":"CARDINAL HEALTH INC",
            "filings":{"recent":{
                "form":["10-K","10-Q","10-K","10-Q"],
                "accessionNumber":[K,Q,"0000721371-25-000038",
                                   "0000721371-25-000018"],
                "filingDate":["2026-08-11","2026-04-30","2025-08-12",
                              "2025-05-01"],
                "reportDate":["2026-06-30","2026-03-31","2025-06-30",
                              "2025-03-31"],
                "primaryDocument":["cah-20260630.htm","cah-20260331.htm",
                                   "cah-20250630.htm","cah-20250331.htm"],
                "acceptanceDateTime":["2026-08-11T17:00:00.000Z",
                                      "2026-04-30T19:00:00.000Z",
                                      "2025-08-12T17:00:00.000Z",
                                      "2025-05-01T17:00:00.000Z"]}}}


def ixbrl():
    return b"""<html>
    <xbrli:context id="annual"><xbrli:entity>
    <xbrli:identifier scheme="http://www.sec.gov/CIK">721371</xbrli:identifier>
    </xbrli:entity><xbrli:period><xbrli:startDate>2025-07-01</xbrli:startDate>
    <xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period></xbrli:context>
    <xbrli:context id="q4"><xbrli:entity>
    <xbrli:identifier scheme="http://www.sec.gov/CIK">721371</xbrli:identifier>
    </xbrli:entity><xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate>
    <xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period></xbrli:context>
    <xbrli:unit id="usd"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>
    <ix:nonFraction name="us-gaap:Revenues" contextRef="annual" unitRef="usd"
    scale="6">200000</ix:nonFraction>
    <ix:nonFraction name="us-gaap:NetIncomeLoss" contextRef="annual" unitRef="usd"
    scale="6">100</ix:nonFraction>
    <ix:nonFraction name="us-gaap:Revenues" contextRef="q4" unitRef="usd"
    scale="6">55000</ix:nonFraction>
    </html>"""


def test_sec_ix_viewer_is_a_pointer_to_the_original_raw_document():
    result=summarize_original_filings(submissions(),CIK,as_of=date(2026,10,12))
    annual=result["latest_original_10k"]
    assert annual["accession"]==K
    assert annual["filed"]=="2026-08-11"
    assert annual["document_url"]==URL
    assert annual["ix_viewer_url"]==(
       "https://www.sec.gov/ix?doc=/Archives/edgar/data/"
       "0000721371/000072137126000038/cah-20260630.htm")
    assert result["latest_original_10q"]["accession"]==Q
    assert result["annual_10k_role"]=="SUPPLEMENTARY_CONTEXT_ONLY_FROZEN_GEM_REQUIRES_10Q"
    assert result["financial_facts_certified"] is False


def test_original_annual_source_fact_extraction_does_not_approve_q4_gate():
    annual=select_annual_original(submissions(),cutoff=date(2026,10,12))
    report=summarize_annual_original(ixbrl(),cik=CIK,filing=annual,source_uri=URL)
    assert report["accession"]==K
    assert report["original_document_url"]==URL
    assert report["original_bytes"]==len(ixbrl())
    assert len(report["annual_fact_candidates"])==2
    assert len(report["quarter_length_fact_candidates"])==1
    assert report["frozen_gem_10q_quarterly_eligibility"] is False
    assert report["quarter_derivation_automatically_approved"] is False
    assert report["independently_certified"] is False


def test_cutoff_never_uses_future_annual_filing():
    assert select_annual_original(submissions(),cutoff=date(2026,7,31))["filed"]=="2025-08-12"
    assert select_annual_original(submissions(),cutoff=date(2025,1,1)) is None


def test_sec_file_detail_route_requires_dashboard_auth(monkeypatch):
    from fastapi.testclient import TestClient
    from gem_data.gem_standalone import app
    monkeypatch.setenv("GEM_DASHBOARD_USERNAME","gemowner")
    monkeypatch.setenv("GEM_DASHBOARD_PASSWORD","at-least-twenty-chars-sec-source")
    with TestClient(app) as client:
        assert client.get("/api/gem-portfolio/sec-filing/0000721371").status_code==401
        response=client.get("/api/gem-portfolio/sec-filing/0000721371",
                            auth=("gemowner","at-least-twenty-chars-sec-source"))
        assert response.status_code in (200,422)
        assert response.status_code!=404



def test_sec_issuer_index_and_human_facts_page(monkeypatch):
    from fastapi.testclient import TestClient
    from gem_data.gem_standalone import app
    from gem_data import gem_sec_filing_routes
    from gem_data import gem_sec_exception_queue
    monkeypatch.setenv("GEM_DASHBOARD_USERNAME","gemowner")
    monkeypatch.setenv("GEM_DASHBOARD_PASSWORD","at-least-twenty-chars-sec-source")
    source=summarize_original_filings(submissions(),CIK,as_of=date(2026,10,12))
    source["original_xbrl_review_status"]="SIX_DIRECT_STANDARD_CANDIDATES_NEED_CONTEXT_REVIEW"
    source["original_10k_extracted_facts"]=summarize_annual_original(
        ixbrl(),cik=CIK,filing=select_annual_original(submissions(),cutoff=date(2026,10,12)),
        source_uri=URL)
    source["original_10q_six_fact_candidates"]=None
    monkeypatch.setattr(gem_sec_filing_routes,"lookup_filing",lambda cik:source)
    monkeypatch.setattr(gem_sec_exception_queue,"read_sec_exception_queue",lambda limit:{
         "review_queue":[{"cik":CIK,"blockers":["current_quarter_older_than_210_days"],
             "review_stage":"SIX_FACT_CANDIDATES_UNCERTIFIED","original_inline_reviewed_at":None}],
         "unresolved":1,"original_inline_scanned":1,"original_inline_six_candidate_sets":1})
    with TestClient(app) as client:
        auth=("gemowner","at-least-twenty-chars-sec-source")
        assert client.get("/gem-sec-filings").status_code==401
        index=client.get("/gem-sec-filings",auth=auth)
        assert index.status_code==200
        assert ("/gem-sec-filing/"+CIK) in index.text
        details=client.get("/gem-sec-filing/"+CIK,auth=auth)
        assert details.status_code==200
        assert "254248" not in details.text  # The fixture is synthetic, never real financial data
        assert "200000000000" in details.text
        assert "cah-20260630.htm" in details.text
        assert "not automatically eligible" in details.text.lower() or "not automatically" in details.text.lower()
