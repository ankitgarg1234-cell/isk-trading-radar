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


def test_next_day_transient_failures_retry_but_bad_symbols_hold():
    from datetime import date
    symbols = ["AAPL", "BRK.B", "MSFT", "WEC"]
    attempts = {
        "AAPL": {"days": ["20261013"], "last_reason": None},
        "BRK.B": {"days": ["20261013"], "last_reason": "no valid vendor historical prices found"},
        "MSFT": {"days": ["20261013"], "last_reason": "Marketstack EOD request or JSON failed"},
        "WEC": {"days": ["20261013"], "last_reason": None},
    }
    eligible, held = m._retry_candidates(symbols, {"AAPL"}, attempts, date(2026, 10, 14))
    assert eligible == ["MSFT", "WEC"]
    assert held == ["BRK.B"]


def test_never_repeat_same_day_or_more_than_two_attempts():
    from datetime import date
    attempts = {
        "A": {"days": ["20261014"], "last_reason": None},
        "B": {"days": ["20261012", "20261013"], "last_reason": None},
        "C": {"days": [], "last_reason": None},
    }
    eligible, held = m._retry_candidates(["A", "B", "C"], set(), attempts, date(2026, 10, 14))
    assert eligible == ["C"]
    assert held == ["A", "B"]


def test_all_attempted_does_not_falsely_report_monthly_exhaustion(monkeypatch):
    from datetime import date
    monkeypatch.setattr(m, "_db_urls", lambda: ("reader", "writer", 1000))
    monkeypatch.setattr(m, "_universe_and_spend",
                        lambda *args: (["AAA"], 503, set(),
                                      {"AAA": {"days": ["20261014"], "last_reason": None}}))
    monkeypatch.setattr(m, "_reserve_request",
                        lambda *args: (_ for _ in ()).throw(AssertionError("no vendor request due")))
    result = m.collect_batch(max_tickers=1,
                             observed=datetime(2026, 10, 14, 13, tzinfo=timezone.utc))
    assert result["monthly_remaining_local"] == 497
    assert result["pending_symbols_before"] == 1
    assert result["status"] == "RETRY_BACKOFF_OR_SOURCE_REVIEW_REQUIRED"
    assert result["new_reserved"] == 0


def test_retry_proceeds_with_remaining_credit_and_no_approval(monkeypatch):
    calls = []
    monkeypatch.setattr(m, "_db_urls", lambda: ("reader", "writer", 1000))
    monkeypatch.setattr(m, "_universe_and_spend",
                        lambda *args: (["AAA"], 503, set(),
                                      {"AAA": {"days": ["20261013"],
                                               "last_reason": "Marketstack EOD request or JSON failed"}}))
    monkeypatch.setattr(m, "_reserve_request",
                        lambda reader, writer, ticker, observed, cap: calls.append(ticker) or True)
    monkeypatch.setattr(m, "_persist_observation", lambda *args: 127)
    result = m.collect_batch(max_tickers=1,
                             observed=datetime(2026, 10, 14, 13, tzinfo=timezone.utc),
                             fetch_fn=lambda *args: ([object()], object()))
    assert calls == ["AAA"]
    assert result["status"] == "OBSERVATIONS_ONLY_NOT_APPROVED"
    assert result["new_reserved"] == 1
    assert result["certified"] is False
    assert result["automatic_trading"] is False
