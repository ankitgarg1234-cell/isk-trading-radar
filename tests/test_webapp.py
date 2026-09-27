import json
from fastapi.testclient import TestClient
from app.main import app
import app.main as mainmod
from app.db import SessionLocal, Position, Trade, AnalysisSnapshot


client=TestClient(app)


def full_payload(symbol="TEST"):
    return {
        "symbol":symbol,"price":100,"provider":"fake","asof":"now","category":"Core","action":"BUY NOW","action_reason":"Test reason","position":None,
        "deterministic_score":88,"analyst_score":80,"ai_score":92,"risk_reward":3.2,"expected_yield_pct":25,"analyst_expected_yield_pct":20,"ai_expected_yield_pct":30,
        "deterministic_holding_period_min_days":30,"deterministic_holding_period_max_days":180,"analyst_holding_period_min_days":180,"analyst_holding_period_max_days":365,"holding_period_min_days":20,"holding_period_max_days":60,
        "levels":{"buy_low":95,"buy_high":100,"better_low":90,"better_high":93,"breakout":105,"stop":88,"target":130,"do_not_chase":112},
        "technicals":{"ema20":98,"ema50":94,"ema200":80,"rsi":58,"relative_volume":1.6,"change20_pct":8},
        "breakdown":{"Fundamentals":18,"Catalyst":12,"News":12,"Momentum":12,"Sector":8,"Valuation":8,"Analyst confirmation":4,"Risk/Reward":10},
        "fundamental_reasons":["Revenue growth 30.0% → 4/4"],"fundamental_confidence":"high","analyst_reasons":["Mean analyst target implies 20.0% upside"],"sector_reasons":["Sector benchmark above EMA20 +3"],"momentum_reasons":["Above EMA20 +3"],
        "negative_news_override":None,"mode":"test","adjustments":[{"points":4,"reason":"positive catalyst"}],"reasons":["positive catalyst"],"risks":["test risk"],"sensitivity":[{"condition":"break support","new_score":70}],
        "news":{"label":"Bullish","score":12,"material_events":1,"items":[{"title":"Good news","publisher":"Reuters","link":"","sentiment":"positive","materiality":"high","credibility":"high","priced_in":"fresh","thesis_impact":"supports"}]}
    }


def test_health_endpoint():
    r=client.get('/health')
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_dashboard_renders_shell_and_import_features():
    r=client.get('/')
    assert r.status_code == 200
    body=r.text
    assert "CONTINUOUS CROSS-SECTOR RADAR" in body
    assert "SCREENSHOT / OCR POSITION IMPORT" in body
    assert "ANALYZE ANY SYMBOL" in body
    assert "TRADE LEDGER" in body


def test_manual_position_and_trade_ledger_persist():
    r=client.post('/positions',data={"symbol":"CRDO","shares":"10","avg_cost":"176","account":"Avanza"},follow_redirects=False)
    assert r.status_code == 303
    client.post('/trades',data={"symbol":"CRDO","side":"BUY","shares":"10","price":"176","fees":"2","account":"Avanza","reason":"Radar"},follow_redirects=False)
    with SessionLocal() as db:
        p=db.query(Position).filter(Position.symbol=="CRDO").one()
        t=db.query(Trade).filter(Trade.symbol=="CRDO").one()
        assert p.shares == 10 and p.avg_cost == 176
        assert t.side == "BUY" and t.reason == "Radar"


def test_confirm_screenshot_import_saves_positions():
    r=client.post('/api/import/confirm',json={"positions":[{"symbol":"SRRK","shares":2,"avg_cost":26.4,"account":"Screenshot"}]})
    assert r.status_code == 200 and r.json()["saved"] == 1
    with SessionLocal() as db:
        assert db.query(Position).filter(Position.symbol=="SRRK").one().shares == 2


def test_screenshot_endpoint_has_free_browser_ocr_fallback(monkeypatch):
    monkeypatch.setattr(mainmod.ai_engine,"extract_positions_from_image",lambda content,mime: None)
    r=client.post('/api/import/screenshot',files={"file":("portfolio.png",b"fakepng","image/png")})
    assert r.status_code == 200
    assert r.json()["needs_browser_ocr"] is True


