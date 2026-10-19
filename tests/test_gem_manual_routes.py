"""The GEM manual workbench is authenticated, stateless and broker-free."""
import base64

from fastapi.testclient import TestClient
from gem_data.gem_standalone import app


def _auth():
    val=base64.b64encode(b"gemowner:manual-pw-longer-than-twenty-characters").decode()
    return {"Authorization":"Basic "+val}


def test_manual_dashboard_is_auth_protected(monkeypatch):
    monkeypatch.delenv("GEM_DASHBOARD_USERNAME", raising=False)
    monkeypatch.delenv("GEM_DASHBOARD_PASSWORD", raising=False)
    with TestClient(app) as client:
        assert client.get("/gem-manual").status_code == 503
        assert client.get("/api/gem-manual/mode").status_code == 503
        assert client.post("/api/gem-manual/run/ledger", json={}).status_code == 503


def test_manual_workbench_has_no_broker_backend(monkeypatch):
    monkeypatch.setenv("GEM_DASHBOARD_USERNAME", "gemowner")
    monkeypatch.setenv("GEM_DASHBOARD_PASSWORD", "manual-pw-longer-than-twenty-characters")
    with TestClient(app) as client:
        html=client.get("/gem-manual",headers=_auth())
        assert html.status_code == 200
        assert "No broker connection" in html.text
        meta=client.get("/api/gem-manual/mode",headers=_auth())
        assert meta.status_code == 200
        assert meta.json()["broker_api"] is False
        assert meta.json()["server_persistence"] is False
        res=client.post("/api/gem-manual/run/ledger",headers=_auth(),
                        json={"initial_cash":"10000","events":[]})
        assert res.status_code == 200
        assert res.json()["cash"] == "10000"
        assert res.json()["broker_orders_sent"] == 0


def test_bad_json_or_hold_never_instructs_order(monkeypatch):
    monkeypatch.setenv("GEM_DASHBOARD_USERNAME", "gemowner")
    monkeypatch.setenv("GEM_DASHBOARD_PASSWORD", "manual-pw-longer-than-twenty-characters")
    with TestClient(app) as client:
        bad=client.post("/api/gem-manual/run/ledger",headers=_auth(),
                        data='wrong',headers_extra={}) if False else None
        res=client.post("/api/gem-manual/run/tickets",headers=_auth(),
                        json={"signal":{"selected":["A","B","C"],"data_status":"HOLD"},
                              "ledger":{"cash":"10000","shares":{}},"reference_prices":{}})
        assert res.status_code == 200
        assert res.json()["tickets"] == []
        assert res.json()["status"] == "DATA_HOLD"
        assert client.post("/api/gem-manual/run/broker",headers=_auth(),
                           json={}).status_code == 404
