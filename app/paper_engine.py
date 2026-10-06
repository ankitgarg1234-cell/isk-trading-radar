from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo
from sqlalchemy import or_

from .config import settings
from .db import (
    SessionLocal, RadarCandidate, PortfolioPreference,
    PaperAccount, PaperPosition, PaperTrade, PaperSnapshot,
)
from .portfolio_engine import INVESTABLE_ENTRY_ACTIONS, MIN_ENTRY_RISK_REWARD, build_optimizer_plan, candidate_rank_score, normalise_profile, suggested_position_size
from .analysis_engine import position_action

PAPER_ACCOUNT = "Optimizer Paper"
BENCHMARK_SYMBOL = "^SP500TR"
NY = ZoneInfo("America/New_York")


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _observed(d: date) -> date:
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    d = date(year, month, 1)
    d += timedelta(days=(weekday - d.weekday()) % 7 + (n - 1) * 7)
    return d


def _last_weekday(year: int, month: int, weekday: int) -> date:
    d = date(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def _easter_sunday(year: int) -> date:
    # Anonymous Gregorian algorithm; NYSE observes Good Friday.
    a = year % 19; b = year // 100; c = year % 100
    d = b // 4; e = b % 4; f = (b + 8) // 25
    g = (b - f + 1) // 3; h = (19 * a + b - d - g + 15) % 30
    i = c // 4; k = c % 4; l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _nyse_holidays(year: int) -> set[date]:
    return {
        _observed(date(year, 1, 1)),
        _nth_weekday(year, 1, 0, 3),   # MLK
        _nth_weekday(year, 2, 0, 3),   # Presidents Day
        _easter_sunday(year) - timedelta(days=2),
        _last_weekday(year, 5, 0),     # Memorial Day
        _observed(date(year, 6, 19)),
        _observed(date(year, 7, 4)),
        _nth_weekday(year, 9, 0, 1),   # Labor Day
        _nth_weekday(year, 11, 3, 4),  # Thanksgiving
        _observed(date(year, 12, 25)),
    }


def trading_sessions_elapsed(opened_at: datetime | None, now: datetime | None = None) -> int:
    opened = _utc(opened_at)
    current = _utc(now or datetime.now(timezone.utc))
    if not opened or not current or current < opened:
        return 0
    start = opened.astimezone(NY).date()
    end = current.astimezone(NY).date()
    holidays: set[date] = set()
    for year in range(start.year - 1, end.year + 2):
        holidays |= _nyse_holidays(year)
    sessions = 0
    d = start
    while d <= end:
        if d.weekday() < 5 and d not in holidays:
            sessions += 1
        d += timedelta(days=1)
    return sessions


def _benchmark_prices(provider, started_at: datetime, symbol: str = BENCHMARK_SYMBOL) -> tuple[float | None, float | None]:
    """Return adjusted benchmark start/latest closes for total-return comparison."""
    try:
        chart = provider.chart(symbol, "1y", "1d")
        if hasattr(provider, "_rows_from_chart"):
            rows, *_ = provider._rows_from_chart(chart)
            if rows:
                start_date = _utc(started_at).date().isoformat() if _utc(started_at) else rows[0]["date"]
                start_row = next((r for r in rows if r.get("date") >= start_date), rows[-1])
                return float(start_row["close"]), float(rows[-1]["close"])
        meta = chart.get("meta") or {}
        current = meta.get("regularMarketPrice") or meta.get("currentMarketPrice")
        return (float(current), float(current)) if current else (None, None)
    except Exception:
        return None, None


def _ensure_account(db) -> PaperAccount:
    account = db.query(PaperAccount).filter(PaperAccount.account == PAPER_ACCOUNT).first()
    if account:
        if account.benchmark_symbol != BENCHMARK_SYMBOL:
            account.benchmark_symbol = BENCHMARK_SYMBOL
            account.benchmark_start_price = None
            account.benchmark_last_price = None
            db.flush()
        return account
    account = PaperAccount(
        account=PAPER_ACCOUNT,
        starting_cash=settings.paper_starting_cash,
        cash=settings.paper_starting_cash,
        benchmark_symbol=BENCHMARK_SYMBOL,
        enabled=settings.paper_trading_enabled,
    )
    db.add(account)
    db.flush()
    return account


def _candidate_payloads(
    db,
    extra_symbols: list[str] | None = None,
    *,
    ranked_limit: int = 0,
) -> dict[str, dict]:
    """Load only the compact candidate rows needed for this paper cycle.

    Normal scanner cycles pass ``ranked_limit=0`` and therefore read only the
    current paper holdings. The Top-20 ranked candidates are
    loaded only when an entry event or the daily rebalance actually needs the
    optimizer.  This keeps Neon egress bounded while preserving immediate entry
    decisions.
    """
    rows = []
    if ranked_limit > 0:
        rows = db.query(RadarCandidate).filter(
            or_(
                RadarCandidate.lane_qualified == True,
                RadarCandidate.current_json.like('%"lane_qualified":true%'),
            )
        ).order_by(
            RadarCandidate.portfolio_rank_score.desc(),
            RadarCandidate.updated_at.desc(),
        ).limit(max(1, ranked_limit)).all()
    have = {r.symbol for r in rows}
    missing = [s for s in (extra_symbols or []) if s not in have]
    if missing:
        rows += db.query(RadarCandidate).filter(RadarCandidate.symbol.in_(missing)).all()
    out: dict[str, dict] = {}
    for row in rows:
        try:
            payload = json.loads(row.current_json or "{}")
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        payload.setdefault("symbol", row.symbol)
        payload.setdefault("price", row.price)
        payload.setdefault("deterministic_score", row.score)
        payload.setdefault("ai_score", row.ai_score)
        payload.setdefault("category", row.category)
        payload.setdefault("action", row.action)
        out[row.symbol] = payload
    return out


def _trade_cost(gross: float) -> float:
    return abs(gross) * max(0.0, settings.paper_trade_cost_bps) / 10000.0


def _sell(db, account: PaperAccount, pos: PaperPosition, price: float, shares: float, reason: str, rank_score: float = 0.0) -> None:
    # Avanza-style paper execution: whole shares only.
    shares = math.floor(min(float(pos.shares), max(0.0, float(shares))) + 1e-9)
    if shares <= 0 or price <= 0:
        return
    gross = shares * price
    fee = _trade_cost(gross)
    account.cash += gross - fee
    pos.shares -= shares
    db.add(PaperTrade(account=PAPER_ACCOUNT, symbol=pos.symbol, side="SELL", shares=shares, price=price, fees=fee, rank_score=rank_score, reason=reason[:255]))
    if pos.shares <= 1e-9:
        db.delete(pos)
    else:
        pos.updated_at = datetime.now(timezone.utc)


def _buy(db, account: PaperAccount, symbol: str, price: float, target_value: float, rank_score: float, reason: str, analysis: dict | None = None) -> float:
    """Paper-buy up to target_value using whole shares only."""
    if price <= 0 or target_value <= 0 or account.cash <= 0:
        return 0.0
    fee_rate = max(0.0, settings.paper_trade_cost_bps) / 10000.0
    spendable = min(float(target_value), float(account.cash))
    shares = math.floor(spendable / (price * (1.0 + fee_rate)) + 1e-12)
    if shares <= 0:
        return 0.0
    gross = shares * price
    fee = _trade_cost(gross)
    account.cash -= gross + fee
    pos = db.query(PaperPosition).filter(PaperPosition.account == PAPER_ACCOUNT, PaperPosition.symbol == symbol).first()
    if pos:
        total_shares = pos.shares + shares
        pos.avg_cost = ((pos.avg_cost * pos.shares) + gross) / total_shares
        pos.shares = total_shares
        pos.rank_score_at_entry = rank_score
        pos.reason = reason[:255]
        if analysis and getattr(pos, "entry_target", None) in (None, 0):
            tp = analysis.get("target_plan") or {}
            hp = analysis.get("holding_horizon") or {}
            pos.entry_target = tp.get("base_target")
            pos.entry_stretch_target = tp.get("stretch_target")
            levels = analysis.get("levels") or {}
            pos.entry_stop = levels.get("entry_stop") or levels.get("stop")
            pos.entry_horizon_days = hp.get("max_days")
            pos.entry_plan_version = analysis.get("scoring_version")
        pos.updated_at = datetime.now(timezone.utc)
    else:
        tp = (analysis or {}).get("target_plan") or {}
        hp = (analysis or {}).get("holding_horizon") or {}
        db.add(PaperPosition(
            account=PAPER_ACCOUNT, symbol=symbol, shares=shares, avg_cost=price,
            rank_score_at_entry=rank_score, reason=reason[:255],
            entry_target=tp.get("base_target"),
            entry_stretch_target=tp.get("stretch_target"),
            entry_stop=(((analysis or {}).get("levels") or {}).get("entry_stop")
                        or ((analysis or {}).get("levels") or {}).get("stop")),
            entry_horizon_days=hp.get("max_days"),
            entry_plan_version=(analysis or {}).get("scoring_version"),
        ))
    db.add(PaperTrade(account=PAPER_ACCOUNT, symbol=symbol, side="BUY", shares=shares, price=price, fees=fee, rank_score=rank_score, reason=reason[:255]))
    return shares


def _live_paper_price(provider, symbol: str, fallback: float = 0.0) -> tuple[float, str]:
    try:
        q = provider.quick_scan(symbol)
        price = float((q or {}).get("price") or 0)
        if price > 0:
            return price, "live quick scan"
    except Exception:
        pass
    return float(fallback or 0), "latest stored quote"


def manual_paper_close(provider, symbol: str, shares: float | None = None) -> dict:
    if settings.score_band_trial_armed_at:
        return {"status": "blocked", "message": "The active paper trial executes the agreed strategy automatically."}
    symbol = str(symbol or "").upper().strip()
    if not symbol:
        return {"status": "error", "message": "Ticker is required"}
    with SessionLocal() as db:
        account = _ensure_account(db)
        pos = db.query(PaperPosition).filter(PaperPosition.account == PAPER_ACCOUNT, PaperPosition.symbol == symbol).first()
        if not pos:
            return {"status": "error", "message": f"{symbol} is not an open paper position"}
        payload = _candidate_payloads(db, [symbol], ranked_limit=0).get(symbol) or {}
        price, price_source = _live_paper_price(provider, symbol, float(payload.get("price") or pos.avg_cost or 0))
        if price <= 0:
            return {"status": "error", "message": f"No usable price is available for {symbol}"}
        qty = math.floor(float(pos.shares) if shares in (None, 0) else min(float(pos.shares), float(shares)) + 1e-9)
        if qty <= 0:
            return {"status": "error", "message": "Shares to close must be at least 1"}
        before = float(account.cash or 0)
        _sell(db, account, pos, price, qty, "MANUAL PAPER CLOSE", candidate_rank_score(payload).get("score", 0))
        db.commit()
        return {"status": "ok", "symbol": symbol, "side": "SELL", "shares": qty, "price": round(price, 4), "price_source": price_source, "cash_before": round(before, 2), "cash_after": round(float(account.cash or 0), 2)}


def manual_paper_add(provider, symbol: str, shares: float) -> dict:
    if settings.score_band_trial_armed_at:
        return {"status": "blocked", "message": "The active paper trial executes the agreed strategy automatically."}
    symbol = str(symbol or "").upper().strip()
    qty = math.floor(float(shares or 0) + 1e-9)
    if not symbol:
        return {"status": "error", "message": "Ticker is required"}
    if qty <= 0:
        return {"status": "error", "message": "Shares to add must be at least 1 whole share"}
    with SessionLocal() as db:
        account = _ensure_account(db)
        payload = _candidate_payloads(db, [symbol], ranked_limit=0).get(symbol) or {}
        lane = payload.get("lane") if payload.get("lane_qualified") is True else None
        if lane not in {"CORE_QUALITY", "EXPLOSIVE"}:
            return {"status": "blocked", "message": f"{symbol} is not currently qualified for Core Quality or Explosive; manual paper buys remain lane-gated."}
        risk_reward = float(payload.get("risk_reward") or 0)
        if risk_reward < MIN_ENTRY_RISK_REWARD:
            return {"status": "blocked", "message": f"{symbol} has modeled R/R {risk_reward:.2f}x. New/additional investment requires at least {MIN_ENTRY_RISK_REWARD:.1f}x.", "risk_reward": round(risk_reward, 2), "minimum_risk_reward": MIN_ENTRY_RISK_REWARD}
        price, price_source = _live_paper_price(provider, symbol, float(payload.get("price") or 0))
        if price <= 0:
            return {"status": "error", "message": f"No usable price is available for {symbol}"}
        fee_rate = max(0.0, settings.paper_trade_cost_bps) / 10000.0
        required = qty * price * (1.0 + fee_rate)
        if required > float(account.cash or 0) + 1e-9:
            return {"status": "blocked", "message": (f"Action can't be completed — no money left to take this action. Available paper cash ${float(account.cash or 0):.2f}; ${required:.2f} is required for {qty} whole share{'s' if qty != 1 else ''}."), "cash": round(float(account.cash or 0), 2), "required_cash": round(required, 2)}
        before = float(account.cash or 0)
        bought = _buy(db, account, symbol, price, required, candidate_rank_score(payload).get("score", 0), f"MANUAL PAPER ADD • {payload.get('lane_label') or lane}", analysis=payload)
        db.commit()
        return {"status": "ok", "symbol": symbol, "side": "BUY", "shares": bought, "price": round(price, 4), "price_source": price_source, "cash_before": round(before, 2), "cash_after": round(float(account.cash or 0), 2)}

def _normalise_whole_share_positions(db, account: PaperAccount, analyses: dict[str, dict]) -> list[dict]:
    """Repair legacy fractional paper positions without creating fake SELL trades.

    Fractional positions were produced by an earlier paper-allocation bug. We
    floor them to whole shares and return the fractional mark-to-market value to
    paper cash, preserving account equity at the correction instant.
    """
    corrections = []
    positions = db.query(PaperPosition).filter(PaperPosition.account == PAPER_ACCOUNT).all()
    now = datetime.now(timezone.utc)
    for pos in positions:
        original = float(pos.shares or 0)
        whole = math.floor(original + 1e-9)
        fraction = max(0.0, original - whole)
        if fraction <= 1e-9:
            continue
        a = analyses.get(pos.symbol) or {}
        price = float(a.get("price") or pos.avg_cost or 0)
        cash_credit = fraction * price if price > 0 else 0.0
        account.cash += cash_credit
        corrections.append({
            "symbol": pos.symbol,
            "from_shares": original,
            "to_shares": whole,
            "cash_credit": cash_credit,
        })
        if whole <= 0:
            db.delete(pos)
        else:
            pos.shares = whole
            pos.updated_at = now
    if corrections:
        db.flush()
    return corrections


def _equity(db, account: PaperAccount, analyses: dict[str, dict]) -> tuple[float, float, list[dict]]:
    positions = db.query(PaperPosition).filter(PaperPosition.account == PAPER_ACCOUNT).all()
    invested = 0.0
    rows = []
    for p in positions:
        a = analyses.get(p.symbol) or {}
        price = float(a.get("price") or p.avg_cost or 0)
        value = p.shares * price
        invested += value
        rows.append({"symbol": p.symbol, "shares": p.shares, "avg_cost": p.avg_cost, "price": price, "value": value, "rank_score": candidate_rank_score(a).get("score", 0) if a else p.rank_score_at_entry})
    return account.cash + invested, invested, rows


def _lane_evidence_reliable(a: dict) -> bool:
    f = a.get("fundamentals") or {}
    t = a.get("technicals") or {}
    return bool(
        str(a.get("fundamental_confidence") or "low").lower() in {"medium", "high"}
        and float(f.get("marketCap") or 0) > 0
        and float(t.get("avg_dollar_volume_20") or 0) > 0
    )


def _reconstruct_position_before_trade(db, trade: PaperTrade) -> dict | None:
    history = db.query(PaperTrade).filter(
        PaperTrade.account == PAPER_ACCOUNT,
        PaperTrade.symbol == trade.symbol,
        PaperTrade.created_at < trade.created_at,
    ).order_by(PaperTrade.created_at.asc(), PaperTrade.id.asc()).all()
    shares = 0.0
    avg_cost = 0.0
    rank_score = 0.0
    reason = ""
    opened_at = None
    for row in history:
        qty = float(row.shares or 0)
        if str(row.side or "").upper() == "BUY" and qty > 0:
            new_total = shares + qty
            avg_cost = ((avg_cost * shares) + (float(row.price or 0) * qty)) / new_total if new_total > 0 else 0.0
            shares = new_total
            rank_score = float(row.rank_score or rank_score or 0)
            reason = str(row.reason or reason or "")
            opened_at = opened_at or row.created_at
        elif str(row.side or "").upper() == "SELL" and qty > 0:
            shares = max(0.0, shares - qty)
            if shares <= 1e-9:
                shares = 0.0
                avg_cost = 0.0
                opened_at = None
    if shares <= 0:
        return None
    return {"shares": shares, "avg_cost": avg_cost, "rank_score": rank_score, "reason": reason, "opened_at": opened_at}


def _repair_unreliable_lane_exits(db, account: PaperAccount, analyses: dict[str, dict], now: datetime) -> list[dict]:
    # Only repair very recent forced exits. Older outside-lane liquidations were
    # intentional portfolio cleanup and must not be resurrected.
    cutoff = now - timedelta(minutes=20)
    trades = db.query(PaperTrade).filter(
        PaperTrade.account == PAPER_ACCOUNT,
        PaperTrade.side == "SELL",
        PaperTrade.created_at >= cutoff,
        PaperTrade.reason.like("OUTSIDE ACTIVE LANES%"),
    ).order_by(PaperTrade.created_at.asc()).all()
    repaired = []
    for trade in trades:
        a = analyses.get(trade.symbol) or {}
        current_lane = a.get("lane") if a.get("lane_qualified") is True else None
        unreliable = not _lane_evidence_reliable(a)
        if not unreliable and current_lane not in {"CORE_QUALITY", "EXPLOSIVE"}:
            continue
        existing = db.query(PaperPosition).filter(PaperPosition.account == PAPER_ACCOUNT, PaperPosition.symbol == trade.symbol).first()
        if existing:
            continue
        prior = _reconstruct_position_before_trade(db, trade)
        if not prior:
            continue
        proceeds = float(trade.shares or 0) * float(trade.price or 0) - float(trade.fees or 0)
        if float(account.cash or 0) + 1e-9 < proceeds:
            continue
        account.cash -= proceeds
        db.add(PaperPosition(
            account=PAPER_ACCOUNT, symbol=trade.symbol, shares=prior["shares"],
            avg_cost=prior["avg_cost"], rank_score_at_entry=prior["rank_score"],
            reason=(prior["reason"] or "RESTORED AFTER UNRELIABLE LANE DATA")[:255],
            opened_at=prior["opened_at"] or now, updated_at=now,
        ))
        db.delete(trade)
        repaired.append({"symbol": trade.symbol, "shares": prior["shares"], "reason": "Reversed unreliable-data lane exit"})
    if repaired:
        db.flush()
    return repaired

def run_paper_cycle(provider, *, force_rebalance: bool = False, entry_event: bool = False) -> dict:
    """Run one shadow-paper cycle. No broker or real Position/Trade rows are touched."""
    if settings.score_band_trial_armed_at:
        return {"status": "canonical_strategy", "executed_orders": [], "blocked_orders": []}
    if not settings.paper_trading_enabled:
        return {"status": "disabled"}
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        account = _ensure_account(db)
        if not account.enabled:
            return {"status": "disabled"}
        paper_positions = db.query(PaperPosition).filter(PaperPosition.account == PAPER_ACCOUNT).all()
        recent_forced_symbols = [
            x.symbol for x in db.query(PaperTrade).filter(
                PaperTrade.account == PAPER_ACCOUNT,
                PaperTrade.side == "SELL",
                PaperTrade.created_at >= now - timedelta(hours=6),
                PaperTrade.reason.like("OUTSIDE ACTIVE LANES%"),
            ).all()
        ]
        # Load current holdings plus any very recent forced-lane exits so transient
        # evidence failures can be detected and safely reversed.
        analysis_symbols = list(dict.fromkeys([p.symbol for p in paper_positions] + recent_forced_symbols))
        analyses = _candidate_payloads(db, analysis_symbols, ranked_limit=0)
        repaired_lane_exits = _repair_unreliable_lane_exits(db, account, analyses, now)
        if repaired_lane_exits:
            paper_positions = db.query(PaperPosition).filter(PaperPosition.account == PAPER_ACCOUNT).all()
        pref = db.query(PortfolioPreference).filter(PortfolioPreference.account == "Main").first()
        profile = normalise_profile(pref.risk_profile if pref else "MEDIUM")

        # One-time state repair for positions created by the old fractional-share
        # allocator. This is bookkeeping correction, not a market SELL.
        executed_orders: list[dict] = []
        blocked_orders: list[dict] = []
        forced_lane_exits: list[dict] = []
        whole_share_corrections = _normalise_whole_share_positions(db, account, analyses)
        if whole_share_corrections:
            paper_positions = db.query(PaperPosition).filter(PaperPosition.account == PAPER_ACCOUNT).all()

        # Immediate risk management uses the existing thesis-gated position action.
        # Explosive positions have a separate 20-U.S.-trading-session thesis clock.
        for p in list(paper_positions):
            a = analyses.get(p.symbol) or {}
            price = float(a.get("price") or 0)
            action = str(a.get("action") or "").upper()
            reason_upper = str(p.reason or "").upper()
            current_lane = a.get("lane") if a.get("lane_qualified") is True else None
            # Incident cleanup: TTAN was an intentional legacy/outside-lane exit
            # that was briefly resurrected by the first overly-broad repair pass.
            # Keep it only if it has genuinely re-qualified into an active lane.
            if p.symbol == "TTAN" and current_lane not in {"CORE_QUALITY", "EXPLOSIVE"} and price > 0:
                qty = math.floor(float(p.shares or 0) + 1e-9)
                if qty > 0:
                    _sell(
                        db, account, p, price, qty,
                        "LEGACY OUTSIDE-LANE CLEANUP — capital released",
                        candidate_rank_score(a).get("score", 0) if a else p.rank_score_at_entry,
                    )
                    forced_lane_exits.append({
                        "symbol": p.symbol, "shares": qty, "price": round(price, 4),
                        "reason": "Legacy outside-lane cleanup after repair correction",
                    })
                continue
            # Paper capital may remain invested only in the two active lanes.
            # Missing/stale lane metadata is not enough to force a sale; an
            # explicit refreshed lane_qualified field is required.
            if (
                "lane_qualified" in a
                and current_lane not in {"CORE_QUALITY", "EXPLOSIVE"}
                and _lane_evidence_reliable(a)
                and price > 0
            ):
                qty = math.floor(float(p.shares or 0) + 1e-9)
                rank_score = candidate_rank_score(a).get("score", 0) if a else p.rank_score_at_entry
                if qty > 0:
                    _sell(db, account, p, price, qty, "OUTSIDE ACTIVE LANES — no longer eligible for Core Quality / Explosive; capital released", rank_score)
                    forced_lane_exits.append({"symbol": p.symbol, "shares": qty, "price": round(price, 4), "reason": "No longer qualifies for Core Quality or Explosive"})
                continue
            was_explosive = "EXPLOSIVE LANE" in reason_upper and "GRADUATED TO CORE" not in reason_upper
            sessions = trading_sessions_elapsed(p.opened_at, now)
            if was_explosive and sessions > 20 and price > 0:
                if bool(a.get("core_quality_qualified")):
                    p.reason = ("GRADUATED TO CORE — 20-session Explosive thesis completed | " + str(p.reason or ""))[:255]
                    p.updated_at = now
                    was_explosive = False
                else:
                    rank_score = candidate_rank_score(a).get("score", 0) if a else p.rank_score_at_entry
                    _sell(
                        db, account, p, price, p.shares,
                        "Explosive 20-session thesis expired — no longer qualifies Core Quality",
                        rank_score,
                    )
                    continue
            if a and price:
                try:
                    action, action_reason = position_action(a, price, {"shares": p.shares, "avg_cost": p.avg_cost, "account": "Paper", "opened_at": p.opened_at, "entry_target": p.entry_target, "entry_stretch_target": p.entry_stretch_target, "entry_stop": p.entry_stop, "entry_horizon_days": p.entry_horizon_days, "entry_plan_version": p.entry_plan_version})
                    action = str(action or "").upper()
                    # Keep the paper-cycle optimizer consistent with the actual
                    # owned-position state without rewriting the global candidate.
                    a["action"] = action
                    a["action_reason"] = action_reason
                except Exception:
                    pass
            rank_score = candidate_rank_score(a).get("score", 0) if a else p.rank_score_at_entry
            if action == "EXIT":
                _sell(db, account, p, price, p.shares, "Dashboard thesis-invalidated EXIT", rank_score)
            elif action == "REDUCE":
                _sell(db, account, p, price, max(1, math.floor(p.shares * 0.5)), "Dashboard thesis-invalidated REDUCE", rank_score)
            elif action == "TAKE PARTIAL PROFIT" and p.shares >= 2:
                trim_pct = float(a.get("profit_take_pct") or 25) / 100.0
                _sell(db, account, p, price, max(1, math.floor(p.shares * trim_pct)), str(a.get("profit_take_reason") or "Dashboard TAKE PARTIAL PROFIT"), rank_score)
        db.flush()

        # If immediate risk management changes the holdings, rerun the Top-20
        # allocation immediately so every currently qualified entry is reconsidered.
        current_after_risk = db.query(PaperPosition).filter(PaperPosition.account == PAPER_ACCOUNT).all()
        risk_changed_portfolio = len(current_after_risk) < len(paper_positions)

        last_rebalance = _utc(account.last_rebalance_at)
        daily_due = last_rebalance is None or (now - last_rebalance).total_seconds() >= settings.paper_rebalance_seconds
        entry_due = bool(entry_event or risk_changed_portfolio)
        rebalance_due = bool(force_rebalance or daily_due or entry_due)
        if rebalance_due:
            current = current_after_risk
            owned = {p.symbol for p in current}
            # Only optimizer events load the ranked candidate funnel.  Top 20 is
            # sufficient because the UI/optimizer never allocates outside it.
            analyses.update(_candidate_payloads(
                db, [p.symbol for p in current], ranked_limit=settings.optimizer_visible_limit
            ))
            # The ranked reload above can replace the locally derived owned action
            # with the persisted new-entry state. Re-derive owned actions after the
            # reload so HOLD/ADD/REDUCE semantics cannot drift before allocation.
            for p in current:
                a = analyses.get(p.symbol) or {}
                price = float(a.get("price") or 0)
                if not a or price <= 0:
                    continue
                try:
                    owned_action, owned_reason = position_action(
                        a, price, {"shares": p.shares, "avg_cost": p.avg_cost, "account": "Paper", "opened_at": p.opened_at, "entry_target": p.entry_target, "entry_stretch_target": p.entry_stretch_target, "entry_stop": p.entry_stop, "entry_horizon_days": p.entry_horizon_days, "entry_plan_version": p.entry_plan_version}
                    )
                    a["action"] = str(owned_action or "").upper()
                    a["action_reason"] = owned_reason
                except Exception:
                    pass
            plan = build_optimizer_plan(
                analyses, owned, profile=profile,
                visible_limit=settings.optimizer_visible_limit,
                shortlist_limit=settings.optimizer_shortlist_limit,
            )

            # Continuous sizing applies only when a brand-new symbol is opened.
            # Existing paper holdings keep their current quantity; no automatic
            # ADD or target-repair resizing is performed after entry.
            current_by_symbol = {p.symbol: p for p in current}
            new_rows = [
                r for r in plan["selected_new"]
                if r["symbol"] not in current_by_symbol
            ]
            allocation_rows = [(r, False, "NEW") for r in new_rows]

            if allocation_rows:
                # One sizing engine for dashboard and paper execution:
                # Deterministic score sets the initial target allocation; stop risk
                # and cash can only reduce it. If aggregate desired capital exceeds cash,
                # scale every target proportionally before whole-share rounding.
                equity_now, _, _ = _equity(db, account, analyses)
                fee_rate = max(0.0, settings.paper_trade_cost_bps) / 10000.0
                desired = []
                for r, is_add, allocation_kind in allocation_rows:
                    a = r["analysis"] or {}
                    price = float(a.get("price") or 0)
                    if price <= 0:
                        continue
                    existing_pos = current_by_symbol.get(r["symbol"]) if is_add else None
                    existing_value = (float(existing_pos.shares) * price) if existing_pos else 0.0
                    sizing = suggested_position_size(
                        a,
                        cash=float(account.cash or 0),
                        reserve_cash=0.0,
                        portfolio_value=max(float(equity_now or 0), float(account.starting_cash or 0)),
                        profile=profile,
                        fx_rate_to_base=1.0,
                        existing_value=existing_value,
                        whole_shares=True,
                    )
                    rounded_shares = int(sizing.get("shares") or 0)
                    one_share_cost = price * (1.0 + fee_rate)
                    rounded_spend = rounded_shares * one_share_cost
                    if rounded_shares <= 0:
                        # Quietly skip target-repair rows that are already at/near
                        # target; only surface an execution blocker for a genuine
                        # new/add action.
                        if allocation_kind != "TARGET REPAIR":
                            blocked_orders.append({
                                "symbol": r["symbol"],
                                "decision": "ADD" if is_add else str(r.get("entry_signal") or "BUY"),
                                "reason": sizing.get("reason") or "No executable whole-share size within score/risk/cash limits",
                                "target_capital": float(sizing.get("target_capital") or 0),
                                "cash": round(float(account.cash or 0), 2),
                            })
                        continue
                    target_capital = min(
                        max(float(sizing.get("target_capital") or 0), rounded_spend),
                        float(account.cash or 0),
                    )
                    desired.append((r, price, sizing, target_capital, is_add, allocation_kind, rounded_shares))

                total_desired = sum(x[3] for x in desired)
                scale = min(1.0, (float(account.cash or 0) / total_desired)) if total_desired > 0 else 0.0
                for r, price, sizing, target_capital, is_add, allocation_kind, rounded_shares in desired:
                    scaled_capital = target_capital * scale
                    one_share_cost = price * (1.0 + fee_rate)
                    if scaled_capital + 1e-9 < one_share_cost:
                        blocked_orders.append({
                            "symbol": r["symbol"],
                            "decision": "ADD" if is_add else str(r.get("entry_signal") or "BUY"),
                            "reason": (
                                (
                                    f"Action can't be completed — no money left to take this action. "
                                    f"Available paper cash ${float(account.cash or 0):.2f}; "
                                    f"minimum required for 1 whole share is ${one_share_cost:.2f}."
                                )
                                if float(account.cash or 0) + 1e-9 < one_share_cost
                                else (
                                    f"Action can't be completed — the score-based allocation is ${scaled_capital:.2f}, "
                                    f"below the ${one_share_cost:.2f} cost of 1 whole share."
                                )
                            ),
                            "target_capital": round(scaled_capital, 2),
                            "cash": round(float(account.cash or 0), 2),
                            "minimum_one_share_cost": round(one_share_cost, 2),
                        })
                        continue
                    lane_label = str((r["analysis"] or {}).get("lane_label") or r.get("lane_label") or "Qualified Lane")
                    existing_pos = current_by_symbol.get(r["symbol"]) if is_add else None
                    if is_add and existing_pos:
                        existing_reason = str(existing_pos.reason or "").upper()
                        if "GRADUATED TO CORE" in existing_reason or "CORE QUALITY LANE" in existing_reason:
                            lane_label = "Core Quality Lane"
                        elif "EXPLOSIVE LANE" in existing_reason:
                            lane_label = "Explosive Lane"
                    target_pct = float(sizing.get("target_allocation_pct") or 0)
                    scale_note = f" • cash-scaled {scale:.2f}x" if scale < 0.999 else ""
                    decision = "ADD" if allocation_kind == "ADD" else "TARGET TOP-UP" if allocation_kind == "TARGET REPAIR" else str(r.get("entry_signal") or "BUY")
                    bought = _buy(
                        db, account, r["symbol"], price, scaled_capital, r["rank_score"],
                        (
                            f"{lane_label} • Top-20 #{r['market_rank']} {decision} • "
                            f"priority target {target_pct:.0f}%{scale_note}"
                        ),
                        analysis=r.get("analysis") or {},
                    )
                    if bought > 0:
                        executed_orders.append({
                            "symbol": r["symbol"], "decision": decision, "shares": bought,
                            "price": round(price, 4), "capital": round(bought * price, 2),
                            "rank_score": round(float(r["rank_score"]), 1),
                        })
                    else:
                        blocked_orders.append({
                            "symbol": r["symbol"], "decision": decision,
                            "reason": "No whole-share order could be executed with current cash/target limits",
                            "target_capital": round(scaled_capital, 2),
                            "cash": round(float(account.cash or 0), 2),
                        })

            db.flush()
            if force_rebalance or daily_due:
                account.last_rebalance_at = now

        # Benchmark is sampled only when the compact paper snapshot is due.
        last_snapshot = db.query(PaperSnapshot).filter(PaperSnapshot.account == PAPER_ACCOUNT).order_by(PaperSnapshot.created_at.desc()).first()
        last_snap_at = _utc(last_snapshot.created_at) if last_snapshot else None
        snapshot_due = (
            last_snap_at is None
            or (now - last_snap_at).total_seconds() >= settings.paper_snapshot_seconds
            or not account.benchmark_start_price
            or not account.benchmark_last_price
        )
        if snapshot_due:
            bench_start, bench_last = _benchmark_prices(provider, account.started_at, account.benchmark_symbol)
            if bench_start and bench_last:
                # Recompute the historical start on each sample against the
                # S&P 500 Total Return Index (^SP500TR).
                account.benchmark_start_price = bench_start
                account.benchmark_last_price = bench_last
            equity, invested, rows = _equity(db, account, analyses)
            port_ret = (equity / account.starting_cash - 1) * 100 if account.starting_cash else 0.0
            bench_ret = ((account.benchmark_last_price / account.benchmark_start_price - 1) * 100) if account.benchmark_last_price and account.benchmark_start_price else 0.0
            max_equity = max([account.starting_cash] + [float(x.equity or 0) for x in db.query(PaperSnapshot).filter(PaperSnapshot.account == PAPER_ACCOUNT).all()])
            drawdown = ((equity / max_equity) - 1) * 100 if max_equity else 0.0
            db.add(PaperSnapshot(account=PAPER_ACCOUNT, equity=equity, cash=account.cash, invested=invested, benchmark_price=account.benchmark_last_price or 0, portfolio_return_pct=port_ret, benchmark_return_pct=bench_ret, excess_return_pct=port_ret-bench_ret, drawdown_pct=drawdown, positions_count=len(rows)))
        account.updated_at = now
        db.commit()
        return {
            "status": "ok",
            "account": PAPER_ACCOUNT,
            "cash": round(account.cash, 2),
            "rebalanced": rebalance_due,
            "entry_event": entry_due,
            "daily_rebalance": bool(force_rebalance or daily_due),
            "whole_share_corrections": whole_share_corrections,
            "executed_orders": executed_orders,
            "blocked_orders": blocked_orders,
            "forced_lane_exits": forced_lane_exits,
            "repaired_unreliable_lane_exits": repaired_lane_exits,
        }


def paper_status(db) -> dict:
    if settings.score_band_trial_armed_at:
        from .score_band_capture import canonical_paper_status
        return canonical_paper_status(db)
    account = db.query(PaperAccount).filter(PaperAccount.account == PAPER_ACCOUNT).first()
    if not account:
        return {
            "enabled": settings.paper_trading_enabled,
            "started": False,
            "starting_cash": settings.paper_starting_cash,
            "cash": settings.paper_starting_cash,
            "invested": 0.0,
            "equity": settings.paper_starting_cash,
            "positions": [],
            "trades": [],
            "legacy_trades": [],
            "position_count": 0,
            "trade_count": 0,
            "legacy_trade_count": 0,
            "normalized_legacy_position_count": 0,
            "normalized_legacy_symbols": [],
            "current_valid_origin_count": 0,
            "current_drawdown_pct": 0.0,
            "absolute_return": 0.0,
            "daily_pnl": 0.0,
            "daily_pnl_pct": 0.0,
            "benchmark_label": "S&P 500 Total Return",
            "core_position_count": 0,
            "explosive_position_count": 0,
            "outside_lane_position_count": 0,
        }
    positions = db.query(PaperPosition).filter(PaperPosition.account == PAPER_ACCOUNT).order_by(PaperPosition.symbol).all()
    analyses = _candidate_payloads(db, [p.symbol for p in positions], ranked_limit=0)
    equity, invested, pos_rows = _equity(db, account, analyses)
    snap = db.query(PaperSnapshot).filter(PaperSnapshot.account == PAPER_ACCOUNT).order_by(PaperSnapshot.created_at.desc()).first()
    trades = db.query(PaperTrade).filter(PaperTrade.account == PAPER_ACCOUNT).order_by(PaperTrade.created_at.desc()).limit(24).all()
    positions_by_symbol = {p.symbol: p for p in positions}
    for row in pos_rows:
        pos = positions_by_symbol.get(row.get("symbol"))
        if pos is None:
            continue
        cost_basis = float(pos.shares or 0) * float(pos.avg_cost or 0)
        pnl = float(row.get("value") or 0) - cost_basis
        analysis = analyses.get(pos.symbol) or {}
        previous_close = float(analysis.get("previous_close") or 0)
        price = float(row.get("price") or 0)
        day_change_pct = ((price / previous_close) - 1) * 100 if price > 0 and previous_close > 0 else None
        row["cost_basis"] = round(cost_basis, 2)
        row["pnl"] = round(pnl, 2)
        row["pnl_pct"] = round((pnl / cost_basis * 100) if cost_basis else 0.0, 2)
        row["previous_close"] = round(previous_close, 4) if previous_close > 0 else None
        row["day_change_pct"] = round(day_change_pct, 2) if day_change_pct is not None else None
        row["weight_pct"] = round((float(row.get("value") or 0) / equity * 100) if equity else 0.0, 2)
        row["entry_rank_score"] = round(float(pos.rank_score_at_entry or 0), 2)
        row["reason"] = pos.reason or ""
        row["opened_at"] = pos.opened_at.isoformat() if pos.opened_at else None
        sessions = trading_sessions_elapsed(pos.opened_at)
        reason_upper = str(pos.reason or "").upper()
        graduated = "GRADUATED TO CORE" in reason_upper
        raw_lane = analysis.get("lane")
        current_lane_qualified = analysis.get("lane_qualified") is True and raw_lane in {"CORE_QUALITY", "EXPLOSIVE"}
        if graduated and current_lane_qualified:
            lane = "CORE_QUALITY"
        elif "EXPLOSIVE LANE" in reason_upper:
            # Entry lane owns the 20-session lifecycle. This identifies how the
            # position was opened even when the current snapshot temporarily
            # fails the new-entry gate; sell/hold remains thesis-gated elsewhere.
            lane = "EXPLOSIVE"
        elif current_lane_qualified:
            lane = raw_lane
        else:
            # Legacy positions and holdings that no longer satisfy current lane
            # eligibility must never be mislabeled Core simply because no lane
            # metadata exists. Keep managing the position without claiming it
            # qualifies for a new Core/Explosive entry today.
            lane = "OUTSIDE_LANES"
        row["lane"] = lane
        row["lane_label"] = (
            "Explosive Lane" if lane == "EXPLOSIVE"
            else "Core Quality Lane" if lane == "CORE_QUALITY"
            else "Outside Current Lanes"
        )
        row["trading_sessions_held"] = sessions
        row["explosive_sessions_remaining"] = max(0, 20 - sessions) if lane == "EXPLOSIVE" else None
        row["graduated_from_explosive"] = graduated
    all_trade_rows = [{
        "id": t.id,
        "symbol": t.symbol,
        "side": t.side,
        "shares": t.shares,
        "price": t.price,
        "fees": t.fees,
        "rank_score": t.rank_score,
        "reason": t.reason or "",
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "legacy_rebalance": bool(
            str(t.side or "").upper() == "SELL"
            and str(t.reason or "").startswith("REBALANCE — fund newly qualified")
        ),
        "legacy_fractional": abs(float(t.shares or 0) - round(float(t.shares or 0))) > 1e-9,
    } for t in trades]
    for t in all_trade_rows:
        t["legacy_artifact"] = bool(t["legacy_rebalance"] or t["legacy_fractional"])
    trade_rows = [t for t in all_trade_rows if not t["legacy_artifact"]][:12]
    legacy_trade_rows = [t for t in all_trade_rows if t["legacy_artifact"]][:12]

    current_symbols = {p.symbol for p in positions}
    origin_trades = []
    if current_symbols:
        origin_trades = db.query(PaperTrade).filter(
            PaperTrade.account == PAPER_ACCOUNT,
            PaperTrade.side == "BUY",
            PaperTrade.symbol.in_(current_symbols),
        ).all()
    normalized_legacy_symbols = sorted({
        t.symbol for t in origin_trades
        if abs(float(t.shares or 0) - round(float(t.shares or 0))) > 1e-9
    } & current_symbols)
    normalized_legacy_set = set(normalized_legacy_symbols)
    current_valid_origin_count = max(0, len(pos_rows) - len(normalized_legacy_symbols))
    for row in pos_rows:
        row["origin_type"] = "NORMALIZED LEGACY" if row.get("symbol") in normalized_legacy_set else "WHOLE-SHARE BUY"

    absolute_return = equity - float(account.starting_cash or 0)
    snapshots = db.query(PaperSnapshot).filter(
        PaperSnapshot.account == PAPER_ACCOUNT
    ).order_by(PaperSnapshot.created_at.desc()).limit(200).all()
    today_ny = datetime.now(timezone.utc).astimezone(NY).date()
    prior_day_snapshot = next(
        (
            s for s in snapshots
            if _utc(s.created_at) and _utc(s.created_at).astimezone(NY).date() < today_ny
        ),
        None,
    )
    daily_base_equity = float(prior_day_snapshot.equity or 0) if prior_day_snapshot else float(account.starting_cash or 0)
    daily_pnl = equity - daily_base_equity
    daily_pnl_pct = (daily_pnl / daily_base_equity * 100) if daily_base_equity else 0.0

    historical_drawdowns = [float(s.drawdown_pct or 0) for s in snapshots]
    max_drawdown_pct = abs(min([0.0] + historical_drawdowns))
    current_drawdown_pct = abs(min(0.0, float(snap.drawdown_pct or 0))) if snap else 0.0

    port_ret = (equity / account.starting_cash - 1) * 100 if account.starting_cash else 0.0
    bench_ret = ((account.benchmark_last_price / account.benchmark_start_price - 1) * 100) if account.benchmark_last_price and account.benchmark_start_price else 0.0
    return {
        "enabled": account.enabled,
        "started": True,
        "starting_cash": account.starting_cash,
        "cash": round(account.cash, 2),
        "invested": round(invested, 2),
        "equity": round(equity, 2),
        "return_pct": round(port_ret, 2),
        "absolute_return": round(absolute_return, 2),
        "daily_pnl": round(daily_pnl, 2),
        "daily_pnl_pct": round(daily_pnl_pct, 2),
        "daily_pnl_base_equity": round(daily_base_equity, 2),
        "benchmark_symbol": account.benchmark_symbol,
        "benchmark_label": "S&P 500 Total Return",
        "benchmark_return_pct": round(bench_ret, 2),
        "excess_return_pct": round(port_ret - bench_ret, 2),
        "drawdown_pct": round(max_drawdown_pct, 2),
        "current_drawdown_pct": round(current_drawdown_pct, 2),
        "positions": pos_rows,
        "position_count": len(pos_rows),
        "core_position_count": sum(1 for r in pos_rows if r.get("lane") == "CORE_QUALITY"),
        "explosive_position_count": sum(1 for r in pos_rows if r.get("lane") == "EXPLOSIVE"),
        "outside_lane_position_count": sum(1 for r in pos_rows if r.get("lane") == "OUTSIDE_LANES"),
        "trades": trade_rows,
        "trade_count": len(trade_rows),
        "legacy_trades": legacy_trade_rows,
        "legacy_trade_count": len(legacy_trade_rows),
        "normalized_legacy_position_count": len(normalized_legacy_symbols),
        "normalized_legacy_symbols": normalized_legacy_symbols,
        "current_valid_origin_count": current_valid_origin_count,
        "started_at": account.started_at,
        "updated_at": account.updated_at,
    }


def reset_paper(db) -> None:
    if settings.score_band_trial_armed_at:
        return {"status": "blocked", "message": "The active paper trial executes the agreed strategy automatically."}
    db.query(PaperSnapshot).filter(PaperSnapshot.account == PAPER_ACCOUNT).delete(synchronize_session=False)
    db.query(PaperTrade).filter(PaperTrade.account == PAPER_ACCOUNT).delete(synchronize_session=False)
    db.query(PaperPosition).filter(PaperPosition.account == PAPER_ACCOUNT).delete(synchronize_session=False)
    db.query(PaperAccount).filter(PaperAccount.account == PAPER_ACCOUNT).delete(synchronize_session=False)
    db.commit()