def test_screenshot_endpoint_accepts_ai_extraction(monkeypatch):
    monkeypatch.setattr(mainmod.ai_engine,"extract_positions_from_image",lambda content,mime:[{"symbol":"CRDO","shares":10,"avg_cost":176,"account":"Screenshot"}])
    r=client.post('/api/import/screenshot',files={"file":("portfolio.png",b"fakepng","image/png")})
    assert r.status_code == 200
    assert r.json()["positions"][0]["symbol"] == "CRDO"


def test_analysis_page_contains_explainability_and_levels():
    p=full_payload("TEST")
    with SessionLocal() as db:
        db.add(AnalysisSnapshot(symbol="TEST",price=100,deterministic_score=88,analyst_score=80,ai_score=92,expected_yield_pct=25,ai_expected_yield_pct=30,category="Core",action="BUY NOW",payload_json=json.dumps(p)))
        db.commit()
    r=client.get('/analysis/TEST')
    assert r.status_code == 200
    body=r.text
    assert "Why the scores were given" in body
    assert "Buy zone" in body
    assert "WHAT COULD CHANGE THE SCORE" in body
    assert "NEWS INTELLIGENCE" in body
    assert "Analyst score" in body


def test_manual_analysis_symbol_field_queues_request(monkeypatch):
    monkeypatch.setattr(mainmod.radar,"analyze_symbol",lambda symbol,persist=True: full_payload(symbol))
    r=client.post('/analyze',data={"symbol":"ABCD","source_note":"Recommended by friend"},follow_redirects=False)
    assert r.status_code == 303
    assert r.headers['location'] == '/analysis/ABCD'


def test_cash_and_watchlist_persist():
    from app.db import PortfolioCash, WatchlistItem
    client.post('/cash',data={"account":"Main","cash":"10000","reserve_cash":"3000","currency":"SEK"},follow_redirects=False)
    client.post('/watchlist',data={"symbol":"NVDA","source":"Manual"},follow_redirects=False)
    with SessionLocal() as db:
        c=db.query(PortfolioCash).filter(PortfolioCash.account=="Main").one()
        w=db.query(WatchlistItem).filter(WatchlistItem.symbol=="NVDA").one()
        assert c.cash == 10000 and c.reserve_cash == 3000
        assert w.source == "Manual"


def test_invalid_trade_side_rejected():
    r=client.post('/trades',data={"symbol":"CRDO","side":"HOLD","shares":"1","price":"100","fees":"0","account":"Manual","reason":"x"},follow_redirects=False)
    assert r.status_code == 400


def test_screenshot_rejects_non_image_file():
    r=client.post('/api/import/screenshot',files={"file":("x.txt",b"abc","text/plain")})
    assert r.status_code == 415


def test_live_api_returns_candidates_and_alerts():
    from app.db import RadarCandidate, Alert
    with SessionLocal() as db:
        db.add(RadarCandidate(symbol="XYZ",category="Core",action="BUY NOW",score=90,ai_score=93,price=50))
        db.add(Alert(symbol="XYZ",alert_type="buy_level",severity="high",title="XYZ: BUY NOW",message="buy level",action="BUY NOW"))
        db.commit()
    r=client.get('/api/live')
    assert r.status_code == 200
    d=r.json()
    assert d["candidates"][0]["symbol"] == "XYZ"
    assert d["alerts"][0]["action"] == "BUY NOW"


def test_analysis_json_uses_saved_snapshot():
    p=full_payload("JSONX")
    with SessionLocal() as db:
        db.add(AnalysisSnapshot(symbol="JSONX",price=100,deterministic_score=88,analyst_score=80,ai_score=92,expected_yield_pct=25,ai_expected_yield_pct=30,category="Core",action="BUY NOW",payload_json=json.dumps(p)))
        db.commit()
    r=client.get('/api/analysis/JSONX')
    assert r.status_code == 200
    assert r.json()["ai_score"] == 92
