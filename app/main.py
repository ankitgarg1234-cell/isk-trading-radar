from __future__ import annotations
import asyncio, json, os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import text
from .config import settings
from .db import engine, SessionLocal, Position, AnalysisRequest, Trade, PortfolioCash, PortfolioPreference, WatchlistItem, AnalysisSnapshot, RadarCandidate, Alert, storage_status
from .analysis_engine import parse_positions_from_text, portfolio_proposals
from .portfolio_engine import RISK_PROFILES, ACTION_RANK, normalise_profile, stock_risk_score, system_signal, active_level, analyst_label, suggested_position_size, account_risk, projected_risk, risk_band
from .scanner import radar
from .ai_engine import AIEngine

@asynccontextmanager
async def lifespan(app:FastAPI):
    task=None
    if not settings.disable_scanner:
        task=asyncio.create_task(radar.loop())
    yield
    if task:
        task.cancel()
        try:await task
        except asyncio.CancelledError:pass

app=FastAPI(title="ISK Trading Radar",version="1.0.0",lifespan=lifespan)
app.add_middleware(SessionMiddleware,secret_key=settings.session_secret,same_site="lax",https_only=False)
app.mount("/static",StaticFiles(directory="app/static"),name="static")
templates=Jinja2Templates(directory="app/templates")
ai_engine=AIEngine()

@app.middleware("http")
async def auth_guard(request:Request,call_next):
    public=request.url.path in {"/login","/health"} or request.url.path.startswith("/static/")
    if settings.auth_enabled and not public and not request.session.get("auth"):
        if request.url.path.startswith("/api/"):return JSONResponse({"detail":"authentication required"},status_code=401)
        return RedirectResponse("/login",status_code=303)
    return await call_next(request)

@app.get("/login",response_class=HTMLResponse)
def login_page(request:Request):return templates.TemplateResponse(request,"login.html",{"enabled":settings.auth_enabled,"error":None})
@app.post("/login",response_class=HTMLResponse)
def login(request:Request,username:str=Form(...),password:str=Form(...)):
    if not settings.auth_enabled or (username==settings.app_username and password==settings.app_password):
        request.session["auth"]=True;return RedirectResponse("/",status_code=303)
    return templates.TemplateResponse(request,"login.html",{"enabled":True,"error":"Invalid username or password"},status_code=401)
@app.post("/logout")
def logout(request:Request):request.session.clear();return RedirectResponse("/login",status_code=303)

@app.get("/health")
def health():
    try:
        with engine.connect() as conn:conn.execute(text("SELECT 1"))
        return {"status":"ok","database":"connected","storage":storage_status(),"scanner_running":radar.running,"last_scan":radar.last_scan,"market_open":radar.market_open()}
    except Exception as exc:return JSONResponse({"status":"degraded","database":str(exc)},status_code=503)

def latest_payloads(db, symbols=None):
    q=db.query(AnalysisSnapshot).order_by(AnalysisSnapshot.created_at.desc())
    if symbols:q=q.filter(AnalysisSnapshot.symbol.in_(symbols))
    out={}
    for s in q.limit(250).all():
        if s.symbol not in out:
            try:out[s.symbol]=json.loads(s.payload_json)
            except:out[s.symbol]={"symbol":s.symbol,"price":s.price,"deterministic_score":s.deterministic_score,"ai_score":s.ai_score,"action":s.action}
    return out

def _latest_and_previous(db, symbols: list[str] | None = None):
    q=db.query(AnalysisSnapshot).order_by(AnalysisSnapshot.created_at.desc())
    if symbols:q=q.filter(AnalysisSnapshot.symbol.in_(symbols))
    latest={}; previous={}
    for snap in q.limit(600).all():
        try: payload=json.loads(snap.payload_json)
        except Exception: payload={"symbol":snap.symbol,"price":snap.price,"deterministic_score":snap.deterministic_score,"ai_score":snap.ai_score,"action":snap.action}
        if snap.symbol not in latest: latest[snap.symbol]=payload
        elif snap.symbol not in previous: previous[snap.symbol]=payload
    return latest, previous


def _portfolio_profile(db) -> str:
    pref=db.query(PortfolioPreference).filter(PortfolioPreference.account=="Main").first()
    return normalise_profile(pref.risk_profile if pref else "MEDIUM")


