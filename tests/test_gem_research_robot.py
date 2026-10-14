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
