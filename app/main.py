from __future__ import annotations
import asyncio, json, os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import text
from .config import settings
from .db import engine, SessionLocal, Position, AnalysisRequest, Trade, PortfolioCash, WatchlistItem, AnalysisSnapshot, RadarCandidate, Alert
from .analysis_engine import parse_positions_from_text, portfolio_proposals
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
        return {"status":"ok","database":"connected","scanner_running":radar.running,"last_scan":radar.last_scan,"market_open":radar.market_open()}
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

@app.get("/",response_class=HTMLResponse)
def dashboard(request:Request):
    with SessionLocal() as db:
        positions=db.query(Position).order_by(Position.symbol).all(); trades=db.query(Trade).order_by(Trade.created_at.desc()).limit(20).all(); analyses_req=db.query(AnalysisRequest).order_by(AnalysisRequest.created_at.desc()).limit(8).all(); alerts=db.query(Alert).filter(Alert.acknowledged==False).order_by(Alert.created_at.desc()).limit(12).all(); candidates=db.query(RadarCandidate).order_by(RadarCandidate.ai_score.desc()).limit(20).all(); cash_rows=db.query(PortfolioCash).all(); payloads=latest_payloads(db)
    cash=sum(c.cash for c in cash_rows); reserve=sum(c.reserve_cash for c in cash_rows)
    pos_views=[]
    for p in positions:
        a=payloads.get(p.symbol,{})
        price=a.get("price") or 0; pnl=(price/p.avg_cost-1)*100 if price and p.avg_cost else None
        pos_views.append({"id":p.id,"symbol":p.symbol,"shares":p.shares,"avg_cost":p.avg_cost,"account":p.account,"price":price,"pnl":pnl,"action":a.get("action","Awaiting analysis"),"ai_score":a.get("ai_score")})
    analyses_for_prop={s:a for s,a in payloads.items() if a}; props=portfolio_proposals([{"symbol":p.symbol,"shares":p.shares,"avg_cost":p.avg_cost} for p in positions],analyses_for_prop,cash,reserve)
    return templates.TemplateResponse(request,"dashboard.html",{"positions":pos_views,"trades":trades,"analyses":analyses_req,"alerts":alerts,"candidates":candidates,"cash":cash,"reserve":reserve,"proposals":props,"market_open":radar.market_open(),"scanner":radar,"now":datetime.now(timezone.utc),"auth_enabled":settings.auth_enabled,"live_poll_seconds":settings.live_poll_seconds})

@app.post("/positions")
def add_position(symbol:str=Form(...),shares:float=Form(...),avg_cost:float=Form(...),account:str=Form("Manual")):
    symbol=symbol.upper().strip(); account=account.strip() or "Manual"
    with SessionLocal() as db:
        p=db.query(Position).filter(Position.symbol==symbol,Position.account==account).first()
        if p:p.shares=shares;p.avg_cost=avg_cost
        else:db.add(Position(symbol=symbol,shares=shares,avg_cost=avg_cost,account=account))
        db.commit()
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
    symbol=symbol.upper().strip()
    with SessionLocal() as db:db.add(AnalysisRequest(symbol=symbol,source_note=source_note.strip() or "Manual"));db.commit()
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
        alerts=db.query(Alert).filter(Alert.acknowledged==False).order_by(Alert.created_at.desc()).limit(10).all(); cands=db.query(RadarCandidate).order_by(RadarCandidate.ai_score.desc()).limit(15).all()
        return {"market_open":radar.market_open(),"scanner_running":radar.running,"last_scan":radar.last_scan,"last_error":radar.last_error,"alerts":[{"id":a.id,"symbol":a.symbol,"title":a.title,"message":a.message,"severity":a.severity,"action":a.action} for a in alerts],"candidates":[{"symbol":c.symbol,"price":c.price,"score":c.score,"ai_score":c.ai_score,"category":c.category,"action":c.action} for c in cands]}

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
async def import_confirm(request:Request):
    data=await request.json(); rows=data.get("positions") or []; saved=0
    with SessionLocal() as db:
        for r in rows:
            try:
                sym=str(r["symbol"]).upper().strip(); shares=float(r["shares"]); avg=float(r["avg_cost"]); account=str(r.get("account") or "Screenshot")
                if not sym or shares<=0 or shares>=1_000_000 or avg<=0:continue
                p=db.query(Position).filter(Position.symbol==sym,Position.account==account).first()
                if p:p.shares=shares;p.avg_cost=avg
                else:db.add(Position(symbol=sym,shares=shares,avg_cost=avg,account=account))
                saved+=1
            except:continue
        db.commit()
    return {"ok":True,"saved":saved}

@app.post("/api/import/screenshot")
async def import_screenshot(file:UploadFile=File(...)):
    if file.content_type and file.content_type not in {"image/png","image/jpeg","image/webp"}:raise HTTPException(415,"Upload a PNG, JPEG or WebP image")
    content=await file.read()
    if len(content)>settings.max_upload_mb*1024*1024:raise HTTPException(413,"Image too large")
    positions=ai_engine.extract_positions_from_image(content,file.content_type or "image/png")
    if positions is None:return JSONResponse({"ok":False,"needs_browser_ocr":True,"message":"AI image extraction is not configured. Browser OCR/manual confirmation can still be used."})
    return {"ok":True,"positions":positions}
