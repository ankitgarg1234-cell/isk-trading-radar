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
        "decision_confidence":"high","data_quality_pct":100,"missing_inputs":[],"optional_missing_inputs":[],
        "evidence_sources":{"price":{"source":"Yahoo Finance chart","status":"available"},"fundamentals":{"source":"SEC EDGAR/XBRL","status":"available"},"news":{"source":"Yahoo Finance search","status":"available","items":1},"analyst":{"source":"Finnhub recommendation trends","status":"available"},"sector":{"source":"SEC SIC mapping","status":"available","benchmark":"XLK"}},
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
    assert "ANALYZE ANY COMPANY OR SYMBOL" in body
    assert "TRADE LEDGER" in body
    assert "Capital movement proposals" not in body
    assert body.count("MANUAL RESEARCH QUEUE") == 1
    assert 'id="analyzeSymbol"' in body
    assert 'id="symbolSuggestions"' in body
    assert 'id="scannerCoreCount"' in body
    assert 'id="scannerExplosiveCount"' in body
    assert 'id="optimizerCore"' in body
    assert 'id="optimizerExplosive"' in body
    assert 'id="paperCoreCount"' in body
    assert 'id="paperExplosiveCount"' in body
    assert "Core Quality Lane" in body
    assert "Explosive Lane" in body


def test_manual_position_and_trade_ledger_persist():
    r=client.post('/positions',data={"symbol":"CRDO","shares":"10","avg_cost":"176","account":"Avanza"},follow_redirects=False)
    assert r.status_code == 303
    client.post('/trades',data={"symbol":"CRDO","side":"BUY","shares":"10","price":"176","fees":"2","account":"Avanza","reason":"Radar"},follow_redirects=False)
    with SessionLocal() as db:
        p=db.query(Position).filter(Position.symbol=="CRDO").one()
        t=db.query(Trade).filter(Trade.symbol=="CRDO").one()
        assert p.shares == 10 and p.avg_cost == 176
        assert t.side == "BUY" and t.reason == "Radar"


def test_confirm_screenshot_import_saves_positions(monkeypatch):
    monkeypatch.setattr(mainmod.radar,"analyze_symbol",lambda symbol,persist=True: full_payload(symbol))
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
    assert "EVIDENCE PROVENANCE" in body
    assert "SEC EDGAR/XBRL" in body


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
        payload=full_payload("XYZ"); payload["price"]=50; payload["entry_zone_status"]="PRIMARY_BUY"; payload["levels"].update({"buy_low":48,"buy_high":52,"stop":44,"target":70})
        db.add(RadarCandidate(symbol="XYZ",category="Core",action="BUY NOW",score=90,ai_score=93,price=50,portfolio_rank_score=90,current_json=json.dumps(payload)))
        db.add(Alert(symbol="XYZ",alert_type="buy_level",severity="high",title="XYZ: BUY",message="buy level",action="BUY"))
        db.commit()
    r=client.get('/api/live')
    assert r.status_code == 200
    d=r.json()
    assert d["candidates"][0]["symbol"] == "XYZ"
    assert d["alerts"][0]["action"] == "BUY"


def test_analysis_json_uses_saved_snapshot():
    p=full_payload("JSONX")
    with SessionLocal() as db:
        db.add(AnalysisSnapshot(symbol="JSONX",price=100,deterministic_score=88,analyst_score=80,ai_score=92,expected_yield_pct=25,ai_expected_yield_pct=30,category="Core",action="BUY NOW",payload_json=json.dumps(p)))
        db.commit()
    r=client.get('/api/analysis/JSONX')
    assert r.status_code == 200
    assert r.json()["ai_score"] == 92


def test_confirm_import_rejects_account_number_as_share_count(monkeypatch):
    monkeypatch.setattr(mainmod.radar,"analyze_symbol",lambda symbol,persist=True: full_payload(symbol))
    r=client.post('/api/import/confirm',json={"positions":[{"symbol":"O","shares":40262928,"avg_cost":4,"account":"Screenshot"}]})
    assert r.status_code == 200
    assert r.json()["saved"] == 0


