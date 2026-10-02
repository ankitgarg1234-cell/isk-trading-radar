from app.analysis_engine import score_bundle, fundamental_score, position_action, position_action_plan, analyst_score, parse_positions_from_text, portfolio_proposals
from .helpers import bundle, strong_fundamentals, positive_news, negative_news


def test_hypergrowth_ratios_are_scaled_as_ratios_not_percentage_points():
    f = {
        "revenueGrowth": 2.0568,
        "earningsGrowth": 8.05,
        "quarterlyRevenueGrowth": 1.147,
        "grossMargins": 0.68,
        "operatingMargins": 0.333,
        "returnOnEquity": 0.173,
    }
    score, reasons, confidence = fundamental_score(f)
    assert score == 19.0
    assert confidence == "high"
    assert any("Revenue growth 205.7% → 4/4" in r for r in reasons)
    assert any("Earnings growth 805.0% → 4/4" in r for r in reasons)
    assert any("Quarterly revenue growth 114.7%" in r and "→ +2" in r for r in reasons)


def test_standard_ratio_fundamentals_keep_existing_score():
    # Ordinary decimal-ratio inputs must remain unchanged by the hypergrowth fix.
    score, reasons, confidence = fundamental_score(strong_fundamentals())
    assert score == 20.0
    assert confidence == "high"
    assert any("Revenue growth 30.0% → 4/4" in r for r in reasons)
    assert any("Earnings growth 35.0% → 4/4" in r for r in reasons)


def test_hypergrowth_revenue_gets_growth_adjusted_valuation_bonus():
    f = strong_fundamentals()
    f["revenueGrowth"] = 2.0568
    f["earningsGrowth"] = 8.05
    f["forwardPE"] = 40
    result = score_bundle(bundle(fundamentals=f))
    assert result["breakdown"]["Valuation"] == 7


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


def test_parse_avanza_portfolio_ocr_columns_correctly():
    text = r"""
O Buy Sell a Alphabet Inc Class A 40262928 1 +0.46 % Sep 25 343.92 $338.28 +147 kr +4.50 % 3,411 SEK
O Buy Sell a Credo Technology 40262928 6 +7.65% Sep 25 210.97 $177.68 +2,268 SEK +22.05% 12,555 SEK
O Buy Sell [ ] Investor B 40262928 27 +0.64 % Sep 25 411.45 405.64 SEK +157 kr +1.43% 11,109 SEK
O Buy Sell a Jaguar Health 40262928 8 +9.07 % Sep 25 7.70 $8.48 -63 SEK -9.34% 611 kr
O Buy Sell & \irum Pharmaceuticals 40262928 4 40.38% Sep25 89.70 $90.08 -23 kr -0.64 % 3,559 SEK
"""
    rows=parse_positions_from_text(text)
    by={r["symbol"]:r for r in rows}
    assert by["GOOGL"]["shares"] == 1
    assert by["GOOGL"]["avg_cost"] == 338.28
    assert by["CRDO"]["shares"] == 6
    assert by["CRDO"]["avg_cost"] == 177.68
    assert by["INVE-B.ST"]["shares"] == 27
    assert by["INVE-B.ST"]["avg_cost"] == 405.64
    assert by["JAGX"]["shares"] == 8
    assert by["JAGX"]["avg_cost"] == 8.48
    assert by["MIRM"]["shares"] == 4
    assert by["MIRM"]["avg_cost"] == 90.08
    assert all(r["shares"] != 40262928 for r in rows)
    assert "O" not in by


def test_low_score_missing_evidence_does_not_force_reduce():
    result={
        "deterministic_score":58,
        "news":{"label":"Neutral","material_events":0,"high_negative_events":0},
        "technicals":{"ema20":100,"rsi":55},
        "levels":{"buy_low":90,"buy_high":95,"better_low":85,"better_high":88,"stop":70,"do_not_chase":120,"breakout":110},
        "breakdown":{"Fundamentals":10},
        "fundamental_confidence":"low",
        "decision_confidence":"low",
    }
    action,reason=position_action(result,100,{"shares":6,"avg_cost":80,"account":"Avanza Screenshot"})
    assert action == "HOLD — DATA REVIEW"
    assert "missing data" in reason.lower() or "incomplete" in reason.lower()


def test_weak_price_momentum_and_low_score_do_not_trigger_panic_reduce():
    result={
        "deterministic_score":59,
        "news":{"label":"Bearish","material_events":1,"high_negative_events":0,"items":[]},
        "technicals":{"ema20":105,"rsi":35},
        "levels":{"buy_low":90,"buy_high":95,"better_low":85,"better_high":88,"stop":70,"do_not_chase":120,"breakout":110},
        "breakdown":{"Fundamentals":7},
        "fundamental_confidence":"high",
        "decision_confidence":"high",
    }
    position={"shares":6,"avg_cost":110,"account":"Avanza Screenshot"}
    action,reason=position_action(result,100,position)
    assert action == "HOLD — DON'T ADD"
    assert "thesis" in reason.lower() or "panic sell" in reason.lower()

