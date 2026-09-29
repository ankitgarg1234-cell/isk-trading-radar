from __future__ import annotations
import asyncio, json, os, re, threading, time
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import text
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
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
_mobile_serializer=URLSafeTimedSerializer(settings.session_secret,salt="isk-radar-mobile-v1")

def _issue_mobile_token(username: str) -> str:
    return _mobile_serializer.dumps({"sub":username,"v":1})

def _verify_mobile_token(token: str) -> bool:
    try:
        payload=_mobile_serializer.loads(token,max_age=settings.mobile_token_ttl_seconds)
        return bool(payload.get("sub")) and int(payload.get("v") or 0)==1
    except (BadSignature,SignatureExpired,TypeError,ValueError):
        return False

def _mobile_bearer(request: Request) -> str:
    auth=str(request.headers.get("authorization") or "")
    if auth.lower().startswith("bearer "):
        return auth.split(" ",1)[1].strip()
    return ""

@app.middleware("http")
async def auth_guard(request:Request,call_next):
    path=request.url.path
    public=path in {"/login","/health","/api/mobile/login"} or path.startswith("/static/")
    if settings.auth_enabled and path.startswith("/api/mobile/") and not public:
        if not _verify_mobile_token(_mobile_bearer(request)):
            return JSONResponse({"detail":"mobile authentication required"},status_code=401)
        return await call_next(request)
    if settings.auth_enabled and not public and not request.session.get("auth"):
        if path.startswith("/api/"):return JSONResponse({"detail":"authentication required"},status_code=401)
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
        return {"status":"ok","database":"connected","storage":storage_status(),"scanner_running":radar.running,"last_scan":radar.last_scan,"market_open":radar.market_open(),"live_poll_seconds":settings.live_poll_seconds,"dashboard_cache_seconds":settings.dashboard_cache_seconds}
    except Exception as exc:return JSONResponse({"status":"degraded","database":str(exc)},status_code=503)

def _candidate_payload(c: RadarCandidate) -> dict:
    if getattr(c, "current_json", None):
        try:
            data=json.loads(c.current_json)
            if isinstance(data,dict) and data.get("symbol"):return data
        except Exception:
            pass
    return {
        "symbol":c.symbol,"price":c.price,"deterministic_score":c.score,"ai_score":c.ai_score,
        "category":c.category,"action":c.action,"levels":{},"technicals":{},"news":{},
    }


_LIVE_CACHE={"expires":0.0,"state":None,"scan_marker":None}
_LIVE_CACHE_LOCK=threading.Lock()

def _invalidate_live_cache():
    with _LIVE_CACHE_LOCK:
        _LIVE_CACHE["expires"]=0.0
        _LIVE_CACHE["state"]=None
        _LIVE_CACHE["scan_marker"]=None

def _cached_live_state():
    now=time.monotonic()
    marker=radar.last_scan.isoformat() if radar.last_scan else None
    with _LIVE_CACHE_LOCK:
        if (
            _LIVE_CACHE["state"] is not None
            and _LIVE_CACHE.get("scan_marker")==marker
            and now < _LIVE_CACHE["expires"]
        ):
            return _LIVE_CACHE["state"]
    with SessionLocal() as db:
        state=_dashboard_state(db)
    with _LIVE_CACHE_LOCK:
        _LIVE_CACHE["state"]=state
        _LIVE_CACHE["scan_marker"]=marker
        _LIVE_CACHE["expires"]=time.monotonic()+max(60,settings.dashboard_cache_seconds)
    return state


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


ATTENTION_ACTIONS={
    "STRONG BUY","BUY","STARTER BUY","CONSIDER BUY",
    # Backward-compatible names from pre-ladder alerts; a fresh scan rewrites
    # them to the four explicit attention-buy labels above.
    "BUY NOW","BREAKOUT BUY","ADD","CONSIDER BUYING NOW","CONSIDER STARTER BUY",
    "TAKE PARTIAL PROFIT","TAKE PROFIT","REBALANCE","ROTATE",
    "REDUCE","EXIT","SELL","STRONG SELL",
}

