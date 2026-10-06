from __future__ import annotations

import json
import threading
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import BackgroundTasks, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from .data import LiveDataSource
from .db import DMCash, DMPosition, DMStrategyState, DMTrade, SessionLocal, get_or_create_cash, get_or_create_state, init_db
from .portfolio import build_portfolio_plan
from .rules import StopState, advance_stop, wilder_atr_series

app = FastAPI(title="Dual Momentum Radar", version="1.0.0")
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret, same_site="lax", https_only=False)
templates = Jinja2Templates(directory="dual_momentum/templates")
SCAN_LOCK = threading.Lock()


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.middleware("http")
async def auth_guard(request: Request, call_next):
    public = request.url.path in {"/login", "/health"}
    if settings.auth_enabled and not public and not request.session.get("dm_auth"):
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": "authentication required"}, status_code=401)
        return RedirectResponse("/login", status_code=303)
    return await call_next(request)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None, "enabled": settings.auth_enabled})


@app.post("/login", response_class=HTMLResponse)
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if not settings.auth_enabled or (username == settings.app_username and password == settings.app_password):
        request.session["dm_auth"] = True
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": "Invalid username or password", "enabled": True}, status_code=401)


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


def _load_snapshot(state: DMStrategyState) -> dict | None:
    if not state.snapshot_json:
        return None
    try:
        value = json.loads(state.snapshot_json)
        return value if isinstance(value, dict) else None
    except Exception:
        return None


def _position_dict(row: DMPosition) -> dict:
    return {
        "symbol": row.symbol,
        "shares": int(row.shares or 0),
        "avg_cost": float(row.avg_cost or 0),
        "peak": row.peak,
        "stop": row.stop,
        "stop_asof": row.stop_asof,
        "opened_on": row.opened_on,
        "pending_stop_exit": bool(row.pending_stop_exit),
        "pending_rule_exit_reason": row.pending_rule_exit_reason,
        "pending_rule_exit_date": row.pending_rule_exit_date,
        "last_verified_fund_status": row.last_verified_fund_status,
        "last_verified_fund_at": row.last_verified_fund_at,
    }


def _dashboard_state() -> dict:
    with SessionLocal() as db:
        state = get_or_create_state(db)
        cash = get_or_create_cash(db)
        positions = db.query(DMPosition).order_by(DMPosition.symbol).all()
        trades = db.query(DMTrade).order_by(DMTrade.created_at.desc()).limit(40).all()
        snapshot = _load_snapshot(state)
        position_dicts = [_position_dict(p) for p in positions]

        reserved_exit_rows = (
            db.query(DMTrade)
            .filter(DMTrade.system_reason.in_(["STOP_EXIT", "RULE_EXIT"]))
            .order_by(DMTrade.created_at.desc())
            .limit(100)
            .all()
        )
        decision_date = str((snapshot or {}).get("decision_date") or "")
        reserved_exits = []
        if decision_date:
            for trade in reserved_exit_rows:
                executed_on = str(trade.executed_on or "")
                reference_date = str(trade.reference_date or "")
                # A stop triggered on the decision close belongs to that monthly
                # execution cycle. Later mid-cycle exits reserve a vacancy.
                if executed_on > decision_date and reference_date != decision_date:
                    reserved_exits.append(
                        {
                            "symbol": trade.symbol,
                            "system_reason": trade.system_reason,
                            "executed_on": executed_on,
                            "reference_date": reference_date or None,
                        }
                    )
        plan = build_portfolio_plan(
            snapshot,
            position_dicts,
            float(cash.cash_usd or 0),
            reserved_slots=len(reserved_exits),
        ) if snapshot else None

        target_weights = (plan or {}).get("target_weights") or {}
        order_map: dict[str, list[dict]] = {}
        for order in (plan or {}).get("orders") or []:
            order_map.setdefault(order["symbol"], []).append(order)

        candidate_views = []
        if snapshot:
            for row in snapshot.get("candidates") or []:
                candidate_views.append(
                    {
                        **row,
                        "selected": row["symbol"] in set((plan or {}).get("selected") or []),
                        "target_weight": target_weights.get(row["symbol"]),
                    }
                )

        position_views = []
        holding_checks = (snapshot or {}).get("holding_checks") or {}
        for p in positions:
            check = holding_checks.get(p.symbol) or {}
            price = check.get("price")
            pnl_pct = None
            market_value = None
            if price is not None and p.avg_cost:
                pnl_pct = float(price) / float(p.avg_cost) - 1.0
                market_value = float(price) * int(p.shares or 0)
            position_views.append(
                {
                    **_position_dict(p),
                    "price": price,
                    "market_value": market_value,
                    "pnl_pct": pnl_pct,
                    "rank": check.get("rank"),
                    "momentum_positive": check.get("momentum_positive"),
                    "score": check.get("score"),
                    "atr_pct": check.get("atr_pct"),
                    "fundamental_status": check.get("fundamental_status"),
                    "fundamental_reason": check.get("fundamental_reason") or check.get("reason"),
                    "target_weight": target_weights.get(p.symbol),
                    "orders": order_map.get(p.symbol) or [],
                }
            )

        return {
            "scan": {
                "status": state.scan_status,
                "variant": state.variant,
                "started_at": state.scan_started_at,
                "finished_at": state.scan_finished_at,
                "error": state.error,
            },
            "snapshot": snapshot,
            "plan": plan,
            "cash": float(cash.cash_usd or 0),
            "positions": position_views,
            "candidates": candidate_views,
            "trades": trades,
            "reserved_exits": reserved_exits,
        }


