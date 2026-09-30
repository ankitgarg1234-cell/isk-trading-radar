import json
from datetime import datetime, timezone, timedelta

from fastapi.testclient import TestClient

from app.db import SessionLocal, RadarCandidate, PaperAccount, PaperPosition, PaperTrade, PaperSnapshot, Alert
from app.main import app
from app.paper_engine import run_paper_cycle, paper_status, _candidate_payloads
from app.portfolio_engine import build_optimizer_plan, candidate_rank_score
from app.scanner import RadarService

client=TestClient(app)


def payload(symbol, score=85, sector="Technology", expected=25, ai=88, price=100):
    return {
        "symbol":symbol,"price":price,"deterministic_score":score,"ai_score":ai,"analyst_score":78,
        "expected_yield_pct":expected,"risk_reward":3.0,"decision_confidence":"high","category":"Core",
        "lane":"CORE_QUALITY","lane_label":"Core Quality Lane","lane_qualified":True,
        "core_quality_qualified":True,"explosive_qualified":False,
        "entry_zone_status":"PRIMARY_BUY","action":"BUY NOW","negative_news_override":None,
        "thesis_assessment":{"invalidated":False},
        "levels":{"buy_low":price*.97,"buy_high":price*1.02,"better_low":price*.9,"better_high":price*.93,"stop":price*.88,"target":price*1.3},
        "technicals":{"atr":2,"relative_volume":1.2,"change20_pct":5},"news":{"material_events":0},
        "fundamentals":{"sector":sector},
    }


def test_optimizer_buys_every_qualified_name_inside_top20():
    analyses={f"S{i:02d}":payload(f"S{i:02d}",score=95-i,sector=f"Sector{i%5}",expected=35-i*.3) for i in range(30)}
    plan=build_optimizer_plan(analyses,profile="HIGH",visible_limit=20,shortlist_limit=10,target_positions=6,max_positions=7)
    assert len(plan["visible"])==20
    assert len(plan["shortlist"])==10
    assert len(plan["selected_new"])==20
    assert plan["position_cap_enabled"] is False
    assert plan["target_positions"] is None
    assert plan["max_positions"] is None
    assert all(r["bucket"]=="INVEST NOW" for r in plan["visible"])



def test_optimizer_has_no_sector_position_cap():
    # Sector is evidence about each stock, not a portfolio-level exclusion.
    # If the strongest candidates all come from one sector, they may all be selected.
    analyses = {
        f"TECH{i}": payload(f"TECH{i}", score=95-i, sector="Technology", expected=35-i)
        for i in range(8)
    }
    plan = build_optimizer_plan(
        analyses, profile="HIGH", visible_limit=20, shortlist_limit=10,
        target_positions=6, max_positions=7, min_rank_score=62
    )
    assert len(plan["selected_new"]) == 8
    assert {r["sector"] for r in plan["selected_new"]} == {"Technology"}


def test_optimizer_does_not_force_five_positions_when_only_three_qualify():
    analyses={
        "A":payload("A",90,"Technology"),"B":payload("B",86,"Healthcare"),"C":payload("C",82,"Industrials"),
        "D":payload("D",60,"Energy"),"E":payload("E",55,"Utilities"),
    }
    plan=build_optimizer_plan(analyses,profile="HIGH",target_positions=6,max_positions=7,min_rank_score=62)
    assert len(plan["selected_new"])==3



def test_primary_buy_69_is_investable_and_selected():
    a=payload("CELC",score=69,sector="Healthcare",expected=20,ai=76,price=84.79)
    a["action"]="CONSIDER BUYING NOW"
    a["entry_zone_status"]="PRIMARY_BUY"
    plan=build_optimizer_plan({"CELC":a},profile="HIGH",visible_limit=20,shortlist_limit=10)
    row=plan["visible"][0]
    assert row["entry_signal"] == "STARTER BUY"
    assert row["bucket"] == "INVEST NOW"
    assert row in plan["selected_new"]


