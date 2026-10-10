"""Offline event replay of the five-stock trial with explicit global adapters.

No fetching, live database or broker. Actual performance execution is separately
gated by research.global_backtest_pipeline; fixtures may run this engine directly.
"""
from __future__ import annotations

import copy
from bisect import bisect_right
import json
import math
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from dual_momentum.rules import PriceBar
from research.spgm_sources import ROOT
from research.strategy_kernel import load_kernel


class InputUnavailable(ValueError):
    pass


def aware(value):
    if value.tzinfo is None:
        raise ValueError("Explicit UTC-aware timestamps required")
    return value


@dataclass(frozen=True)
class FXObservation:
    currency: str
    at: datetime
    available_at: datetime
    usd_per_unit: float
    source: str


class FXTape:
    def __init__(self, observations=()):
        self.rows = tuple(observations)
        for r in self.rows:
            aware(r.at); aware(r.available_at)
            if not r.source or not math.isfinite(r.usd_per_unit) or r.usd_per_unit <= 0:
                raise ValueError("Invalid FX observation")

    def at(self, currency, timestamp):
        aware(timestamp)
        if currency == "USD":
            return 1.0
        rows = [r for r in self.rows if r.currency == currency and r.at <= timestamp and r.available_at <= timestamp]
        if not rows:
            raise InputUnavailable("No observable FX: " + currency)
        latest = max(rows, key=lambda r: (r.at, r.available_at))
        if timestamp - latest.at > timedelta(days=5):
            raise InputUnavailable("FX observation stale beyond five calendar days")
        return latest.usd_per_unit


@dataclass(frozen=True)
class SessionBar:
    symbol: str  # Dated unique listing symbol; do not silently change tie-breaks.
    mic: str
    currency: str  # Major unit ISO currency; price_scale converts GBp etc.
    bar: PriceBar
    open_at: datetime
    close_at: datetime
    available_at: datetime
    source: str
    price_scale: float = 1.0


@dataclass(frozen=True)
class ShareAction:
    symbol: str
    effective_at: datetime
    available_at: datetime
    new_shares_per_old: float
    source: str


