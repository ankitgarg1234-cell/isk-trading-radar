"""Source arithmetic and adversarial financial-data cases, independent of score bands."""
import copy
import json
from pathlib import Path

import pytest

from app.market import SECFundamentalsProvider as SEC, YahooMarketProvider
from app.analysis_engine import fundamental_score, pct, score_bundle
from tests.helpers import bundle, strong_fundamentals

END = "2025-12-31"


def instant(value, end=END, filed="2026-02-01", **extra):
    return dict(val=value, end=end, filed=filed, form="10-K", **extra)


def annual(value, end=END, start="2025-01-01", **extra):
    return dict(instant(value, end, **extra), start=start)


def fact(rows, unit="USD"):
    return {"units": {unit: rows}}


def basic():
    return {"Revenues": fact([annual(100, "2024-12-31", "2024-01-01"), annual(130)]),
            "NetIncomeLoss": fact([annual(10, "2024-12-31", "2024-01-01"), annual(14)]),
            "GrossProfit": fact([annual(78)]), "OperatingIncomeLoss": fact([annual(26)]),
            "StockholdersEquity": fact([instant(50, "2024-12-31"), instant(70)]),
            "AssetsCurrent": fact([instant(90)]), "LiabilitiesCurrent": fact([instant(45)]),
            "LongTermDebtCurrent": fact([instant(10)]),
            "ShortTermBorrowings": fact([instant(5)]),
            "LongTermDebtNoncurrent": fact([instant(20)])}


def calculate(monkeypatch, us, submissions=None):
    p = SEC()
    monkeypatch.setattr(p, "resolve", lambda s: dict(cik=1, cik10="0000000001", title=s))
    monkeypatch.setattr(p, "_json", lambda u: (submissions or {}) if "/submissions/" in u else {"facts": {"us-gaap": us}})
    return p.fundamentals("TEST")


def test_average_roe_is_fiscal_year_matched_and_ignores_new_quarter_equity(monkeypatch):
    us = basic(); us["StockholdersEquity"]["units"]["USD"].append(instant(1000, "2026-03-31"))
    f = calculate(monkeypatch, us)
    assert f["returnOnEquity"] == pytest.approx(14/60)
    assert f["_roe_equity_start"] == 50 and f["_roe_equity_end"] == 70


@pytest.mark.parametrize("opening,closing", [(None, 70), (0, 70), (-50, 70), (50, -70)])
def test_missing_or_nonpositive_equity_never_gets_positive_roe(monkeypatch, opening, closing):
    us=basic(); us["StockholdersEquity"] = fact(([instant(opening, "2024-12-31")] if opening is not None else []) + [instant(closing)])
    f=calculate(monkeypatch, us)
    assert f["returnOnEquity"] is None
    if closing <= 0:
        assert f["debtToEquity"] is None


@pytest.mark.parametrize("metric,key", [("GrossProfit", "grossMargins"), ("OperatingIncomeLoss", "operatingMargins"), ("NetIncomeLoss", "earningsGrowth")])
def test_missing_latest_numerator_cannot_use_older_year(monkeypatch, metric, key):
    us=basic();us[metric]=fact([annual(60, "2024-12-31", "2024-01-01")])
    assert calculate(monkeypatch, us)[key] is None


def test_matching_end_with_wrong_start_is_rejected(monkeypatch):
    us=basic();us["GrossProfit"]=fact([annual(78, start="2024-11-01")])
    assert calculate(monkeypatch,us)["grossMargins"] is None


def test_stale_annual_revenue_is_not_presented_as_latest(monkeypatch):
    subs={"filings":{"recent":{"form":["10-K"],"reportDate":["2026-12-31"]}}}
    f=calculate(monkeypatch,basic(),subs)
    assert f["revenueGrowth"] is None and f["grossMargins"] is None
    assert f["_fundamental_period"] is None


def test_currency_and_instant_facts_cannot_be_used_as_annual_flows(monkeypatch):
    us=basic();us["GrossProfit"]=fact([annual(78)],"EUR")
    assert calculate(monkeypatch,us)["grossMargins"] is None
    assert SEC._annual_values(fact([instant(130)])) == []


