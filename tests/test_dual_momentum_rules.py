from __future__ import annotations

import math

from dual_momentum.portfolio import build_portfolio_plan
from dual_momentum.rules import (
    FundamentalStatus,
    MomentumSignal,
    advance_stop,
    ema_seeded,
    evaluate_fundamentals,
    initial_stop,
    momentum_score,
    target_weights,
)


def _signal(symbol: str, atr_pct: float) -> MomentumSignal:
    return MomentumSignal(
        symbol=symbol,
        score=0.20,
        r63=0.10,
        r126=0.20,
        r252=0.30,
        adv63=1_000_000,
        atr14=atr_pct * 100,
        price=100,
        atr_pct=atr_pct,
    )


def test_ema200_uses_arithmetic_seed():
    values = [float(i) for i in range(1, 202)]
    ema = ema_seeded(values)
    assert ema[198] is None
    assert ema[199] == 100.5
    expected = (2 / 201) * 201 + (199 / 201) * 100.5
    assert math.isclose(ema[200], expected, rel_tol=1e-12)


def test_momentum_baseline_and_lag_use_different_endpoints():
    values = [100 + i for i in range(300)]
    baseline, _ = momentum_score(values, lagged=False)
    lagged, _ = momentum_score(values, lagged=True)
    assert baseline > 0
    assert lagged > 0
    assert baseline != lagged


def test_fundamentals_require_nonnegative_growth_and_positive_margin():
    check = evaluate_fundamentals(
        [10, 10, 10, 10, 11, 11, 11, 11],
        [5, 5, 5, 5],
    )
    assert check.status == FundamentalStatus.PASS
    assert math.isclose(check.revenue_growth_ttm, 0.10, rel_tol=1e-12)
    assert math.isclose(check.gross_margin_ttm, 20 / 44, rel_tol=1e-12)

    fail = evaluate_fundamentals(
        [11, 11, 11, 11, 10, 10, 10, 10],
        [5, 5, 5, 5],
    )
    assert fail.status == FundamentalStatus.FAIL

    review = evaluate_fundamentals([10, 10, 10], None)
    assert review.status == FundamentalStatus.REVIEW


def test_inverse_atr_sizing_preserves_n_over_20_equity_exposure():
    weights, cash = target_weights([_signal("AAA", 0.02), _signal("BBB", 0.02)])
    assert math.isclose(sum(weights.values()), 0.10, rel_tol=1e-12)
    assert math.isclose(weights["AAA"], 0.05, rel_tol=1e-12)
    assert math.isclose(weights["BBB"], 0.05, rel_tol=1e-12)
    assert math.isclose(cash, 0.90, rel_tol=1e-12)


def test_lower_atr_gets_larger_weight():
    weights, _ = target_weights([_signal("LOW", 0.01), _signal("HIGH", 0.02)])
    assert weights["LOW"] > weights["HIGH"]


def test_stop_ratchets_and_never_loosens():
    state = initial_stop(100, 5)
    assert state.peak == 100
    assert state.stop == 85

    state = advance_stop(state, 110, 6)
    assert state.peak == 110
    assert state.stop == 92

    state2 = advance_stop(state, 100, 10)
    assert state2.peak == 110
    assert state2.stop == 92
    assert not state2.breached

    breached = advance_stop(state2, 92, 5)
    assert breached.breached
    assert breached.stop == 92


def _candidate(rank: int, symbol: str, status: str = "PASS", atr_pct: float = 0.02) -> dict:
    return {
        "rank": rank,
        "symbol": symbol,
        "price": 100.0,
        "score": 0.25,
        "atr14": atr_pct * 100.0,
        "atr_pct": atr_pct,
        "fundamental_status": status,
        "sector": "Technology",
        "security_id": symbol,
    }


