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
    assert all(item["status"] != "VERIFIED" for item in result["sources"])
    assert all(item["trade_eligible"] is False for item in result["sources"])


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
    assert sources["sec"] == "PARTIAL"  # Dated archived evidence, not a live QA certificate
    assert result["execution"] == "DISABLED"


def test_october_reference_exact_five_and_daily_reconciliation():
    ref = gem.oct1_retrospective_reference()
    assert ref is not None
    assert ref["classification"] == "BACKFILLED_UNCERTIFIED"
    assert ref["as_of"] == "2026-10-09"
    assert ref["fills_recorded"] == 0
    assert len(ref["daily_nav"]) == 7
    assert {o["ticker"]: o["quantity"] for o in ref["orders"]} == {
        "P": 15, "MPC": 5, "PLTR": 10, "HPE": 30, "VLO": 5}
    assert abs(ref["nav_usd"] - 11284.998022) < .01
    assert abs(ref["spy_nav_usd"] - 10164.856926) < .01
    assert abs(ref["cash_usd"] - 229.447943) < .01
    assert ref["return_pct"] > ref["spy_return_pct"]


def test_october_reference_tampered_nav_blocked(monkeypatch, tmp_path):
    original = Path(gem.__file__).with_name("gem_oct1_reference.json")
    fixture = json.loads(original.read_text())
    fixture["daily_nav"][-1]["gem_nav"] += 100
    invalid = tmp_path / "tampered-reference.json"
    invalid.write_text(json.dumps(fixture))
    from pathlib import Path as FilePath
    original_with_name = FilePath.with_name
    monkeypatch.setattr(FilePath, "with_name",
                        lambda self, name: invalid if name == "gem_oct1_reference.json" else original_with_name(self, name))
    assert gem.oct1_retrospective_reference() is None


def test_october_reference_never_funds_forward_paper_account(monkeypatch):
    monkeypatch.delenv("GEM_STATUS_SNAPSHOT_PATH", raising=False)
    monkeypatch.delenv("GEM_READONLY_DATABASE_URL", raising=False)
    state = gem.gem_status()
    assert state["oct1_backfill"] is not None
    assert state["portfolio"] is None
    assert state["execution"] == "DISABLED"
    assert state["read_model_connected"] is False


def test_neon_reader_failure_is_fail_closed_without_dm_database(monkeypatch):
    monkeypatch.setenv("GEM_READONLY_DATABASE_URL", "postgresql://invalid-gem-reader")
    monkeypatch.setenv("DATABASE_URL", "postgresql://existing-trial-do-not-touch")
    def deny(*args, **kwargs):
        raise gem.psycopg.OperationalError("restricted reader unavailable")
    monkeypatch.setattr(gem.psycopg, "connect", deny)
    state = gem.gem_status()
    assert state["read_model_connected"] is False
    assert state["gem_db"] is None
    assert state["portfolio"] is None
    assert state["execution"] == "DISABLED"
    assert state["oct1_backfill"]["fills_recorded"] == 0


def test_neon_reader_verifies_both_gem_accounts_without_writes(monkeypatch):
    monkeypatch.setenv("GEM_READONLY_DATABASE_URL", "postgresql://gem-only-reader")
    calls = []
    class Cursor:
        count = 0
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, sql, params):
            calls.append((sql, params))
            assert sql.strip().upper().startswith("SELECT")
            assert "dual_momentum" not in sql
            self.count += 1
        def fetchall(self):
            if self.count == 1:
                return [
                    ("gem-v1-forward-2026-10", gem.FROZEN_REF, "SHADOW", False, 0, 0),
                    ("gem-v1-oct1-backfill-2026", gem.FROZEN_REF, "SHADOW", False, 0, 0),
                ]
            return []
        def fetchone(self): return (7,)
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def cursor(self): return Cursor()
    monkeypatch.setattr(gem.psycopg, "connect", lambda *a, **k: Connection())
    state = gem.gem_status()
    assert state["read_model_connected"] is True
    assert state["gem_db"]["backfill_observations"] == 7
    assert state["gem_db"]["forward_signals"] == 0
    assert state["execution"] == "DISABLED"
    assert len(calls) == 3
