"""Offline original NYSE first-party source receipt fixtures."""
import httpx
import pytest

from scripts.gem_nyse_fetch_primary_2026 import (
    read_primary_nyse_calendar, CalendarSourceUnavailable, NYSE_URL,
    REQUIRED_MARKERS,
)


def test_primary_page_capture_sha_but_no_auto_certification():
    body = "<html><body>" + " ".join(REQUIRED_MARKERS) + "</body></html>"
    with httpx.Client(transport=httpx.MockTransport(
            lambda req: httpx.Response(200, text=body,
                                      headers={"content-type": "text/html"})
    )) as client:
        receipt, raw = read_primary_nyse_calendar(client)
    assert receipt["url"] == NYSE_URL
    assert receipt["response_bytes"] == len(raw)
    assert len(receipt["raw_sha256"]) == 64
    assert receipt["source_raw_observed"] is True
    assert receipt["independent_reviewer_approved"] is False
    assert receipt["trading_authorized"] is False


def test_unexpected_page_cannot_be_accepted_as_nyse_calendar():
    with httpx.Client(transport=httpx.MockTransport(
            lambda req: httpx.Response(200, text="<html>Login required</html>",
                                      headers={"content-type": "text/html"})
    )) as client:
        with pytest.raises(CalendarSourceUnavailable, match="markers incomplete"):
            read_primary_nyse_calendar(client)


def test_http_blocker_is_not_silently_treated_as_source_evidence():
    with httpx.Client(transport=httpx.MockTransport(
            lambda req: httpx.Response(403, text="blocked",
                                      headers={"content-type": "text/html"})
    )) as client:
        with pytest.raises(CalendarSourceUnavailable, match="unavailable"):
            read_primary_nyse_calendar(client)
