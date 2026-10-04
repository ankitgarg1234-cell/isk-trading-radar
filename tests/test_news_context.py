from datetime import datetime, timezone
from dataclasses import replace

import pytest

from app.analysis_engine import news_analysis, legacy_news_analysis, score_bundle, LEGACY_SCORING_VERSION
from .helpers import bundle

NOW = "2026-10-04T18:45:00+00:00"
STAMP = datetime.fromisoformat(NOW).timestamp()


def article(title, **fields):
    return {"title": title, "publisher": "Reuters", "published": STAMP - 60, **fields}


def assess(*articles, symbol="CRDO", company_name="Credo Technology Group Holding Ltd"):
    return news_analysis(list(articles), symbol=symbol, company_name=company_name, asof=NOW)


def test_unrelated_article_cannot_add_sentiment_or_catalysts():
    n = assess(article("Nvidia raises guidance after record earnings beat", relatedTickers=["NVDA"]))
    assert n["score"] == 7.5  # Deliberately preserve the frozen scale.
    assert n["label"] == "Unavailable"
    assert n["material_events"] == 0 and n["catalysts"] == []
    assert n["excluded_count"] == 1


def test_company_alias_and_explicit_provider_association():
    assert assess(article("Credo raises guidance"))["positive"] == 1.25
    assert assess(article("Company raises guidance", relatedTickers=["CRDO"]))["positive"] == 1.25
    assert assess(article("Company raises guidance"))["excluded_count"] == 1


def test_short_ticker_does_not_match_ordinary_word():
    n = assess(article("Company raises guidance on growth"), symbol="ON", company_name="")
    assert n["excluded_count"] == 1
    assert assess(article("ON raises guidance"), symbol="ON", company_name="")["positive"] == 1.25


@pytest.mark.parametrize("title", [
    "Could Credo be the next big AI winner?", "Should you buy CRDO?",
    "Credo expected to raise guidance", "Rumor: Credo receives FDA approval",
    "Credo does not raise guidance", "Credo fails to win contract",
    "Credo never receives FDA approval", "Credo shares surge on AI optimism",
    "Credo guidance not raised", "FDA has not approved Credo treatment",
])
def test_speculation_negation_and_generic_hype_do_not_earn_points(title):
    n = assess(article(title))
    assert n["positive"] == 0
    assert n["material_events"] == 0


def test_upgrade_is_one_event_not_two_overlapping_substrings():
    n = assess(article("CRDO upgraded by broker"))
    assert n["positive"] == 1.25
    assert len(n["items"][0]["matched_events"]) == 1
    assert legacy_news_analysis([article("CRDO upgraded by broker")])["positive"] == 2.5


def test_mixed_report_preserves_negative_and_removes_bullish_bonus():
    n = assess(article("Credo reports record revenue but cuts guidance"))
    assert n["positive"] == 0 and n["negative"] == 1.25
    assert n["items"][0]["sentiment"] == "mixed"
    assert n["high_negative_events"] == 1
    assert n["score"] < 7.5


def test_profit_growth_disappoints_is_not_bullish():
    n = assess(article("Credo profit growth disappoints investors"))
    assert n["positive"] == 0 and n["negative"] > 0


def test_other_named_company_clause_does_not_credit_target():
    n = assess(article("Nvidia raises guidance; Credo shares fall"))
    assert n["positive"] == 0


def test_duplicate_headlines_and_tracking_urls_count_once():
    one = article("Credo raises guidance", link="https://example.com/release?utm=1")
    two = article("Credo raises guidance", link="https://example.com/release?utm=2", publisher="Business Wire")
    n = assess(one, two, one)
    assert n["unique_event_count"] == 1 and n["duplicate_count"] == 2
    assert n["positive"] == 1.25
    assert n["items"][0]["coverage_count"] == 3


def test_syndicated_rephrasing_of_earnings_is_one_event():
    n = assess(article("Credo beats earnings estimates"), article("CRDO earnings beat expectations"))
    assert n["unique_event_count"] == 1 and n["positive"] == 1.25


def test_conflicting_coverage_cannot_erase_negative_event():
    n = assess(article("Credo raises guidance"), article("Credo cuts guidance"))
    assert n["unique_event_count"] == 1
    assert n["positive"] == 0 and n["negative"] == 1.25


def test_different_quarters_and_distinct_contracts_are_not_merged():
    n = assess(article("Credo Q1 earnings beat estimates"), article("Credo Q2 earnings beat estimates"))
    assert n["unique_event_count"] == 2
    n = assess(article("Credo wins contract with Alphabet"), article("Credo secures multiyear contract with Microsoft"))
    assert n["unique_event_count"] == 2


def test_missing_time_does_not_enable_approximate_event_grouping():
    n = assess(article("Credo beats earnings estimates", published=None), article("CRDO earnings beat expectations", published=None))
    assert n["unique_event_count"] == 2


def test_future_news_is_excluded_and_empty_feed_is_unknown():
    n = assess(article("Credo raises guidance", published=STAMP + 60))
    assert n["items"] == [] and n["excluded_items"][0]["excluded_reason"] == "future publication timestamp"
    empty = assess()
    assert empty["coverage"] == "unavailable" and empty["label"] == "Unavailable"
    assert empty["score"] == empty["baseline_points"] == 7.5


def test_event_credit_is_capped_and_source_order_does_not_change_score():
    a = article("Credo raises guidance after record earnings beat", publisher="Business Wire")
    b = article("CRDO earnings beat estimates and raises guidance", publisher="Reuters")
    first, second = assess(a, b), assess(b, a)
    assert first["score"] == second["score"]
    assert first["positive"] <= 2.5


