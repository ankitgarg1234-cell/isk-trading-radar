import copy
import json
from pathlib import Path

import httpx
import pytest

from app.market import SECFundamentalsProvider as SEC
from app.sec_evidence import inline_facts, merge_inline
from app.analysis_engine import fundamental_score, fundamental_input_diagnostics

CASES = json.loads((Path(__file__).parent / 'fixtures/sec_filing_coverage_2026_10_06.json').read_text())


def calculate(monkeypatch, case, *, inline=None):
    p = SEC()
    monkeypatch.setattr(p, 'resolve', lambda s: dict(cik=case['cik'], cik10=f"{case['cik']:010d}", title=s))
    monkeypatch.setattr(p, '_json', lambda u: case['submissions'] if '/submissions/' in u else case['facts'])
    requests = []
    def request(req):
        requests.append(str(req.url))
        return httpx.Response(200, text=inline if inline is not None else case.get('inline', ''), request=req)
    p.client = httpx.Client(transport=httpx.MockTransport(request))
    return p, requests


def test_current_ifrs_40f_replaces_obsolete_gaap_without_splicing(monkeypatch):
    case = CASES['AEM']; p, requests = calculate(monkeypatch, case)
    f = p.fundamentals('AEM')
    assert f['_accounting_basis'] == 'IFRS'
    assert f['_fundamental_period'] == f['_balance_period'] == '2025-12-31'
    assert f['revenueGrowth'] == pytest.approx(11907851000 / 8285753000 - 1)
    assert f['earningsGrowth'] == pytest.approx(4461461000 / 1895581000 - 1)
    assert f['returnOnEquity'] == pytest.approx(4461461000 / ((20832900000 + 24742464000) / 2))
    assert f['sharesOutstanding'] == 500046600
    assert f['grossMargins'] is None and f['operatingMargins'] is None
    assert fundamental_score(f)[0] == 12
    assert fundamental_input_diagnostics(f)['fundamental_floor_status'] == 'data_review'
    assert not requests  # current IFRS feed avoids redundant annual download


def test_real_quarter_recovers_facts_and_scale_missing_from_companyfacts(monkeypatch):
    p, requests = calculate(monkeypatch, CASES['ABT'])
    f = p.fundamentals('ABT')
    assert f['_balance_period'] == f['_quarterly_period'] == '2026-06-30'
    assert f['quarterlyRevenueGrowth'] == pytest.approx(12593000000 / 11142000000 - 1)
    assert f['sharesOutstanding'] == 1730383296
    assert f['returnOnEquity'] == pytest.approx(6524000000 / ((47664000000 + 52130000000) / 2))
    assert fundamental_score(f)[0] == 10  # no invented missing borrowing value
    assert len(requests) == 1 and requests[0] == CASES['ABT']['inline_source']
    assert p.fundamentals('ABT') == f and len(requests) == 1


def snippet(value='123', *, extra='', dimension='', identifier='0000001800', unit='iso4217:USD', name='us-gaap:Revenues'):
    return f'''<html><xbrli:context id="c"><xbrli:entity><xbrli:identifier>{identifier}</xbrli:identifier>{dimension}</xbrli:entity>
      <xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period></xbrli:context>
      <xbrli:unit id="u"><xbrli:measure>{unit}</xbrli:measure></xbrli:unit>
      <ix:nonFraction name="{name}" contextRef="c" unitRef="u" scale="6" {extra}>{value}</ix:nonFraction></html>'''


def parse(html):
    return inline_facts(html, cik=1800, form='10-Q', filed='2026-07-28', accn='abc', report_date='2026-06-30')


@pytest.mark.parametrize('change', [
    dict(dimension='<xbrli:segment><xbrldi:explicitMember>A</xbrldi:explicitMember></xbrli:segment>'),
    dict(identifier='0000009999'), dict(unit='iso4217:EUR'), dict(name='abt:CustomRevenue'),
    dict(value='—'), dict(value='nan'), dict(extra='format="ixt:num-comma-decimal"'), dict(extra='xsi:nil="true"'),
])
def test_unproven_inline_observations_cannot_earn_credit(change):
    assert parse(snippet(**change)) == []


def test_inline_scale_sign_and_conflicting_duplicates():
    assert parse(snippet(extra='sign="-"'))[0][1]['val'] == -123000000
    assert parse(snippet(value='123,456'))[0][1]['val'] == 123456000000
    assert parse(snippet() + snippet(value='124')) == []
    assert parse(snippet(value='-123', extra='sign="-"')) == []


def test_feed_conflict_is_unavailable_and_raw_source_remains_unchanged():
    original={'facts': {'us-gaap': {'Revenues': {'units': {'USD': [parse(snippet())[0][1]]}}}}}
    before=copy.deepcopy(original)
    merged=merge_inline(original, parse(snippet(value='124')))
    assert merged['facts']['us-gaap']['Revenues']['units']['USD'] == []
    assert original == before


def test_filing_failure_keeps_verified_annual_evidence(monkeypatch):
    p, _ = calculate(monkeypatch, CASES['ABT'])
    p.client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(403, request=r)))
    f = p.fundamentals('ABT')
    assert f['_fundamental_period'] == '2025-12-31' and f['quarterlyRevenueGrowth'] is None
    assert 'unavailable' in f['_filing_evidence_status']


@pytest.mark.parametrize('f,status,minimum,maximum', [
    ({}, 'data_review', 0, 20),
    ({'revenueGrowth':.3,'earningsGrowth':.3,'returnOnEquity':.25},'data_review',11,20),
    ({'revenueGrowth':0,'earningsGrowth':-.2,'grossMargins':0,'operatingMargins':-.1,
      'returnOnEquity':-.1,'debtToEquity':0,'quarterlyRevenueGrowth':0},'below_floor',3,3),
])
def test_unresolved_evidence_is_distinct_from_observed_below_floor(f,status,minimum,maximum):
    d=fundamental_input_diagnostics(f)
    assert (d['fundamental_floor_status'],d['fundamental_score_min'],d['fundamental_score_max']) == (status,minimum,maximum)


def test_existing_liability_bound_credit_is_not_counted_twice():
    f={'revenueGrowth':.3,'earningsGrowth':.3,'returnOnEquity':.25,
       '_fundamental_integrity':'matched', '_balance_period':'2025-12-31',
       '_debt_bound_period':'2025-12-31','_debt_to_equity_upper_bound':50,
       'grossMargins':0,'operatingMargins':-.1,'quarterlyRevenueGrowth':0}
    d=fundamental_input_diagnostics(f)
    assert d['fundamental_score_min'] == d['fundamental_score_max'] == 14
    assert d['fundamental_floor_status'] == 'passed'


def test_financial_services_band_limitation_is_explicit_model_review():
    f={'sector':'Financial Services','revenueGrowth':.03,'earningsGrowth':.05,'returnOnEquity':.15}
    assert fundamental_input_diagnostics(f)['fundamental_floor_status'] == 'model_review'
