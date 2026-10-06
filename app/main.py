from __future__ import annotations
import asyncio, json, os, threading, time
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import text, or_
from .config import settings
from .db import engine, SessionLocal, Position, PaperPosition, AnalysisRequest, Trade, PortfolioCash, PortfolioPreference, WatchlistItem, AnalysisSnapshot, RadarCandidate, Alert, storage_status
from .analysis_engine import parse_positions_from_text, position_action, position_action_plan, SCORING_VERSION
from .short_horizon import VERSION as FORECAST_VERSION, forecast_current
from .portfolio_engine import RISK_PROFILES, ACTION_RANK, normalise_profile, stock_risk_score, system_signal, active_level, analyst_label, suggested_position_size, account_risk, projected_risk, risk_band, build_optimizer_plan, candidate_rank_score
from .paper_engine import paper_status, reset_paper, run_paper_cycle, manual_paper_add, manual_paper_close
from .scanner import radar
from .ai_engine import AIEngine
from .score_band_capture import experiment_status
from . import article_news
from .trading_rules import MIN_ENTRY_RISK_REWARD
from .full_scan import FullUniverseScan

full_scan = FullUniverseScan(radar)
radar.full_universe_scan = full_scan

@asynccontextmanager
async def lifespan(app:FastAPI):
    task=None
    experiment = await asyncio.to_thread(experiment_status)
    radar.last_experiment_result = {"status": experiment["status"], "version": experiment["version"],
        "started_at": experiment["started_at"], "profile": experiment["spec"]["profile"],
        "trial_status": (experiment.get("trial") or {}).get("status"),
        "trial_ends_at": (experiment.get("trial") or {}).get("ends_at"),
        "optional_finnhub_configured": bool(settings.finnhub_api_key)}
    if not settings.disable_scanner:
        article_news.worker.start()
        await asyncio.to_thread(full_scan.resume)
        task=asyncio.create_task(radar.loop())
    yield
    full_scan.stop()
    article_news.worker.stop()
    if task:
        task.cancel()
        try:await task
        except asyncio.CancelledError:pass

app=FastAPI(title="ISK Trading Radar",version="1.0.0",lifespan=lifespan)
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

app.add_middleware(SessionMiddleware,secret_key=settings.session_secret,same_site="lax",https_only=False)

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
        return {"status":"ok","database":"connected","scoring_version":SCORING_VERSION,"forecast_version":FORECAST_VERSION,"forecast_mode":"research_only","storage":storage_status(),"article_news":article_news.worker.status(),"scanner_running":radar.running,"scan_in_progress":radar.scan_in_progress,"scan_started_at":radar.scan_started_at,"last_scan":radar.last_scan,"last_scan_duration_seconds":radar.last_scan_duration_seconds,"last_scan_result":radar.last_result,"last_error":radar.last_error,"market_open":radar.market_open(),"universe_size":radar.universe_size,"live_poll_seconds":settings.live_poll_seconds,"dashboard_cache_seconds":settings.dashboard_cache_seconds,"score_band_experiment":radar.last_experiment_result}
    except Exception as exc:return JSONResponse({"status":"degraded","database":str(exc)},status_code=503)

@app.get("/api/experiments/score-bands")
def score_band_experiment_api():
    return experiment_status(include_history=True)


@app.get("/experiments/score-bands", response_class=HTMLResponse)
def score_band_experiment_page(request: Request):
    return templates.TemplateResponse(request, "score_band_experiment.html", {"experiment": experiment_status()})


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

def _manual_reallocation_suggestion(position: dict, selected_new: list[dict]) -> dict:
    """Suggest redeployment only after thesis-gated REDUCE/EXIT.

    A loss, weak momentum, technical pressure or a low score alone must never
    create a switch recommendation. The position-management layer already
    guarantees REDUCE/EXIT only after explicit thesis/fundamental invalidation.
    """
    action=str(position.get("action") or "").upper()
    pnl=position.get("pnl")
    if action not in {"REDUCE","EXIT"}:
        return {
            "status":"NO CHANGE","target":None,
            "reason":"No forced switch: price pressure, momentum weakness or a loss alone is not a sell trigger while the thesis remains intact.",
        }
    replacement=next((r for r in selected_new if r.get("symbol") != position.get("symbol")),None)
    loss_text=(
        "Book the loss only because the thesis/fundamentals are invalidated"
        if pnl is not None and float(pnl) < 0
        else "Exit/trim only because the thesis/fundamentals are invalidated"
    )
    if not replacement:
        return {
            "status":"RAISE CASH","target":None,
            "reason":f"{loss_text}; no qualified replacement is actionable right now, so do not force a switch.",
        }
    return {
        "status":"REDEPLOY",
        "target":replacement.get("symbol"),
        "target_signal":replacement.get("entry_signal"),
        "target_rank":replacement.get("market_rank"),
        "target_score":replacement.get("rank_score"),
        "reason":(
            f"{loss_text}; consider redeploying released capital into "
            f"{replacement.get('symbol')} only while it remains an actionable "
            f"{replacement.get('entry_signal') or 'BUY'} in the qualified Top-20."
        ),
    }

