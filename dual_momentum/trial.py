"""Isolated, forward-only one-month S&P 500 paper-trading trial.

This is NOT a broker. Signals are staged at completed closes; fills are
estimated only for orders recorded before the later session. Missing data
fail closed. The legacy dm_* account is never read or modified.
"""
from __future__ import annotations

import json
import math
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, SessionLocal, engine
from .data import LiveDataSource
from .rules import ema_seeded, wilder_atr_series

START = date(2026, 10, 9)
END = date(2026, 11, 9)
CAPITAL = 10_000.0
TRADING_COST_BPS = 7
SECTOR_CAP = 0.50
STOP_MULT = 3.5
WEIGHTS = (0.30, 0.25, 0.20, 0.15, 0.10)
ETFS = {
    "Information Technology": "XLK",
    "Communication Services": "XLC",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Energy": "XLE",
    "Financials": "XLF",
    "Health Care": "XLV",
    "Industrials": "XLI",
    "Materials": "XLB",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
}
RUN_LOCK = threading.Lock()
NY = ZoneInfo("America/New_York")


class DMTrialRow(Base):
    __tablename__ = "dm_trial_202610"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="NEW")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_poll: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def _initial():
    return dict(start=START.isoformat(), end=END.isoformat(), initial_capital=CAPITAL,
                cash=CAPITAL, holdings={}, pending=[], trades=[], equity=[],
                last_session=None, last_signal=None, last_regime=None,
                spy_start=None, notes=[], processed_sessions=[], halted=False)


def init_trial():
    Base.metadata.create_all(bind=engine, tables=[DMTrialRow.__table__])
    with SessionLocal() as db:
        if db.get(DMTrialRow, 1) is None:
            db.add(DMTrialRow(id=1, payload=json.dumps(_initial()), status="READY"))
            db.commit()


def read_trial():
    with SessionLocal() as db:
        row = db.get(DMTrialRow, 1)
        if row is None:
            return {"status": "NOT_INITIALIZED", "state": _initial()}
        return dict(status=row.status, error=row.error,
                    last_poll=row.last_poll.isoformat() if row.last_poll else None,
                    state=json.loads(row.payload))


def _write(payload, status="READY", error=None):
    with SessionLocal() as db:
        row = db.get(DMTrialRow, 1)
        if row is None:
            row = DMTrialRow(id=1, payload="{}")
            db.add(row)
        row.payload = json.dumps(payload, separators=(",", ":"), allow_nan=False)
        row.status = status
        row.error = error
        row.last_poll = datetime.now(timezone.utc)
        db.commit()


def _next_weekday(d):
    d += timedelta(days=1)
    while d.weekday() > 4:
        d += timedelta(days=1)
    return d


def _closed_bars(bars):
    now = datetime.now(NY)
    # Never accept a live, unfinished daily candle.
    return [bar for bar in bars if bar.date < now.date().isoformat() or
            (bar.date == now.date().isoformat() and
             (now.hour, now.minute) >= (16, 20))]


def _atr(bars):
    value = wilder_atr_series(bars)
    return float(value[-1]) if value and value[-1] is not None else None


def _momentum(bars):
    if len(bars) < 253:
        return None
    px = [float(b.total_return_close) for b in bars]
    ema = ema_seeded(px, 200)[-1]
    if ema is None or not all(px[-1-n] > 0 for n in (0, 63, 126, 252)):
        return None
    rets = [(px[-1] / px[-1-n] - 1) for n in (63, 126, 252)]
    atr = _atr(bars)
    if atr is None or atr <= 0:
        return None
    return dict(score=sum(rets)/3, r63=rets[0], above_ema=px[-1]>ema,
                close=float(bars[-1].close), atr=atr, last=bars[-1].date)


