"""Offline SEC historical submissions archive reconciliation for frequent filers."""
import json
from datetime import date
import pytest
from gem_data.sec_historical_submissions import (
    historical_fragment_urls, merge_archived_filings, ArchiveHistoryHold,
)
from gem_data.sec_inline_remediation_worker import select_original_filing_pair

CIK="0000831001"
DOC="c-20260630.htm"
OLD="c-20250630.htm"
NAME="CIK0000831001-submissions-001.json"
URL="https://data.sec.gov/submissions/"+NAME


def current():
    return {"cik":831001,"filings":{
        "recent":{"form":["10-Q"],"accessionNumber":["0000831001-26-000045"],
                  "filingDate":["2026-08-06"],"reportDate":["2026-06-30"],
                  "primaryDocument":[DOC],"acceptanceDateTime":["2026-08-06T16:00:00"]},
        "files":[{"name":NAME,"filingFrom":"2023-01-01",
                  "filingTo":"2025-12-31","filingCount":1000}]}}


def archive():
    return {"form":["10-Q"],"accessionNumber":["0000831001-25-000045"],
            "filingDate":["2025-08-06"],"reportDate":["2025-06-30"],
            "primaryDocument":[OLD],"acceptanceDateTime":["2025-08-06T16:00:00"]}


def test_citi_recovers_exact_2025_quarter_accession_from_sec_archive():
    base=current()
    assert historical_fragment_urls(base,CIK,cutoff=date(2026,10,12))==[URL]
    with pytest.raises(ValueError,match="Prior year"):
        select_original_filing_pair(base,cutoff=date(2026,10,12))
    enriched,receipts=merge_archived_filings(base,[(URL,json.dumps(archive()).encode())])
    latest,older=select_original_filing_pair(enriched,cutoff=date(2026,10,12))
    assert latest["accession"]=="0000831001-26-000045"
    assert older["accession"]=="0000831001-25-000045"
    assert older["primary_document"]==OLD
    assert receipts[0]["url"]==URL
    assert len(receipts[0]["sha256"])==64


def test_reject_invalid_sec_archive_file_column_alignment():
    bad=archive()
    bad["form"].append("10-Q")
    with pytest.raises(ArchiveHistoryHold,match="alignment"):
        merge_archived_filings(current(),[(URL,json.dumps(bad).encode())])


def test_cik_specific_sec_archive_url_not_forged():
    manipulated=current()
    manipulated["filings"]["files"][0]["name"]="CIK0000000001-submissions-001.json"
    assert historical_fragment_urls(manipulated,CIK,cutoff=date(2026,10,12))==[]
