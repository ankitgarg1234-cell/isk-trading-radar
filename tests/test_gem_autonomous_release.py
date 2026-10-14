"""Pure GEM release gate tests: robot never self-certifies or routes orders."""
from datetime import datetime,timezone
import copy
import pytest
from gem_data.gem_autonomous_release import SOURCE_KEYS, FROZEN_COMMIT, evaluate_release,ReadinessHold


def facts():
    integrity={
        "data_access":"CONNECTED", "membership_security_lines":503,
        "approved_monthly_signals":0,
        "prices":{"overall_fully_verified":0},
        "sec":{"source_pairs":500,"independently_certified":0},
        "sources":[{"key":key,"status":"PARTIAL","source_approval":"NOT_APPROVED",
                    "progress_tag":"MACHINE SOURCE ONLY","next_step":"Get original QA"}
                   for key in SOURCE_KEYS],
    }
    price={"data_access":"CONNECTED",
           "collection":{"security_lines_target":503,"marketstack_histories_stored":499},
           "stored_receipt_audit":{"integrity_pass":499},
           "verification":{"independently_certified_price_histories":0}}
    ledger={"experiment_frozen_commit":FROZEN_COMMIT,"mode":"SHADOW",
            "execution_enabled":False,"qa_approved_valid":0,
            "prospective_shadow_sessions":0}
    return integrity,price,ledger


def test_current_data_explicitly_blocks_every_production_prerequisite():
    report=evaluate_release(*facts(),at=datetime(2026,10,14,14,tzinfo=timezone.utc))
    assert report["schema"]=="gem-autonomous-production-gates-v1"
    assert report["production_trading_ready"] is False
    assert report["trading_enabled"] is False
    assert report["robot_can_certify_sources"] is False
    assert report["robot_can_authorize_trades"] is False
    assert report["research_inputs_ready"] is False
    assert "source_prices" in report["blocked_gates"]
    assert "source_sec" in report["blocked_gates"]
    assert "prospective_shadow_20_sessions" in report["blocked_gates"]
    assert "separate_execution_controls" in report["blocked_gates"]


def test_release_reports_actual_raw_receipt_hash_count():
    report=evaluate_release(*facts())
    raw=next(x for x in report["gates"] if x["key"]=="complete_verified_price_universe")
    assert "499 intact stored receipts" in raw["evidence"]
    assert raw["passed"] is False


def test_raw_price_sha_success_not_equivalent_to_cross_vendor_approval():
    integrity,price,ledger=facts()
    price["collection"]["marketstack_histories_stored"]=503
    price["stored_receipt_audit"]["raw_integrity_pass"]=503
    report=evaluate_release(integrity,price,ledger)
    assert "complete_verified_price_universe" in report["blocked_gates"]


def test_all_source_labels_alone_never_unlock_unreviewed_signal():
    integrity,price,ledger=facts()
    for source in integrity["sources"]:
        source["source_approval"]="APPROVED"
        source["status"]="VERIFIED"
    price["collection"]["marketstack_histories_stored"]=503
    price["verification"]["independently_certified_price_histories"]=503
    integrity["prices"]["overall_fully_verified"]=503
    integrity["sec"]["independently_certified"]=500
    report=evaluate_release(integrity,price,ledger)
    assert report["research_inputs_ready"] is False
    assert "reviewer_independent_qa" in report["blocked_gates"]
    assert "full_universe_rank_release" in report["blocked_gates"]


def test_complete_research_gate_never_enables_unimplemented_broker():
    integrity,price,ledger=facts()
    for s in integrity["sources"]:
        s["source_approval"]="APPROVED";s["status"]="VERIFIED"
    price["collection"]["marketstack_histories_stored"]=503
    price["verification"]["independently_certified_price_histories"]=503
    integrity["prices"]["overall_fully_verified"]=503
    integrity["sec"]["independently_certified"]=500
    integrity["approved_monthly_signals"]=1
    ledger["qa_approved_valid"]=1
    ledger["prospective_shadow_sessions"]=20
    out=evaluate_release(integrity,price,ledger)
    assert out["research_inputs_ready"] is True
    assert out["production_trading_ready"] is False
    assert out["blocked_gates"]==["separate_execution_controls"]


