import copy
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.score_band_experiment import (
    advance, allocation_pct, entry_check, experiment_spec, new_state,
    profit_cash_quantity, proposed_quantity, summary, trailing_stop,
    ensure_single_account,
)


def observation(symbol="TEST", price=100, score=90, analyst=80, minute=0, target=120, stop=95):
    return {"symbol": symbol, "currency": "USD", "price": price,
        "asof": f"2026-10-05T14:{minute:02d}:00+00:00", "deterministic_score": score,
        "data_sources": {"price": {"quote_asof": f"2026-10-05T14:{minute:02d}:00+00:00"}},
        "analyst_score": analyst, "risk_reward": (target-price)/(price-stop) if price>stop else 0,
        "lane": "CORE_QUALITY", "lane_qualified": True, "decision_confidence": "high",
        "fundamental_confidence": "high", "news": {"label": "Neutral", "material_events": 0},
        "breakdown": {"Fundamentals": 18}, "thesis_assessment": {"invalidated": False},
        "levels": {"buy_low": 98, "buy_high": 102, "better_low": 94, "better_high": 97,
                   "breakout": 110, "stop": stop, "do_not_chase": 114},
        "target_plan": {"base_target": target, "stretch_target": target+10},
        "technicals": {"rsi": 55, "ema20": 99, "change20_pct": 2, "relative_volume": 1.6, "atr": 2}}


def tick(state, *rows, market_open=True):
    now = max(r["asof"] for r in rows)
    return advance(state, list(rows), now, market_open, benchmark=100)


@pytest.mark.parametrize("score,weight", [(64.99,0),(65,5),(69.99,5),(70,10),(74.99,10),(75,15),(79.99,15),
    (80,20),(84.99,20),(85,30),(89.99,30),(90,40),(100,40),(101,0),(None,0),(float("nan"),0)])
def test_band_boundaries(score, weight):
    assert allocation_pct(score) == weight


@pytest.mark.parametrize("score,analyst,okay", [(65,75,True),(64.99,90,False),(90,74.99,False),(90,None,False)])
def test_all_qualifiers_are_mandatory(score, analyst, okay):
    assert entry_check(observation(score=score,analyst=analyst))[0] == okay


def test_rr_recomputed_and_breakout_confirmation_required():
    a = observation(price=110, target=114, stop=100)
    assert entry_check(a) == (True, "breakout", 0.4)
    a["target_plan"]["base_target"] = 113.999
    a["risk_reward"] = 100
    assert entry_check(a)[1] == "rr_below_0_4"
    a["target_plan"]["base_target"] = 120
    a["technicals"]["relative_volume"] = 1.49
    assert entry_check(a)[1] == "no_entry_trigger"
    a["technicals"]["relative_volume"] = 2
    a["target_plan"]["base_target"] = 130
    assert entry_check(a,115)[1] == "do_not_chase"


def test_momentum_and_missing_indicators_block_entry():
    a = observation()
    a["data_sources"] = {"price":{"quote_asof":a["asof"]}}
    a["technicals"]["rsi"] = 39.99
    assert entry_check(a)[1] == "momentum_not_ready"
    a["technicals"].update(rsi=50,ema20=105,change20_pct=-3)
    assert entry_check(a)[1] == "momentum_not_ready"
    a["technicals"].pop("ema20")
    assert entry_check(a)[1] == "momentum_not_ready"


def test_risk_budget_fees_and_existing_exposure_constrain_quantity():
    state = new_state("AGGRESSIVE")
    book = state["variants"]["complete_strategy"]
    a = observation(stop=99)
    assert proposed_quantity(a,book,state["spec"],100) == 39
    a["levels"]["stop"] = 90
    assert proposed_quantity(a,book,state["spec"],100) == 19
    book["cash"] = 1000
    book["positions"]["TEST"] = {"shares":90,"avg_cost":100}
    book["marks"]["TEST"] = 100
    assert proposed_quantity(a,book,state["spec"],100,book["positions"]["TEST"]) == 0


