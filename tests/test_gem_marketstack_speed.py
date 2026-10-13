"""No-network regression checks for faster, credit-limited Marketstack collection."""
from datetime import datetime, timezone

import pytest
from gem_data import gem_marketstack_backfill as m


OBSERVED = datetime(2026, 10, 13, 13, 0, tzinfo=timezone.utc)


def setup_batch(monkeypatch, *, used=0, count=100, cap=1000):
    calls = []
    monkeypatch.setattr(m, "_db_urls", lambda: ("readonly", "appendonly", cap))
    monkeypatch.setattr(
        m, "_universe_and_spend",
        lambda reader, month, today: (
            [f"T{i:03}" for i in range(count)], used, set(), set()
        ),
    )
    def reserve(reader, writer, symbol, observed, cap):
        calls.append(symbol)
        return True
    monkeypatch.setattr(m, "_reserve_request", reserve)
    monkeypatch.setattr(m, "_persist_observation", lambda *a: 127)
    monkeypatch.setattr(m, "_record_failed_observation", lambda *a: None)
    return calls


def test_twenty_securities_per_batch_without_exceeding_limit(monkeypatch):
    reserved = setup_batch(monkeypatch)
    report = m.collect_batch(
        observed=OBSERVED,
        fetch_fn=lambda symbol, first, last: ([object()], object()),
    )
    assert len(reserved) == 20
    assert report["new_reserved"] == 20
    assert report["observed_symbols"] == 20
    assert report["observed_bars"] == 2540
    assert report["certified"] is False
    assert report["automatic_trading"] is False


def test_quota_remaining_is_never_exceeded(monkeypatch):
    reserved = setup_batch(monkeypatch, used=993)
    report = m.collect_batch(
        observed=OBSERVED,
        fetch_fn=lambda symbol, first, last: ([object()], object()),
    )
    assert len(reserved) == 7
    assert report["new_reserved"] == 7


def test_provider_429_circuit_breaker_stops_extra_charges(monkeypatch):
    reserved = setup_batch(monkeypatch)
    def vendor(*args):
        raise m.MarketstackProbeError("MARKETSTACK_HTTP_429")
    report = m.collect_batch(observed=OBSERVED, fetch_fn=vendor)
    assert len(reserved) == 1
    assert report["status"] == "PROVIDER_OR_SYSTEMIC_FAILURE_PAUSED"
    assert report["pause_reason"] == "MARKETSTACK_HTTP_429"


def test_three_consecutive_missing_fields_pause_and_save_budget(monkeypatch):
    reserved = setup_batch(monkeypatch)
    def vendor(*args):
        raise m.MarketstackProbeError("missing or invalid vendor field: close")
    report = m.collect_batch(observed=OBSERVED, fetch_fn=vendor)
    assert len(reserved) == 3
    assert len(report["failed"]) == 3
    assert report["status"] == "PROVIDER_OR_SYSTEMIC_FAILURE_PAUSED"


def test_unapproved_outside_initial_month(monkeypatch):
    setup_batch(monkeypatch)
    with pytest.raises(m.MarketstackBackfillHold, match="expired"):
        m.collect_batch(observed=datetime(2026, 11, 1, tzinfo=timezone.utc))
