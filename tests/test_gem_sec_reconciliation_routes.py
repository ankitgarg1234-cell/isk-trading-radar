"""Authenticated SEC reconciliation is machine evidence, never trade approval."""
from fastapi.testclient import TestClient
from gem_data.gem_standalone import app
from gem_data import gem_sec_reconciliation_routes as routes


def sample():
    return {
        "schema":"gem-sec-reconciliation-coverage-v1",
        "as_of":"2026-10-12",
        "issuers_machine_assessed":500,
        "machine_candidate_complete_not_certified":316,
        "machine_unresolved":184,
        "original_review_reconciled":184,
        "original_review_pending":0,
        "original_six_fact_candidates_recovered_not_certified":2,
        "preliminary_revenue_growth_gate_fail_not_certified":1,
        "combined_machine_or_original_candidates_not_certified":318,
        "still_no_six_fact_set":182,
        "independently_certified":0,
        "investment_release":"DATA_HOLD",
        "resolution_counts":{"SIX_FACTS_RECOVERED_CONTEXT_QA_REQUIRED":2},
        "items":[{"cik":"0000721371","machine_status":"UNKNOWN",
                  "resolution":"SIX_FACTS_RECOVERED_CONTEXT_QA_REQUIRED",
                  "candidate_metrics":{"revenue_yoy_pct":11.045,
                                       "operating_margin_delta_pp":-0.49},
                  "original_filing_detail":"/gem-sec-filing/0000721371"}],
    }


def test_reconciliation_index_requires_auth_and_is_not_certification(monkeypatch):
    monkeypatch.setenv("GEM_DASHBOARD_USERNAME","gemowner")
    monkeypatch.setenv("GEM_DASHBOARD_PASSWORD","test-password-at-least-twenty-characters")
    monkeypatch.setattr(routes,"sec_reconciliation_snapshot",sample)
    with TestClient(app) as client:
        assert client.get("/gem-sec-reconciliation").status_code==401
        assert client.get("/api/gem-portfolio/sec-reconciliation").status_code==401
        auth=("gemowner","test-password-at-least-twenty-characters")
        page=client.get("/gem-sec-reconciliation",auth=auth)
        assert page.status_code==200
        assert "184" in page.text
        assert "0000721371" in page.text
        assert "DATA HOLD" in page.text
        report=client.get("/api/gem-portfolio/sec-reconciliation",auth=auth)
        assert report.status_code==200
        assert report.json()["independently_certified"]==0
        assert report.json()["combined_machine_or_original_candidates_not_certified"]==318
        csv=client.get("/gem-sec-reconciliation.csv",auth=auth)
        assert csv.status_code==200
        assert "0000721371" in csv.text
        assert "NO" in csv.text