def test_fundamental_failures_do_not_compress_raw_momentum_ranks():
    snapshot = {
        "regime": {"state": "BULL"},
        "candidates": [
            _candidate(1, "FAIL", "FAIL"),
            _candidate(2, "PASS2", "PASS"),
            _candidate(20, "PASS20", "PASS"),
            _candidate(21, "PASS21", "PASS"),
        ],
        "holding_checks": {},
    }
    plan = build_portfolio_plan(snapshot, [], 100_000.0)
    assert plan["selected"] == ["PASS2", "PASS20"]
    assert "PASS21" not in plan["selected"]
    assert math.isclose(plan["target_equity_exposure"], 0.10, rel_tol=1e-12)


def test_review_incumbent_is_retained_but_cannot_be_added():
    snapshot = {
        "regime": {"state": "BULL"},
        "candidates": [_candidate(10, "KEEP", "REVIEW")],
        "holding_checks": {
            "KEEP": {
                "rank": 10,
                "in_index": True,
                "membership_exit": False,
                "momentum_positive": True,
                "score": 0.2,
                "price": 100.0,
                "atr14": 2.0,
                "atr_pct": 0.02,
                "fundamental_status": "REVIEW",
                "fundamental_reason": "Required fundamentals unavailable",
                "sector": "Technology",
                "security_id": "KEEP",
            }
        },
    }
    positions = [{"symbol": "KEEP", "shares": 1, "avg_cost": 100.0, "pending_stop_exit": False}]
    plan = build_portfolio_plan(snapshot, positions, 9_900.0)
    assert plan["selected"] == ["KEEP"]
    assert "KEEP" in plan["review_frozen"]
    assert not any(o["side"] == "BUY" and o["symbol"] == "KEEP" for o in plan["orders"])


def test_rank_exit_still_applies_when_fundamentals_are_under_review():
    snapshot = {
        "regime": {"state": "BULL"},
        "candidates": [],
        "holding_checks": {
            "OLD": {
                "rank": 36,
                "in_index": True,
                "membership_exit": False,
                "momentum_positive": True,
                "price": 100.0,
                "atr14": 2.0,
                "atr_pct": 0.02,
                "fundamental_status": "REVIEW",
                "fundamental_reason": "Required fundamentals unavailable",
            }
        },
    }
    positions = [{"symbol": "OLD", "shares": 5, "avg_cost": 90.0, "pending_stop_exit": False}]
    plan = build_portfolio_plan(snapshot, positions, 0.0)
    assert any(o["side"] == "SELL" and o["symbol"] == "OLD" and o["shares"] == 5 for o in plan["orders"])


def test_membership_exit_overrides_review_retention():
    snapshot = {
        "regime": {"state": "BULL"},
        "candidates": [],
        "holding_checks": {
            "REMOVED": {
                "rank": None,
                "in_index": False,
                "membership_exit": True,
                "momentum_positive": None,
                "fundamental_status": "REVIEW",
                "reason": "Security is absent from the S&P 500 membership feed",
            }
        },
    }
    positions = [{"symbol": "REMOVED", "shares": 3, "avg_cost": 80.0, "pending_stop_exit": False}]
    plan = build_portfolio_plan(snapshot, positions, 0.0)
    assert any(o["side"] == "SELL" and o["symbol"] == "REMOVED" for o in plan["orders"])


def test_reserved_midcycle_vacancy_is_not_refilled_from_same_snapshot():
    snapshot = {
        "regime": {"state": "BULL"},
        "candidates": [
            _candidate(1, "AAA", "PASS"),
            _candidate(2, "BBB", "PASS"),
        ],
        "holding_checks": {},
    }
    plan = build_portfolio_plan(snapshot, [], 100_000.0, reserved_slots=1)
    assert len(plan["selected"]) == 2  # 19 slots remain available; both can be selected

    many = [_candidate(i, f"S{i:02d}", "PASS") for i in range(1, 21)]
    plan2 = build_portfolio_plan(
        {"regime": {"state": "BULL"}, "candidates": many, "holding_checks": {}},
        [],
        100_000.0,
        reserved_slots=1,
    )
    assert len(plan2["selected"]) == 19
    assert "S20" not in plan2["selected"]
    assert plan2["reserved_slots"] == 1
