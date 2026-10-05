"""Observed production omissions and independent mathematical/financial controls."""
import json
from pathlib import Path

import httpx
import pytest

from app.analysis_engine import fundamental_score, rsi, news_analysis
from app.market import SECFundamentalsProvider as SEC, FinnhubAnalystProvider, YahooMarketProvider
from .test_fundamental_integrity import basic, calculate, fact, annual, instant

CASES = json.loads((Path(__file__).parent / 'fixtures/score_input_cases.json').read_text())


def test_wilder_rsi_retains_losses_outside_last_window():
    assert rsi([100, 90, 110, 111, 112], 2) == pytest.approx(72.2222222222)


@pytest.mark.parametrize('closes,expected', [([10] * 20, 50), (list(range(20)), 100), (list(range(20, 0, -1)), 0), ([1] * 14, None)])
def test_rsi_flat_one_way_and_short_series(closes, expected):
    assert rsi(closes) == expected


@pytest.mark.parametrize('symbol,expected', [('NVDA', 65.6738), ('CRDO', 55.5246)])
def test_source_history_constructive_rsi_was_rejected_by_simple_average(symbol, expected):
    closes = CASES[symbol]['closes']
    assert rsi(closes) == pytest.approx(expected, abs=.02)
    changes = [b-a for a, b in zip(closes, closes[1:])][-14:]
    assert 100-100/(1+sum(max(c, 0) for c in changes)/sum(max(-c, 0) for c in changes)) > 72


def test_matched_cost_reconstructs_missing_gross_profit(monkeypatch):
    us = basic(); us.pop('GrossProfit'); us['CostOfRevenue'] = fact([annual(52)])
    f = calculate(monkeypatch, us)
    assert f['grossMargins'] == .6
    assert 'matched cost' in f['_gross_margin_method']


@pytest.mark.parametrize('cost', [annual(1, '2024-12-31', '2024-01-01'), annual(1, start='2024-11-01'), annual(-1)])
def test_bad_or_stale_cost_never_invents_a_margin(monkeypatch, cost):
    us = basic(); us.pop('GrossProfit'); us['CostOfRevenue'] = fact([cost])
    assert calculate(monkeypatch, us)['grossMargins'] is None


def test_revised_revenue_cannot_mix_with_unrevised_cost(monkeypatch):
    us = basic(); us.pop('GrossProfit'); us['Revenues']['units']['USD'][-1]['accn'] = 'revised'
    us['CostOfRevenue'] = fact([annual(52, accn='original')])
    assert calculate(monkeypatch, us)['grossMargins'] is None


def test_reported_gross_profit_remains_preferred(monkeypatch):
    us = basic(); us['CostOfRevenue'] = fact([annual(100)])
    assert calculate(monkeypatch, us)['grossMargins'] == .6


@pytest.mark.parametrize('liabilities,points', [(52.4, 2), (52.5, 1), (104.9, 1), (105, 0)])
def test_liabilities_bound_proves_only_guaranteed_existing_debt_band(monkeypatch, liabilities, points):
    us = basic()
    for tag in ('LongTermDebtCurrent', 'LongTermDebtNoncurrent', 'ShortTermBorrowings'):
        us.pop(tag)
    us['Liabilities'] = fact([instant(liabilities)])
    f = calculate(monkeypatch, us)
    assert f['debtToEquity'] is None
    # Isolate the additional, proved debt credit from the unchanged other bands.
    unbounded = {**f, '_debt_to_equity_upper_bound': None}
    assert fundamental_score(f)[0]-fundamental_score(unbounded)[0] == points


@pytest.mark.parametrize('debt', [200, -1, float('nan')])
def test_actual_high_or_invalid_debt_takes_precedence_over_bound(debt):
    f = {'revenueGrowth': .1, 'debtToEquity': debt, '_fundamental_integrity': 'verified', '_balance_period': '2026-06-30',
         '_debt_bound_period': '2026-06-30', '_debt_to_equity_upper_bound': 10}
    assert fundamental_score(f)[0] == 2  # Revenue alone; no debt credit.