def _attentionworthy_alert(a: Alert) -> bool:
    return str(a.action or "").upper() in ATTENTION_ACTIONS

def _alert_priority(a: Alert) -> tuple[int, float]:
    action=str(a.action or "").upper()
    if action in {"EXIT","REDUCE","STRONG SELL","SELL"}: rank=0
    elif action in {"STRONG BUY","BUY","STARTER BUY","CONSIDER BUY"}: rank=1
    elif action in {"ROTATE","REBALANCE","TAKE PARTIAL PROFIT","TAKE PROFIT"}: rank=2
    else: rank=9
    ts=a.created_at.timestamp() if a.created_at else 0
    return (rank,-ts)

def _is_snoozed(a: Alert, now: datetime | None = None) -> bool:
    if not a.snoozed_until:return False
    now=now or datetime.now(timezone.utc)
    su=a.snoozed_until
    if su.tzinfo is None:su=su.replace(tzinfo=timezone.utc)
    return su > now

def _dashboard_state(db):
    positions=db.query(Position).order_by(Position.symbol).all()
    trades=db.query(Trade).order_by(Trade.created_at.desc()).limit(20).all()
    analyses_req=db.query(AnalysisRequest).order_by(AnalysisRequest.created_at.desc()).limit(8).all()
    raw_alerts=db.query(Alert).filter(Alert.acknowledged==False).order_by(Alert.created_at.desc()).limit(100).all()
    alerts=[a for a in raw_alerts if not _is_snoozed(a) and _attentionworthy_alert(a)]
    alerts=sorted(alerts,key=_alert_priority)[:20]
    candidates=db.query(RadarCandidate).order_by(RadarCandidate.updated_at.desc()).limit(150).all()
    # Ensure current holdings are always represented even if they fall outside the
    # most recently updated 150 Radar rows. This query returns compact current-state
    # rows, never historical payloads.
    have={c.symbol for c in candidates}
    missing=[p.symbol for p in positions if p.symbol not in have]
    if missing:
        candidates += db.query(RadarCandidate).filter(RadarCandidate.symbol.in_(missing)).all()
    cash_rows=db.query(PortfolioCash).all()
    payloads={}
    missing_current=[]
    for c in candidates:
        has_compact=False
        if getattr(c,"current_json",None):
            try:
                parsed=json.loads(c.current_json)
                if isinstance(parsed,dict) and parsed.get("symbol"):
                    payloads[c.symbol]=parsed;has_compact=True
            except Exception:
                pass
        if not has_compact:
            payloads[c.symbol]={
                "symbol":c.symbol,"price":c.price,"deterministic_score":c.score,"ai_score":c.ai_score,
                "category":c.category,"action":c.action,"levels":{},"technicals":{},"news":{},
            }
            missing_current.append(c.symbol)
    # Backward-compatibility bridge for a database created before ``current_json``.
    # It is used only until the next scan populates compact current-state rows.
    if missing_current:
        latest={}
        q=db.query(AnalysisSnapshot).filter(AnalysisSnapshot.symbol.in_(missing_current)).order_by(AnalysisSnapshot.created_at.desc())
        for snap in q.limit(max(10,len(missing_current)*2)).all():
            if snap.symbol in latest:continue
            try:latest[snap.symbol]=json.loads(snap.payload_json)
            except Exception:continue
        payloads.update(latest)
    # Holdings must remain position-aware even during the brief migration window
    # before a RadarCandidate current-state row exists. This fallback is bounded
    # to the user's holdings, not the broad market universe.
    missing_holdings=[p.symbol for p in positions if p.symbol not in payloads]
    for sym in missing_holdings:
        snap=db.query(AnalysisSnapshot).filter(AnalysisSnapshot.symbol==sym).order_by(AnalysisSnapshot.created_at.desc()).first()
        if snap:
            try:payloads[sym]=json.loads(snap.payload_json)
            except Exception:pass
    previous={c.symbol:{"action":c.previous_action} for c in candidates if getattr(c,"previous_action","")}
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
    _invalidate_live_cache()
    return RedirectResponse("/",303)

