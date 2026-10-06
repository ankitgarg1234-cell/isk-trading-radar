from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, SessionLocal, engine


class DMPosition(Base):
    __tablename__ = "dm_positions"

    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    shares: Mapped[int] = mapped_column(Integer, default=0)
    avg_cost: Mapped[float] = mapped_column(Float, default=0.0)
    peak: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_asof: Mapped[str | None] = mapped_column(String(16), nullable=True)
    pending_stop_exit: Mapped[bool] = mapped_column(Boolean, default=False)
    last_verified_fund_status: Mapped[str] = mapped_column(String(16), default="UNKNOWN")
    last_verified_fund_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class DMCash(Base):
    __tablename__ = "dm_cash"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    cash_usd: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class DMStrategyState(Base):
    __tablename__ = "dm_strategy_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    scan_status: Mapped[str] = mapped_column(String(24), default="NEVER_RUN")
    variant: Mapped[str] = mapped_column(String(24), default="baseline")
    snapshot_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    scan_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    scan_finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DMTrade(Base):
    __tablename__ = "dm_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    side: Mapped[str] = mapped_column(String(8))
    shares: Mapped[int] = mapped_column(Integer)
    price: Mapped[float] = mapped_column(Float)
    fees: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_or_create_state(db):
    row = db.query(DMStrategyState).filter(DMStrategyState.id == 1).first()
    if row is None:
        row = DMStrategyState(id=1)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def get_or_create_cash(db):
    row = db.query(DMCash).filter(DMCash.id == 1).first()
    if row is None:
        row = DMCash(id=1, cash_usd=0.0)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row
