"""Offline SEC accession, six-fact, as-of-cutoff QA tests. No network."""
from copy import deepcopy
import pytest
from gem_data.sec_asof_reconciliation import audit_sec_six_facts, SecEvidenceHold

CIK = "0001652044"
H = "a" * 64


def good():
    current = "0001652044-26-000012"
    prior = "0001652044-25-000010"
    filings = [
        {"form": "10-Q", "accession": current,
         "filed_date_raw": "2026-08-02",
         "acceptance_datetime_raw": "2026-08-02T16:02:00",
         "primary_document": "q2.htm"},
        {"form": "10-Q", "accession": prior,
         "filed_date_raw": "2025-08-02",
         "acceptance_datetime_raw": "2025-08-02T16:02:00",
         "primary_document": "q2.htm"}
    ]
    manifest = {
        "schema": "gem-sec-quarter-discovery-v1", "cik": CIK,
        "raw_submissions_receipt": {
            "provider": "SEC_ORIGINAL",
            "uri": f"https://data.sec.gov/submissions/CIK{CIK}.json",
            "sha256": H, "bytes": 1000,
        },
        "discovered_recent_10q": filings,
    }
    facts = {}
    receipts = {}
    for row in filings:
        accession = row["accession"]
        prior_fact = accession == prior
        sh = ("b" if prior_fact else "c") * 64
        receipts[accession] = {
            "provider": "SEC_ORIGINAL", "sha256": sh,
            "uri": f"https://www.sec.gov/Archives/edgar/data/{int(CIK)}/{accession.replace('-', '')}/q2.xml",
        }
        for measure in ("revenue", "income", "operating"):
            name = measure + ("_prior" if prior_fact else "_now")
            facts[name] = {
                "accession": accession, "form": "10-Q", "cik": CIK,
                "unit": "USD", "concept": "us-gaap:" + measure,
                "start": "2025-04-01" if prior_fact else "2026-04-01",
                "end": "2025-06-30" if prior_fact else "2026-06-30",
                "value": 30, "source_sha256": sh,
                "first_public_observed_at": "2025-08-03T12:00:00Z" if prior_fact else "2026-08-03T12:00:00Z",
            }
    return manifest, facts, receipts


def audit(m=None, f=None, r=None, day="2026-09-30"):
    g = good()
    return audit_sec_six_facts(
        manifest=m if m is not None else g[0],
        facts=f if f is not None else g[1],
        signal_session=day,
        original_xbrl_receipts=r if r is not None else g[2],
    )


def test_good_metadata_is_still_not_independently_certified():
    result = audit()
    assert result["facts_checked"] == 6
    assert result["ranking_authorized"] is False
    assert result["publication_and_xbrl_context_independently_verified"] is False
    assert result["status"] == "PENDING_INDEPENDENT_SEC_QA"


def test_filing_after_signal_is_blocked():
    m, f, r = good()
    m["discovered_recent_10q"][0]["acceptance_datetime_raw"] = "2026-09-30T16:05:00"
    with pytest.raises(SecEvidenceHold, match="prior-session cutoff"):
        audit(m, f, r)


def test_retrospectively_first_observed_fact_cannot_be_treated_as_pit():
    m, f, r = good()
    f["revenue_now"]["first_public_observed_at"] = "2026-10-12T20:15:00Z"
    with pytest.raises(SecEvidenceHold, match="observed too late"):
        audit(m, f, r)


def test_different_filing_or_period_for_operating_income_blocks():
    m, f, r = good()
    f["operating_now"]["end"] = "2026-06-29"
    with pytest.raises(SecEvidenceHold, match="Mixed quarter"):
        audit(m, f, r)


def test_missing_raw_xbrl_receipt_blocks_even_with_facts():
    m, f, r = good()
    r.pop("0001652044-26-000012")
    with pytest.raises(SecEvidenceHold, match="XBRL byte receipt"):
        audit(m, f, r)


def test_unmapped_accession_blocks():
    m, f, r = good()
    f["revenue_now"]["accession"] = "0001652044-26-999999"
    with pytest.raises(SecEvidenceHold, match="Unrecognized"):
        audit(m, f, r)


def test_broken_submissions_manifest_cik_blocks():
    m, f, r = good()
    m["raw_submissions_receipt"]["uri"] = "https://attacker.example/CIK.json"
    with pytest.raises(SecEvidenceHold, match="submissions receipt"):
        audit(m, f, r)