def _analyze_symbols(symbols:list[str]):
    for symbol in symbols:
        try: radar.analyze_symbol(symbol, True)
        except Exception: pass
    _invalidate_live_cache()

@app.post("/positions")
def add_position(background_tasks:BackgroundTasks,symbol:str=Form(...),shares:float=Form(...),avg_cost:float=Form(...),account:str=Form("Manual")):
    symbol=symbol.upper().strip(); account=account.strip() or "Manual"
    with SessionLocal() as db:
        p=db.query(Position).filter(Position.symbol==symbol,Position.account==account).first()
        if p:p.shares=shares;p.avg_cost=avg_cost
        else:db.add(Position(symbol=symbol,shares=shares,avg_cost=avg_cost,account=account))
        db.commit()
    _invalidate_live_cache()
    background_tasks.add_task(_analyze_symbols,[symbol])
    return RedirectResponse("/",303)

@app.post("/positions/{position_id}/delete")
def delete_position(position_id:int):
    with SessionLocal() as db:
        p=db.get(Position,position_id)
        if p:db.delete(p);db.commit()
    _invalidate_live_cache()
    return RedirectResponse("/",303)

@app.post("/cash")
def set_cash(account:str=Form("Main"),cash:float=Form(...),reserve_cash:float=Form(0),currency:str=Form("SEK")):
    with SessionLocal() as db:
        c=db.query(PortfolioCash).filter(PortfolioCash.account==account).first()
        if not c:c=PortfolioCash(account=account);db.add(c)
        c.cash=cash;c.reserve_cash=reserve_cash;c.currency=currency.upper();c.updated_at=datetime.now(timezone.utc);db.commit()
    _invalidate_live_cache()
    return RedirectResponse("/",303)

@app.post("/trades")
def add_trade(symbol:str=Form(...),side:str=Form(...),shares:float=Form(...),price:float=Form(...),fees:float=Form(0),account:str=Form("Manual"),reason:str=Form("")):
    symbol=symbol.upper().strip();side=side.upper().strip()
    if side not in {"BUY","SELL"}:raise HTTPException(400,"side must be BUY or SELL")
    with SessionLocal() as db:
        db.add(Trade(symbol=symbol,side=side,shares=shares,price=price,fees=fees,account=account,reason=reason));db.commit()
    _invalidate_live_cache()
    return RedirectResponse("/",303)

@app.post("/watchlist")
def add_watchlist(symbol:str=Form(...),source:str=Form("Manual")):
    symbol=symbol.upper().strip()
    with SessionLocal() as db:
        if not db.query(WatchlistItem).filter(WatchlistItem.symbol==symbol).first():db.add(WatchlistItem(symbol=symbol,source=source));db.commit()
    _invalidate_live_cache()
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
    _invalidate_live_cache()
    return RedirectResponse(f"/analysis/{symbol}",303)

@app.get("/analysis/{symbol}",response_class=HTMLResponse)
def analysis_page(request:Request,symbol:str,refresh:int=0):
    symbol=symbol.upper().strip(); data=None
    if refresh:
        try:data=radar.analyze_symbol(symbol,True)
        except Exception:data=None
    if data is None:
        with SessionLocal() as db:
            c=db.query(RadarCandidate).filter(RadarCandidate.symbol==symbol).first()
            if c:
                data=_candidate_payload(c)
            if not data or not data.get("symbol"):
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
        c=db.query(RadarCandidate).filter(RadarCandidate.symbol==symbol).first()
        if c and c.current_json:
            return _candidate_payload(c)
        s=db.query(AnalysisSnapshot).filter(AnalysisSnapshot.symbol==symbol).order_by(AnalysisSnapshot.created_at.desc()).first()
        if s:
            try:return json.loads(s.payload_json)
            except Exception:pass
    return radar.analyze_symbol(symbol,True)

@app.post("/api/scan-now")
def scan_now():
    result=radar.scan_once(force=True)
    _invalidate_live_cache()
    return result

