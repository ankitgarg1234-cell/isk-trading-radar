#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import statistics
import sys
import time
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import dual_momentum_backtest_5y as dm
from dual_momentum.rules import FundamentalStatus, StopState, advance_stop, ema_seeded, estimated_commission

START = dm.START
END = dm.END
PRICE_START = dm.PRICE_START
SPY_START = dm.SPY_START
STARTING_CASH = dm.STARTING_CASH
MARKET_DRAG = dm.MARKET_DRAG
MAX_HOLDINGS = dm.MAX_HOLDINGS
ENTRY_CUTOFF = dm.ENTRY_CUTOFF
RETENTION_CUTOFF = dm.RETENTION_CUTOFF
GM_EXEMPT = dm.GM_EXEMPT

EXPECTED_BASELINE_END = 12866.327757423398

AUDIT_LEADERS = {
    "MSFT": {"contribution_rank": 1, "sp500_contribution_pct": 3.49},
    "AAPL": {"contribution_rank": 2, "sp500_contribution_pct": 3.24},
    "NVDA": {"contribution_rank": 3, "sp500_contribution_pct": 2.90},
    "AMZN": {"contribution_rank": 4, "sp500_contribution_pct": 2.02},
    "META": {"contribution_rank": 5, "sp500_contribution_pct": 1.71},
    "TSLA": {"contribution_rank": 6, "sp500_contribution_pct": 1.09},
    "GOOGL": {"contribution_rank": 7, "sp500_contribution_pct": 0.99},
    "GOOG": {"contribution_rank": 8, "sp500_contribution_pct": 0.88},
    "AVGO": {"contribution_rank": 9, "sp500_contribution_pct": 0.75},
    "LLY": {"contribution_rank": 10, "sp500_contribution_pct": 0.53},
}


@dataclass(frozen=True)
class Variant:
    key: str
    label: str
    disable_atr_stops: bool = True
    exposure_mode: str = "sqrt"
    no_monthly_trim: bool = False
    disable_rank_exit: bool = False
    fundamentals_entry_only: bool = False


VARIANTS = [
    Variant("research_base", "No ATR stop + sqrt(N/20)"),
]


@dataclass
class Position:
    symbol: str
    shares: int
    avg_cost: float
    peak: float
    stop: float
    opened: object
    last_verified: str = "UNKNOWN"


@dataclass
class Order:
    symbol: str
    side: str
    shares: int
    reason: str
    rank: int
    kind: str
    created: object
    earliest: object


class Limiter:
    def __init__(self, rps: float):
        self.dt = 1.0 / rps
        self.lock = threading.Lock()
        self.next = 0.0

    def wait(self):
        with self.lock:
            now = time.monotonic()
            if now < self.next:
                time.sleep(self.next - now)
            self.next = time.monotonic() + self.dt


