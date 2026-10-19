"""Integrity projections are evidence summaries, not trading certification."""
from datetime import datetime, timezone
from gem_data.gem_source_health import classify


def test_machine_complete_does_not_certify_missing_competitors():
    now=datetime(2026,10,13,10,0,tzinfo=timezone.utc)
    receipts=[
       {"source_type":"membership","provider":"SECONDARY_GITHUB_SP500","receipt_count":2,
        "unique_members":0,"refreshed_at":now},
       {"source_type":"sec","provider":"SEC_ZIP_SUBMISSIONS","receipt_count":1000,
        "unique_members":500,"refreshed_at":now},
       {"source_type":"sec","provider":"SEC_ZIP_COMPANYFACTS","receipt_count":1000,
        "unique_members":500,"refreshed_at":now},
    ]
    report=classify(receipts,[{"source_type":"sec","last_checked":now}],
         {"inspected":415,"machine_complete":259,"certified":0,
          "verified_receipts":27,"last_audited":now},
         membership_count=503,ibkr_sample_count=4,approved_signals=0,checked_at=now)
    assert report["sec"]["source_pairs"]==500
    assert report["sec"]["machine_incomplete_or_unknown"]==156
    assert report["sec"]["not_machine_assessed"]==85
    assert report["sec"]["independently_certified"]==0
    assert report["prices"]["marketstack_fully_verified"]==0
    assert report["prices"]["ibkr_diagnostic_sample"]==4
    assert report["approved_monthly_signals"]==0
    assert all(s["stages"][-1]["state"]=="PENDING" for s in report["sources"])
    sec=next(s for s in report["sources"] if s["key"]=="sec")
    assert sec["last_refreshed"] and sec["last_audited"]


def test_no_evidence_unknown_not_full_coverage():
    out=classify([],[],{},membership_count=0)
    assert out["investment_release"]=="DATA_HOLD"
    assert out["sec"]["source_pairs"]==0
    assert out["prices"]["security_lines_target"]==0
    assert all(s["status"]=="NO_EVIDENCE" for s in out["sources"])

def test_dashboard_unavailable_never_uses_fictitious_zeroes():
    from gem_data.gem_source_health import unavailable_integrity
    result = unavailable_integrity()
    assert result["data_access"] == "UNAVAILABLE"
    assert len(result["sources"]) == 6
    assert result["approved_monthly_signals"] is None
    assert result["prices"]["overall_fully_verified"] is None
    assert result["sec"]["independently_certified"] is None
    assert all(s["status"] == "UNAVAILABLE" for s in result["sources"])


def test_source_projection_does_not_query_unauthorized_audit_table():
    import inspect
    from gem_data.gem_source_health import read_source_integrity
    source = inspect.getsource(read_source_integrity)
    assert "FROM gem_sec_independent_receipt_audit" not in source