@app.get("/api/live")
def live():
    state=_cached_live_state()
    return {"market_open":radar.market_open(),"scanner_running":radar.running,"last_scan":radar.last_scan,"last_error":radar.last_error,"universe_size":radar.universe_size,"universe_prefiltered":radar.last_universe_prefiltered,"universe_deep_candidates":radar.last_universe_candidates,"deep_analyzed":radar.last_deep_analyzed,"risk_profile":state["risk_profile"],"account_risk":state["account_risk"],"summary":state["summary"],"base_currency":state["base_currency"],"alerts":[{"id":a.id,"symbol":a.symbol,"title":a.title,"message":a.message,"severity":a.severity,"action":a.action,"alert_type":a.alert_type,"created_at":a.created_at.isoformat() if a.created_at else None} for a in state["alerts"]],"candidates":state["candidates"],"cache_seconds":settings.dashboard_cache_seconds}

@app.get("/api/alerts/{alert_id}")
def alert_detail(alert_id:int):
    with SessionLocal() as db:
        a=db.get(Alert,alert_id)
        if not a:raise HTTPException(404,"Alert not found")
        cand=db.query(RadarCandidate).filter(RadarCandidate.symbol==a.symbol).first()
        payload=_candidate_payload(cand) if cand else {}
        snap=None
        if not payload or not payload.get("symbol"):
            snap=db.query(AnalysisSnapshot).filter(AnalysisSnapshot.symbol==a.symbol).order_by(AnalysisSnapshot.created_at.desc()).first()
            if snap:
                try:payload=json.loads(snap.payload_json)
                except Exception:payload={}
        p=db.query(Position).filter(Position.symbol==a.symbol).order_by(Position.created_at.desc()).first()
        pd={"shares":p.shares,"avg_cost":p.avg_cost,"account":p.account} if p else None
        level=active_level(payload,bool(p)) if payload else {"label":"—","value":"—","distance":"—"}
        price=float(payload.get("price") or (snap.price if snap else 0) or 0)
        pnl=((price/p.avg_cost-1)*100) if p and p.avg_cost and price else None
        thesis=payload.get("thesis_assessment") or {}
        news=payload.get("news") or {}
        return {
            "alert":{"id":a.id,"symbol":a.symbol,"title":a.title,"message":a.message,"severity":a.severity,"action":a.action,"created_at":a.created_at.isoformat() if a.created_at else None},
            "analysis":{
                "price":price,"system_score":payload.get("deterministic_score"),"ai_score":payload.get("ai_score"),
                "analyst_score":payload.get("analyst_score"),"analyst_label":analyst_label(payload) if payload else "No consensus",
                "action":payload.get("action") or a.action,"reason":payload.get("action_reason") or a.message,
                "confidence":payload.get("decision_confidence"),"active_level":level,
                "news_label":news.get("label"),"material_events":news.get("material_events",0),
                "fundamental_score":(payload.get("breakdown") or {}).get("Fundamentals"),
                "fundamental_confidence":payload.get("fundamental_confidence"),
                "thesis_invalidated":bool(thesis.get("invalidated")),"thesis_reasons":thesis.get("reasons") or [],
                "sensitivity":payload.get("sensitivity") or [],"position":pd,"pnl":pnl,"action_plan":payload.get("action_plan"),
                "latest_news":[{"title":n.get("title"),"sentiment":n.get("sentiment"),"materiality":n.get("materiality"),"publisher":n.get("publisher")} for n in (news.get("items") or [])[:5]],
            }
        }

@app.post("/alerts/{alert_id}/ack")
def ack_alert(alert_id:int):
    with SessionLocal() as db:
        a=db.get(Alert,alert_id)
        if a:a.acknowledged=True;db.commit()
    _invalidate_live_cache()
    return JSONResponse({"ok":True})

@app.post("/alerts/{alert_id}/dismiss")
def dismiss_alert(alert_id:int):
    # Dismiss removes the alert from the active queue but preserves it as reviewed history.
    with SessionLocal() as db:
        a=db.get(Alert,alert_id)
        if a:a.acknowledged=True;db.commit()
    _invalidate_live_cache()
    return JSONResponse({"ok":True})