def test_reduce_requires_verified_fundamental_invalidation_and_has_quantity_plan():
    result={
        "deterministic_score":57,
        "news":{"label":"Bearish","material_events":1,"high_negative_events":1,"items":[{"title":"Company cuts guidance after demand deterioration","sentiment":"negative"}]},
        "technicals":{"ema20":105,"rsi":35},
        "levels":{"buy_low":90,"buy_high":95,"better_low":85,"better_high":88,"stop":70,"do_not_chase":120,"breakout":110},
        "breakdown":{"Fundamentals":7},
        "fundamental_confidence":"high",
        "decision_confidence":"high",
        "previous_snapshot":{"breakdown":{"Fundamentals":14}},
    }
    position={"shares":6,"avg_cost":110,"account":"Avanza Screenshot"}
    action,reason=position_action(result,100,position)
    assert action == "REDUCE"
    assert "deteriorated" in reason.lower() or "thesis-breaking" in reason.lower()
    plan=position_action_plan(action,result,100,position)
    assert plan["suggested_shares"] == 3
    assert plan["remaining_shares"] == 3

def test_technical_stop_break_alone_does_not_auto_exit():
    result={
        "deterministic_score":70,
        "news":{"label":"Neutral","material_events":0,"high_negative_events":0,"items":[]},
        "technicals":{"ema20":105,"rsi":35},
        "levels":{"buy_low":90,"buy_high":95,"better_low":85,"better_high":88,"stop":101,"do_not_chase":120,"breakout":110},
        "breakdown":{"Fundamentals":14},
        "fundamental_confidence":"high",
        "decision_confidence":"high",
    }
    action,reason=position_action(result,100,{"shares":6,"avg_cost":110,"account":"Avanza Screenshot"})
    assert action == "HOLD — THESIS REVIEW"
    assert "technical" in reason.lower()


def test_analyst_score_can_use_recommendation_counts_without_target():
    f={"strongBuy":10,"buy":8,"hold":2,"sell":0,"strongSell":0}
    score,reasons,upside=analyst_score(f,100)
    assert score is not None and score > 75
    assert upside is None
    assert any("Recommendation mix" in r for r in reasons)


def test_primary_buy_zone_moderate_score_can_consider_buying_now():
    result={
        "deterministic_score":68,
        "news":{"label":"Neutral","material_events":0,"high_negative_events":0},
        "technicals":{"ema20":98,"rsi":54,"relative_volume":1.0,"change20_pct":1.0},
        "levels":{"buy_low":95,"buy_high":100,"better_low":88,"better_high":92,"stop":80,"do_not_chase":120,"breakout":110},
        "breakdown":{"Fundamentals":14},
        "fundamental_confidence":"high",
        "decision_confidence":"high",
    }
    action,reason=position_action(result,97,None)
    assert action == "CONSIDER BUYING NOW"
    assert "Primary buy zone reached" in reason


def test_value_corridor_does_not_revert_to_wait_for_buy_zone():
    result={
        "deterministic_score":70,
        "news":{"label":"Neutral","material_events":0,"high_negative_events":0},
        "technicals":{"ema20":96,"rsi":52,"relative_volume":1.0,"change20_pct":0.5},
        "levels":{"buy_low":95,"buy_high":100,"better_low":85,"better_high":90,"stop":75,"do_not_chase":120,"breakout":110},
        "breakdown":{"Fundamentals":14},
        "fundamental_confidence":"high",
        "decision_confidence":"high",
    }
    action,reason=position_action(result,93,None)
    assert action == "CONSIDER STARTER BUY"
    assert "below the primary buy zone" in reason


def test_value_corridor_waits_for_better_buy_when_falling():
    result={
        "deterministic_score":72,
        "news":{"label":"Neutral","material_events":0,"high_negative_events":0},
        "technicals":{"ema20":98,"rsi":45,"relative_volume":0.6,"change20_pct":-5.0},
        "levels":{"buy_low":95,"buy_high":100,"better_low":85,"better_high":90,"stop":75,"do_not_chase":120,"breakout":110},
        "breakdown":{"Fundamentals":14},
        "fundamental_confidence":"high",
        "decision_confidence":"high",
    }
    action,reason=position_action(result,93,None)
    assert action == "WAIT FOR BETTER BUY"
    assert "85.00" in reason and "90.00" in reason


def test_better_buy_zone_mild_weakness_does_not_force_wait():
    """A Better Buy zone is expected to coincide with some weakness; one flag should stage, not veto."""
    result={
        "deterministic_score":72,
        "news":{"label":"Neutral","material_events":0,"high_negative_events":0},
        "technicals":{"ema20":71.0,"rsi":46,"relative_volume":0.8,"change20_pct":-3.0},
        "levels":{"buy_low":71.14,"buy_high":72.31,"better_low":69.04,"better_high":70.12,"stop":67.87,"do_not_chase":80.80,"breakout":79.00},
        "breakdown":{"Fundamentals":15},
        "fundamental_confidence":"high",
        "decision_confidence":"high",
    }
    action,reason=position_action(result,69.62,None)
    assert action in {"CONSIDER STARTER BUY","CONSIDER BUYING NOW"}
    assert "Better-buy zone reached" in reason


def test_better_buy_zone_strong_converging_weakness_can_still_wait():
    result={
        "deterministic_score":74,
        "news":{"label":"Neutral","material_events":0,"high_negative_events":0},
        "technicals":{"ema20":73.0,"rsi":36,"relative_volume":1.7,"change20_pct":-8.0},
        "levels":{"buy_low":71.14,"buy_high":72.31,"better_low":69.04,"better_high":70.12,"stop":67.87,"do_not_chase":80.80,"breakout":79.00},
        "breakdown":{"Fundamentals":15},
        "fundamental_confidence":"high",
        "decision_confidence":"high",
    }
    action,reason=position_action(result,69.62,None)
    assert action == "WAIT MORE"
    assert "falling-knife" in reason
