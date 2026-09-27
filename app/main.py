from datetime import datetime, timezone
import os
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, String, Integer, Float, DateTime, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

app = FastAPI(title="ISK Trading Radar", version="0.1.0")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./radar.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://") and "+psycopg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine)

class Base(DeclarativeBase):
    pass

class Position(Base):
    __tablename__ = "positions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    shares: Mapped[float] = mapped_column(Float)
    avg_cost: Mapped[float] = mapped_column(Float)
    account: Mapped[str] = mapped_column(String(64), default="Manual")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

class AnalysisRequest(Base):
    __tablename__ = "analysis_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    source_note: Mapped[str] = mapped_column(String(255), default="Manual")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

Base.metadata.create_all(engine)

@app.get("/health")
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as exc:
        return {"status": "degraded", "database": str(exc)}

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    with SessionLocal() as db:
        positions = db.query(Position).order_by(Position.created_at.desc()).all()
        analyses = db.query(AnalysisRequest).order_by(AnalysisRequest.created_at.desc()).limit(8).all()
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "positions": positions,
        "analyses": analyses,
        "now": datetime.now(timezone.utc),
    })

@app.post("/positions")
def add_position(
    symbol: str = Form(...),
    shares: float = Form(...),
    avg_cost: float = Form(...),
    account: str = Form("Manual"),
):
    symbol = symbol.upper().strip()
    with SessionLocal() as db:
        db.add(Position(symbol=symbol, shares=shares, avg_cost=avg_cost, account=account.strip() or "Manual"))
        db.commit()
    return RedirectResponse("/", status_code=303)

@app.post("/analyze")
def analyze_symbol(symbol: str = Form(...), source_note: str = Form("Manual")):
    symbol = symbol.upper().strip()
    with SessionLocal() as db:
        db.add(AnalysisRequest(symbol=symbol, source_note=source_note.strip() or "Manual"))
        db.commit()
    return RedirectResponse(f"/analysis/{symbol}", status_code=303)

@app.get("/analysis/{symbol}", response_class=HTMLResponse)
def analysis_page(request: Request, symbol: str):
    symbol = symbol.upper().strip()
    # V1 placeholder: live feeds/scoring will replace these values next.
    return templates.TemplateResponse("analysis.html", {
        "request": request,
        "symbol": symbol,
        "system_score": "Pending",
        "ai_score": "Pending",
        "action": "Awaiting live-data integration",
    })
