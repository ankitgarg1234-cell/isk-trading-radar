from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from .config import settings
from .db import (
    SessionLocal, RadarCandidate, PortfolioPreference,
    PaperAccount, PaperPosition, PaperTrade, PaperSnapshot,
)
from .portfolio_engine import (
    build_optimizer_plan, candidate_rank_score, normalise_profile, suggested_position_size,
    classify_lane, CORE_LANE, EXPLOSIVE_LANE,
)
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
    return d + timedelta(days=((weekday - d.weekday()) % 7) + (n - 1) * 7)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    d = date(year + (month == 12), 1 if month == 12 else month + 1, 1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def _easter_sunday(year: int) -> date:
    # Anonymous Gregorian algorithm; used only to derive Good Friday.
    a = year % 19; b = year // 100; cc = year % 100; d = b // 4; e = b % 4
    f = (b + 8) // 25; g = (b - f + 1) // 3; h = (19 * a + b - d - g + 15) % 30
    i = cc // 4; k = cc % 4; l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _nyse_holidays(year: int) -> set[date]:
    holidays = {
        _observed(date(year, 1, 1)),
        _nth_weekday(year, 1, 0, 3),   # MLK
        _nth_weekday(year, 2, 0, 3),   # Washington's Birthday
        _easter_sunday(year) - timedelta(days=2),  # Good Friday
        _last_weekday(year, 5, 0),     # Memorial Day
        _observed(date(year, 6, 19)),  # Juneteenth
        _observed(date(year, 7, 4)),
        _nth_weekday(year, 9, 0, 1),   # Labor Day
        _nth_weekday(year, 11, 3, 4),  # Thanksgiving
        _observed(date(year, 12, 25)),
    }
    # New Year's Day can be observed on Dec 31 of the previous calendar year.
    holidays.add(_observed(date(year + 1, 1, 1)))
    return holidays


def trading_sessions_elapsed(opened_at: datetime | None, now: datetime | None = None) -> int:
    opened = _utc(opened_at)
    current = _utc(now or datetime.now(timezone.utc))
    if not opened or not current:
        return 0
    start = opened.astimezone(NY).date()
    end = current.astimezone(NY).date()
    if end <= start:
        return 0
    holidays: set[date] = set()
    for year in range(start.year - 1, end.year + 2):
        holidays |= _nyse_holidays(year)
    count = 0
    d = start + timedelta(days=1)
    while d <= end:
        if d.weekday() < 5 and d not in holidays:
            count += 1
        d += timedelta(days=1)
    return count


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
        fresh_cutoff = datetime.now(timezone.utc) - timedelta(hours=18)
        rows = db.query(RadarCandidate).filter(
            RadarCandidate.updated_at >= fresh_cutoff
        ).order_by(
            RadarCandidate.portfolio_rank_score.desc(),
            RadarCandidate.updated_at.desc(),
        ).limit(max(40, ranked_limit * 6)).all()
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


def _buy(
    db, account: PaperAccount, symbol: str, price: float, target_value: float,
    rank_score: float, reason: str, entry_lane: str = CORE_LANE,
) -> float:
    """Paper-buy whole shares up to a gross stock-capital target."""
    if price <= 0 or target_value <= 0 or account.cash <= 0:
        return 0.0
    fee_rate = max(0.0, settings.paper_trade_cost_bps) / 10000.0
    by_target = math.floor(float(target_value) / price + 1e-12)
    by_cash = math.floor(float(account.cash) / (price * (1.0 + fee_rate)) + 1e-12)
    shares = max(0, min(by_target, by_cash))
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
        if not pos.entry_lane:
            pos.entry_lane = entry_lane
        pos.reason = reason[:255]
        pos.updated_at = datetime.now(timezone.utc)
    else:
        db.add(PaperPosition(
            account=PAPER_ACCOUNT, symbol=symbol, shares=shares, avg_cost=price,
            rank_score_at_entry=rank_score, entry_lane=entry_lane, reason=reason[:255],
        ))
    db.add(PaperTrade(account=PAPER_ACCOUNT, symbol=symbol, side="BUY", shares=shares, price=price, fees=fee, rank_score=rank_score, reason=reason[:255]))
    return shares


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


def run_paper_cycle(provider, *, force_rebalance: bool = False, entry_event: bool = False) -> dict:
    """Run one shadow-paper cycle. No broker or real Position/Trade rows are touched."""
    if not settings.paper_trading_enabled:
        return {"status": "disabled"}
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        account = _ensure_account(db)
        if not account.enabled:
            return {"status": "disabled"}
        paper_positions = db.query(PaperPosition).filter(PaperPosition.account == PAPER_ACCOUNT).all()
        # Every scan needs only the current holdings for immediate thesis-gated
        # risk management.  Do not pull the full candidate set from Neon here.
        analyses = _candidate_payloads(db, [p.symbol for p in paper_positions], ranked_limit=0)
        pref = db.query(PortfolioPreference).filter(PortfolioPreference.account == "Main").first()
        profile = normalise_profile(pref.risk_profile if pref else "MEDIUM")

        # One-time state repair for positions created by the old fractional-share
        # allocator. This is bookkeeping correction, not a market SELL.
        whole_share_corrections = _normalise_whole_share_positions(db, account, analyses)
        if whole_share_corrections:
            paper_positions = db.query(PaperPosition).filter(PaperPosition.account == PAPER_ACCOUNT).all()

        # Immediate risk management plus the explicit 20-session Explosive thesis clock.
        for p in list(paper_positions):
            a = analyses.get(p.symbol) or {}
            price = float(a.get("price") or 0)
            if not p.entry_lane:
                current_lane = classify_lane(a).get("lane")
                p.entry_lane = current_lane or CORE_LANE
            if p.entry_lane == EXPLOSIVE_LANE:
                sessions = trading_sessions_elapsed(p.opened_at, now)
                if sessions >= settings.explosive_max_trading_sessions and a and price:
                    lane_now = classify_lane(a)
                    if lane_now.get("core_quality"):
                        p.entry_lane = CORE_LANE
                        p.reason = f"Graduated from Explosive after {sessions} trading sessions — Core quality remains qualified"
                        p.updated_at = now
                    else:
                        rank_score = candidate_rank_score(a).get("score", p.rank_score_at_entry)
                        _sell(
                            db, account, p, price, p.shares,
                            f"Explosive thesis expired after {sessions} trading sessions — no Core qualification",
                            rank_score,
                        )
                        continue
            action = str(a.get("action") or "").upper()
            if a and price:
                try:
                    action, _ = position_action(a, price, {"shares": p.shares, "avg_cost": p.avg_cost, "account": "Paper"})
                    action = str(action or "").upper()
                except Exception:
                    pass
            rank_score = candidate_rank_score(a).get("score", 0) if a else p.rank_score_at_entry
            if action == "EXIT":
                _sell(db, account, p, price, p.shares, "Dashboard thesis-invalidated EXIT", rank_score)
            elif action == "REDUCE":
                _sell(db, account, p, price, max(1, math.floor(p.shares * 0.5)), "Dashboard thesis-invalidated REDUCE", rank_score)
            elif action == "TAKE PARTIAL PROFIT" and p.shares >= 2:
                _sell(db, account, p, price, max(1, math.floor(p.shares * 0.25)), "Dashboard TAKE PARTIAL PROFIT", rank_score)
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
            plan = build_optimizer_plan(
                analyses, owned, profile=profile,
                visible_limit=settings.optimizer_visible_limit,
                shortlist_limit=settings.optimizer_shortlist_limit,
            )

            # Allocate every qualified new entry plus explicit ADD using the same
            # score-led sizing engine displayed on the dashboard.
            new_rows = [
                r for r in plan["selected_new"]
                if not db.query(PaperPosition).filter(
                    PaperPosition.account == PAPER_ACCOUNT,
                    PaperPosition.symbol == r["symbol"],
                ).first()
            ]
            add_rows = [r for r in plan["visible"] if r.get("optimizer_action") == "ADD"]
            allocation_rows = new_rows + add_rows

            if allocation_rows and float(account.cash or 0) > 0:
                equity_before, _, _ = _equity(db, account, analyses)
                proposed = []
                for r in allocation_rows:
                    a = r["analysis"] or {}
                    price = float(a.get("price") or 0)
                    if price <= 0:
                        continue
                    pos = db.query(PaperPosition).filter(
                        PaperPosition.account == PAPER_ACCOUNT,
                        PaperPosition.symbol == r["symbol"],
                    ).first()
                    existing_value = float(pos.shares * price) if pos else 0.0
                    sizing = suggested_position_size(
                        a,
                        cash=float(account.cash or 0),
                        reserve_cash=0.0,
                        portfolio_value=equity_before,
                        profile=profile,
                        fx_rate_to_base=1.0,
                        existing_value=existing_value,
                        whole_shares=True,
                        conviction_score=r["rank_score"],
                    )
                    desired = float(sizing.get("capital") or 0)
                    if desired > 0:
                        proposed.append((r, price, desired, sizing))

                fee_rate = max(0.0, settings.paper_trade_cost_bps) / 10000.0
                gross_cash_capacity = float(account.cash or 0) / (1.0 + fee_rate)
                total_desired = sum(x[2] for x in proposed)
                scale = min(1.0, gross_cash_capacity / total_desired) if total_desired > 0 else 0.0

                for r, price, desired, sizing in proposed:
                    scaled_target = desired * scale
                    lane_name = r.get("lane") or CORE_LANE
                    action_word = "ADD" if r.get("optimizer_action") == "ADD" else r.get("entry_signal")
                    _buy(
                        db, account, r["symbol"], price, scaled_target, r["rank_score"],
                        (
                            f"Top-20 #{r['market_rank']} {lane_name} {action_word} — "
                            f"priority {r['rank_score']:.1f}/100, score target {sizing.get('target_allocation_pct', 0):.0f}%"
                            + (f", cash-scaled {scale:.2f}x" if scale < 0.999 else "")
                        ),
                        entry_lane=lane_name if not db.query(PaperPosition).filter(
                            PaperPosition.account == PAPER_ACCOUNT,
                            PaperPosition.symbol == r["symbol"],
                        ).first() else (db.query(PaperPosition).filter(
                            PaperPosition.account == PAPER_ACCOUNT,
                            PaperPosition.symbol == r["symbol"],
                        ).first().entry_lane or lane_name),
                    )

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
        }


