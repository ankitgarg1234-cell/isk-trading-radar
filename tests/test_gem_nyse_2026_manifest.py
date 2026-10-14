"""Offline NYSE schedule regression against known official 2026 source dates."""
from datetime import date
import pytest

from gem_data.gem_nyse_2026_manifest import (
    published_schedule_2026, HOLIDAYS_2026, EARLY_CLOSE_2026)


def test_2026_nyse_has_251_official_sessions_and_month_end():
    report = published_schedule_2026()
    sessions = [d["session"] for d in report["sessions"]]
    assert len(sessions) == len(set(sessions)) == 251
    assert report["month_end_sessions"]["2026-09"] == "2026-09-30"
    assert report["month_end_sessions"]["2026-10"] == "2026-10-30"
    assert "2026-10-01" in sessions
    assert "2026-07-03" not in sessions
    assert "2026-09-07" not in sessions
    assert all(day not in sessions for day in HOLIDAYS_2026)
    assert len(EARLY_CLOSE_2026) == 2
    assert report["actual_completed_sessions_verified"] is False
    assert report["calendar_trading_certified"] is False
    assert report["trade_authorized"] is False
    assert len(report["report_sha256"]) == 64


def test_timezone_transition_and_early_closures_match_published_rules():
    rows = {d["session"]: d for d in published_schedule_2026()["sessions"]}
    assert rows["2026-01-02"]["open_utc"] == "2026-01-02T14:30:00+00:00"
    assert rows["2026-03-09"]["open_utc"] == "2026-03-09T13:30:00+00:00"
    assert rows["2026-11-27"]["early_close"]
    assert rows["2026-11-27"]["close_utc"] == "2026-11-27T18:00:00+00:00"
    assert rows["2026-12-24"]["early_close"]
    assert rows["2026-12-24"]["close_utc"] == "2026-12-24T18:00:00+00:00"


def test_independent_calendar_comparison_fails_closed_on_difference():
    baseline = published_schedule_2026()
    sessions = [x["session"] for x in baseline["sessions"]]
    signed = published_schedule_2026(independent_exchange_calendar=sessions)
    assert signed["independent_schedule_reconciled"] is True
    assert signed["calendar_trading_certified"] is False
    with pytest.raises(ValueError, match="disagree"):
        published_schedule_2026(independent_exchange_calendar=sessions[:-1])
