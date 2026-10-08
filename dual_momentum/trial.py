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
    """Backtest-compatible raw 3/6/12m momentum and risk-adjusted 50/30/20 score."""
    if len(bars) < 253:
        return None
    px = [float(b.total_return_close) for b in bars]
    # Pandas EWM(adjust=False, min_periods=N) seeds from the first observation.
    def ewm(period):
        alpha = 2.0/(period+1)
        value = px[0]
        for p in px[1:]:
            value = alpha*p+(1-alpha)*value
        return value
    e50 = ewm(50)
    e200 = ewm(200)
    if not all(px[-1-n] > 0 for n in (0, 63, 126, 252)):
        return None
    rets = [px[-1]/px[-1-n]-1.0 for n in (63, 126, 252)]
    daily = [px[i]/px[i-1]-1.0 for i in range(1,len(px))]
    def annual_vol(n):
        returns = daily[-n:]
        mean = sum(returns)/n
        var = sum((r-mean)**2 for r in returns)/(n-1)
        return math.sqrt(var*252)
    vols = [annual_vol(n) for n in (63,126,252)]
    if min(vols) <= 0:
        return None
    risk = sum(w*r/v for w,r,v in zip((.50,.30,.20),rets,vols))
    atr = _atr(bars)
    if atr is None or atr <= 0:
        return None
    return dict(score=sum(rets)/3, risk=risk, r63=rets[0],
                above_ema50=px[-1]>e50, above_ema=px[-1]>e200,
                close=float(bars[-1].close), atr=atr, last=bars[-1].date)


def _sector_and_cap(members, stats, etf_stats, spy_bars):
    spy = _momentum(spy_bars)
    if spy is None:
        raise RuntimeError("SPY EMA200/252-day data incomplete")
    previous_spy = _momentum(spy_bars[:-1])
    if previous_spy is None:
        raise RuntimeError("SPY preceding session signal unavailable")
    spy_bear = not spy["above_ema"] and not previous_spy["above_ema"]
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
    sole_breadth = next((row["breadth"] for row in sector_evidence if row["bull"]), 0.0)
    if not spy_bear:
        if len(bulls) >= 2:
            cap = 1.0
        elif len(bulls) == 1:
            cap = .90 if sole_breadth > .70 else .70 if sole_breadth >= .50 else 0.0
        else:
            cap = 0.0
    elif len(bulls) >= 2:
        cap = 0.50
    elif len(bulls) == 1:
        cap = 0.50 if sole_breadth >= .60 else 0.40 if sole_breadth >= .50 else 0.0
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


def _calculate_targets(state, members, stats, regime_cap, price_by_symbol,
                       sessions=None, spy_r63=-math.inf):
    """Protected raw Top-15 incumbents, risk-adjusted qualified challengers.

    Risk ranking: .50*R63/vol63 + .30*R126/vol126 + .20*R252/vol252
    Original five allocation weights use a 2% pre-capital cash reserve.
    Sector caps reduce each name in an overcrowded sector pro rata.
    """
    sector_by_symbol = {m["symbol"]: str(m.get("sector") or "Unknown") for m in members}
    raw = sorted(
        (s for s in stats if s in sector_by_symbol and math.isfinite(stats[s]["score"])),
        key=lambda s: (-stats[s]["score"], s))
    rank = {s: i+1 for i,s in enumerate(raw)}
    retained = [s for s in state["holdings"]
                if s in rank and rank[s] <= 15 and stats[s]["score"] > 0
                and stats[s]["above_ema"] and math.isfinite(stats[s]["risk"])]
    qualified = sorted(
        (s for s in stats if s in sector_by_symbol and
         math.isfinite(stats[s]["risk"]) and stats[s]["above_ema50"]
         and stats[s]["above_ema"] and stats[s]["r63"] > spy_r63),
        key=lambda s: (-stats[s]["risk"],s))
    blocked = set()
    signal_date = max((v["last"] for v in stats.values()), default="")
    for sym, stop_date in (state.get("lockouts") or {}).items():
        if sessions is None:
            cursor = date.fromisoformat(stop_date)
            end_day = date.fromisoformat(signal_date)
            seen = 0
            while cursor < end_day:
                cursor += timedelta(days=1)
                if cursor.weekday() < 5:
                    seen += 1
        else:
            seen = sum(stop_date < session <= signal_date for session in sessions)
        if seen < 5:
            blocked.add(sym)
    selected = retained[:5]
    for sym in qualified:
        if len(selected) >= 5:
            break
        if sym not in selected and sym not in blocked:
            selected.append(sym)
    selected.sort(key=lambda sym: (-stats[sym]["risk"],sym))
    nav = _positions_value(state, price_by_symbol)
    max_equity = max(0.0, min(1.0, float(regime_cap)))
    weights = {sym: .98*WEIGHTS[i]*max_equity for i,sym in enumerate(selected)}
    sector_sum = {}
    for sym,w in weights.items():
        sec=sector_by_symbol[sym]
        sector_sum[sec]=sector_sum.get(sec,0.0)+w
    for sym in weights:
        sec=sector_by_symbol[sym]
        if sector_sum[sec]>SECTOR_CAP:
            weights[sym] *= SECTOR_CAP/sector_sum[sec]
    qty = {sym:max(0, math.floor(nav*w/stats[sym]["close"]))
           for sym,w in weights.items()}
    return qty, weights, selected, rank


