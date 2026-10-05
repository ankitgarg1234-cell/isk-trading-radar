import json
from datetime import datetime, timedelta, timezone

from app.analysis_engine import score_bundle
from app.db import SessionLocal, PaperAccount, PaperPosition, PaperTrade, RadarCandidate
from app.paper_engine import run_paper_cycle, paper_status
from app.portfolio_engine import score_target_allocation_pct, suggested_position_size, candidate_rank_score
from app.strategic_capital import StrategicCapitalProvider
from tests.helpers import bundle, strong_fundamentals, history


class BenchProvider:
    def chart(self, symbol, period, interval):
        return {"meta": {"regularMarketPrice": 100}}


def _core_payload(symbol="CORE", score=90, price=10):
    factor = score / 100.0
    return {
        "symbol": symbol,
        "price": price,
        "previous_close": price,
        "category": "Core",
        "lane": "CORE_QUALITY",
        "lane_label": "Core Quality Lane",
        "lane_qualified": True,
        "core_quality_qualified": True,
        "explosive_qualified": False,
        "deterministic_score": score,
        "analyst_score": 80,
        "target_plan": {"base_target":price*1.3,"stretch_target":price*1.4},
        "breakdown": {
            "Fundamentals": 20 * factor,
            "Catalyst": 15 * factor,
            "Valuation": 10 * factor,
            "Momentum": 15 * factor,
            "Risk/Reward": 10 * factor,
            "Sector": 10 * factor,
        },
        "data_quality_pct": 100 * factor,
        "expected_yield_pct": 30,
        "risk_reward": 3.5,
        "decision_confidence": "high",
        "entry_zone_status": "PRIMARY_BUY",
        "levels": {
            "buy_low": price * .95, "buy_high": price * 1.02,
            "better_low": price * .9, "better_high": price * .93,
            "breakout": price * 1.08, "stop": price * .95,
            "target": price * 1.3, "do_not_chase": price * 1.15,
        },
        "technicals": {"atr": price * .02, "relative_volume": 1.3, "change20_pct": 8, "rsi": 55, "ema20": price * .98},
        "news": {"label": "Neutral", "material_events": 1, "high_negative_events": 0, "items": []},
        "fundamentals": {"sector": "Technology"},
        "action": "BUY NOW",
    }


def test_lane_model_classifies_strong_catalyst_setup_as_explosive():
    b = bundle(price=100)
    b["fundamentals"]["marketCap"] = 5_000_000_000
    # Recent tape is constructive near 100, while a prior fundamental/catalyst
    # valuation anchor leaves >30% modeled upside. One isolated older high is
    # intentionally not sufficient by itself: the test also carries strong
    # fundamentals, material news and 2.2x relative volume.
    rows = history(start=40, days=260, daily=.23, last_volume_multiplier=2.2)
    rows[120].update({"open":139, "high":141, "low":138, "close":140, "volume":1_000_000})
    b["history"] = rows
    result = score_bundle(b)
    assert result["lane"] == "EXPLOSIVE"
    assert result["lane_label"] == "Explosive Lane"
    assert result["core_quality_qualified"] is True
    assert result["explosive_qualified"] is True
    assert result["deterministic_holding_period_max_days"] == 20


def test_lane_model_rejects_penny_stock_even_with_strong_news_and_volume():
    b = bundle(price=4.50)
    b["fundamentals"]["marketCap"] = 5_000_000_000
    result = score_bundle(b)
    assert result["lane"] is None
    assert result["lane_qualified"] is False
    assert result["promotion_risk"]["hard_reject"] is True
    assert any("share price below" in x for x in result["promotion_risk"]["reasons"])


def test_extreme_unexplained_volume_cannot_enter_explosive_lane():
    b = bundle(news=[], price=100)
    b["fundamentals"]["marketCap"] = 5_000_000_000
    b["history"] = history(start=80, daily=.08, last_volume_multiplier=10)
    result = score_bundle(b)
    assert result["explosive_qualified"] is False
    assert result["promotion_risk"]["unexplained_extreme_volume"] is True


def test_score_allocation_ladder_caps_at_fifteen_percent():
    cases = [
        (67, 0), (68, 2), (74.9, 2), (75, 4), (80, 6), (85, 8),
        (90, 10), (95, 12), (97.9, 12), (98, 15), (100, 15),
    ]
    for score, expected in cases:
        assert score_target_allocation_pct(score) == expected