def _currency_for(symbol: str, payload: dict) -> str:
    return str(payload.get("currency") or ("SEK" if symbol.endswith(".ST") else "USD")).upper()


def _fx_map(currencies: set[str], base_currency: str) -> dict[str,float|None]:
    out={base_currency:1.0}
    for cur in currencies:
        if cur==base_currency:continue
        try:out[cur]=radar.provider.fx_rate(cur,base_currency)
        except Exception:out[cur]=None
    return out


def _sum_cash(cash_rows, base_currency: str, fx: dict[str,float|None]):
    cash=0.0; reserve=0.0
    for c in cash_rows:
        cur=str(c.currency or base_currency).upper(); rate=fx.get(cur)
        if rate is None:continue
        cash += float(c.cash or 0)*rate; reserve += float(c.reserve_cash or 0)*rate
    return cash,reserve


def _actionable_sort(v: dict):
    signal=v.get("system_signal") or "WATCH"
    fit_rank={"GOOD FIT":0,"STRETCH":1,"ABOVE TARGET":2,"UNKNOWN":3}.get(v.get("risk_fit"),3)
    return (ACTION_RANK.get(signal,99), fit_rank, -float(v.get("ai_score") or 0), float(v.get("distance_pct") or 999))


def _dashboard_state(db):
    positions=db.query(Position).order_by(Position.symbol).all()
    trades=db.query(Trade).order_by(Trade.created_at.desc()).limit(20).all()
    analyses_req=db.query(AnalysisRequest).order_by(AnalysisRequest.created_at.desc()).limit(8).all()
    alerts=db.query(Alert).filter(Alert.acknowledged==False).order_by(Alert.created_at.desc()).limit(12).all()
    candidates=db.query(RadarCandidate).order_by(RadarCandidate.updated_at.desc()).limit(150).all()
    cash_rows=db.query(PortfolioCash).all()
    payloads, previous=_latest_and_previous(db)
    risk_profile=_portfolio_profile(db)

    # Use configured cash currency as account base. Without cash configuration,
    # use the first holding currency so tests/read-only views never need FX.
    if cash_rows:
        base_currency=str(cash_rows[0].currency or "SEK").upper()
    elif positions:
        first_payload=payloads.get(positions[0].symbol,{})
        base_currency=_currency_for(positions[0].symbol,first_payload)
    elif candidates:
        base_currency=_currency_for(candidates[0].symbol,payloads.get(candidates[0].symbol,{}))
    else:
        base_currency="SEK"
    currencies={str(c.currency or base_currency).upper() for c in cash_rows}
    for p in positions:currencies.add(_currency_for(p.symbol,payloads.get(p.symbol,{})))
    for c in candidates:
        a=payloads.get(c.symbol,{})
        if a:currencies.add(_currency_for(c.symbol,a))
    fx=_fx_map(currencies,base_currency)
    cash,reserve=_sum_cash(cash_rows,base_currency,fx)

    pos_views=[]; risk_rows=[]; owned={}
    for p in positions:
        a=payloads.get(p.symbol,{})
        price=float(a.get("price") or 0); pnl=(price/p.avg_cost-1)*100 if price and p.avg_cost else None
        currency=_currency_for(p.symbol,a); rate=fx.get(currency)
        value_base=(price*p.shares*rate) if price and rate else 0.0
        srisk=stock_risk_score(a) if a else 50.0
        sector=(a.get("fundamentals") or {}).get("sector") or "Unknown"
        row={"id":p.id,"symbol":p.symbol,"shares":p.shares,"avg_cost":p.avg_cost,"account":p.account,"price":price,"pnl":pnl,"action":a.get("action","ANALYSIS QUEUED"),"ai_score":a.get("ai_score"),"action_plan":a.get("action_plan"),"action_reason":a.get("action_reason"),"currency":currency,"decision_confidence":a.get("decision_confidence"),"value_base":value_base,"stock_risk":srisk,"sector":sector,"category":a.get("category"),"material_events":(a.get("news") or {}).get("material_events",0),"system_signal":system_signal(a,True) if a else "WATCH"}
        pos_views.append(row); risk_rows.append(row); owned[p.symbol]=row

    account=account_risk(risk_rows,cash,target_profile=risk_profile)
    portfolio_value=float(account.get("total") or cash)

    radar_views=[]
    for c in candidates:
        a=payloads.get(c.symbol) or {"symbol":c.symbol,"price":c.price,"deterministic_score":c.score,"ai_score":c.ai_score,"category":c.category,"action":c.action,"levels":{},"technicals":{},"news":{}}
        is_owned=c.symbol in owned
        level=active_level(a,is_owned)
        currency=_currency_for(c.symbol,a); rate=fx.get(currency)
        existing_value=owned.get(c.symbol,{}).get("value_base",0.0)
        sizing=suggested_position_size(a,cash=cash,reserve_cash=reserve,portfolio_value=portfolio_value,profile=risk_profile,fx_rate_to_base=rate or 0,existing_value=existing_value,whole_shares=True)
        projected=projected_risk(risk_rows,cash,a,sizing,rate or 0,risk_profile) if rate else None
        prev=previous.get(c.symbol) or {}
        changed=None
        if prev and prev.get("action") and prev.get("action")!=a.get("action"):
            changed=f"{prev.get('action')} → {a.get('action')}"
        fundamentals=a.get("fundamentals") or {}
        name=fundamentals.get("companyName") or a.get("company_name") or c.symbol
        signal=system_signal(a,is_owned)
        view={
            "symbol":c.symbol,"name":name,"price":float(a.get("price") or c.price or 0),"currency":currency,
            "category":a.get("category") or c.category,"score":float(a.get("deterministic_score") or c.score or 0),"ai_score":float(a.get("ai_score") or c.ai_score or 0),
            "analyst_score":a.get("analyst_score"),"analyst_label":analyst_label(a),"action":a.get("action") or c.action,"action_reason":a.get("action_reason") or "",
            "system_signal":signal,"owned":is_owned,"owned_shares":owned.get(c.symbol,{}).get("shares"),"owned_avg":owned.get(c.symbol,{}).get("avg_cost"),
            "level_label":level["label"],"level_value":level["value"],"distance":level["distance"],"distance_pct":level["distance_pct"],
            "target":(a.get("levels") or {}).get("target"),"stop":(a.get("levels") or {}).get("stop"),"risk_reward":a.get("risk_reward"),
            "expected_yield_pct":a.get("ai_expected_yield_pct") if a.get("ai_expected_yield_pct") is not None else a.get("expected_yield_pct"),
            "stock_risk":sizing.get("stock_risk",stock_risk_score(a)),"risk_band":risk_band(sizing.get("stock_risk",stock_risk_score(a))),"risk_fit":sizing.get("fit","UNKNOWN"),
            "suggested_shares":sizing.get("shares",0),"suggested_capital":sizing.get("capital",0),"sizing_reason":sizing.get("reason",""),
            "projected_risk":projected.get("score") if projected else None,"changed":changed,
            "updated_at":c.updated_at.isoformat() if c.updated_at else None,
        }
        radar_views.append(view)
    radar_views.sort(key=_actionable_sort)
    analyses_for_prop={s:a for s,a in payloads.items() if a}
    props=portfolio_proposals([{"symbol":p.symbol,"shares":p.shares,"avg_cost":p.avg_cost} for p in positions],analyses_for_prop,cash,reserve)
    summary={
        "buy_now":sum(v["system_signal"] in {"STRONG BUY","BUY","STARTER BUY"} and not v["owned"] for v in radar_views),
        "portfolio_actions":sum(v["system_signal"] in {"SELL","STRONG SELL","TAKE PROFIT"} and v["owned"] for v in radar_views),
        "deployable_cash":max(0,cash-reserve),
        "best_candidate":next((v for v in radar_views if v["system_signal"] in {"STRONG BUY","BUY","STARTER BUY"} and v.get("suggested_shares",0)>0 and not v["owned"]),None),
    }
    return {"positions":pos_views,"trades":trades,"analyses":analyses_req,"alerts":alerts,"candidates":radar_views,"cash":cash,"reserve":reserve,"proposals":props,"risk_profile":risk_profile,"risk_profiles":RISK_PROFILES,"account_risk":account,"base_currency":base_currency,"summary":summary}