def _dashboard_state(db):
    positions=db.query(Position).order_by(Position.symbol).all()
    paper_positions=db.query(PaperPosition).filter(PaperPosition.account=="Optimizer Paper").order_by(PaperPosition.symbol).all()
    trades=db.query(Trade).order_by(Trade.created_at.desc()).limit(20).all()
    recent_analysis_rows=db.query(AnalysisRequest).order_by(AnalysisRequest.created_at.desc()).limit(100).all()
    analyses_req=[];seen_analysis_symbols=set()
    for row in recent_analysis_rows:
        sym=str(row.symbol or "").upper()
        if not sym or sym in seen_analysis_symbols:
            continue
        seen_analysis_symbols.add(sym)
        analyses_req.append(row)
        if len(analyses_req)>=8:
            break
    raw_alerts=db.query(Alert).filter(Alert.acknowledged==False).order_by(Alert.created_at.desc()).limit(100).all()

    # Read only the strongest/freshest compact rows. Full-market scanning continues
    # in the background; the dashboard is intentionally capped at 20 opportunities.
    fresh_cutoff=datetime.now(timezone.utc)-timedelta(days=4)
    # Fetch currently qualified rows first. The previous implementation ranked
    # all recent rows before filtering lane qualification, so stale/unqualified
    # high-rank rows could crowd fresh qualified names out of the 120-row fetch.
    candidates=(db.query(RadarCandidate)
        .filter(
            RadarCandidate.updated_at >= fresh_cutoff,
            or_(
                RadarCandidate.lane_qualified == True,
                RadarCandidate.current_json.like('%"lane_qualified":true%'),
            ),
        )
        .order_by(RadarCandidate.portfolio_rank_score.desc(),RadarCandidate.updated_at.desc())
        .limit(200).all())
    have={c.symbol for c in candidates}
    tracked_symbols={p.symbol for p in positions} | {p.symbol for p in paper_positions}
    missing=[sym for sym in tracked_symbols if sym not in have]
    if missing:
        candidates += db.query(RadarCandidate).filter(RadarCandidate.symbol.in_(missing)).all()
    candidate_map={c.symbol:c for c in candidates}

    cash_rows=db.query(PortfolioCash).all()
    payloads={};missing_current=[];stale_scoring_symbols=[]
    for c in candidates:
        has_compact=False
        if getattr(c,"current_json",None):
            try:
                parsed=json.loads(c.current_json)
                if (
                    isinstance(parsed,dict)
                    and parsed.get("symbol")
                    and parsed.get("scoring_version")==SCORING_VERSION
                ):
                    payloads[c.symbol]=parsed;has_compact=True
                elif isinstance(parsed,dict) and parsed.get("symbol"):
                    stale_scoring_symbols.append(c.symbol)
            except Exception:pass
        if not has_compact:
            # Never expose target/R-R from an older scoring engine. Keep a neutral
            # placeholder while the scanner prioritizes this symbol for refresh.
            payloads[c.symbol]={"symbol":c.symbol,"price":c.price,"deterministic_score":c.score,"ai_score":c.ai_score,"category":c.category,"action":"REFRESHING MODEL","levels":{},"technicals":{},"news":{},"scoring_refresh_pending":True}
            missing_current.append(c.symbol)
    if missing_current:
        latest={}
        q=db.query(AnalysisSnapshot).filter(AnalysisSnapshot.symbol.in_(missing_current)).order_by(AnalysisSnapshot.created_at.desc())
        for snap in q.limit(max(10,len(missing_current)*3)).all():
            if snap.symbol in latest:continue
            try:
                parsed=json.loads(snap.payload_json)
                if parsed.get("scoring_version")==SCORING_VERSION:
                    latest[snap.symbol]=parsed
            except Exception:
                continue
        payloads.update(latest)
    missing_holdings=[sym for sym in tracked_symbols if sym not in payloads]
    for sym in missing_holdings:
        snaps=db.query(AnalysisSnapshot).filter(AnalysisSnapshot.symbol==sym).order_by(AnalysisSnapshot.created_at.desc()).limit(5).all()
        for snap in snaps:
            try:
                parsed=json.loads(snap.payload_json)
                if parsed.get("scoring_version")==SCORING_VERSION:
                    payloads[sym]=parsed
                    break
            except Exception:
                continue
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
        price=float(a.get("price") or 0)
        if a and price:
            try:
                manual_action,manual_reason=position_action(
                    a,price,{"shares":p.shares,"avg_cost":p.avg_cost,"account":p.account,"opened_at":p.created_at,"entry_target":p.entry_target,"entry_stretch_target":p.entry_stretch_target,"entry_stop":p.entry_stop,"entry_horizon_days":p.entry_horizon_days,"entry_plan_version":p.entry_plan_version}
                )
                a["action"]=manual_action
                a["action_reason"]=manual_reason
                a["action_plan"]=position_action_plan(
                    manual_action,a,price,{"shares":p.shares,"avg_cost":p.avg_cost,"account":p.account,"opened_at":p.created_at,"entry_target":p.entry_target,"entry_stretch_target":p.entry_stretch_target,"entry_stop":p.entry_stop,"entry_horizon_days":p.entry_horizon_days,"entry_plan_version":p.entry_plan_version}
                )
            except Exception:
                pass
        previous_close=float(a.get("previous_close") or 0)
        pnl=(price/p.avg_cost-1)*100 if price and p.avg_cost else None
        day_change_pct=((price/previous_close)-1)*100 if price and previous_close else None
        currency=_currency_for(p.symbol,a);rate=fx.get(currency)
        value_base=(price*p.shares*rate) if price and rate else 0.0
        srisk=stock_risk_score(a) if a else 50.0
        sector=(a.get("fundamentals") or {}).get("sector") or "Unknown"
        rank=candidate_rank_score(a) if a else {"score":0}
        lane=a.get("lane")
        lane_label=a.get("lane_label") or ("Explosive Lane" if lane=="EXPLOSIVE" else "Core Quality Lane" if lane=="CORE_QUALITY" else "Outside Current Lanes")
        row={"id":p.id,"symbol":p.symbol,"shares":p.shares,"avg_cost":p.avg_cost,"account":p.account,"source_tag":"MANUAL","source_detail":p.account or "Manual","price":price,"previous_close":previous_close or None,"day_change_pct":day_change_pct,"pnl":pnl,"action":a.get("action","ANALYSIS QUEUED"),"ai_score":a.get("ai_score"),"action_plan":a.get("action_plan"),"action_reason":a.get("action_reason"),"currency":currency,"decision_confidence":a.get("decision_confidence"),"value_base":value_base,"stock_risk":srisk,"sector":sector,"category":a.get("category"),"lane":lane,"lane_label":lane_label,"material_events":(a.get("news") or {}).get("material_events",0),"system_signal":system_signal(a,True) if a else "WATCH","portfolio_rank_score":rank.get("score",0)}
        pos_views.append(row);risk_rows.append(row);owned[p.symbol]=row

    paper_owned={}
    for p in paper_positions:
        a=payloads.get(p.symbol,{})
        price=float(a.get("price") or p.avg_cost or 0)
        if a and price:
            try:
                paper_action,paper_reason=position_action(
                    a,price,{"shares":p.shares,"avg_cost":p.avg_cost,"account":"Paper","opened_at":p.opened_at,"entry_target":p.entry_target,"entry_stretch_target":p.entry_stretch_target,"entry_stop":p.entry_stop,"entry_horizon_days":p.entry_horizon_days,"entry_plan_version":p.entry_plan_version}
                )
                a["action"]=paper_action
                a["action_reason"]=paper_reason
            except Exception:
                pass
        currency=_currency_for(p.symbol,a);rate=fx.get(currency)
        paper_owned[p.symbol]={
            "symbol":p.symbol,"shares":p.shares,"avg_cost":p.avg_cost,
            "value_base":(price*p.shares*rate) if price and rate else 0.0,
        }
    owned_symbols=set(owned) | set(paper_owned)

    account=account_risk(risk_rows,cash,target_profile=risk_profile)
    portfolio_value=float(account.get("total") or cash)
    optimizer=build_optimizer_plan(
        payloads,owned_symbols,profile=risk_profile,
        visible_limit=settings.optimizer_visible_limit,
        shortlist_limit=settings.optimizer_shortlist_limit,
    )
    plan_by_symbol={r["symbol"]:r for r in optimizer["visible"]}

    # Manual/broker holdings remain independent from the paper P&L, but they are
    # still actively managed. A replacement is suggested only after a thesis-
    # gated REDUCE/EXIT; mere drawdown or technical pressure never triggers it.
    for row in pos_views:
        row["reallocation"]=_manual_reallocation_suggestion(row,optimizer["selected_new"])

    paper_blocked_by_symbol = {
        str(x.get("symbol") or "").upper(): x
        for x in ((radar.last_result or {}).get("paper_blocked_orders") or [])
        if isinstance(x, dict) and x.get("symbol")
    }
    radar_views=[]
    for rankrow in optimizer["visible"]:
        sym=rankrow["symbol"]
        c=candidate_map.get(sym)
        a=payloads.get(sym) or {}
        is_owned=sym in owned_symbols
        owned_row=owned.get(sym) or paper_owned.get(sym) or {}
        level=active_level(a,is_owned)
        currency=_currency_for(sym,a);rate=fx.get(currency)
        existing_value=owned_row.get("value_base",0.0)
        optimizer_approved=rankrow.get("bucket") in {"INVEST NOW","ROTATE IN"}
        explicit_add=is_owned and str(a.get("action") or "").upper()=="ADD"
        if optimizer_approved or explicit_add:
            sizing=suggested_position_size(a,cash=cash,reserve_cash=reserve,portfolio_value=portfolio_value,profile=risk_profile,fx_rate_to_base=rate or 0,existing_value=existing_value,whole_shares=True)
        elif is_owned:
            sizing={"shares":0,"capital":0,"fit":rankrow.get("risk_fit","UNKNOWN"),"stock_risk":rankrow.get("stock_risk",stock_risk_score(a)),"reason":"Existing position — HOLD / DON'T ADD; no additional paper order"}
        else:
            sizing={"shares":0,"capital":0,"fit":rankrow.get("risk_fit","UNKNOWN"),"stock_risk":rankrow.get("stock_risk",stock_risk_score(a)),"reason":rankrow.get("decision_reason") or "No capital allocated: current signal is not an investable Top-20 entry"}
        projected=projected_risk(risk_rows,cash,a,sizing,rate or 0,risk_profile) if rate and sizing.get("shares") else None
        prev=previous.get(sym) or {};changed=None
        if prev and prev.get("action") and prev.get("action")!=a.get("action"):changed=f"{prev.get('action')} → {a.get('action')}"
        fundamentals=a.get("fundamentals") or {};name=fundamentals.get("companyName") or a.get("company_name") or sym
        signal=system_signal(a,is_owned)
        paper_block = paper_blocked_by_symbol.get(sym)
        effective_optimizer_action = rankrow.get("optimizer_action")
        effective_optimizer_reason = rankrow.get("decision_reason")
        if paper_block:
            block_decision = str(paper_block.get("decision") or "").upper()
            block_reason = str(paper_block.get("reason") or "Paper execution constraint")
            target_capital = float(paper_block.get("target_capital") or 0)
            if block_decision == "ADD" and target_capital <= 0:
                signal = "HOLD"
                effective_optimizer_action = "NO ADD — TARGET FULL"
                effective_optimizer_reason = "Raw ADD setup is present, but the existing paper position already meets/exceeds its score-led target. " + block_reason
            else:
                cash_left = float(paper_block.get("cash") or 0)
                min_cost = float(paper_block.get("minimum_one_share_cost") or 0)
                if min_cost > 0 and cash_left + 1e-9 < min_cost:
                    effective_optimizer_action = "CAN'T COMPLETE — NO MONEY LEFT"
                    effective_optimizer_reason = block_reason
                else:
                    effective_optimizer_action = "PAPER CASH / SIZE BLOCKED"
                    effective_optimizer_reason = block_reason
        view_price=float(a.get("price") or (c.price if c else 0) or 0)
        view_previous_close=float(a.get("previous_close") or 0)
        view_day_change_pct=((view_price/view_previous_close)-1)*100 if view_price and view_previous_close else None
        view={
            "symbol":sym,"name":name,"price":view_price,"previous_close":view_previous_close or None,"day_change_pct":view_day_change_pct,"currency":currency,
            "category":a.get("category") or (c.category if c else "Watch"),"lane":rankrow.get("lane") or a.get("lane"),"lane_label":rankrow.get("lane_label") or a.get("lane_label") or ("Explosive Lane" if (rankrow.get("lane") or a.get("lane"))=="EXPLOSIVE" else "Core Quality Lane"),"score":float(a.get("deterministic_score") or (c.score if c else 0) or 0),"ai_score":float(a.get("ai_score") or (c.ai_score if c else 0) or 0),
            "analyst_score":a.get("analyst_score"),"analyst_label":analyst_label(a),"action":a.get("action") or (c.action if c else "WATCH"),"action_reason":a.get("action_reason") or "",
            "system_signal":signal,"owned":is_owned,"owned_shares":owned_row.get("shares"),"owned_avg":owned_row.get("avg_cost"),
            "level_label":level["label"],"level_value":level["value"],"distance":level["distance"],"distance_pct":level["distance_pct"],
            "target":(a.get("levels") or {}).get("target"),
            "stop":(a.get("levels") or {}).get("entry_stop") or (a.get("levels") or {}).get("stop"),
            "entry_stop":(a.get("levels") or {}).get("entry_stop"),
            "thesis_stop":(a.get("levels") or {}).get("thesis_stop") or (a.get("levels") or {}).get("stop"),
            "risk_reward":a.get("risk_reward"),
            "expected_yield_pct":a.get("expected_yield_pct"),
            "stock_risk":sizing.get("stock_risk",stock_risk_score(a)),"risk_band":risk_band(sizing.get("stock_risk",stock_risk_score(a))),"risk_fit":sizing.get("fit",rankrow.get("risk_fit","UNKNOWN")),
            "suggested_shares":sizing.get("shares",0),"suggested_capital":sizing.get("capital",0),"sizing_reason":sizing.get("reason",""),
            "projected_risk":projected.get("score") if projected else None,"changed":changed,
            "updated_at":c.updated_at.isoformat() if c and c.updated_at else None,
            "market_rank":rankrow.get("market_rank"),"portfolio_rank_score":rankrow.get("rank_score"),"optimizer_bucket":rankrow.get("bucket"),"optimizer_action":effective_optimizer_action,"optimizer_decision_reason":effective_optimizer_reason,"paper_execution_block":paper_block,
            "rank_components":rankrow.get("rank_components"),"ai_confirmation":rankrow.get("ai_confirmation"),"analyst_confirmation":rankrow.get("analyst_confirmation"),
            "strategic_capital":a.get("strategic_capital") or {},
            "strategic_capital_shadow":rankrow.get("strategic_capital_shadow") or {},
            "promotion_risk":a.get("promotion_risk") or {},
        }
        radar_views.append(view)

    approved_buy_symbols={r["symbol"] for r in optimizer["selected_new"]}
    paper_owned_symbols=set(paper_owned)
    alerts=[]
    for a in raw_alerts:
        if _is_snoozed(a) or not _attentionworthy_alert(a):continue
        # A paper position is already owned even if it is not in the manual
        # Position table. Suppress stale/new-entry BUY alerts for owned paper
        # holdings unless the underlying portfolio action is explicitly ADD.
        if a.symbol in paper_owned_symbols and str(a.action or "").upper() in {"STRONG BUY","BUY","STARTER BUY","CONSIDER BUY","BUY NOW","BREAKOUT BUY","CONSIDER BUYING NOW","CONSIDER STARTER BUY"}:
            if str((payloads.get(a.symbol) or {}).get("action") or "").upper() != "ADD":
                continue
        # In the current paper-only workflow, a buy-level alert must agree with
        # the Top-20 allocator. This prevents raw CONSIDER/BUY signals outside the
        # actionable allocation set from looking like paper-trade decisions.
        if a.alert_type=="buy_level" and a.symbol not in approved_buy_symbols:continue
        alerts.append(a)
    alerts=sorted(alerts,key=_alert_priority)[:20]

    paper=paper_status(db)

    lane_refresh_pending = 0
    explosive_evaluated = 0
    explosive_near_misses = 0
    blocker_counts = {}
    for a in payloads.values():
        if not isinstance(a, dict) or not a.get("symbol"):
            continue
        if "lane_qualified" not in a or "lane" not in a:
            lane_refresh_pending += 1
            continue
        explosive_evaluated += 1
        if a.get("core_quality_qualified") is True and a.get("explosive_qualified") is not True:
            explosive_near_misses += 1
        if a.get("explosive_qualified") is not True:
            for blocker in a.get("explosive_blockers") or []:
                blocker_counts[blocker] = blocker_counts.get(blocker, 0) + 1
    explosive_top_blockers = [
        {"label": label, "count": count}
        for label, count in sorted(blocker_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:4]
    ]

    # Candidate dashboard is an action surface, not a watchlist. Existing
    # holdings stay in Open Positions; new names appear here only when the shared
    # entry trigger is actionable right now.
    actionable_radar_views = [
        v for v in radar_views
        if not v.get("owned") and v.get("optimizer_bucket") in {"INVEST NOW", "ROTATE IN"}
    ]
    summary={
        "buy_now":len(optimizer["selected_new"]),
        "portfolio_actions":sum(v["system_signal"] in {"SELL","STRONG SELL","TAKE PROFIT"} and v["owned"] for v in radar_views),
        "deployable_cash":max(0,cash-reserve),
        "best_candidate":next(iter(actionable_radar_views),None),
        "visible_candidates":len(actionable_radar_views),"shortlist_count":len(actionable_radar_views),"position_cap_enabled":optimizer.get("position_cap_enabled",False),
        "core_quality_count":sum(1 for v in actionable_radar_views if v.get("lane")=="CORE_QUALITY"),
        "explosive_count":sum(1 for v in actionable_radar_views if v.get("lane")=="EXPLOSIVE"),
    }
    lane_counts=optimizer.get("lane_counts") or {}
    optimizer_summary={
        "version":optimizer["version"],"live_gating":settings.optimizer_live_gating,
        "visible":len(radar_views),"shortlist":len(optimizer["shortlist"]),
        "invest_now":len(optimizer["selected_new"]),"owned":optimizer["owned_count"],
        "position_cap_enabled":optimizer.get("position_cap_enabled",False),
        "allocation_policy":optimizer.get("allocation_policy"),"rotations":len(optimizer["rotations"]),
        "min_entry_risk_reward":optimizer.get("min_entry_risk_reward",MIN_ENTRY_RISK_REWARD),
        "core_quality":lane_counts.get("core_quality",0),"explosive":lane_counts.get("explosive",0),
        "lane_refresh_pending":lane_refresh_pending,
        "explosive_evaluated":explosive_evaluated,
        "explosive_near_misses":explosive_near_misses,
        "explosive_top_blockers":explosive_top_blockers,
    }
    display_radar_views=sorted(
        actionable_radar_views,
        key=lambda v: (0 if v.get("lane")=="CORE_QUALITY" else 1, int(v.get("market_rank") or 999)),
    )
    return {"positions":pos_views,"trades":trades,"analyses":analyses_req,"alerts":alerts,"candidates":display_radar_views,"cash":cash,"reserve":reserve,"risk_profile":risk_profile,"risk_profiles":RISK_PROFILES,"account_risk":account,"base_currency":base_currency,"summary":summary,"optimizer":optimizer_summary,"paper":paper}


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
def delete_position(position_id:int,background_tasks:BackgroundTasks):
    with SessionLocal() as db:
        p=db.get(Position,position_id)
        if not p:raise HTTPException(status_code=404,detail="Manual holding not found")
        symbol=p.symbol
        db.delete(p)
        db.commit()
    _invalidate_live_cache()
    background_tasks.add_task(_analyze_symbols,[symbol])
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

