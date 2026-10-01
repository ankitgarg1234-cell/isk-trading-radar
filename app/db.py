from datetime import datetime, timezone
from sqlalchemy import create_engine, String, Integer, Float, DateTime, Boolean, Text, UniqueConstraint, inspect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from .config import settings

DATABASE_URL = settings.database_url
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://") and "+psycopg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

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

class Trade(Base):
    __tablename__ = "trades"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    side: Mapped[str] = mapped_column(String(8))
    shares: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    fees: Mapped[float] = mapped_column(Float, default=0.0)
    account: Mapped[str] = mapped_column(String(64), default="Manual")
    reason: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

class PortfolioCash(Base):
    __tablename__ = "portfolio_cash"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    cash: Mapped[float] = mapped_column(Float, default=0.0)
    reserve_cash: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(8), default="SEK")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class PortfolioPreference(Base):
    __tablename__ = "portfolio_preferences"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account: Mapped[str] = mapped_column(String(64), unique=True, index=True, default="Main")
    risk_profile: Mapped[str] = mapped_column(String(16), default="MEDIUM")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

class WatchlistItem(Base):
    __tablename__ = "watchlist"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    source: Mapped[str] = mapped_column(String(64), default="Manual")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

class AnalysisSnapshot(Base):
    __tablename__ = "analysis_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    price: Mapped[float] = mapped_column(Float, default=0.0)
    deterministic_score: Mapped[float] = mapped_column(Float, default=0.0)
    analyst_score: Mapped[float] = mapped_column(Float, default=0.0)
    ai_score: Mapped[float] = mapped_column(Float, default=0.0)
    expected_yield_pct: Mapped[float] = mapped_column(Float, default=0.0)
    ai_expected_yield_pct: Mapped[float] = mapped_column(Float, default=0.0)
    category: Mapped[str] = mapped_column(String(32), default="Watch")
    action: Mapped[str] = mapped_column(String(40), default="WATCH")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

