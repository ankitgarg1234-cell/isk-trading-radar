import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.db import PaperAccount, ScoreBandExperiment, SessionLocal
from app.recovery import ensure_recovery_seed
from app.score_band_experiment import VERSION, ensure_single_account, new_state
import app.score_band_capture as capture


def _seed_payload():
    return {
        "profile": "MEDIUM",
        "asof": "2026-10-06T16:03:57+00:00",
        "started_at": "2026-10-06T13:30:00+00:00",
        "starting_cash": 10000.0,
        "cash": 0.02,
        "equity": 10004.63,
        "benchmark_return_pct": 0.36,
        "max_drawdown_pct": -0.32,
        "positions": [
            {"symbol": "GOOGL", "shares": 4, "avg_cost": 345.16, "mark": 347.84,
             "entry_rank": 77.3, "reason": "pullback"},
            {"symbol": "FTK", "shares": 50, "avg_cost": 29.28, "mark": 29.0576,
             "entry_rank": 73.2, "reason": "pullback"},
        ],
    }


def test_recovery_seed_is_one_time_and_preserves_snapshot(monkeypatch):
    monkeypatch.setenv("RADAR_RECOVERY_SEED_JSON", json.dumps(_seed_payload()))

    assert ensure_recovery_seed() is True
    assert ensure_recovery_seed() is False

    with SessionLocal() as db:
        rows = db.query(ScoreBandExperiment).filter_by(version=VERSION).all()
        assert len(rows) == 1
        state = ensure_single_account(json.loads(rows[0].state_json))
        book = state["variants"]["complete_strategy"]
        assert state["recovery"]["active"] is True
        assert book["cash"] == pytest.approx(0.02)
        assert set(book["positions"]) == {"GOOGL", "FTK"}
        assert book["positions"]["GOOGL"]["shares"] == 4
        assert book["positions"]["GOOGL"]["recovery_frozen"] is True
        assert book["marks"]["FTK"] == pytest.approx(29.0576)
        assert book["pending"] == {}
        account = db.query(PaperAccount).filter_by(account="Optimizer Paper").one()
        assert account.starting_cash == pytest.approx(10000.0)
        assert account.cash == pytest.approx(0.02)


def test_recovery_mark_only_updates_prices_without_orders_or_trades():
    state = new_state("MEDIUM")
    book = state["variants"]["complete_strategy"]
    book["cash"] = 500.0
    book["positions"]["TEST"] = {
        "shares": 10,
        "avg_cost": 100.0,
        "entry_fee_per_share": 0.1,
        "entry_stop": 0.01,
        "entry_target": 1_000_000_000.0,
        "entry_stretch_target": 1_000_000_000.0,
        "entry_horizon_days": 3650,
        "stop": 0.01,
        "harvested": False,
        "peak": 100.0,
        "opened_at": "2026-10-06T13:30:00+00:00",
        "profit_steps": [],
        "recovery_frozen": True,
    }
    book["marks"]["TEST"] = 100.0
    book["pending"] = {}
    book["trades"] = [{"symbol": "TEST", "side": "BUY", "shares": 10, "price": 100.0}]
    before_trades = list(book["trades"])

    result = capture._recovery_mark_only(
        state,
        [{"symbol": "TEST", "price": 105.0, "asof": "2026-10-07T13:30:00+00:00"},
         {"symbol": "NEW", "price": 50.0, "asof": "2026-10-07T13:30:00+00:00"}],
        datetime(2026, 10, 7, 13, 30, tzinfo=timezone.utc),
        True,
    )

    assert result == {"status": "recovery_readonly", "observations": 1, "fills": 0}
    assert book["marks"]["TEST"] == pytest.approx(105.0)
    assert "NEW" not in book["marks"]
    assert book["pending"] == {}
    assert book["trades"] == before_trades
    assert book["curve"][-1]["equity"] == pytest.approx(1550.0)


def test_run_cycle_routes_to_mark_only_when_recovery_enabled(monkeypatch):
    monkeypatch.setenv("RADAR_RECOVERY_SEED_JSON", json.dumps(_seed_payload()))
    ensure_recovery_seed()

    monkeypatch.setattr(
        capture,
        "settings",
        SimpleNamespace(
            score_band_trial_armed_at="",
            recovery_readonly_paper=True,
        ),
    )
    monkeypatch.setattr(capture, "fresh_benchmark", lambda now: (None, None))

    full = {
        "symbol": "GOOGL",
        "price": 350.0,
        "currency": "USD",
        "asof": "2026-10-07T13:31:00+00:00",
        "data_sources": {"price": {"quote_asof": "2026-10-07T13:31:00+00:00"}},
        "deterministic_score": 99,
        "analyst_score": 99,
        "risk_reward": 5.0,
        "levels": {"buy_low": 300, "buy_high": 400, "stop": 300},
        "target_plan": {"base_target": 500},
        "technicals": {},
        "news": {},
    }
    result = capture.run_experiment_cycle(
        [full], True, datetime(2026, 10, 7, 13, 31, tzinfo=timezone.utc)
    )
    assert result["status"] == "recovery_readonly"
    assert result["fills"] == 0

    with SessionLocal() as db:
        row = db.query(ScoreBandExperiment).filter_by(version=VERSION).one()
        state = ensure_single_account(json.loads(row.state_json))
        book = state["variants"]["complete_strategy"]
        assert set(book["positions"]) == {"GOOGL", "FTK"}
        assert book["pending"] == {}
        assert book["marks"]["GOOGL"] == pytest.approx(350.0)