def test_risk_fit_does_not_block_qualified_top20_entry():
    high_risk = payload("RISKY", score=90, sector="Technology", expected=35, price=10)
    high_risk["category"] = "Explosive Runner"
    high_risk["technicals"] = {"atr": 1.2, "relative_volume": 3.0, "change20_pct": 35}
    plan = build_optimizer_plan({"RISKY": high_risk}, profile="LOW", visible_limit=20, shortlist_limit=10)
    row = plan["visible"][0]
    assert row["entry_signal"] in {"STRONG BUY", "BUY", "STARTER BUY"}
    assert row["risk_fit"] == "ABOVE TARGET"
    assert row["bucket"] == "INVEST NOW"
    assert len(plan["selected_new"]) == 1

def test_optimizer_never_admits_sub_five_stock_even_if_payload_claims_lane_qualified():
    a = payload("CHEAP", score=95, sector="Technology", expected=40, price=4.99)
    a["lane"] = "EXPLOSIVE"
    a["lane_label"] = "Explosive Lane"
    a["explosive_qualified"] = True
    plan = build_optimizer_plan({"CHEAP": a}, profile="HIGH", visible_limit=20)
    assert plan["visible"] == []
    assert plan["selected_new"] == []


def test_optimizer_excludes_pre_v2_category_only_payload():
    a = payload("STALE", score=95, price=25)
    for key in ("lane", "lane_label", "lane_qualified", "core_quality_qualified", "explosive_qualified"):
        a.pop(key, None)
    a["category"] = "Core"
    plan = build_optimizer_plan({"STALE": a}, profile="HIGH", visible_limit=20)
    assert plan["visible"] == []


def test_ai_is_confirmation_not_part_of_portfolio_rank_math():
    a=payload("A",score=82,ai=20)
    b=payload("B",score=82,ai=98)
    assert candidate_rank_score(a)["score"] == candidate_rank_score(b)["score"]
    assert candidate_rank_score(a)["ai_confirmation"] != candidate_rank_score(b)["ai_confirmation"]


def test_dashboard_never_returns_more_than_twenty_radar_rows():
    with SessionLocal() as db:
        for i in range(30):
            p=payload(f"T{i:02d}",score=95-(i%20),sector=f"Sector{i%6}",expected=30-i*.2)
            db.add(RadarCandidate(symbol=p["symbol"],category="Core",action="BUY NOW",score=p["deterministic_score"],ai_score=p["ai_score"],price=100,portfolio_rank_score=99-i,current_json=json.dumps(p)))
        db.commit()
    d=client.get('/api/live').json()
    assert len(d["candidates"])==20
    assert d["optimizer"]["visible"]==20
    assert d["optimizer"]["position_cap_enabled"] is False
    assert "max_positions" not in d["optimizer"]


class BenchProvider:
    def chart(self,symbol,range_="5d",interval="1d"):
        return {"meta":{"regularMarketPrice":500.0}}


def test_paper_cycle_starts_at_10000_and_can_hold_all_qualified_names():
    sectors=["Technology","Healthcare","Industrials","Energy","Utilities","Financial Services","Consumer Cyclical"]
    with SessionLocal() as db:
        for i in range(10):
            p=payload(f"P{i}",score=95-i,sector=sectors[i%len(sectors)],expected=35-i,price=100+i)
            rank=candidate_rank_score(p)["score"]
            db.add(RadarCandidate(symbol=p["symbol"],category="Core",action="BUY NOW",score=p["deterministic_score"],ai_score=p["ai_score"],price=p["price"],portfolio_rank_score=rank,current_json=json.dumps(p)))
        db.commit()
    result=run_paper_cycle(BenchProvider(),force_rebalance=True)
    assert result["status"]=="ok"
    with SessionLocal() as db:
        acct=db.query(PaperAccount).one()
        positions=db.query(PaperPosition).all()
        assert acct.starting_cash==10000
        assert len(positions) == 10
        assert all(p.shares > 0 for p in positions)
        assert all(float(p.shares).is_integer() for p in positions)
        assert acct.cash >= 0


def test_paper_status_exposes_position_identity_pnl_and_recent_trades():
    with SessionLocal() as db:
        status = paper_status(db)
        assert "positions" in status
        assert "trades" in status
        if status["positions"]:
            row = status["positions"][0]
            for key in ("symbol", "shares", "avg_cost", "price", "value", "pnl", "pnl_pct", "weight_pct", "entry_rank_score", "reason"):
                assert key in row
        if status["trades"]:
            trade = status["trades"][0]
            for key in ("symbol", "side", "shares", "price", "rank_score", "reason", "created_at"):
                assert key in trade


