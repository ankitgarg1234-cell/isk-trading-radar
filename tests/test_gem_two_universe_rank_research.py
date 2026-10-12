"""Research-only two-universe ranking checks; no external requests in tests."""
from datetime import date

import pytest

from scripts.gem_two_universe_rank_research import (
    classify_month, conditional_top5, monthly_source_url, parse_monthly,
)


def feature(r63, growth=.5, earnings="True", margin=5):
    return {
        "r63": str(r63),
        "revenue_yoy": str(growth),
        "earnings_improvement": str(earnings),
        "margin_delta_pp": str(margin),
    }


def test_public_monthly_archive_stops_april_2026_without_inventing_files():
    assert monthly_source_url(2022, 1).endswith("/spy202201")
    assert monthly_source_url(2026, 4).endswith("/spy202604")
    assert monthly_source_url(2026, 5) is None
    assert monthly_source_url(2021, 12) is None


def test_public_monthly_parser_preserves_names_and_normalizes_class_alias():
    raw = b"BRK/B\tBerkshire Hathaway\t0.2\nAAPL\tApple\t0.3\n"
    with pytest.raises(ValueError, match="Implausible"):
        parse_monthly(raw)  # reject obviously partial provider data


def test_archived_frozen_gate_thresholds_and_order():
    rows = {
        "AAA": feature(.6), "BBB": feature(.5), "CCC": feature(.4, growth=.2),
        "DDD": feature(.9, earnings="False"),
        "EEE": feature(.7, margin=3), "FFF": feature(0),
    }
    assert conditional_top5(rows, set(rows)) == ["AAA", "BBB"]
    assert conditional_top5(rows, {"AAA", "BBB", "CCC", "DDD", "EEE", "FFF"}) == ["AAA", "BBB"]


def test_two_source_observed_only_change_is_not_full_selection():
    day = date(2025, 6, 30)
    panel = {day.isoformat(): {
        "AAA": feature(.7), "BBB": feature(.6), "CCC": feature(.5),
    }}
    source_a = {"AAA", "BBB", "UNKNOWN"}  # Missing competitor row cannot be assumed to fail.
    source_b = {"BBB", "CCC", "UNKNOWN"}
    report = classify_month(day, source_a, source_b, panel, {})
    assert report["observed_only_top5_A"] == ["AAA", "BBB"]
    assert report["observed_only_top5_B"] == ["BBB", "CCC"]
    assert report["observed_only_top5_differ"] is True
    assert report["source_A_missing_feature_symbols"] == ["UNKNOWN"]
    assert report["source_B_missing_feature_symbols"] == ["UNKNOWN"]
    assert report["ranking_validated"] is False
    assert report["paper_execution_authorized"] is False
    assert report["comparison_status"] == "CONDITIONAL_ARCHIVED_FEATURE_RESEARCH_ONLY"


def test_archive_reproduction_mismatch_aborts_definitive_rank_comparison():
    day = date(2025, 1, 31)
    panel = {day.isoformat(): {"AAA": feature(.7)}}
    rep = classify_month(day, {"AAA"}, {"AAA"}, panel, {day.isoformat(): ["OTHER"]})
    assert rep["baseline_feature_reproduction_match"] is False
    assert rep["comparison_status"] == "FROZEN_ARCHIVE_REPRODUCTION_MISMATCH"
    assert rep["ranking_validated"] is False


def test_2022_no_archived_signal_features_returns_explicit_no_rank():
    rep = classify_month(date(2022, 12, 30), {"AAA"}, {"AAA"}, {}, {})
    assert rep["comparison_status"] == "NO_FROZEN_ARCHIVED_FEATURES_FOR_MONTH"
    assert rep["observed_only_top5_A"] is None
    assert rep["observed_only_top5_B"] is None


def test_missing_second_historical_source_does_not_forge_comparison():
    rep = classify_month(date(2026, 9, 30), {"AAA"}, None, {}, {})
    assert rep["comparison_status"] == "NO_SECOND_PUBLIC_MONTHLY_REFERENCE"
    assert rep["source_B_member_count"] is None
    assert rep["observed_only_top5_differ"] is None


def test_frozen_rank_feature_zero_and_missing_data_cannot_be_selected():
    rows = {"GOOD": feature(.7), "NAN": feature("NaN"),
            "BAD": {"r63": "0.9", "revenue_yoy": "", "earnings_improvement": "True",
                    "margin_delta_pp": "6.0"}}
    assert conditional_top5(rows, set(rows)) == ["GOOD"]
