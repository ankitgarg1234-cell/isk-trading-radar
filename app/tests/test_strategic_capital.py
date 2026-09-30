from app.portfolio_engine import candidate_rank_score
from app.scanner import _compact_payload, _strategic_fingerprint
from app.strategic_capital import StrategicCapitalProvider


def _base_payload():
    return {
        "symbol": "ACME", "price": 100, "deterministic_score": 82, "ai_score": 80,
        "analyst_score": 75, "expected_yield_pct": 22, "risk_reward": 2.5,
        "decision_confidence": "high", "category": "Core", "entry_zone_status": "PRIMARY_BUY",
        "action": "BUY NOW", "negative_news_override": None,
        "thesis_assessment": {"invalidated": False},
        "levels": {"buy_low": 98, "buy_high": 102, "better_low": 90, "better_high": 93, "stop": 88, "target": 125},
        "technicals": {"atr": 2, "relative_volume": 1.2, "change20_pct": 4},
        "news": {"material_events": 0}, "fundamentals": {"sector": "Technology"},
    }


def test_government_equity_and_trump_administration_are_not_personal_investment():
    p = StrategicCapitalProvider()
    events = p.classify_news("ACME", [
        {
            "title": "President Trump announces U.S. government equity stake in Acme",
            "publisher": "The White House",
            "link": "https://www.whitehouse.gov/fact-sheets/acme",
        }
    ])
    assert len(events) == 1
    assert events[0]["type"] == "GOVERNMENT_EQUITY_STAKE"
    assert events[0]["source_quality"] == "OFFICIAL"


def test_donald_trump_personal_interest_is_separate_from_family_interest():
    p = StrategicCapitalProvider()
    events = p.classify_news("ACME", [
        {"title": "Donald Trump personally buys shares in Acme", "publisher": "Reuters", "link": "https://reuters.com/a"},
        {"title": "Donald Trump Jr. invests in Acme", "publisher": "Reuters", "link": "https://reuters.com/b"},
    ])
    assert events[0]["type"] == "TRUMP_PERSONAL_INTEREST_MENTION"
    assert events[1]["type"] == "TRUMP_FAMILY_INTEREST"


def test_strategic_capital_is_shadow_only_and_does_not_change_rank_v1():
    a = _base_payload()
    b = dict(a)
    b["strategic_capital"] = {
        "mode": "SHADOW_ONLY", "label": "VERY STRONG", "direction": "POSITIVE",
        "evidence_strength": 95, "shadow_rank_adjustment": 7.6,
        "government_equity_stake": "EVIDENCE FOUND",
        "trump_administration_action": "EVIDENCE FOUND",
        "trump_personal_disclosure": {"status": "NOT FOUND IN CHECKED DISCLOSURE"},
    }
    assert candidate_rank_score(a)["score"] == candidate_rank_score(b)["score"]
    assert candidate_rank_score(b)["strategic_capital_shadow"]["shadow_rank_adjustment"] == 7.6


def test_official_award_materiality_is_normalized_to_company_revenue_without_scoring_it():
    p = StrategicCapitalProvider()
    p._usa_spending_awards = lambda _: {
        "status": "CHECKED", "total_amount": 250_000_000,
        "events": [{"type":"FEDERAL_AWARD","title":"DOE award","direction":"POSITIVE","materiality":"HIGH","verification":"VERIFIED SOURCE","source_quality":"OFFICIAL","source":"USAspending.gov","source_url":"https://www.usaspending.gov/"}],
        "checked_at": "2026-09-29T20:00:00+00:00",
    }
    p._trump_personal_disclosure = lambda company, symbol: {"status":"NOT FOUND IN CHECKED DISCLOSURE"}
    p._whitehouse_investment_tracker = lambda company, symbol: {"status":"NOT FOUND", "source_status":"CHECKED", "events":[]}
    g = p.assess("ACME", company_name="Acme Corp", annual_revenue=1_000_000_000, fetch_official=True)
    assert g["federal_amount_to_revenue_pct"] == 25.0
    assert g["direction"] == "POSITIVE"
    assert g["mode"] == "SHADOW_ONLY"


def test_compact_payload_limits_strategic_event_volume_and_fingerprint_changes_materially():
    events = [{"type":"FEDERAL_AWARD","title":f"Award {i}","direction":"POSITIVE","materiality":"HIGH"} for i in range(20)]
    full = _base_payload()
    full["strategic_capital"] = {"events": events, "federal_awards": {"events": events, "total_amount": 10}, "direction":"POSITIVE","evidence_strength":50}
    compact = _compact_payload(full)
    assert len(compact["strategic_capital"]["events"]) == 6
    assert len(compact["strategic_capital"]["federal_awards"]["events"]) == 5
    f1 = _strategic_fingerprint(compact["strategic_capital"])
    compact["strategic_capital"]["government_equity_stake"] = "EVIDENCE FOUND"
    assert _strategic_fingerprint(compact["strategic_capital"]) != f1