def test_entry_event_buys_immediately_without_resetting_daily_rotation_clock():
    p = payload("EVT", score=82, sector="Healthcare", expected=30, price=100)
    rank = candidate_rank_score(p)["score"]
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        db.add(PaperAccount(account="Optimizer Paper", starting_cash=10000, cash=10000, benchmark_symbol="SPY", enabled=True, last_rebalance_at=now))
        db.add(RadarCandidate(symbol="EVT", category="Core", action="BUY NOW", score=82, ai_score=88, price=100, portfolio_rank_score=rank, current_json=json.dumps(p)))
        db.commit()
    result = run_paper_cycle(BenchProvider(), entry_event=True)
    assert result["rebalanced"] is True
    assert result["entry_event"] is True
    assert result["daily_rebalance"] is False
    with SessionLocal() as db:
        pos = db.query(PaperPosition).filter(PaperPosition.symbol == "EVT").first()
        acct = db.query(PaperAccount).one()
        assert pos is not None
        # Event-driven entries must not postpone the separate daily rotation clock.
        assert abs(acct.last_rebalance_at.replace(tzinfo=timezone.utc).timestamp() - now.timestamp()) < 1


def test_new_qualified_name_never_forces_sale_of_intact_holding_when_cash_is_zero():
    now = datetime.now(timezone.utc)
    old = payload("OLD", score=72, sector="Industrials", expected=12, price=100)
    old["entry_zone_status"] = "WATCH"
    old["action"] = "HOLD — DON'T ADD"
    new = payload("NEW", score=90, sector="Technology", expected=30, price=100)

    with SessionLocal() as db:
        db.add(PaperAccount(
            account="Optimizer Paper", starting_cash=10000, cash=0,
            benchmark_symbol="SPY", enabled=True, last_rebalance_at=now,
        ))
        db.add(PaperPosition(
            account="Optimizer Paper", symbol="OLD", shares=100,
            avg_cost=100, rank_score_at_entry=70, reason="existing intact holding",
        ))
        db.add(RadarCandidate(
            symbol="OLD", category="Core", action=old["action"], score=72, ai_score=88,
            price=100, portfolio_rank_score=candidate_rank_score(old)["score"],
            current_json=json.dumps(old),
        ))
        db.add(RadarCandidate(
            symbol="NEW", category="Core", action="BUY NOW", score=90, ai_score=88,
            price=100, portfolio_rank_score=candidate_rank_score(new)["score"],
            current_json=json.dumps(new),
        ))
        db.commit()

    result = run_paper_cycle(BenchProvider(), entry_event=True)
    assert result["rebalanced"] is True
    with SessionLocal() as db:
        old_pos = db.query(PaperPosition).filter(PaperPosition.symbol == "OLD").one()
        new_pos = db.query(PaperPosition).filter(PaperPosition.symbol == "NEW").first()
        sells = db.query(PaperTrade).filter(PaperTrade.side == "SELL").all()
        assert old_pos.shares == 100
        assert new_pos is None
        assert sells == []


def test_normal_cycle_can_load_only_current_holdings_without_top20_egress():
    with SessionLocal() as db:
        for i in range(30):
            p = payload(f"E{i:02d}", score=90, sector=f"S{i%5}")
            db.add(RadarCandidate(symbol=p["symbol"], category="Core", action="BUY NOW", score=90, ai_score=88, price=100, portfolio_rank_score=90-i, current_json=json.dumps(p)))
        db.commit()
        rows = _candidate_payloads(db, ["E29"], ranked_limit=0)
        assert set(rows) == {"E29"}
        ranked = _candidate_payloads(db, ["E29"], ranked_limit=20)
        assert len(ranked) <= 21
        assert "E29" in ranked


def test_scanner_entry_event_is_material_and_not_repeated_for_same_state():
    radar = RadarService(provider=object(), ai=object())
    p = payload("MAT", score=80, sector="Technology", expected=25, price=100)
    assert radar._paper_entry_event(p) is True
    assert radar._paper_entry_event(dict(p)) is False
    changed = dict(p)
    changed["expected_yield_pct"] = 5
    assert radar._paper_entry_event(changed) is True

