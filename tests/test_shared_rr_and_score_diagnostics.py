import copy

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.analysis_engine import (score_bundle, calibrated_score_components, risk_reward_score,
                                 DETERMINISTIC_WEIGHTS, recalibrate_snapshot, SCORING_VERSION)
from app.portfolio_engine import MIN_ENTRY_RISK_REWARD, entry_attention_signal, build_optimizer_plan
from app.scanner import _attention_buy_signal
from app.score_band_experiment import entry_check, experiment_spec
from app.score_diagnostics import scan_score_diagnostics
from tests.test_portfolio_engine import sample_analysis
from tests.test_score_band_experiment import observation
from tests.helpers import bundle


@pytest.mark.parametrize("rr,okay", [(0.39, False), (0.4, True), (0.5, True), (1.99, True), (2, True)])
def test_dashboard_alerts_and_paper_share_rr_boundary(rr, okay):
    a = {**sample_analysis(), **observation(score=80, target=100 + 10 * rr, stop=90)}
    assert (entry_attention_signal(a) is not None) == okay
    assert (_attention_buy_signal(a)[0] is not None) == okay
    plan = build_optimizer_plan({"TEST": a})
    assert bool(plan["visible"]) == okay
    paper = observation(score=80, target=100 + 10 * rr, stop=90)
    assert entry_check(paper)[0] == okay
    assert plan["min_entry_risk_reward"] == experiment_spec()["min_rr"] == MIN_ENTRY_RISK_REWARD == 0.4


def test_lower_rr_floor_does_not_change_scores_or_allow_sub_70_paper_entries():
    a = observation(score=69.9, target=104, stop=90)
    before = copy.deepcopy(a)
    assert entry_check(a)[1] == "deterministic_below_70_or_invalid"
    assert a == before


def test_dashboard_renders_shared_floor():
    response = TestClient(app).get("/")
    assert response.status_code == 200
    assert "R/R ≥ 0.4x" in response.text
    assert "R/R ≥ 2.0x" not in response.text


def test_diagnostics_keep_only_five_best_and_count_inputs_without_mutation():
    rows = [dict(sample_analysis(), symbol=f"S{i}", deterministic_score=40 + i * 10)
            for i in range(7)]
    rows[0]["fundamentals"] = {"forwardPE": 25, "targetMeanPrice": 130, "marketCap": 1e9}
    before = copy.deepcopy(rows)
    d = scan_score_diagnostics(rows)
    assert d["maximum_score"] == 100
    assert d["score_at_least_70"] == 4
    assert sum(d["score_bins"].values()) == 7
    assert len(d["top_candidates"]) == 5
    assert [row["symbol"] for row in d["top_candidates"]] == ["S6", "S5", "S4", "S3", "S2"]
    assert d["missing_inputs"] == {"valuation_pe": 6, "consensus_price_target": 6, "market_cap": 6}
    assert rows == before


def test_diagnostics_distinguish_invalid_scores_and_empty_cycle():
    rows = [{"symbol": str(i), "deterministic_score": value}
            for i, value in enumerate([None, float("nan"), float("inf"), -1, 101, "bad"])]
    d = scan_score_diagnostics(rows)
    assert d["invalid_scores"] == 6
    assert d["maximum_score"] is None
    assert d["score_at_least_70"] == 0
    assert scan_score_diagnostics([])["analyzed"] == 0


def test_real_scoring_can_exceed_70_with_supported_inputs():
    result = score_bundle(bundle())
    assert result["deterministic_score"] > 70
    assert result["lane_qualified"] is True
    # Raw component points stay auditable at their original maxima; calibrated
    # contributions are what sum to the deterministic 100-point conviction.
    assert abs(sum(result["score_contributions"].values()) - result["deterministic_score"]) <= 0.4


def test_calibration_weights_remain_a_100_point_model():
    assert sum(DETERMINISTIC_WEIGHTS.values()) == 100


@pytest.mark.parametrize("rr,points", [(0,0),(0.2,2),(0.4,4),(1,6),(2,8),(3,10),(5,10)])
def test_rr_calibration_matches_entry_economics(rr, points):
    assert risk_reward_score(rr) == pytest.approx(points)


def test_v21_recalibrates_known_high_quality_neutral_setup_to_70_without_relaxing_gates():
    # Replays the documented ANET component vector from the v19 production RCA.
    # The old linear scale produced ~61.8 despite 20/20 fundamentals and 83.4
    # analyst support. 0.33x R/R still fails the separate 0.4x entry gate, but
    # the deterministic quality/setup score is no longer structurally sub-70.
    raw = {
        "Fundamentals":20, "Catalyst":5, "News":7.5, "Momentum":12,
        "Sector":9, "Valuation":3, "Analyst confirmation":4.2,
        "Risk/Reward":1.1,
    }
    weighted = calibrated_score_components(raw, 0.33)
    assert sum(weighted.values()) >= 70


def test_v20_completed_snapshot_recalibrates_locally_to_same_v21_score_and_lane():
    b=bundle()
    current=score_bundle(b)
    old={**b,**current,"scoring_version":"2026-10-06-sec-filing-coverage-v20"}
    migrated=recalibrate_snapshot(old)
    assert migrated is not None
    assert migrated["scoring_version"] == SCORING_VERSION
    assert migrated["recalibrated_from_scoring_version"] == "2026-10-06-sec-filing-coverage-v20"
    assert migrated["deterministic_score"] == pytest.approx(current["deterministic_score"], abs=0.1)
    assert migrated["lane"] == current["lane"]
    assert migrated["lane_qualified"] == current["lane_qualified"]


def test_v21_does_not_promote_merely_minimum_quality_neutral_setup():
    raw = {
        "Fundamentals":14, "Catalyst":5, "News":7.5, "Momentum":9,
        "Sector":5, "Valuation":5, "Analyst confirmation":3.75,
        "Risk/Reward":1.33,
    }
    weighted = calibrated_score_components(raw, 0.4)
    assert sum(weighted.values()) < 70