def test_dashboard_shows_reason_for_position_action():
    payload=full_payload("WHYX")
    payload["action"]="REDUCE"
    payload["action_reason"]="Bearish evidence and weakening momentum are both present; P&L 4.2%"
    payload["action_plan"]={"suggested_shares":2,"actual_percent":25.0,"remaining_shares":6,"rationale":"Reduce risk while keeping a smaller position for reassessment"}
    with SessionLocal() as db:
        db.add(Position(symbol="WHYX",shares=8,avg_cost=95,account="Avanza"))
        db.add(AnalysisSnapshot(symbol="WHYX",price=99,deterministic_score=58,analyst_score=60,ai_score=55,expected_yield_pct=10,ai_expected_yield_pct=8,category="Core",action="REDUCE",payload_json=json.dumps(payload)))
        db.commit()
    r=client.get('/')
    assert r.status_code == 200
    assert "Why:" in r.text
    assert "Bearish evidence and weakening momentum are both present" in r.text


def test_health_reports_storage_backend():
    r=client.get('/health')
    assert r.status_code == 200
    storage=r.json()["storage"]
    assert "backend" in storage and "persistent" in storage


def test_dashboard_warns_when_using_local_sqlite():
    r=client.get('/')
    assert r.status_code == 200
    assert "Account history is not durable yet" in r.text


def test_position_survives_new_database_session():
    client.post('/positions',data={"symbol":"PERSIST","shares":"3","avg_cost":"42","account":"Avanza"},follow_redirects=False)
    with SessionLocal() as first:
        assert first.query(Position).filter(Position.symbol=="PERSIST").one().shares == 3
    # A page refresh/new request opens a completely new SQLAlchemy session.
    r=client.get('/')
    assert r.status_code == 200
    with SessionLocal() as second:
        assert second.query(Position).filter(Position.symbol=="PERSIST").one().avg_cost == 42


def test_manual_analysis_accepts_company_name(monkeypatch):
    monkeypatch.setattr(mainmod.radar.provider,"resolve_symbol",lambda q:{"symbol":"CRDO","name":"Credo Technology Group Holding Ltd","source":"test"})
    monkeypatch.setattr(mainmod.radar,"analyze_symbol",lambda symbol,persist=True: full_payload(symbol))
    r=client.post('/analyze',data={"symbol":"Credo Technology","source_note":"Recommended by friend"},follow_redirects=False)
    assert r.status_code == 303
    assert r.headers['location'] == '/analysis/CRDO'
    with SessionLocal() as db:
        req=db.query(mainmod.AnalysisRequest).filter(mainmod.AnalysisRequest.symbol=="CRDO").one()
        assert "Credo Technology" in req.source_note



def test_dashboard_has_actionable_filters_risk_profile_and_visible_levels(monkeypatch):
    from app.db import RadarCandidate, AnalysisSnapshot
    p=full_payload("FILTERX")
    p["currency"]="USD"
    p["entry_zone_status"]="PRIMARY_BUY"
    p["fundamentals"]={"companyName":"Filter Example Inc","sector":"Technology"}
    monkeypatch.setattr(mainmod.radar.provider,"fx_rate",lambda a,b:1.0)
    with SessionLocal() as db:
        db.add(RadarCandidate(symbol="FILTERX",category="Core",action="BUY NOW",score=88,ai_score=92,price=100))
        db.add(AnalysisSnapshot(symbol="FILTERX",price=100,deterministic_score=88,analyst_score=80,ai_score=92,expected_yield_pct=25,ai_expected_yield_pct=30,category="Core",action="BUY NOW",payload_json=json.dumps(p)))
        db.commit()
    r=client.get('/')
    assert r.status_code == 200
    for text in ["Search ticker or company name","Target risk","Active level","Distance","Suggested size","STRONG BUY","Filter Example Inc"]:
        assert text in r.text


def test_risk_profile_selection_persists():
    from app.db import PortfolioPreference
    r=client.post('/risk-profile',data={"risk_profile":"HIGH"},follow_redirects=False)
    assert r.status_code == 303
    with SessionLocal() as db:
        pref=db.query(PortfolioPreference).filter(PortfolioPreference.account=="Main").one()
        assert pref.risk_profile == "HIGH"


