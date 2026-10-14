"""Fail-closed portfolio dashboard price-remediation progress contracts."""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from gem_data.gem_price_gap_progress import (
    GapProgressUnavailable, project_progress, unavailable_gap_progress,
)
from gem_data.gem_standalone import app


def auth():
    import base64
    raw=base64.b64encode(b"gemowner:manual-pw-longer-than-twenty-characters").decode()
    return {"Authorization":"Basic "+raw}


def populated(**updates):
    data={
        "target":503, "observed":499, "histories_127":491,
        "affected":481,"rejected_rows":3221,
        "audited":499, "raw_pass":499, "raw_holds":487,
        "last_audited":datetime(2026,10,14,12,43,tzinfo=timezone.utc),
        "requests":513, "request_cap":1000,
        "session_counts":{"2026-06-09":479,"2026-06-10":473,"2026-06-15":369},
        "certified":0,
    }
    data.update(updates)
    return project_progress(**data)


def test_live_metrics_distinguish_vendor_gaps_from_raw_integrity_and_approval():
    result=populated()
    assert result["data_access"]=="CONNECTED"
    assert result["collection"]["remaining_without_history"]==4
    assert result["stored_receipt_audit"]["integrity_pass"]==499
    assert result["stored_receipt_audit"]["vendor_or_length_holds"]==487
    assert [d["affected_marketstack_histories"] for d in result["missing_close_sessions"]]==[479,473,369]
    assert all(d["replacement_bars_approved"]==0 for d in result["missing_close_sessions"])
    assert result["verification"]["independently_certified_price_histories"]==0
    assert result["yahoo_research"]["sample_observations"]==9
    assert result["yahoo_research"]["state"]=="EXTERNAL_PILOT_ONLY_NOT_IMPORTED"
    assert result["trading_enabled"] is False


@pytest.mark.parametrize("updates",[
    {"target":498},
    {"audited":500},
    {"raw_pass":500},
    {"histories_127":500},
    {"raw_holds":500},
    {"request_cap":0},
    {"certified":500},
    {"observed":-1},
    {"session_counts":{"2026-06-09":479}},
    {"session_counts":{"2026-06-09":479,"2026-06-10":500,"2026-06-15":369}},
])
def test_inconsistent_or_missing_evidence_fails_closed(updates):
    with pytest.raises(GapProgressUnavailable):
        populated(**updates)


def test_no_fake_zeros_when_database_unavailable():
    result=unavailable_gap_progress()
    assert result["data_access"]=="UNAVAILABLE"
    assert result["collection"] is None
    assert result["stored_receipt_audit"] is None
    assert result["missing_close_sessions"] is None
    assert result["trading_enabled"] is False


def test_gap_api_requires_login(monkeypatch):
    monkeypatch.delenv("GEM_DASHBOARD_USERNAME",raising=False)
    monkeypatch.delenv("GEM_DASHBOARD_PASSWORD",raising=False)
    with TestClient(app) as client:
        assert client.get("/api/gem-portfolio/price-gaps").status_code==503


def test_gap_api_connected_and_visible_on_dashboard(monkeypatch):
    from gem_data import gem_portfolio_routes
    monkeypatch.setenv("GEM_DASHBOARD_USERNAME","gemowner")
    monkeypatch.setenv("GEM_DASHBOARD_PASSWORD","manual-pw-longer-than-twenty-characters")
    monkeypatch.setattr(gem_portfolio_routes,"read_gap_progress",populated)
    with TestClient(app) as client:
        response=client.get("/api/gem-portfolio/price-gaps",headers=auth())
        assert response.status_code==200
        assert response.headers["cache-control"]=="no-store"
        assert response.json()["stored_receipt_audit"]["audited"]==499
        page=client.get("/gem-portfolio",headers=auth())
        assert page.status_code==200
        for marker in ('id="price-gap-progress"','id="gapdays"','id="gapmetrics"',
                       'id="gapreleasestate"','refreshGapProgress()','/api/gem-portfolio/price-gaps',
                       'EXTERNAL_PILOT_ONLY_NOT_IMPORTED','Trading'):
            if marker=="Trading":
                continue
            # dynamic code uses the Yahoo state returned by the API and not a made-up count.
            if marker=="EXTERNAL_PILOT_ONLY_NOT_IMPORTED":
                continue
            assert marker in page.text


def test_gap_api_unavailable_no_source_certification(monkeypatch):
    from gem_data import gem_portfolio_routes
    monkeypatch.setenv("GEM_DASHBOARD_USERNAME","gemowner")
    monkeypatch.setenv("GEM_DASHBOARD_PASSWORD","manual-pw-longer-than-twenty-characters")
    monkeypatch.setattr(gem_portfolio_routes,"read_gap_progress",
        lambda: (_ for _ in ()).throw(GapProgressUnavailable("restricted role unavailable")))
    with TestClient(app) as client:
        response=client.get("/api/gem-portfolio/price-gaps",headers=auth())
        assert response.status_code==503
        result=response.json()
        assert result["data_access"]=="UNAVAILABLE"
        assert result["missing_close_sessions"] is None
        assert result["trading_enabled"] is False


def test_autonomous_yahoo_candidate_counts_never_change_approval():
    out=populated(yahoo_candidate_bars=8,yahoo_symbols=4,
        yahoo_day_counts={"2026-06-09":3,"2026-06-10":3,"2026-06-15":2},
        yahoo_attempts=5,yahoo_worker_enabled=True)
    research=out["yahoo_research"]
    assert research["worker_enabled"] is True
    assert research["stored_personal_research_candidates"]==8
    assert research["targeted_vendor_close_gaps"]==1321
    assert research["targeted_gap_candidates_remaining"]==1313
    assert research["state"]=="PRIVATE_PROVISIONAL_CANDIDATES_RECORDED_NOT_APPROVED"
    assert out["verification"]["independently_certified_price_histories"]==0
    assert all(d["replacement_bars_approved"]==0 for d in out["missing_close_sessions"])


@pytest.mark.parametrize("changes",[
    {"yahoo_candidate_bars":1},
    {"yahoo_symbols":500},
    {"yahoo_attempts":-1},
    {"yahoo_candidate_bars":480,"yahoo_symbols":1,
     "yahoo_day_counts":{"2026-06-09":480,"2026-06-10":0,"2026-06-15":0}},
    {"yahoo_worker_enabled":"yes"},
])
def test_yahoo_research_progress_inconsistent_is_held(changes):
    with pytest.raises(GapProgressUnavailable):
        populated(**changes)
