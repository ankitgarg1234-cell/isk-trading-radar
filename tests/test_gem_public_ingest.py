"""No-network GEM-only public source ingestion contract tests."""
import base64
from datetime import datetime, timezone, timedelta
import json
import zlib
import httpx
import pytest

from gem_data.gem_public_ingest import (
    NYSE, SECONDARY, MARKERS, fetch_one, evidence_records, next_daily_run,
    write_observation, InvalidEvidence,
)

NOW = datetime(2026, 10, 12, 21, 0, tzinfo=timezone.utc)


def mock():
    csv = ("Symbol,CIK\n" + "".join(
        f"TEST{i},{1000000 + i}\n" for i in range(500)
    )).encode()
    html = ("<html><body>" + " ".join(MARKERS) + "</body></html>").encode()
    def get(req):
        if str(req.url) == NYSE:
            return httpx.Response(200, content=html,
                                  headers={"content-type": "text/html"})
        if str(req.url) == SECONDARY:
            return httpx.Response(200, content=csv,
                                  headers={"content-type": "text/plain"})
        raise AssertionError("unexpected URL")
    return httpx.Client(transport=httpx.MockTransport(get))


def test_primary_calendar_original_bytes_are_persistable_and_not_certified():
    with mock() as c:
        raw, metrics = fetch_one(c, "calendar")
    receipt, probe = evidence_records("calendar", NOW, raw, metrics)
    saved = receipt["metadata"]
    assert zlib.decompress(base64.b64decode(saved["source_raw_zlib_base64"])) == raw
    assert saved["source_raw_sha256"] == receipt["source_sha256"]
    assert not saved["certified"]
    assert not probe["details"]["trading_authorized"]
    assert probe["state"] == "PARTIAL"
    assert receipt["coverage_status"] == "UNKNOWN"


def test_secondary_membership_is_not_point_in_time_evidence():
    with mock() as c:
        raw, metrics = fetch_one(c, "membership")
    assert metrics["security_lines"] == 500
    assert not metrics["official_point_in_time_membership"]
    receipt, probe = evidence_records("membership", NOW, raw, metrics)
    assert "Secondary current membership" in probe["details"]["proof"]
    assert not receipt["metadata"]["certified"]


def test_failed_source_produces_blocked_probe_without_receipt():
    receipt, probe = evidence_records("calendar", NOW, None, None, reason="HTTP denied")
    assert receipt is None
    assert probe["state"] == "BLOCKED"
    assert probe["sample_count"] == 0
    assert probe["details"]["certified"] is False


def test_writer_only_inserts_in_preexisting_isolated_gem_tables():
    receipt, probe = evidence_records("calendar", NOW, b"raw", {"test": 1})
    calls = []
    class Cur:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def execute(self, query, args=None):
            calls.append((query, args))
    class Conn:
        def cursor(self): return Cur()
    write_observation(Conn(), receipt, probe)
    assert calls[0][0] == "SET TRANSACTION READ WRITE"
    assert calls[1][0] == "SET LOCAL statement_timeout = 7000"
    assert len(calls) == 4
    assert all("gem_" in sql and "INSERT INTO" in sql for sql, _ in calls[2:])
    assert all("ON CONFLICT" in sql for sql, _ in calls[2:])
    assert all("UPDATE" not in sql.upper() and "DELETE" not in sql.upper()
               for sql, _ in calls)


def test_scheduler_uses_utc_even_when_clock_is_daylight_saving_offset():
    now = datetime.fromisoformat("2026-10-12T21:50:00+02:00")
    assert next_daily_run(now).isoformat() == "2026-10-12T23:45:00+00:00"
    assert next_daily_run(datetime(2026, 10, 12, 23, 50, tzinfo=timezone.utc)) == (
        datetime(2026, 10, 13, 23, 45, tzinfo=timezone.utc))