def _scan_job(variant: str) -> None:
    if not SCAN_LOCK.acquire(blocking=False):
        return
    source = LiveDataSource()
    try:
        with SessionLocal() as db:
            state = get_or_create_state(db)
            state.scan_status = "RUNNING"
            state.variant = variant
            state.error = None
            state.scan_started_at = datetime.now(timezone.utc)
            db.commit()
            holdings = {p.symbol for p in db.query(DMPosition).all()}

        snapshot = source.scan(holdings=holdings, lagged=(variant == "lagged-21"))

        with SessionLocal() as db:
            state = get_or_create_state(db)
            state.snapshot_json = json.dumps(snapshot, separators=(",", ":"), default=str)
            state.scan_status = "READY"
            state.scan_finished_at = datetime.now(timezone.utc)
            state.error = None

            # Only verified PASS updates the incumbent's verified fundamental state.
            checks = snapshot.get("holding_checks") or {}
            for position in db.query(DMPosition).all():
                check = checks.get(position.symbol) or {}
                if check.get("fundamental_status") == "PASS":
                    position.last_verified_fund_status = "PASS"
                    position.last_verified_fund_at = snapshot.get("decision_date")
                elif check.get("fundamental_status") == "FAIL":
                    position.last_verified_fund_status = "FAIL"
                    position.last_verified_fund_at = snapshot.get("decision_date")
            db.commit()
    except Exception as exc:
        with SessionLocal() as db:
            state = get_or_create_state(db)
            state.scan_status = "ERROR"
            state.error = f"{type(exc).__name__}: {exc}"
            state.scan_finished_at = datetime.now(timezone.utc)
            db.commit()
    finally:
        source.close()
        SCAN_LOCK.release()


@app.get("/health")
def health():
    with SessionLocal() as db:
        state = get_or_create_state(db)
        return {
            "status": "ok",
            "strategy": "dual-momentum-v1",
            "scan_status": state.scan_status,
            "variant": state.variant,
            "performance": "unvalidated",
        }


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(request, "dashboard.html", _dashboard_state())


