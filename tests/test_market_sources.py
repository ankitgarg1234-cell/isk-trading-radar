from app.market import SECFundamentalsProvider, YahooMarketProvider, sic_to_sector
from app.analysis_engine import score_bundle
from .helpers import bundle, strong_fundamentals


def _duration(val, start, end, form="10-K", filed="2026-02-01"):
    return {"val": val, "start": start, "end": end, "form": form, "filed": filed, "fy": int(end[:4]), "fp": "FY" if form.startswith("10-K") else "Q2"}


def _instant(val, end, form="10-K", filed="2026-02-01"):
    return {"val": val, "end": end, "form": form, "filed": filed}


def test_sic_sector_mapping_handles_software_and_healthcare():
    assert sic_to_sector(7372, "PREPACKAGED SOFTWARE") == "Technology"
    assert sic_to_sector(2834, "PHARMACEUTICAL PREPARATIONS") == "Healthcare"
    assert sic_to_sector(6022, "STATE COMMERCIAL BANKS") == "Financial Services"


def test_sec_companyfacts_produces_compatible_fundamentals(monkeypatch):
    provider = SECFundamentalsProvider(user_agent="Radar Test test@example.com")
    monkeypatch.setattr(provider, "resolve", lambda symbol: {"cik": 1234, "cik10": "0000001234", "title": "Test Co", "ticker": symbol})
    submissions = {"sic": "7372", "sicDescription": "PREPACKAGED SOFTWARE", "name": "Test Co"}
    facts = {
        "facts": {"us-gaap": {
            "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
                _duration(100, "2024-01-01", "2024-12-31", filed="2025-02-01"),
                _duration(130, "2025-01-01", "2025-12-31", filed="2026-02-01"),
                _duration(25, "2025-01-01", "2025-03-31", form="10-Q", filed="2025-05-01"),
                _duration(33, "2026-01-01", "2026-03-31", form="10-Q", filed="2026-05-01"),
            ]}},
            "NetIncomeLoss": {"units": {"USD": [
                _duration(10, "2024-01-01", "2024-12-31", filed="2025-02-01"),
                _duration(14, "2025-01-01", "2025-12-31", filed="2026-02-01"),
            ]}},
            "GrossProfit": {"units": {"USD": [_duration(78, "2025-01-01", "2025-12-31")] }},
            "OperatingIncomeLoss": {"units": {"USD": [_duration(26, "2025-01-01", "2025-12-31")] }},
            "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [_duration(18, "2025-01-01", "2025-12-31")] }},
            "StockholdersEquity": {"units": {"USD": [_instant(70, "2025-12-31")] }},
            "AssetsCurrent": {"units": {"USD": [_instant(90, "2025-12-31")] }},
            "LiabilitiesCurrent": {"units": {"USD": [_instant(45, "2025-12-31")] }},
            "LongTermDebtNoncurrent": {"units": {"USD": [_instant(14, "2025-12-31")] }},
        }}
    }

    def fake_json(url):
        return submissions if "/submissions/" in url else facts
    monkeypatch.setattr(provider, "_json", fake_json)
    out = provider.fundamentals("TEST")
    assert out["_status"] == "available"
    assert out["_source"] == "SEC EDGAR/XBRL"
    assert out["sector"] == "Technology"
    assert round(out["revenueGrowth"], 2) == 0.30
    assert round(out["earningsGrowth"], 2) == 0.40
    assert round(out["grossMargins"], 2) == 0.60
    assert round(out["operatingMargins"], 2) == 0.20
    assert round(out["returnOnEquity"], 2) == 0.20
    assert round(out["debtToEquity"], 1) == 20.0
    assert round(out["currentRatio"], 1) == 2.0
    assert out["_coverage"] >= 5


def test_sec_fallback_recovers_yahoo_fundamental_failure(monkeypatch):
    class FakeSEC:
        def fundamentals(self, symbol):
            return {
                **strong_fundamentals(), "_status": "available", "_source": "SEC EDGAR/XBRL",
                "_fundamental_period": "2025-12-31", "sic": 7372,
            }
    class FakeAnalyst:
        def recommendations(self, symbol):
            return {"strongBuy": 4, "buy": 3, "hold": 1, "sell": 0, "strongSell": 0, "_analyst_status": "available", "_analyst_source": "Finnhub recommendation trends"}

    provider = YahooMarketProvider(sec_provider=FakeSEC(), analyst_provider=FakeAnalyst())
    monkeypatch.setattr(provider, "yahoo_fundamentals", lambda symbol: {
        "_status": "unavailable (HTTPStatusError)", "_source": "Yahoo quoteSummary",
        "_analyst_status": "unavailable from Yahoo quoteSummary", "_analyst_source": "Yahoo quoteSummary",
    })
    out = provider.fundamentals("CRDO")
    assert out["_status"] == "available"
    assert out["revenueGrowth"] == strong_fundamentals()["revenueGrowth"]
    assert out["_fundamental_source"] == "SEC EDGAR/XBRL"
    assert out["_analyst_status"] == "available"
    assert out["strongBuy"] == 4


def test_analyst_is_optional_for_high_decision_confidence():
    f = strong_fundamentals()
    for k in ("targetMeanPrice", "targetHighPrice", "targetLowPrice", "recommendationMean", "strongBuy", "buy", "hold", "sell", "strongSell"):
        f.pop(k, None)
    f["_analyst_status"] = "not available"
    b = bundle(fundamentals=f)
    b["data_sources"] = {
        "price": {"source": "Yahoo Finance chart", "status": "available"},
        "fundamentals": {"source": "SEC EDGAR/XBRL", "status": "available"},
        "news": {"source": "Yahoo Finance search", "status": "available"},
        "analyst": {"source": "none", "status": "unavailable"},
        "sector": {"source": "SEC SIC mapping", "status": "available", "benchmark": "XLK"},
    }
    result = score_bundle(b)
    assert result["decision_confidence"] == "high"
    assert "analyst consensus" not in result["missing_inputs"]
    assert "analyst consensus" in result["optional_missing_inputs"]
    assert result["evidence_sources"]["fundamentals"]["source"] == "SEC EDGAR/XBRL"
