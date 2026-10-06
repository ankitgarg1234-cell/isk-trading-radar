from app.portfolio_engine import (
    RISK_PROFILES, account_risk, active_level, stock_risk_score,
    build_optimizer_plan, entry_attention_signal, suggested_position_size, system_signal,
)


def sample_analysis():
    return {
        "symbol":"TEST","price":100,"category":"Core","action":"BUY NOW",
        "lane":"CORE_QUALITY","lane_label":"Core Quality Lane","lane_qualified":True,
        "core_quality_qualified":True,"explosive_qualified":False,
        "promotion_risk":{"hard_reject":False,"promotional_risk":False},
        "deterministic_score":88,"ai_score":92,"analyst_score":80,
        "entry_zone_status":"PRIMARY_BUY","decision_confidence":"high",
        "levels":{"buy_low":95,"buy_high":101,"better_low":90,"better_high":93,"breakout":108,"stop":92,"target":130,"do_not_chase":115},
        "target_plan":{"base_target":130,"stretch_target":140},
        "technicals":{"atr":3,"relative_volume":1.2,"change20_pct":6,"rsi":55,"ema20":98},
        "risk_reward":3.5,
        "news":{"label":"Neutral","material_events":0,"high_negative_events":0},
        "fundamentals":{"sector":"Technology"},
    }


def test_risk_profile_changes_size_not_stock_score():
    a=sample_analysis(); original=a["deterministic_score"]
    low=suggested_position_size(a,cash=100000,reserve_cash=20000,portfolio_value=100000,profile="LOW",fx_rate_to_base=1)
    high=suggested_position_size(a,cash=100000,reserve_cash=5000,portfolio_value=100000,profile="HIGH",fx_rate_to_base=1)
    assert high["shares"] >= low["shares"]
    assert a["deterministic_score"] == original


def test_active_level_shows_now_when_inside_buy_zone():
    a=sample_analysis(); level=active_level(a,False)
    assert level["label"] == "Primary Buy"
    assert level["distance"] == "NOW"


def test_system_signal_can_surface_strong_buy():
    assert system_signal(sample_analysis(),False) == "STRONG BUY"


def test_account_risk_flags_concentrated_portfolio():
    rows=[
        {"symbol":"A","value_base":80000,"stock_risk":75,"sector":"Technology","category":"Explosive Runner","material_events":1},
        {"symbol":"B","value_base":10000,"stock_risk":40,"sector":"Technology","category":"Core","material_events":0},
    ]
    r=account_risk(rows,10000,target_profile="MEDIUM")
    assert r["score"] > 50
    assert r["largest_position_pct"] >= 70
    assert r["gap"] > 0

def test_primary_buy_64_remains_watch_despite_raw_buy_language():
    a=sample_analysis()
    a["action"]="CONSIDER BUYING NOW"
    a["deterministic_score"]=69
    a["ai_score"]=76
    a["entry_zone_status"]="PRIMARY_BUY"
    assert system_signal(a,False) == "WATCH"



def test_owned_wait_more_means_hold_dont_add():
    a=sample_analysis()
    a["action"]="WAIT MORE"
    a["entry_zone_status"]="PRIMARY_BUY"
    assert system_signal(a,True) == "HOLD"


def test_owned_buy_zone_does_not_imply_second_purchase_without_explicit_add():
    a=sample_analysis()
    a["action"]="BUY NOW"
    assert system_signal(a,True) == "HOLD"
    a["action"]="ADD"
    assert system_signal(a,True) == "BUY"


def test_whole_share_rounding_uses_nearest_score_target(monkeypatch):
    import app.portfolio_engine as pe
    a=sample_analysis()
    a["price"]=450
    a["levels"]["stop"]=390
    monkeypatch.setattr(pe,"candidate_rank_score",lambda _a:{"score":78})
    s=pe.suggested_position_size(a,cash=7000,reserve_cash=0,portfolio_value=10000,profile="MEDIUM",fx_rate_to_base=1,whole_shares=True)
    assert s["target_allocation_pct"] == 4.0
    assert s["score_target_shares_raw"] < 1
    assert s["shares"] == 1


def test_whole_share_rounding_repairs_near_two_share_target(monkeypatch):
    import app.portfolio_engine as pe
    a=sample_analysis()
    a["price"]=108
    a["levels"]["stop"]=100
    monkeypatch.setattr(pe,"candidate_rank_score",lambda _a:{"score":72.5})
    s=pe.suggested_position_size(a,cash=7000,reserve_cash=0,portfolio_value=10000,profile="MEDIUM",fx_rate_to_base=1,whole_shares=True)
    assert s["target_allocation_pct"] == 2.0
    assert 1.5 < s["score_target_shares_raw"] < 2.0
    assert s["shares"] == 2


def test_whole_share_rounding_never_breaks_15pct_position_cap(monkeypatch):
    import app.portfolio_engine as pe
    a=sample_analysis()
    a["price"]=800
    a["levels"]["stop"]=760
    monkeypatch.setattr(pe,"candidate_rank_score",lambda _a:{"score":99})
    s=pe.suggested_position_size(a,cash=10000,reserve_cash=0,portfolio_value=10000,profile="HIGH",fx_rate_to_base=1,whole_shares=True)
    assert s["target_allocation_pct"] == 15.0
    assert s["shares"] == 1
    assert s["capital"] <= 1500


def test_entry_attention_requires_minimum_0_4x_rr():
    a=sample_analysis()
    a["action"]="CONSIDER BUYING NOW"
    a["deterministic_score"]=80
    a["risk_reward"]=0.399
    a["target_plan"]["base_target"]=100+8*.399
    assert entry_attention_signal(a) is None
    a["risk_reward"]=0.4
    a["target_plan"]["base_target"]=103.2
    assert entry_attention_signal(a) == "BUY"


def test_optimizer_filters_sub_0_4x_rr_and_backfills_better_match():
    low=sample_analysis()
    low["symbol"]="LOWRR"
    low["risk_reward"]=0.39
    low["target_plan"]["base_target"]=100+8*.39
    low["deterministic_score"]=95

    good=sample_analysis()
    good["symbol"]="GOODRR"
    good["risk_reward"]=0.4
    good["target_plan"]["base_target"]=103.2
    good["deterministic_score"]=82

    plan=build_optimizer_plan(
        {"LOWRR":low,"GOODRR":good},
        owned_symbols=set(),
        profile="MEDIUM",
        visible_limit=20,
        shortlist_limit=20,
    )
    symbols=[r["symbol"] for r in plan["visible"]]
    assert "LOWRR" not in symbols
    assert "GOODRR" in symbols
    assert plan["min_entry_risk_reward"] == 0.4