@app.get("/api/symbol-search")
def symbol_search(q:str=""):
    query=(q or "").strip()
    if not query:
        return {"results":[]}
    q_upper=query.upper()
    q_lower=" ".join(query.lower().split())
    try:
        universe=radar.provider.us_equity_universe()
    except Exception:
        universe=[]

    scored=[]
    for row in universe:
        symbol=str(row.get("symbol") or "").upper()
        name=str(row.get("name") or symbol)
        exchange=str(row.get("exchange") or "")
        sym_lower=symbol.lower()
        name_lower=name.lower()
        score=None
        if symbol==q_upper:
            score=0
        elif sym_lower.startswith(q_lower):
            score=1
        elif name_lower.startswith(q_lower):
            score=2
        elif q_lower in sym_lower:
            score=3
        elif q_lower in name_lower:
            score=4
        if score is not None:
            scored.append((score, len(symbol), symbol, name, exchange))
    scored.sort(key=lambda x:(x[0],x[1],x[2]))
    results=[{"symbol":s,"name":n,"exchange":e} for _,_,s,n,e in scored[:12]]

    if not results:
        # Fallback to locally known Radar candidates when the universe directory
        # is temporarily unavailable.
        with SessionLocal() as db:
            rows=db.query(RadarCandidate).order_by(RadarCandidate.portfolio_rank_score.desc()).limit(150).all()
            for row in rows:
                payload=_candidate_payload(row)
                name=str((payload.get("fundamentals") or {}).get("companyName") or row.symbol)
                if q_lower in row.symbol.lower() or q_lower in name.lower():
                    results.append({"symbol":row.symbol,"name":name,"exchange":""})
                    if len(results)>=12:
                        break
    return {"results":results}


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
    with SessionLocal() as db:
        req=db.query(AnalysisRequest).filter(AnalysisRequest.symbol==symbol).order_by(AnalysisRequest.created_at.desc()).first()
        if req:
            req.source_note=note
            req.created_at=datetime.now(timezone.utc)
        else:
            db.add(AnalysisRequest(symbol=symbol,source_note=note))
        db.commit()
    try:radar.analyze_symbol(symbol,True,strategic_refresh=True)
    except Exception:pass
    _invalidate_live_cache()
    return RedirectResponse(f"/analysis/{symbol}",303)

