"""Read-only GEM dashboard safety checks. Does not open production DB."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dual_momentum import gem_dashboard as gem


def test_empty_projection_shows_no_portfolio(monkeypatch):
    monkeypatch.delenv("GEM_STATUS_SNAPSHOT_PATH", raising=False)
    result = gem.gem_status()
    assert result["portfolio"] is None
    assert result["execution"] == "DISABLED"
    assert result["read_model_connected"] is False
    assert result["starting_capital_planned"] == 10000
    assert all(item["status"] == "UNKNOWN" for item in result["sources"])


def test_stale_and_wrong_release_block(monkeypatch, tmp_path):
    p = tmp_path / "gem-projection.json"
    monkeypatch.setenv("GEM_STATUS_SNAPSHOT_PATH", str(p))
    base = {
        "schema": "gem-dashboard-v1", "frozen_ref": gem.FROZEN_REF,
        "environment": "paper", "observed_at": datetime.now(timezone.utc).isoformat(),
        "ledger": {"reconciled": True, "trusted_head": "a" * 64,
                   "portfolio": {"nav": 12345.0, "return_pct": 23.45}}
    }
    p.write_text(json.dumps({**base, "frozen_ref": "wrong"}), encoding="utf-8")
    assert gem.gem_status()["portfolio"] is None
    p.write_text(json.dumps({**base, "observed_at": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()}), encoding="utf-8")
    assert gem.gem_status()["read_model_connected"] is False


def test_unauthenticated_claim_does_not_enable_execution(monkeypatch, tmp_path):
    p = tmp_path / "shadow.json"
    monkeypatch.setenv("GEM_STATUS_SNAPSHOT_PATH", str(p))
    p.write_text(json.dumps({
        "schema": "gem-dashboard-v1", "frozen_ref": gem.FROZEN_REF,
        "environment": "shadow", "observed_at": datetime.now(timezone.utc).isoformat(),
        "sources": {"sec": {"status": "VERIFIED", "as_of": "2026-10-12"}},
        "qa": "PASS", "user_approved": True, "execute": True,
        "ledger": {"reconciled": True, "trusted_head": "a" * 64,
                   "portfolio": {"nav": 999999.0}}
    }), encoding="utf-8")
    result = gem.gem_status()
    assert result["execution"] == "DISABLED"
    assert result["portfolio"] is None
    assert result["mode"] == "shadow"


def test_malformed_file_blocks_without_side_effect(monkeypatch, tmp_path):
    p = tmp_path / "invalid.json"
    p.write_text("{not-json", encoding="utf-8")
    monkeypatch.setenv("GEM_STATUS_SNAPSHOT_PATH", str(p))
    assert gem.gem_status()["read_model_connected"] is False
    assert p.read_text(encoding="utf-8") == "{not-json"


def test_source_missing_never_becomes_verified(monkeypatch, tmp_path):
    p = tmp_path / "partial.json"
    monkeypatch.setenv("GEM_STATUS_SNAPSHOT_PATH", str(p))
    p.write_text(json.dumps({
        "schema": "gem-dashboard-v1", "frozen_ref": gem.FROZEN_REF,
        "environment": "shadow", "observed_at": datetime.now(timezone.utc).isoformat(),
        "sources": {"prices": {"status": "STALE"}, "calendar": {"status": "INVALID"}},
    }), encoding="utf-8")
    result = gem.gem_status()
    sources = {row["key"]: row["status"] for row in result["sources"]}
    assert sources["prices"] == "STALE"
    assert sources["calendar"] == "UNKNOWN"
    assert sources["sec"] == "UNKNOWN"
    assert result["execution"] == "DISABLED"


def test_neon_reader_connection_failure_blocks_and_hides_ledger(monkeypatch):
    monkeypatch.setenv("GEM_READONLY_DATABASE_URL", "postgresql://localhost:1/missing")
    result = gem.gem_status()
    assert result["read_model_connected"] is False
    assert result["portfolio"] is None
    assert result["execution"] == "DISABLED"
    assert "read failed" in result["projection_error"]


def test_neon_reader_empty_and_independent_of_dm_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://existing-trial/untouched")
    monkeypatch.delenv("GEM_READONLY_DATABASE_URL", raising=False)
    monkeypatch.delenv("GEM_STATUS_SNAPSHOT_PATH", raising=False)
    result = gem.gem_status()
    assert result["read_model_connected"] is False
    assert result["shadow_signals"] is None
    assert result["source_receipts"] is None
