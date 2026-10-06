"""Prevent contradictory fiscal sources and invalid analyst evidence."""
import pytest
import json
from pathlib import Path

from app.analysis_engine import analyst_score, fundamental_score
from app.market import YahooMarketProvider, SECFundamentalsProvider, sic_to_sector, SECTOR_ETF


@pytest.mark.parametrize("quarter", [.3, .05, None])
def test_sec_integrity_controls_quarter_and_its_provenance(monkeypatch, quarter):
    class SEC:
        def fundamentals(self, symbol):
            return {"_fundamental_integrity": "matched-fiscal-periods-v1",
                    "_status": "available", "revenueGrowth": .05,
                    "quarterlyRevenueGrowth": quarter,
                    "_quarterly_period": "2026-06-30", "_quarterly_source": "SEC EDGAR/XBRL",
                    "_quarterly_method": "reported quarter",
                    "_quarterly_status": "available" if quarter is not None else "no comparable latest quarter"}
    class Analyst:
        def recommendations(self, symbol):
            return {}
    provider = YahooMarketProvider(sec_provider=SEC(), analyst_provider=Analyst())
    monkeypatch.setattr(provider, "yahoo_fundamentals", lambda symbol: {
        "revenueGrowth": .2, "earningsGrowth": .2, "grossMargins": .4,
        "quarterlyRevenueGrowth": .15})
    result = provider.fundamentals("TEST")
    assert result["quarterlyRevenueGrowth"] == quarter
    assert result["_quarterly_period"] == "2026-06-30"
    assert result["_quarterly_source"] == "SEC EDGAR/XBRL"
    # Known annual growth earns 2; only the verified quarter can add its bonus.
    assert fundamental_score(result)[0] == 2 + (2 if quarter == .3 else 0)


@pytest.mark.parametrize("bad", ["bad", "nan", float("inf"), -1, 0, 6])
def test_invalid_mean_does_not_hide_valid_recommendation_counts(bad):
    score, _, _ = analyst_score({"recommendationMean": bad, "strongBuy": 10}, 100)
    assert score == 100


@pytest.mark.parametrize("field,bad", [
    ("recommendationMean", "nan"), ("recommendationMean", 6),
    ("targetMeanPrice", float("nan")), ("targetMeanPrice", float("inf")),
    ("targetMeanPrice", -100), ("strongBuy", -1),
    ("strongBuy", .5), ("strongBuy", "nan"),
])
def test_invalid_evidence_cannot_create_an_analyst_score(field, bad):
    assert analyst_score({field: bad}, 100) == (None, [
        "Analyst data unavailable from current provider (unavailable)"], None)


def test_malformed_bucket_invalidates_whole_mix():
    assert analyst_score({"strongBuy": -1, "buy": 2}, 100)[0] is None


@pytest.mark.parametrize("price", [0, -1, float("nan"), float("inf")])
def test_invalid_price_cannot_create_target_upside(price):
    assert analyst_score({"targetMeanPrice": 150, "recommendationMean": 2}, price) == (
        75, ["Recommendation mean 2.00 (1=strong buy, 5=sell)"], None)


def test_valid_provider_values_preserve_existing_weights():
    assert analyst_score({"targetMeanPrice": 120, "recommendationMean": 2}, 100)[0] == 82.5
    assert analyst_score({"strongBuy": 2, "buy": 3, "hold": 5}, 100)[0] == 69


def test_captured_wdc_sec_quarter_survives_provider_merge(monkeypatch):
    case = json.loads((Path(__file__).parent / "fixtures/fundamental_source_cases.json").read_text())["WDC"]
    sec = SECFundamentalsProvider()
    monkeypatch.setattr(sec, "resolve", lambda s: dict(cik=case["cik"], cik10=f'{case["cik"]:010d}', title=s))
    monkeypatch.setattr(sec, "_json", lambda u: case["submissions"] if "/submissions/" in u else case["facts"])
    class Analyst:
        def recommendations(self, symbol):
            return {}
    provider = YahooMarketProvider(sec_provider=sec, analyst_provider=Analyst())
    monkeypatch.setattr(provider, "yahoo_fundamentals", lambda s: {
        "revenueGrowth": .1, "earningsGrowth": .1, "grossMargins": .3,
        "quarterlyRevenueGrowth": .05})
    merged = provider.fundamentals("WDC")
    assert merged["quarterlyRevenueGrowth"] == pytest.approx(3747 / 2605 - 1)
    assert fundamental_score(merged)[0] == 19


@pytest.mark.parametrize("code,description,sector,benchmark", [
    # SEC SIC code-list classifications; AAON's description captured live.
    (3585, "Air-Cond & Warm Air Heatg Equip & Comm & Indl Refrig Equip", "Industrials", "XLI"),
    (3580, "REFRIGERATION & SERVICE INDUSTRY MACHINERY", "Industrials", "XLI"),
    (3590, "MISC INDUSTRIAL & COMMERCIAL MACHINERY & EQUIPMENT", "Industrials", "XLI"),
    (6500, "", "Real Estate", "XLRE"),
    (6512, "OPERATORS OF NONRESIDENTIAL BUILDINGS", "Real Estate", "XLRE"),
    (6798, "", "Real Estate", "XLRE"),
    (6022, "", "Financial Services", "XLF"),
    (6321, "ACCIDENT & HEALTH INSURANCE", "Financial Services", "XLF"),
    (6324, "HOSPITAL & MEDICAL SERVICE PLANS", "Financial Services", "XLF"),
    (6799, "INVESTORS, NEC", "Financial Services", "XLF"),
    (3571, "", "Technology", "XLK"),
    (8062, "GENERAL MEDICAL & SURGICAL HOSPITALS", "Healthcare", "XLV"),
])
def test_sector_range_gaps_and_specific_codes_choose_existing_benchmarks(code, description, sector, benchmark):
    assert sic_to_sector(code, description) == sector
    assert SECTOR_ETF[sic_to_sector(code, description)] == benchmark