@pytest.mark.parametrize('change', [{'end': '2024-12-31'}, {'val': -1}, {'filed': '2026-04-01'}])
def test_unmatched_or_invalid_liabilities_cannot_prove_debt_band(monkeypatch, change):
    us = basic(); us['Liabilities'] = fact([{**instant(10), **change}])
    assert calculate(monkeypatch, us)['_debt_to_equity_upper_bound'] is None


@pytest.mark.parametrize('symbol', ['GOOGL', 'MSFT'])
def test_source_filings_recover_only_proven_credit(monkeypatch, symbol):
    case = CASES[symbol]; p = SEC()
    monkeypatch.setattr(p, 'resolve', lambda s: {'cik': case['cik'], 'cik10': f"{case['cik']:010d}", 'title': s})
    monkeypatch.setattr(p, '_json', lambda u: case['submissions'] if '/submissions/' in u else case['facts'])
    f = p.fundamentals(symbol)
    if symbol == 'GOOGL':
        assert f['grossMargins'] is not None
        assert 'matched cost' in f['_gross_margin_method']
        assert fundamental_score(f)[0] == 19
    else:
        assert f['debtToEquity'] is None  # Historical borrowings remain unknown.
        assert f['_debt_to_equity_upper_bound'] == pytest.approx(315989/442387*100)
        assert fundamental_score(f)[0] == 20


def assess(title, symbol='CRDO', company='Credo Technology Group Holding Ltd'):
    return news_analysis([{'title': title, 'publisher': 'Reuters'}], symbol=symbol, company_name=company)


@pytest.mark.parametrize('title', [
    'Credo (CRDO) Grew Revenue 114.70%. Why Can Nobody Price It?',
    'Credo revenue rose 20%. Could the rally last?',
    'Credo raises guidance on May 5, 2026',
    'Credo wins contract and signs partnership',
])
def test_asserted_facts_survive_separate_speculation_and_continuations(title):
    n = assess(title)
    assert n['positive'] > 0 and n['score'] > 7.5


@pytest.mark.parametrize('title', [
    'Could Credo revenue rise 20%?', 'Credo may raise guidance',
    'Nvidia raises guidance. Stock upgraded. Credo shares fall',
    'Credo shares rise as Nvidia wins contract',
])
def test_speculation_or_another_company_cannot_gain_credit(title):
    assert assess(title)['positive'] == 0


def test_observed_passive_stock_upgrade_is_recognized_once():
    n = assess("Microsoft Seen As 'Adults In Charge' Of AI. Stock Upgraded To Buy.", 'MSFT', 'MICROSOFT CORP')
    assert n['positive'] == 1.25
    assert n['items'][0]['matched_events'][0]['type'] == 'rating'


def test_optional_enrichment_requests_only_missing_fields(monkeypatch):
    calls = []
    analyst = FinnhubAnalystProvider(token='private')
    def handle(request):
        calls.append(request.url.path)
        return httpx.Response(403) if 'price-target' in request.url.path else httpx.Response(200, json={'symbol': 'TEST', 'metric': {'peTTM': 18}})
    analyst.client = httpx.Client(transport=httpx.MockTransport(handle))
    sec = type('Source', (), {'fundamentals': lambda self, s: {'sharesOutstanding': 1e9}})()
    p = YahooMarketProvider(sec_provider=sec, analyst_provider=analyst)
    monkeypatch.setattr(p, 'yahoo_fundamentals', lambda s: {})
    monkeypatch.setattr(analyst, 'recommendations', lambda s: {})
    f = p.fundamentals('TEST')
    assert f['trailingPE'] == 18
    assert len(calls) == 2 and not any('profile2' in path for path in calls)


def test_existing_valuation_does_not_spend_optional_request_budget():
    calls = []
    p = FinnhubAnalystProvider(token='private')
    p.client = httpx.Client(transport=httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(403)))
    p.market_evidence_for('TEST', need_valuation=False, need_profile=False)
    assert len(calls) == 1 and 'price-target' in calls[0].url.path