def test_optimizer_has_no_per_tier_max_two_cap():
    analyses = {}
    for i in range(6):
        p = payload(f"TIER{i}", score=95-i, sector="Technology", expected=35-i)
        p["tier"] = "A"
        analyses[p["symbol"]] = p
    plan = build_optimizer_plan(
        analyses, profile="HIGH", visible_limit=20, shortlist_limit=10,
        target_positions=6, max_positions=7, min_rank_score=62
    )
    assert len(plan["selected_new"]) == 6


def test_actionable_rank_11_is_bought_because_shortlist_is_review_only():
    analyses = {
        f"R{i:02d}": payload(f"R{i:02d}", score=95-i, sector="Technology", expected=35-i * 0.2)
        for i in range(12)
    }
    plan = build_optimizer_plan(
        analyses, profile="HIGH", visible_limit=20, shortlist_limit=10,
        target_positions=6, max_positions=7, min_rank_score=62
    )
    assert all(r.get("decision_reason") for r in plan["visible"])
    rank_11 = plan["visible"][10]
    assert rank_11["entry_signal"] in {"STRONG BUY", "BUY", "STARTER BUY"}
    assert rank_11["optimizer_action"] == rank_11["entry_signal"]
    assert rank_11["bucket"] == "INVEST NOW"
    assert "no holding-count" in rank_11["decision_reason"]


def test_gwre_style_policy_change_rechecks_without_buy_state_transition(monkeypatch):
    from dataclasses import replace
    import app.scanner as scanner_mod

    radar = RadarService(provider=object(), ai=object())
    gwre = payload("GWRE", score=77, sector="Technology", expected=25, price=100)
    assert radar._paper_entry_event(gwre) is True
    assert radar._paper_entry_event(dict(gwre)) is False

    assert radar._paper_optimizer_invalidation_event() is True
    assert radar._paper_optimizer_invalidation_event() is False

    monkeypatch.setattr(
        scanner_mod, "settings",
        replace(scanner_mod.settings, optimizer_visible_limit=scanner_mod.settings.optimizer_visible_limit + 1),
    )
    assert radar._paper_optimizer_invalidation_event() is True
    assert radar._paper_entry_event(dict(gwre)) is False


def test_scan_once_rechecks_top20_every_cycle_even_without_new_signal(monkeypatch):
    import app.scanner as scanner_mod

    radar = RadarService(provider=object(), ai=object())
    monkeypatch.setattr(radar, "candidate_symbols", lambda: [])
    monkeypatch.setattr(radar, "_enrich_strategic_top_candidates", lambda: (False, []))
    monkeypatch.setattr(radar, "_sync_rotation_alerts", lambda: None)
    calls = []

    def fake_paper_cycle(provider, *, force_rebalance=False, entry_event=False):
        calls.append(entry_event)
        return {"status": "ok"}

    monkeypatch.setattr(scanner_mod, "run_paper_cycle", fake_paper_cycle)
    first = radar.scan_once(force=True)
    assert first["paper_optimizer_invalidated"] is True
    assert first["paper_top20_recheck"] is True
    assert calls == [True]

    calls.clear()
    second = radar.scan_once(force=True)
    assert second["paper_optimizer_invalidated"] is False
    assert second["paper_top20_recheck"] is True
    assert calls == [True]