def _sector_and_cap(members, stats, etf_stats, spy_bars):
    spy = _momentum(spy_bars)
    if spy is None:
        raise RuntimeError("SPY EMA200/252-day data incomplete")
    spy_close = [b.total_return_close for b in spy_bars]
    ema_series = ema_seeded(spy_close, 200)
    spy_bear = (spy_close[-1] <= ema_series[-1] and
                spy_close[-2] <= ema_series[-2])
    grouped = {}
    for m in members:
        sector = str(m.get("sector") or "")
        if sector in ETFS:
            grouped.setdefault(sector, []).append(m["symbol"])
    bulls = []
    sector_evidence = []
    for sector, symbols in sorted(grouped.items()):
        e = etf_stats.get(ETFS[sector])
        checked = [stats[s] for s in symbols if s in stats]
        # Missing breadth is a veto, not evidence of healthy participation.
        coverage = len(checked)/len(symbols) if symbols else 0
        breadth = sum(bool(s["above_ema"]) for s in checked)/len(checked) if checked else 0
        bull = bool(e and e["above_ema"] and e["r63"] > spy["r63"] and
                    breadth >= .50 and coverage >= .90)
        if bull:
            bulls.append(sector)
        sector_evidence.append(dict(sector=sector, breadth=round(breadth,3),
                                    coverage=round(coverage,3), bull=bull))
    overall_breadth = sum(s["above_ema"] for s in stats.values())/len(stats) if stats else 0
    if not spy_bear:
        if len(bulls) >= 2:
            cap = 1.0
        elif len(bulls) == 1:
            cap = .90 if overall_breadth >= .70 else .70 if overall_breadth >= .50 else 0.0
        else:
            cap = 0.0
    elif len(bulls) >= 2:
        cap = 0.50
    elif len(bulls) == 1:
        cap = 0.50 if overall_breadth >= .60 else 0.40 if overall_breadth >= .50 else 0.0
    else:
        cap = 0.0
    return cap, dict(spy="BEAR" if spy_bear else "BULL",
                     bull_sectors=bulls, sectors=sector_evidence,
                     overall_breadth=round(overall_breadth,3))


def _positions_value(state, price_by_symbol):
    total = float(state["cash"])
    for symbol, holding in state["holdings"].items():
        px = price_by_symbol.get(symbol)
        if px is None:
            raise RuntimeError("Cannot mark %s: missing current price" % symbol)
        total += int(holding["shares"]) * px
    return total


def _calculate_targets(state, members, stats, regime_cap, price_by_symbol):
    sector_by_symbol = {m["symbol"]: str(m.get("sector") or "Unknown") for m in members}
    rankable = sorted(
        (s for s in stats if stats[s]["score"] > 0 and stats[s]["above_ema"]
         and s in sector_by_symbol),
        key=lambda s: (-stats[s]["score"], s))
    rank = {s: i+1 for i, s in enumerate(rankable)}
    retained = sorted((s for s in state["holdings"] if s in rank and rank[s] <= 15),
                      key=lambda s: rank[s])
    selected = retained[:5]
    for sym in rankable:
        if len(selected) >= 5:
            break
        if sym not in selected and rank[sym] <= 5 and sym not in state.get("lockouts", {}):
            selected.append(sym)
    nav = _positions_value(state, price_by_symbol)
    max_equity = max(0.0, min(1.0, float(regime_cap)))
    sector_remaining = {}
    weights = {}
    for i, s in enumerate(selected):
        sector = sector_by_symbol[s]
        # Equal scaling of the rank-weights is used when fewer than 5 qualify.
        proposed = (WEIGHTS[i] if i < 5 else 0.0) * max_equity
        room = SECTOR_CAP - sector_remaining.get(sector, 0.0)
        actual = max(0.0, min(proposed, room))
        weights[s] = actual
        sector_remaining[sector] = sector_remaining.get(sector, 0.0) + actual
    qty = {s: max(0, math.floor(nav*w/stats[s]["close"]))
           for s,w in weights.items()}
    return qty, weights, selected, rank


def _estimate_fee(shares, px):
    if shares <= 0:
        return 0.
    return max(1., 0.005*shares) + shares*px*(TRADING_COST_BPS/10000)


def _execute_pending(state, bars_by_symbol, on_date):
    pending = list(state.get("pending") or [])
    if not pending or on_date < pending[0]["fill_after"]:
        return
    # Do not silently pretend an order was submitted before its signal.
    if pending[0]["signal_date"] >= on_date:
        raise RuntimeError("Non-forward order detected")
    orders = sorted(pending[0]["orders"], key=lambda o: (o["side"] != "SELL", o["symbol"]))
    unfilled = []
    for order in orders:
        symbol = order["symbol"]
        bar = next((b for b in bars_by_symbol.get(symbol, []) if b.date == on_date), None)
        if bar is None or float(bar.open) <= 0:
            unfilled.append(order)
            continue
        px = float(bar.open)*(1+TRADING_COST_BPS/10000 if order["side"]=="BUY" else
                             1-TRADING_COST_BPS/10000)
        shares = int(order["shares"])
        if order["side"] == "SELL":
            owned = int((state["holdings"].get(symbol) or {}).get("shares", 0))
            shares = min(owned, shares)
            if shares <= 0:
                continue
            fee = max(1.0, .005*shares)
            state["cash"] += shares*px - fee
            holding = state["holdings"][symbol]
            holding["shares"] -= shares
            if holding["shares"] == 0:
                del state["holdings"][symbol]
        else:
            fee = max(1.0, .005*shares)
            while shares > 0 and shares*px + fee > state["cash"]+1e-6:
                shares -= 1
                fee = max(1.0, .005*shares) if shares else 0.0
            if shares <= 0:
                unfilled.append({**order, "status": "INSUFFICIENT_CASH"})
                continue
            state["cash"] -= shares*px + fee
            h = state["holdings"].get(symbol)
            if h:
                h["cost"] = (h["cost"]*h["shares"]+px*shares)/(h["shares"]+shares)
                h["shares"] += shares
            else:
                # Stop set from PREVIOUS close's ATR, never this session's ATR.
                prior = [b for b in bars_by_symbol.get(symbol, []) if b.date < on_date]
                atr = _atr(prior) if prior else None
                if atr is None:
                    state["cash"] += shares*px+fee
                    unfilled.append({**order, "status": "MISSING_PRE_FILL_ATR"})
                    continue
                state["holdings"][symbol] = dict(shares=shares, cost=px,
                                                  peak=px, stop=max(.01,px-STOP_MULT*atr),
                                                  opened=on_date)
        state["trades"].append(dict(date=on_date,symbol=symbol,side=order["side"],
                                    shares=shares,price=round(px,5),
                                    fee=round(fee,3),reason=order.get("reason",""),
                                    kind="MODELED_NEXT_OPEN"))
    state["pending"] = []
    if unfilled:
        state["notes"].append("%s: %s order(s) could not fill; NOT backdated" % (on_date,len(unfilled)))
        # Fail closed: do not execute missed orders at a later, unapproved price.