def test_next_observation_fill_duplicates_closed_session_and_restart():
    state = new_state("AGGRESSIVE")
    a = observation(stop=99)
    assert tick(state,a,market_open=False)["fills"] == 0
    tick(state,a)
    assert not state["variants"]["complete_strategy"]["trades"]
    tick(state,a)
    assert not state["variants"]["complete_strategy"]["trades"]
    import json
    state = json.loads(json.dumps(state))
    tick(state,observation(minute=2,stop=99))
    book = state["variants"]["complete_strategy"]
    assert len(book["trades"]) == 1
    assert book["trades"][0]["signal_at"] < book["trades"][0]["observed_at"]
    assert book["cash"] + book["positions"]["TEST"]["shares"]*100 < 10000


def test_fill_gap_rechecks_frozen_target_without_raising_it():
    state = new_state()
    tick(state,observation(target=102,stop=95))
    # New analysis suggests a higher target; the order must retain the signal target.
    tick(state,observation(price=101.5,target=150,minute=2))
    book = state["variants"]["complete_strategy"]
    assert not book["trades"]
    assert book["blockers"]["rr_below_0_4"] == 1


def test_cash_is_allocated_highest_score_first_and_never_negative():
    state = new_state("AGGRESSIVE")
    rows = [observation(symbol=s,score=score,stop=99) for s,score in (("D",72),("C",82),("B",87),("A",93))]
    tick(state,*rows)
    tick(state,*[{**r,"asof":"2026-10-05T14:02:00+00:00"} for r in rows])
    book = state["variants"]["complete_strategy"]
    assert [t["symbol"] for t in book["trades"]] == ["A","B","C","D"]
    assert [t["shares"] for t in book["trades"]] == [39,29,19,9]
    assert book["cash"] >= 0


def test_profit_withdrawal_releases_cash_not_all_realized_profit():
    assert profit_cash_quantity(10,100,120,0) == 2
    assert profit_cash_quantity(1,100,120) == 0
    assert profit_cash_quantity(10,100,100) == 0
    state = new_state()
    book = state["variants"]["complete_strategy"]
    book["cash"] = 8999
    book["positions"]["TEST"] = {"shares":10,"avg_cost":100,"entry_fee_per_share":0.1,
        "entry_target":120,"entry_stop":95,"stop":95,"peak":100,"harvested":False}
    tick(state,observation(price=120,minute=0))
    tick(state,observation(price=120,minute=2))
    assert book["positions"]["TEST"]["shares"] == 8
    sells = [t for t in book["trades"] if t["side"] == "SELL"]
    assert len(sells) == 1 and sells[0]["cash_released"] > 200
    assert 39 < sells[0]["realized_profit"] < 40
    assert book["positions"]["TEST"]["stop"] == 116
    tick(state,observation(price=121,minute=4))
    tick(state,observation(price=121,minute=6))
    assert len([t for t in book["trades"] if t["side"] == "SELL"]) == 1


def test_trail_tightens_and_gap_exit_uses_observed_fill_not_stop():
    assert trailing_stop(95,120,2,120,110,55) == 116
    assert trailing_stop(116,120,2,117,118,45) == 118
    assert trailing_stop(118,120,4,121,110,60) == 118
    state = new_state()
    book = state["variants"]["complete_strategy"]
    book["positions"]["TEST"] = {"shares":8,"avg_cost":100,"entry_fee_per_share":0.1,
        "entry_target":120,"entry_stop":95,"stop":118,"peak":120,"harvested":True}
    tick(state,observation(price=117,minute=0))
    tick(state,observation(price=110,minute=2))
    assert "TEST" not in book["positions"]
    assert book["trades"][0]["price"] < 110
    assert book["trades"][0]["reason"] == "MOMENTUM_TRAIL"


def test_stale_future_observations_and_expired_intents_do_not_fill():
    state = new_state()
    a = observation()
    advance(state,[a],"2026-10-05T14:11:00+00:00",True)
    assert not state["variants"]["complete_strategy"]["pending"]
    advance(state,[a],"2026-10-05T13:59:00+00:00",True)
    assert not state["variants"]["complete_strategy"]["pending"]
    tick(state,a)
    tick(state,observation(minute=12))
    assert not state["variants"]["complete_strategy"]["trades"]


