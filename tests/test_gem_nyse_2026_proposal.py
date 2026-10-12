"""NYSE calendar proposal tests: official 2026 dates, DST and fail-closed status."""
from datetime import datetime, timezone
import pytest
from gem_data.nyse_2026_proposal import proposed_nyse_calendar_2026


def build(start="2026-06-01", end="2026-06-30", observed="2026-10-12T22:00:00+00:00"):
    return proposed_nyse_calendar_2026(
        start=start, end=end, observed_at=datetime.fromisoformat(observed)
    )


def test_missing_marketstack_june_dates_are_real_nyse_sessions():
    proposal = build()
    dates = {r["session"] for r in proposal["sessions"]}
    assert {"2026-06-09", "2026-06-10", "2026-06-15"} <= dates
    assert "2026-06-19" not in dates
    assert proposal["status"] == "PROPOSED_SCHEDULE_ONLY"
    assert proposal["primary_source_independently_certified"] is False
    assert proposal["source_raw_receipt_sha256"] is None
    assert proposal["trading_authorized"] is False


def test_known_2026_thanksgiving_and_christmas_half_sessions():
    p = build("2026-11-01", "2026-12-31")
    idx = {r["session"]: r for r in p["sessions"]}
    assert "2026-11-26" not in idx
    assert "2026-12-25" not in idx
    assert idx["2026-11-27"]["early_close"]
    assert idx["2026-11-27"]["close_utc"] == "2026-11-27T18:00:00+00:00"
    assert idx["2026-12-24"]["early_close"]
    assert idx["2026-12-24"]["close_utc"] == "2026-12-24T18:00:00+00:00"


def test_september_month_end_and_october_next_open():
    p = build("2026-09-01", "2026-10-31")
    sep = p["month_ends"]["2026-09"]
    assert sep["month_end_session"] == "2026-09-30"
    assert sep["next_session"] == "2026-10-01"
    assert sep["next_open_utc"] == "2026-10-01T13:30:00+00:00"
    assert sep["month_end_completed"] is True


def test_daylight_saving_and_bank_holiday_dont_move_equity_open():
    p = build("2026-10-01", "2026-11-10")
    idx = {r["session"]: r for r in p["sessions"]}
    assert idx["2026-10-12"]["open_utc"] == "2026-10-12T13:30:00+00:00"
    assert idx["2026-11-02"]["open_utc"] == "2026-11-02T14:30:00+00:00"


def test_incomplete_current_session_cannot_be_treated_as_completed():
    p = build("2026-10-12", "2026-10-12", "2026-10-12T15:00:00+00:00")
    assert p["sessions"][0]["completed_at_observation"] is False


def test_reject_unsupported_year_and_naive_observation():
    with pytest.raises(ValueError):
        build("2027-01-01", "2027-01-31")
    with pytest.raises(ValueError, match="timezone-aware"):
        proposed_nyse_calendar_2026(
            start="2026-09-01", end="2026-09-30",
            observed_at=datetime(2026, 9, 30, 20, 0)
        )
