import copy
from datetime import datetime, timezone
from types import SimpleNamespace

from app.score_band_experiment import arm_trial, advance, new_state, trial_summary
from tests.test_score_band_experiment import observation


ARMED = "2026-10-04T13:00:00+00:00"


def state():
    s = new_state("MEDIUM")
    arm_trial(s, ARMED)
    return s


def test_unstarted_account_gets_approved_profile_without_balance_reset():
    s = new_state("MEDIUM")
    book = s["variants"]["complete_strategy"]
    before = copy.deepcopy(book)
    arm_trial(s, ARMED)
    assert s["spec"]["profile"] == "HIGH"
    assert s["spec"]["risk_per_trade_pct"] == 1.25
    assert book == before


def test_started_account_profile_and_ledger_are_preserved():
    s = new_state("AGGRESSIVE")
    s["started_at"] = "2026-10-02T14:00:00+00:00"
    book = s["variants"]["complete_strategy"]
    book["cash"] = 9000
    before = copy.deepcopy(book)
    arm_trial(s, ARMED)
    assert s["spec"]["profile"] == "AGGRESSIVE"
    assert book == before


def test_closed_market_does_not_start_clock():
    s = state(); a = observation()
    advance(s, [a], a["asof"], False, 100)
    assert s["trial"]["started_at"] is None
    assert s["trial"]["ends_at"] is None


def test_missing_analyst_and_stale_quotes_do_not_start_clock():
    s = state(); a = observation(analyst=None)
    advance(s, [a], a["asof"], True, 100)
    assert s["trial"]["started_at"] is None
    a = observation()
    advance(s, [a], "2026-10-05T14:11:00+00:00", True, 100)
    assert s["trial"]["started_at"] is None


def test_calendar_month_respects_new_york_dst_and_does_not_fill_signal():
    s = state(); a = observation(stop=99)
    advance(s, [a], a["asof"], True, 100)
    assert s["trial"]["started_at"] == a["asof"]
    assert s["trial"]["ends_at"] == "2026-11-05T15:00:00+00:00"
    assert s["variants"]["complete_strategy"]["trades"] == []
    later = observation(minute=2, stop=99)
    advance(s, [later], later["asof"], True, 101)
    out = trial_summary(s)
    assert out["trade_count"] == 1
    assert out["benchmark_return_pct"] == 1
    assert s["variants"]["complete_strategy"]["trades"][0]["shares"] == 39


def test_missing_start_benchmark_is_unavailable_not_backfilled():
    s = state(); a = observation()
    advance(s, [a], a["asof"], True)
    assert s["trial"]["status"] == "running"
    a = observation(minute=2)
    advance(s, [a], a["asof"], True, 101)
    assert trial_summary(s)["benchmark_return_pct"] is None
    assert trial_summary(s)["excess_return_pct"] is None


def test_stale_benchmark_is_not_reported_as_current():
    s = state(); a = observation()
    advance(s, [a], a["asof"], True, 100)
    a = observation(minute=11)
    advance(s, [a], a["asof"], True)
    assert trial_summary(s)["benchmark_return_pct"] is None


def test_deadline_freezes_book_without_post_deadline_fills_or_forced_sale():
    s = state(); a = observation(stop=99)
    advance(s, [a], a["asof"], True, 100)
    a = observation(minute=2, stop=99)
    advance(s, [a], a["asof"], True, 101)
    book = s["variants"]["complete_strategy"]
    before = copy.deepcopy(book)
    after = observation(price=200)
    after["asof"] = "2026-11-05T15:00:00+00:00"
    advance(s, [after], after["asof"], True, 200)
    assert s["trial"]["status"] == "completed"
    assert book["positions"] == before["positions"]
    assert book["marks"] == before["marks"]
    assert book["trades"] == before["trades"]
    assert s["trial"]["valuation_asof"] == "2026-10-05T14:02:00+00:00"
    frozen = copy.deepcopy(s)
    arm_trial(s, "2026-12-01T14:00:00+00:00")
    advance(s, [], "2026-12-01T14:00:00+00:00", False)
    assert s == frozen


def test_calendar_month_clamps_month_end():
    s = state(); a = observation()
    a["asof"] = "2027-01-31T15:00:00+00:00"
    advance(s, [a], a["asof"], True, 100)
    assert s["trial"]["ends_at"] == "2027-02-28T15:00:00+00:00"


def test_activation_uses_preserved_equity_not_assumed_ten_thousand():
    s = new_state("HIGH"); s["started_at"] = ARMED
    s["variants"]["complete_strategy"]["cash"] = 9000
    arm_trial(s, ARMED)
    a = observation(score=69)
    advance(s, [a], a["asof"], True, 100)
    assert s["trial"]["baseline_equity"] == 9000
    assert trial_summary(s)["return_pct"] == 0


def test_arm_and_clock_persist_without_resetting_on_status_reload(monkeypatch):
    from app import score_band_capture as capture
    monkeypatch.setattr(capture, "settings", SimpleNamespace(score_band_trial_armed_at=ARMED))
    monkeypatch.setattr(capture, "fresh_benchmark", lambda now: (100, now.isoformat()))
    initial = capture.experiment_status()
    assert initial["spec"]["profile"] == "HIGH"
    assert initial["trial"]["status"] == "waiting_for_inputs"
    a = observation(stop=99)
    capture.run_experiment_cycle([a], True, datetime.fromisoformat(a["asof"]))
    first = capture.experiment_status(True)
    again = capture.experiment_status(True)
    assert first == again
    assert first["trial"]["ends_at"] == "2026-11-05T15:00:00+00:00"


def test_benchmark_rejects_old_exchange_time_not_retrieval_time(monkeypatch):
    from app import score_band_capture as capture
    monkeypatch.setattr(capture._BENCHMARK_PROVIDER, "chart", lambda *args: {
        "meta": {"regularMarketPrice": 100, "regularMarketTime": 1}})
    assert capture.fresh_benchmark(datetime(2026, 10, 5, 14, tzinfo=timezone.utc)) == (None, None)


def test_benchmark_accepts_fresh_exchange_quote(monkeypatch):
    from app import score_band_capture as capture
    now = datetime(2026, 10, 5, 14, tzinfo=timezone.utc)
    monkeypatch.setattr(capture._BENCHMARK_PROVIDER, "chart", lambda *args: {
        "meta": {"regularMarketPrice": 100, "regularMarketTime": now.timestamp()}})
    assert capture.fresh_benchmark(now) == (100, now.isoformat())
