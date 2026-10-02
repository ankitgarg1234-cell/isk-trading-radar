from copy import deepcopy
from datetime import datetime, timezone

from app.analysis_engine import position_action, position_action_plan


def analysis():
    return {
        "deterministic_score": 82,
        "news": {"label": "Neutral", "material_events": 0, "high_negative_events": 0, "items": []},
        "technicals": {"ema20": 118, "rsi": 56, "relative_volume": 1, "change20_pct": 4},
        "levels": {"buy_low": 105, "buy_high": 110, "better_low": 100, "better_high": 103,
                   "stop": 90, "target": 125, "do_not_chase": 145, "breakout": 130},
        "risk_reward": 2.5, "target_plan": {"stretch_target": 135},
        "holding_horizon": {"max_days": 90}, "fundamental_confidence": "high",
        "breakdown": {"Fundamentals": 18},
    }


def position(shares=8):
    return {"shares": shares, "original_shares": shares, "avg_cost": 100, "account": "Paper",
            "whole_shares": True, "entry_target": 120, "entry_stretch_target": 135, "entry_stop": 90,
            "entry_horizon_days": 90, "profit_taken_shares": 0, "profit_taken_stages": []}


def test_fixed_base_and_stretch_do_not_erode_runner_on_repeated_scans():
    p = position()
    a = analysis()
    action, _ = position_action(a, 121, p)
    plan = position_action_plan(action, a, 121, p)
    assert plan["suggested_shares"] == 2
    p.update(shares=6, profit_taken_shares=2, profit_taken_stages=["BASE"])
    for _ in range(5):
        assert position_action(a, 121, p)[0].startswith("HOLD")
        assert "profit_take_stage" not in a
    action, _ = position_action(a, 136, p)
    plan = position_action_plan(action, a, 136, p)
    assert plan["suggested_shares"] == 2
    p.update(shares=4, profit_taken_shares=4, profit_taken_stages=["BASE", "STRETCH"])
    assert position_action(a, 136, p)[0].startswith("HOLD")


def test_gap_to_stretch_completes_both_targets_once():
    a = analysis()
    p = position()
    action, _ = position_action(a, 136, p)
    plan = position_action_plan(action, a, 136, p)
    assert plan["suggested_shares"] == 4
    assert plan["profit_take_complete_stages"] == ["BASE", "STRETCH"]


def test_whole_share_tranches_are_cumulative_and_preserve_runner():
    a = analysis()
    p = position(6)
    action, _ = position_action(a, 121, p)
    assert position_action_plan(action, a, 121, p)["suggested_shares"] == 2
    p.update(shares=4, profit_taken_shares=2, profit_taken_stages=["BASE"])
    action, _ = position_action(a, 136, p)
    assert position_action_plan(action, a, 136, p)["suggested_shares"] == 1
    one = position(1)
    action, _ = position_action(a, 136, one)
    assert position_action_plan(action, a, 136, one)["suggested_shares"] == 0


def test_holding_horizon_uses_historical_decision_clock():
    a = analysis()
    a["technicals"]["ema20"] = 120
    p = position()
    p["opened_at"] = "2024-01-02T21:00:00+00:00"
    early = deepcopy(a)
    assert position_action(early, 110, p, decision_at=datetime(2024, 1, 12, 21, tzinfo=timezone.utc))[0].startswith("HOLD")
    assert early["position_plan"]["holding_days"] == 10
    late = deepcopy(a)
    assert position_action(late, 110, p, decision_at=datetime(2024, 5, 2, 20, tzinfo=timezone.utc))[0] == "TAKE PARTIAL PROFIT"
    assert late["profit_take_stage"] == "HORIZON"