@app.get("/",response_class=HTMLResponse)
def dashboard(request:Request):
    with SessionLocal() as db:state=_dashboard_state(db)
    return templates.TemplateResponse(request,"dashboard.html",{**state,"market_open":radar.market_open(),"scanner":radar,"now":datetime.now(timezone.utc),"auth_enabled":settings.auth_enabled,"live_poll_seconds":settings.live_poll_seconds,"storage":storage_status()})

@app.post("/risk-profile")
def set_risk_profile(risk_profile:str=Form(...)):
    profile=normalise_profile(risk_profile)
    with SessionLocal() as db:
        pref=db.query(PortfolioPreference).filter(PortfolioPreference.account=="Main").first()
        if not pref:pref=PortfolioPreference(account="Main");db.add(pref)
        pref.risk_profile=profile;pref.updated_at=datetime.now(timezone.utc);db.commit()
    return RedirectResponse("/",303)

def _analyze_symbols(symbols:list[str]):
    for symbol in symbols:
        try: radar.analyze_symbol(symbol, True)
        except Exception: pass

@app.post("/positions")
def add_position(background_tasks:BackgroundTasks,symbol:str=Form(...),shares:float=Form(...),avg_cost:float=Form(...),account:str=Form("Manual")):
    symbol=symbol.upper().strip(); account=account.strip() or "Manual"
    with SessionLocal() as db:
        p=db.query(Position).filter(Position.symbol==symbol,Position.account==account).first()
        if p:p.shares=shares;p.avg_cost=avg_cost
        else:db.add(Position(symbol=symbol,shares=shares,avg_cost=avg_cost,account=account))
        db.commit()
    background_tasks.add_task(_analyze_symbols,[symbol])
    return RedirectResponse("/",303)