@app.get("/analysis/{symbol}",response_class=HTMLResponse)
def analysis_page(request:Request,symbol:str,refresh:int=0):
    symbol=symbol.upper().strip(); data=None
    if refresh:
        try:data=radar.analyze_symbol(symbol,True,strategic_refresh=True)
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
    # Never serve a deterministic score created by an older scoring algorithm.
    # This prevents persisted pre-deploy snapshots from surviving a scoring fix.
    if data is not None and (data.get("scoring_version") != SCORING_VERSION or not forecast_current(data) or article_news.is_dirty(symbol, data.get("asof"))):
        try:data=radar.analyze_symbol(symbol,True)
        except Exception:data=None
    if data is None:
        try:data=radar.analyze_symbol(symbol,True)
        except Exception as exc:data={"symbol":symbol,"error":str(exc),"deterministic_score":0,"analyst_score":None,"ai_score":0,"action":"DATA UNAVAILABLE","price":0,"breakdown":{},"levels":{},"technicals":{},"news":{"items":[],"label":"Unknown","score":0},"reasons":[],"risks":["Market-data request failed"],"sensitivity":[]}
    return templates.TemplateResponse(request,"analysis.html",{"d":data})

@app.get("/api/analysis/{symbol}")
def analysis_json(symbol:str, refresh:int=0):
    symbol=symbol.upper().strip()
    if refresh:
        return radar.analyze_symbol(symbol,True,strategic_refresh=True)
    with SessionLocal() as db:
        c=db.query(RadarCandidate).filter(RadarCandidate.symbol==symbol).first()
        if c and c.current_json:
            data=_candidate_payload(c)
            if data.get("scoring_version") == SCORING_VERSION and forecast_current(data) and not article_news.is_dirty(symbol, data.get("asof")):
                return data
        s=db.query(AnalysisSnapshot).filter(AnalysisSnapshot.symbol==symbol).order_by(AnalysisSnapshot.created_at.desc()).first()
        if s:
            try:
                data=json.loads(s.payload_json)
                if data.get("scoring_version") == SCORING_VERSION and forecast_current(data) and not article_news.is_dirty(symbol, data.get("asof")):
                    return data
            except Exception:
                pass
    return radar.analyze_symbol(symbol,True)