def test_paper_percentages_separate_daily_move_from_entry_pnl():
    with SessionLocal() as db:
        db.add(PaperAccount(account="Optimizer Paper", starting_cash=10000, cash=5000, benchmark_symbol="SPY", enabled=True))
        # Insert out of alphabetical order to prove paper_status does not rely on
        # database row order when attaching cost basis / P&L to symbols.
        db.add(PaperPosition(account="Optimizer Paper", symbol="BBB", shares=10, avg_cost=100, rank_score_at_entry=70, reason="B"))
        db.add(PaperPosition(account="Optimizer Paper", symbol="AAA", shares=5, avg_cost=80, rank_score_at_entry=80, reason="A"))
        a = payload("AAA", score=85, price=110)
        a["previous_close"] = 100
        b = payload("BBB", score=80, price=50)
        b["previous_close"] = 55
        db.add(RadarCandidate(symbol="AAA", category="Core", action="BUY NOW", score=85, ai_score=88, price=110, portfolio_rank_score=85, current_json=json.dumps(a)))
        db.add(RadarCandidate(symbol="BBB", category="Core", action="BUY NOW", score=80, ai_score=88, price=50, portfolio_rank_score=80, current_json=json.dumps(b)))
        db.commit()

    with SessionLocal() as db:
        status = paper_status(db)
    by_symbol = {r["symbol"]: r for r in status["positions"]}
    assert by_symbol["AAA"]["day_change_pct"] == 10.0
    assert by_symbol["AAA"]["pnl_pct"] == 37.5
    assert by_symbol["AAA"]["reason"] == "A"
    assert by_symbol["BBB"]["day_change_pct"] == -9.09
    assert by_symbol["BBB"]["pnl_pct"] == -50.0
    assert by_symbol["BBB"]["reason"] == "B"



def test_paper_summary_absolute_daily_and_legacy_trade_split():
    now = datetime.now(timezone.utc)
    a = payload("AAA", score=85, price=105)
    a["previous_close"] = 100
    with SessionLocal() as db:
        db.add(PaperAccount(
            account="Optimizer Paper", starting_cash=10000, cash=9000,
            benchmark_symbol="SPY", enabled=True, started_at=now-timedelta(days=2),
        ))
        db.add(PaperPosition(
            account="Optimizer Paper", symbol="AAA", shares=10,
            avg_cost=100, rank_score_at_entry=80, reason="valid buy",
        ))
        db.add(RadarCandidate(
            symbol="AAA", category="Core", action="BUY NOW", score=85, ai_score=88,
            price=105, portfolio_rank_score=80, current_json=json.dumps(a),
        ))
        db.add(PaperSnapshot(
            account="Optimizer Paper", equity=9900, cash=9000, invested=900,
            benchmark_price=100, portfolio_return_pct=-1, benchmark_return_pct=0,
            excess_return_pct=-1, drawdown_pct=-1, positions_count=1,
            created_at=now-timedelta(days=1),
        ))
        db.add(PaperTrade(
            account="Optimizer Paper", symbol="AAA", side="BUY", shares=10,
            price=100, fees=1, rank_score=80, reason="valid buy",
            created_at=now-timedelta(hours=2),
        ))
        db.add(PaperTrade(
            account="Optimizer Paper", symbol="AAA", side="SELL", shares=1,
            price=101, fees=0.1, rank_score=80,
            reason="REBALANCE — fund newly qualified uncapped Top-20 entries",
            created_at=now-timedelta(hours=1),
        ))
        db.commit()

    with SessionLocal() as db:
        status = paper_status(db)
    assert status["equity"] == 10050.0
    assert status["absolute_return"] == 50.0
    assert status["daily_pnl"] == 150.0
    assert status["daily_pnl_pct"] == 1.52
    assert status["trade_count"] == 1
    assert status["legacy_trade_count"] == 1
    assert status["trades"][0]["side"] == "BUY"
    assert status["legacy_trades"][0]["legacy_rebalance"] is True


def test_existing_paper_account_migrates_to_sp500_total_return_benchmark():
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        db.add(PaperAccount(
            account="Optimizer Paper", starting_cash=10000, cash=10000,
            benchmark_symbol="SPY", enabled=True, started_at=now-timedelta(days=1),
        ))
        db.commit()
    run_paper_cycle(BenchProvider(), force_rebalance=True)
    with SessionLocal() as db:
        acct = db.query(PaperAccount).one()
        assert acct.benchmark_symbol == "^SP500TR"


