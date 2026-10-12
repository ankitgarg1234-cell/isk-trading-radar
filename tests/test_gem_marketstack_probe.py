"""Offline Marketstack probe contract tests: no credentials or network calls."""
from datetime import date

import httpx
import pytest

from gem_data.marketstack_eod_probe import MarketstackEODProbe, MarketstackProbeError


def bar(session: str, **updates):
    result = {
        "symbol": "AAPL", "date": session + "T00:00:00+0000",
        "open": 101, "high": 105, "low": 100, "close": 104,
        "volume": 1234567, "adj_close": 103,
        "split_factor": 1, "dividend": 0,
    }
    result.update(updates)
    return result


def fake_transport(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_reads_two_pages_in_order_and_hashes_raw_receipts():
    calls = []

    def respond(request):
        calls.append(request)
        offset = int(request.url.params["offset"])
        data = (
            [bar("2026-10-01"), bar("2026-10-02")]
            if offset == 0 else [bar("2026-10-05")]
        )
        return httpx.Response(200, json={
            "pagination": {"total": 3, "count": len(data), "offset": offset, "limit": 2},
            "data": data,
        })

    with fake_transport(respond) as client:
        with MarketstackEODProbe(key="test-secret", client=client, page_limit=2) as p:
            bars, receipt = p.fetch("aapl", date(2026, 10, 1), date(2026, 10, 5))
            assert len(bars) == 3
            assert receipt.consumed_symbol_credits == 2
            assert receipt.retrieved_pages == 2
            assert p.consumed_credits == 2
            assert bars[0].vendor_adj_close == 103
            assert len(receipt.response_sha256) == 2
            assert len(receipt.response_sha256[0]) == 64
            assert all(req.url.path == "/v2/eod" for req in calls)
            assert all(req.url.params["symbols"] == "AAPL" for req in calls)
            assert all(req.url.params["access_key"] == "test-secret" for req in calls)
            assert receipt.status == "UNVERIFIED_VENDOR_OBSERVATION"


def test_missing_vendor_adjusted_close_is_not_silently_replaced():
    with fake_transport(lambda _: httpx.Response(200, json={
        "pagination": {"total": 1, "count": 1, "offset": 0},
        "data": [bar("2026-10-01", adj_close=None)],
    })) as client:
        with MarketstackEODProbe(key="dummy", client=client) as p:
            with pytest.raises(MarketstackProbeError, match="adj_close"):
                p.fetch("AAPL", date(2026, 10, 1), date(2026, 10, 2))


def test_rejects_vendor_symbol_mismatch():
    with fake_transport(lambda _: httpx.Response(200, json={
        "pagination": {"total": 1, "count": 1, "offset": 0},
        "data": [bar("2026-10-01", symbol="MSFT")],
    })) as client:
        with MarketstackEODProbe(key="dummy", client=client) as p:
            with pytest.raises(MarketstackProbeError, match="symbol mismatch"):
                p.fetch("AAPL", date(2026, 10, 1), date(2026, 10, 2))


def test_fails_closed_on_credit_limit_before_second_page():
    def reply(req):
        return httpx.Response(200, json={
            "pagination": {"total": 2, "count": 1, "offset": 0},
            "data": [bar("2026-10-01")],
        })

    with fake_transport(reply) as client:
        with MarketstackEODProbe(key="dummy", client=client, max_credits=1) as p:
            with pytest.raises(MarketstackProbeError, match="budget exhausted"):
                p.fetch("AAPL", date(2026, 10, 1), date(2026, 10, 2))
            assert p.consumed_credits == 1


def test_http_error_does_not_expose_key():
    with fake_transport(lambda _: httpx.Response(401, json={"error": "bad key"})) as client:
        with MarketstackEODProbe(key="top-secret", client=client) as p:
            with pytest.raises(MarketstackProbeError) as exc:
                p.fetch("AAPL", date(2026, 10, 1), date(2026, 10, 2))
            assert "top-secret" not in str(exc.value)


def test_invalid_ohlc_rejected():
    with fake_transport(lambda _: httpx.Response(200, json={
        "pagination": {"total": 1, "count": 1, "offset": 0},
        "data": [bar("2026-10-01", high=99)],
    })) as client:
        with MarketstackEODProbe(key="dummy", client=client) as p:
            with pytest.raises(MarketstackProbeError, match="OHLC"):
                p.fetch("AAPL", date(2026, 10, 1), date(2026, 10, 2))


def test_invalid_future_window_rejected_without_request():
    with fake_transport(lambda _: (_ for _ in ()).throw(AssertionError("network call"))) as client:
        with MarketstackEODProbe(key="dummy", client=client) as p:
            with pytest.raises(ValueError, match="future"):
                p.fetch("AAPL", date(2090, 1, 1), date(2090, 1, 5))
