from __future__ import annotations
import asyncio, json, os, threading, time
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import text
from .config import settings
from .db import engine, SessionLocal, Position, AnalysisRequest, Trade, PortfolioCash, PortfolioPreference, WatchlistItem, AnalysisSnapshot, RadarCandidate, Alert, storage_status
from .analysis_engine import parse_positions_from_text
from .portfolio_engine import RISK_PROFILES, ACTION_RANK, normalise_profile, stock_risk_score, system_signal, active_level, analyst_label, suggested_position_size, account_risk, projected_risk, risk_band, build_optimizer_plan, candidate_rank_score
from .paper_engine import paper_status, reset_paper, run_paper_cycle
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

    # Read only the strongest/freshest compact rows. Full-market scanning continues
    # in the background; the dashboard is intentionally capped at 20 opportunities.
    fresh_cutoff=datetime.now(timezone.utc)-timedelta(days=4)
    candidates=(db.query(RadarCandidate)
        .filter(RadarCandidate.updated_at >= fresh_cutoff)
        .order_by(RadarCandidate.portfolio_rank_score.desc(),RadarCandidate.updated_at.desc())
        .limit(120).all())
    if not candidates or max((float(getattr(c,"portfolio_rank_score",0) or 0) for c in candidates),default=0)<=0:
        candidates=db.query(RadarCandidate).order_by(RadarCandidate.updated_at.desc()).limit(150).all()
    have={c.symbol for c in candidates}
    missing=[p.symbol for p in positions if p.symbol not in have]
    if missing:
        candidates += db.query(RadarCandidate).filter(RadarCandidate.symbol.in_(missing)).all()
    candidate_map={c.symbol:c for c in candidates}

    cash_rows=db.query(PortfolioCash).all()
    payloads={};missing_current=[]
    for c in candidates:
        has_compact=False
        if getattr(c,"current_json",None):
            try:
                parsed=json.loads(c.current_json)
                if isinstance(parsed,dict) and parsed.get("symbol"):
                    payloads[c.symbol]=parsed;has_compact=True
            except Exception:pass
        if not has_compact:
            payloads[c.symbol]={"symbol":c.symbol,"price":c.price,"deterministic_score":c.score,"ai_score":c.ai_score,"category":c.category,"action":c.action,"levels":{},"technicals":{},"news":{}}
            missing_current.append(c.symbol)
    if missing_current:
        latest={}
        q=db.query(AnalysisSnapshot).filter(AnalysisSnapshot.symbol.in_(missing_current)).order_by(AnalysisSnapshot.created_at.desc())
        for snap in q.limit(max(10,len(missing_current)*2)).all():
            if snap.symbol in latest:continue
            try:latest[snap.symbol]=json.loads(snap.payload_json)
            except Exception:continue
        payloads.update(latest)
    missing_holdings=[p.symbol for p in positions if p.symbol not in payloads]
    for sym in missing_holdings:
        snap=db.query(AnalysisSnapshot).filter(AnalysisSnapshot.symbol==sym).order_by(AnalysisSnapshot.created_at.desc()).first()
        if snap:
            try:payloads[sym]=json.loads(snap.payload_json)
            except Exception:pass
    previous={c.symbol:{"action":c.previous_action} for c in candidates if getattr(c,"previous_action","")}
    risk_profile=_portfolio_profile(db)

    if cash_rows:base_currency=str(cash_rows[0].currency or "SEK").upper()
    elif positions:base_currency=_currency_for(positions[0].symbol,payloads.get(positions[0].symbol,{}))
    elif candidates:base_currency=_currency_for(candidates[0].symbol,payloads.get(candidates[0].symbol,{}))
    else:base_currency="SEK"
    currencies={str(c.currency or base_currency).upper() for c in cash_rows}
    for p in positions:currencies.add(_currency_for(p.symbol,payloads.get(p.symbol,{})))
    for c in candidates:
        a=payloads.get(c.symbol,{})
        if a:currencies.add(_currency_for(c.symbol,a))
    fx=_fx_map(currencies,base_currency)
    cash,reserve=_sum_cash(cash_rows,base_currency,fx)

    pos_views=[];risk_rows=[];owned={}
    for p in positions:
        a=payloads.get(p.symbol,{})
        price=float(a.get("price") or 0);pnl=(price/p.avg_cost-1)*100 if price and p.avg_cost else None
        currency=_currency_for(p.symbol,a);rate=fx.get(currency)
        value_base=(price*p.shares*rate) if price and rate else 0.0
        srisk=stock_risk_score(a) if a else 50.0
        sector=(a.get("fundamentals") or {}).get("sector") or "Unknown"
        rank=candidate_rank_score(a) if a else {"score":0}
        row={"id":p.id,"symbol":p.symbol,"shares":p.shares,"avg_cost":p.avg_cost,"account":p.account,"price":price,"pnl":pnl,"action":a.get("action","ANALYSIS QUEUED"),"ai_score":a.get("ai_score"),"action_plan":a.get("action_plan"),"action_reason":a.get("action_reason"),"currency":currency,"decision_confidence":a.get("decision_confidence"),"value_base":value_base,"stock_risk":srisk,"sector":sector,"category":a.get("category"),"material_events":(a.get("news") or {}).get("material_events",0),"system_signal":system_signal(a,True) if a else "WATCH","portfolio_rank_score":rank.get("score",0)}
        pos_views.append(row);risk_rows.append(row);owned[p.symbol]=row

    account=account_risk(risk_rows,cash,target_profile=risk_profile)
    portfolio_value=float(account.get("total") or cash)
    optimizer=build_optimizer_plan(
        payloads,set(owned),profile=risk_profile,
        visible_limit=settings.optimizer_visible_limit,
        shortlist_limit=settings.optimizer_shortlist_limit,
        target_positions=settings.optimizer_target_positions,
        max_positions=settings.optimizer_max_positions,
        min_rank_score=settings.optimizer_min_rank_score,
        max_same_sector=settings.optimizer_max_same_sector,
        rotation_gap=settings.optimizer_rotation_gap,
        rotation_yield_gap=settings.optimizer_rotation_yield_gap,
    )
    plan_by_symbol={r["symbol"]:r for r in optimizer["visible"]}

    radar_views=[]
    for rankrow in optimizer["visible"]:
        sym=rankrow["symbol"]
        c=candidate_map.get(sym)
        a=payloads.get(sym) or {}
        is_owned=sym in owned
        level=active_level(a,is_owned)
        currency=_currency_for(sym,a);rate=fx.get(currency)
        existing_value=owned.get(sym,{}).get("value_base",0.0)
        optimizer_approved=rankrow.get("bucket") in {"INVEST NOW","ROTATE IN"}
        if optimizer_approved or is_owned:
            sizing=suggested_position_size(a,cash=cash,reserve_cash=reserve,portfolio_value=portfolio_value,profile=risk_profile,fx_rate_to_base=rate or 0,existing_value=existing_value,whole_shares=True)
        else:
            sizing={"shares":0,"capital":0,"fit":rankrow.get("risk_fit","UNKNOWN"),"stock_risk":rankrow.get("stock_risk",stock_risk_score(a)),"reason":"No capital allocated: optimizer did not select this candidate for the 5–7 stock portfolio"}
        projected=projected_risk(risk_rows,cash,a,sizing,rate or 0,risk_profile) if rate and sizing.get("shares") else None
        prev=previous.get(sym) or {};changed=None
        if prev and prev.get("action") and prev.get("action")!=a.get("action"):changed=f"{prev.get('action')} → {a.get('action')}"
        fundamentals=a.get("fundamentals") or {};name=fundamentals.get("companyName") or a.get("company_name") or sym
        signal=system_signal(a,is_owned)
        view={
            "symbol":sym,"name":name,"price":float(a.get("price") or (c.price if c else 0) or 0),"currency":currency,
            "category":a.get("category") or (c.category if c else "Watch"),"score":float(a.get("deterministic_score") or (c.score if c else 0) or 0),"ai_score":float(a.get("ai_score") or (c.ai_score if c else 0) or 0),
            "analyst_score":a.get("analyst_score"),"analyst_label":analyst_label(a),"action":a.get("action") or (c.action if c else "WATCH"),"action_reason":a.get("action_reason") or "",
            "system_signal":signal,"owned":is_owned,"owned_shares":owned.get(sym,{}).get("shares"),"owned_avg":owned.get(sym,{}).get("avg_cost"),
            "level_label":level["label"],"level_value":level["value"],"distance":level["distance"],"distance_pct":level["distance_pct"],
            "target":(a.get("levels") or {}).get("target"),"stop":(a.get("levels") or {}).get("stop"),"risk_reward":a.get("risk_reward"),
            "expected_yield_pct":a.get("expected_yield_pct"),
            "stock_risk":sizing.get("stock_risk",stock_risk_score(a)),"risk_band":risk_band(sizing.get("stock_risk",stock_risk_score(a))),"risk_fit":sizing.get("fit",rankrow.get("risk_fit","UNKNOWN")),
            "suggested_shares":sizing.get("shares",0),"suggested_capital":sizing.get("capital",0),"sizing_reason":sizing.get("reason",""),
            "projected_risk":projected.get("score") if projected else None,"changed":changed,
            "updated_at":c.updated_at.isoformat() if c and c.updated_at else None,
            "market_rank":rankrow.get("market_rank"),"portfolio_rank_score":rankrow.get("rank_score"),"optimizer_bucket":rankrow.get("bucket"),"optimizer_action":rankrow.get("optimizer_action"),
            "rank_components":rankrow.get("rank_components"),"ai_confirmation":rankrow.get("ai_confirmation"),"analyst_confirmation":rankrow.get("analyst_confirmation"),
        }
        radar_views.append(view)

    approved_buy_symbols={r["symbol"] for r in optimizer["selected_new"]}
    alerts=[]
    for a in raw_alerts:
        if _is_snoozed(a) or not _attentionworthy_alert(a):continue
        if settings.optimizer_live_gating and a.alert_type=="buy_level" and a.symbol not in approved_buy_symbols:continue
        alerts.append(a)
    alerts=sorted(alerts,key=_alert_priority)[:20]

    view_by_symbol={v["symbol"]:v for v in radar_views}
    props=[]
    for r in optimizer["selected_new"]:
        v=view_by_symbol.get(r["symbol"],{})
        detail=f"Portfolio rank #{r['market_rank']} • priority {r['rank_score']:.1f}/100 • {r['entry_signal']} • deterministic expected return {r['expected_yield_pct']:.1f}%."
        if v.get("suggested_shares"):
            detail += f" Suggested {v['suggested_shares']} shares (≈ {v.get('suggested_capital',0):.0f} {base_currency})."
        props.append({"type":"INVEST NOW" if settings.optimizer_live_gating else "SHADOW INVEST","title":f"Optimizer selects {r['symbol']}","detail":detail,"symbol_to":r["symbol"]})
    for rot in optimizer["rotations"]:
        props.append({"type":"ROTATE","title":rot["title"],"detail":rot["detail"],"symbol_from":rot["symbol_from"],"symbol_to":rot["symbol_to"]})

    paper=paper_status(db)
    summary={
        "buy_now":len(optimizer["selected_new"]),
        "portfolio_actions":sum(v["system_signal"] in {"SELL","STRONG SELL","TAKE PROFIT"} and v["owned"] for v in radar_views),
        "deployable_cash":max(0,cash-reserve),
        "best_candidate":next((v for v in radar_views if v.get("optimizer_bucket")=="INVEST NOW"),None),
        "visible_candidates":len(radar_views),"shortlist_count":len(optimizer["shortlist"]),"target_positions":optimizer["target_positions"],"max_positions":optimizer["max_positions"],
    }
    optimizer_summary={"version":optimizer["version"],"live_gating":settings.optimizer_live_gating,"visible":len(radar_views),"shortlist":len(optimizer["shortlist"]),"invest_now":len(optimizer["selected_new"]),"owned":optimizer["owned_count"],"target_positions":optimizer["target_positions"],"max_positions":optimizer["max_positions"],"rotations":len(optimizer["rotations"])}
    return {"positions":pos_views,"trades":trades,"analyses":analyses_req,"alerts":alerts,"candidates":radar_views,"cash":cash,"reserve":reserve,"proposals":props,"risk_profile":risk_profile,"risk_profiles":RISK_PROFILES,"account_risk":account,"base_currency":base_currency,"summary":summary,"optimizer":optimizer_summary,"paper":paper}


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

