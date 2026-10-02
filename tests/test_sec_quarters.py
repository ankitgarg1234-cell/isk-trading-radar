import json
from pathlib import Path

import pytest

from app.market import SECFundamentalsProvider, YahooMarketProvider


def fact(rows):
    return {"units": {"USD": rows}}


def row(value, start, end, form="10-Q", filed="2026-08-01", **extra):
    return dict(val=value, start=start, end=end, form=form, filed=filed, **extra)


def test_same_filing_labels_do_not_exclude_correct_prior_or_select_oldest():
    rows = [
        row(500, "2022-01-01", "2022-03-31", fy=2022, fp="Q1"),
        row(100, "2025-01-01", "2025-03-31", fy=2026, fp="Q1"),
        row(150, "2026-01-01", "2026-03-31", fy=2026, fp="Q1"),
    ]
    assert SECFundamentalsProvider._quarter_yoy_growth(rows) == pytest.approx(.5)
    assert SECFundamentalsProvider._quarter_yoy_growth(rows[::-1]) == pytest.approx(.5)


@pytest.mark.parametrize("prior_end", ["2024-03-31", "2025-06-30"])
def test_no_comparable_prior_year_returns_missing(prior_end):
    rows = [dict(val=100, end=prior_end, fp="Q1", fy=2025),
            dict(val=150, end="2026-03-31", fp="Q1", fy=2026)]
    assert SECFundamentalsProvider._quarter_yoy_growth(rows) is None


def test_53_week_calendar_and_zero_prior():
    rows = [row(100, "2024-12-28", "2025-03-28"),
            row(150, "2026-01-03", "2026-04-03")]
    assert SECFundamentalsProvider._quarter_yoy_growth(rows) == pytest.approx(.5)
    rows[0]["val"] = 0
    assert SECFundamentalsProvider._quarter_yoy_growth(rows) is None


def test_annual_report_quarter_is_used_and_ytd_instant_rejected():
    rows = [row(40, "2025-10-01", "2025-12-31", "10-K", fp="FY"),
            row(90, "2025-01-01", "2025-09-30"),
            dict(val=500, end="2026-03-31", form="10-Q")]
    assert SECFundamentalsProvider._quarter_values(fact(rows)) == [rows[0]]


def test_q4_derived_from_same_year_ytd_and_direct_fact_preferred():
    rows = [row(100, "2025-01-01", "2025-12-31", "10-K"),
            row(70, "2025-01-01", "2025-09-30")]
    q4 = SECFundamentalsProvider._quarter_values(fact(rows))[-1]
    assert (q4["start"], q4["end"], q4["val"]) == ("2025-10-01", "2025-12-31", 30)
    assert q4["_derived"] == "annual minus nine-month YTD"
    direct = row(31, "2025-10-01", "2025-12-31", "10-K")
    assert SECFundamentalsProvider._quarter_values(fact(rows + [direct]))[-1] == direct


@pytest.mark.parametrize("ytd", [
    row(70, "2025-01-02", "2025-09-30"),  # different fiscal-year start
    row(50, "2025-01-01", "2025-06-30"),  # six months
    row(110, "2025-01-01", "2025-09-30"),  # invalid residual revenue
])
def test_incomplete_or_incompatible_ytd_cannot_create_q4(ytd):
    annual = row(100, "2025-01-01", "2025-12-31", "10-K")
    assert SECFundamentalsProvider._quarter_values(fact([annual, ytd])) == []


def test_revised_annual_cannot_be_subtracted_from_unrevised_interim():
    rows = [row(100, "2025-01-01", "2025-12-31", "10-K", "2026-02-01"),
            row(80, "2025-01-01", "2025-12-31", "10-K/A", "2026-08-01", accn="amended"),
            row(70, "2025-01-01", "2025-09-30", filed="2025-11-01", accn="interim")]
    assert SECFundamentalsProvider._quarter_values(fact(rows)) == []
    # A standalone Q4 from the original annual filing is also stale after revision.
    rows.append(row(30, "2025-10-01", "2025-12-31", "10-K", "2026-02-01"))
    assert SECFundamentalsProvider._quarter_values(fact(rows)) == []
    rows.append(row(55, "2025-01-01", "2025-09-30", "10-K/A", "2026-08-01", accn="amended"))
    assert SECFundamentalsProvider._quarter_values(fact(rows))[-1]["val"] == 25


def provider_for(monkeypatch, facts):
    provider = SECFundamentalsProvider()
    monkeypatch.setattr(provider, "resolve", lambda s: dict(cik=106040, cik10="0000106040", title=s))
    monkeypatch.setattr(provider, "_json", lambda u: {} if "/submissions/" in u else facts)
    return provider


def test_source_backed_wdc_uses_latest_q4_not_2018_or_q3(monkeypatch):
    facts = json.loads((Path(__file__).parent / "fixtures/wdc_revenue_facts.json").read_text())
    f = provider_for(monkeypatch, facts).fundamentals("WDC")
    assert f["quarterlyRevenueGrowth"] == pytest.approx(3747 / 2605 - 1)
    assert f["_quarterly_period"] == "2026-07-03"
    assert f["_quarterly_method"] == "annual minus nine-month YTD"


def test_unavailable_latest_q4_does_not_silently_use_old_q3(monkeypatch):
    facts = {"facts": {"us-gaap": {"Revenues": fact([
        row(100, "2024-07-01", "2024-09-30"),
        row(150, "2025-07-01", "2025-09-30"),
        row(700, "2025-01-01", "2025-12-31", "10-K"),
    ])}}}
    f = provider_for(monkeypatch, facts).fundamentals("TEST")
    assert f["quarterlyRevenueGrowth"] is None
    assert f["_quarterly_period"] == "2025-12-31"
    assert f["_quarterly_status"] == "no comparable latest quarter"


def test_revenue_tag_switch_uses_current_series(monkeypatch):
    facts = {"facts": {"us-gaap": {
        "RevenueFromContractWithCustomerExcludingAssessedTax": fact([row(50, "2022-01-01", "2022-03-31")]),
        "Revenues": fact([row(100, "2025-01-01", "2025-03-31"), row(150, "2026-01-01", "2026-03-31")]),
    }}}
    f = provider_for(monkeypatch, facts).fundamentals("TEST")
    assert f["quarterlyRevenueGrowth"] == pytest.approx(.5)
    assert f["_quarterly_period"] == "2026-03-31"


def test_healthy_yahoo_still_receives_sec_quarter_and_provenance(monkeypatch):
    class SEC:
        def fundamentals(self, symbol):
            return dict(quarterlyRevenueGrowth=.5, _quarterly_period="2026-03-31",
                        _quarterly_source="SEC EDGAR/XBRL", _quarterly_method="reported quarter",
                        _quarterly_status="available", _status="available")
    class Analyst:
        def recommendations(self, symbol):
            return {}
    provider = YahooMarketProvider(sec_provider=SEC(), analyst_provider=Analyst())
    monkeypatch.setattr(provider, "yahoo_fundamentals", lambda s: dict(
        marketCap=1e10, revenueGrowth=.2, earningsGrowth=.3, grossMargins=.4))
    f = provider.fundamentals("TEST")
    assert f["quarterlyRevenueGrowth"] == .5
    assert f["revenueGrowth"] == .2
    assert f["_quarterly_period"] == "2026-03-31"
    assert f["_quarterly_source"] == "SEC EDGAR/XBRL"