@pytest.mark.parametrize("prior,current,status", [(-100,-200,"worsening loss"),(-100,-50,"improving loss"),(-100,50,"returned to profitability"),(0,50,"zero prior-year income; percentage growth unavailable")])
def test_loss_and_zero_base_never_receive_false_percentage_growth(monkeypatch, prior,current,status):
    us=basic();us["NetIncomeLoss"]=fact([annual(prior,"2024-12-31","2024-01-01"),annual(current)])
    f=calculate(monkeypatch,us)
    assert f["earningsGrowth"] is None and f["_earnings_change"] == status
    assert not any("→ 4/4" in r for r in fundamental_score({"earningsGrowth":f["earningsGrowth"],"_earnings_change":status})[1])


def test_profit_to_loss_is_negative_growth(monkeypatch):
    us=basic();us["NetIncomeLoss"]=fact([annual(100,"2024-12-31","2024-01-01"),annual(-50)])
    f=calculate(monkeypatch,us)
    assert f["earningsGrowth"] == -1.5 and f["returnOnEquity"] < 0


def test_missing_intermediate_year_does_not_fake_annual_growth(monkeypatch):
    us=basic();us["Revenues"]["units"]["USD"][0]=annual(100,"2023-12-31","2023-01-01")
    assert calculate(monkeypatch,us)["revenueGrowth"] is None


def test_zero_earnings_is_preserved_and_forecast_is_not_actual():
    assert fundamental_score({"earningsGrowth":0,"growth":1})[0] == 1
    assert fundamental_score({"growth":1})[2] == "low"


def test_distinct_debt_components_sum_once(monkeypatch):
    f=calculate(monkeypatch,basic())
    assert f["_debt_value"] == 35
    assert f["debtToEquity"] == 50


def test_total_current_debt_and_short_borrowing_are_not_added_twice(monkeypatch):
    us=basic();us["DebtCurrent"]=fact([instant(15)])
    assert calculate(monkeypatch,us)["_debt_value"] == 35


def test_total_long_term_and_maturity_aliases_are_not_added_twice(monkeypatch):
    us=basic();us["LongTermDebt"]=fact([instant(30)])
    assert calculate(monkeypatch,us)["_debt_value"] == 35


def test_zero_debt_is_valid_but_missing_component_is_unknown(monkeypatch):
    us=basic()
    for key in ("LongTermDebtCurrent","ShortTermBorrowings","LongTermDebtNoncurrent"):
        us[key]=fact([instant(0)])
    f=calculate(monkeypatch,us)
    assert f["debtToEquity"] == 0
    assert fundamental_score({"debtToEquity":0})[0] == 2
    del us["LongTermDebtCurrent"]
    assert calculate(monkeypatch,us)["debtToEquity"] is None


def test_stale_debt_component_cannot_use_latest_equity(monkeypatch):
    us=basic();us["LongTermDebtCurrent"]=fact([instant(10,"2024-12-31")])
    assert calculate(monkeypatch,us)["debtToEquity"] is None


def test_newer_alias_is_preferred_to_older_same_date_fact(monkeypatch):
    us=basic();us["LongTermDebtAndFinanceLeaseObligationsCurrent"]=fact([instant(100,filed="2026-01-01")])
    assert calculate(monkeypatch,us)["_debt_value"] == 35


@pytest.mark.parametrize("component",["LongTermDebtCurrent","LongTermDebtNoncurrent","ShortTermBorrowings"])
def test_negative_debt_components_rejected_even_when_total_positive(monkeypatch,component):
    us=basic();us[component]=fact([instant(-1)])
    assert calculate(monkeypatch,us)["debtToEquity"] is None


@pytest.mark.parametrize("bad",[float("nan"),float("inf"),"nan","inf","oops"])
def test_invalid_numbers_do_not_crash_or_count_toward_confidence(bad):
    f={"revenueGrowth":.3,"earningsGrowth":.3,"grossMargins":.6,"operatingMargins":.2,"returnOnEquity":bad,"debtToEquity":bad}
    assert pct(bad) is None
    assert fundamental_score(f)[2] == "medium"