@pytest.mark.parametrize("action",[
    lambda i,p,l: i.update(data_access="UNAVAILABLE"),
    lambda i,p,l: p.update(data_access="UNAVAILABLE"),
    lambda i,p,l: i["sources"].pop(),
    lambda i,p,l: i.update(membership_security_lines=505),
    lambda i,p,l: l.pop("qa_approved_valid"),
    lambda i,p,l: l.update(qa_approved_valid=-1),
    lambda i,p,l: l.update(prospective_shadow_sessions="20"),
    lambda i,p,l: l.update(execution_enabled="true"),
])
def test_missing_or_inconsistent_evidence_fails_closed(action):
    i,p,l=facts()
    action(i,p,l)
    with pytest.raises(ReadinessHold):
        evaluate_release(i,p,l)


def test_frozen_commit_mismatch_is_tracked_not_silently_changed():
    i,p,l=facts()
    l["experiment_frozen_commit"]="0"*40
    out=evaluate_release(i,p,l)
    assert "frozen_strategy" in out["blocked_gates"]
    assert out["gates"][0]["owner"]=="AUTOMATED_CONSISTENCY_CHECK"


def test_qa_preview_is_machine_diagnostic_not_review_certificate():
    i,p,l=facts()
    i["sources"][0]["source_approval"]="APPROVED"
    out=evaluate_release(i,p,l)
    assert "source_membership" in out["blocked_gates"]


def test_readiness_api_authenticated_and_all_gates_visible(monkeypatch):
    import base64
    from fastapi.testclient import TestClient
    from gem_data.gem_standalone import app
    from gem_data import gem_portfolio_routes
    monkeypatch.setenv("GEM_DASHBOARD_USERNAME","gemowner")
    monkeypatch.setenv("GEM_DASHBOARD_PASSWORD","test-password-at-least-twenty-characters")
    report=evaluate_release(*facts(),at=datetime(2026,10,14,14,tzinfo=timezone.utc))
    monkeypatch.setattr(gem_portfolio_routes,"read_latest_release_diagnostic",lambda:report)
    headers={"Authorization":"Basic "+base64.b64encode(
        b"gemowner:test-password-at-least-twenty-characters").decode()}
    with TestClient(app) as client:
        assert client.get("/api/gem-portfolio/autonomous-readiness").status_code==401
        response=client.get("/api/gem-portfolio/autonomous-readiness",headers=headers)
        assert response.status_code==200
        assert response.headers["cache-control"]=="no-store"
        assert response.json()["production_trading_ready"] is False
        assert "source_prices" in response.json()["blocked_gates"]
        page=client.get("/gem-portfolio",headers=headers)
        assert page.status_code==200
        assert 'id="autonomous-production-readiness"' in page.text
        assert 'id="release-gates"' in page.text
        assert "renderAutonomousReadiness" in page.text


def test_readiness_api_unavailable_holds(monkeypatch):
    import base64
    from fastapi.testclient import TestClient
    from gem_data.gem_standalone import app
    from gem_data import gem_portfolio_routes
    monkeypatch.setenv("GEM_DASHBOARD_USERNAME","gemowner")
    monkeypatch.setenv("GEM_DASHBOARD_PASSWORD","test-password-at-least-twenty-characters")
    monkeypatch.setattr(gem_portfolio_routes,"read_latest_release_diagnostic",
                        lambda:(_ for _ in ()).throw(ReadinessHold("unavailable")))
    headers={"Authorization":"Basic "+base64.b64encode(
        b"gemowner:test-password-at-least-twenty-characters").decode()}
    with TestClient(app) as client:
        response=client.get("/api/gem-portfolio/autonomous-readiness",headers=headers)
        assert response.status_code==503
        assert response.json()["production_trading_ready"] is False
        assert response.json()["gates"]==[]