@app.post("/positions/{position_id}/delete")
def delete_position(position_id:int):
    with SessionLocal() as db:
        p=db.get(Position,position_id)
        if p:db.delete(p);db.commit()
    return RedirectResponse("/",303)

@app.post("/cash")
def set_cash(account:str=Form("Main"),cash:float=Form(...),reserve_cash:float=Form(0),currency:str=Form("SEK")):
    with SessionLocal() as db:
        c=db.query(PortfolioCash).filter(PortfolioCash.account==account).first()
        if not c:c=PortfolioCash(account=account);db.add(c)
        c.cash=cash;c.reserve_cash=reserve_cash;c.currency=currency.upper();c.updated_at=datetime.now(timezone.utc);db.commit()
    return RedirectResponse("/",303)

@app.post("/trades")
def add_trade(symbol:str=Form(...),side:str=Form(...),shares:float=Form(...),price:float=Form(...),fees:float=Form(0),account:str=Form("Manual"),reason:str=Form("")):
    symbol=symbol.upper().strip();side=side.upper().strip()
    if side not in {"BUY","SELL"}:raise HTTPException(400,"side must be BUY or SELL")
    with SessionLocal() as db:
        db.add(Trade(symbol=symbol,side=side,shares=shares,price=price,fees=fees,account=account,reason=reason));db.commit()
    return RedirectResponse("/",303)

@app.post("/watchlist")
def add_watchlist(symbol:str=Form(...),source:str=Form("Manual")):
    symbol=symbol.upper().strip()
    with SessionLocal() as db:
        if not db.query(WatchlistItem).filter(WatchlistItem.symbol==symbol).first():db.add(WatchlistItem(symbol=symbol,source=source));db.commit()
    return RedirectResponse("/",303)

@app.post("/analyze")
def analyze_symbol(symbol:str=Form(...),source_note:str=Form("Manual")):
    raw=symbol.strip()
    try:
        resolved=radar.provider.resolve_symbol(raw)
        symbol=resolved["symbol"].upper().strip()
    except Exception as exc:
        raise HTTPException(400,f"Could not resolve company name or ticker: {raw}") from exc
    note=(source_note.strip() or "Manual")
    if raw.upper()!=symbol:
        note=f"{note} | entered: {raw} | resolved: {resolved.get('name') or symbol}"
    with SessionLocal() as db:db.add(AnalysisRequest(symbol=symbol,source_note=note));db.commit()
    try:radar.analyze_symbol(symbol,True)
    except Exception:pass
    return RedirectResponse(f"/analysis/{symbol}",303)