def _stop_check(state, bars_by_symbol, day):
    for symbol, holding in list(state["holdings"].items()):
        bar = next((b for b in bars_by_symbol.get(symbol, []) if b.date==day), None)
        if not bar:
            continue
        # Resting stop established strictly before today's session.
        if holding["opened"] < day and float(bar.low) <= float(holding["stop"]):
            shares = int(holding["shares"])
            trigger = min(float(bar.open), float(holding["stop"]))
            px = trigger*(1-TRADING_COST_BPS/10000)
            fee = max(1., .005*shares)
            state["cash"] += shares*px-fee
            state["trades"].append(dict(date=day,symbol=symbol,side="SELL",
                                        shares=shares,price=round(px,5),fee=round(fee,3),
                                        reason="3.5x Wilder ATR resting stop (modeled)",
                                        kind="MODELED_STOP"))
            del state["holdings"][symbol]
            state.setdefault("lockouts", {})[symbol] = day
            continue
        history = [b for b in bars_by_symbol.get(symbol,[]) if b.date<=day]
        atr = _atr(history) if len(history)>=15 else None
        if atr and holding["opened"]<=day:
            peak = max(float(holding["peak"]),float(bar.close))
            holding["peak"] = peak
            holding["stop"] = max(float(holding["stop"]),peak-STOP_MULT*atr)


def _stage(state, asof, desired, reason):
    existing = state.get("pending") or []
    if existing:
        return
    orders = []
    for symbol in sorted(set(desired)|set(state["holdings"])):
        current = int((state["holdings"].get(symbol) or {}).get("shares",0))
        target = int(desired.get(symbol,0))
        if target != current:
            orders.append(dict(symbol=symbol, side="BUY" if target>current else "SELL",
                               shares=abs(target-current),reason=reason))
    if orders:
        state["pending"] = [dict(signal_date=asof, fill_after=_next_weekday(date.fromisoformat(asof)).isoformat(),
                                 orders=orders)]


