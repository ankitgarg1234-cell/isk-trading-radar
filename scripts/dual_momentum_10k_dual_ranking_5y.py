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

EXPECTED_BASELINE_END = 18751.686956494832


@dataclass(frozen=True)
class Variant:
    key: str
    label: str
    leadership_pct: float
    leadership_mode: str
    leadership_top_issuers: int = 0
    leadership_max_names: int = 5
    momentum_weights: tuple[float, float, float] = (1.0/3.0, 1.0/3.0, 1.0/3.0)
    disable_atr_stops: bool = True
    exposure_mode: str = "sqrt"
    no_monthly_trim: bool = True
    disable_rank_exit: bool = False
    fundamentals_entry_only: bool = True
    derive_gross_profit: bool = True
    integer_allocator: bool = True


VARIANTS = [
    Variant("control", "Raw momentum control", 0.00, "none"),
    Variant("heuristic_lead25", "Prior fixed 25% heuristic leadership sleeve", 0.25, "heuristic", 15, 5),
    Variant("dual_rank_lead25", "25% leadership sleeve ranked by momentum + point-in-time market cap", 0.25, "dual_rank", 0, 5),
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


def percentile_map(values):
    if not values:
        return {}
    if len(values) == 1:
        return {next(iter(values)): 1.0}
    vals = list(values.values())
    n = len(vals)
    out = {}
    for key, val in values.items():
        lower = sum(1 for x in vals if x < val)
        equal = sum(1 for x in vals if x == val)
        out[key] = (lower + 0.5 * (equal - 1)) / (n - 1)
    return out


def main():
    print("DUALRANK10K_STAGE membership", flush=True)
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

    print(f"DUALRANK10K_STAGE prices symbols={len(symbols)}", flush=True)
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
                print(f"DUALRANK10K_PRICE {n}/{len(futs)} ok={len(charts)} fail={len(price_failed)} aliases={len(alias_recoveries)}", flush=True)

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

    snapshots_by_variant = {v.key: {} for v in VARIANTS}
    top35_union = set()
    member_month_total = 0
    member_month_signal = 0
    for d in month_ends:
        active = active_intervals(d)
        base_sigs = []
        for sym, mem in active.items():
            ch = charts.get(sym)
            if not ch:
                continue
            z = dm.signal(ch, d, f"{mem.cik or sym}:{sym}")
            if z:
                base_sigs.append(z)
        member_month_total += len(active)
        member_month_signal += len(base_sigs)
        i_spy = spy_idx[d]
        reg = "BULL" if ema[i_spy] is not None and spy.rows[i_spy]["adjclose"] > ema[i_spy] else "BEAR"

        for v in VARIANTS:
            w63, w126, w252 = v.momentum_weights
            sigs = []
            for base in base_sigs:
                z = dict(base)
                z["score"] = w63 * z["r63"] + w126 * z["r126"] + w252 * z["r252"]
                sigs.append(z)
            sigs.sort(key=lambda z: (-z["score"], -z["adv63"], z["security_id"]))
            positive = [z for z in sigs if z["score"] > 0]
            ranks = {z["symbol"]: i + 1 for i, z in enumerate(positive)}
            smap = {z["symbol"]: z for z in sigs}
            top35 = positive[:35]
            top35_union.update(z["symbol"] for z in top35)
            snapshots_by_variant[v.key][d] = {
                "regime": reg,
                "active": active,
                "signals": smap,
                "ranks": ranks,
                "top35": [z["symbol"] for z in top35],
            }

    valuein = dm.load_valuein()
    needs_sec = set()
    for v in VARIANTS:
        for d, snap in snapshots_by_variant[v.key].items():
            if snap["regime"] != "BULL":
                continue
            for sym in snap["top35"]:
                mem = snap["active"].get(sym)
                exempt = bool(mem and mem.sector in GM_EXEMPT)
                ck = dm.fund_from_valuein(valuein, sym, d, exempt)
                if ck.status == FundamentalStatus.REVIEW:
                    needs_sec.add(sym)

    cik_by_symbol = {}
    for sym in symbols:
        rows = by_symbol_intervals.get(sym) or []
        cik = next((x.cik for x in reversed(rows) if x.cik), "")
        if cik:
            cik_by_symbol[sym] = cik

    # Fetch companyfacts for every historical issuer so market-cap ranking is
    # point-in-time rather than based on today's mega-cap list.
    needs_sec = set(sym for sym in symbols if sym in cik_by_symbol)

    secfacts = {}
    sec_failed = {}
    limiter = Limiter(6.0)

    symbols_by_cik = defaultdict(list)
    for sym in sorted(needs_sec):
        symbols_by_cik[cik_by_symbol[sym]].append(sym)

    def sec_task_cik(cik):
        try:
            limiter.wait()
            fact = dm.request_json(dm.SEC_COMPANYFACTS.format(cik), attempts=4, headers={"User-Agent": dm.UA})
            return cik, fact, None
        except Exception as exc:
            return cik, None, f"{type(exc).__name__}: {exc}"

    print(f"DUALRANK10K_STAGE companyfacts issuers={len(symbols_by_cik)}", flush=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = [pool.submit(sec_task_cik, cik) for cik in sorted(symbols_by_cik)]
        for n, fut in enumerate(as_completed(futs), 1):
            cik, fact, err = fut.result()
            for sym in symbols_by_cik[cik]:
                if fact:
                    secfacts[sym] = fact
                else:
                    sec_failed[sym] = err
            if n % 75 == 0 or n == len(futs):
                print(f"DUALRANK10K_SEC {n}/{len(futs)} issuer_ok={n - sum(1 for _ in [])} symbol_facts={len(secfacts)} symbol_fail={len(sec_failed)}", flush=True)

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

    COST_TAG_HINTS = (
        "CostOfRevenue",
        "CostOfRevenues",
        "CostOfGoodsAndServicesSold",
        "CostOfGoodsSold",
        "CostOfSales",
        "CostOfProductsSold",
        "CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization",
    )

    def fund_check_derived(sym, d, sector):
        base = fund_check(sym, d, sector)
        if base["status"] != "REVIEW" or "gross" not in str(base.get("reason") or "").lower():
            return base
        facts = secfacts.get(sym)
        if not facts:
            return base

        rev_choices = []
        for tag in dm.REVENUE_TAGS:
            qs = dm.quarter_series_sec(dm.sec_fact(facts, (tag,)), d)
            if qs:
                rev_choices.append(qs)
        rev = max(rev_choices, key=lambda q: (q[-1][0], len(q))) if rev_choices else []
        if len(rev) < 8:
            return base

        usgaap = ((facts.get("facts") or {}).get("us-gaap") or {})
        candidate_tags = []
        for tag in usgaap:
            low = tag.lower()
            if tag in COST_TAG_HINTS or (
                ("costofrevenue" in low or "costofrevenues" in low or "costofgoods" in low or "costofsales" in low)
                and "inventory" not in low
            ):
                candidate_tags.append(tag)

        latest_ends = [pe for pe, _ in rev[-4:]]
        best = None
        for tag in candidate_tags:
            qs = dm.quarter_series_sec(usgaap.get(tag), d)
            if not qs:
                continue
            qmap = dict(qs)
            aligned = [qmap.get(pe) for pe in latest_ends]
            coverage = sum(v is not None for v in aligned)
            if coverage < 4:
                continue
            score = (coverage, qs[-1][0], len(qs))
            if best is None or score > best[0]:
                best = (score, tag, aligned)

        if best is None:
            return base

        rev8 = [float(v) for _, v in rev[-8:]]
        latest_rev4 = rev8[-4:]
        cost4 = [float(v) for v in best[2]]
        gp4 = [r - k for r, k in zip(latest_rev4, cost4)]
        ck = dm.evaluate_fundamentals(
            rev8,
            gp4,
            gross_margin_exempt=(sector in GM_EXEMPT),
        )
        return {
            "status": ck.status.value,
            "revenue_growth": ck.revenue_growth_ttm,
            "gross_margin": ck.gross_margin_ttm,
            "reason": ck.reason,
            "source": "sec-derived-gp:" + best[1],
        }

    def latest_shares_outstanding(facts, asof):
        if not facts:
            return None
        dei = (facts.get("facts") or {}).get("dei") or {}
        fact = dei.get("EntityCommonStockSharesOutstanding")
        if not fact:
            return None
        candidates = []
        for unit_rows in (fact.get("units") or {}).values():
            for r in unit_rows or []:
                fd = dm.pdate(r.get("filed"))
                ed = dm.pdate(r.get("end"))
                val = dm.fnum(r.get("val"))
                if not fd or not ed or val is None or val <= 0:
                    continue
                if fd >= asof or ed > asof:
                    continue
                candidates.append((ed, fd, float(val)))
        if not candidates:
            return None
        candidates.sort()
        return candidates[-1][2]

    stock_ema200 = {}
    for sym, ch in charts.items():
        stock_ema200[sym] = ema_seeded([r["adjclose"] for r in ch.rows], 200)

    def above_stock_ema200(sym, d):
        ch = charts.get(sym)
        if not ch:
            return False
        i = ch.index.get(d)
        if i is None:
            return False
        series = stock_ema200.get(sym) or []
        if i >= len(series) or series[i] is None:
            return False
        return float(ch.rows[i]["adjclose"]) > float(series[i])

    calendar = [d for d in spy_test_dates if START <= d <= END]
    month_set = set(month_ends)

    def run_variant(v: Variant):
        snapshots = snapshots_by_variant[v.key]
        positions = {}
        leadership_monthly = []
        cash = STARTING_CASH
        orders = []
        trades = []
        curve = []
        total_costs = 0.0
        traded_notional = 0.0
        unresolved_orders = []
        split_fraction_events = []
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
                return

            leadership_preselected = []
            leadership_pre_rows = []
            if v.leadership_pct > 0:
                issuer_candidates_pre = defaultdict(list)
                for sym0, mem0 in snap["active"].items():
                    sig0 = snap["signals"].get(sym0)
                    if sig0 is None or sig0["signal_price"] <= 0 or sig0["score"] <= 0:
                        continue
                    sh0 = latest_shares_outstanding(secfacts.get(sym0), day)
                    if sh0 is None:
                        continue
                    issuer0 = mem0.cik or sym0
                    issuer_candidates_pre[issuer0].append(
                        (sym0, mem0, sig0, sh0 * float(sig0["signal_price"]))
                    )

                if v.leadership_mode == "heuristic":
                    ranked_pre = []
                    for issuer0, rows0 in issuer_candidates_pre.items():
                        ranked_pre.append((max(x[3] for x in rows0), issuer0, rows0))
                    ranked_pre.sort(key=lambda x: (-x[0], x[1]))
                    for issuer_mcap0, issuer0, rows0 in ranked_pre[:v.leadership_top_issuers]:
                        classes0 = []
                        for sym0, mem0, sig0, _ in rows0:
                            rank0 = snap["ranks"].get(sym0)
                            if rank0 is None or rank0 > 100 or sig0["r126"] <= 0 or not above_stock_ema200(sym0, day):
                                continue
                            fc0 = fund_check_derived(sym0, day, mem0.sector)
                            if sym0 not in positions and fc0["status"] != "PASS":
                                continue
                            classes0.append((rank0, -sig0["adv63"], sig0["security_id"], sym0, mem0, sig0, fc0))
                        if classes0:
                            classes0.sort()
                            _, _, _, sym0, mem0, sig0, fc0 = classes0[0]
                            leadership_pre_rows.append({
                                "issuer": issuer0,
                                "symbol": sym0,
                                "market_cap_proxy": issuer_mcap0,
                                "raw_rank": snap["ranks"].get(sym0),
                                "leadership_score": None,
                                "momentum_percentile": None,
                                "market_cap_percentile": None,
                                "fundamental_status": fc0["status"],
                            })
                    leadership_pre_rows.sort(
                        key=lambda x: (-x["market_cap_proxy"], x["raw_rank"], x["symbol"])
                    )
                    leadership_pre_rows = leadership_pre_rows[:v.leadership_max_names]

                elif v.leadership_mode == "dual_rank":
                    issuer_best = {}
                    for issuer0, rows0 in issuer_candidates_pre.items():
                        classes0 = []
                        for sym0, mem0, sig0, mcap0 in rows0:
                            fc0 = fund_check_derived(sym0, day, mem0.sector)
                            if sym0 not in positions and fc0["status"] != "PASS":
                                continue
                            classes0.append((
                                -sig0["score"],
                                -sig0["adv63"],
                                sig0["security_id"],
                                sym0, mem0, sig0, fc0, mcap0,
                            ))
                        if classes0:
                            classes0.sort()
                            _, _, _, sym0, mem0, sig0, fc0, mcap0 = classes0[0]
                            issuer_best[issuer0] = (sym0, mem0, sig0, fc0, mcap0)

                    momentum_pct = percentile_map({
                        issuer0: row0[2]["score"]
                        for issuer0, row0 in issuer_best.items()
                    })
                    mcap_pct = percentile_map({
                        issuer0: row0[4]
                        for issuer0, row0 in issuer_best.items()
                    })

                    for issuer0, (sym0, mem0, sig0, fc0, mcap0) in issuer_best.items():
                        score0 = 0.5 * momentum_pct[issuer0] + 0.5 * mcap_pct[issuer0]
                        leadership_pre_rows.append({
                            "issuer": issuer0,
                            "symbol": sym0,
                            "market_cap_proxy": mcap0,
                            "raw_rank": snap["ranks"].get(sym0),
                            "leadership_score": score0,
                            "momentum_percentile": momentum_pct[issuer0],
                            "market_cap_percentile": mcap_pct[issuer0],
                            "fundamental_status": fc0["status"],
                        })
                    leadership_pre_rows.sort(
                        key=lambda x: (
                            -x["leadership_score"],
                            -x["momentum_percentile"],
                            -x["market_cap_percentile"],
                            x["symbol"],
                        )
                    )
                    leadership_pre_rows = leadership_pre_rows[:v.leadership_max_names]

                leadership_preselected = [r["symbol"] for r in leadership_pre_rows]

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
                if (not v.disable_rank_exit) and (rank is None or rank > RETENTION_CUTOFF) and sym not in leadership_preselected:
                    exiting.add(sym)
                    queue_exit(sym, day, "Raw momentum rank outside Top 35", "RULE", rank or 9999)
                    continue
                mem = snap["active"].get(sym)
                if mem is None:
                    exiting.add(sym)
                    queue_exit(sym, day, "Not in point-in-time S&P 500 membership", "RULE", rank or 9999)
                    continue
                fc = fund_check_derived(sym, day, mem.sector) if v.derive_gross_profit else fund_check(sym, day, mem.sector)
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
                fc = fund_check_derived(sym, day, mem.sector) if v.derive_gross_profit else fund_check(sym, day, mem.sector)
                if fc["status"] == "PASS":
                    entries.append(sym)

            rotational_selected = retained + entries

            leadership_selected = list(leadership_preselected)
            leadership_issuer_rows = list(leadership_pre_rows)

            # A holding survives if it still qualifies through either engine.
            selected = list(dict.fromkeys(rotational_selected + leadership_selected))
            leadership_monthly.append({
                "date": day.isoformat(),
                "selected": list(leadership_selected),
                "qualified_issuers": leadership_issuer_rows[:v.leadership_max_names],
            })

            sigs = [snap["signals"][s] for s in selected if s in snap["signals"]]
            n = len(sigs)
            if n == 0:
                for o in orders:
                    if o.earliest <= day:
                        o.earliest = nextday
                return

            breadth = len(rotational_selected) / 20.0
            if v.exposure_mode == "sqrt":
                rotational_exposure_raw = math.sqrt(breadth) if breadth > 0 else 0.0
            else:
                rotational_exposure_raw = breadth
            rotational_budget = (1.0 - v.leadership_pct) * min(1.0, rotational_exposure_raw)
            leadership_budget = v.leadership_pct if leadership_selected else 0.0
            exposure = min(1.0, rotational_budget + leadership_budget)

            weights = defaultdict(float)
            rot_sigs = [snap["signals"][s] for s in rotational_selected if s in snap["signals"]]
            if rot_sigs and rotational_budget > 0:
                inv_rot = {s["symbol"]: 1.0 / s["atr_pct"] for s in rot_sigs if s["atr_pct"] > 0}
                denom_rot = sum(inv_rot.values())
                if denom_rot > 0:
                    for sym0, val0 in inv_rot.items():
                        weights[sym0] += rotational_budget * val0 / denom_rot

            lead_sigs = [snap["signals"][s] for s in leadership_selected if s in snap["signals"]]
            if lead_sigs and leadership_budget > 0:
                inv_lead = {s["symbol"]: 1.0 / s["atr_pct"] for s in lead_sigs if s["atr_pct"] > 0}
                denom_lead = sum(inv_lead.values())
                if denom_lead > 0:
                    for sym0, val0 in inv_lead.items():
                        weights[sym0] += leadership_budget * val0 / denom_lead

            current_weights = {}
            for sym, p in positions.items():
                ch = charts.get(sym)
                r = ch.exact(day) if ch else None
                if r and nav > 0:
                    current_weights[sym] = p.shares * ch.native(r, "close", day) / nav

            for sym in review_retained:
                if sym in weights:
                    weights[sym] = min(weights[sym], current_weights.get(sym, 0.0))

            target_quantities = {}
            if v.integer_allocator:
                # Production-aware whole-share allocation: floor ideal quantities
                # first, then use remaining portfolio-level exposure budget on the
                # largest fractional remainders. This can buy one expensive leader
                # even when its individual target is below one share, without
                # borrowing or changing the total exposure target.
                ideal = {}
                target_quantities = {}
                for sym in selected:
                    sig = snap["signals"][sym]
                    cq = positions[sym].shares if sym in positions else 0
                    ideal_q = (nav * weights.get(sym, 0.0) / sig["signal_price"]) if sig["signal_price"] > 0 else 0.0
                    ideal[sym] = ideal_q
                    floor_q = int(math.floor(max(0.0, ideal_q)))
                    target_quantities[sym] = max(cq, floor_q)

                target_exposure_value = nav * exposure
                used = sum(
                    target_quantities[sym] * snap["signals"][sym]["signal_price"]
                    for sym in selected
                )
                remainder_budget = max(0.0, target_exposure_value - used)
                candidates = sorted(
                    selected,
                    key=lambda sym: (
                        -(ideal[sym] - math.floor(max(0.0, ideal[sym]))),
                        snap["ranks"].get(sym) or 9999,
                        sym,
                    ),
                )
                progressed = True
                while progressed:
                    progressed = False
                    for sym in candidates:
                        price = snap["signals"][sym]["signal_price"]
                        # Approximate one-share incremental all-in cost at signal time.
                        unit_cost = price * (1.0 + MARKET_DRAG) + 1.0
                        if unit_cost <= remainder_budget + 1e-9:
                            target_quantities[sym] += 1
                            remainder_budget -= unit_cost
                            progressed = True
            else:
                for sym in selected:
                    sig = snap["signals"][sym]
                    target_value = nav * weights.get(sym, 0.0)
                    target_quantities[sym] = dm.target_qty(target_value, sig["signal_price"])

            for sym in selected:
                tq = target_quantities.get(sym, 0)
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

        print(f"DUALRANK10K_SIM_START {v.key}", flush=True)
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

        leader_trades_2023 = defaultdict(lambda: {"buys": 0, "sells": 0})
        for t in trades:
            if str(t["date"]).startswith("2023-") and t["symbol"] in {"MSFT","AAPL","NVDA","AMZN","META","TSLA","GOOGL","GOOG","AVGO","LLY"}:
                if t["side"] == "BUY":
                    leader_trades_2023[t["symbol"]]["buys"] += 1
                else:
                    leader_trades_2023[t["symbol"]]["sells"] += 1

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
            "leader_trade_counts_2023": dict(leader_trades_2023),
            "leadership_monthly": leadership_monthly,
        }
        print("DUALRANK10K_VARIANT_RESULT=" + json.dumps(out, separators=(",", ":")), flush=True)
        return out

    results = [run_variant(v) for v in VARIANTS]
    baseline = next(x for x in results if x["key"] == "control")
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
            "common_framework": "$10,000 starting capital; whole shares; no borrowing; 33/33/33 momentum; no ATR stops; sqrt(N/20) rotational exposure; raw Top-20 rotational entry; Top-35 rotational retention; inverse-ATR relative weights; no routine monthly trimming; derived point-in-time gross profit; portfolio-level integer allocation; fundamentals entry-only.",
            "control": "No leadership sleeve; all selection uses the raw global 33/33/33 momentum engine.",
            "heuristic_lead25": "Prior fixed 25% leadership sleeve: Top-15 point-in-time market-cap issuers, maximum five names, requiring positive momentum, raw rank <=100, R126>0, price above own EMA200 and fundamental PASS for new entries.",
            "dual_rank_lead25": "Fixed 25% leadership sleeve. Among positive-momentum issuers with point-in-time SEC shares-outstanding market-cap proxy and fundamental PASS for new entries, choose one share class per issuer, score each issuer as 50% global momentum percentile + 50% point-in-time market-cap percentile, and select the top five. The 75% rotational sleeve remains raw global 33/33/33 momentum.",
        }


    }

    out = ROOT / "backtests" / "results" / "dual_momentum_10k_dual_ranking_5y.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(final, indent=2, default=str))
    print("DUALRANK10K_FINAL_JSON=" + json.dumps(final, separators=(",", ":"), default=str), flush=True)


if __name__ == "__main__":
    main()
