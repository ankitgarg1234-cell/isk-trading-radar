"""SEC read-only collector contract tests; never request external SEC in CI."""
import json
from hashlib import sha256
import pytest
import httpx

from gem_data.sec_original_collector import (
    SecOriginalCollector, SourceUnavailable, normalize_cik,
    validate_sec_user_agent, save_new_evidence, RawReceipt,
)


def test_cik_normalization_and_no_host_injection():
    assert normalize_cik("1652044") == "0001652044"
    with pytest.raises(ValueError):
        normalize_cik("../fake")
    with pytest.raises(ValueError):
        normalize_cik("1652044?x=1")
    with pytest.raises(ValueError):
        validate_sec_user_agent("generic scraper")


def test_original_sec_10q_discovery_preserves_raw_acceptance():
    source = {
        "cik": 1652044,
        "filings": {
            "recent": {
                "form": ["10-Q", "8-K", "10-Q/A"],
                "accessionNumber": ["0001652044-26-000012", "0001652044-26-000011", "0001652044-26-000003"],
                "filingDate": ["2026-07-29", "2026-08-01", "2026-04-30"],
                "acceptanceDateTime": ["2026-07-29T16:00:00", "2026-08-01T14:00:00", "2026-04-30T17:03:00"],
                "primaryDocument": ["q2.htm", "8k.htm", "q1.htm"],
            },
            "files": [{"name": "CIK0001652044-submissions-001.json"}],
        },
    }
    expected_url = "https://data.sec.gov/submissions/CIK0001652044.json"
    def respond(request):
        assert str(request.url) == expected_url
        assert "@" in request.headers.get("User-Agent", "")
        return httpx.Response(200, content=json.dumps(source).encode("utf8"))
    with SecOriginalCollector("Research Project research@example.org", transport=httpx.MockTransport(respond)) as collector:
        result = collector.recent_10q_manifest("1652044")
    assert len(result["discovered_recent_10q"]) == 2
    assert result["discovered_recent_10q"][0]["acceptance_datetime_raw"] == "2026-07-29T16:00:00"
    assert result["raw_submissions_receipt"]["sha256"]
    assert result["six_quarter_inputs_certified"] is False
    assert result["publication_time_certified"] is False
    assert result["paper_execution_authorized"] is False


def test_mismatched_sec_cik_blocks():
    def respond(request):
        return httpx.Response(200, json={"cik": 123, "filings": {"recent": {}}})
    with SecOriginalCollector("GEM Research research@example.org", transport=httpx.MockTransport(respond)) as collector:
        with pytest.raises(SourceUnavailable, match="CIK mismatch"):
            collector.recent_10q_manifest("1652044")


def test_oversized_sec_original_blocks():
    def respond(request):
        return httpx.Response(200, content=b"x" * 6_000_001)
    with SecOriginalCollector("GEM Research research@example.org", transport=httpx.MockTransport(respond)) as collector:
        with pytest.raises(SourceUnavailable, match="bounded size"):
            collector.original_header("1652044", "0001652044-26-000012")


def test_sec_evidence_create_only(tmp_path):
    manifest = {"cik": "0001652044", "schema": "gem-sec-quarter-discovery-v1"}
    path = save_new_evidence(str(tmp_path), manifest)
    assert path.exists()
    with pytest.raises(FileExistsError, match="overwrite"):
        save_new_evidence(str(tmp_path), manifest)

def _original_receipt(cik: str, raw: bytes) -> RawReceipt:
    return RawReceipt(
        provider="SEC_ORIGINAL",
        uri=f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/123456/header.html",
        requested_at="2026-09-01T10:00:00Z",
        completed_at="2026-09-01T10:01:00Z",
        bytes=len(raw),
        sha256=sha256(raw).hexdigest(),
    )


def test_invalid_sec_header_does_not_leave_manifest(tmp_path):
    manifest = {"cik": "0001652044", "schema": "gem-sec-quarter-discovery-v1"}
    receipt = _original_receipt("1652044", b"trusted header")
    with pytest.raises(ValueError, match="do not match"):
        save_new_evidence(str(tmp_path), manifest, receipt, b"xxxxxxx header")
    assert list(tmp_path.iterdir()) == []


def test_header_and_receipt_are_a_required_pair(tmp_path):
    manifest = {"cik": "0001652044", "schema": "gem-sec-quarter-discovery-v1"}
    with pytest.raises(ValueError, match="together"):
        save_new_evidence(str(tmp_path), manifest, original_header=b"unreceipted")
    assert list(tmp_path.iterdir()) == []


def test_valid_original_is_create_only_and_verifiable(tmp_path):
    manifest = {"cik": "0001652044", "schema": "gem-sec-quarter-discovery-v1"}
    original = b"SEC original bytes"
    receipt = _original_receipt("1652044", original)
    path = save_new_evidence(str(tmp_path), manifest, receipt, original)
    assert json.loads(path.read_text()) == manifest
    assert (tmp_path / f"CIK0001652044-original-header-{receipt.sha256}.html").read_bytes() == original
    with pytest.raises(FileExistsError, match="overwrite"):
        save_new_evidence(str(tmp_path), manifest, receipt, original)
    assert json.loads(path.read_text()) == manifest


def test_sec_manifest_cik_must_not_escape_evidence_directory(tmp_path):
    with pytest.raises(ValueError, match="Invalid SEC CIK"):
        save_new_evidence(str(tmp_path), {"cik": "../outside"})
    assert list(tmp_path.iterdir()) == []