def test_score_sets_target_but_stop_risk_can_only_reduce_it():
    high = _core_payload(score=100, price=100)
    high["expected_yield_pct"] = 35
    high["risk_reward"] = 3.5
    high["levels"]["stop"] = 95
    sized = suggested_position_size(
        high, cash=100000, reserve_cash=0, portfolio_value=100000,
        profile="MEDIUM", fx_rate_to_base=1,
    )
    assert sized["target_allocation_pct"] == 15
    assert sized["capital"] <= 15000

    wide_stop = dict(high)
    wide_stop["levels"] = dict(high["levels"], stop=80)
    risk_capped = suggested_position_size(
        wide_stop, cash=100000, reserve_cash=0, portfolio_value=100000,
        profile="MEDIUM", fx_rate_to_base=1,
    )
    assert risk_capped["capital"] < sized["capital"]
    assert risk_capped["target_allocation_pct"] == 15


def test_paper_allocator_preserves_score_weighting_when_cash_constrained():
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        db.add(PaperAccount(
            account="Optimizer Paper", starting_cash=1000, cash=1000,
            benchmark_symbol="^SP500TR", benchmark_start_price=100,
            benchmark_last_price=100, enabled=True, last_rebalance_at=now,
        ))
        for i in range(5):
            p = _core_payload(f"H{i}", score=100, price=10)
            p["expected_yield_pct"] = 35
            db.add(RadarCandidate(
                symbol=p["symbol"], category="Core", action="BUY NOW", score=100, ai_score=90,
                price=10, portfolio_rank_score=candidate_rank_score(p)["score"], current_json=json.dumps(p),
            ))
        for i in range(5):
            p = _core_payload(f"M{i}", score=82, price=10)
            p["expected_yield_pct"] = 20
            db.add(RadarCandidate(
                symbol=p["symbol"], category="Core", action="BUY NOW", score=82, ai_score=85,
                price=10, portfolio_rank_score=candidate_rank_score(p)["score"], current_json=json.dumps(p),
            ))
        db.commit()

    run_paper_cycle(BenchProvider(), entry_event=True)
    with SessionLocal() as db:
        positions = {p.symbol: p for p in db.query(PaperPosition).all()}
        assert positions["H0"].shares > positions["M0"].shares
        assert all(float(p.shares).is_integer() for p in positions.values())
        assert db.query(PaperTrade).filter(PaperTrade.side == "SELL").count() == 0


def test_explosive_position_expires_after_twenty_sessions_if_core_quality_fails():
    now = datetime.now(timezone.utc)
    p = _core_payload("EXPX", score=80, price=20)
    p.update({"lane": None, "lane_qualified": False, "core_quality_qualified": False, "category": "Watch", "action": "HOLD"})
    with SessionLocal() as db:
        db.add(PaperAccount(
            account="Optimizer Paper", starting_cash=1000, cash=800,
            benchmark_symbol="^SP500TR", benchmark_start_price=100, benchmark_last_price=100,
            enabled=True, last_rebalance_at=now,
        ))
        db.add(PaperPosition(
            account="Optimizer Paper", symbol="EXPX", shares=10, avg_cost=20,
            rank_score_at_entry=85, reason="Explosive Lane • Top-20 #1 BUY",
            opened_at=now - timedelta(days=35),
        ))
        db.add(RadarCandidate(
            symbol="EXPX", category="Watch", action="HOLD", score=80, ai_score=80,
            price=20, portfolio_rank_score=50, current_json=json.dumps(p),
        ))
        db.commit()

    run_paper_cycle(BenchProvider(), entry_event=False)
    with SessionLocal() as db:
        assert db.query(PaperPosition).filter(PaperPosition.symbol == "EXPX").first() is None
        sell = db.query(PaperTrade).filter(PaperTrade.symbol == "EXPX", PaperTrade.side == "SELL").one()
        assert "20-session thesis expired" in sell.reason


