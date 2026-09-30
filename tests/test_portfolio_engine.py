from app.portfolio_engine import (
    RISK_PROFILES, account_risk, active_level, stock_risk_score,
    suggested_position_size, system_signal,
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
        "technicals":{"atr":3,"relative_volume":1.2,"change20_pct":6,"rsi":55,"ema20":98},
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

def test_primary_buy_69_is_starter_buy_consistently():
    a=sample_analysis()
    a["action"]="CONSIDER BUYING NOW"
    a["deterministic_score"]=69
    a["ai_score"]=76
    a["entry_zone_status"]="PRIMARY_BUY"
    assert system_signal(a,False) == "STARTER BUY"



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
