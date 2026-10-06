"""Actual SEC alias retirement and controls for period-safe recovery."""
import copy
import json
from pathlib import Path

import pytest

from app.analysis_engine import fundamental_score, fundamental_input_diagnostics
from app.market import SECFundamentalsProvider as SEC
from tests.test_fundamental_integrity import basic, calculate, fact, annual, instant

INCOME = ("NetIncomeLoss", "ProfitLoss")
EQUITY = ("StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest")


def test_retired_income_alias_uses_current_complete_concept(monkeypatch):
    us = basic()
    us["ProfitLoss"] = copy.deepcopy(us["NetIncomeLoss"])
    us["NetIncomeLoss"]["units"]["USD"].pop()
    f = calculate(monkeypatch, us)
    assert f["_net_income_tag"] == "ProfitLoss"
    assert f["earningsGrowth"] == pytest.approx(.4)
    assert f["returnOnEquity"] == pytest.approx(14/60)


def test_retired_equity_alias_recovers_matched_roe_and_debt(monkeypatch):
    us = basic()
    us[EQUITY[1]] = copy.deepcopy(us[EQUITY[0]])
    us[EQUITY[0]] = fact([instant(100, "2019-12-31")])
    f = calculate(monkeypatch, us)
    assert f["_equity_tag"] == EQUITY[1]
    assert f["returnOnEquity"] == pytest.approx(14/60)
    assert f["debtToEquity"] == pytest.approx(35/70*100)


def test_current_preferred_alias_keeps_priority(monkeypatch):
    us = basic()
    us["ProfitLoss"] = fact([annual(999)])
    us[EQUITY[1]] = fact([instant(999)])
    f = calculate(monkeypatch, us)
    assert f["_net_income_tag"] == INCOME[0]
    assert f["_equity_tag"] == EQUITY[0]
    assert f["earningsGrowth"] == pytest.approx(.4)
    assert f["returnOnEquity"] == pytest.approx(14/60)


def test_growth_does_not_splice_retired_and_new_income_concepts(monkeypatch):
    us = basic()
    us["NetIncomeLoss"]["units"]["USD"].pop()
    us["ProfitLoss"] = fact([annual(14)])
    f = calculate(monkeypatch, us)
    assert f["earningsGrowth"] is None
    assert f["returnOnEquity"] == pytest.approx(14/60)
    assert f["_earnings_change"] == "no comparable fiscal year"


@pytest.mark.parametrize("replacement", [
    fact([annual(14)], "EUR"),
    fact([annual(14, start="2025-02-01")]),
    fact([dict(annual(14), form="8-K")]),
    fact([annual(14, "2026-12-31", "2026-01-01")]),
    fact([annual(float("nan"))]),
])
def test_ineligible_income_alias_cannot_replace_missing_current_data(monkeypatch, replacement):
    us = basic()
    us["NetIncomeLoss"]["units"]["USD"].pop()
    us["ProfitLoss"] = replacement
    f = calculate(monkeypatch, us)
    assert f["earningsGrowth"] is None and f["returnOnEquity"] is None


@pytest.mark.parametrize("bad", [
    fact([instant(999)], "EUR"),
    fact([dict(instant(999), start="2025-01-01")]),
    fact([dict(instant(999), form="8-K")]),
    fact([instant(999, "2026-12-31")]),
    fact([instant(float("nan"))]),
])
def test_ineligible_equity_alias_does_not_displace_eligible_series(monkeypatch, bad):
    us = basic(); us[EQUITY[1]] = bad
    f = calculate(monkeypatch, us)
    assert f["_equity_tag"] == EQUITY[0]
    assert f["returnOnEquity"] == pytest.approx(14/60)


@pytest.mark.parametrize("closing", [0, -70])
def test_current_nonpositive_equity_is_not_replaced_with_stale_positive_alias(monkeypatch, closing):
    us = basic()
    us[EQUITY[0]] = fact([instant(50, "2024-12-31")])
    us[EQUITY[1]] = fact([instant(50, "2024-12-31"), instant(closing)])
    f = calculate(monkeypatch, us)
    assert f["_equity_tag"] == EQUITY[1]
    assert f["returnOnEquity"] is None and f["debtToEquity"] is None


def test_real_broadcom_retired_aliases_recover_reported_financials(monkeypatch):
    captured = json.loads((Path(__file__).parent / "fixtures/current_sec_aliases_avgo.json").read_text())
    f = calculate(monkeypatch, captured["facts"]["facts"]["us-gaap"], captured["submissions"])
    assert f["_net_income_tag"] == "ProfitLoss"
    assert f["_equity_tag"] == EQUITY[1]
    assert f["earningsGrowth"] == pytest.approx(23126/5895-1)
    assert f["returnOnEquity"] == pytest.approx(23126/((67678+81292)/2))
    assert f["debtToEquity"] == pytest.approx(59419/99690*100)
    assert f["_fundamental_period"] == "2025-11-02"
    assert f["_balance_period"] == "2026-08-02"
    assert fundamental_score(f)[0] == 20
    legacy = dict(f, earningsGrowth=None, returnOnEquity=None, debtToEquity=None,
                  _debt_to_equity_upper_bound=None)
    assert fundamental_score(legacy)[0] == 12


def test_input_diagnostics_preserve_zero_negative_values_and_score():
    f = dict(revenueGrowth=0, earningsGrowth=-.2, grossMargins=0,
             operatingMargins=-.05, returnOnEquity=-.1, debtToEquity=0)
    before = copy.deepcopy(f)
    assert fundamental_input_diagnostics(f) == {
        "fundamental_missing_inputs": [], "fundamental_model_limitation": None,
        "fundamental_floor_status": "below_floor", "fundamental_score_min": 3,
        "fundamental_score_max": 5, "fundamental_missing_bonus_inputs": ["quarterlyRevenueGrowth"]}
    assert f == before and fundamental_score(f) == fundamental_score(before)


def test_missing_financial_metrics_are_model_limits_not_proven_weakness():
    f = dict(sector="Financial Services", revenueGrowth=.028, earningsGrowth=-.024, returnOnEquity=.161)
    diagnostics = fundamental_input_diagnostics(f)
    assert diagnostics["fundamental_missing_inputs"] == ["grossMargins", "operatingMargins", "debtToEquity"]
    assert "no separate financial-services model" in diagnostics["fundamental_model_limitation"]
    assert fundamental_score(f)[0] == 2