def test_live_api_exposes_decision_surface_fields(monkeypatch):
    from app.db import RadarCandidate, AnalysisSnapshot
    p=full_payload("LIVEUI")
    p["currency"]="USD";p["entry_zone_status"]="PRIMARY_BUY";p["fundamentals"]={"companyName":"Live UI Inc","sector":"Industrials"}
    monkeypatch.setattr(mainmod.radar.provider,"fx_rate",lambda a,b:1.0)
    with SessionLocal() as db:
        db.add(RadarCandidate(symbol="LIVEUI",category="Core",action="BUY NOW",score=88,ai_score=92,price=100))
        db.add(AnalysisSnapshot(symbol="LIVEUI",price=100,deterministic_score=88,analyst_score=80,ai_score=92,expected_yield_pct=25,ai_expected_yield_pct=30,category="Core",action="BUY NOW",payload_json=json.dumps(p)))
        db.commit()
    d=client.get('/api/live').json(); row=next(x for x in d["candidates"] if x["symbol"]=="LIVEUI")
    assert row["system_signal"] == "STRONG BUY"
    assert row["level_label"] == "Primary Buy"
    assert row["distance"] == "NOW"
    assert "risk_fit" in row and "suggested_shares" in row


def test_dashboard_has_filters_for_every_radar_decision_column(monkeypatch):
    from app.db import RadarCandidate, AnalysisSnapshot
    p=full_payload("COLFLT")
    p["currency"]="USD";p["entry_zone_status"]="PRIMARY_BUY";p["fundamentals"]={"companyName":"Column Filter Inc","sector":"Technology"}
    monkeypatch.setattr(mainmod.radar.provider,"fx_rate",lambda a,b:1.0)
    with SessionLocal() as db:
        db.add(RadarCandidate(symbol="COLFLT",category="Core",action="BUY NOW",score=88,ai_score=92,price=100))
        db.add(AnalysisSnapshot(symbol="COLFLT",price=100,deterministic_score=88,analyst_score=80,ai_score=92,expected_yield_pct=25,ai_expected_yield_pct=30,category="Core",action="BUY NOW",payload_json=json.dumps(p)))
        db.commit()
    r=client.get('/')
    assert r.status_code == 200
    body=r.text
    for element_id in [
        'radarSearch','radarStockOperator','radarStockValue','radarCategoryFilter','radarOwnedFilter',
        'radarPriceOperator','radarPriceValue','radarSignalOperator','radarSignalFilter','radarSystemMin','radarAiMin',
        'radarLevelOperator','radarLevelFilter','radarDistanceOperator','radarDistanceValue',
        'radarTargetMetric','radarTargetOperator','radarTargetValue',
        'radarAnalystOperator','radarAnalystFilter','radarAnalystMin',
        'radarFitOperator','radarFitFilter','radarRiskFilter','radarStockRiskMax',
        'radarSizeFilter','radarSizeMetric','radarSizeOperator','radarSizeValue',
        'columnFilterCount','radarResultCount'
    ]:
        assert f'id="{element_id}"' in body
    for attr in ['data-price=','data-level=','data-distance-label=','data-target=','data-stop=','data-rr=',
                 'data-analyst-label=','data-analyst-score=','data-risk-fit=',
                 'data-stock-risk=','data-suggested-shares=','data-suggested-capital=']:
        assert attr in body


def test_dashboard_uses_servicenow_style_inline_column_filters():
    r=client.get('/')
    assert r.status_code == 200
    body=r.text
    assert 'class="sn-filter-th' in body
    assert 'class="sn-filter-line"' in body
    assert '>Operator<' in body
    assert '>Metric<' in body
    assert 'class="sn-more"' in body
    assert 'column-filter-panel' not in body
    assert 'Clear filters' in body



def test_alert_drilldown_dismiss_and_snooze_endpoints():
    from app.db import Alert, AnalysisSnapshot, SessionLocal
    payload=full_payload("ALRT")
    payload["action_reason"]="Primary buy zone reached"
    payload["thesis_assessment"]={"invalidated":False,"reasons":[]}
    payload["sensitivity"]=[{"condition":"Bad guidance","new_score":55}]
    with SessionLocal() as db:
        db.add(AnalysisSnapshot(symbol="ALRT",price=100,deterministic_score=80,analyst_score=75,ai_score=84,expected_yield_pct=20,ai_expected_yield_pct=22,category="Core",action="BUY NOW",payload_json=json.dumps(payload)))
        a=Alert(symbol="ALRT",alert_type="buy_level",severity="high",title="ALRT: BUY NOW",message="Primary buy zone reached",action="BUY NOW")
        db.add(a);db.commit();aid=a.id
    r=client.get(f'/api/alerts/{aid}')
    assert r.status_code==200
    d=r.json();assert d["analysis"]["system_score"] is not None
    assert d["analysis"]["thesis_invalidated"] is False
    r=client.post(f'/alerts/{aid}/snooze',json={"minutes":60});assert r.status_code==200
    live=client.get('/api/live').json();assert all(a["id"]!=aid for a in live["alerts"])
    r=client.post(f'/alerts/{aid}/dismiss');assert r.status_code==200


