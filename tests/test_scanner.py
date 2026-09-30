from datetime import datetime
from zoneinfo import ZoneInfo
from app.scanner import RadarService
from app.db import SessionLocal, Position, WatchlistItem


class FakeProvider:
    def discover(self,count=60):
        return [{"symbol":"DISC","change_pct":25},{"symbol":"OTHER","change_pct":5}]
    def us_equity_universe(self):
        return [{"symbol":f"U{i:03d}","name":f"Universe {i}"} for i in range(150)]
    def quick_scan(self,symbol):
        i=int(symbol[1:])
        return {"symbol":symbol,"scan_score":100-i,"qualifies":i < 20,"price":10+i,"change_5_pct":5,"change_20_pct":8,"relative_volume":1.5,"dollar_volume":2_000_000}


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


def test_marketwide_universe_is_not_limited_to_seed_symbols(monkeypatch):
    r=RadarService(provider=FakeProvider(),ai=FakeAI())
    syms=r.candidate_symbols()
    assert r.universe_size == 150
    assert r.last_universe_prefiltered > 12
    assert any(s.startswith("U") for s in syms)
    assert "DISC" in syms



def test_persist_refreshes_same_active_alert_instead_of_duplicating():
    from app.db import Alert
    r=RadarService(provider=FakeProvider(),ai=FakeAI())
    payload={
        "symbol":"DEDUP","price":100,"deterministic_score":90,"analyst_score":80,"ai_score":93,
        "expected_yield_pct":25,"ai_expected_yield_pct":30,"category":"Core","action":"BUY NOW",
        "action_reason":"first reason","levels":{"buy_low":98,"buy_high":101},
    }
    r.persist(payload)
    payload["action_reason"]="updated reason"
    r.persist(payload)
    with SessionLocal() as db:
        alerts=db.query(Alert).filter(Alert.symbol=="DEDUP",Alert.acknowledged==False).all()
        assert len(alerts)==1
        assert "deterministic conviction 90/100" in alerts[0].message


def test_persist_current_state_strips_heavy_history_and_throttles_snapshots():
    import json
    from app.db import AnalysisSnapshot, RadarCandidate
    r=RadarService(provider=FakeProvider(),ai=FakeAI())
    payload={
        "symbol":"LEAN","price":100,"deterministic_score":80,"analyst_score":75,"ai_score":84,
        "expected_yield_pct":20,"ai_expected_yield_pct":22,"category":"Core","action":"BUY NOW",
        "action_reason":"test","levels":{"buy_low":95,"buy_high":101,"target":125,"stop":90},
        "technicals":{"rsi":55},"breakdown":{"Fundamentals":18},"news":{"label":"Neutral","material_events":0,"items":[]},
        "history":[{"date":f"2026-01-{(i%28)+1:02d}","close":100+i} for i in range(250)],
        "sector_benchmark":{"symbol":"XLK","history":[{"date":"2026-01-01","close":1} for _ in range(120)]},
    }
    r.persist(payload)
    r.persist(payload)
    with SessionLocal() as db:
        cand=db.query(RadarCandidate).filter(RadarCandidate.symbol=="LEAN").one()
        current=json.loads(cand.current_json)
        assert "history" not in current
        assert "history" not in (current.get("sector_benchmark") or {})
        assert db.query(AnalysisSnapshot).filter(AnalysisSnapshot.symbol=="LEAN").count() == 1


def test_material_action_change_writes_new_compact_snapshot():
    import json
    from app.db import AnalysisSnapshot
    r=RadarService(provider=FakeProvider(),ai=FakeAI())
    payload={
        "symbol":"CHANGE","price":100,"deterministic_score":80,"analyst_score":75,"ai_score":84,
        "expected_yield_pct":20,"ai_expected_yield_pct":22,"category":"Core","action":"WATCH",
        "action_reason":"test","levels":{},"technicals":{},"breakdown":{"Fundamentals":18},
        "news":{"label":"Neutral","material_events":0,"items":[]},"history":[{"close":1} for _ in range(100)],
    }
    r.persist(payload)
    payload["action"]="BUY NOW"
    r.persist(payload)
    with SessionLocal() as db:
        rows=db.query(AnalysisSnapshot).filter(AnalysisSnapshot.symbol=="CHANGE").all()
        assert len(rows) == 2
        assert all("\"history\"" not in row.payload_json for row in rows)