@app.post("/alerts/{alert_id}/snooze")
async def snooze_alert(alert_id:int, request:Request):
    try:data=await request.json()
    except Exception:data={}
    minutes=max(15,min(480,int(data.get("minutes") or 60)))
    with SessionLocal() as db:
        a=db.get(Alert,alert_id)
        if not a:raise HTTPException(404,"Alert not found")
        a.snoozed_until=datetime.now(timezone.utc).replace(tzinfo=None)+timedelta(minutes=minutes)
        db.commit()
    _invalidate_live_cache()
    return JSONResponse({"ok":True,"minutes":minutes})

def _mobile_alert_json(a: Alert) -> dict:
    return {"id":a.id,"symbol":a.symbol,"title":a.title,"message":a.message,"severity":a.severity,"action":a.action,"alert_type":a.alert_type,"created_at":a.created_at.isoformat() if a.created_at else None}

def _mobile_diagnostics() -> dict:
    db_status="connected"; db_error=None
    try:
        with engine.connect() as conn:conn.execute(text("SELECT 1"))
    except Exception as exc:
        db_status="degraded"; db_error=str(exc)[:300]
    now=datetime.now(timezone.utc); age=None
    if radar.last_scan:
        ls=radar.last_scan
        if ls.tzinfo is None:ls=ls.replace(tzinfo=timezone.utc)
        age=max(0,int((now-ls).total_seconds()))
    return {
        "database":{"status":db_status,"error":db_error,"storage":storage_status()},
        "scanner":{"running":radar.running,"market_open":radar.market_open(),"last_scan":radar.last_scan.isoformat() if radar.last_scan else None,"last_scan_age_seconds":age,"last_error":radar.last_error},
        "universe":{"size":radar.universe_size,"prefiltered":radar.last_universe_prefiltered,"deep_candidates":radar.last_universe_candidates,"deep_analyzed":radar.last_deep_analyzed},
        "cache":{"live_poll_seconds":settings.live_poll_seconds,"dashboard_cache_seconds":settings.dashboard_cache_seconds},
    }

def _mobile_find_candidate(message: str, state: dict) -> dict | None:
    upper=str(message or "").upper()
    for c in state.get("candidates") or []:
        sym=str(c.get("symbol") or "").upper()
        if sym and re.search(rf"(?<![A-Z0-9.]){re.escape(sym)}(?![A-Z0-9.])",upper):return c
    return None