def test_dashboard_alerts_are_clickable_and_have_cross_and_direct_conviction_filters():
    from app.db import Alert, RadarCandidate, SessionLocal
    with SessionLocal() as db:
        payload=full_payload("CLICK"); payload["entry_zone_status"]="PRIMARY_BUY"
        db.add(RadarCandidate(symbol="CLICK",category="Core",action="BUY NOW",score=88,ai_score=92,price=100,portfolio_rank_score=88,current_json=json.dumps(payload)))
        db.add(Alert(symbol="CLICK",alert_type="buy_level",severity="high",title="CLICK: BUY",message="reason",action="BUY"));db.commit()
    r=client.get('/')
    body=r.text
    assert 'class="alert-main alert-toggle"' in body
    assert 'class="icon-btn dismiss-alert"' in body
    assert 'data-alert-detail=' in body
    assert 'class="sn-conviction-row"' in body
    assert 'id="radarSystemMin"' in body and 'id="radarAiMin"' in body


def test_dashboard_can_render_from_compact_current_state_without_snapshot(monkeypatch):
    from app.db import RadarCandidate
    p=full_payload("COMPACT")
    p["currency"]="USD";p["fundamentals"]={"companyName":"Compact State Inc","sector":"Technology"}
    monkeypatch.setattr(mainmod.radar.provider,"fx_rate",lambda a,b:1.0)
    with SessionLocal() as db:
        db.add(RadarCandidate(symbol="COMPACT",category="Core",action="BUY NOW",score=88,ai_score=92,price=100,current_json=json.dumps(p)))
        db.commit()
    r=client.get('/')
    assert r.status_code==200
    assert "Compact State Inc" in r.text
    with SessionLocal() as db:
        assert db.query(AnalysisSnapshot).filter(AnalysisSnapshot.symbol=="COMPACT").count()==0


def test_live_endpoint_uses_short_server_cache(monkeypatch):
    calls={"n":0}
    original=mainmod._dashboard_state
    def wrapped(db):
        calls["n"]+=1
        return original(db)
    monkeypatch.setattr(mainmod,"_dashboard_state",wrapped)
    mainmod._invalidate_live_cache()
    assert client.get('/api/live').status_code==200
    assert client.get('/api/live').status_code==200
    assert calls["n"]==1


def test_live_polling_default_is_not_aggressive():
    from app.config import settings
    assert settings.live_poll_seconds >= 60
    assert settings.dashboard_cache_seconds >= 60


def test_attention_queue_hides_legacy_wait_watch_hold_alerts():
    from app.db import SessionLocal, Alert, RadarCandidate
    with SessionLocal() as db:
        db.add(Alert(symbol="OLDWAIT",alert_type="wait_more",severity="medium",title="OLDWAIT: WAIT MORE",message="legacy",action="WAIT MORE"))
        payload=full_payload("ACTION"); payload["entry_zone_status"]="PRIMARY_BUY"
        db.add(RadarCandidate(symbol="ACTION",category="Core",action="BUY NOW",score=88,ai_score=92,price=100,portfolio_rank_score=88,current_json=json.dumps(payload)))
        db.add(Alert(symbol="ACTION",alert_type="buy_level",severity="high",title="ACTION: BUY",message="actionable",action="BUY"))
        db.commit()
    live=client.get('/api/live').json()
    actions=[a['action'] for a in live['alerts']]
    assert 'WAIT MORE' not in actions
    assert 'BUY' in actions