def test_explosive_position_graduates_to_core_after_twenty_sessions_when_quality_holds():
    now = datetime.now(timezone.utc)
    p = _core_payload("GRAD", score=85, price=20)
    p["action"] = "HOLD"
    with SessionLocal() as db:
        db.add(PaperAccount(
            account="Optimizer Paper", starting_cash=1000, cash=800,
            benchmark_symbol="^SP500TR", benchmark_start_price=100, benchmark_last_price=100,
            enabled=True, last_rebalance_at=now,
        ))
        db.add(PaperPosition(
            account="Optimizer Paper", symbol="GRAD", shares=10, avg_cost=20,
            rank_score_at_entry=85, reason="Explosive Lane • Top-20 #1 BUY",
            opened_at=now - timedelta(days=35),
        ))
        db.add(RadarCandidate(
            symbol="GRAD", category="Core", action="HOLD", score=85, ai_score=85,
            price=20, portfolio_rank_score=80, current_json=json.dumps(p),
        ))
        db.commit()

    run_paper_cycle(BenchProvider(), entry_event=False)
    with SessionLocal() as db:
        pos = db.query(PaperPosition).filter(PaperPosition.symbol == "GRAD").one()
        assert "GRADUATED TO CORE" in pos.reason
        assert db.query(PaperTrade).filter(PaperTrade.side == "SELL").count() == 0


def test_kushner_affinity_news_is_captured_as_connected_capital_shadow_evidence():
    provider = StrategicCapitalProvider()
    events = provider.classify_news("QXO", [{
        "title": "Jared Kushner's Affinity Partners invests in QXO shares",
        "publisher": "Reuters",
        "published": int(datetime.now(timezone.utc).timestamp()),
        "link": "https://www.reuters.com/example",
    }])
    assert events
    assert events[0]["type"] == "TRUMP_FAMILY_OR_CONNECTED_CAPITAL"
    assert events[0]["source_quality"] == "HIGH-CREDIBILITY MEDIA"


def test_explosive_requires_thirty_percent_remaining_upside():
    b = bundle()
    b["fundamentals"]["marketCap"] = 5_000_000_000
    result = score_bundle(b)
    assert result["expected_yield_pct"] < 30
    assert result["explosive_qualified"] is False
    assert result["lane"] in {"CORE_QUALITY", None}


def test_recent_reverse_split_is_hard_rejected_without_extra_feed():
    b = bundle()
    b["fundamentals"]["marketCap"] = 5_000_000_000
    b["recent_reverse_splits"] = [{"date": 1_790_000_000, "ratio": "1:20"}]
    result = score_bundle(b)
    assert result["lane_qualified"] is False
    assert result["promotion_risk"]["hard_reject"] is True
    assert any("recent reverse split" in x for x in result["promotion_risk"]["reasons"])


def test_existing_position_risk_is_subtracted_before_add_sizing():
    a = _core_payload("ADDME", score=100, price=100)
    a["levels"]["stop"] = 95
    # $100k portfolio, Medium risk budget = $750. Existing $10k position
    # carries ~$500 stop risk, leaving ~$250 risk budget / ~$5k ADD ceiling.
    sized = suggested_position_size(
        a, cash=90_000, reserve_cash=0, portfolio_value=100_000,
        profile="MEDIUM", fx_rate_to_base=1, existing_value=10_000,
        whole_shares=False,
    )
    assert sized["target_allocation_pct"] == 15
    assert round(sized["existing_risk_amount"], 2) == 500.00
    assert round(sized["remaining_risk_budget"], 2) == 250.00
    assert sized["capital"] <= 5_000.01


def test_paper_engine_executes_only_explicit_add_toward_score_target():
    now = datetime.now(timezone.utc)
    a = _core_payload("ADDME", score=100, price=100)
    a["levels"]["stop"] = 95
    # Persisted global state can still look like a new-entry BUY. The paper
    # cycle must re-evaluate it with the actual position and derive ADD.
    a["action"] = "BUY NOW"
    rank = candidate_rank_score(a)["score"]
    with SessionLocal() as db:
        db.add(PaperAccount(
            account="Optimizer Paper", starting_cash=10_000, cash=9_000,
            benchmark_symbol="^SP500TR", benchmark_start_price=100,
            benchmark_last_price=100, enabled=True, last_rebalance_at=now,
        ))
        db.add(PaperPosition(
            account="Optimizer Paper", symbol="ADDME", shares=10, avg_cost=100,
            rank_score_at_entry=rank, reason="Core Quality Lane • Top-20 #1 BUY",
            opened_at=now,
        ))
        db.add(RadarCandidate(
            symbol="ADDME", category="Core", action="BUY NOW", score=100, ai_score=95,
            price=100, portfolio_rank_score=rank, current_json=json.dumps(a),
        ))
        db.commit()

    run_paper_cycle(BenchProvider(), entry_event=True)
    with SessionLocal() as db:
        pos = db.query(PaperPosition).filter(PaperPosition.symbol == "ADDME").one()
        assert 10 < pos.shares <= 15
        buys = db.query(PaperTrade).filter(PaperTrade.symbol == "ADDME", PaperTrade.side == "BUY").all()
        assert len(buys) == 1
        assert "ADD" in buys[0].reason