def test_periodic_disclosure_parser_detects_company_purchase_and_amount_range():
    text = """Executive Branch Personnel Public Financial Disclosure Report: Periodic Transaction Report
    NVIDIA CORP (NVDA) Purchase 04/09/2026 $1,000,001 - $5,000,000
    """
    matches = StrategicCapitalProvider._match_disclosure_text(text, "NVIDIA Corporation", "NVDA")
    assert matches
    assert matches[0]["action"] == "PURCHASE"
    assert matches[0]["date"] == "04/09/2026"
    assert matches[0]["amount_range"] == "$1,000,001 - $5,000,000"


def test_trump_personal_disclosure_checks_periodic_reports_not_just_annual(monkeypatch):
    from dataclasses import replace
    import app.strategic_capital as strategic_module
    monkeypatch.setattr(
        strategic_module, "settings",
        replace(strategic_module.settings, strategic_disclosure_pdf_enabled=True),
    )
    p = StrategicCapitalProvider()
    periodic = """Executive Branch Personnel Public Financial Disclosure Report: Periodic Transaction Report
    NVIDIA CORP (NVDA) Purchase 04/09/2026 $1,000,001 - $5,000,000
    """
    annual = "Annual financial disclosure without the company name"

    def fake_doc(url, force=False):
        return (periodic, "CHECKED") if "Periodic-Transaction-Report" in url else (annual, "CHECKED")

    monkeypatch.setattr(p, "_document_text", fake_doc)
    out = p._trump_personal_disclosure("NVIDIA Corporation", "NVDA", force=True)
    assert out["status"].startswith("VERIFIED TRANSACTION DISCLOSURE")
    assert out["sources_checked"] >= 2
    assert any(e["type"] == "TRUMP_PERSONAL_DISCLOSURE_TRANSACTION" for e in out["events"])


def test_usaspending_keyword_search_captures_indirect_product_procurement_without_calling_it_company_revenue():
    class R:
        def __init__(self, payload): self.payload = payload
        def raise_for_status(self): return None
        def json(self): return self.payload

    class Client:
        def __init__(self): self.calls = 0
        def post(self, url, json):
            self.calls += 1
            if self.calls in (1, 2):
                return R({"results": []})
            return R({"results": [{
                "Award ID": "ABC123", "Recipient Name": "TECH RESELLER LLC",
                "Start Date": "2026-08-01", "Award Amount": 25000000,
                "Awarding Agency": "Department of Defense",
                "Description": "Annual NVIDIA enterprise software and GPU support subscription",
            }]})

    p = StrategicCapitalProvider()
    p.client = Client()
    StrategicCapitalProvider._award_cache.clear()
    out = p._usa_spending_awards("NVIDIA Corporation", "NVDA", force=True)
    assert out["total_amount"] == 0
    assert out["indirect_mention_award_amount"] == 25000000
    assert any(e["type"] == "FEDERAL_PRODUCT_OR_VENDOR_MENTION" for e in out["events"])
    assert out["events"][0]["relationship"] == "INDIRECT / PRIME AWARD TO ANOTHER RECIPIENT"


def test_periodic_parser_keeps_adjacent_purchase_and_sale_rows_separate():
    text = """Periodic Transaction Report
    NVIDIA CORP purchase 4/15/2026 $100,001 - $250,000
    NVIDIA CORP sale 4/17/2026 $1,000,001 - $5,000,000
    NVIDIA CORP purchase 4/27/2026 $500,001 - $1,000,000
    """
    matches = StrategicCapitalProvider._match_disclosure_text(text, "NVIDIA Corporation", "NVDA")
    rows = [(m["action"], m["date"], m["amount_range"]) for m in matches[:3]]
    assert rows == [
        ("PURCHASE", "4/15/2026", "$100,001 - $250,000"),
        ("SALE", "4/17/2026", "$1,000,001 - $5,000,000"),
        ("PURCHASE", "4/27/2026", "$500,001 - $1,000,000"),
    ]


def test_whitehouse_investment_tracker_is_admin_interest_not_government_capital():
    class R:
        text = '<html><body><table><tr><td>NVIDIA</td><td>$608 Billion</td><td>Technology & AI</td></tr></table></body></html>'
        def raise_for_status(self): return None
    class Client:
        def get(self, *args, **kwargs): return R()

    p = StrategicCapitalProvider()
    p.client = Client()
    StrategicCapitalProvider._html_cache.clear()
    out = p._whitehouse_investment_tracker('NVIDIA Corporation', 'NVDA', force=True)
    assert out['status'] == 'EVIDENCE FOUND'
    assert out['events'][0]['type'] == 'ADMINISTRATION_HIGHLIGHTED_INVESTMENT'
    assert out['events'][0]['direction'] == 'CONTEXT'
    assert 'not U.S. government investment' in out['events'][0]['description']