def _ranking_audit(state, members, stats, selected, raw_ranks,
                   spy_r63, sessions=None, decision_date=None,
                   historical_selection=False, limit=25):
    """Explain a FROZEN decision without influencing selection or orders.

    Mirrors the exact raw and risk-adjusted entry sorting and qualification
    predicates in _calculate_targets. Called after selecting, never as input.
    For a previously saved decision, source (new versus retained) is unknown.
    """
    symbols = {m["symbol"] for m in members}
    sectors = {m["symbol"]: str(m.get("sector") or "Unknown") for m in members}
    eligible = sorted(
        (sym for sym in symbols if sym in stats and
         math.isfinite(stats[sym]["risk"]) and
         stats[sym]["above_ema50"] and stats[sym]["above_ema"] and
         stats[sym]["r63"] > spy_r63),
        key=lambda sym: (-stats[sym]["risk"], sym))
    signal_date = decision_date or max((v["last"] for v in stats.values()), default="")
    blocked = set()
    for sym, stop_date in (state.get("lockouts") or {}).items():
        if sessions is None:
            cursor = date.fromisoformat(stop_date)
            count = 0
            while cursor < date.fromisoformat(signal_date):
                cursor += timedelta(days=1)
                if cursor.weekday() < 5:
                    count += 1
        else:
            count = sum(stop_date < session <= signal_date for session in sessions)
        if count < 5:
            blocked.add(sym)
    eligible = [sym for sym in eligible if sym not in blocked]
    entry_ranks = {sym: i + 1 for i, sym in enumerate(eligible)}
    raw_top = sorted(raw_ranks, key=lambda sym: (raw_ranks[sym], sym))[:20]
    coverage = (set(raw_top) |
                set(eligible[:limit]) |
                set(selected))
    selected_set = set(selected)
    rows = []
    for sym in coverage:
        info = stats.get(sym)
        if not info:
            continue
        is_selected = sym in selected_set
        reasons = []
        if not info["above_ema50"]:
            reasons.append("Below 50-day EMA")
        if not info["above_ema"]:
            reasons.append("Below 200-day EMA")
        if info["r63"] <= spy_r63:
            reasons.append("63-day return not above SPY")
        if sym in blocked:
            reasons.append("Five-session post-stop entry lockout")
        if is_selected:
            if historical_selection:
                status = "SELECTED"
                reason = "Selected in recorded decision; original entry/retention route not separately stored"
            elif sym in state["holdings"] and raw_ranks.get(sym,9999) <= 15 and info["score"] > 0 and info["above_ema"]:
                status = "RETAINED"
                reason = "Protected incumbent within raw Top 15"
            else:
                status = "NEW ENTRY"
                reason = "Next eligible risk-adjusted candidate after protecting incumbents"
            if reasons:
                reason += " (current entry screen: " + "; ".join(reasons) + ")"
        elif reasons:
            status = "NOT ELIGIBLE"
            reason = "; ".join(reasons)
        elif sym in entry_ranks:
            status = "NOT SELECTED"
            reason = "Five positions filled by qualified higher-priority candidates or retained Top-15 incumbents"
        else:
            status = "NO PRICE SIGNAL"
            reason = "Required signal data unavailable"
        rows.append({
            "symbol":sym, "sector":sectors.get(sym,"Unknown"),
            "raw_rank":raw_ranks.get(sym),
            "eligible_rank":entry_ranks.get(sym),
            "raw_score":round(info["score"], 6),
            "risk_adjusted_score":round(info["risk"], 6),
            "ema50_pass":bool(info["above_ema50"]),
            "ema200_pass":bool(info["above_ema"]),
            "spy_relative_pass":bool(info["r63"]>spy_r63),
            "selected":is_selected,
            "status":status,
            "reason":reason,
        })
    rows.sort(key=lambda row: (
        0 if row["selected"] else 1 if row["raw_rank"] is not None and row["raw_rank"] <= 5 else 2,
        row["eligible_rank"] if row["eligible_rank"] is not None else 9999,
        row["raw_rank"] if row["raw_rank"] is not None else 9999,
        row["symbol"]))
    return {
        "asof": signal_date,
        "basis": "Recorded historical decision" if historical_selection else "Current completed-close decision",
        "raw_rank_method": "Equal average 63/126/252-session total returns",
        "entry_rank_method": "0.50×R63/vol63 + 0.30×R126/vol126 + 0.20×R252/vol252",
        "qualification": "Above EMA50 and EMA200; R63 greater than SPY R63; five-session lockout",
        "raw_top5": [sym for sym in raw_top[:5]],
        "eligible_top5": eligible[:5],
        "selected":list(selected),
        "universe_with_valid_signals": len(symbols.intersection(stats)),
        "qualified_and_not_locked": len(eligible),
        "rows": rows,
    }


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
        if holding["opened"] <= day and float(bar.low) <= float(holding["stop"]):
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
            holding["stop"] = max(float(holding["stop"]),float(bar.close)-STOP_MULT*atr)