def test_negative_debt_does_not_earn_credit():
    assert fundamental_score({"debtToEquity":-100})[2] == "low"


def test_cap_is_explained_without_changing_weights():
    f=strong_fundamentals();f.update(grossMargins=.7,returnOnEquity=.3,quarterlyRevenueGrowth=.3)
    score,reasons,_=fundamental_score(f)
    assert score==20 and "subtotal 22.0" in reasons[-1]


def test_restatement_selects_latest_comparable_facts(monkeypatch):
    us=basic();us["GrossProfit"]["units"]["USD"].append(annual(65,filed="2026-03-01"))
    assert calculate(monkeypatch,us)["grossMargins"] == .5


def test_sec_rejected_values_are_not_refilled_from_other_period_provider(monkeypatch):
    class Source:
        def fundamentals(self,symbol):
            return dict(_status="available",_fundamental_integrity="matched-fiscal-periods-v1",grossMargins=None,earningsGrowth=0,revenueGrowth=.3)
    class Analyst:
        def recommendations(self,symbol):return {}
    p=YahooMarketProvider(sec_provider=Source(),analyst_provider=Analyst())
    monkeypatch.setattr(p,"yahoo_fundamentals",lambda s:dict(grossMargins=.9,earningsGrowth=1,revenueGrowth=.5,marketCap=1e9))
    f=p.fundamentals("TEST")
    assert f["grossMargins"] is None and f["earningsGrowth"] == 0 and f["revenueGrowth"] == .3
    assert f["_fundamental_source"] == "SEC EDGAR/XBRL"


@pytest.mark.parametrize("symbol,expected_roe",[("CRDO",472279/((2063612+681582)/2)),("WDC",9424/((8864+5311)/2)),("MSFT",None),("NVDA",None)])
def test_source_backed_average_equity_and_matching_fiscal_metrics(monkeypatch,symbol,expected_roe):
    cases=json.loads((Path(__file__).parent/'fixtures/fundamental_source_cases.json').read_text())
    case=cases[symbol];p=SEC()
    monkeypatch.setattr(p,'resolve',lambda s:dict(cik=case['cik'],cik10=f"{case['cik']:010d}",title=s))
    monkeypatch.setattr(p,'_json',lambda u:case['submissions'] if '/submissions/' in u else case['facts'])
    f=p.fundamentals(symbol)
    assert f['_roe_status']=='available'
    if expected_roe is not None:assert f['returnOnEquity']==pytest.approx(expected_roe)
    assert f['grossMargins'] is not None and f['earningsGrowth'] is not None
    if symbol=='CRDO':
        assert fundamental_score(f)[0]==20
        assert f['debtToEquity'] is None  # no debt facts, never fabricate zero
    if symbol=='WDC':
        assert f['quarterlyRevenueGrowth']==pytest.approx(3747/2605-1)
        assert f['earningsGrowth']==pytest.approx(9424/1889-1)


@pytest.mark.parametrize('version,same_version',[('old-scoring-version',False),(None,True)])
def test_scoring_upgrade_is_not_company_deterioration(monkeypatch,version,same_version):
    from app.scanner import RadarService
    from app.analysis_engine import SCORING_VERSION
    from app.db import SessionLocal,RadarCandidate
    old={'scoring_version':version or SCORING_VERSION,'breakdown':{'Fundamentals':20},'deterministic_score':85,'action':'HOLD'}
    with SessionLocal() as db:
        db.add(RadarCandidate(symbol='TEST',current_json=json.dumps(old)));db.commit()
    sample=bundle()
    provider=type('Provider',(),{'bundle':lambda self,s:sample})()
    ai=type('AI',(),{'analyze':lambda *args:{}})()
    service=RadarService(provider=provider,ai=ai)
    out=service.analyze_symbol('TEST',persist=False)
    assert bool(out['previous_snapshot']) is same_version
