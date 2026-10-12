"""Pure offline regression fixtures, no vendor keys or billable requests."""
from gem_data.marketstack_history_quality import audit_eod_coverage
import pytest


def row(symbol, day, **update):
    base = {
        "symbol": symbol,
        "date": day + "T00:00:00+0000",
        "open": 100.0, "high": 105.0, "low": 99.0,
        "close": 103.0, "adj_close": 102.0, "volume": 50000,
    }
    base.update(update)
    return base


def test_cross_exchange_june_2026_null_closes_hold_without_fill():
    days = ["2026-06-09", "2026-06-10", "2026-06-15"]
    rows = [
        row(s, d, close=None, adj_close=None)
        for s in ("AAPL", "SPY", "JPM")
        for d in days
    ]
    result = audit_eod_coverage(
        rows, symbols=["AAPL", "SPY", "JPM"], completed_sessions=days
    )
    assert result["status"] == "HOLD"
    assert result["certified"] is False
    assert result["issue_count"] == 18
    assert {x["reason"] for x in result["reported_issues"]} == {
        "INVALID_CLOSE", "INVALID_ADJ_CLOSE"
    }
    assert {x["session"] for x in result["reported_issues"]} == set(days)


def test_missing_interior_date_detected_even_if_vendor_row_count_plausible():
    days = ["2026-06-08", "2026-06-09", "2026-06-10"]
    result = audit_eod_coverage(
        [row("AAPL", days[0]), row("AAPL", days[2])],
        symbols=["AAPL"], completed_sessions=days
    )
    assert result["issue_count"] == 1
    assert result["reported_issues"][0] == {
        "symbol": "AAPL", "session": "2026-06-09", "reason": "MISSING_VENDOR_ROW"
    }


def test_complete_healthy_vendor_shape_does_not_certify_source():
    result = audit_eod_coverage(
        [row("JPM", "2026-06-09")], symbols=["JPM"],
        completed_sessions=["2026-06-09"]
    )
    assert result["issue_count"] == 0
    assert result["certified"] is False
    assert result["status"] == "UNVERIFIED_LOCAL_SHAPE_ONLY"


def test_duplicate_unexpected_and_bad_ohlc_all_block():
    result = audit_eod_coverage(
        [row("AAPL", "2026-06-09", high=90),
         row("AAPL", "2026-06-09"),
         row("AAPL", "2026-06-12")],
        symbols=["AAPL"], completed_sessions=["2026-06-09"]
    )
    assert result["status"] == "HOLD"
    assert {r["reason"] for r in result["reported_issues"]} == {
        "INVALID_NOMINAL_OHLC", "DUPLICATE_VENDOR_ROW", "UNEXPECTED_VENDOR_ROW"
    }


def test_rejects_fake_or_unsorted_completed_session_manifest():
    with pytest.raises(ValueError):
        audit_eod_coverage([], symbols=["AAPL"],
                           completed_sessions=["2026-06-10", "2026-06-09"])
    with pytest.raises(ValueError):
        audit_eod_coverage([], symbols=["AAPL", "AAPL"],
                           completed_sessions=["2026-06-09"])


def test_issue_count_preserved_when_report_is_capped():
    dates = ["2026-06-09", "2026-06-10", "2026-06-15"]
    result = audit_eod_coverage(
        [], symbols=["AAPL", "JPM"], completed_sessions=dates,
        max_reported_issues=2
    )
    assert result["status"] == "HOLD"
    assert result["issue_count"] == 6
    assert len(result["reported_issues"]) == 2
    assert result["issues_truncated"] is True