def test_attention_buy_ladder_only_surfaces_agreed_entry_scores():
    from app.scanner import _attention_buy_signal
    base={"price":100,"decision_confidence":"high","negative_news_override":False,"thesis_assessment":{"invalidated":False}}
    cases=[
        (53,"PRIMARY_BUY",None),
        (67,"BETTER_BUY",None),
        (68,"PRIMARY_BUY","STARTER BUY"),
        (68,"BETTER_BUY","STARTER BUY"),
        (74,"BETTER_BUY","STARTER BUY"),
        (75,"PRIMARY_BUY","BUY"),
        (84,"BETTER_BUY","BUY"),
        (85,"PRIMARY_BUY","STRONG BUY"),
        (100,"BETTER_BUY","STRONG BUY"),
    ]
    for score,zone,expected in cases:
        payload={**base,"deterministic_score":score,"entry_zone_status":zone}
        action,_=_attention_buy_signal(payload)
        assert action == expected


def test_wait_more_buy_zone_does_not_create_attention_alert():
    from app.db import Alert
    r=RadarService(provider=FakeProvider(),ai=FakeAI())
    payload={
        "symbol":"WAIT53","price":100,"deterministic_score":53,"analyst_score":70,"ai_score":60,
        "expected_yield_pct":15,"ai_expected_yield_pct":16,"category":"Watch","action":"WAIT MORE",
        "action_reason":"Primary buy zone reached, but deterministic conviction is only 53/100",
        "entry_zone_status":"PRIMARY_BUY","decision_confidence":"high","negative_news_override":False,
        "thesis_assessment":{"invalidated":False},"levels":{"buy_low":98,"buy_high":101},
    }
    r.persist(payload)
    with SessionLocal() as db:
        assert db.query(Alert).filter(Alert.symbol=="WAIT53",Alert.acknowledged==False).count() == 0


def test_agreed_buy_attention_actions_are_persisted():
    from app.db import Alert
    r=RadarService(provider=FakeProvider(),ai=FakeAI())
    for symbol,score,zone,expected in [
        ("SB85",85,"PRIMARY_BUY","STRONG BUY"),
        ("BUY75",75,"BETTER_BUY","BUY"),
        ("ST74",74,"BETTER_BUY","STARTER BUY"),
        ("PB68",68,"PRIMARY_BUY","STARTER BUY"),
    ]:
        r.persist({
            "symbol":symbol,"price":100,"deterministic_score":score,"analyst_score":80,"ai_score":82,
            "expected_yield_pct":20,"ai_expected_yield_pct":22,"category":"Core","action":"WAIT MORE",
            "action_reason":"underlying radar state","entry_zone_status":zone,"decision_confidence":"high",
            "negative_news_override":False,"thesis_assessment":{"invalidated":False},"levels":{},
        })
        with SessionLocal() as db:
            a=db.query(Alert).filter(Alert.symbol==symbol,Alert.acknowledged==False).one()
            assert a.action == expected


def test_uncapped_policy_adds_new_buy_without_rotation_for_space(monkeypatch):
    import json
    from app.db import Alert, RadarCandidate
    with SessionLocal() as db:
        for sym in ["WEAK","H2","H3","H4","H5","H6"]:
            db.add(Position(symbol=sym,shares=10,avg_cost=100,account="Test"))
        weak={"symbol":"WEAK","price":95,"action":"HOLD — DON'T ADD","deterministic_score":50,"ai_score":55,"expected_yield_pct":4,"risk_reward":1.0,"decision_confidence":"high","entry_zone_status":"WATCH","levels":{},"fundamentals":{"sector":"Industrials"},"news":{"material_events":0}}
        best={"symbol":"BEST","price":50,"action":"BUY NOW","deterministic_score":90,"ai_score":94,"expected_yield_pct":35,"risk_reward":3.2,"decision_confidence":"high","entry_zone_status":"PRIMARY_BUY","levels":{"buy_low":48,"buy_high":52,"stop":42,"target":70},"fundamentals":{"sector":"Technology"},"news":{"material_events":0},"thesis_assessment":{"invalidated":False}}
        db.add(RadarCandidate(symbol="WEAK",action="HOLD — DON'T ADD",score=50,ai_score=55,price=95,portfolio_rank_score=30,current_json=json.dumps(weak)))
        db.add(RadarCandidate(symbol="BEST",action="BUY NOW",score=90,ai_score=94,price=50,portfolio_rank_score=90,current_json=json.dumps(best)))
        db.commit()
    from dataclasses import replace
    import app.scanner as scanmod
    monkeypatch.setattr(scanmod,"settings",replace(scanmod.settings,optimizer_live_gating=True))
    r=RadarService(provider=FakeProvider(),ai=FakeAI())
    r._sync_rotation_alerts()
    with SessionLocal() as db:
        assert db.query(Alert).filter(Alert.alert_type=="portfolio_swap",Alert.acknowledged==False).count() == 0
        a=db.query(Alert).filter(Alert.symbol=="BEST",Alert.alert_type=="buy_level",Alert.acknowledged==False).one()
        assert a.action in {"STRONG BUY","BUY","STARTER BUY"}