def test_core_lane_requires_market_cap_evidence():
    b = bundle()
    b["fundamentals"].pop("marketCap", None)
    result = score_bundle(b)
    assert result["lane_qualified"] is False
    assert result["lane"] is None
    assert any("market-cap evidence unavailable" in x for x in result["lane_reasons"])


def test_core_lane_requires_minimum_average_dollar_liquidity():
    b = bundle()
    rows = history(start=100, days=260, daily=.01, last_volume_multiplier=1.2)
    for row in rows:
        row["volume"] = 20_000
    b["history"] = rows
    result = score_bundle(b)
    assert result["lane_qualified"] is False
    assert result["lane"] is None
    assert any("average dollar volume" in x for x in result["lane_reasons"])


def test_secondary_chatter_cannot_verify_explosive_catalyst():
    b = bundle(price=100)
    b["history"] = history(start=40, days=260, daily=.23, last_volume_multiplier=2.2)
    b["history"][120].update({"open":139, "high":141, "low":138, "close":140, "volume":1_000_000})
    now = int(datetime.now(timezone.utc).timestamp())
    b["news"] = [{
        "title": "Company raises guidance after record earnings beat",
        "publisher": "Random Stocks Blog",
        "relatedTickers": ["TEST"],
        "published": now,
        "link": "https://example.com/chatter",
    }]
    result = score_bundle(b)
    assert result["core_quality_qualified"] is True
    assert result["explosive_qualified"] is False
    assert result["catalyst_verified"] is False


def test_credible_material_news_can_verify_explosive_catalyst():
    b = bundle(price=100)
    b["history"] = history(start=40, days=260, daily=.23, last_volume_multiplier=2.2)
    b["history"][120].update({"open":139, "high":141, "low":138, "close":140, "volume":1_000_000})
    result = score_bundle(b)
    assert result["explosive_qualified"] is True
    assert result["catalyst_verified"] is True
    assert result["catalyst_evidence"]


def test_explosive_blockers_explain_why_core_quality_name_does_not_qualify():
    b = bundle()
    b["fundamentals"]["marketCap"] = 5_000_000_000
    result = score_bundle(b)
    assert result["core_quality_qualified"] is True
    assert result["explosive_qualified"] is False
    assert result["explosive_blockers"]
    assert "modeled remaining upside < 30%" in result["explosive_blockers"]


def test_legacy_or_currently_ineligible_paper_holding_is_not_labeled_core():
    now = datetime.now(timezone.utc)
    legacy = {
        "symbol": "OLDLOW",
        "price": 3.50,
        "previous_close": 3.60,
        "deterministic_score": 80,
        "category": "Core",
        "action": "HOLD",
        "levels": {"stop": 2.5, "target": 5.0},
        "technicals": {},
        "news": {},
        "fundamentals": {"sector": "Healthcare"},
    }
    with SessionLocal() as db:
        db.add(PaperAccount(
            account="Optimizer Paper", starting_cash=1000, cash=650,
            benchmark_symbol="^SP500TR", benchmark_start_price=100,
            benchmark_last_price=100, enabled=True, last_rebalance_at=now,
        ))
        db.add(PaperPosition(
            account="Optimizer Paper", symbol="OLDLOW", shares=100, avg_cost=3.50,
            rank_score_at_entry=80, reason="Optimizer #1 BUY", opened_at=now,
        ))
        db.add(RadarCandidate(
            symbol="OLDLOW", category="Core", action="HOLD", score=80, ai_score=80,
            price=3.50, portfolio_rank_score=80, current_json=json.dumps(legacy),
        ))
        db.commit()
        status = paper_status(db)
        row = next(x for x in status["positions"] if x["symbol"] == "OLDLOW")
        assert row["lane"] == "OUTSIDE_LANES"
        assert row["lane_label"] == "Outside Current Lanes"
        assert status["core_position_count"] == 0
        assert status["outside_lane_position_count"] == 1
