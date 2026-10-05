import copy
import json

import pytest

from app.market_evidence import recover_market_evidence
from app.scanner import RadarService
from app.db import SessionLocal, RadarCandidate, AnalysisSnapshot
from .helpers import bundle

NOW = '2026-10-05T17:30:00+00:00'


def inputs():
    current = {'symbol': 'TEST', 'currency': 'USD', 'asof': NOW, 'fundamentals': {
        '_valuation_status': 'unavailable (request budget)', '_market_cap_status': 'unavailable (enrichment budget)'}}
    saved = {'symbol': 'TEST', 'currency': 'USD', 'fundamentals': {
        'trailingPE': 80, '_valuation_source': 'Finnhub basic financials (TTM P/E)', '_valuation_asof': '2026-10-05T16:00:00+00:00',
        'marketCap': 1e9, '_market_cap_source': 'Finnhub company profile (millions converted to USD)', '_market_cap_asof': '2026-10-05T16:00:00+00:00'}}
    return current, saved


@pytest.mark.parametrize('status', ['unavailable (request budget)', 'unavailable (endpoint cooldown)'])
def test_transient_failure_retains_valid_evidence_without_advancing_age(status):
    c, s = inputs(); c['fundamentals']['_valuation_status'] = status; recover_market_evidence(c, [s])
    assert c['fundamentals']['trailingPE'] == 80  # High P/E must not turn neutral/cheap.
    assert c['fundamentals']['marketCap'] == 1e9
    assert c['fundamentals']['_valuation_asof'] == s['fundamentals']['_valuation_asof']
    assert 'cached validated' in c['fundamentals']['_valuation_status']


@pytest.mark.parametrize('changes', [
    {'_valuation_asof': '2026-10-05T11:30:00+00:00'},
    {'_valuation_asof': '2026-10-05T17:31:00+00:00'},
    {'_valuation_asof': 'bad'}, {'_valuation_source': 'unknown'}, {'trailingPE': -1},
])
def test_stale_future_unknown_or_invalid_evidence_cannot_be_recovered(changes):
    c, s = inputs(); s['fundamentals'].update(changes); recover_market_evidence(c, [s])
    assert 'trailingPE' not in c['fundamentals']


@pytest.mark.parametrize('change', [{'symbol': 'OTHER'}, {'currency': 'EUR'}])
def test_identity_or_currency_mismatch_cannot_recover(change):
    c, s = inputs(); s.update(change); recover_market_evidence(c, [s])
    assert 'trailingPE' not in c['fundamentals']


@pytest.mark.parametrize('status', ['unavailable (positive TTM P/E not returned)', 'unavailable (HTTP 403)', 'unavailable (empty/error response)'])
def test_definitive_provider_response_is_not_replaced_with_old_positive(status):
    c, s = inputs(); c['fundamentals']['_valuation_status'] = status; recover_market_evidence(c, [s])
    assert 'trailingPE' not in c['fundamentals']


def test_new_observation_and_other_components_remain_authoritative():
    c, s = inputs(); c['fundamentals'].update(trailingPE=20, revenueGrowth=-.2)
    s['fundamentals'].update(revenueGrowth=1, targetMeanPrice=200, strongBuy=100)
    recover_market_evidence(c, [s])
    assert c['fundamentals']['trailingPE'] == 20
    assert c['fundamentals']['revenueGrowth'] == -.2
    assert 'targetMeanPrice' not in c['fundamentals'] and 'strongBuy' not in c['fundamentals']


def test_newer_definitive_snapshot_supersedes_positive_history():
    c, s = inputs(); newer = copy.deepcopy(s)
    newer['fundamentals'].update(trailingPE=None, _valuation_asof='2026-10-05T17:00:00+00:00',
                                _valuation_status='unavailable (positive TTM P/E not returned)')
    recover_market_evidence(c, [s, newer])
    assert 'trailingPE' not in c['fundamentals']


def test_scanner_recovers_prior_and_restart_snapshot_before_scoring(monkeypatch):
    from datetime import datetime, timezone
    c, s = inputs()
    c['asof'] = datetime.now(timezone.utc).isoformat()
    for prefix in ['valuation', 'market_cap']:
        s['fundamentals'][f'_{prefix}_asof'] = c['asof']
    b = bundle(); b['symbol'] = 'TEST'; b['asof'] = c['asof']; b['fundamentals'].pop('forwardPE', None)
    b['fundamentals'].pop('marketCap', None); b['fundamentals'].update(c['fundamentals'])
    with SessionLocal() as db:
        db.add(RadarCandidate(symbol='TEST', current_json=json.dumps(c)))
        db.add(AnalysisSnapshot(symbol='TEST', payload_json=json.dumps(s))); db.commit()
    service = RadarService(provider=type('P', (), {'bundle': lambda self, symbol: copy.deepcopy(b)})(),
                           ai=type('A', (), {'analyze': lambda *args: {}})())
    monkeypatch.setattr('app.scanner.article_news.attach', lambda n, *args: n)
    out = service.analyze_symbol('TEST', persist=False)
    assert out['fundamentals']['trailingPE'] == 80
    assert out['breakdown']['Valuation'] == 3
    assert out['fundamentals']['marketCap'] == 1e9
