"""Offline SEC read-only original submissions + point-in-time HOLD fixtures."""
import json
from datetime import datetime, timezone

import httpx
import pytest
from gem_data.sec_daily_discovery import select_ciks, probe_batch, _snapshot

DAY = datetime(2026, 10, 13, 4, 0, tzinfo=timezone.utc)
CSV = ("Symbol,CIK\n" + "".join(f"TEST{i},{1000000+i}\n" for i in range(500))).encode()


def test_cik_cohort_is_bounded_and_covers_all_six_day_cycles():
    groups = []
    for i in range(6):
        from datetime import timedelta
        ciks, total = select_ciks(CSV, DAY + timedelta(days=i))
        assert total == 500
        assert 1 <= len(ciks) <= 90
        groups += ciks
    assert len(groups) == len(set(groups)) == 500


def test_mock_sec_original_observations_preserve_source_bytes_without_certifying_facts():
    ciks, _ = select_ciks(CSV, DAY)
    def respond(req):
        cik = str(req.url).split("CIK")[1].split(".json")[0]
        assert cik in ciks
        assert "@" in req.headers.get("User-Agent", "")
        return httpx.Response(200, json={
            "cik": int(cik),
            "filings": {"recent": {
                "form": ["10-Q", "10-K"],
                "accessionNumber": [cik+"-26-000001", cik+"-26-000002"],
                "filingDate": ["2026-08-01", "2026-03-01"],
                "acceptanceDateTime": ["2026-08-01T16:00:00", "2026-03-01T18:00:00"],
            }},
        })
    proof, summary = probe_batch(
        CSV, DAY, "GEM Research authorized-contact@example.com",
        transport=httpx.MockTransport(respond))
    assert summary["ciks_attempted"] == len(ciks)
    assert summary["ciks_failed"] == 0
    assert len(proof) == len(ciks)+1
    assert proof[-1][1]["state"] == "PARTIAL"
    assert proof[-1][1]["details"]["certified"] is False
    for receipt, probe in proof[:-1]:
        assert receipt["provider"] == "SEC_ORIGINAL_SUBMISSIONS"
        assert receipt["metadata"]["discovery"]["quarter_accessions_found"] == 1
        assert receipt["metadata"]["original_xbrl_facts_verified"] is False
        assert probe["state"] == "PARTIAL"


def test_malformed_sec_identity_blocks_issuer_and_summary():
    def bad(req):
        return httpx.Response(200, json={"cik": 0, "filings": {"recent": {}}})
    proof, counts = probe_batch(
        CSV, DAY, "GEM Research authorized-contact@example.com",
        transport=httpx.MockTransport(bad))
    assert counts["ciks_failed"] == counts["ciks_attempted"]
    assert proof[-1][1]["state"] == "BLOCKED"
    assert all(receipt is None for receipt, _ in proof)


def test_no_placeholder_sec_user_agent():
    with pytest.raises(ValueError, match="SEC_USER_AGENT"):
        probe_batch(CSV, DAY, "generic scraper")

def test_original_sec_storage_budget_fails_closed():
    import random
    from gem_data.sec_daily_discovery import _bounded_compress, SourceUnavailable
    random_bytes = random.Random(178).randbytes(300_000)
    with pytest.raises(SourceUnavailable, match="storage budget"):
        _bounded_compress(random_bytes, 0)

def test_real_network_sec_pilot_is_bounded_to_three_issuers():
    ciks, total = select_ciks(CSV, DAY)
    counter = []
    def response(req):
        cik = str(req.url).split("CIK")[1].split(".json")[0]
        counter.append(cik)
        return httpx.Response(200, json={
            "cik": int(cik), "filings": {"recent": {
                "form": [], "accessionNumber": [], "filingDate": [],
                "acceptanceDateTime": []
            }}
        })
    evidence, summary = probe_batch(
        CSV, DAY, "GEM Research approved@example.com",
        transport=httpx.MockTransport(response), pilot_limit=3
    )
    assert len(counter) == 3
    assert len(set(counter)) == 3
    assert summary["ciks_attempted"] == 3
    assert summary["ciks_in_secondary_current_list"] == total
    assert len(evidence) == 4


def test_invalid_sec_pilot_limit_never_makes_a_network_request():
    with pytest.raises(ValueError, match="pilot limit"):
        probe_batch(CSV, DAY, "GEM Research approved@example.com",
                    pilot_limit=90)