@app.get("/analysis/{symbol}",response_class=HTMLResponse)
def analysis_page(request:Request,symbol:str,refresh:int=0):
    symbol=symbol.upper().strip(); data=None
    if refresh:
        try:data=radar.analyze_symbol(symbol,True)
        except Exception:data=None
    if data is None:
        with SessionLocal() as db:
            s=db.query(AnalysisSnapshot).filter(AnalysisSnapshot.symbol==symbol).order_by(AnalysisSnapshot.created_at.desc()).first()
            if s:
                try:data=json.loads(s.payload_json)
                except:data=None
    if data is None:
        try:data=radar.analyze_symbol(symbol,True)
        except Exception as exc:data={"symbol":symbol,"error":str(exc),"deterministic_score":0,"analyst_score":None,"ai_score":0,"action":"DATA UNAVAILABLE","price":0,"breakdown":{},"levels":{},"technicals":{},"news":{"items":[],"label":"Unknown","score":0},"reasons":[],"risks":["Market-data request failed"],"sensitivity":[]}
    return templates.TemplateResponse(request,"analysis.html",{"d":data})

@app.get("/api/analysis/{symbol}")
def analysis_json(symbol:str, refresh:int=0):
    symbol=symbol.upper().strip()
    if refresh:
        return radar.analyze_symbol(symbol,True)
    with SessionLocal() as db:
        s=db.query(AnalysisSnapshot).filter(AnalysisSnapshot.symbol==symbol).order_by(AnalysisSnapshot.created_at.desc()).first()
        if s:
            try:return json.loads(s.payload_json)
            except Exception:pass
    return radar.analyze_symbol(symbol,True)

@app.post("/api/scan-now")
def scan_now():return radar.scan_once(force=True)

@app.get("/api/live")
def live():
    with SessionLocal() as db:
        state=_dashboard_state(db)
        return {"market_open":radar.market_open(),"scanner_running":radar.running,"last_scan":radar.last_scan,"last_error":radar.last_error,"universe_size":radar.universe_size,"universe_prefiltered":radar.last_universe_prefiltered,"universe_deep_candidates":radar.last_universe_candidates,"deep_analyzed":radar.last_deep_analyzed,"risk_profile":state["risk_profile"],"account_risk":state["account_risk"],"summary":state["summary"],"base_currency":state["base_currency"],"alerts":[{"id":a.id,"symbol":a.symbol,"title":a.title,"message":a.message,"severity":a.severity,"action":a.action} for a in state["alerts"]],"candidates":state["candidates"]}

@app.post("/alerts/{alert_id}/ack")
def ack_alert(alert_id:int):
    with SessionLocal() as db:
        a=db.get(Alert,alert_id)
        if a:a.acknowledged=True;db.commit()
    return JSONResponse({"ok":True})

@app.post("/api/import/parse-text")
async def import_parse_text(request:Request):
    data=await request.json(); return {"positions":parse_positions_from_text(data.get("text", ""))}

@app.post("/api/import/confirm")
async def import_confirm(request:Request, background_tasks:BackgroundTasks):
    data=await request.json(); rows=data.get("positions") or []; saved=0; saved_symbols=[]
    with SessionLocal() as db:
        for r in rows:
            try:
                sym=str(r["symbol"]).upper().strip(); shares=float(r["shares"]); avg=float(r["avg_cost"]); account=str(r.get("account") or "Screenshot")
                if not sym or shares<=0 or shares>=1_000_000 or avg<=0:continue
                p=db.query(Position).filter(Position.symbol==sym,Position.account==account).first()
                if p:p.shares=shares;p.avg_cost=avg
                else:db.add(Position(symbol=sym,shares=shares,avg_cost=avg,account=account))
                saved+=1; saved_symbols.append(sym)
            except:continue
        db.commit()
    if saved_symbols: background_tasks.add_task(_analyze_symbols, list(dict.fromkeys(saved_symbols)))
    return {"ok":True,"saved":saved,"analysis_queued":len(set(saved_symbols))}

@app.post("/api/import/screenshot")
async def import_screenshot(file:UploadFile=File(...)):
    if file.content_type and file.content_type not in {"image/png","image/jpeg","image/webp"}:raise HTTPException(415,"Upload a PNG, JPEG or WebP image")
    content=await file.read()
    if len(content)>settings.max_upload_mb*1024*1024:raise HTTPException(413,"Image too large")
    positions=ai_engine.extract_positions_from_image(content,file.content_type or "image/png")
    if positions is None:return JSONResponse({"ok":False,"needs_browser_ocr":True,"message":"AI image extraction is not configured. Browser OCR/manual confirmation can still be used."})
    return {"ok":True,"positions":positions}
