"""Frozen gate/rank shadow check over explicit, already-derived features.

This does not derive SEC quarter facts, momentum, membership, or split units.
Missing/unresolved features fail the entire shadow check instead of shrinking
the universe and silently promoting a replacement candidate.
"""
from dataclasses import dataclass
import math
from .common import ControlError, positive_integer


@dataclass(frozen=True)
class FeatureRow:
    ticker: str
    security_id: str
    prior_price_observations: int
    positive_bars: bool
    nominal_close: float
    adv20: float
    r63: float
    revenue_yoy: float
    earnings_improvement: bool
    margin_delta_pp: float


def select_frozen_features(rows, *, expected_member_tickers):
    """Replicate original sorted-member input, strict GEM gates and stable r63.

    expected_member_tickers is the full independently certified signal-date
    universe. It is not inferred from the rows. Callers must separately prove
    quarter/freshness lineage and temporal provenance through pre-trade QA.
    """
    expected = list(expected_member_tickers)
    if not expected or len(expected) != len(set(expected)):
        raise ControlError("Historical universe missing or duplicated")
    if any(not isinstance(symbol, str) or not symbol for symbol in expected):
        raise ControlError("Invalid historical-universe symbol")
    rows = list(rows)
    if any(not isinstance(row, FeatureRow) for row in rows):
        raise ControlError("Unexpected feature schema")
    if len({row.ticker for row in rows}) != len(rows):
        raise ControlError("Duplicate feature ticker")
    if any(not isinstance(row.ticker, str) or not row.ticker for row in rows):
        raise ControlError("Invalid feature ticker")
    if set(row.ticker for row in rows) != set(expected):
        raise ControlError("Incomplete historical-universe coverage")
    if len({row.security_id for row in rows}) != len(rows) or any(not row.security_id for row in rows):
        raise ControlError("Unresolved or duplicate security identity")
    eligible = []
    for row in sorted(rows, key=lambda item: item.ticker):
        positive_integer(row.prior_price_observations, allow_zero=True)
        if type(row.positive_bars) is not bool or type(row.earnings_improvement) is not bool:
            raise ControlError("Unresolved eligibility/earnings flag")
        for value in (row.nominal_close, row.adv20, row.r63, row.revenue_yoy, row.margin_delta_pp):
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ControlError("Unresolved/nonfinite contemporaneous feature")
        if (row.prior_price_observations >= 126 and row.positive_bars
                and row.nominal_close >= 5 and row.adv20 >= 10_000_000
                and row.r63 > 0 and row.revenue_yoy > .2
                and row.earnings_improvement and row.margin_delta_pp > 3):
            eligible.append(row)
    ranked = sorted(eligible, key=lambda row: row.r63, reverse=True)
    return {"ranked_tickers": [row.ticker for row in ranked],
            "selected_tickers": [row.ticker for row in ranked[:5]],
            "slot_weight": "0.2", "unfilled_slots": max(0, 5 - len(ranked))}
