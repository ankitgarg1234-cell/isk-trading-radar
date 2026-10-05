from datetime import datetime, timedelta, timezone
import httpx
import pytest
from app.market_evidence import matched_relative_volume, NY, EndpointCache
from app.market import YahooMarketProvider, FinnhubAnalystProvider
from app.analysis_engine import score_bundle
from .helpers import bundle


def intraday(day=None):
    day = day or datetime(2026, 10, 5, 10, 12, tzinfo=NY)
    times, volumes = [], []
    for offset in range(33, -1, -1):
        session = day - timedelta(days=offset)
        if session.weekday() >= 5:
            continue
        for minute in range(570, 960, 5):
            dt = session.replace(hour=minute // 60, minute=minute % 60, second=0)
            times.append(int(dt.timestamp()))
            volumes.append(200 if offset == 0 else 100)
    return {'timestamp': times, 'indicators': {'quote': [{'volume': volumes}]}}, day


def test_partial_bucket_and_extended_hours_are_excluded():
    chart, day = intraday()
    chart['timestamp'].extend([int(day.replace(hour=8).timestamp()), int(day.replace(hour=10, minute=10).timestamp())])
    chart['indicators']['quote'][0]['volume'].extend([1e9, 1e9])
    result = matched_relative_volume(chart, day.timestamp(), day)
    assert result['relative_volume'] == 2
    assert result['current_volume'] == 8 * 200
    assert result['historical_sessions'] == 20


@pytest.mark.parametrize('bad', [None, -1, float('nan'), float('inf')])
def test_missing_or_invalid_bucket_is_not_zero(bad):
    chart, day = intraday()
    index = chart['timestamp'].index(int(day.replace(hour=9, minute=30).timestamp()))
    chart['indicators']['quote'][0]['volume'][index] = bad
    assert matched_relative_volume(chart, day.timestamp(), day)['relative_volume'] is None


def test_stale_quote_and_insufficient_sessions_are_unavailable():
    chart, day = intraday()
    assert matched_relative_volume(chart, day.timestamp(), day + timedelta(minutes=11))['relative_volume'] is None
    chart['timestamp'] = chart['timestamp'][-78:]
    chart['indicators']['quote'][0]['volume'] = chart['indicators']['quote'][0]['volume'][-78:]
    assert matched_relative_volume(chart, day.timestamp(), day)['relative_volume'] is None


def test_zero_current_volume_is_valid():
    chart, day = intraday()
    chart['indicators']['quote'][0]['volume'][-78:] = [0] * 78
    assert matched_relative_volume(chart, day.timestamp(), day)['relative_volume'] == 0


def test_unknown_normalized_volume_cannot_use_daily_ratio():
    b = bundle()
    b['relative_volume_evidence'] = {'relative_volume': None, 'status': 'unavailable'}
    result = score_bundle(b)
    assert result['technicals']['relative_volume'] is None
    assert 'time-matched relative volume' in result['optional_missing_inputs']
    assert not any('Relative volume >1.2x' in reason for reason in result['momentum_reasons'])


def test_yahoo_401_refreshes_cookie_and_crumb():
    calls = []
    def handle(request):
        calls.append(request)
        if request.url.host == 'fc.yahoo.com':
            return httpx.Response(404, headers={'set-cookie': 'A3=test; Domain=.yahoo.com; Path=/'})
        if 'getcrumb' in request.url.path:
            assert 'A3=test' in request.headers.get('cookie', '')
            return httpx.Response(200, text='test-crumb')
        if request.url.params.get('crumb') != 'test-crumb':
            return httpx.Response(401)
        return httpx.Response(200, json={'quoteSummary': {'result': [{'summaryDetail': {'trailingPE': {'raw': 25}}}]}})
    provider = YahooMarketProvider()
    provider.client = httpx.Client(transport=httpx.MockTransport(handle))
    assert provider.yahoo_fundamentals('TEST')['trailingPE'] == 25
    assert len(calls) == 4


def test_empty_yahoo_summary_is_unavailable():
    p = YahooMarketProvider()
    p.client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={'quoteSummary': {'result': []}})))
    assert p.yahoo_fundamentals('TEST')['_status'].startswith('unavailable')