def _poll_impl():
    now = datetime.now(NY)
    asof_limit = now.date().isoformat() if (now.hour,now.minute)>=(16,20) else (
        now.date()-timedelta(days=1)).isoformat()
    if now.date() > END + timedelta(days=2):
        # Trial ends and freezes automatically. No fresh orders.
        return {"status":"ENDED","reason":"Trial period complete"}
    source = LiveDataSource(price_workers=12)
    try:
        members = source.current_sp500()
        if len(members) < 480:
            raise RuntimeError("S&P 500 membership feed incomplete")
        symbols = sorted({m["symbol"] for m in members} | set(ETFS.values()) | {"SPY"})
        prior = read_trial()["state"]
        symbols = sorted(set(symbols)|set(prior["holdings"])|
                         {o["symbol"] for p in prior.get("pending",[]) for o in p["orders"]})
        bars_by_symbol = {}
        errors = []
        def one(s):
            return s, _closed_bars(source.price_bars(s,"2y"))
        with ThreadPoolExecutor(max_workers=12) as pool:
            fs={pool.submit(one,s):s for s in symbols}
            for f in as_completed(fs):
                s=fs[f]
                try:
                    _, bars=f.result()
                    bars_by_symbol[s]=[b for b in bars if b.date<=asof_limit]
                except Exception as exc:
                    errors.append("%s:%s"%(s,type(exc).__name__))
        spy_bars=bars_by_symbol.get("SPY") or []
        if len(spy_bars)<254:
            raise RuntimeError("SPY history missing")
        completed=[b.date for b in spy_bars if START.isoformat()<=b.date<=END.isoformat()]
        state=prior
        last=state.get("last_session")
        if last and any(d<=last for d in completed):
            completed=[d for d in completed if d>last]
        # Set initial starting benchmark reference to previous-day adjusted SPY.
        if state.get("spy_start") is None:
            anchor=[b for b in spy_bars if b.date<START.isoformat()]
            if anchor:
                state["spy_start"]=float(anchor[-1].total_return_close)
        # Before first real session, stage the first orders from an ACTUAL
        # completed pre-start market close. Never backdate initial orders.
        if not state["equity"] and not state.get("pending"):
            ready=[b for b in spy_bars if b.date<START.isoformat()]
            if ready and ready[-1].date==asof_limit:
                _stage_decision(state,members,bars_by_symbol,ready[-1].date,"INITIAL")
        for day in completed:
            if state.get("pending"):
                _execute_pending(state,bars_by_symbol,day)
            _stop_check(state,bars_by_symbol,day)
            marks={}
            for symbol in state["holdings"]:
                rows=[b for b in bars_by_symbol.get(symbol,[]) if b.date<=day]
                if not rows or rows[-1].date!=day:
                    raise RuntimeError("%s: no price at %s, equity not advanced"%(symbol,day))
                marks[symbol]=float(rows[-1].close)
            nav=_positions_value(state,marks)
            spy_today=next((b.total_return_close for b in spy_bars if b.date==day),None)
            if spy_today is None:
                raise RuntimeError("Missing SPY benchmark")
            spy_value=CAPITAL*float(spy_today)/float(state["spy_start"] or spy_today)
            state["equity"].append(dict(date=day,nav=round(nav,3),cash=round(state["cash"],3),
                                        spy=round(spy_value,3),holdings=len(state["holdings"])))
            state["last_session"]=day
            # At EOD monthly decisions use today's data; fills no earlier than
            # the next available session, never at today's close.
            following=[d for d in completed if d>day]
            next_known=following[0] if following else None
            month_end=not next_known or day[:7]!=next_known[:7]
            if month_end and day<END.isoformat() and not state.get("pending"):
                _stage_decision(state,members,bars_by_symbol,day,"MONTH_END")
        # If no session advanced, no trades are invented.
        if not state["equity"] and not state.get("pending") and asof_limit>=START.isoformat():
            state["notes"].append("No timely pre-open signal existed; no retrospective opening fills")
        if len(state["notes"])>35:
            state["notes"]=state["notes"][-35:]
        state["data_quality"]=dict(members=len(members),symbols=len(bars_by_symbol),
                                   failures=len(errors),sample_failures=errors[:12],
                                   last_completed_spy=spy_bars[-1].date)
        _write(state,"READY")
        return {"status":"READY","last_session":state.get("last_session"),"trades":len(state["trades"])}
    finally:
        source.close()


def _stage_decision(state,members,bars_by_symbol,day,reason):
    # Everything is time-sliced at decision close. Never read future candles.
    cut={s:[b for b in bars if b.date<=day] for s,bars in bars_by_symbol.items()}
    stats={s:m for s,bars in cut.items() if (m:=_momentum(bars)) is not None}
    spy=cut.get("SPY",[])
    if len(spy)<254:
        raise RuntimeError("SPY signal incomplete")
    member_stats={m["symbol"]:stats[m["symbol"]] for m in members if m["symbol"] in stats}
    if len(member_stats)<450:
        raise RuntimeError("Only %s S&P 500 stock signals: refuse to stage"%len(member_stats))
    cap,regime=_sector_and_cap(members,member_stats,stats,spy)
    marks={s:float(bars[-1].close) for s,bars in cut.items() if bars}
    desired,weights,selected,ranks=_calculate_targets(state,members,member_stats,cap,marks)
    _stage(state,day,desired,reason)
    state["last_signal"]=dict(asof=day,reason=reason,selected=selected,
                              weights=weights,raw_ranks={s:ranks.get(s) for s in selected},
                              equity_cap=cap,sector_cap=SECTOR_CAP,targets=desired)
    state["last_regime"]=regime


def poll():
    if not RUN_LOCK.acquire(blocking=False):
        return {"status":"ALREADY_RUNNING"}
    try:
        saved=read_trial()
        _write(saved["state"],"RUNNING")
        try:
            return _poll_impl()
        except Exception as exc:
            with SessionLocal() as db:
                row=db.get(DMTrialRow,1)
                if row:
                    row.status="ERROR"
                    row.error="%s: %s"%(type(exc).__name__,exc)
                    row.last_poll=datetime.now(timezone.utc)
                    db.commit()
            return {"status":"ERROR","error":"%s: %s"%(type(exc).__name__,exc)}
    finally:
        RUN_LOCK.release()
