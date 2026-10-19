"""Deterministic offline parity diagnostics; no network or broker."""
from gem_data.archive_ranking_parity import audit


def case(ticker, r63, growth, earnings, margin):
    return {"date": "2025-01-31", "ticker": ticker, "r63": str(r63),
            "revenue_yoy": str(growth), "earnings_improvement": str(earnings),
            "margin_delta_pp": str(margin), "G": str(growth > .2), "E": str(earnings)}


def test_negative_momentum_is_visible_strategy_drift():
    details, monthly = audit([case("AAA", -.1, .5, True, 5),
                              case("BBB", .2, .6, True, 6)])
    assert next(r for r in details if r["ticker"] == "AAA")["reason"] == "FROZEN_GATE_DIFFERENCE"
    assert monthly[0]["gate_differences"] == 1
    assert monthly[0]["top5_matches"] is False


def test_identical_positive_gates_match():
    details, monthly = audit([case("AAA", .3, .5, True, 5),
                              case("BBB", .2, .6, True, 6)])
    assert all(r["reason"] == "MATCH_ARCHIVED_FEATURES" for r in details)
    assert monthly[0]["top5_matches"] is True


def test_unknown_evidence_not_misclassified_as_proven_drift():
    row = case("AAA", .1, .5, True, 5)
    row["revenue_yoy"] = ""
    details, monthly = audit([row])
    assert details[0]["reason"] == "INSUFFICIENT_ARCHIVED_FEATURE_EVIDENCE"
    assert monthly[0]["missing_feature_evidence"] == 1
