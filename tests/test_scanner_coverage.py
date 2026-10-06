from app.scanner import RadarService
from app.config import settings
from dataclasses import replace
import app.scanner as scanner_module


class Provider:
    def us_equity_universe(self):
        return [{"symbol": f"U{i}"} for i in range(5758)]


def service(monkeypatch):
    radar = RadarService(provider=Provider(), ai=object())
    monkeypatch.setattr(radar, 'holding_symbols', lambda: [])
    monkeypatch.setattr(scanner_module, 'settings', replace(settings, scan_batch_size=32, universe_prefilter_batch_size=200))
    return radar


def test_live_deep_analysis_is_bounded_and_overflow_is_carried(monkeypatch):
    radar = service(monkeypatch)
    queue = [f"S{i}" for i in range(44)]
    batch, queued = radar._deep_analysis_batch(queue)
    assert batch == queue[:12] and queued == 44
    assert radar._deferred_analysis_symbols == queue[12:]


def test_fresh_live_candidates_preempt_old_overflow(monkeypatch):
    radar = service(monkeypatch)
    first = [f"S{i}" for i in range(60)]
    batch, _ = radar._deep_analysis_batch(first)
    assert len(batch) == 12
    assert radar._deferred_analysis_symbols == first[12:]

    fresh = [f"NEW{i}" for i in range(6)]
    next_batch, _ = radar._deep_analysis_batch(fresh)
    assert next_batch[:6] == fresh
    assert next_batch[6:] == first[12:18]
    assert first[18:] == radar._deferred_analysis_symbols[:42]


def test_holdings_remain_first_and_queue_is_deduplicated(monkeypatch):
    radar = service(monkeypatch)
    monkeypatch.setattr(radar, 'holding_symbols', lambda: ['HELD'])
    radar._deferred_analysis_symbols = ['DEFER', 'HELD']
    batch, queued = radar._deep_analysis_batch(['DEFER', 'HELD', 'NEW'])
    assert batch == ['HELD', 'DEFER', 'NEW'] and queued == 3


def test_quick_scan_cursor_advances_even_in_same_wall_clock_slot(monkeypatch):
    radar = service(monkeypatch)
    monkeypatch.setattr(radar, 'market_open', lambda now=None: False)
    first = radar._universe_slice()
    second = radar._universe_slice()
    assert first[0]['symbol'] == 'U0'
    assert second[0]['symbol'] == 'U200'
    assert not ({r['symbol'] for r in first} & {r['symbol'] for r in second})


def test_sequential_quick_scan_visits_every_listed_name(monkeypatch):
    radar = service(monkeypatch)
    monkeypatch.setattr(radar, 'market_open', lambda now=None: False)
    seen = set()
    for _ in range(29):
        rows = radar._universe_slice()
        assert len(rows) == 200
        seen.update(row['symbol'] for row in rows)
    assert len(seen) == 5758