@app.post("/api/scan-now")
def scan_now():
    result=radar.scan_once(force=True)
    _invalidate_live_cache()
    return result

@app.post("/api/full-scan")
def start_full_scan():
    return full_scan.start()

@app.get("/api/full-scan")
def full_scan_status():
    return full_scan.status()

@app.get("/api/full-scan/results.csv")
def full_scan_results():
    return Response(full_scan.results_csv(), media_type="text/csv",
                    headers={"Content-Disposition":"attachment; filename=full-universe-scan.csv"})

@app.get("/scan-audit", response_class=HTMLResponse)
def full_scan_page(request: Request):
    return templates.TemplateResponse(request, "full_scan.html", {})

@app.post("/paper/run-now")
def paper_run_now():
    result=radar.scan_once(force=True) if settings.score_band_trial_armed_at else run_paper_cycle(radar.provider,force_rebalance=True)
    _invalidate_live_cache()
    return RedirectResponse("/",303)

@app.post("/paper/reset")
def paper_reset():
    with SessionLocal() as db:reset_paper(db)
    _invalidate_live_cache()
    return RedirectResponse("/",303)

@app.post("/api/paper/positions/{symbol}/add")
async def paper_manual_add(symbol:str, request:Request):
    try:
        data=await request.json()
    except Exception:
        data={}
    result=manual_paper_add(radar.provider,symbol,float(data.get("shares") or 0))
    _invalidate_live_cache()
    code=200 if result.get("status")=="ok" else 409 if result.get("status")=="blocked" else 400
    return JSONResponse(result,status_code=code)

