"""Offline tests for unattended GEM research evidence checks."""
import pytest
from gem_data.gem_research_robot import KEYS, evaluate

def report():
    return {"data_access":"CONNECTED","investment_release":"DATA_HOLD",
            "sources":[{"key":key,"source_approval":"NOT_APPROVED",
                        "progress_tag":"EVIDENCE PENDING","next_step":"Review evidence"}
                       for key in KEYS]}

def test_six_blockers_never_approve_trades():
    results=evaluate(report())
    assert len(results)==6
    assert all(r["status"]=="BLOCKED_EVIDENCE" for r in results)
    assert not any(r["trading_authorized"] or r["certified_by_robot"] for r in results)

def test_source_approval_only_reports_independent_status():
    data=report()
    data["sources"][0]["source_approval"]="APPROVED"
    results=evaluate(data)
    assert results[0]["status"]=="INDEPENDENT_REVIEW_COMPLETE"
    assert not results[0]["certified_by_robot"]

def test_fail_closed_on_bad_snapshot():
    data=report()
    data["sources"].pop()
    with pytest.raises(ValueError):
        evaluate(data)
    data=report()
    data["data_access"]="UNAVAILABLE"
    with pytest.raises(ValueError):
        evaluate(data)


def test_unattended_recovery_records_real_bounded_result(monkeypatch):
    from gem_data import gem_research_robot as robot
    from gem_data import gem_marketstack_backfill as backfill
    monkeypatch.setenv("GEM_MARKETSTACK_BACKFILL_ENABLED", "yes")
    calls = []
    def vendor(*, max_tickers):
        calls.append(max_tickers)
        return {"status": "OBSERVATIONS_ONLY_NOT_APPROVED",
                "observed_symbols": 2, "new_reserved": 2,
                "retry_eligible": 3, "held_for_source_review": 4,
                "monthly_remaining_local": 497}
    monkeypatch.setattr(backfill, "collect_batch", vendor)
    result = robot._recover_prices()
    assert calls == [3]
    assert result["observed"] == 2
    assert result["reserved"] == 2
    assert result["state"] == "OBSERVATIONS_ONLY_NOT_APPROVED"
    assert "trading_authorized" not in result


def test_unattended_recovery_holds_on_configuration_and_does_not_retry(monkeypatch):
    from gem_data import gem_research_robot as robot
    from gem_data import gem_marketstack_backfill as backfill
    monkeypatch.setenv("GEM_MARKETSTACK_BACKFILL_ENABLED", "yes")
    monkeypatch.setattr(backfill, "collect_batch",
                        lambda **kwargs: (_ for _ in ()).throw(backfill.MarketstackBackfillHold("test-only")))
    result = robot._recover_prices()
    assert result["state"] == "CONFIGURATION_OR_SOURCE_HOLD"
    assert result["reserved"] == 0


def test_unattended_recovery_off_when_not_opted_in(monkeypatch):
    from gem_data import gem_research_robot as robot
    monkeypatch.delenv("GEM_MARKETSTACK_BACKFILL_ENABLED", raising=False)
    assert robot._recover_prices()["state"] == "DISABLED"