def test_persistence_is_separate_and_observations_are_deduplicated():
    from app.db import SessionLocal, PaperAccount, PaperPosition, Position, ScoreBandObservation
    from app.score_band_capture import run_experiment_cycle, experiment_status, experiment_holding_symbols
    with SessionLocal() as db:
        db.add(PaperAccount(account="Optimizer Paper",cash=5851.26,starting_cash=10000))
        db.add(PaperPosition(account="Optimizer Paper",symbol="WDC",shares=10,avg_cost=414.46))
        db.add(Position(symbol="CRDO",shares=2,avg_cost=178,account="Manual"))
        db.commit()
    a = observation()
    now = datetime(2026,10,5,14,tzinfo=timezone.utc)
    run_experiment_cycle([a],True,now)
    run_experiment_cycle([a],True,now)
    assert "TEST" in experiment_holding_symbols()
    b = observation(minute=2)
    b["data_sources"] = {"price":{"quote_asof":b["asof"]}}
    run_experiment_cycle([b],True,datetime(2026,10,5,14,2,tzinfo=timezone.utc))
    result = experiment_status(True)
    assert result["observation_count"] == 2
    assert result["variants"]["complete_strategy"]["trade_count"] == 1
    with SessionLocal() as db:
        assert db.query(ScoreBandObservation).count() == 2
        assert db.query(PaperAccount).one().cash == 5851.26
        assert db.query(PaperPosition).one().shares == 10
        assert db.query(Position).one().shares == 2


def test_report_waiting_state_and_api():
    from app.main import app
    client = TestClient(app)
    response = client.get("/api/experiments/score-bands")
    assert response.status_code == 200
    assert response.json()["status"] == "waiting_for_market_open"
    assert list(response.json()["variants"]) == ["complete_strategy"]
    page = client.get("/experiments/score-bands")
    assert page.status_code == 200
    assert "One paper account" in page.text
    assert page.text.count("<tr><td>Strategy paper account") == 1


def test_initial_stop_exits_on_next_quote_and_includes_entry_fees():
    state = new_state()
    tick(state,observation())
    tick(state,observation(minute=2))
    book = state["variants"]["complete_strategy"]
    tick(state,observation(price=94,minute=4))
    assert "TEST" in book["positions"]
    tick(state,observation(price=90,minute=6))
    assert "TEST" not in book["positions"]
    assert book["trades"][-1]["reason"] == "INITIAL_STOP"
    ledger_cash = 10000 + sum((1 if t["side"]=="SELL" else -1)*t["shares"]*t["price"] - t["fees"] for t in book["trades"])
    assert book["cash"] == pytest.approx(ledger_cash)
    assert book["cash"] - 10000 == pytest.approx(book["trades"][-1]["realized_profit"])


def test_retrieval_of_old_quote_cannot_fill_and_analyst_inputs_are_archived():
    from app.score_band_capture import compact_observation, run_experiment_cycle, experiment_status
    a = observation()
    a["asof"] = "2026-10-05T14:20:00+00:00"
    a["fundamentals"] = {"recommendationMean": 1.5, "targetMeanPrice": 125}
    compact = compact_observation(a)
    assert compact["asof"] == "2026-10-05T14:00:00+00:00"
    assert compact["analyst_inputs"]["recommendationMean"] == 1.5
    run_experiment_cycle([a],True,datetime(2026,10,5,14,20,tzinfo=timezone.utc))
    assert experiment_status()["observation_count"] == 0
    a["data_sources"]["price"].pop("quote_asof")
    run_experiment_cycle([a],True,datetime(2026,10,5,14,20,tzinfo=timezone.utc))
    assert experiment_status()["observation_count"] == 0


def test_breakout_anchor_excludes_running_daily_bar_and_does_not_mutate_source():
    from app.score_band_capture import compact_observation
    a = observation(price=110,target=125,stop=105)
    a["history"] = [{"date":f"2026-09-{i:02d}","close":109} for i in range(1,22)]
    a["history"].append({"date":"2026-10-05","close":110})
    original = copy.deepcopy(a)
    compact = compact_observation(a)
    assert compact["levels"]["breakout"] == pytest.approx(109.2)
    assert compact["levels"]["do_not_chase"] == pytest.approx(111.2)
    assert entry_check(compact)[1] == "breakout"
    assert a == original


