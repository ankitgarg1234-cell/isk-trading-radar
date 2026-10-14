"""Test source QA stays separate from GEM collection speed and SPY return math."""
import math
import pytest

from gem_data.gem_price_repair_plan import plan_price_repairs
from gem_data.gem_spy_total_return_diagnostic import provisional_spy_total_return


def test_repair_plan_distinguishes_collection_from_verification():
    members=[f"X{i:03d}" for i in range(480)]
    receipts={
        "X000":{"provider":"MARKETSTACK","metadata":{
            "ticker":"X000","completed_sessions":127,
            "rejected_session_count":0,"fallback_needed":False}},
        "X001":{"provider":"MARKETSTACK","metadata":{
            "ticker":"X001","completed_sessions":100,
            "rejected_session_count":0,"fallback_needed":False}},
        "X002":{"provider":"MARKETSTACK","metadata":{
            "ticker":"X002","completed_sessions":150,
            "rejected_session_count":12,"fallback_needed":True}},
    }
    report=plan_price_repairs(members,receipts)
    assert report["members"]==480
    assert report["collected_members"]==3
    assert report["counts"]=={
        "VERIFY_SOURCE_ADJUSTMENT":1,
        "REPAIR_HISTORICAL_GAPS":1,
        "RECONCILE_REJECTED_VENDOR_BARS":1,
        "ACQUIRE_MISSING_VENDOR_HISTORY":477}
    assert len(report["sha256"])==64
    assert all(not row["complete_for_trading"]
               and not row["new_vendor_call_authorized"]
               for row in report["queue"])
    assert not report["ranking_authorized"]


def test_duplicate_or_forged_memberships_are_fail_closed():
    members=[f"X{i:03d}" for i in range(480)]
    with pytest.raises(ValueError):
        plan_price_repairs(members[:-1]+[members[0]],{})
    with pytest.raises(ValueError):
        plan_price_repairs(members,{"NVDA":{
            "provider":"MARKETSTACK","metadata":{}}})


def test_spy_dividend_reinvestment_does_not_omit_distribution():
    rows=[
        {"session":"2026-09-17","close":100.0,"dividend":0.0},
        {"session":"2026-09-18","close":99.0,"dividend":1.0},
        {"session":"2026-09-21","close":101.0,"dividend":0.0},
    ]
    result=provisional_spy_total_return(rows,
        expected_sessions=["2026-09-17","2026-09-18","2026-09-21"])
    assert math.isclose(result["total_return"],101/99 - 1,rel_tol=1e-12)
    assert result["dividend_events"]==1
    assert result["reported_index"][1]["total_return_index"]==1.0
    assert not result["total_return_benchmark_certified"]
    assert not result["trade_authorized"]


def test_spy_missing_dates_or_split_cannot_silently_pass():
    rows=[
        {"session":"2026-09-17","close":100.0},
        {"session":"2026-09-21","close":102.0},
    ]
    with pytest.raises(ValueError,match="sessions"):
        provisional_spy_total_return(rows,expected_sessions=[
            "2026-09-17","2026-09-18","2026-09-21"])
    with pytest.raises(ValueError,match="split"):
        provisional_spy_total_return([rows[0],dict(rows[1],stock_split=2)])


def test_spy_rejects_missing_close_and_nonfinite_cash_flow():
    rows=[{"session":"2026-09-17","close":100.0},
          {"session":"2026-09-18","close":None}]
    with pytest.raises(ValueError,match="raw close"):
        provisional_spy_total_return(rows)
    rows[1]={"session":"2026-09-18","close":99,
             "dividend":float("nan")}
    with pytest.raises(ValueError,match="cash dividend"):
        provisional_spy_total_return(rows)