@app.post("/api/paper/positions/{symbol}/close")
async def paper_manual_close(symbol:str, request:Request):
    try:
        data=await request.json()
    except Exception:
        data={}
    shares=data.get("shares")
    result=manual_paper_close(radar.provider,symbol,float(shares) if shares not in (None,"",0) else None)
    _invalidate_live_cache()
    code=200 if result.get("status")=="ok" else 400
    return JSONResponse(result,status_code=code)


@app.get("/api/live")
def live():
    state=_cached_live_state()
    return {"market_open":radar.market_open(),"scanner_running":radar.running,"scan_in_progress":radar.scan_in_progress,"scan_started_at":radar.scan_started_at,"last_scan":radar.last_scan,"last_scan_duration_seconds":radar.last_scan_duration_seconds,"last_scan_result":radar.last_result,"last_error":radar.last_error,"universe_size":radar.universe_size,"universe_prefiltered":radar.last_universe_prefiltered,"universe_deep_candidates":radar.last_universe_candidates,"universe_core_candidates":radar.last_universe_core_candidates,"universe_explosive_candidates":radar.last_universe_explosive_candidates,"deep_analyzed":radar.last_deep_analyzed,"risk_profile":state["risk_profile"],"account_risk":state["account_risk"],"summary":state["summary"],"optimizer":state["optimizer"],"paper":state["paper"],"positions":state["positions"],"base_currency":state["base_currency"],"alerts":[{"id":a.id,"symbol":a.symbol,"title":a.title,"message":a.message,"severity":a.severity,"action":a.action,"alert_type":a.alert_type,"created_at":a.created_at.isoformat() if a.created_at else None} for a in state["alerts"]],"candidates":state["candidates"],"cache_seconds":settings.dashboard_cache_seconds}

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
        pd={"shares":p.shares,"avg_cost":p.avg_cost,"account":p.account,"opened_at":p.created_at,"entry_target":p.entry_target,"entry_stretch_target":p.entry_stretch_target,"entry_stop":p.entry_stop,"entry_horizon_days":p.entry_horizon_days,"entry_plan_version":p.entry_plan_version} if p else None
        level=active_level(payload,bool(p)) if payload else {"label":"—","value":"—","distance":"—"}
        price=float(payload.get("price") or (snap.price if snap else 0) or 0)
        previous_close=float(payload.get("previous_close") or 0)
        day_change_pct=((price/previous_close)-1)*100 if price and previous_close else None
        pnl=((price/p.avg_cost-1)*100) if p and p.avg_cost and price else None
        thesis=payload.get("thesis_assessment") or {}
        news=payload.get("news") or {}
        return {
            "alert":{"id":a.id,"symbol":a.symbol,"title":a.title,"message":a.message,"severity":a.severity,"action":a.action,"created_at":a.created_at.isoformat() if a.created_at else None},
            "analysis":{
                "price":price,"previous_close":previous_close or None,"day_change_pct":day_change_pct,"system_score":payload.get("deterministic_score"),"ai_score":payload.get("ai_score"),
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