def test_late_benchmark_cannot_create_false_same_start_comparison():
    state = new_state()
    a = observation()
    advance(state,[a],a["asof"],True,benchmark=None)
    b = observation(minute=2)
    advance(state,[b],b["asof"],True,benchmark=100)
    assert summary(state)["benchmark_return_pct"] is None


def test_experiment_api_uses_existing_authentication(monkeypatch):
    from dataclasses import replace
    import app.main as main
    monkeypatch.setattr(main,"settings",replace(main.settings,app_password="test-secret"))
    client = TestClient(main.app)
    assert client.get("/api/experiments/score-bands").status_code == 401
    response = client.post("/login",data={"username":main.settings.app_username,"password":"test-secret"},follow_redirects=False)
    assert response.status_code == 303
    assert client.get("/api/experiments/score-bands").status_code == 200


def test_scanner_passes_deep_batch_to_experiment_without_top20_cut(monkeypatch):
    import app.scanner as scanner
    service = scanner.RadarService()
    monkeypatch.setattr(service,"market_open",lambda:True)
    monkeypatch.setattr(service,"candidate_symbols",lambda:["TEST"])
    monkeypatch.setattr(service,"holding_symbols",lambda:[])
    monkeypatch.setattr(service,"analyze_symbol",lambda s:observation())
    monkeypatch.setattr(service,"_enrich_strategic_top_candidates",lambda:(False,[]))
    monkeypatch.setattr(service,"_sync_rotation_alerts",lambda x:None)
    monkeypatch.setattr(scanner,"run_paper_cycle",lambda *a,**k:{"cash":10000})
    captured=[]
    def capture(rows,market_open):
        captured.extend(rows)
        return {"status":"observing"}
    monkeypatch.setattr(scanner,"run_experiment_cycle",capture)
    result = service._scan_once_impl()
    assert [a["symbol"] for a in captured] == ["TEST"]
    assert service.last_experiment_result["status"] == "observing"
    assert not any("score-band" in s for s in result["errors"])


def test_single_account_migration_preserves_balance_positions_and_history():
    state = new_state("HIGH")
    tick(state,observation())
    tick(state,observation(minute=2))
    expected = copy.deepcopy(state["variants"]["complete_strategy"])
    control = copy.deepcopy(new_state()["variants"]["complete_strategy"])
    control["pending"]["OLD"] = {"side":"BUY","observed_at":observation()["asof"]}
    state["variants"]["current_rules_control"] = control
    state["variants"]["new_selection"] = copy.deepcopy(control)
    ensure_single_account(state)
    assert list(state["variants"]) == ["complete_strategy"]
    assert state["variants"]["complete_strategy"] == expected
    assert state["archived_variants"]["current_rules_control"] == control
    migrated = copy.deepcopy(state)
    ensure_single_account(state)
    assert state == migrated
    assert state["spec"]["profile"] == "HIGH"
    assert state["spec"]["active_accounts"] == 1


def test_existing_database_migrates_to_one_without_reset_or_archive_tracking():
    import json
    from app.db import SessionLocal, ScoreBandExperiment
    from app.score_band_experiment import VERSION
    from app.score_band_capture import experiment_status, experiment_holding_symbols
    state = new_state("HIGH")
    book = state["variants"]["complete_strategy"]
    book["cash"] = 4321.5
    control = copy.deepcopy(new_state()["variants"]["complete_strategy"])
    control["positions"]["CONTROLONLY"] = {"shares":1,"avg_cost":100}
    state["variants"]["current_rules_control"] = control
    with SessionLocal() as db:
        db.add(ScoreBandExperiment(version=VERSION,state_json=json.dumps(state)))
        db.commit()
    result = experiment_status(True)
    assert list(result["variants"]) == ["complete_strategy"]
    assert result["variants"]["complete_strategy"]["cash"] == 4321.5
    assert list(result["trades"]) == ["complete_strategy"]
    assert "CONTROLONLY" not in experiment_holding_symbols()
    with SessionLocal() as db:
        persisted = json.loads(db.query(ScoreBandExperiment).one().state_json)
        assert persisted["archived_variants"]["current_rules_control"] == control


def test_missing_complete_ledger_refuses_to_manufacture_new_balance():
    state = new_state()
    state["variants"].clear()
    with pytest.raises(ValueError,match="refusing to reset"):
        ensure_single_account(state)
