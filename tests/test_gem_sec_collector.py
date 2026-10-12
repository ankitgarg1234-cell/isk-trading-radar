"""SEC read-only collector contract tests; never request external SEC in CI."""
import json
import pytest
import httpx

from gem_data.sec_original_collector import (
    SecOriginalCollector, SourceUnavailable, normalize_cik,
    validate_sec_user_agent, save_new_evidence,
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
