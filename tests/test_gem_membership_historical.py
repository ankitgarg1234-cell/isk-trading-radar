from gem_data.membership_calendar import member_at, month_end_plan, CalendarMembershipHold
from gem_data.historical_claim_builder import build_claims
import pytest


def test_membership_effective_dates_control_inclusion():
    base=[{"security_id":"1","ticker":"DAY"}]
    events=[
        {"effective_date":"2026-02-09","announced_at":"2026-02-04",
         "security_id":"1","ticker":"DAY","action":"REMOVE",
         "primary_evidence_sha256":"a"*64},
        {"effective_date":"2026-02-09","announced_at":"2026-02-04",
         "security_id":"2","ticker":"CIEN","action":"ADD",
         "primary_evidence_sha256":"a"*64}]
    before=member_at(base,events,"2026-01-30")
    after=member_at(base,events,"2026-02-27")
    assert [m["ticker"] for m in before["universe"]]==["DAY"]
    assert [m["ticker"] for m in after["universe"]]==["CIEN"]
    assert after["independently_certified"] is False


def test_membership_invalid_rename_holds():
    with pytest.raises(CalendarMembershipHold):
        member_at([], [{"effective_date":"2026-01-02",
                        "announced_at":"2026-01-01","security_id":"X",
                        "ticker":"NEW","action":"RENAME"}],"2026-01-31")


def test_month_end_not_any_calendar_end():
    result=month_end_plan(["2026-01-29","2026-01-30","2026-02-02","2026-02-03"],
                          completed_through="2026-01-30",
                          official_receipt_sha256="a"*64)
    assert result[0]["signal_session"]=="2026-01-30"
    assert result[0]["next_session"]=="2026-02-02"
    assert result[0]["automatic_orders"] is False


def test_original_membership_and_split_claim_worklist():
    frozen={
        "membership":{"changes":[
            {"date":"2026-02-09","added":"CIEN","removed":"DAY"}]},
        "market":{"A":{"splits":[{"date":"2025-08-01","numerator":2,"denominator":1}],
                       "dividends":[{"date":"2025-08-05","amount":.25}]},
                  "WDC":{"splits":[],"dividends":[]}},
    }
    trades=[{"date":"2025-07-01","ticker":"A","experiment":"A_2025",
             "policy":"original","shares":"10","side":"BUY"}]
    signals=[{"date":"2025-06-30","policy":"original","tickers":"A|WDC"}]
    claims=build_claims(frozen,trades=trades,signals=signals)
    identified={x["claim_id"]:x for x in claims}
    assert "sp500:2026-02-09:ADDITION:CIEN" in identified
    assert "sp500:2026-02-09:DELETION:DAY" in identified
    assert identified["action:2025-08-01:SPLIT:A"]["impact"]=="HELD_DURING_REPLAY"
    assert "action:2025-02-24:SPINOFF:WDC:SNDK" in identified
    assert len(claims)==len(set(identified))