@app.post("/paper/run-now")
def paper_run_now():
    result=run_paper_cycle(radar.provider,force_rebalance=True)
    _invalidate_live_cache()
    return RedirectResponse("/",303)

@app.post("/paper/reset")
def paper_reset():
    with SessionLocal() as db:reset_paper(db)
    _invalidate_live_cache()
    return RedirectResponse("/",303)

@app.get("/api/live")
def live():
    state=_cached_live_state()
    return {"market_open":radar.market_open(),"scanner_running":radar.running,"last_scan":radar.last_scan,"last_error":radar.last_error,"universe_size":radar.universe_size,"universe_prefiltered":radar.last_universe_prefiltered,"universe_deep_candidates":radar.last_universe_candidates,"deep_analyzed":radar.last_deep_analyzed,"risk_profile":state["risk_profile"],"account_risk":state["account_risk"],"summary":state["summary"],"optimizer":state["optimizer"],"paper":state["paper"],"base_currency":state["base_currency"],"alerts":[{"id":a.id,"symbol":a.symbol,"title":a.title,"message":a.message,"severity":a.severity,"action":a.action,"alert_type":a.alert_type,"created_at":a.created_at.isoformat() if a.created_at else None} for a in state["alerts"]],"candidates":state["candidates"],"cache_seconds":settings.dashboard_cache_seconds}

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