def main():
    print("AUD23_STAGE membership", flush=True)
    intervals, membership_source = dm.load_membership()
    overlapping = [x for x in intervals if x.overlaps(START, END)]
    symbols = sorted({x.symbol for x in overlapping})
    by_symbol_intervals = defaultdict(list)
    for x in intervals:
        by_symbol_intervals[x.symbol].append(x)
    for s in by_symbol_intervals:
        by_symbol_intervals[s].sort(key=lambda x: x.added)

    staged = dm.load_staged_prices()
    charts = {}
    price_failed = {}
    alias_recoveries = {}

    cik_symbols = defaultdict(set)
    for x in intervals:
        if x.cik:
            cik_symbols[x.cik].add(x.symbol)
    aliases_by_symbol = {}
    for sym in symbols:
        ciks = {x.cik for x in by_symbol_intervals.get(sym, []) if x.cik}
        aliases = set()
        for cik in ciks:
            aliases.update(cik_symbols.get(cik) or set())
        aliases.discard(sym)
        aliases_by_symbol[sym] = sorted(aliases)

    def chart_overlaps_symbol(ch, sym):
        relevant = [x for x in by_symbol_intervals.get(sym, []) if x.overlaps(START, END)]
        if not relevant or not ch.rows:
            return False
        for x in relevant:
            lo = max(START, x.added)
            hi = min(END, (x.removed - timedelta(days=1)) if x.removed else END)
            if any(lo <= r["date"] <= hi for r in ch.rows):
                return True
        return False

    def rekey_chart(ch, sym, alias):
        return dm.Chart(sym, ch.rows, ch.splits, ch.dividends, ch.source + ":same-cik-alias:" + alias)

    def price_task(sym):
        primary_error = None
        try:
            return sym, dm.fetch_chart(sym, PRICE_START, END + timedelta(days=3), staged=staged), None, None
        except Exception as exc:
            primary_error = f"{type(exc).__name__}: {exc}"
        for alias in aliases_by_symbol.get(sym) or []:
            try:
                ach = dm.fetch_chart(alias, PRICE_START, END + timedelta(days=3), staged=staged)
                if chart_overlaps_symbol(ach, sym):
                    return sym, rekey_chart(ach, sym, alias), None, alias
            except Exception:
                pass
        return sym, None, primary_error, None

    print(f"AUD23_STAGE prices symbols={len(symbols)}", flush=True)
    with ThreadPoolExecutor(max_workers=6) as pool:
        futs = [pool.submit(price_task, s) for s in symbols]
        for n, fut in enumerate(as_completed(futs), 1):
            sym, ch, err, alias = fut.result()
            if ch:
                charts[sym] = ch
                if alias:
                    alias_recoveries[sym] = alias
            else:
                price_failed[sym] = err
            if n % 100 == 0 or n == len(futs):
                print(f"AUD23_PRICE {n}/{len(futs)} ok={len(charts)} fail={len(price_failed)} aliases={len(alias_recoveries)}", flush=True)

    spy = dm.fetch_chart("SPY", SPY_START, END + timedelta(days=3), staged=None)
    try:
        bench = dm.fetch_chart("^SP500TR", START - timedelta(days=10), END + timedelta(days=3), staged=None)
        benchmark_name = "S&P 500 Total Return (^SP500TR)"
    except Exception:
        bench = spy
        benchmark_name = "SPY adjusted close fallback"

    spy_dates = [r["date"] for r in spy.rows]
    spy_test_dates = [d for d in spy_dates if START <= d <= END]
    spy_idx = {r["date"]: i for i, r in enumerate(spy.rows)}
    ema = ema_seeded([r["adjclose"] for r in spy.rows], 200)

    month_ends = []
    for d in spy_test_dates:
        i = spy_idx[d]
        if i + 1 < len(spy.rows):
            nd = spy.rows[i + 1]["date"]
            if (nd.year, nd.month) != (d.year, d.month):
                month_ends.append(d)
    if END in spy_idx:
        month_ends.append(END)
    month_ends = sorted(set(month_ends))
    next_spy = {}
    for d in month_ends:
        i = spy_idx[d]
        next_spy[d] = spy.rows[i + 1]["date"] if i + 1 < len(spy.rows) else None

    def active_intervals(d):
        chosen = {}
        for x in intervals:
            if x.active(d):
                prior = chosen.get(x.symbol)
                if prior is None or x.added > prior.added:
                    chosen[x.symbol] = x
        return chosen

    snapshots = {}
    top35_union = set()
    member_month_total = 0
    member_month_signal = 0
    for d in month_ends:
        active = active_intervals(d)
        sigs = []
        for sym, mem in active.items():
            ch = charts.get(sym)
            if not ch:
                continue
            z = dm.signal(ch, d, f"{mem.cik or sym}:{sym}")
            if z:
                sigs.append(z)
        member_month_total += len(active)
        member_month_signal += len(sigs)
        sigs.sort(key=lambda z: (-z["score"], -z["adv63"], z["security_id"]))
        positive = [z for z in sigs if z["score"] > 0]
        ranks = {z["symbol"]: i + 1 for i, z in enumerate(positive)}
        smap = {z["symbol"]: z for z in sigs}
        i_spy = spy_idx[d]
        reg = "BULL" if ema[i_spy] is not None and spy.rows[i_spy]["adjclose"] > ema[i_spy] else "BEAR"
        top35 = positive[:35]
        top35_union.update(z["symbol"] for z in top35)
        snapshots[d] = {
            "regime": reg,
            "active": active,
            "signals": smap,
            "ranks": ranks,
            "top35": [z["symbol"] for z in top35],
        }

    valuein = dm.load_valuein()
    needs_sec = set()
    for d, snap in snapshots.items():
        if snap["regime"] != "BULL":
            continue
        for sym in snap["top35"]:
            mem = snap["active"].get(sym)
            exempt = bool(mem and mem.sector in GM_EXEMPT)
            ck = dm.fund_from_valuein(valuein, sym, d, exempt)
            if ck.status == FundamentalStatus.REVIEW:
                needs_sec.add(sym)

    for d in month_ends:
        if d.year != 2023:
            continue
        snap = snapshots[d]
        for sym in AUDIT_LEADERS:
            mem = snap["active"].get(sym)
            if not mem:
                continue
            ck = dm.fund_from_valuein(valuein, sym, d, mem.sector in GM_EXEMPT)
            if ck.status == FundamentalStatus.REVIEW:
                needs_sec.add(sym)

    cik_by_symbol = {}
    for sym in (set(top35_union) | set(AUDIT_LEADERS)):
        rows = by_symbol_intervals.get(sym) or []
        cik = next((x.cik for x in reversed(rows) if x.cik), "")
        if cik:
            cik_by_symbol[sym] = cik

    secfacts = {}
    sec_failed = {}
    limiter = Limiter(6.0)

    def sec_task(sym):
        cik = cik_by_symbol.get(sym)
        if not cik:
            return sym, None, "CIK missing"
        try:
            limiter.wait()
            return sym, dm.request_json(dm.SEC_COMPANYFACTS.format(cik), attempts=4, headers={"User-Agent": dm.UA}), None
        except Exception as exc:
            return sym, None, f"{type(exc).__name__}: {exc}"

    print(f"AUD23_STAGE fundamentals top35_union={len(top35_union)} sec={len(needs_sec)}", flush=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = [pool.submit(sec_task, s) for s in sorted(needs_sec)]
        for n, fut in enumerate(as_completed(futs), 1):
            sym, fact, err = fut.result()
            if fact:
                secfacts[sym] = fact
            else:
                sec_failed[sym] = err
            if n % 50 == 0 or n == len(futs):
                print(f"AUD23_SEC {n}/{len(futs)} ok={len(secfacts)} fail={len(sec_failed)}", flush=True)

    fund_cache = {}

    def fund_check(sym, d, sector):
        key = (sym, d)
        if key in fund_cache:
            return fund_cache[key]
        exempt = sector in GM_EXEMPT
        ck = dm.fund_from_valuein(valuein, sym, d, exempt)
        source = "valuein"
        if ck.status == FundamentalStatus.REVIEW and sym in secfacts:
            ck = dm.fund_from_sec(secfacts[sym], d, exempt)
            source = "sec"
        out = {
            "status": ck.status.value,
            "revenue_growth": ck.revenue_growth_ttm,
            "gross_margin": ck.gross_margin_ttm,
            "reason": ck.reason,
            "source": source,
        }
        fund_cache[key] = out
        return out

    calendar = [d for d in spy_test_dates if START <= d <= END]
    month_set = set(month_ends)

    def run_variant(v: Variant):
        positions = {}
        cash = STARTING_CASH
        orders = []
        trades = []
        curve = []
        total_costs = 0.0
        traded_notional = 0.0
        unresolved_orders = []
        split_fraction_events = []
        audit_rows = []
        last_prices = {}
        processed_removals = set()
        removal_events = sorted(
            (x.removed, x.symbol)
            for x in intervals
            if x.removed and START <= x.removed <= END
        )
        removal_i = 0

        def native_open(ch, d):
            r = ch.exact(d)
            return None if r is None else ch.native(r, "open", d)

        def native_close(ch, d):
            r = ch.exact(d)
            return None if r is None else ch.native(r, "close", d)

        def queue_exit(sym, d, reason, kind, rank=9999):
            nonlocal orders
            orders = [o for o in orders if not (o.symbol == sym and o.side == "BUY")]
            if any(o.symbol == sym and o.side == "SELL" and o.kind in ("STOP", "RULE", "BEAR", "MEMBERSHIP") for o in orders):
                return
            p = positions.get(sym)
            if p:
                orders.append(Order(sym, "SELL", int(p.shares), reason, rank, kind, d, d))

        def execute_orders(day):
            nonlocal cash, orders, total_costs, traded_notional
            if not orders:
                return
            sells = sorted([o for o in orders if o.side == "SELL"], key=lambda o: (o.rank, o.symbol))
            buys = sorted([o for o in orders if o.side == "BUY"], key=lambda o: (o.rank, o.symbol))
            remaining = []

            for o in sells:
                if day < o.earliest:
                    remaining.append(o)
                    continue
                p = positions.get(o.symbol)
                if not p:
                    continue
                ch = charts.get(o.symbol)
                op = native_open(ch, day) if ch else None
                if op is None or op <= 0:
                    remaining.append(o)
                    continue
                q = min(int(o.shares), int(p.shares))
                if q <= 0:
                    continue
                fill = op * (1.0 - MARKET_DRAG)
                fee = estimated_commission(q)
                cash += q * fill - fee
                total_costs += fee + q * (op - fill)
                traded_notional += q * op
                trades.append({
                    "date": day.isoformat(), "symbol": o.symbol, "side": "SELL",
                    "shares": q, "fill": fill, "fees": fee, "kind": o.kind, "reason": o.reason,
                })
                p.shares -= q
                if p.shares <= 0:
                    positions.pop(o.symbol, None)

            for o in buys:
                if day < o.earliest:
                    remaining.append(o)
                    continue
                ch = charts.get(o.symbol)
                op = native_open(ch, day) if ch else None
                if op is None or op <= 0:
                    remaining.append(o)
                    continue
                desired = int(o.shares)
                fill = op * (1.0 + MARKET_DRAG)
                q = desired
                while q > 0 and q * fill + estimated_commission(q) > cash + 1e-9:
                    q -= 1
                if q <= 0:
                    continue
                fee = estimated_commission(q)
                if o.symbol in positions:
                    p = positions[o.symbol]
                    newq = p.shares + q
                    p.avg_cost = (p.avg_cost * p.shares + fill * q) / newq
                    p.shares = newq
                else:
                    pi = ch.prior_index(day)
                    atr = ch.native_atr_index(pi, day) if pi >= 0 else None
                    if atr is None or atr <= 0:
                        unresolved_orders.append({"date": day.isoformat(), "symbol": o.symbol, "reason": "entry ATR unavailable"})
                        continue
                    positions[o.symbol] = Position(o.symbol, q, fill, fill, fill - 3.0 * atr, day)
                cash -= q * fill + fee
                total_costs += fee + q * (fill - op)
                traded_notional += q * op
                trades.append({
                    "date": day.isoformat(), "symbol": o.symbol, "side": "BUY",
                    "shares": q, "fill": fill, "fees": fee, "kind": o.kind, "reason": o.reason,
                })
                if q < desired:
                    unresolved_orders.append({"date": day.isoformat(), "symbol": o.symbol, "reason": f"funding clip {desired}->{q}"})
            orders = remaining

        def mark_equity(day):
            eq = cash
            for sym, p in positions.items():
                ch = charts.get(sym)
                if not ch:
                    continue
                r = ch.before(day)
                if r:
                    px = ch.native(r, "close", day)
                    last_prices[sym] = px
                    eq += p.shares * px
                elif sym in last_prices:
                    eq += p.shares * last_prices[sym]
            return eq

        def append_audit(day, nav, selected, weights):
            if day.year != 2023:
                return
            snap = snapshots[day]
            selected_set = set(selected or [])
            month_orders = [o for o in orders if o.created == day]
            for sym, meta in AUDIT_LEADERS.items():
                mem = snap["active"].get(sym)
                sig = snap["signals"].get(sym)
                rank = snap["ranks"].get(sym)
                held = sym in positions
                shares = int(positions[sym].shares) if held else 0
                current_weight = None
                if held and sig is not None and nav > 0:
                    current_weight = shares * float(sig["signal_price"]) / nav
                fc = None
                if mem is not None:
                    fc = fund_check(sym, day, mem.sector)
                target_weight = weights.get(sym) if weights else None
                sym_orders = [o for o in month_orders if o.symbol == sym]
                planned = "; ".join(f"{o.side} {o.shares} {o.kind}: {o.reason}" for o in sym_orders)

                if sym_orders:
                    reason = planned
                elif snap["regime"] == "BEAR":
                    reason = "REGIME_BEAR"
                elif mem is None:
                    reason = "NOT_IN_S&P500"
                elif sig is None:
                    reason = "PRICE_OR_HISTORY_SIGNAL_UNAVAILABLE"
                elif sig["score"] <= 0:
                    reason = "MOMENTUM_NON_POSITIVE"
                elif held and sym in selected_set:
                    if fc and fc["status"] == "REVIEW":
                        reason = "RETAINED_FUNDAMENTALS_REVIEW_NO_ADDITION"
                    else:
                        reason = "RETAINED_NO_ORDER"
                elif (not held) and rank is not None and rank > ENTRY_CUTOFF:
                    reason = "RAW_RANK_OUTSIDE_TOP20"
                elif (not held) and fc and fc["status"] != "PASS":
                    reason = f"FUNDAMENTAL_{fc['status']}: {fc['reason']}"
                elif sym in selected_set:
                    reason = "SELECTED_NO_WHOLE_SHARE_ORDER_OR_ALREADY_AT_TARGET"
                elif held:
                    reason = "HELD_BUT_EXITING_OR_NOT_SELECTED"
                else:
                    reason = "NOT_SELECTED_OTHER"

                audit_rows.append({
                    "decision_date": day.isoformat(),
                    "symbol": sym,
                    "contribution_rank": meta["contribution_rank"],
                    "sp500_contribution_pct": meta["sp500_contribution_pct"],
                    "regime": snap["regime"],
                    "member": mem is not None,
                    "momentum_score": None if sig is None else sig["score"],
                    "raw_rank": rank,
                    "top20": bool(rank is not None and rank <= 20),
                    "top35": bool(rank is not None and rank <= 35),
                    "fundamental_status": None if fc is None else fc["status"],
                    "fundamental_reason": None if fc is None else fc["reason"],
                    "fundamental_source": None if fc is None else fc["source"],
                    "held_at_month_end": held,
                    "shares": shares,
                    "actual_weight": current_weight,
                    "selected_after_decision": sym in selected_set,
                    "target_weight": target_weight,
                    "planned_order": planned or None,
                    "diagnosis": reason,
                })

        def monthly_plan(day, nav):
            nonlocal orders
            snap = snapshots[day]
            nextday = next_spy.get(day)
            if not nextday:
                return
            orders = [o for o in orders if o.kind in ("STOP", "MEMBERSHIP")]

            if snap["regime"] == "BEAR":
                for sym in list(positions):
                    queue_exit(sym, day, "SPY total return <= EMA200", "BEAR", 0)
                for o in orders:
                    if o.earliest <= day:
                        o.earliest = nextday
                append_audit(day, nav, [], {})
                return

            retained = []
            review_retained = set()
            exiting = set()
            for sym, p in list(positions.items()):
                if any(o.symbol == sym and o.side == "SELL" and o.kind in ("STOP", "MEMBERSHIP") for o in orders):
                    exiting.add(sym)
                    continue
                rank = snap["ranks"].get(sym)
                sig = snap["signals"].get(sym)
                if sig is None or sig["score"] <= 0:
                    exiting.add(sym)
                    queue_exit(sym, day, "Momentum score non-positive or price signal unavailable", "RULE", 9999)
                    continue
                if (not v.disable_rank_exit) and (rank is None or rank > RETENTION_CUTOFF):
                    exiting.add(sym)
                    queue_exit(sym, day, "Raw momentum rank outside Top 35", "RULE", rank or 9999)
                    continue
                mem = snap["active"].get(sym)
                if mem is None:
                    exiting.add(sym)
                    queue_exit(sym, day, "Not in point-in-time S&P 500 membership", "RULE", rank or 9999)
                    continue
                fc = fund_check(sym, day, mem.sector)
                if not v.fundamentals_entry_only:
                    if fc["status"] == "FAIL":
                        p.last_verified = "FAIL"
                        exiting.add(sym)
                        queue_exit(sym, day, "Fundamental gate failed", "RULE", rank)
                        continue
                    if fc["status"] == "PASS":
                        p.last_verified = "PASS"
                    else:
                        review_retained.add(sym)
                else:
                    if fc["status"] == "PASS":
                        p.last_verified = "PASS"
                retained.append(sym)

            entries = []
            entry_universe = snap["top35"][:ENTRY_CUTOFF]
            for sym in entry_universe:
                if len(retained) + len(entries) >= MAX_HOLDINGS:
                    break
                if sym in positions or sym in exiting:
                    continue
                mem = snap["active"].get(sym)
                if not mem:
                    continue
                fc = fund_check(sym, day, mem.sector)
                if fc["status"] == "PASS":
                    entries.append(sym)

            selected = retained + entries
            sigs = [snap["signals"][s] for s in selected if s in snap["signals"]]
            n = len(sigs)
            if n == 0:
                for o in orders:
                    if o.earliest <= day:
                        o.earliest = nextday
                append_audit(day, nav, selected, {})
                return

            breadth = n / 20.0
            if v.exposure_mode == "n_over_20":
                exposure = breadth
            elif v.exposure_mode == "floor40":
                exposure = max(0.40, breadth)
            elif v.exposure_mode == "floor50":
                exposure = max(0.50, breadth)
            elif v.exposure_mode == "floor60":
                exposure = max(0.60, breadth)
            elif v.exposure_mode == "sqrt":
                exposure = math.sqrt(breadth)
            elif v.exposure_mode == "full":
                exposure = 1.0
            else:
                raise RuntimeError(f"Unknown exposure mode: {v.exposure_mode}")
            exposure = min(1.0, exposure)
            inv = {s["symbol"]: 1.0 / s["atr_pct"] for s in sigs if s["atr_pct"] > 0}
            denom = sum(inv.values())
            weights = {s: exposure * val / denom for s, val in inv.items()} if denom > 0 else {}

            current_weights = {}
            for sym, p in positions.items():
                ch = charts.get(sym)
                r = ch.exact(day) if ch else None
                if r and nav > 0:
                    current_weights[sym] = p.shares * ch.native(r, "close", day) / nav

            for sym in review_retained:
                if sym in weights:
                    weights[sym] = min(weights[sym], current_weights.get(sym, 0.0))

            for sym in selected:
                sig = snap["signals"][sym]
                target_value = nav * weights.get(sym, 0.0)
                tq = dm.target_qty(target_value, sig["signal_price"])
                cq = positions[sym].shares if sym in positions else 0
                rank = snap["ranks"].get(sym) or 9999
                if sym in review_retained and tq > cq:
                    tq = cq
                if tq < cq:
                    if not v.no_monthly_trim:
                        orders.append(Order(sym, "SELL", cq - tq, "Monthly resize to target", rank, "TRIM", day, nextday))
                elif tq > cq:
                    orders.append(Order(sym, "BUY", tq - cq, "Monthly resize/new entry", rank, "BUY", day, nextday))

            for o in orders:
                if o.created == day and o.earliest <= day:
                    o.earliest = nextday
            append_audit(day, nav, selected, weights)

        print(f"AUD23_SIM_START {v.key}", flush=True)
        for session_n, day in enumerate(calendar, 1):
            for sym, p in list(positions.items()):
                ch = charts.get(sym)
                if not ch:
                    continue
                for sd, ratio in ch.splits:
                    if sd == day:
                        new_shares = p.shares * ratio
                        rounded = round(new_shares)
                        if abs(new_shares - rounded) > 1e-8:
                            op = native_open(ch, day) or (native_close(ch, day) or 0.0)
                            whole = math.floor(new_shares + 1e-12)
                            frac = new_shares - whole
                            if frac > 0 and op > 0:
                                cash += frac * op
                            split_fraction_events.append({"date": day.isoformat(), "symbol": sym, "fraction": frac})
                            p.shares = int(whole)
                        else:
                            p.shares = int(rounded)
                        p.avg_cost /= ratio
                        p.peak /= ratio
                        p.stop /= ratio

            for sym, p in list(positions.items()):
                ch = charts.get(sym)
                if ch:
                    dv = ch.dividend_native(day)
                    if dv:
                        cash += p.shares * dv

            while removal_i < len(removal_events) and removal_events[removal_i][0] <= day:
                rd, sym = removal_events[removal_i]
                key = (rd, sym)
                if key not in processed_removals and sym in positions:
                    queue_exit(sym, day, f"Effective S&P 500 removal {rd.isoformat()}", "MEMBERSHIP", 0)
                    for o in orders:
                        if o.symbol == sym and o.kind == "MEMBERSHIP":
                            o.earliest = day
                    processed_removals.add(key)
                removal_i += 1

            execute_orders(day)

            if not v.disable_atr_stops:
                for sym, p in list(positions.items()):
                    ch = charts.get(sym)
                    r = ch.exact(day) if ch else None
                    if not r:
                        continue
                    i = ch.index[day]
                    atr = ch.native_atr_index(i, day)
                    close = ch.native(r, "close", day)
                    if atr is None or atr <= 0:
                        continue
                    prior = StopState(p.peak, p.stop, False)
                    nxt = advance_stop(prior, close, atr)
                    if nxt.breached:
                        nd = spy.rows[spy_idx[day] + 1]["date"] if spy_idx[day] + 1 < len(spy.rows) else day + timedelta(days=1)
                        queue_exit(sym, day, "3xATR closing stop breached", "STOP", 0)
                        for o in orders:
                            if o.symbol == sym and o.kind == "STOP":
                                o.earliest = nd
                    else:
                        p.peak = nxt.peak
                        p.stop = nxt.stop

            nav = mark_equity(day)
            curve.append({"date": day, "equity": nav, "cash": cash, "holdings": len(positions)})
            if day in month_set:
                monthly_plan(day, nav)

        for o in orders:
            unresolved_orders.append({
                "date": END.isoformat(), "symbol": o.symbol,
                "reason": f"unexecuted {o.kind} order: {o.reason}",
            })

        end_value = curve[-1]["equity"]
        years = (curve[-1]["date"] - curve[0]["date"]).days / 365.25
        total_return = end_value / STARTING_CASH - 1.0
        cagr = (end_value / STARTING_CASH) ** (1.0 / years) - 1.0

        peak = 0.0
        max_dd = 0.0
        cash_weights = []
        holdings_counts = []
        byyear = defaultdict(list)
        for r in curve:
            peak = max(peak, r["equity"])
            max_dd = min(max_dd, r["equity"] / peak - 1.0)
            byyear[r["date"].year].append(r)
            cash_weights.append(r["cash"] / r["equity"] if r["equity"] > 0 else 0.0)
            holdings_counts.append(r["holdings"])

        annual = {}
        prev = STARTING_CASH
        for y in sorted(byyear):
            val = byyear[y][-1]["equity"]
            annual[str(y)] = val / prev - 1.0
            prev = val

        avg_equity = statistics.mean(r["equity"] for r in curve)
        annual_turnover = traded_notional / avg_equity / years if avg_equity > 0 and years > 0 else None
        sell_kinds = defaultdict(int)
        for t in trades:
            if t["side"] == "SELL":
                sell_kinds[t["kind"]] += 1

        sell_reason_counts_2023 = defaultdict(int)
        sells_2023 = 0
        trims_2023 = 0
        for t in trades:
            if t["side"] == "SELL" and str(t["date"]).startswith("2023-"):
                sells_2023 += 1
                sell_reason_counts_2023[t["kind"]] += 1
                if t["kind"] == "TRIM":
                    trims_2023 += 1

        audit_trades = [
            t for t in trades
            if str(t["date"]).startswith("2023-") and t["symbol"] in AUDIT_LEADERS
        ]

        leader_summary = {}
        for sym, meta in AUDIT_LEADERS.items():
            rows = [r for r in audit_rows if r["symbol"] == sym]
            ch = charts.get(sym)
            yrows = [r for r in (ch.rows if ch else []) if r["date"].year == 2023]
            yret = None
            if len(yrows) >= 2 and yrows[0]["adjclose"] > 0:
                yret = yrows[-1]["adjclose"] / yrows[0]["adjclose"] - 1.0
            sym_trades = [t for t in audit_trades if t["symbol"] == sym]
            leader_summary[sym] = {
                **meta,
                "price_total_return_2023": yret,
                "months_member": sum(1 for r in rows if r["member"]),
                "months_top20": sum(1 for r in rows if r["top20"]),
                "months_top35": sum(1 for r in rows if r["top35"]),
                "months_fund_pass": sum(1 for r in rows if r["fundamental_status"] == "PASS"),
                "months_fund_fail": sum(1 for r in rows if r["fundamental_status"] == "FAIL"),
                "months_fund_review": sum(1 for r in rows if r["fundamental_status"] == "REVIEW"),
                "months_held": sum(1 for r in rows if r["held_at_month_end"]),
                "months_selected": sum(1 for r in rows if r["selected_after_decision"]),
                "first_top20": next((r["decision_date"] for r in rows if r["top20"]), None),
                "first_pass_top20_bull": next((
                    r["decision_date"] for r in rows
                    if r["regime"] == "BULL" and r["top20"] and r["fundamental_status"] == "PASS"
                ), None),
                "first_held_month_end": next((r["decision_date"] for r in rows if r["held_at_month_end"]), None),
                "buy_trades_2023": sum(1 for t in sym_trades if t["side"] == "BUY"),
                "sell_trades_2023": sum(1 for t in sym_trades if t["side"] == "SELL"),
                "trade_log_2023": sym_trades,
                "month_end_diagnoses": [
                    {
                        "decision_date": r["decision_date"],
                        "rank": r["raw_rank"],
                        "fundamental_status": r["fundamental_status"],
                        "held": r["held_at_month_end"],
                        "selected": r["selected_after_decision"],
                        "actual_weight": r["actual_weight"],
                        "target_weight": r["target_weight"],
                        "diagnosis": r["diagnosis"],
                    }
                    for r in rows
                ],
            }

        out = {
            "key": v.key,
            "label": v.label,
            "end_value": end_value,
            "absolute_profit": end_value - STARTING_CASH,
            "total_return": total_return,
            "cagr": cagr,
            "max_drawdown": max_dd,
            "annual": annual,
            "average_cash_weight": statistics.mean(cash_weights),
            "average_equity_weight": 1.0 - statistics.mean(cash_weights),
            "average_holdings": statistics.mean(holdings_counts),
            "max_holdings": max(holdings_counts),
            "annualized_turnover": annual_turnover,
            "transaction_costs": total_costs,
            "trade_count": len(trades),
            "sell_kinds": dict(sell_kinds),
            "ending_cash": cash,
            "ending_holdings": len(positions),
            "unresolved_order_count": len(unresolved_orders),
            "sells_2023": sells_2023,
            "trims_2023": trims_2023,
            "sell_kinds_2023": dict(sell_reason_counts_2023),
            "audit_rows": audit_rows,
            "audit_trades_2023": audit_trades,
            "leader_summary": leader_summary,
        }
        print("AUD23_VARIANT_RESULT=" + json.dumps(out, separators=(",", ":")), flush=True)
        return out

    results = [run_variant(v) for v in VARIANTS]
    baseline = next(x for x in results if x["key"] == "research_base")
    for x in results:
        x["delta_vs_baseline"] = {
            "cagr_pp": (x["cagr"] - baseline["cagr"]) * 100.0,
            "total_return_pp": (x["total_return"] - baseline["total_return"]) * 100.0,
            "extra_drawdown_pp": (abs(x["max_drawdown"]) - abs(baseline["max_drawdown"])) * 100.0,
            "cash_weight_pp": (x["average_cash_weight"] - baseline["average_cash_weight"]) * 100.0,
            "end_value_usd": x["end_value"] - baseline["end_value"],
        }

    benchmark = dm.benchmark_stats(bench, START, END)
    final = {
        "period": {"start": START.isoformat(), "end": END.isoformat()},
        "benchmark": {"name": benchmark_name, **benchmark},
        "baseline_reconciliation": {
            "expected_end_value": EXPECTED_BASELINE_END,
            "actual_end_value": baseline["end_value"],
            "difference_usd": baseline["end_value"] - EXPECTED_BASELINE_END,
        },
        "variants": results,
        "coverage": {
            "membership_source": membership_source,
            "historical_symbols": len(symbols),
            "price_symbols_ok": len(charts),
            "price_symbols_failed": len(price_failed),
            "price_symbol_coverage": len(charts) / len(symbols) if symbols else 0.0,
            "member_month_signal_coverage": member_month_signal / member_month_total if member_month_total else 0.0,
            "ticker_alias_recovery_count": len(alias_recoveries),
            "ticker_alias_recoveries": alias_recoveries,
            "sec_fallback_requested": len(needs_sec),
            "sec_fallback_ok": len(secfacts),
            "sec_fallback_failed": len(sec_failed),
            "missing_price_symbols": sorted(price_failed),
        },
        "definitions": {
            "research_base": "No ATR stops + sqrt(N/20); raw Top-20 entry, Top-35 retention, inverse-ATR weights, original post-entry fundamental exits and monthly resizing.",
            "audit_leaders": "Top 10 S&P 500 return contributors for 2023 from State Street attribution; used only as diagnostic targets, not in strategy selection.",
        }


    }

    out = ROOT / "backtests" / "results" / "dual_momentum_2023_missed_winners_audit.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(final, indent=2, default=str))
    print("AUD23_FINAL_JSON=" + json.dumps(final, separators=(",", ":"), default=str), flush=True)


if __name__ == "__main__":
    main()