def test_locked_version_retains_original_score_target_and_scale():
    sample = bundle(news=[article("Unrelated upgraded stock reports record profit growth")])
    legacy = score_bundle(sample, news_model="legacy-v1")
    revised = score_bundle(sample)
    assert legacy["scoring_version"] == LEGACY_SCORING_VERSION
    assert legacy["news"]["score"] == 15
    assert revised["news"]["score"] == 7.5
    assert revised["news"]["excluded_count"] == 1
    assert legacy["breakdown"]["Fundamentals"] == revised["breakdown"]["Fundamentals"]
    assert legacy["analyst_score"] == revised["analyst_score"]


def test_provider_preserves_explicit_ticker_metadata(monkeypatch):
    from app.market import YahooMarketProvider
    provider = YahooMarketProvider()
    monkeypatch.setattr(provider, "_json", lambda *args, **kwargs: {"news": [{"title": "Results", "relatedTickers": ["CRDO"]}]})
    assert provider.news("CRDO")[0]["relatedTickers"] == ["CRDO"]


def test_scanner_passes_frozen_analysis_without_persisting_second_account(monkeypatch):
    from app.scanner import RadarService
    from app.config import settings
    from app.score_band_capture import compact_observation
    sample = bundle(news=[article("Unrelated upgraded stock reports record profit growth")])
    import app.scanner as scanner_module
    monkeypatch.setattr(scanner_module, "settings", replace(settings, score_band_trial_armed_at=NOW, strategic_capital_enabled=False))
    provider = type("Provider", (), {"bundle": lambda self, symbol: sample})()
    ai = type("AI", (), {"analyze": lambda *args: {}})()
    service = RadarService(provider=provider, ai=ai)
    saved = []
    monkeypatch.setattr(service, "persist", lambda full: saved.append(dict(full)))
    full = service.analyze_symbol("TEST")
    locked = full["_locked_trial_observation"]
    from app.analysis_engine import position_action
    frozen_result = score_bundle(sample, news_model="legacy-v1")
    position_action(frozen_result, sample["price"], None)
    expected = compact_observation({**sample, **frozen_result})
    for key in ("deterministic_score", "levels", "target_plan", "news", "scoring_version", "thesis_assessment"):
        assert locked[key] == expected[key]
    assert "_locked_trial_observation" not in saved[0]
    assert full["news_scoring_comparison"]["trial_uses_revised_news"] is False


def test_capture_fails_closed_when_revised_analysis_lacks_locked_input(monkeypatch):
    import app.score_band_capture as capture
    from app.config import settings
    monkeypatch.setattr(capture, "settings", replace(settings, score_band_trial_armed_at=NOW))
    monkeypatch.setattr(capture, "fresh_benchmark", lambda now: (None, None))
    got = []
    original = capture.advance
    def record(state, observations, *args):
        got.extend(observations)
        return original(state, observations, *args)
    monkeypatch.setattr(capture, "advance", record)
    capture.run_experiment_cycle([{"news": {"version": "headline-context-v2"}}], market_open=True,
                                 now=datetime.fromisoformat(NOW))
    assert got == []


def test_news_audit_template_renders_exclusions_and_comparison():
    from jinja2 import Environment, FileSystemLoader
    from pathlib import Path
    sample = bundle()
    result = score_bundle(sample)
    result["news_scoring_comparison"] = {"trial_deterministic_score": 90, "revised_deterministic_score": 80}
    result.update(symbol="TEST", price=100, ai_score=0, reasons=[], risks=[], sensitivity=[])
    template = Environment(loader=FileSystemLoader(Path(__file__).resolve().parents[1] / "app/templates"))
    rendered = template.get_template("analysis.html").render(d=result)
    assert "unique headline groups" in rendered and "Locked trial score: 90" in rendered


def test_multi_ticker_association_without_identified_subject_is_excluded():
    assert assess(article("Company raises guidance", relatedTickers=["CRDO", "NVDA"]))["excluded_count"] == 1


def test_repeated_release_text_on_separate_dates_is_not_one_event():
    n = assess(article("Credo raises guidance"), article("Credo raises guidance", published=STAMP - 5*86400))
    assert n["unique_event_count"] == 2


def test_capture_uses_locked_observation_and_preserves_score_version(monkeypatch):
    import app.score_band_capture as capture
    from app.config import settings
    from .test_score_band_experiment import observation
    monkeypatch.setattr(capture, "settings", replace(settings, score_band_trial_armed_at=NOW))
    monkeypatch.setattr(capture, "fresh_benchmark", lambda now: (None, None))
    got = []
    original = capture.advance
    def record(state, observations, *args):
        got.extend(observations)
        return original(state, observations, *args)
    monkeypatch.setattr(capture, "advance", record)
    locked = observation(NOW)
    locked["scoring_version"] = LEGACY_SCORING_VERSION
    capture.run_experiment_cycle([{"deterministic_score": 1, "_locked_trial_observation": locked}],
                                 market_open=True, now=datetime.fromisoformat(NOW))
    assert got[0]["deterministic_score"] == locked["deterministic_score"]
    assert got[0]["scoring_version"] == LEGACY_SCORING_VERSION


def test_compact_dashboard_retains_the_news_audit_without_heavy_price_history():
    from app.scanner import _compact_payload
    news = assess(*[article(f"Credo Q1 earnings beat estimates", published=STAMP-i*5*86400) for i in range(10)])
    compact = _compact_payload({"news": news, "history": [{"close": 100}] * 260})
    assert len(compact["news"]["items"]) == 10
    assert "history" not in compact


def test_mixed_group_keeps_adverse_source_for_thesis_assessment():
    from app.analysis_engine import thesis_assessment
    news = assess(article("Credo raises guidance"), article("Credo cuts guidance"))
    assert news["items"][0]["title"] == "Credo raises guidance"
    assert thesis_assessment({"news": news})["invalidated"] is True