def test_finnhub_units_targets_and_cache():
    calls = []
    def handle(request):
        calls.append(request.url.path)
        values = {'metric': {'metric': {'peTTM': 25}},
                  'profile2': {'ticker': 'TEST', 'currency': 'USD', 'marketCapitalization': 1500, 'shareOutstanding': 50},
                  'price-target': {'symbol': 'TEST', 'targetMean': 30, 'targetLow': 20, 'targetHigh': 40, 'lastUpdated': datetime.now(timezone.utc).isoformat()}}
        return httpx.Response(200, json=values[request.url.path.split('/')[-1]])
    p = FinnhubAnalystProvider(token='secret')
    p.client = httpx.Client(transport=httpx.MockTransport(handle))
    result = p.market_evidence('TEST')
    assert result['marketCap'] == 1_500_000_000
    assert result['sharesOutstanding'] == 50_000_000
    assert result['trailingPE'] == 25
    assert result['targetMeanPrice'] == 30
    assert p.market_evidence('TEST')['_valuation_asof'] == result['_valuation_asof']
    assert len(calls) == 3


def test_forbidden_endpoint_is_cooled_down_and_secret_redacted():
    calls = []
    client = httpx.Client(transport=httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(403)))
    cache = EndpointCache()
    _, status = cache.fetch(client, 'price-target', 'ONE', 'SECRET', 3600)
    cache.fetch(client, 'price-target', 'TWO', 'SECRET', 3600)
    assert len(calls) == 1
    assert '403' in status and 'SECRET' not in status


@pytest.mark.parametrize('changed', [{'lastUpdated': '2020-01-01'}, {'symbol': 'OTHER'}, {'targetMean': -1}, {'targetHigh': 10}])
def test_invalid_targets_are_not_scored(changed):
    target = {'symbol': 'TEST', 'targetMean': 30, 'targetLow': 20, 'targetHigh': 40, 'lastUpdated': datetime.now(timezone.utc).isoformat(), **changed}
    p = FinnhubAnalystProvider(token='secret')
    p.client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=target if 'price-target' in r.url.path else {})))
    assert 'targetMeanPrice' not in p.market_evidence('TEST')


def test_negative_pe_cannot_earn_cheap_valuation_points():
    b = bundle()
    b['fundamentals'].update(forwardPE=-10, trailingPE=-20)
    assert score_bundle(b)['breakdown']['Valuation'] == 5


def test_matching_local_intervals_across_daylight_saving_change():
    chart, day = intraday(datetime(2026, 11, 10, 10, 12, tzinfo=NY))
    assert matched_relative_volume(chart, day.timestamp(), day)['relative_volume'] == 2


def test_request_budget_never_sleeps_or_exceeds_limit():
    calls = []
    cache = EndpointCache()
    client = httpx.Client(transport=httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(200, json={'metric': {'peTTM': 25}})))
    for i in range(50):
        cache.fetch(client, 'metric', str(i), 'secret', 21600)
    assert len(calls) == 45


def test_fallback_does_not_relabel_existing_yahoo_fields(monkeypatch):
    class Analyst:
        def recommendations(self, symbol):
            return {}
        def market_evidence(self, symbol):
            return {'trailingPE': 50, '_valuation_source': 'Finnhub', 'targetMeanPrice': 500,
                    '_target_source': 'Finnhub', '_target_status': 'available'}
    class SEC:
        def fundamentals(self, symbol):
            return {}
    p = YahooMarketProvider(sec_provider=SEC(), analyst_provider=Analyst())
    monkeypatch.setattr(p, 'yahoo_fundamentals', lambda symbol: {'forwardPE': 20, 'targetMeanPrice': 100})
    f = p.fundamentals('TEST')
    assert f['forwardPE'] == 20 and 'trailingPE' not in f
    assert f['targetMeanPrice'] == 100 and '_target_source' not in f
