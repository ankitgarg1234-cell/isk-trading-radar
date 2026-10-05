import httpx
from app.market import FinnhubAnalystProvider, YahooMarketProvider
from app.market_evidence import EndpointCache
from app.analysis_engine import analyst_score, score_bundle
from app.score_diagnostics import scan_score_diagnostics
from .helpers import bundle


def client(calls):
    def handle(request):
        endpoint = request.url.path.rsplit('/', 1)[-1]
        calls.append(endpoint)
        payload = [{'strongBuy': 11, 'buy': 24, 'hold': 5, 'sell': 0, 'strongSell': 0, 'period': '2026-09-01'}] if endpoint == 'recommendation' else {'metric': {'peTTM': 25}}
        return httpx.Response(200, json=payload)
    return httpx.Client(transport=httpx.MockTransport(handle))


def test_enrichment_cannot_exhaust_recommendation_capacity(monkeypatch):
    monkeypatch.setattr('app.market_evidence.time.monotonic', lambda: 100)
    calls, cache = [], EndpointCache()
    http = client(calls)
    for i in range(50):
        cache.fetch(http, 'metric', str(i), 'secret', 21600)
    for i in range(30):
        data, status = cache.fetch(http, 'recommendation', str(i), 'secret', 21600)
        assert status == 'available' and data
    assert calls.count('metric') == 15
    assert calls.count('recommendation') == 30
    assert len(calls) == 45
    assert cache.fetch(http, 'recommendation', 'EXTRA', 'secret', 21600)[0] is None


def test_metric_churn_cannot_evict_cached_recommendations(monkeypatch):
    clock = [100]
    monkeypatch.setattr('app.market_evidence.time.monotonic', lambda: clock[0])
    calls, cache = [], EndpointCache()
    http = client(calls)
    first, _ = cache.fetch(http, 'recommendation', 'TEST', 'secret', 21600)
    for i in range(300):
        clock[0] += 61
        cache.fetch(http, 'metric', str(i), 'secret', 21600)
    repeated, status = cache.fetch(http, 'recommendation', 'TEST', 'secret', 21600)
    assert status == 'available' and repeated == first
    assert calls.count('recommendation') == 1
    assert len(cache.entries['metric']) == 128
    assert len(cache.entries['recommendation']) == 1


def test_prefetch_scores_survive_later_enrichment_pressure(monkeypatch):
    monkeypatch.setattr('app.market_evidence.time.monotonic', lambda: 100)
    calls = []
    p = FinnhubAnalystProvider(token='secret')
    p.client = client(calls)
    symbols = [f'S{i}' for i in range(45)]
    p.prefetch_recommendations(symbols)
    for symbol in symbols:
        p.market_evidence(symbol)
        f = p.recommendations(symbol)
        assert f['_analyst_status'] == 'available'
        assert analyst_score(f, 100)[0] is not None
    assert len(calls) == 45
    assert set(calls) == {'recommendation'}


def test_restricted_target_does_not_remove_recommendation_score():
    p = FinnhubAnalystProvider(token='secret')
    calls = []
    base = client(calls)
    def handle(request):
        if 'price-target' in request.url.path:
            return httpx.Response(403)
        return base.send(request)
    p.client = httpx.Client(transport=httpx.MockTransport(handle))
    class SEC:
        def fundamentals(self, symbol):
            return {}
    market = YahooMarketProvider(sec_provider=SEC(), analyst_provider=p)
    market.yahoo_fundamentals = lambda symbol: {'_status': 'unavailable (HTTP 401)'}
    f = market.fundamentals('TEST')
    assert f['_target_status'] == 'unavailable (HTTP 403)'
    assert f['_analyst_status'] == 'available'
    assert analyst_score(f, 100)[0] == 81.8


def test_diagnostics_distinguish_budget_missing_from_existing_scores():
    rows = [{'analyst_score': None, 'fundamentals': {'_analyst_status': 'unavailable (request budget)'}},
            {'analyst_score': 85, 'fundamentals': {'_analyst_status': 'available'}}]
    result = scan_score_diagnostics(rows)
    assert result['analyst_scores_available'] == result['analyst_scores_missing'] == 1
    assert result['analyst_missing_statuses'] == {'unavailable (request budget)': 1}


def test_recommendation_score_still_works_without_price_target():
    b = bundle()
    b['fundamentals'].pop('targetMeanPrice', None)
    b['fundamentals'].update(strongBuy=11, buy=24, hold=5, sell=0, strongSell=0)
    b['fundamentals'].pop('recommendationMean', None)
    assert score_bundle(b)['analyst_score'] == 81.8


def test_temporary_provider_throttle_retries_after_cooldown(monkeypatch):
    clock = [100]
    monkeypatch.setattr('app.market_evidence.time.monotonic', lambda: clock[0])
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(429) if len(calls) == 1 else httpx.Response(200, json=[{'buy': 5}])
    cache = EndpointCache()
    http = httpx.Client(transport=httpx.MockTransport(handle))
    assert cache.fetch(http, 'recommendation', 'TEST', 'secret', 21600)[0] is None
    clock[0] += 61
    assert cache.fetch(http, 'recommendation', 'TEST', 'secret', 21600)[1] == 'available'
    assert len(calls) == 2
