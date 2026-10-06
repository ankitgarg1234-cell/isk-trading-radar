from __future__ import annotations

import math

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