def _mobile_copilot_fallback(mode: str, message: str, state: dict) -> dict:
    mode=mode.upper(); msg=str(message or "").strip(); low=msg.lower(); candidate=_mobile_find_candidate(msg,state)
    if mode=="ASK":
        if candidate:
            reply=(f"{candidate['symbol']} is currently {candidate.get('system_signal','WATCH')} with deterministic score "
                   f"{candidate.get('score',0):.0f}/100 and AI score {candidate.get('ai_score',0):.0f}/100. "
                   f"Active level: {candidate.get('level_label','—')}. {candidate.get('action_reason') or candidate.get('sizing_reason') or ''}").strip()
            return {"reply":reply,"mode":mode,"candidate":candidate,"proposal":None,"ai_assisted":False}
        buys=[c for c in state.get("candidates") or [] if c.get("system_signal") in {"STRONG BUY","BUY","STARTER BUY","CONSIDER BUY"}]
        if any(k in low for k in ("buy","opportun","attention","now")):
            top=buys[:3]
            if not top:return {"reply":"There are no actionable buy entries in the current attention ladder.","mode":mode,"proposal":None,"ai_assisted":False}
            line="; ".join(f"{c['symbol']} {c['system_signal']} ({c.get('score',0):.0f}/100)" for c in top)
            return {"reply":f"Current actionable Radar entries: {line}.","mode":mode,"proposal":None,"ai_assisted":False}
        return {"reply":f"Radar has {len(buys)} actionable buy entries. Account risk is {state.get('account_risk',{}).get('score','—')}/100 with target profile {state.get('risk_profile','MEDIUM')}.","mode":mode,"proposal":None,"ai_assisted":False}
    if mode=="CONFIGURE":
        for profile in ("LOW","MEDIUM","HIGH","AGGRESSIVE"):
            if profile.lower() in low:
                return {"reply":f"I can change the target portfolio risk profile to {profile}. Approval is required before I apply it.","mode":mode,"proposal":{"action":"SET_RISK_PROFILE","value":profile,"label":f"Set risk profile to {profile}"},"ai_assisted":False}
        return {"reply":"Configuration changes are approval-gated. In this build I can safely change the portfolio risk profile; more settings can be added to the allowlist.","mode":mode,"proposal":None,"ai_assisted":False}
    diag=_mobile_diagnostics()
    if mode=="DIAGNOSE":
        scan=diag["scanner"]; dbd=diag["database"]
        reply=f"Database: {dbd['status']}. Scanner running: {'yes' if scan['running'] else 'no'}. Market open: {'yes' if scan['market_open'] else 'no'}. Last scan age: {scan['last_scan_age_seconds'] if scan['last_scan_age_seconds'] is not None else 'unknown'} seconds."
        if scan.get("last_error"):reply+=f" Last scanner error: {scan['last_error']}."
        if dbd.get("error"):reply+=f" Database error: {dbd['error']}."
        return {"reply":reply,"mode":mode,"diagnostics":diag,"proposal":None,"ai_assisted":False}
    if any(k in low for k in ("scanner","scan","not updating","stale")):
        return {"reply":"I can force a fresh market scan and invalidate the live cache. This is a reversible runtime repair and requires approval.","mode":mode,"diagnostics":diag,"proposal":{"action":"RUN_SCAN_NOW","label":"Run fresh scan now"},"ai_assisted":False}
    if "cache" in low or "refresh" in low:
        return {"reply":"I can clear the server-side live dashboard cache. Approval is required.","mode":mode,"diagnostics":diag,"proposal":{"action":"CLEAR_LIVE_CACHE","label":"Clear live cache"},"ai_assisted":False}
    if candidate:
        return {"reply":f"I can force a fresh analysis for {candidate['symbol']}. Approval is required.","mode":mode,"diagnostics":diag,"proposal":{"action":"REANALYZE_SYMBOL","value":candidate['symbol'],"label":f"Reanalyse {candidate['symbol']}"},"ai_assisted":False}
    return {"reply":"Runtime diagnosis is available now. A source-code change or deployment fix will be shown as a proposed engineering change, but automatic GitHub/Render patch deployment is intentionally disabled until that connector is configured with approval and rollback gates.","mode":mode,"diagnostics":diag,"proposal":None,"requires_engineering_connector":True,"ai_assisted":False}

@app.post("/api/mobile/login")
async def mobile_login(request:Request):
    data=await request.json(); username=str(data.get("username") or ""); password=str(data.get("password") or "")
    ok=(not settings.auth_enabled) or (username==settings.app_username and password==settings.app_password)
    if not ok:raise HTTPException(401,"Invalid username or password")
    user=username or settings.app_username or "mobile"
    return {"token":_issue_mobile_token(user),"token_type":"bearer","expires_in":settings.mobile_token_ttl_seconds,"username":user}

@app.get("/api/mobile/bootstrap")
def mobile_bootstrap():
    state=_cached_live_state()
    return {
        "market_open":radar.market_open(),"scanner_running":radar.running,"last_scan":radar.last_scan.isoformat() if radar.last_scan else None,"last_error":radar.last_error,
        "universe_size":radar.universe_size,"risk_profile":state["risk_profile"],"account_risk":state["account_risk"],"summary":state["summary"],"base_currency":state["base_currency"],
        "cash":state["cash"],"reserve":state["reserve"],"positions":state["positions"],"proposals":state["proposals"],"candidates":state["candidates"],
        "alerts":[_mobile_alert_json(a) for a in state["alerts"]],"poll_seconds":settings.live_poll_seconds,
    }