def test_legacy_fractional_position_is_normalised_without_sell_trade():
    now = datetime.now(timezone.utc)
    a = payload("DUST", score=80, price=25)
    a["action"] = "HOLD — DON'T ADD"
    a["entry_zone_status"] = "WATCH"
    with SessionLocal() as db:
        db.add(PaperAccount(
            account="Optimizer Paper", starting_cash=10000, cash=9000,
            benchmark_symbol="^SP500TR", enabled=True, last_rebalance_at=now,
        ))
        db.add(PaperPosition(
            account="Optimizer Paper", symbol="DUST", shares=10.75,
            avg_cost=20, rank_score_at_entry=70, reason="legacy fractional allocation",
        ))
        db.add(RadarCandidate(
            symbol="DUST", category="Core", action=a["action"], score=80, ai_score=88,
            price=25, portfolio_rank_score=70, current_json=json.dumps(a),
        ))
        db.commit()

    before_equity = 9000 + 10.75 * 25
    result = run_paper_cycle(BenchProvider(), entry_event=False)
    assert result["whole_share_corrections"]
    with SessionLocal() as db:
        acct = db.query(PaperAccount).one()
        pos = db.query(PaperPosition).filter(PaperPosition.symbol == "DUST").one()
        sells = db.query(PaperTrade).filter(PaperTrade.side == "SELL").all()
        assert pos.shares == 10
        assert sells == []
        after_equity = acct.cash + pos.shares * 25
        assert round(after_equity, 6) == round(before_equity, 6)


def test_sub_one_share_legacy_dust_is_removed_without_sell_trade():
    now = datetime.now(timezone.utc)
    a = payload("DUST", score=80, price=25)
    a["action"] = "HOLD — DON'T ADD"
    a["entry_zone_status"] = "WATCH"
    with SessionLocal() as db:
        db.add(PaperAccount(
            account="Optimizer Paper", starting_cash=10000, cash=9999,
            benchmark_symbol="^SP500TR", enabled=True, last_rebalance_at=now,
        ))
        db.add(PaperPosition(
            account="Optimizer Paper", symbol="DUST", shares=0.000003,
            avg_cost=25, rank_score_at_entry=70, reason="legacy dust",
        ))
        db.add(RadarCandidate(
            symbol="DUST", category="Core", action=a["action"], score=80, ai_score=88,
            price=25, portfolio_rank_score=70, current_json=json.dumps(a),
        ))
        db.commit()

    run_paper_cycle(BenchProvider(), entry_event=False)
    with SessionLocal() as db:
        assert db.query(PaperPosition).filter(PaperPosition.symbol == "DUST").first() is None
        assert db.query(PaperTrade).filter(PaperTrade.side == "SELL").count() == 0


def test_fractional_historical_trade_is_legacy_not_valid_trade():
    with SessionLocal() as db:
        db.add(PaperAccount(
            account="Optimizer Paper", starting_cash=10000, cash=10000,
            benchmark_symbol="^SP500TR", enabled=True,
        ))
        db.add(PaperTrade(
            account="Optimizer Paper", symbol="BRZE", side="BUY", shares=0.000003,
            price=25.47, fees=0, rank_score=73.5,
            reason="old fractional allocation",
        ))
        db.commit()
    with SessionLocal() as db:
        status = paper_status(db)
    assert status["trade_count"] == 0
    assert status["legacy_trade_count"] == 1
    assert status["legacy_trades"][0]["legacy_fractional"] is True


def test_paper_status_reconciles_valid_trades_with_normalized_legacy_holdings():
    now = datetime.now(timezone.utc)
    a = payload("AAA", score=85, price=100)
    b = payload("BBB", score=82, price=50)
    with SessionLocal() as db:
        db.add(PaperAccount(
            account="Optimizer Paper", starting_cash=10000, cash=8000,
            benchmark_symbol="^SP500TR", enabled=True, started_at=now-timedelta(days=2),
        ))
        db.add(PaperPosition(account="Optimizer Paper", symbol="AAA", shares=10, avg_cost=90, rank_score_at_entry=80, reason="whole"))
        db.add(PaperPosition(account="Optimizer Paper", symbol="BBB", shares=20, avg_cost=40, rank_score_at_entry=75, reason="normalized"))
        db.add(RadarCandidate(symbol="AAA", category="Core", action="HOLD — DON'T ADD", score=85, ai_score=88, price=100, portfolio_rank_score=80, current_json=json.dumps(a)))
        db.add(RadarCandidate(symbol="BBB", category="Core", action="HOLD — DON'T ADD", score=82, ai_score=88, price=50, portfolio_rank_score=75, current_json=json.dumps(b)))
        db.add(PaperTrade(account="Optimizer Paper", symbol="AAA", side="BUY", shares=10, price=90, fees=0, rank_score=80, reason="whole buy"))
        db.add(PaperTrade(account="Optimizer Paper", symbol="BBB", side="BUY", shares=20.5, price=40, fees=0, rank_score=75, reason="legacy fractional buy"))
        db.commit()

    with SessionLocal() as db:
        status = paper_status(db)
    assert status["position_count"] == 2
    assert status["trade_count"] == 1
    assert status["normalized_legacy_position_count"] == 1
    assert status["current_valid_origin_count"] == 1
    assert status["normalized_legacy_symbols"] == ["BBB"]
    by_symbol = {p["symbol"]: p for p in status["positions"]}
    assert by_symbol["AAA"]["origin_type"] == "WHOLE-SHARE BUY"
    assert by_symbol["BBB"]["origin_type"] == "NORMALIZED LEGACY"


