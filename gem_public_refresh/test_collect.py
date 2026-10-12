"""Offline fixtures only; daily workflow makes real public requests separately."""
from datetime import datetime, timezone
import httpx
from gem_public_refresh.collect import (
    NYSE_URL, MEMBERS_URL, NYSE_MARKERS,
    capture_sources, fetch_bounded, BadSource,
)


def client(nyse=True, members=True):
    raw_members = ("Symbol,CIK\\n" + "".join(
        f"TEST{i}, {i + 1000000}\\n" for i in range(500))).replace("\\n", "\n").encode()
    def respond(request):
        if str(request.url) == NYSE_URL:
            if not nyse:
                return httpx.Response(403, content=b"Access denied")
            return httpx.Response(200, text="<html><body>" +
                                  " ".join(NYSE_MARKERS) + "</body></html>",
                                  headers={"content-type": "text/html"})
        if str(request.url) == MEMBERS_URL:
            if not members:
                return httpx.Response(503, content=b"unavailable")
            return httpx.Response(200, content=raw_members,
                                  headers={"content-type": "text/plain"})
        raise AssertionError("Unapproved URL")
    return httpx.Client(transport=httpx.MockTransport(respond))


def test_genuine_shape_of_two_source_observations_never_certifies():
    with client() as c:
        status, raw = capture_sources(
            client=c, observed=datetime(2026, 10, 12, 23, tzinfo=timezone.utc))
    assert status["independently_certified_count"] == 0
    assert not status["trading_authorized"]
    assert status["sources"]["calendar"]["status"] == "PARTIAL"
    assert status["sources"]["membership"]["status"] == "PARTIAL"
    assert status["sources"]["membership"]["security_lines"] == 500
    assert len(raw) == 2
    assert all(item["certified"] is False for item in status["sources"].values())
    assert status["sources"]["prices"]["status"] == "BLOCKED"


def test_source_failure_never_gets_a_fresh_status():
    with client(nyse=False) as c:
        status, raw = capture_sources(
            client=c, observed=datetime(2026, 10, 12, 23, tzinfo=timezone.utc))
    assert status["sources"]["calendar"]["status"] == "BLOCKED"
    assert status["sources"]["calendar"]["observation_fresh"] is False
    assert status["sources"]["membership"]["status"] == "PARTIAL"
    assert "nyse-2026-source.html" not in raw


def test_future_year_blocks_2026_schedule_as_stale():
    with client() as c:
        status, raw = capture_sources(
            client=c, observed=datetime(2027, 1, 2, tzinfo=timezone.utc))
    assert status["sources"]["calendar"]["status"] == "BLOCKED"


def test_unapproved_url_does_not_fetch():
    with client() as c:
        try:
            fetch_bounded(c, "https://example.org/", limit=10, media_type="text/plain")
        except BadSource:
            pass
        else:
            raise AssertionError("Should reject unapproved source")