def test_analysis_refresh_forces_strategic_official_refresh(monkeypatch):
    called = {}
    def fake_analyze(symbol, persist=True, strategic_refresh=False):
        called["symbol"] = symbol
        called["strategic_refresh"] = strategic_refresh
        return full_payload(symbol)
    monkeypatch.setattr(mainmod.radar, "analyze_symbol", fake_analyze)
    r = client.get('/analysis/NVDA?refresh=1')
    assert r.status_code == 200
    assert called == {"symbol": "NVDA", "strategic_refresh": True}


def test_manual_analysis_request_is_deduplicated_by_symbol(monkeypatch):
    monkeypatch.setattr(mainmod.radar.provider,"resolve_symbol",lambda q:{"symbol":"CRDO","name":"Credo Technology","source":"test"})
    monkeypatch.setattr(mainmod.radar,"analyze_symbol",lambda *args,**kwargs: full_payload("CRDO"))
    r1=client.post('/analyze',data={"symbol":"Credo Technology","source_note":"Manual"},follow_redirects=False)
    r2=client.post('/analyze',data={"symbol":"CRDO","source_note":"Analyst upgrade"},follow_redirects=False)
    assert r1.status_code == 303 and r2.status_code == 303
    with SessionLocal() as db:
        rows=db.query(mainmod.AnalysisRequest).filter(mainmod.AnalysisRequest.symbol=="CRDO").all()
        assert len(rows) == 1
        assert rows[0].source_note == "Analyst upgrade"
    body=client.get('/').text
    assert body.count('href="/analysis/CRDO"') >= 1
    queue_start=body.index("MANUAL RESEARCH QUEUE")
    queue_end=body.index("</section>",queue_start)
    assert body[queue_start:queue_end].count('href="/analysis/CRDO"') == 1


def test_symbol_search_autocomplete_returns_ticker_and_company(monkeypatch):
    monkeypatch.setattr(mainmod.radar.provider,"us_equity_universe",lambda:[
        {"symbol":"CRDO","name":"Credo Technology Group Holding Ltd","exchange":"NASDAQ"},
        {"symbol":"CRM","name":"Salesforce Inc","exchange":"NYSE"},
        {"symbol":"CRED","name":"Example Cred Corp","exchange":"NASDAQ"},
    ])
    r=client.get('/api/symbol-search?q=credo')
    assert r.status_code == 200
    rows=r.json()["results"]
    assert rows[0]["symbol"] == "CRDO"
    assert rows[0]["name"].startswith("Credo Technology")
    assert rows[0]["exchange"] == "NASDAQ"


def test_symbol_search_prioritizes_ticker_prefix(monkeypatch):
    monkeypatch.setattr(mainmod.radar.provider,"us_equity_universe",lambda:[
        {"symbol":"CRDO","name":"Credo Technology","exchange":"NASDAQ"},
        {"symbol":"CRM","name":"Salesforce Inc","exchange":"NYSE"},
        {"symbol":"CRC","name":"California Resources","exchange":"NYSE"},
    ])
    rows=client.get('/api/symbol-search?q=cr').json()["results"]
    assert [x["symbol"] for x in rows[:3]] == ["CRC","CRM","CRDO"]


def test_dashboard_deduplicates_preexisting_research_history():
    from datetime import datetime, timezone, timedelta
    now=datetime.now(timezone.utc)
    with SessionLocal() as db:
        db.add(mainmod.AnalysisRequest(symbol="DUP",source_note="older",created_at=now-timedelta(hours=2)))
        db.add(mainmod.AnalysisRequest(symbol="DUP",source_note="latest",created_at=now-timedelta(hours=1)))
        db.add(mainmod.AnalysisRequest(symbol="OTHER",source_note="manual",created_at=now))
        db.commit()
    body=client.get('/').text
    queue_start=body.index("MANUAL RESEARCH QUEUE")
    queue_end=body.index("</section>",queue_start)
    queue=body[queue_start:queue_end]
    assert queue.count('href="/analysis/DUP"') == 1
    assert "latest" in queue
    assert "older" not in queue


def test_live_api_exposes_lane_discovery_and_position_counts():
    r=client.get('/api/live')
    assert r.status_code == 200
    data=r.json()
    assert "universe_core_candidates" in data
    assert "universe_explosive_candidates" in data
    assert "core_quality" in data["optimizer"]
    assert "explosive" in data["optimizer"]
    assert "core_position_count" in data["paper"]
    assert "explosive_position_count" in data["paper"]
