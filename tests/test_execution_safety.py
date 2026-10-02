"""Executable quantities, quote freshness and fixed profit tranches.

The provider is deliberately offline. A fresh executable quote is an explicit
fixture input, so these checks never depend on Yahoo or a production account.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, inspect

from app.analysis_engine import SCORING_VERSION
from app.db import Base, PaperAccount, PaperPosition, PaperTrade, PortfolioPreference, RadarCandidate, SessionLocal
from app.paper_engine import _candidate_payloads, run_paper_cycle
from app.portfolio_engine import candidate_rank_score, suggested_position_size


def candidate(symbol="SAFE", *, price=100, rr=2.4):
    return {
        "symbol": symbol, "scoring_version": SCORING_VERSION,
        "asof": datetime.now(timezone.utc).isoformat(),
        "price_asof": datetime.now(timezone.utc).isoformat(), "price": price,
        "deterministic_score": 90, "ai_score": 90, "expected_yield_pct": 25,
        "risk_reward": rr, "decision_confidence": "high", "fundamental_confidence": "high",
        "data_quality_pct": 100, "lane": "CORE_QUALITY", "lane_label": "Core Quality Lane",
        "lane_qualified": True, "core_quality_qualified": True, "explosive_qualified": False,
        "entry_zone_status": "PRIMARY_BUY", "action": "BUY NOW",
        "negative_news_override": None, "promotion_risk": {"hard_reject": False},
        "thesis_assessment": {"invalidated": False},
        "levels": {"buy_low": price * .97, "buy_high": price * 1.02,
                   "better_low": price * .90, "better_high": price * .93,
                   "stop": 88, "target": 125, "breakout": 140, "do_not_chase": 150},
        "target_plan": {"base_target": 125, "stretch_target": 145},
        "holding_horizon": {"max_days": 90},
        "technicals": {"atr": 2, "relative_volume": 1.2, "change20_pct": 5,
                       "ema20": price * .99, "rsi": 55, "avg_dollar_volume_20": 100_000_000},
        "news": {"label": "Neutral", "material_events": 0, "high_negative_events": 0},
        "fundamentals": {"sector": "Technology", "marketCap": 10_000_000_000},
        "breakdown": {"Fundamentals": 20, "Catalyst": 15, "Valuation": 10,
                      "Momentum": 15, "Risk/Reward": 9, "Sector": 10},
    }


def save(db, payload, *, stored_at=None, rank=None):
    row = RadarCandidate(
        symbol=payload["symbol"], action=payload["action"], price=payload["price"],
        score=payload["deterministic_score"], ai_score=payload["ai_score"],
        portfolio_rank_score=rank if rank is not None else candidate_rank_score(payload)["score"],
        lane=payload.get("lane"), lane_qualified=payload["lane_qualified"],
        current_json=json.dumps(payload),
    )
    if stored_at is not None:
        row.updated_at = stored_at
    db.add(row)
    return row


def account(db, cash=10000):
    db.add(PaperAccount(account="Optimizer Paper", cash=cash, starting_cash=10000,
                        benchmark_symbol="^SP500TR", benchmark_start_price=500,
                        benchmark_last_price=500, last_rebalance_at=datetime.now(timezone.utc)))
    db.add(PortfolioPreference(account="Main", risk_profile="MEDIUM"))


class OfflineQuotes:
    def __init__(self, quote=None):
        self.quote = quote

    def chart(self, *args, **kwargs):
        return {"meta": {"regularMarketPrice": 500}}

    def quick_scan(self, symbol):
        if self.quote is None:
            raise RuntimeError("No offline executable quote supplied")
        return dict(self.quote, symbol=symbol)


def test_paper_execution_cannot_enlarge_risk_limited_sizing():
    payload = candidate()
    sizing = suggested_position_size(payload, cash=10000, reserve_cash=0,
                                     portfolio_value=10000, profile="MEDIUM")
    assert sizing["shares"] == 6
    with SessionLocal() as db:
        save(db, payload)
        account(db)
        db.commit()
    result = run_paper_cycle(OfflineQuotes(), entry_event=True)
    with SessionLocal() as db:
        position = db.query(PaperPosition).one()
        trade = db.query(PaperTrade).one()
        assert position.shares == trade.shares == sizing["shares"]
        assert position.shares * (payload["price"] - payload["levels"]["stop"]) <= 75
        assert db.query(PaperAccount).one().cash == pytest.approx(9399.4)
        assert result["executed_orders"][0]["shares"] == 6


def test_fees_reduce_quantity_instead_of_overdrawing_cash():
    with SessionLocal() as db:
        save(db, candidate())
        account(db, cash=600)
        # Keep total equity at $10K so this is a cash/fee ceiling test rather
        # than a deliberate drawdown shrinking the stop-risk budget.
        db.add(PaperPosition(account="Optimizer Paper", symbol="OTHER", shares=94,
                             avg_cost=100, reason="Core Quality Lane"))
        db.commit()
    run_paper_cycle(OfflineQuotes(), entry_event=True)
    with SessionLocal() as db:
        assert db.query(PaperPosition).filter(PaperPosition.symbol == "SAFE").one().shares == 5
        assert db.query(PaperAccount).one().cash == pytest.approx(99.5)


def test_drawdown_reduces_the_risk_budget_with_current_equity():
    with SessionLocal() as db:
        save(db, candidate())
        account(db, cash=8000)
        db.commit()
    run_paper_cycle(OfflineQuotes(), entry_event=True)
    with SessionLocal() as db:
        position = db.query(PaperPosition).one()
        assert position.shares == 5
        assert position.shares * 12 == 8000 * .0075


def test_refreshed_owned_quote_marks_current_equity_before_add_sizing():
    payload = candidate()
    payload["price_asof"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    with SessionLocal() as db:
        save(db, payload)
        account(db, cash=9400)
        db.add(PaperPosition(account="Optimizer Paper", symbol="SAFE", shares=6, avg_cost=100,
                             original_shares=6, profit_taken_shares=0, profit_taken_stages="[]",
                             entry_target=125, entry_stretch_target=145, entry_stop=88,
                             entry_horizon_days=90, entry_plan_version=SCORING_VERSION,
                             reason="Core Quality Lane"))
        db.commit()
    quote_price = 92.99
    equity_at_quote = 9400 + 6 * quote_price
    result = run_paper_cycle(OfflineQuotes({"price": quote_price, "price_asof": datetime.now(timezone.utc).isoformat()}), entry_event=True)
    assert result["executed_orders"][0]["shares"] == 8
    with SessionLocal() as db:
        shares = db.query(PaperPosition).one().shares
        assert shares * (quote_price - 88) <= equity_at_quote * .0075


def test_top20_is_loaded_after_full_risk_reward_eligibility():
    with SessionLocal() as db:
        for i in range(19):
            save(db, candidate(f"LOWRR{i:02}", rr=1.4), rank=100 - i)
        save(db, candidate("ELIGIBLE_A"), rank=80)
        save(db, candidate("ELIGIBLE_B"), rank=79)
        db.commit()
        loaded = _candidate_payloads(db, ranked_limit=20)
        assert set(loaded) == {"ELIGIBLE_A", "ELIGIBLE_B"}


@pytest.mark.parametrize("invalid", ["version", "analysis_age", "quote_age", "missing_source_timestamp"])
def test_saved_old_or_unverifiable_decisions_do_not_create_orders(invalid):
    payload = candidate()
    if invalid == "version":
        payload["scoring_version"] = "old-target-engine"
    elif invalid == "analysis_age":
        payload["asof"] = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    elif invalid == "quote_age":
        payload["price_asof"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    else:
        payload["price_asof"] = None
    with SessionLocal() as db:
        save(db, payload)  # a new enrichment/database write cannot refresh the quote
        account(db)
        db.commit()
    result = run_paper_cycle(OfflineQuotes(), entry_event=True)
    assert result["executed_orders"] == []
    with SessionLocal() as db:
        assert db.query(PaperTrade).count() == 0


def test_refreshed_price_rechecks_risk_reward_before_entry():
    payload = candidate()
    payload["price_asof"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    with SessionLocal() as db:
        save(db, payload)
        account(db)
        db.commit()
    result = run_paper_cycle(OfflineQuotes({"price": 108, "price_asof": datetime.now(timezone.utc).isoformat()}), entry_event=True)
    assert result["executed_orders"] == []
    assert "executable-price R/R" in result["blocked_orders"][0]["reason"]


@pytest.mark.parametrize("bad_price", ["unavailable", float("nan"), float("inf")])
def test_invalid_refreshed_prices_block_orders_without_aborting_the_cycle(bad_price):
    payload = candidate()
    payload["price_asof"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    with SessionLocal() as db:
        save(db, payload)
        account(db)
        db.commit()
    result = run_paper_cycle(OfflineQuotes({"price": bad_price, "price_asof": datetime.now(timezone.utc).isoformat()}), entry_event=True)
    assert result["status"] == "ok"
    assert result["executed_orders"] == []
    assert result["blocked_orders"]


def held_payload(price):
    payload = candidate("HARVEST", price=price, rr=3.0)
    payload["levels"]["stop"] = 110
    payload["levels"]["target"] = 180
    payload["target_plan"] = {"base_target": 180, "stretch_target": 200}
    return payload


def open_harvest_position(db, *, shares=8, price=121):
    save(db, held_payload(price))
    account(db, cash=2000)
    db.add(PaperPosition(account="Optimizer Paper", symbol="HARVEST", shares=shares, avg_cost=100,
                         original_shares=shares, profit_taken_shares=0, profit_taken_stages="[]",
                         entry_target=120, entry_stretch_target=135, entry_stop=90,
                         entry_horizon_days=90, entry_plan_version=SCORING_VERSION,
                         reason="Core Quality Lane", opened_at=datetime.now(timezone.utc)))


def test_base_and_stretch_are_fixed_once_only_tranches_without_rebuy_churn():
    with SessionLocal() as db:
        open_harvest_position(db)
        db.commit()
    for _ in range(7):
        run_paper_cycle(OfflineQuotes(), entry_event=True)
    with SessionLocal() as db:
        position = db.query(PaperPosition).one()
        assert position.shares == 6
        assert position.profit_taken_shares == 2
        assert json.loads(position.profit_taken_stages) == ["BASE"]
        assert db.query(PaperTrade).count() == 1
        row = db.query(RadarCandidate).one()
        row.current_json = json.dumps(held_payload(136))
        row.price = 136
        row.updated_at = datetime.now(timezone.utc)
        db.commit()
    for _ in range(4):
        run_paper_cycle(OfflineQuotes(), entry_event=True)
    with SessionLocal() as db:
        position = db.query(PaperPosition).one()
        assert position.shares == 4
        assert position.profit_taken_shares == 4
        assert json.loads(position.profit_taken_stages) == ["BASE", "STRETCH"]
        assert [trade.shares for trade in db.query(PaperTrade).order_by(PaperTrade.id)] == [2, 2]


def test_jump_to_stretch_harvests_cumulative_half_once():
    with SessionLocal() as db:
        open_harvest_position(db, price=136)
        db.commit()
    for _ in range(3):
        run_paper_cycle(OfflineQuotes(), entry_event=True)
    with SessionLocal() as db:
        position = db.query(PaperPosition).one()
        assert position.shares == 4
        assert position.profit_taken_shares == 4
        assert json.loads(position.profit_taken_stages) == ["BASE", "STRETCH"]
        assert db.query(PaperTrade).one().shares == 4


def test_whole_share_harvesting_preserves_one_share_runner():
    with SessionLocal() as db:
        open_harvest_position(db, shares=2, price=136)
        db.commit()
    for _ in range(4):
        run_paper_cycle(OfflineQuotes(), entry_event=True)
    with SessionLocal() as db:
        assert db.query(PaperPosition).one().shares == 1
        assert db.query(PaperTrade).one().shares == 1


def test_technical_lane_change_does_not_liquidate_thesis_intact_core():
    payload = candidate("CORE")
    payload.update(lane=None, lane_qualified=False, core_quality_qualified=False)
    with SessionLocal() as db:
        save(db, payload)
        account(db, cash=2000)
        db.add(PaperPosition(account="Optimizer Paper", symbol="CORE", shares=8, avg_cost=110,
                             reason="Core Quality Lane", entry_target=125, entry_stretch_target=145,
                             entry_stop=88, entry_horizon_days=90, entry_plan_version=SCORING_VERSION))
        db.commit()
    run_paper_cycle(OfflineQuotes(), entry_event=True)
    with SessionLocal() as db:
        assert db.query(PaperPosition).one().shares == 8
        assert db.query(PaperTrade).count() == 0


def test_profit_stage_columns_are_added_to_an_existing_database(monkeypatch):
    import app.db as db_module
    legacy = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(legacy)
    with legacy.begin() as connection:
        for table in ("positions", "paper_positions"):
            for column in ("original_shares", "profit_taken_shares", "profit_taken_stages"):
                connection.exec_driver_sql(f"ALTER TABLE {table} DROP COLUMN {column}")
    monkeypatch.setattr(db_module, "engine", legacy)
    db_module._ensure_runtime_columns()
    for table in ("positions", "paper_positions"):
        columns = {column["name"] for column in inspect(legacy).get_columns(table)}
        assert {"original_shares", "profit_taken_shares", "profit_taken_stages"} <= columns