def paper_status(db) -> dict:
    account = db.query(PaperAccount).filter(PaperAccount.account == PAPER_ACCOUNT).first()
    if not account:
        return {
            "enabled": settings.paper_trading_enabled,
            "started": False,
            "starting_cash": settings.paper_starting_cash,
            "positions": [],
            "trades": [],
            "legacy_trades": [],
            "position_count": 0,
            "core_position_count": 0,
            "explosive_position_count": 0,
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
        row["lane"] = pos.entry_lane or classify_lane(analysis).get("lane") or CORE_LANE
        row["trading_sessions_held"] = trading_sessions_elapsed(pos.opened_at)
        row["explosive_sessions_remaining"] = max(
            0, settings.explosive_max_trading_sessions - row["trading_sessions_held"]
        ) if row["lane"] == EXPLOSIVE_LANE else None
        row["reason"] = pos.reason or ""
        row["opened_at"] = pos.opened_at.isoformat() if pos.opened_at else None
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
        "core_position_count": sum(r.get("lane") == CORE_LANE for r in pos_rows),
        "explosive_position_count": sum(r.get("lane") == EXPLOSIVE_LANE for r in pos_rows),
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
    db.query(PaperSnapshot).filter(PaperSnapshot.account == PAPER_ACCOUNT).delete(synchronize_session=False)
    db.query(PaperTrade).filter(PaperTrade.account == PAPER_ACCOUNT).delete(synchronize_session=False)
    db.query(PaperPosition).filter(PaperPosition.account == PAPER_ACCOUNT).delete(synchronize_session=False)
    db.query(PaperAccount).filter(PaperAccount.account == PAPER_ACCOUNT).delete(synchronize_session=False)
    db.commit()