class RadarCandidate(Base):
    __tablename__ = "radar_candidates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    category: Mapped[str] = mapped_column(String(32), default="Watch")
    action: Mapped[str] = mapped_column(String(40), default="WATCH")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    ai_score: Mapped[float] = mapped_column(Float, default=0.0)
    price: Mapped[float] = mapped_column(Float, default=0.0)
    portfolio_rank_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    rank_version: Mapped[str] = mapped_column(String(32), default="rank-v1")
    lane: Mapped[str] = mapped_column(String(24), nullable=True, index=True)
    lane_qualified: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    # Compact current-state payload used by the live dashboard. Heavy one-year
    # price arrays are intentionally excluded to keep managed-Postgres egress low.
    current_json: Mapped[str] = mapped_column(Text, default="{}")
    previous_action: Mapped[str] = mapped_column(String(40), default="")
    last_snapshot_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    last_snapshot_key: Mapped[str] = mapped_column(String(128), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    alert_type: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(16), default="info")
    title: Mapped[str] = mapped_column(String(160))
    message: Mapped[str] = mapped_column(Text, default="")
    action: Mapped[str] = mapped_column(String(40), default="REVIEW")
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    snoozed_until: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class PaperAccount(Base):
    __tablename__ = "paper_accounts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account: Mapped[str] = mapped_column(String(64), unique=True, index=True, default="Optimizer Paper")
    starting_cash: Mapped[float] = mapped_column(Float, default=10000.0)
    cash: Mapped[float] = mapped_column(Float, default=10000.0)
    benchmark_symbol: Mapped[str] = mapped_column(String(16), default="^SP500TR")
    benchmark_start_price: Mapped[float] = mapped_column(Float, nullable=True)
    benchmark_last_price: Mapped[float] = mapped_column(Float, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_rebalance_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class PaperPosition(Base):
    __tablename__ = "paper_positions"
    __table_args__ = (UniqueConstraint("account", "symbol", name="uq_paper_position_account_symbol"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account: Mapped[str] = mapped_column(String(64), index=True, default="Optimizer Paper")
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    shares: Mapped[float] = mapped_column(Float)
    avg_cost: Mapped[float] = mapped_column(Float)
    rank_score_at_entry: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str] = mapped_column(String(255), default="")
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class PaperTrade(Base):
    __tablename__ = "paper_trades"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account: Mapped[str] = mapped_column(String(64), index=True, default="Optimizer Paper")
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    side: Mapped[str] = mapped_column(String(8))
    shares: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    fees: Mapped[float] = mapped_column(Float, default=0.0)
    rank_score: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class PaperSnapshot(Base):
    __tablename__ = "paper_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account: Mapped[str] = mapped_column(String(64), index=True, default="Optimizer Paper")
    equity: Mapped[float] = mapped_column(Float, default=0.0)
    cash: Mapped[float] = mapped_column(Float, default=0.0)
    invested: Mapped[float] = mapped_column(Float, default=0.0)
    benchmark_price: Mapped[float] = mapped_column(Float, default=0.0)
    portfolio_return_pct: Mapped[float] = mapped_column(Float, default=0.0)
    benchmark_return_pct: Mapped[float] = mapped_column(Float, default=0.0)
    excess_return_pct: Mapped[float] = mapped_column(Float, default=0.0)
    drawdown_pct: Mapped[float] = mapped_column(Float, default=0.0)
    positions_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


def storage_status() -> dict:
    """Return a safe summary of the configured database backend.

    Render's local filesystem is ephemeral, so the default SQLite fallback must
    never be presented as durable account storage. A remote Postgres URL is
    treated as persistent storage for the V1 ledger.
    """
    backend = engine.url.get_backend_name()
    persistent = backend.startswith("postgresql")
    return {
        "backend": backend,
        "persistent": persistent,
        "label": "Persistent Postgres" if persistent else "Local SQLite",
        "warning": None if persistent else (
            "Account data is stored in local SQLite. On Render this filesystem is ephemeral, "
            "so positions, cash, trades and analysis history can disappear after a restart or redeploy."
        ),
    }

Base.metadata.create_all(engine)

def _ensure_runtime_columns():
    """Small additive migration layer for incremental V1 patches.

    SQLAlchemy ``create_all`` does not add columns to existing tables, so older
    Render/Neon databases need new optional columns added explicitly. These
    migrations are additive only; they never delete ledger/history data.
    """
    try:
        cols={c["name"] for c in inspect(engine).get_columns("alerts")}
        if "snoozed_until" not in cols:
            with engine.begin() as conn:
                conn.exec_driver_sql("ALTER TABLE alerts ADD COLUMN snoozed_until TIMESTAMP NULL")
    except Exception:
        pass
    try:
        cols={c["name"] for c in inspect(engine).get_columns("radar_candidates")}
        additions={
            "current_json": "TEXT DEFAULT '{}'",
            "previous_action": "VARCHAR(40) DEFAULT ''",
            "last_snapshot_at": "TIMESTAMP NULL",
            "last_snapshot_key": "VARCHAR(128) DEFAULT ''",
            "portfolio_rank_score": "FLOAT DEFAULT 0",
            "rank_version": "VARCHAR(32) DEFAULT 'rank-v1'",
            "lane": "VARCHAR(24) NULL",
            "lane_qualified": "BOOLEAN DEFAULT FALSE",
        }
        for name, ddl in additions.items():
            if name not in cols:
                with engine.begin() as conn:
                    conn.exec_driver_sql(f"ALTER TABLE radar_candidates ADD COLUMN {name} {ddl}")
    except Exception:
        pass
    # Backfill lane columns from compact JSON for rows written before the
    # explicit lane columns existed. This keeps currently qualified names visible
    # immediately after deployment instead of waiting for every symbol to rescan.
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql(
                """UPDATE radar_candidates
                   SET lane_qualified=TRUE, lane='CORE_QUALITY'
                   WHERE current_json LIKE '%"lane_qualified":true%'
                     AND current_json LIKE '%"lane":"CORE_QUALITY"%'"""
            )
            conn.exec_driver_sql(
                """UPDATE radar_candidates
                   SET lane_qualified=TRUE, lane='EXPLOSIVE'
                   WHERE current_json LIKE '%"lane_qualified":true%'
                     AND current_json LIKE '%"lane":"EXPLOSIVE"%'"""
            )
    except Exception:
        pass

_ensure_runtime_columns()