def test_max_drawdown_reports_positive_historical_magnitude():
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        db.add(PaperAccount(
            account="Optimizer Paper", starting_cash=10000, cash=10000,
            benchmark_symbol="^SP500TR", enabled=True, started_at=now-timedelta(days=3),
        ))
        db.add(PaperSnapshot(account="Optimizer Paper", equity=10000, cash=10000, invested=0, benchmark_price=100, portfolio_return_pct=0, benchmark_return_pct=0, excess_return_pct=0, drawdown_pct=0, positions_count=0, created_at=now-timedelta(days=3)))
        db.add(PaperSnapshot(account="Optimizer Paper", equity=9500, cash=9500, invested=0, benchmark_price=100, portfolio_return_pct=-5, benchmark_return_pct=0, excess_return_pct=-5, drawdown_pct=-5, positions_count=0, created_at=now-timedelta(days=2)))
        db.add(PaperSnapshot(account="Optimizer Paper", equity=9800, cash=9800, invested=0, benchmark_price=100, portfolio_return_pct=-2, benchmark_return_pct=0, excess_return_pct=-2, drawdown_pct=-2, positions_count=0, created_at=now-timedelta(days=1)))
        db.commit()

    with SessionLocal() as db:
        status = paper_status(db)
    assert status["drawdown_pct"] == 5.0
    assert status["current_drawdown_pct"] == 2.0


def test_dashboard_uses_one_open_positions_paper_section_only():
    html = client.get("/").text
    assert 'id="paperOpenPositions"' in html
    assert 'id="paperOpenPositionsTable"' in html
    assert 'href="#paperOpenPositionsTable"' in html
    assert 'Recent valid paper trades' not in html
    assert 'Recent paper trades' not in html
    assert 'Legacy allocator audit' not in html
    assert 'id="paperPortfolio"' not in html
    assert 'id="paperPositionCards"' not in html
    assert 'id="paperTradesBody"' not in html
    assert '>Origin<' not in html


def test_paper_owned_symbol_is_hold_and_stale_buy_alert_is_hidden():
    now = datetime.now(timezone.utc)
    a = payload("NOW", score=80, price=134.0)
    a["action"] = "BUY NOW"
    with SessionLocal() as db:
        db.add(PaperAccount(
            account="Optimizer Paper", starting_cash=10000, cash=8500,
            benchmark_symbol="^SP500TR", enabled=True, started_at=now-timedelta(days=1),
        ))
        db.add(PaperPosition(
            account="Optimizer Paper", symbol="NOW", shares=11, avg_cost=129.16,
            rank_score_at_entry=86.9, reason="Optimizer #1 BUY",
        ))
        db.add(RadarCandidate(
            symbol="NOW", category="Core", action="BUY NOW", score=80, ai_score=87,
            price=134.0, portfolio_rank_score=88, current_json=json.dumps(a),
            updated_at=now,
        ))
        db.add(Alert(
            symbol="NOW", alert_type="buy_level", severity="high",
            title="NOW: Entry level reached — BUY",
            message="Primary Buy reached", action="BUY", acknowledged=False,
            created_at=now,
        ))
        db.commit()

    html = client.get("/").text
    idx = html.index('data-symbol="NOW"')
    row_html = html[idx:idx+3500]
    assert 'signal-hold' in row_html
    assert 'HOLD / DON&#39;T ADD' in row_html or "HOLD / DON'T ADD" in row_html
    assert 'NOW: Entry level reached — BUY' not in html
