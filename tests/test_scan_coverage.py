"""Completed-work rotation and reserved opportunity-supply budgets."""
import json
from datetime import datetime, timedelta, timezone

from app.analysis_engine import SCORING_VERSION
from app.db import PaperPosition, RadarCandidate, SessionLocal, WatchlistItem
from app.scanner import RadarService
import app.scanner as scanner_module


class QuietUniverse:
    def us_equity_universe(self):
        return [{"symbol": f"U{i:03}"} for i in range(1000)]

    def discover(self, count=100):
        return [{"symbol": f"DISC{i}", "change_pct": 10 - i} for i in range(8)]

    def quick_scan(self, symbol):
        i = int(symbol[1:])
        return {"symbol": symbol, "price": 100,
                "avg_dollar_volume_20": 200_000_000 - i * 100_000,
                "scan_score": 5, "change_5_pct": 0, "change_20_pct": 0,
                "relative_volume": 1, "near_20d_high": .95}


def backlog(db, holdings=0):
    for i in range(20):
        db.add(RadarCandidate(symbol=f"STALE{i:02}", portfolio_rank_score=99 - i,
                              current_json=json.dumps({"scoring_version": "old-target-engine"})))
    for i in range(8):
        db.add(WatchlistItem(symbol=f"WATCH{i}", source="coverage test"))
    for i in range(holdings):
        db.add(PaperPosition(account="Optimizer Paper", symbol=f"HELD{i}",
                             shares=1, avg_cost=100, reason="Core Quality Lane"))


def test_slow_scan_uses_next_completed_slice_without_wall_clock_skip(monkeypatch):
    class Clock(datetime):
        point = datetime(2026, 10, 2, 13, 30, tzinfo=timezone.utc)

        @classmethod
        def now(cls, tz=None):
            return cls.point.astimezone(tz) if tz else cls.point.replace(tzinfo=None)

    monkeypatch.setattr(scanner_module, "datetime", Clock)
    service = RadarService(provider=QuietUniverse(), ai=object())
    first = service._universe_slice()
    assert first[0]["symbol"] == "U000"
    Clock.point += timedelta(seconds=250)
    # Asking again before completed work does not move the cursor.
    assert service._universe_slice()[0]["symbol"] == "U000"
    service._prefilter_universe(first)
    assert service._universe_slice()[0]["symbol"] == "U200"


def test_total_prefilter_failure_keeps_slice_for_retry():
    class Offline(QuietUniverse):
        def quick_scan(self, symbol):
            raise RuntimeError("offline")

    service = RadarService(provider=Offline(), ai=object())
    first = service._universe_slice()
    assert service._prefilter_universe(first) == []
    assert service._universe_slice()[0]["symbol"] == first[0]["symbol"]


def test_quiet_exploration_rotates_instead_of_repeating_the_top_liquid_names():
    service = RadarService(provider=QuietUniverse(), ai=object())
    entries = service.provider.us_equity_universe()[:200]
    selections = [{row["symbol"] for row in service._prefilter_universe(entries)} for _ in range(3)]
    assert [len(selected) for selected in selections] == [16, 16, 16]
    assert len(set.union(*selections)) == 48
    assert service.last_universe_explosive_candidates == 0
    assert service.last_universe_core_candidates == 16


def test_model_refresh_backlog_cannot_starve_reserved_discovery_and_broad_slots():
    with SessionLocal() as db:
        backlog(db, holdings=6)
        db.commit()
    service = RadarService(provider=QuietUniverse(), ai=object())
    queue = service.candidate_symbols()
    batch = queue[:service._candidate_batch_limit]
    assert len(batch) == 48
    assert all(f"HELD{i}" in batch[:6] for i in range(6))
    assert sum(symbol.startswith("DISC") for symbol in batch) == 8
    assert sum(symbol.startswith("U") for symbol in batch) == 16
    assert any(symbol.startswith("STALE") for symbol in batch)
    assert len(batch) == len(set(batch))


def test_reserved_broad_candidates_reach_the_actual_analysis_loop(monkeypatch):
    with SessionLocal() as db:
        backlog(db)
        db.commit()
    service = RadarService(provider=QuietUniverse(), ai=object())
    analyzed = []

    def analysis(symbol, **kwargs):
        analyzed.append(symbol)
        return {"symbol": symbol, "scoring_version": SCORING_VERSION, "price": 100,
                "lane_qualified": False, "deterministic_score": 50, "risk_reward": 0}

    monkeypatch.setattr(service, "analyze_symbol", analysis)
    monkeypatch.setattr(service, "_enrich_strategic_top_candidates", lambda: (False, []))
    monkeypatch.setattr(service, "_sync_rotation_alerts", lambda *args: None)
    monkeypatch.setattr(scanner_module, "run_paper_cycle", lambda *args, **kwargs: {"executed_orders": [], "blocked_orders": []})
    result = service.scan_once(force=True)
    assert result["analyzed"] == len(analyzed) == 48
    assert sum(symbol.startswith("U") for symbol in analyzed) == 16
    assert sum(symbol.startswith("DISC") for symbol in analyzed) == 8
    assert result["errors"] == []


def test_large_holdings_queue_keeps_both_exploration_sources_within_the_budget():
    with SessionLocal() as db:
        backlog(db, holdings=32)
        db.commit()
    service = RadarService(provider=QuietUniverse(), ai=object())
    batch = service.candidate_symbols()[:service._candidate_batch_limit]
    assert len(batch) == 48
    assert sum(symbol.startswith("HELD") for symbol in batch) == 32
    assert any(symbol.startswith("U") for symbol in batch)
    assert any(symbol.startswith("DISC") for symbol in batch)
