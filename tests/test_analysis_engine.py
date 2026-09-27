from app.analysis_engine import score_bundle, position_action, parse_positions_from_text, portfolio_proposals
from .helpers import bundle, strong_fundamentals, positive_news, negative_news


def test_explosive_runner_requires_strong_fundamentals():
    weak={"revenueGrowth":.02,"earningsGrowth":-.10,"grossMargins":.18,"operatingMargins":-.05,"returnOnEquity":-.1,"debtToEquity":220,"forwardPE":80,"sector":"Technology"}
    result=score_bundle(bundle(fundamentals=weak,news=positive_news()))
    assert result["category"] != "Explosive Runner"
    assert result["breakdown"]["Fundamentals"] < 14


def test_strong_setup_can_be_explosive_runner():
    result=score_bundle(bundle())
    assert result["breakdown"]["Fundamentals"] >= 14
    assert result["category"] in {"Explosive Runner","Core"}
    assert result["deterministic_score"] >= 75


def test_material_negative_news_overrides_score():
    result=score_bundle(bundle(news=negative_news(two=True)))
    assert result["negative_news_override"]
    assert result["deterministic_score"] <= 68
    assert result["category"] == "Watch"


def test_existing_profitable_position_can_take_partial_profit():
    result={
        "deterministic_score":85,
        "news":{"label":"Bearish","material_events":1,"high_negative_events":1},
        "technicals":{"ema20":205,"rsi":38},
        "levels":{"buy_low":195,"buy_high":200,"better_low":186,"better_high":190,"stop":180,"do_not_chase":225,"breakout":215},
    }
    action,reason=position_action(result,198,{"shares":10,"avg_cost":176})
    assert action == "TAKE PARTIAL PROFIT"
    assert "Profitable" in reason


def test_new_position_waits_for_better_buy_when_weakening():
    result={
        "deterministic_score":82,
        "news":{"label":"Bearish","material_events":1,"high_negative_events":0},
        "technicals":{"ema20":205,"rsi":40,"relative_volume":1.0},
        "levels":{"buy_low":195,"buy_high":200,"better_low":186,"better_high":189,"stop":180,"do_not_chase":225,"breakout":215},
    }
    action,reason=position_action(result,198,None)
    assert action == "WAIT MORE"
    assert "186.00" in reason


def test_buy_now_when_buy_zone_and_thesis_intact():
    result={
        "deterministic_score":88,
        "news":{"label":"Neutral","material_events":0,"high_negative_events":0},
        "technicals":{"ema20":198,"rsi":55,"relative_volume":1.3},
        "levels":{"buy_low":195,"buy_high":200,"better_low":190,"better_high":193,"stop":182,"do_not_chase":225,"breakout":215},
    }
    action,_=position_action(result,198,None)
    assert action == "BUY NOW"


def test_parse_position_ocr_text_and_deduplicate():
    text="""CRDO 10 176.00 213.00\nSRRK 2 26.40 30.10\nCRDO 12 180.00 213.00"""
    rows=parse_positions_from_text(text)
    by={r["symbol"]:r for r in rows}
    assert by["CRDO"]["shares"] == 12
    assert by["CRDO"]["avg_cost"] == 180
    assert by["SRRK"]["shares"] == 2


def test_portfolio_optimizer_can_rotate_and_deploy_cash():
    analyses={
        "WEAK":{"action":"TAKE PARTIAL PROFIT","ai_score":70,"ai_expected_yield_pct":5},
        "STRONG":{"action":"BUY NOW","ai_score":94,"ai_expected_yield_pct":35},
    }
    props=portfolio_proposals([{"symbol":"WEAK","shares":10,"avg_cost":50}],analyses,10000,3000)
    types={p["type"] for p in props}
    assert "DEPLOY CASH" in types
    assert "ROTATE" in types


def test_heuristic_ai_exposes_adjustments_risks_and_sensitivity():
    from app.analysis_engine import heuristic_ai
    r=score_bundle(bundle())
    ai=heuristic_ai(r)
    assert 0 <= ai["ai_score"] <= 100
    assert isinstance(ai["adjustments"],list)
    assert ai["risks"]
    assert len(ai["sensitivity"]) >= 3
    assert ai["holding_period_min_days"] < ai["holding_period_max_days"]