@app.post("/api/mobile/risk-profile")
async def mobile_set_risk_profile(request:Request):
    data=await request.json(); profile=normalise_profile(str(data.get("risk_profile") or "MEDIUM"))
    with SessionLocal() as db:
        pref=db.query(PortfolioPreference).filter(PortfolioPreference.account=="Main").first()
        if not pref:pref=PortfolioPreference(account="Main");db.add(pref)
        pref.risk_profile=profile;pref.updated_at=datetime.now(timezone.utc);db.commit()
    _invalidate_live_cache();return {"ok":True,"risk_profile":profile}

@app.post("/api/mobile/analyze")
async def mobile_analyze(request:Request):
    data=await request.json(); raw=str(data.get("query") or data.get("symbol") or "").strip()
    if not raw:raise HTTPException(400,"Ticker or company name is required")
    try:resolved=radar.provider.resolve_symbol(raw); symbol=resolved["symbol"].upper().strip()
    except Exception as exc:raise HTTPException(400,f"Could not resolve company name or ticker: {raw}") from exc
    try:radar.analyze_symbol(symbol,True)
    except Exception:pass
    _invalidate_live_cache();return {"ok":True,"symbol":symbol,"name":resolved.get("name") or symbol}

@app.get("/api/mobile/analysis/{symbol}")
def mobile_analysis(symbol:str,refresh:int=0):
    return analysis_json(symbol,refresh)

@app.get("/api/mobile/diagnostics")
def mobile_diagnostics():
    return _mobile_diagnostics()

@app.post("/api/mobile/alerts/{alert_id}/ack")
def mobile_ack_alert(alert_id:int):
    return ack_alert(alert_id)

@app.post("/api/mobile/alerts/{alert_id}/dismiss")
def mobile_dismiss_alert(alert_id:int):
    return dismiss_alert(alert_id)

@app.post("/api/mobile/alerts/{alert_id}/snooze")
async def mobile_snooze_alert(alert_id:int,request:Request):
    return await snooze_alert(alert_id,request)

@app.post("/api/mobile/copilot")
async def mobile_copilot(request:Request):
    data=await request.json(); mode=str(data.get("mode") or "ASK").upper(); message=str(data.get("message") or "").strip()
    if mode not in {"ASK","CONFIGURE","DIAGNOSE","FIX"}:raise HTTPException(400,"Unsupported copilot mode")
    state=_cached_live_state(); return _mobile_copilot_fallback(mode,message,state)

@app.post("/api/mobile/copilot/apply")
async def mobile_copilot_apply(request:Request):
    data=await request.json(); action=str(data.get("action") or "").upper(); value=str(data.get("value") or "").strip().upper()
    if action=="SET_RISK_PROFILE":
        profile=normalise_profile(value)
        with SessionLocal() as db:
            pref=db.query(PortfolioPreference).filter(PortfolioPreference.account=="Main").first()
            if not pref:pref=PortfolioPreference(account="Main");db.add(pref)
            pref.risk_profile=profile;pref.updated_at=datetime.now(timezone.utc);db.commit()
        _invalidate_live_cache();return {"ok":True,"message":f"Risk profile changed to {profile}."}
    if action=="CLEAR_LIVE_CACHE":
        _invalidate_live_cache();return {"ok":True,"message":"Live dashboard cache cleared."}
    if action=="RUN_SCAN_NOW":
        result=radar.scan_once(force=True);_invalidate_live_cache();return {"ok":True,"message":"Fresh scan completed.","result":result}
    if action=="REANALYZE_SYMBOL":
        if not re.fullmatch(r"[A-Z0-9.\-]{1,16}",value):raise HTTPException(400,"Invalid symbol")
        radar.analyze_symbol(value,True);_invalidate_live_cache();return {"ok":True,"message":f"{value} reanalysis completed."}
    raise HTTPException(400,"Action is not in the mobile repair allowlist")

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
    _invalidate_live_cache()
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