def _daily_risk_check(state, members, bars_by_symbol, day):
    """Keep the month-end shortlist, but correct daily risk-budget breaches.

    Uses only bars available at today's completed close, with executable
    orders queued no earlier than the NEXT open. No forced cross-sector buys.
    """
    if not state.get("last_signal") or state.get("pending"):
        return
    cut={s:[b for b in bars if b.date<=day] for s,bars in bars_by_symbol.items()}
    stats={s:m for s,bars in cut.items() if (m:=_momentum(bars)) is not None}
    members_valid={m["symbol"]:stats[m["symbol"]] for m in members if m["symbol"] in stats}
    if len(members_valid)<450:
        state["notes"].append(day+": incomplete breadth, daily risk check blocked")
        return
    spy=cut.get("SPY",[])
    cap, regime = _sector_and_cap(members,members_valid,stats,spy)
    marks={s:float(bs[-1].close) for s,bs in cut.items() if bs}
    nav=_positions_value(state,marks)
    sector_lookup={m["symbol"]:str(m.get("sector") or "Unknown") for m in members}
    market_by_sector={}
    invested=0.0
    for sym,h in state["holdings"].items():
        value=int(h["shares"])*marks[sym]
        invested+=value
        sector=sector_lookup.get(sym,"Unknown")
        market_by_sector[sector]=market_by_sector.get(sector,0.0)+value
    # A change in the SPY/sector allowance is actionable; drift is only
    # corrected at next opening, not retroactively at the decision close.
    old_cap=float(state.get("active_cap",state["last_signal"]["equity_cap"]))
    drift=invested>nav*cap+nav*.005 or any(x>nav*SECTOR_CAP+nav*.005 for x in market_by_sector.values())
    if abs(old_cap-cap)<1e-9 and not drift:
        return
    sel=list(state["last_signal"].get("selected") or [])
    sector_sum={}
    weights={}
    for i,sym in enumerate(sel):
        if sym not in sector_lookup or sym not in marks:
            continue
        # Do not reinstate a position that is still serving a stop lockout.
        if sym in state.get("lockouts",{}) and sym not in state["holdings"]:
            continue
        w=.98*WEIGHTS[i]*cap
        weights[sym]=w
        sector=sector_lookup[sym]
        sector_sum[sector]=sector_sum.get(sector,0.0)+w
    for sym in weights:
        sector=sector_lookup[sym]
        if sector_sum[sector]>SECTOR_CAP:
            weights[sym]*=SECTOR_CAP/sector_sum[sector]
    desired={sym:max(0,math.floor(nav*w/marks[sym])) for sym,w in weights.items()}
    _stage(state,day,desired,"EOD_SECTOR_OR_REGIME_RISK")
    state["active_cap"]=cap
    state["last_regime"]=regime
    state["notes"].append(day+": cap "+str(old_cap)+" -> "+str(cap)+
                          "; sector concentration review; next-open rebalance")


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
        prior = read_trial()["state"]
        # One SPY query first: don't download ~500 stocks repeatedly while the
        # most recent completed close is unavailable or its adjclose is missing.
        spy_probe = [b for b in _closed_bars(source.price_bars("SPY","2y"))
                     if b.date <= asof_limit]
        if (not prior.get("last_signal") and not prior.get("trades") and
                not prior.get("equity") and
                now.date() <= START and
                (not spy_probe or spy_probe[-1].date < (START-timedelta(days=1)).isoformat())):
            prior["data_quality"] = dict(members=None, symbols=1, failures=0,
                    last_completed_spy=spy_probe[-1].date if spy_probe else None)
            prior["notes"] = [n for n in prior["notes"] if not n.startswith("Waiting for")]
            prior["notes"].append("Waiting for October 8 SPY adjusted close; no forward opening signal can be staged yet")
            _write(prior,"WAITING_FOR_CLOSE")
            return {"status":"WAITING_FOR_CLOSE","reason":"Oct 8 SPY EOD not yet available"}
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
            ready=[b for b in spy_bars if b.date== (START-timedelta(days=1)).isoformat()]
            # A previous-close signal may target today's opening ONLY if
            # its order is staged BEFORE the 09:30 New York market open.
            initial_window = (now.date() < START or
                              (now.date() == START and (now.hour, now.minute) < (9, 30)))
            if ready and ready[-1].date==asof_limit and initial_window:
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
            month_end=_next_weekday(date.fromisoformat(day)).month != date.fromisoformat(day).month
            if month_end and day<END.isoformat() and not state.get("pending"):
                _stage_decision(state,members,bars_by_symbol,day,"MONTH_END")
            elif day<END.isoformat() and not state.get("pending"):
                _daily_risk_check(state,members,bars_by_symbol,day)
        # If no session advanced, no trades are invented.
        if not state.get("pending") and not state["holdings"] and not state["trades"] and START.isoformat() <= asof_limit < END.isoformat():
            # Missed launch: propose at the latest completed close for NEXT open only.
            latest_spy=spy_bars[-1].date
            if latest_spy==asof_limit:
                _stage_decision(state,members,bars_by_symbol,latest_spy,"LATE_START")
                state["notes"].append("Trial began later than October 9; no retrospective fills")
        # Fill diagnostics on an existing saved signal without changing its
        # selections, exposure, orders, fills or cash. Audit uses that date's
        # bars, not any future price information.
        signal = state.get("last_signal") or {}
        if signal.get("asof") and not signal.get("ranking_audit"):
            asof = signal["asof"]
            cut = {sym:[b for b in bars if b.date<=asof]
                   for sym,bars in bars_by_symbol.items()}
            evidence = {sym:momentum for sym,bs in cut.items()
                        if (momentum := _momentum(bs)) is not None}
            members_stats = {m["symbol"]:evidence[m["symbol"]]
                             for m in members if m["symbol"] in evidence}
            spy_at_signal = evidence.get("SPY")
            if spy_at_signal and len(members_stats)>=450:
                raw_symbols = sorted(members_stats,
                                     key=lambda sym:(-members_stats[sym]["score"],sym))
                raw_ranks = {sym:i+1 for i,sym in enumerate(raw_symbols)}
                signal["ranking_audit"] = _ranking_audit(
                    state,members,members_stats,signal.get("selected") or [],
                    raw_ranks,spy_at_signal["r63"],
                    sessions=[bar.date for bar in cut["SPY"]],
                    decision_date=asof,historical_selection=True)
                sectors={m["symbol"]:str(m.get("sector") or "Unknown") for m in members}
                signal["sector_by_symbol"] = {
                    sym:sectors.get(sym,"Unknown") for sym in signal.get("selected") or []}
        if len(state["notes"])>35:
            state["notes"]=state["notes"][-35:]
        state["data_quality"]=dict(members=len(members),symbols=len(bars_by_symbol),
                                   failures=len(errors),sample_failures=errors[:12],
                                   last_completed_spy=spy_bars[-1].date)
        ready = bool(state.get("last_signal") or state.get("trades") or state.get("equity"))
        status = "READY" if ready else "WAITING_FOR_CLOSE"
        if not ready:
            state["notes"] = [n for n in state["notes"] if not n.startswith("Waiting for")]
            state["notes"].append("Waiting for a completed and fully adjusted pre-start SPY market bar before staging a forward paper order; no historical fill will be invented")
        _write(state,status)
        return {"status":status,"last_session":state.get("last_session"),"trades":len(state["trades"])}
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
    desired,weights,selected,ranks=_calculate_targets(state,members,member_stats,cap,marks,
                                                        sessions=[b.date for b in spy],
                                                        spy_r63=stats["SPY"]["r63"])
    _stage(state,day,desired,reason)
    ranking_audit = _ranking_audit(
        state, members, member_stats, selected, ranks,
        stats["SPY"]["r63"], sessions=[b.date for b in spy],
        decision_date=day)
    sector_by_symbol={m["symbol"]:str(m.get("sector") or "Unknown") for m in members}
    state["last_signal"]=dict(asof=day,reason=reason,selected=selected,
                              weights=weights,raw_ranks={s:ranks.get(s) for s in selected},
                              sector_by_symbol={sym:sector_by_symbol.get(sym,"Unknown")
                                                for sym in selected},
                              equity_cap=cap,sector_cap=SECTOR_CAP,targets=desired,
                              ranking_audit=ranking_audit)
    state["last_regime"]=regime
    state["active_cap"]=cap


