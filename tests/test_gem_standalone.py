"""Safety checks for the isolated Render GEM-only entry point."""
import base64

from fastapi.testclient import TestClient

from gem_data.gem_standalone import app


def auth(name="gemowner", password="test-password-at-least-twenty-characters"):
    token = base64.b64encode(f"{name}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def test_liveness_does_not_trigger_any_paper_startup(monkeypatch):
    monkeypatch.delenv("GEM_DASHBOARD_USERNAME", raising=False)
    monkeypatch.delenv("GEM_DASHBOARD_PASSWORD", raising=False)
    with TestClient(app) as client:
        result = client.get("/health")
        assert result.status_code == 200
        assert result.json()["mode"] == "READ_ONLY"
        assert result.json()["trading_enabled"] is False
        assert result.json()["auth_configured"] is False


def test_no_auth_secret_fails_closed(monkeypatch):
    monkeypatch.delenv("GEM_DASHBOARD_USERNAME", raising=False)
    monkeypatch.delenv("GEM_DASHBOARD_PASSWORD", raising=False)
    with TestClient(app) as client:
        assert client.get("/gem-trial").status_code == 503
        assert client.get("/api/gem-trial/status").status_code == 503


def test_wrong_password_blocks_both_html_and_api(monkeypatch):
    monkeypatch.setenv("GEM_DASHBOARD_USERNAME", "gemowner")
    monkeypatch.setenv("GEM_DASHBOARD_PASSWORD", "test-password-at-least-twenty-characters")
    with TestClient(app) as client:
        html = client.get("/gem-trial", headers=auth(password="incorrect-password-at-least-twenty"))
        api = client.get("/api/gem-trial/status", headers=auth(password="incorrect-password-at-least-twenty"))
        assert html.status_code == 401
        assert api.status_code == 401
        assert html.headers.get("WWW-Authenticate", "").startswith("Basic")


def test_gem_only_routes_and_disabled_signals(monkeypatch):
    monkeypatch.setenv("GEM_DASHBOARD_USERNAME", "gemowner")
    monkeypatch.setenv("GEM_DASHBOARD_PASSWORD", "test-password-at-least-twenty-characters")
    monkeypatch.delenv("GEM_READONLY_DATABASE_URL", raising=False)
    monkeypatch.delenv("GEM_STATUS_SNAPSHOT_PATH", raising=False)
    with TestClient(app) as client:
        assert client.get("/gem-trial", headers=auth()).status_code == 200
        response = client.get("/api/gem-trial/status", headers=auth())
        assert response.status_code == 200
        data = response.json()
        assert data["execution"] == "DISABLED"
        assert data["ranking_ready"] is False
        assert data["verified_source_count"] == 0
        assert client.get("/trial", headers=auth()).status_code == 404
        assert client.get("/login", headers=auth()).status_code == 404
        assert client.get("/api/trial/status", headers=auth()).status_code == 404
        assert client.get("/openapi.json", headers=auth()).status_code == 404


def test_password_not_exposed_in_health(monkeypatch):
    monkeypatch.setenv("GEM_DASHBOARD_USERNAME", "gemowner")
    monkeypatch.setenv("GEM_DASHBOARD_PASSWORD", "test-password-at-least-twenty-characters")
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.json()["auth_configured"] is True
        assert "test-password" not in r.text
