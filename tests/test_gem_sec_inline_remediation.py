"""Original Inline XBRL remediation: source identity, USD, contexts, ambiguity.

All tests are local synthetic filings. No SEC network, Neon or vendor credits.
"""
from datetime import date

import pytest

from gem_data.sec_inline_xbrl_evidence import (
    extract_inline_candidates, InlineEvidenceHold,
)
from gem_data.sec_inline_remediation_worker import (
    select_original_filing_pair, summarize_pair, original_primary_url,
    InlineReviewHold,
)

CIK="0000000001"
ACC26="0000000001-26-000020"
ACC25="0000000001-25-000020"
URI="https://www.sec.gov/Archives/edgar/data/1/000000000126000020/quarter.htm"


def filing_html(*, dimension=False, identifier="1"):
    contexts = (
       '<xbrli:context id="CURRENT"><xbrli:entity>'
       '<xbrli:identifier scheme="http://www.sec.gov/CIK">'+identifier+'</xbrli:identifier>'
       + ('<xbrli:segment><xbrldi:explicitMember dimension="a:b">a:c'
          '</xbrldi:explicitMember></xbrli:segment>' if dimension else '')
       + '</xbrli:entity><xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate>'
       '<xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period></xbrli:context>'
    )
    return ('<html>'+contexts+
      '<xbrli:unit id="usd"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>'
      '<ix:nonFraction name="us-gaap:Revenues" contextRef="CURRENT" unitRef="usd" scale="6">1,300</ix:nonFraction>'
      '<ix:nonFraction name="us-gaap:OperatingIncomeLoss" contextRef="CURRENT" unitRef="usd" scale="6" sign="-">30</ix:nonFraction>'
      '<ix:nonFraction name="us-gaap:NetIncomeLoss" contextRef="CURRENT" unitRef="usd" scale="6">55</ix:nonFraction>'
      '<ix:nonFraction name="custom:AdjustedOperatingIncome" contextRef="CURRENT" unitRef="usd" scale="6">95</ix:nonFraction>'
      '</html>').encode()


def test_original_ixbrl_extraction_preserves_source_provenance():
    out=extract_inline_candidates(filing_html(),cik=CIK,accession=ACC26,source_uri=URI)
    assert out["eligible_undimensioned_usd_candidates"]==4
    assert out["automatic_mapping_approved"] is False
    revenue=next(x for x in out["candidates"] if x["category"]=="STANDARD_REVENUE")
    assert revenue["amount_usd"]=="1300000000"
    assert revenue["start"]=="2026-04-01"
    assert out["candidates"][1]["amount_usd"]=="-30000000"
    assert any(x["category"]=="ISSUER_EXTENSION_REVIEW_ONLY" for x in out["candidates"])


def test_dimensioned_facts_not_used_as_company_total():
    out=extract_inline_candidates(filing_html(dimension=True),cik=CIK,accession=ACC26,source_uri=URI)
    assert out["eligible_undimensioned_usd_candidates"]==0


def test_wrong_company_cik_fails():
    with pytest.raises(InlineEvidenceHold,match="CIK"):
        extract_inline_candidates(filing_html(identifier="2"),cik=CIK,accession=ACC26,source_uri=URI)


def test_wrong_sec_accession_url_fails():
    with pytest.raises(InlineEvidenceHold,match="accession"):
        extract_inline_candidates(filing_html(),cik=CIK,accession=ACC25,source_uri=URI)


def test_original_prior_quarter_10q_retrieval():
    d={"filings":{"recent":{
        "form":["10-Q","10-Q","10-Q"],
        "accessionNumber":[ACC26,ACC25,"0000000001-24-000020"],
        "filingDate":["2026-08-01","2025-08-01","2024-08-01"],
        "reportDate":["2026-06-30","2025-06-30","2024-06-30"],
        "primaryDocument":["quarter.htm","quarter.htm","quarter.htm"]}}}
    current,prior=select_original_filing_pair(d,cutoff=date(2026,10,12))
    assert current["accession"]==ACC26
    assert prior["accession"]==ACC25
    assert original_primary_url(CIK,current)==URI
    with pytest.raises(InlineReviewHold):
        select_original_filing_pair(d,cutoff=date(2025,1,1))


def test_six_direct_candidates_are_not_certification():
    a=extract_inline_candidates(filing_html(),cik=CIK,accession=ACC26,source_uri=URI)
    b={**a,"candidates":[{**x,"start":"2025-04-01","end":"2025-06-30"}
                          for x in a["candidates"]],"original_raw_sha256":"b"*64}
    result=summarize_pair({"period_end":"2026-06-30","accession":ACC26,"evidence":a},
                          {"period_end":"2025-06-30","accession":ACC25,"evidence":b})
    assert result["all_six_standard_category_candidates"] is True
    assert result["certified"] is False
    assert result["trading_authorized"] is False


def test_conflicting_revenue_facts_remain_unresolved():
    a=extract_inline_candidates(filing_html(),cik=CIK,accession=ACC26,source_uri=URI)
    new={**a, "candidates":a["candidates"]+[
      {**a["candidates"][0],"concept":"us-gaap:SalesRevenueNet","amount_usd":"999"}]}
    result=summarize_pair({"period_end":"2026-06-30","accession":ACC26,"evidence":new},
                          {"period_end":"2025-06-30","accession":ACC25,"evidence":{
                           **a,"candidates":[{**x,"start":"2025-04-01","end":"2025-06-30"}
                                               for x in a["candidates"]]}})
    assert result["all_six_standard_category_candidates"] is False
    assert "STANDARD_REVENUE" in result["current"]["ambiguous_standard_concepts"]


def test_original_filing_staleness_is_not_a_six_fact_recovery():
    d={"filings":{"recent":{
        "form":["10-Q","10-Q"],
        "accessionNumber":[ACC26,ACC25],
        "filingDate":["2026-01-02","2025-01-02"],
        "reportDate":["2025-12-31","2024-12-31"],
        "primaryDocument":["quarter.htm","quarter.htm"]}}}
    with pytest.raises(InlineReviewHold,match="stale"):
        select_original_filing_pair(d,cutoff=date(2026,10,12))
