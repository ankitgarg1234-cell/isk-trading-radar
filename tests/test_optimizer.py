import json

from fastapi.testclient import TestClient

from app.db import SessionLocal, RadarCandidate, PaperAccount, PaperPosition
from app.main import app
from app.paper_engine import run_paper_cycle
from app.portfolio_engine import build_optimizer_plan, candidate_rank_score

client=TestClient(app)


def payload(symbol, score=85, sector="Technology", expected=25, ai=88, price=100):
    return {
        "symbol":symbol,"price":price,"deterministic_score":score,"ai_score":ai,"analyst_score":78,
        "expected_yield_pct":expected,"risk_reward":3.0,"decision_confidence":"high","category":"Core",
        "entry_zone_status":"PRIMARY_BUY","action":"BUY NOW","negative_news_override":None,
        "thesis_assessment":{"invalidated":False},
        "levels":{"buy_low":price*.97,"buy_high":price*1.02,"better_low":price*.9,"better_high":price*.93,"stop":price*.88,"target":price*1.3},
        "technicals":{"atr":2,"relative_volume":1.2,"change20_pct":5},"news":{"material_events":0},
        "fundamentals":{"sector":sector},
    }


def test_optimizer_funnel_caps_visible_and_portfolio_slots():
    analyses={f"S{i:02d}":payload(f"S{i:02d}",score=95-i,sector=f"Sector{i%5}",expected=35-i*.3) for i in range(30)}
    plan=build_optimizer_plan(analyses,profile="HIGH",visible_limit=20,shortlist_limit=10,target_positions=6,max_positions=7,max_same_sector=2)
    assert len(plan["visible"])==20
    assert len(plan["shortlist"])==10
    assert len(plan["selected_new"])<=6
    assert all(r["bucket"] in {"INVEST NOW","SHORTLIST","RESERVE","PORTFOLIO","ROTATE IN"} for r in plan["visible"])


def test_optimizer_does_not_force_five_positions_when_only_three_qualify():
    analyses={
        "A":payload("A",90,"Technology"),"B":payload("B",86,"Healthcare"),"C":payload("C",82,"Industrials"),
        "D":payload("D",60,"Energy"),"E":payload("E",55,"Utilities"),
    }
    plan=build_optimizer_plan(analyses,profile="HIGH",target_positions=6,max_positions=7,min_rank_score=62)
    assert len(plan["selected_new"])==3


def test_ai_is_confirmation_not_part_of_portfolio_rank_math():
    a=payload("A",score=82,ai=20)
    b=payload("B",score=82,ai=98)
    assert candidate_rank_score(a)["score"] == candidate_rank_score(b)["score"]
    assert candidate_rank_score(a)["ai_confirmation"] != candidate_rank_score(b)["ai_confirmation"]


def test_dashboard_never_returns_more_than_twenty_radar_rows():
    with SessionLocal() as db:
        for i in range(30):
            p=payload(f"T{i:02d}",score=95-(i%20),sector=f"Sector{i%6}",expected=30-i*.2)
            db.add(RadarCandidate(symbol=p["symbol"],category="Core",action="BUY NOW",score=p["deterministic_score"],ai_score=p["ai_score"],price=100,portfolio_rank_score=99-i,current_json=json.dumps(p)))
        db.commit()
    d=client.get('/api/live').json()
    assert len(d["candidates"])==20
    assert d["optimizer"]["visible"]==20
    assert d["optimizer"]["max_positions"]==7


class BenchProvider:
    def chart(self,symbol,range_="5d",interval="1d"):
        return {"meta":{"regularMarketPrice":500.0}}


def test_paper_cycle_starts_at_10000_and_never_exceeds_seven_positions():
    sectors=["Technology","Healthcare","Industrials","Energy","Utilities","Financial Services","Consumer Cyclical"]
    with SessionLocal() as db:
        for i in range(10):
            p=payload(f"P{i}",score=95-i,sector=sectors[i%len(sectors)],expected=35-i,price=100+i)
            rank=candidate_rank_score(p)["score"]
            db.add(RadarCandidate(symbol=p["symbol"],category="Core",action="BUY NOW",score=p["deterministic_score"],ai_score=p["ai_score"],price=p["price"],portfolio_rank_score=rank,current_json=json.dumps(p)))
        db.commit()
    result=run_paper_cycle(BenchProvider(),force_rebalance=True)
    assert result["status"]=="ok"
    with SessionLocal() as db:
        acct=db.query(PaperAccount).one()
        positions=db.query(PaperPosition).all()
        assert acct.starting_cash==10000
        assert 1 <= len(positions) <= 7
        assert acct.cash >= 0