class HistoricalEngine:
    def __init__(self, records, calendars, reference_sessions, members_at,
                 decision_times, *, fx=None, actions=(), initial_capital=10_000.0,
                 signal_coverage=0.95):
        self.k = load_kernel()
        self.records = tuple(records)
        # Calendar entries are (local ISO session date, UTC open, UTC close).
        self.calendars = calendars
        self.calendar_closes = {mic:sorted((close,day) for day,_,close in sessions)
                                for mic,sessions in calendars.items()}
        self.calendar_close_times = {mic:[t for t,_ in rows] for mic,rows in self.calendar_closes.items()}
        self.calendar_indices = {mic:{day:i for i,(_,day) in enumerate(rows)} for mic,rows in self.calendar_closes.items()}
        self.reference = tuple(sorted(reference_sessions))  # (session date, decision timestamp)
        self.members_at = members_at
        self.decisions = set(decision_times)
        self.fx = fx or FXTape()
        self.actions = tuple(actions)
        if not 0.95 <= signal_coverage <= 1:
            raise ValueError("Cannot weaken universe data-coverage acceptance")
        self.minimum_coverage = signal_coverage
        self.initial_capital = float(initial_capital)
        self.spy_anchor = None
        self.history = {}
        self.last_record = {}
        self.history_gaps = set()
        self.audit = []
        self.valuations = []
        self.orders = []
        self.applied_actions = []
        self.state = dict(cash=float(initial_capital), holdings={}, pending=[], trades=[],
                          notes=[], equity=[], lockouts={}, last_signal=None, last_regime=None)
        self._validate()

    def _validate(self):
        seen, identities = set(), {}
        for r in self.records:
            for t in (r.open_at, r.close_at, r.available_at):
                aware(t)
            if not (r.open_at < r.close_at <= r.available_at) or not r.source:
                raise ValueError("Invalid session provenance/times")
            if not math.isfinite(r.price_scale) or r.price_scale <= 0:
                raise ValueError("Invalid quote-unit scale")
            values = (r.bar.open, r.bar.high, r.bar.low, r.bar.close, r.bar.total_return_close)
            if any(not math.isfinite(x) or x <= 0 for x in values):
                raise ValueError("Invalid OHLC/TR")
            if not r.bar.low <= min(r.bar.open, r.bar.close) <= max(r.bar.open, r.bar.close) <= r.bar.high:
                raise ValueError("OHLC inequalities fail")
            if (r.symbol, r.bar.date) in seen:
                raise ValueError("Duplicate security session")
            seen.add((r.symbol, r.bar.date))
            identity = (r.mic, r.currency, r.price_scale)
            if r.symbol in identities and identities[r.symbol] != identity:
                raise ValueError("Listing identity/units change needs a separate dated adapter")
            identities[r.symbol] = identity
            if (r.bar.date, r.open_at, r.close_at) not in self.calendars.get(r.mic, ()):
                raise ValueError("Bar is not an actual exchange session")
        self.identities = identities
        for action in self.actions:
            aware(action.effective_at); aware(action.available_at)
            if action.available_at > action.effective_at or not action.source or not math.isfinite(action.new_shares_per_old) or action.new_shares_per_old <= 0:
                raise ValueError("Action lacks prior-known ratio/evidence")
        for _, cutoff in self.reference:
            aware(cutoff)

    @staticmethod
    def native(r):
        b, f = r.bar, r.price_scale
        return replace(b, open=b.open*f, high=b.high*f, low=b.low*f, close=b.close*f)

    def _action(self, a):
        ratio = a.new_shares_per_old
        holding = self.state["holdings"].get(a.symbol)
        if holding:
            quantity = holding["shares"] * ratio
            if not math.isclose(quantity, round(quantity), abs_tol=1e-9):
                raise InputUnavailable("Fractional action entitlement needs verified cash-in-lieu")
            holding["shares"] = int(round(quantity))
            for field in ("cost", "peak", "stop"):
                holding[field] /= ratio
        for p in self.state["pending"]:
            for o in p["orders"]:
                if o["symbol"] == a.symbol:
                    q = o["shares"] * ratio
                    if not math.isclose(q, round(q), abs_tol=1e-9):
                        raise InputUnavailable("Fractional pending action quantity")
                    o["shares"] = int(round(q))
        self.history[a.symbol] = [replace(b, open=b.open/ratio, high=b.high/ratio,
                                          low=b.low/ratio, close=b.close/ratio)
                                  for b in self.history.get(a.symbol, [])]
        # TR is separately supplied in a coherent fixed index basis, already
        # accounting for actions. Never apply a second split to the TR series.
        self.applied_actions.append(dict(symbol=a.symbol, effective_at=a.effective_at.isoformat(),
                                         ratio=ratio, source=a.source))

    def _fill(self, order, r):
        b = self.native(r)
        conversion = self.fx.at(r.currency, r.open_at)
        shares = int(order["shares"])
        px = b.open * (1.0007 if order["side"] == "BUY" else .9993)
        if order["side"] == "SELL":
            h = self.state["holdings"].get(r.symbol)
            shares = min(shares, h["shares"] if h else 0)
            if not shares:
                return
            fee = max(1.0, .005*shares)
            self.state["cash"] += shares*px*conversion-fee
            h["shares"] -= shares
            if not h["shares"]:
                del self.state["holdings"][r.symbol]
        else:
            history=self.history.get(r.symbol,[])
            expected=[day for day,_,close in self.calendars[r.mic] if close<r.open_at]
            if expected and (not history or history[-1].date!=max(expected)):
                self.state['notes'].append(r.symbol+': incomplete previous session; opening order expired')
                return
            atr = self.k["_atr"](self.history.get(r.symbol, []))
            if atr is None:
                self.state["notes"].append(r.symbol+": missing previous-close ATR; order expired")
                return
            while shares > 0 and shares*px*conversion+max(1., .005*shares) > self.state["cash"]+1e-6:
                shares -= 1
            if not shares:
                self.state["notes"].append(r.symbol+": insufficient cash; order expired")
                return
            fee = max(1.0, .005*shares)
            self.state["cash"] -= shares*px*conversion+fee
            h = self.state["holdings"].get(r.symbol)
            if h:
                h["cost"] = (h["cost"]*h["shares"]+px*shares)/(h["shares"]+shares)
                h["shares"] += shares
            else:
                self.state["holdings"][r.symbol] = dict(shares=shares, cost=px, peak=px,
                    stop=max(.01, px-3.5*atr), opened=b.date)
        self.state["trades"].append(dict(date=b.date, symbol=r.symbol, side=order["side"], shares=shares,
            price=round(px, 5), fee=round(fee, 3), reason=order["reason"], kind="MODELED_NEXT_OPEN",
            price_usd=px*conversion, fx=conversion, currency=r.currency, at=r.open_at.isoformat()))

    def _completed(self, r):
        b = self.native(r)
        tr = r.bar.total_return_close * self.fx.at(r.currency, r.close_at)
        b = replace(b, total_return_close=tr)
        previous=self.history.get(r.symbol,[])
        if previous and self.calendar_indices[r.mic][b.date]!=self.calendar_indices[r.mic][previous[-1].date]+1:
            self.history_gaps.add(r.symbol)
        self.history.setdefault(r.symbol, []).append(b)
        self.last_record[r.symbol] = r
        h = self.state["holdings"].get(r.symbol)
        if not h:
            return
        if b.low <= h["stop"]:
            shares = h["shares"]
            px = min(b.open, h["stop"])*.9993
            # Daily OHLC supplies no intraday trigger time. Use pre-open
            # observable FX; proceeds become available only at bar publication.
            conversion = self.fx.at(r.currency, r.open_at)
            fee = max(1., .005*shares)
            self.state["cash"] += shares*px*conversion-fee
            self.state["trades"].append(dict(date=b.date, symbol=r.symbol, side="SELL", shares=shares,
                price=round(px, 5), fee=round(fee, 3), reason="3.5x Wilder ATR resting stop (modeled)",
                kind="MODELED_STOP", price_usd=px*conversion, fx=conversion, currency=r.currency,
                at=r.available_at.isoformat()))
            del self.state["holdings"][r.symbol]
            self.state["lockouts"][r.symbol] = r.available_at.astimezone(ZoneInfo("America/New_York")).date().isoformat()
        else:
            atr = self.k["_atr"](self.history[r.symbol]) if len(self.history[r.symbol]) >= 15 else None
            if atr:
                h["peak"] = max(h["peak"], b.close)
                h["stop"] = max(h["stop"], b.close-3.5*atr)

    def _signals(self, at, members):
        needed = {m["symbol"] for m in members} | set(self.k["ETFS"].values()) | {"SPY"} | set(self.state["holdings"])
        stats, marks = {}, {}
        for symbol in needed:
            if symbol in self.history_gaps:
                raise InputUnavailable(symbol+': missing intermediate actual trading session; no compressed lookback')
            r = self.last_record.get(symbol)
            if not r:
                continue
            index = bisect_right(self.calendar_close_times[r.mic], at)-1
            expected = self.calendar_closes[r.mic][index][1] if index >= 0 else None
            if expected and r.bar.date != expected:
                raise InputUnavailable(symbol+": missing latest completed exchange session")
            bars = self.history[symbol]
            info = self.k["_momentum"](bars)
            marks[symbol] = bars[-1].close*self.fx.at(r.currency, at)
            if info:
                # TR/EMAs/volatility already USD; ATR and stop coordinates local.
                info["close"] = marks[symbol]
                stats[symbol] = info
        universe = {m["symbol"] for m in members}
        stock_stats = {s: stats[s] for s in universe if s in stats}
        if len(stock_stats)/max(1, len(universe)) < self.minimum_coverage:
            raise InputUnavailable("Complete-universe signal coverage below95%")
        countries={}
        for m in members:
            countries.setdefault(m.get('country','Unknown'),[]).append(m['symbol'])
        for country,symbols in countries.items():
            if len(symbols)/max(1,len(universe))>=.01 and sum(s in stock_stats for s in symbols)/len(symbols)<.90:
                raise InputUnavailable(country+': material-country signal coverage below90%')
        if len(stock_stats) < 450:
            raise InputUnavailable("Original450-signal safeguard failed")
        if any(s not in stats for s in self.k["ETFS"].values()):
            raise InputUnavailable("Sector reference history incomplete")
        cap, regime = self.k["_sector_and_cap"](members, stock_stats, stats, self.history.get("SPY", []))
        return stock_stats, marks, cap, regime, stats["SPY"]["r63"]

    def _queue(self, desired, at, day, reason):
        if self.state["pending"]:
            return
        orders = []
        for symbol in sorted(set(desired) | set(self.state["holdings"])):
            current = self.state["holdings"].get(symbol, {}).get("shares", 0)
            target = desired.get(symbol, 0)
            if current == target:
                continue
            if symbol not in self.identities:
                raise InputUnavailable("Unresolved order listing: " + symbol)
            mic = self.identities[symbol][0]
            openings = [op for _, op, _ in self.calendars[mic] if op > at]
            if not openings:
                raise InputUnavailable("No future calendar opening for " + symbol)
            orders.append(dict(symbol=symbol, side="BUY" if target>current else "SELL",
                               shares=abs(target-current), reason=reason, scheduled_at=min(openings).isoformat()))
        if orders:
            self.state["pending"] = [dict(signal_date=day, signal_at=at.isoformat(), orders=orders)]
            self.orders.extend(copy.deepcopy(orders))

    def _reference_close(self, day, at):
        members = self.members_at(at)
        if any(m.get("sector") not in self.k["ETFS"] for m in members):
            raise InputUnavailable("Unresolved historical GICS; no Unknown bucket")
        if len({m["symbol"] for m in members}) != len(members):
            raise InputUnavailable("Duplicate/ambiguous listing symbols")
        stats, marks, cap, regime, spy_r63 = self._signals(at, members)
        if at in self.decisions and getattr(self,'classification_observer',None):
            self.classification_observer(day,at,members,stats,marks,cap,regime,spy_r63)
        nav = self.k["_positions_value"](self.state, marks)
        spy_close=self.history['SPY'][-1].total_return_close if self.history.get('SPY') else None
        if self.spy_anchor is None and spy_close:self.spy_anchor=spy_close
        benchmark=self.initial_capital*spy_close/self.spy_anchor if spy_close and self.spy_anchor else None
        exposure = {s: h["shares"]*marks[s] for s, h in self.state["holdings"].items()}
        self.state["equity"].append(dict(date=day, nav=round(nav,3), cash=round(self.state["cash"],3),
                                         holdings=len(exposure)))
        self.valuations.append(dict(date=day, at=at.isoformat(), nav=nav, cash=self.state["cash"],
                                    positions=exposure, shares={s:h["shares"] for s,h in self.state["holdings"].items()},
                                    sectors={m["symbol"]:m["sector"] for m in members},spy_nav=benchmark))
        if getattr(self,"end_at",None) == at:
            return  # Original trial terminal close freezes; no fresh order.
        if at in self.decisions:
            if self.state["pending"]:
                return
            quantities, weights, selected, ranks = self.k["_calculate_targets"](
                self.state, members, stats, cap, marks, sessions=[d for d,t in self.reference if t<=at], spy_r63=spy_r63)
            self._queue(quantities, at, day, "MONTH_END")
            self.state["last_signal"] = dict(asof=day, selected=selected, equity_cap=cap, weights=weights,
                                               raw_ranks={s:ranks.get(s) for s in selected})
            self.state["active_cap"] = cap
            self.audit.append(dict(day=day, at=at.isoformat(), regime=regime, selected=selected,
                                   weights=weights, targets=quantities, scores=stats, raw_ranks=ranks,
                                   ranking_audit=self.k["_ranking_audit"](self.state,members,stats,selected,ranks,
                                        spy_r63,sessions=[d for d,t in self.reference if t<=at],decision_date=day)))
        elif self.state["last_signal"] and not self.state["pending"]:
            # Exact trial daily budget formula; marks are explicitly USD.
            sectors = {m["symbol"]:m["sector"] for m in members}
            sector_values = {}
            for s, value in exposure.items():
                sec = sectors.get(s, "Unknown")
                sector_values[sec] = sector_values.get(sec,0)+value
            old_cap = self.state.get("active_cap", self.state["last_signal"]["equity_cap"])
            drift = sum(exposure.values())>nav*cap+nav*.005 or any(v>nav*.50+nav*.005 for v in sector_values.values())
            if abs(old_cap-cap)<1e-9 and not drift:
                return
            weights, totals = {}, {}
            for i,s in enumerate(self.state["last_signal"]["selected"]):
                if s not in sectors or s not in marks or (s in self.state["lockouts"] and s not in self.state["holdings"]):
                    continue
                w = .98*self.k["WEIGHTS"][i]*cap
                weights[s] = w
                totals[sectors[s]] = totals.get(sectors[s],0)+w
            for s in weights:
                if totals[sectors[s]] > .50:
                    weights[s] *= .50/totals[sectors[s]]
            desired = {s:max(0, math.floor(nav*w/marks[s])) for s,w in weights.items()}
            self._queue(desired, at, day, "EOD_SECTOR_OR_REGIME_RISK")
            self.state["active_cap"] = cap
        self.state["last_regime"] = regime

    def run(self, start_at, end_at):
        aware(start_at); aware(end_at)
        if start_at > end_at:
            raise ValueError("Invalid replay window")
        self.end_at = end_at
        events = {}
        # Missing quote records must still reach their scheduled actual opening,
        # expire there and never fill at a later observed price.
        for mic in {x[0] for x in self.identities.values()}:
            for _, op, _ in self.calendars[mic]:
                events.setdefault(op, {"open":[],"close":[],"action":[],"reference":[]})
        for r in self.records:
            events.setdefault(r.open_at, {"open":[],"close":[],"action":[],"reference":[]})["open"].append(r)
            events.setdefault(r.available_at, {"open":[],"close":[],"action":[],"reference":[]})["close"].append(r)
        for a in self.actions:
            events.setdefault(a.effective_at, {"open":[],"close":[],"action":[],"reference":[]})["action"].append(a)
        for day, at in self.reference:
            if start_at <= at <= end_at:
                events.setdefault(at, {"open":[],"close":[],"action":[],"reference":[]})["reference"].append(day)
        for at in sorted(t for t in events if t<=end_at):
            event = events[at]
            for a in event["action"]:
                self._action(a)
            opened = {r.symbol:r for r in event["open"]}
            if self.state["pending"]:
                p = self.state["pending"][0]
                remain = []
                for order in sorted(p["orders"], key=lambda o:(o["side"]!="SELL",o["symbol"])):
                    scheduled = datetime.fromisoformat(order["scheduled_at"])
                    if scheduled>at:
                        remain.append(order)
                    elif scheduled == at and order["symbol"] in opened:
                        if datetime.fromisoformat(p["signal_at"]) >= at:
                            raise ValueError("Non-forward fill")
                        self._fill(order, opened[order["symbol"]])
                    else:
                        self.state["notes"].append(order["symbol"]+": missed opening; order expired without later fill")
                p["orders"] = remain
                if not remain:
                    self.state["pending"] = []
            for r in event["close"]:
                self._completed(r)
            for day in event["reference"]:
                self._reference_close(day, at)
        return copy.deepcopy(self.state)

    def save(self, directory, *, data_kind):
        directory = Path(directory).resolve()
        if ROOT.resolve() not in directory.parents or data_kind not in {"SYNTHETIC_FIXTURE", "VALIDATED_HISTORICAL"}:
            raise ValueError("Ignored output and explicit evidence kind required")
        directory.mkdir(parents=True, exist_ok=True)
        for name, rows in (("daily_nav",self.valuations),("trades",self.state["trades"]),
                           ("decisions",self.audit),("orders",self.orders),("actions",self.applied_actions)):
            (directory/(name+".json")).write_text(json.dumps({"data_kind":data_kind,"rows":rows},indent=2)+"\n")