def refresh_ranking_only():
    """Build an independent decision-date audit, with ZERO paper trades.

    This diagnostic intentionally works even while trading is disabled for
    non-durable storage. A manual request never changes cash, holdings,
    pending orders or simulated fills.
    """
    if not RUN_LOCK.acquire(blocking=False):
        return {"status": "BUSY"}
    source = LiveDataSource(price_workers=12)
    try:
        original = read_trial()
        signal = original["state"].get("last_signal") or {}
        spy_bars = _closed_bars(source.price_bars("SPY", "2y"))
        if len(spy_bars) < 254:
            raise RuntimeError("Cannot verify SPY signal: insufficient completed daily bars")
        asof = signal.get("asof") or spy_bars[-1].date
        if asof > spy_bars[-1].date:
            raise RuntimeError("Recorded signal date is later than most recent completed SPY bar")
        members = source.current_sp500()
        if len(members) < 480:
            raise RuntimeError("Current S&P 500 membership feed incomplete")
        fetch_symbols = sorted({m["symbol"] for m in members} | {"SPY"})
        data = {}
        def fetch(symbol):
            bars = _closed_bars(source.price_bars(symbol, "2y"))
            return symbol, [b for b in bars if b.date <= asof]
        with ThreadPoolExecutor(max_workers=12) as pool:
            futures = {pool.submit(fetch,sym):sym for sym in fetch_symbols}
            for future in as_completed(futures):
                sym = futures[future]
                try:
                    _, bars = future.result()
                    if bars and bars[-1].date == asof:
                        data[sym] = bars
                except Exception:
                    continue
        stats = {sym:info for sym,bars in data.items()
                 if (info := _momentum(bars)) is not None}
        member_stats = {m["symbol"]:stats[m["symbol"]]
                        for m in members if m["symbol"] in stats}
        if len(member_stats) < 450 or "SPY" not in stats:
            raise RuntimeError("Candidate coverage insufficient for audited ranks")
        ranked = sorted(member_stats, key=lambda sym:(-member_stats[sym]["score"],sym))
        raw_ranks = {sym:i+1 for i,sym in enumerate(ranked)}
        selected = list(signal.get("selected") or [])
        diagnostic = _ranking_audit(
            original["state"],members,member_stats,selected,raw_ranks,
            stats["SPY"]["r63"], sessions=[b.date for b in data["SPY"]],
            decision_date=asof,historical_selection=True)
        if not signal:
            diagnostic["basis"] = "Read-only candidate preview; NOT an executed strategy decision"
            for row in diagnostic["rows"]:
                if row["status"] == "NOT SELECTED":
                    row["status"] = "ELIGIBLE"
                    row["reason"] = "Qualified candidate (read-only preview; no paper order)"
        # Merge into the LATEST ledger row, not into the snapshot read before
        # the market-data requests. Do not overwrite funds or orders.
        with SessionLocal() as db:
            row = db.get(DMTrialRow,1)
            if row is None:
                raise RuntimeError("Paper ledger is unavailable")
            current = json.loads(row.payload)
            current_signal = current.get("last_signal") or {}
            if (current_signal.get("asof"),current_signal.get("selected")) != (
                    signal.get("asof"),signal.get("selected")):
                raise RuntimeError("Signal changed during audit; refresh ranking again")
            if current_signal:
                current_signal["ranking_audit"] = diagnostic
                # Sector metadata is informational. Never change recorded
                # positions, share targets or the signal selection.
                sectors={m["symbol"]:str(m.get("sector") or "Unknown")
                         for m in members}
                current_signal["sector_by_symbol"]={
                    sym:sectors.get(sym,"Unknown")
                    for sym in current_signal.get("selected") or []}
            else:
                current["read_only_ranking_preview"] = diagnostic
            current.pop("ranking_audit_error",None)
            row.payload = json.dumps(current,separators=(",",":"),allow_nan=False)
            db.commit()
        return {"status":"AUDIT_READY","asof":asof,
                "qualified":diagnostic["qualified_and_not_locked"],
                "stocks":diagnostic["universe_with_valid_signals"]}
    except Exception as exc:
        # Diagnostic failures must not alter trading status.
        error = "%s: %s" % (type(exc).__name__,exc)
        with SessionLocal() as db:
            row=db.get(DMTrialRow,1)
            if row is not None:
                current=json.loads(row.payload)
                current["ranking_audit_error"]=error
                row.payload=json.dumps(current,separators=(",",":"))
                db.commit()
        return {"status":"AUDIT_ERROR","error":error}
    finally:
        source.close()
        RUN_LOCK.release()


def poll():
    if not RUN_LOCK.acquire(blocking=False):
        return {"status":"ALREADY_RUNNING"}
    try:
        saved=read_trial()
        if engine.url.get_backend_name() == "sqlite":
            warning = ("Paper execution disabled: Render's SQLite storage is ephemeral. "
                       "Connect the existing Render Postgres database by setting DATABASE_URL "
                       "on the dual-momentum-radar service before Friday's market opening.")
            state = saved["state"]
            state["pending"] = []  # Never carry ephemeral opening orders forward.
            state["notes"] = [x for x in state["notes"] if not x.startswith("Paper execution disabled:")]
            state["notes"].append(warning)
            _write(state,"STORAGE_BLOCKED",warning)
            return {"status":"STORAGE_BLOCKED","reason":warning}
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