@app.get("/api/state")
def api_state():
    state = _dashboard_state()
    # SQLAlchemy rows are not JSON serializable; trade rows are omitted from this compact endpoint.
    state["trades"] = [
        {
            "symbol": t.symbol,
            "side": t.side,
            "shares": t.shares,
            "price": t.price,
            "fees": t.fees,
            "reason": t.reason,
            "system_reason": t.system_reason,
            "reference_date": t.reference_date,
            "executed_on": t.executed_on,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in state["trades"]
    ]
    return state


@app.post("/api/scan")
def run_scan(background_tasks: BackgroundTasks, variant: str = Form("baseline")):
    if variant not in {"baseline", "lagged-21"}:
        raise HTTPException(status_code=400, detail="Unknown momentum variant")
    with SessionLocal() as db:
        state = get_or_create_state(db)
        if state.scan_status == "RUNNING":
            return JSONResponse({"status": "already_running"}, status_code=202)
        state.scan_status = "QUEUED"
        state.variant = variant
        state.error = None
        db.commit()
    background_tasks.add_task(_scan_job, variant)
    return {"status": "queued", "variant": variant}


@app.post("/cash")
def set_cash(cash_usd: float = Form(...)):
    if cash_usd < 0:
        raise HTTPException(status_code=400, detail="Cash cannot be negative")
    with SessionLocal() as db:
        row = get_or_create_cash(db)
        row.cash_usd = float(cash_usd)
        row.updated_at = datetime.now(timezone.utc)
        db.commit()
    return RedirectResponse("/", status_code=303)


@app.post("/positions")
def save_position(
    symbol: str = Form(...),
    shares: int = Form(...),
    avg_cost: float = Form(...),
    peak: float | None = Form(None),
    stop: float | None = Form(None),
    opened_on: str | None = Form(None),
):
    symbol = symbol.strip().upper().replace(".", "-")
    if not symbol or shares < 0 or avg_cost < 0:
        raise HTTPException(status_code=400, detail="Invalid position")
    with SessionLocal() as db:
        row = db.query(DMPosition).filter(DMPosition.symbol == symbol).first()
        if shares == 0:
            if row:
                db.delete(row)
                db.commit()
            return RedirectResponse("/", status_code=303)
        if row is None:
            row = DMPosition(symbol=symbol, shares=shares, avg_cost=avg_cost)
            db.add(row)
        else:
            row.shares = shares
            row.avg_cost = avg_cost
        if peak is not None:
            row.peak = peak
        if stop is not None:
            row.stop = stop
        if opened_on:
            row.opened_on = opened_on
        row.updated_at = datetime.now(timezone.utc)
        db.commit()
    return RedirectResponse("/", status_code=303)


@app.post("/positions/{symbol}/delete")
def delete_position(symbol: str):
    symbol = symbol.strip().upper()
    with SessionLocal() as db:
        row = db.query(DMPosition).filter(DMPosition.symbol == symbol).first()
        if row:
            db.delete(row)
            db.commit()
    return RedirectResponse("/", status_code=303)


def _snapshot_signal(snapshot: dict | None, symbol: str) -> dict | None:
    if not snapshot:
        return None
    for row in snapshot.get("candidates") or []:
        if row.get("symbol") == symbol:
            return row
    check = (snapshot.get("holding_checks") or {}).get(symbol)
    return check if isinstance(check, dict) else None


@app.post("/trades")
def record_trade(
    symbol: str = Form(...),
    side: str = Form(...),
    shares: int = Form(...),
    price: float = Form(...),
    fees: float = Form(0.0),
    trade_date: str | None = Form(None),
    reason: str = Form(""),
):
    symbol = symbol.strip().upper().replace(".", "-")
    side = side.strip().upper()
    if side not in {"BUY", "SELL"} or shares <= 0 or price <= 0 or fees < 0:
        raise HTTPException(status_code=400, detail="Invalid trade")
    effective_date = trade_date or datetime.now(timezone.utc).date().isoformat()
    try:
        date.fromisoformat(effective_date)
    except Exception:
        raise HTTPException(status_code=400, detail="Trade date must be YYYY-MM-DD")

    with SessionLocal() as db:
        cash = get_or_create_cash(db)
        state = get_or_create_state(db)
        snapshot = _load_snapshot(state)
        signal = _snapshot_signal(snapshot, symbol)
        position = db.query(DMPosition).filter(DMPosition.symbol == symbol).first()
        system_reason = None
        reference_date = None

        if side == "BUY":
            debit = price * shares + fees
            if debit > float(cash.cash_usd or 0) + 1e-9:
                raise HTTPException(status_code=400, detail="Insufficient cash; borrowing and negative cash are prohibited")
            if position is None:
                # Initial stop ATR must be from the session immediately preceding
                # the actual opening fill, not merely the month-end snapshot.
                source = LiveDataSource(price_workers=1)
                try:
                    prior_bars = [
                        bar for bar in source.price_bars(symbol, "2y")
                        if bar.date < effective_date
                    ]
                    atr_series = wilder_atr_series(prior_bars)
                    atr = next(
                        (float(value) for value in reversed(atr_series) if value is not None and float(value) > 0),
                        0.0,
                    )
                except Exception:
                    atr = 0.0
                finally:
                    source.close()
                if atr <= 0:
                    raise HTTPException(status_code=400, detail="Preceding-session ATR14 unavailable; cannot establish the required initial stop")
                position = DMPosition(
                    symbol=symbol,
                    shares=shares,
                    avg_cost=price,
                    peak=price,
                    stop=price - 3.0 * atr,
                    stop_asof=None,
                    opened_on=effective_date,
                    pending_stop_exit=False,
                    last_verified_fund_status=str((signal or {}).get("fundamental_status") or "UNKNOWN"),
                    last_verified_fund_at=(snapshot or {}).get("decision_date"),
                )
                db.add(position)
            else:
                old_shares = int(position.shares or 0)
                new_shares = old_shares + shares
                position.avg_cost = ((position.avg_cost or 0) * old_shares + price * shares) / new_shares
                position.shares = new_shares
                # Additions inherit the existing peak and stop; never reset stop history.
            cash.cash_usd = float(cash.cash_usd or 0) - debit
        else:
            if position is None or shares > int(position.shares or 0):
                raise HTTPException(status_code=400, detail="Sell quantity exceeds the recorded position")
            if position.pending_stop_exit:
                system_reason = "STOP_EXIT"
                reference_date = position.stop_asof
            elif position.pending_rule_exit_reason:
                system_reason = "RULE_EXIT"
                reference_date = position.pending_rule_exit_date
            credit = price * shares - fees
            cash.cash_usd = float(cash.cash_usd or 0) + credit
            position.shares = int(position.shares or 0) - shares
            if position.shares == 0:
                db.delete(position)
            else:
                position.updated_at = datetime.now(timezone.utc)

        db.add(
            DMTrade(
                symbol=symbol,
                side=side,
                shares=shares,
                price=price,
                fees=fees,
                reason=reason[:255],
                system_reason=system_reason,
                reference_date=reference_date,
                executed_on=effective_date,
            )
        )
        cash.updated_at = datetime.now(timezone.utc)
        db.commit()
    return RedirectResponse("/", status_code=303)


def _completed_daily_bars(bars):
    now_ny = datetime.now(ZoneInfo("America/New_York"))
    if now_ny.hour < 16 or (now_ny.hour == 16 and now_ny.minute < 15):
        today = now_ny.date().isoformat()
        return [bar for bar in bars if bar.date < today]
    return bars


@app.post("/api/stops/refresh")
def refresh_stops():
    source = LiveDataSource(price_workers=1)
    results = []
    try:
        try:
            current_members = {row["symbol"] for row in source.current_sp500()}
            change_rows = source.sp500_changes()
            removal_dates: dict[str, str] = {}
            for row in change_rows:
                removed = str(row.get("removed") or "")
                effective = row.get("effective_date")
                if removed and effective is not None and removed not in removal_dates:
                    removal_dates[removed] = effective.isoformat()
        except Exception:
            current_members = None
            removal_dates = {}

        with SessionLocal() as db:
            positions = db.query(DMPosition).order_by(DMPosition.symbol).all()
            today = datetime.now(timezone.utc).date().isoformat()
            for position in positions:
                if current_members is not None and position.symbol not in current_members:
                    if not position.pending_rule_exit_reason:
                        position.pending_rule_exit_reason = "S&P 500 membership has ended; sell next executable session"
                        position.pending_rule_exit_date = removal_dates.get(position.symbol) or today
                    results.append(
                        {
                            "symbol": position.symbol,
                            "status": "PENDING_RULE_EXIT",
                            "reason": position.pending_rule_exit_reason,
                            "reference_date": position.pending_rule_exit_date,
                        }
                    )
                    continue

                if position.pending_rule_exit_reason:
                    results.append(
                        {
                            "symbol": position.symbol,
                            "status": "PENDING_RULE_EXIT",
                            "reason": position.pending_rule_exit_reason,
                            "reference_date": position.pending_rule_exit_date,
                        }
                    )
                    continue

                if position.stop is None or position.peak is None or not position.opened_on:
                    results.append({"symbol": position.symbol, "status": "REVIEW", "reason": "Stop history is incomplete"})
                    continue
                if position.pending_stop_exit:
                    results.append({"symbol": position.symbol, "status": "PENDING_EXIT", "stop": position.stop})
                    continue

                try:
                    chart = source._chart_json(position.symbol, "2y")
                    split_by_date: dict[str, list[float]] = {}
                    for event in list(((chart.get("events") or {}).get("splits") or {}).values()):
                        try:
                            event_ts = float(event.get("date") or 0)
                            event_date = datetime.fromtimestamp(event_ts, tz=timezone.utc).date().isoformat()
                            numerator = float(event.get("numerator") or 0)
                            denominator = float(event.get("denominator") or 0)
                            ratio = numerator / denominator if numerator > 0 and denominator > 0 else 0.0
                        except Exception:
                            continue
                        if ratio <= 0 or event_date < position.opened_on:
                            continue
                        if position.stop_asof and event_date <= position.stop_asof:
                            continue
                        split_by_date.setdefault(event_date, []).append(ratio)

                    bars = _completed_daily_bars(source._bars_from_chart(chart))
                    atrs = wilder_atr_series(bars)
                    processed = 0
                    corporate_review = False

                    for i, bar in enumerate(bars):
                        if bar.date < position.opened_on:
                            continue
                        if position.stop_asof and bar.date <= position.stop_asof:
                            continue

                        for ratio in split_by_date.get(bar.date, []):
                            transformed_shares = int(position.shares or 0) * ratio
                            rounded = round(transformed_shares)
                            if abs(transformed_shares - rounded) > 1e-9:
                                position.pending_rule_exit_reason = (
                                    "Corporate action creates fractional shares/cash-in-lieu; reconcile before further stop replay"
                                )
                                position.pending_rule_exit_date = bar.date
                                results.append(
                                    {
                                        "symbol": position.symbol,
                                        "status": "CORPORATE_ACTION_REVIEW",
                                        "reason": position.pending_rule_exit_reason,
                                        "reference_date": bar.date,
                                    }
                                )
                                corporate_review = True
                                break
                            position.shares = int(rounded)
                            position.avg_cost = float(position.avg_cost or 0) / ratio
                            position.peak = float(position.peak) / ratio
                            position.stop = float(position.stop) / ratio

                        if corporate_review:
                            break

                        atr = atrs[i]
                        if atr is None or atr <= 0:
                            continue
                        next_state = advance_stop(
                            StopState(peak=float(position.peak), stop=float(position.stop), breached=False),
                            float(bar.close),
                            float(atr),
                        )
                        processed += 1
                        if next_state.breached:
                            position.pending_stop_exit = True
                            position.stop_asof = bar.date
                            results.append(
                                {
                                    "symbol": position.symbol,
                                    "status": "TRIGGERED",
                                    "trigger_close": bar.close,
                                    "stop": position.stop,
                                    "trigger_date": bar.date,
                                }
                            )
                            break
                        position.peak = next_state.peak
                        position.stop = next_state.stop
                        position.stop_asof = bar.date
                    else:
                        results.append(
                            {
                                "symbol": position.symbol,
                                "status": "UPDATED",
                                "peak": position.peak,
                                "stop": position.stop,
                                "through": position.stop_asof,
                                "sessions": processed,
                            }
                        )
                except Exception as exc:
                    results.append({"symbol": position.symbol, "status": "ERROR", "reason": f"{type(exc).__name__}: {exc}"})
            db.commit()
    finally:
        source.close()
    return {"results": results}

