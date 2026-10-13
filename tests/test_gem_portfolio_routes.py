"""GEM portfolio dashboard is authenticated and never connects to broker."""
import base64
from io import BytesIO
from fastapi.testclient import TestClient
from gem_data.gem_standalone import app
from gem_data.gem_positions_import import parse_tabular_positions, PositionImportHold
import pytest


def auth():
    raw=base64.b64encode(b"gemowner:manual-pw-longer-than-twenty-characters").decode()
    return {"Authorization": "Basic "+raw}


def test_read_only_portfolio_requires_auth(monkeypatch):
    monkeypatch.delenv("GEM_DASHBOARD_USERNAME",raising=False)
    monkeypatch.delenv("GEM_DASHBOARD_PASSWORD",raising=False)
    with TestClient(app) as client:
        assert client.get("/gem-portfolio").status_code==503
        assert client.get("/api/gem-portfolio/integrity").status_code==503


def test_portfolio_has_integrity_diagrams_and_manual_controls(monkeypatch):
    monkeypatch.setenv("GEM_DASHBOARD_USERNAME","gemowner")
    monkeypatch.setenv("GEM_DASHBOARD_PASSWORD","manual-pw-longer-than-twenty-characters")
    with TestClient(app) as client:
        page=client.get("/gem-portfolio",headers=auth())
        assert page.status_code==200
        for phrase in ("Data integrity at a glance","Market-data provider coverage",
                       "SEC fundamentals","Import &amp; review","Mark closed (draft)"):
            assert phrase in page.text
        assert "No verified five-stock recommendation" in page.text
        assert client.get("/",follow_redirects=False).headers["location"]=="/gem-portfolio"


def test_csv_positions_import_only_draft(monkeypatch):
    monkeypatch.setenv("GEM_DASHBOARD_USERNAME","gemowner")
    monkeypatch.setenv("GEM_DASHBOARD_PASSWORD","manual-pw-longer-than-twenty-characters")
    with TestClient(app) as client:
        response=client.post("/api/gem-portfolio/import",headers=auth(),
            files={"file":("positions.csv",b"Symbol,Quantity\nAAPL,12\nMSFT,7\n","text/csv")})
        assert response.status_code==200
        out=response.json()
        assert out["holdings"]==[{"ticker":"AAPL","shares":"12"},
                                 {"ticker":"MSFT","shares":"7"}]
        assert out["server_saved"] is False
        assert out["broker_orders_sent"]==0


def test_image_import_fails_closed_without_consent(monkeypatch):
    monkeypatch.setenv("GEM_DASHBOARD_USERNAME","gemowner")
    monkeypatch.setenv("GEM_DASHBOARD_PASSWORD","manual-pw-longer-than-twenty-characters")
    with TestClient(app) as client:
        response=client.post("/api/gem-portfolio/import",headers=auth(),
            files={"file":("screen.png",b"fake-image","image/png")})
        assert response.status_code==422
        assert "consent" in response.json()["detail"].lower()


def test_duplicate_tickers_not_silently_merged():
    with pytest.raises(PositionImportHold, match="Duplicate"):
        parse_tabular_positions("holdings.csv",b"ticker,shares\nAAPL,4\nAAPL,6\n")


def test_invalid_quantity_rejected():
    with pytest.raises(PositionImportHold):
        parse_tabular_positions("holdings.csv",b"ticker,shares\nAAPL,-5\n")
