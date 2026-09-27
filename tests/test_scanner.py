from datetime import datetime
from zoneinfo import ZoneInfo
from app.scanner import RadarService
from app.db import SessionLocal, Position, WatchlistItem


class FakeProvider:
    def discover(self,count=60):
        return [{"symbol":"DISC","change_pct":25},{"symbol":"OTHER","change_pct":5}]


class FakeAI: pass


def test_market_open_regular_session_and_weekend():
    r=RadarService(provider=FakeProvider(),ai=FakeAI())
    ny=ZoneInfo("America/New_York")
    assert r.market_open(datetime(2026,9,28,10,0,tzinfo=ny)) is True
    assert r.market_open(datetime(2026,9,28,8,0,tzinfo=ny)) is False
    assert r.market_open(datetime(2026,9,27,12,0,tzinfo=ny)) is False


def test_existing_positions_and_watchlist_are_prioritized():
    with SessionLocal() as db:
        db.add(Position(symbol="HELD",shares=4,avg_cost=10,account="Test"))
        db.add(WatchlistItem(symbol="WATCH",source="Test"))
        db.commit()
    r=RadarService(provider=FakeProvider(),ai=FakeAI())
    syms=r.candidate_symbols()
    assert syms[0] == "HELD"
    assert "WATCH" in syms[:3]
    assert "DISC" in syms


def test_persist_generates_buy_alert_without_duplicate_on_same_action():
    from app.db import Alert, RadarCandidate
    r=RadarService(provider=FakeProvider(),ai=FakeAI())
    payload={
        "symbol":"BUYME","price":100,"deterministic_score":90,"analyst_score":80,"ai_score":93,
        "expected_yield_pct":25,"ai_expected_yield_pct":30,"category":"Core","action":"BUY NOW",
        "action_reason":"Buy level reached","levels":{"buy_low":98,"buy_high":101},
    }
    r.persist(payload); r.persist(payload)
    with SessionLocal() as db:
        assert db.query(RadarCandidate).filter(RadarCandidate.symbol=="BUYME").one().action == "BUY NOW"
        assert db.query(Alert).filter(Alert.symbol=="BUYME").count() == 1
