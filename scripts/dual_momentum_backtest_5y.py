#!/usr/bin/env python3
from __future__ import annotations

import csv
import gzip
import io
import json
import math
import os
import statistics
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

from dual_momentum.rules import (
    FundamentalStatus,
    StopState,
    advance_stop,
    ema_seeded,
    estimated_commission,
    evaluate_fundamentals,
    wilder_atr_series,
)

ROOT = Path(__file__).resolve().parents[1]
START = date(2021, 10, 1)
END = date(2026, 9, 30)
PRICE_START = date(2020, 6, 1)
SPY_START = date(2015, 1, 1)
STARTING_CASH = 10000.0
MARKET_DRAG = 0.0007
MAX_HOLDINGS = 20
ENTRY_CUTOFF = 20
RETENTION_CUTOFF = 35

MEMBERSHIP_URLS = [
    "https://raw.githubusercontent.com/lawcal/sp500-components-history/main/data/components_history.csv",
    "https://cdn.jsdelivr.net/gh/lawcal/sp500-components-history@main/data/components_history.csv",
]
YAHOO_HOSTS = [
    "https://query1.finance.yahoo.com/v8/finance/chart/",
    "https://query2.finance.yahoo.com/v8/finance/chart/",
]
SEC_COMPANYFACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{}.json"
UA = "DualMomentumResearch/1.0 contact=research@example.com"

REVENUE_TAGS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
)
GROSS_TAGS = ("GrossProfit",)
FIN_FORMS = {"10-Q", "10-Q/A", "10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}
ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}
GM_EXEMPT = {"Financials", "Real Estate"}

STAGED_PRICE_PATH = ROOT / "backtests" / "staged" / "wf3_prices.json.gz"
STAGED_FUND_PATH = ROOT / "backtests" / "staged" / "wf3_valuein_fundamentals.json.gz"


def norm_symbol(v):
    return str(v or "").strip().upper().replace(".", "-")


def pdate(v):
    if not v:
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except Exception:
        return None


def fnum(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def epoch(d):
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())


def request_text(url, attempts=5):
    err = None
    for n in range(attempts):
        try:
            r = requests.get(url, headers={"User-Agent": UA, "Accept": "text/csv,*/*"}, timeout=30)
            if r.status_code in (429, 500, 502, 503, 504):
                raise RuntimeError("HTTP {}".format(r.status_code))
            r.raise_for_status()
            return r.text
        except Exception as exc:
            err = exc
            time.sleep(min(8.0, 0.8 * (n + 1) ** 2))
    raise RuntimeError(str(err))


def request_json(url, params=None, attempts=5, headers=None):
    err = None
    hdr = {"User-Agent": UA, "Accept": "application/json"}
    if headers:
        hdr.update(headers)
    for n in range(attempts):
        try:
            r = requests.get(url, params=params, headers=hdr, timeout=35)
            if r.status_code in (429, 500, 502, 503, 504):
                raise RuntimeError("HTTP {}".format(r.status_code))
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            err = exc
            time.sleep(min(10.0, 1.0 * (n + 1) ** 2))
    raise RuntimeError(str(err))


@dataclass
class MemberInterval:
    symbol: str
    name: str
    sector: str
    cik: str
    added: date
    removed: date | None

    def active(self, d):
        return self.added <= d and (self.removed is None or self.removed > d)

    def overlaps(self, start, end):
        return self.added <= end and (self.removed is None or self.removed > start)


def load_membership():
    text = None
    source = None
    last = None
    for url in MEMBERSHIP_URLS:
        try:
            text = request_text(url)
            source = url
            break
        except Exception as exc:
            last = exc
    if text is None:
        raise RuntimeError("membership unavailable: {}".format(last))
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        symbol = norm_symbol(row.get("symbol"))
        added = pdate(row.get("date_added"))
        if not symbol or not added:
            continue
        sector = str(row.get("sector") or "").replace("_", " ").title()
        cik_raw = str(row.get("cik") or "").strip()
        try:
            cik = str(int(float(cik_raw))).zfill(10) if cik_raw else ""
        except Exception:
            cik = ""
        out.append(MemberInterval(
            symbol=symbol,
            name=str(row.get("name") or symbol).strip(),
            sector=sector,
            cik=cik,
            added=added,
            removed=pdate(row.get("date_removed")),
        ))
    if len(out) < 600:
        raise RuntimeError("membership rows incomplete: {}".format(len(out)))
    return out, source


@dataclass
class Chart:
    symbol: str
    rows: list[dict]
    splits: list[tuple[date, float]]
    dividends: dict[date, float]
    source: str

    def __post_init__(self):
        self.index = {r["date"]: i for i, r in enumerate(self.rows)}
        self.dates = [r["date"] for r in self.rows]
        bars = []
        from dual_momentum.rules import PriceBar
        for r in self.rows:
            bars.append(PriceBar(
                date=r["date"].isoformat(),
                open=r["open"],
                high=r["high"],
                low=r["low"],
                close=r["close"],
                total_return_close=r["adjclose"],
                volume=r["volume"],
            ))
        self.atr_adj = wilder_atr_series(bars)

    def factor(self, d):
        f = 1.0
        for sd, ratio in self.splits:
            if sd > d:
                f *= ratio
        return f

    def exact(self, d):
        i = self.index.get(d)
        return None if i is None else self.rows[i]

    def before(self, d):
        lo = 0
        hi = len(self.rows)
        while lo < hi:
            mid = (lo + hi) // 2
            if self.rows[mid]["date"] <= d:
                lo = mid + 1
            else:
                hi = mid
        return None if lo == 0 else self.rows[lo - 1]

    def prior_index(self, d):
        i = self.index.get(d)
        if i is not None:
            return i - 1
        lo = 0
        hi = len(self.rows)
        while lo < hi:
            mid = (lo + hi) // 2
            if self.rows[mid]["date"] < d:
                lo = mid + 1
            else:
                hi = mid
        return lo - 1

    def native(self, r, field, scale_date=None):
        d = scale_date or r["date"]
        return float(r[field]) * self.factor(d)

    def native_atr_index(self, i, scale_date=None):
        if i < 0 or i >= len(self.atr_adj):
            return None
        v = self.atr_adj[i]
        if v is None:
            return None
        d = scale_date or self.rows[i]["date"]
        return float(v) * self.factor(d)

    def dividend_native(self, d):
        amt = self.dividends.get(d)
        return 0.0 if amt is None else float(amt) * self.factor(d)


def load_staged_prices():
    if not STAGED_PRICE_PATH.exists():
        return {}
    try:
        with gzip.open(STAGED_PRICE_PATH, "rt", encoding="utf-8") as fh:
            raw = json.load(fh)
        return raw.get("market") or {}
    except Exception:
        return {}


def staged_to_chart(symbol, raw):
    rows0 = raw.get("rows") or []
    if len(rows0) < 20:
        return None
    divmap = defaultdict(float)
    for dv in raw.get("dividends") or []:
        dd = pdate(dv.get("date"))
        if dd:
            divmap[dd] += float(dv.get("amount") or 0)
    rows = []
    tr = None
    prior_close = None
    for x in rows0:
        dd = pdate(x.get("date"))
        close = fnum(x.get("close"))
        op = fnum(x.get("open"))
        hi = fnum(x.get("high"))
        lo = fnum(x.get("low"))
        if not dd or None in (close, op, hi, lo) or min(close, op, hi, lo) <= 0:
            continue
        if tr is None:
            tr = close
        elif prior_close and prior_close > 0:
            tr *= (close + divmap.get(dd, 0.0)) / prior_close
        rows.append({
            "date": dd, "open": op, "high": hi, "low": lo, "close": close,
            "adjclose": tr, "volume": float(x.get("volume") or 0),
        })
        prior_close = close
    splits = []
    for sp in raw.get("splits") or []:
        dd = pdate(sp.get("date"))
        num = fnum(sp.get("numerator"))
        den = fnum(sp.get("denominator"))
        if dd and num and den and num > 0 and den > 0:
            splits.append((dd, num / den))
    return Chart(symbol, rows, sorted(splits), dict(divmap), "staged-yahoo-fallback")


def fetch_chart(symbol, start, end, staged=None):
    params = {
        "period1": epoch(start),
        "period2": epoch(end + timedelta(days=3)),
        "interval": "1d",
        "includePrePost": "false",
        "events": "div,splits",
        "includeAdjustedClose": "true",
    }
    last = None
    for host in YAHOO_HOSTS:
        try:
            js = request_json(host + symbol, params=params, attempts=4, headers={"User-Agent": "Mozilla/5.0 DualMomentumBacktest"})
            result = ((js.get("chart") or {}).get("result") or [])
            if not result:
                raise RuntimeError("no chart result")
            ch = result[0]
            gran = str((ch.get("meta") or {}).get("dataGranularity") or "")
            if gran and gran != "1d":
                raise RuntimeError("non-daily granularity {}".format(gran))
            ts = ch.get("timestamp") or []
            ind = ch.get("indicators") or {}
            q = (ind.get("quote") or [{}])[0]
            adj = ((ind.get("adjclose") or [{}])[0]).get("adjclose") or []
            rows = []
            for i, t in enumerate(ts):
                def at(name):
                    z = q.get(name) or []
                    return z[i] if i < len(z) else None
                op, hi, lo, cl = map(fnum, [at("open"), at("high"), at("low"), at("close")])
                ac = fnum(adj[i] if i < len(adj) else None)
                if None in (op, hi, lo, cl) or min(op, hi, lo, cl) <= 0:
                    continue
                if ac is None or ac <= 0:
                    ac = cl
                rows.append({
                    "date": datetime.fromtimestamp(float(t), tz=timezone.utc).date(),
                    "open": op, "high": hi, "low": lo, "close": cl, "adjclose": ac,
                    "volume": float(at("volume") or 0),
                })
            if len(rows) < 20:
                raise RuntimeError("too few rows")
            events = ch.get("events") or {}
            splits = []
            for x in (events.get("splits") or {}).values():
                dd = datetime.fromtimestamp(float(x.get("date") or 0), tz=timezone.utc).date()
                num = fnum(x.get("numerator"))
                den = fnum(x.get("denominator"))
                if num and den and num > 0 and den > 0:
                    splits.append((dd, num / den))
            dividends = defaultdict(float)
            for x in (events.get("dividends") or {}).values():
                dd = datetime.fromtimestamp(float(x.get("date") or 0), tz=timezone.utc).date()
                amt = fnum(x.get("amount"))
                if amt is not None:
                    dividends[dd] += amt
            return Chart(symbol, rows, sorted(splits), dict(dividends), "yahoo")
        except Exception as exc:
            last = exc
    if staged and symbol in staged:
        z = staged_to_chart(symbol, staged[symbol])
        if z:
            return z
    raise RuntimeError(str(last))


def signal(chart, d, security_id):
    i = chart.index.get(d)
    if i is None or i < 252 or i < 62:
        return None
    if i >= len(chart.atr_adj) or chart.atr_adj[i] is None:
        return None
    a = chart.rows
    end = a[i]["adjclose"]
    vals = []
    for tau in (63, 126, 252):
        den = a[i - tau]["adjclose"]
        if den <= 0 or end <= 0:
            return None
        vals.append(end / den - 1.0)
    score = sum(vals) / 3.0
    adv = sum(float(x["close"]) * float(x.get("volume") or 0) for x in a[i - 62:i + 1]) / 63.0
    close = float(a[i]["close"])
    atr_adj = float(chart.atr_adj[i])
    if close <= 0 or atr_adj <= 0:
        return None
    return {
        "symbol": chart.symbol,
        "security_id": security_id,
        "score": score,
        "r63": vals[0], "r126": vals[1], "r252": vals[2],
        "adv63": adv,
        "atr_pct": atr_adj / close,
        "atr_native": atr_adj * chart.factor(d),
        "signal_price": close * chart.factor(d),
    }


def load_valuein():
    if not STAGED_FUND_PATH.exists():
        return {}
    try:
        with gzip.open(STAGED_FUND_PATH, "rt", encoding="utf-8") as fh:
            raw = json.load(fh)
        return raw.get("facts") or {}
    except Exception:
        return {}


def duration(start, end):
    a = pdate(start)
    b = pdate(end)
    return None if not a or not b else (b - a).days


def quarter_series_valuein(rows, concept, asof):
    eligible = []
    for r in rows:
        if r.get("standard_concept") != concept:
            continue
        fd = pdate(r.get("filing_date"))
        if not fd or fd >= asof:
            continue
        if str(r.get("form_type") or "") not in FIN_FORMS:
            continue
        eligible.append(r)
    keep = {}
    for r in eligible:
        pe = str(r.get("period_end") or "")
        if not pe:
            continue
        span = fnum(r.get("period_span_days"))
        raw = fnum(r.get("numeric_value"))
        derived = fnum(r.get("derived_quarterly_value"))
        val = None
        quality = 0
        form = str(r.get("form_type") or "")
        if span is not None and 65 <= span <= 120 and raw is not None:
            val, quality = raw, 4
        elif derived is not None:
            val, quality = derived, 3
        if val is None:
            continue
        key = (str(r.get("filing_date") or ""), str(r.get("accepted_at") or ""), quality)
        if pe not in keep or key > keep[pe][0]:
            keep[pe] = (key, val)
    annual = [r for r in eligible if str(r.get("form_type") or "") in ANNUAL_FORMS and 300 <= (fnum(r.get("period_span_days")) or 0) <= 430]
    for ar in annual:
        pe = str(ar.get("period_end") or "")
        if not pe or pe in keep:
            continue
        aval = fnum(ar.get("numeric_value"))
        if aval is None:
            continue
        cands = []
        for y in eligible:
            if y.get("period_start") != ar.get("period_start"):
                continue
            sp = fnum(y.get("period_span_days"))
            yval = fnum(y.get("numeric_value"))
            gap = duration(y.get("period_end"), ar.get("period_end"))
            if sp is None or yval is None or gap is None:
                continue
            if 240 <= sp <= 310 and 65 <= gap <= 120 and str(y.get("filing_date") or "") <= str(ar.get("filing_date") or ""):
                cands.append(y)
        if cands:
            y = max(cands, key=lambda z: (str(z.get("filing_date") or ""), str(z.get("period_end") or "")))
            val = aval - float(y.get("numeric_value"))
            keep[pe] = ((str(ar.get("filing_date") or ""), str(ar.get("accepted_at") or ""), 2), val)
    return [(pe, x[1]) for pe, x in sorted(keep.items())]


def fund_from_valuein(valuein, symbol, asof, exempt):
    rows = valuein.get(symbol) or []
    rev = quarter_series_valuein(rows, "TotalRevenue", asof)
    gp = quarter_series_valuein(rows, "GrossProfit", asof)
    rv = [v for _, v in rev[-8:]]
    gp_map = dict(gp)
    latest_ends = [pe for pe, _ in rev[-4:]]
    gv = [gp_map.get(pe) for pe in latest_ends]
    gv_clean = None if len(latest_ends) < 4 or any(v is None for v in gv) else [float(v) for v in gv]
    return evaluate_fundamentals(rv if len(rv) >= 8 else None, gv_clean, gross_margin_exempt=exempt)


def sec_entries(fact):
    if not fact:
        return []
    units = fact.get("units") or {}
    return list(units.get("USD") or [])


def sec_fact(facts, tags):
    us = (facts.get("facts") or {}).get("us-gaap") or {}
    for tag in tags:
        if tag in us:
            return us[tag]
    return None


def quarter_series_sec(fact, asof):
    rows = []
    for r in sec_entries(fact):
        if r.get("form") not in FIN_FORMS:
            continue
        fd = pdate(r.get("filed"))
        if not fd or fd >= asof:
            continue
        val = fnum(r.get("val"))
        if val is None:
            continue
        rows.append(r)
    keep = {}
    for r in rows:
        pe = str(r.get("end") or "")
        span = duration(r.get("start"), r.get("end"))
        if not pe or span is None or not 65 <= span <= 120:
            continue
        k = str(r.get("filed") or "")
        if pe not in keep or k > keep[pe][0]:
            keep[pe] = (k, float(r.get("val")))
    annual = [r for r in rows if r.get("form") in ANNUAL_FORMS and 300 <= (duration(r.get("start"), r.get("end")) or 0) <= 430]
    for ar in annual:
        pe = str(ar.get("end") or "")
        if not pe or pe in keep:
            continue
        cands = []
        for y in rows:
            if y.get("start") != ar.get("start"):
                continue
            sp = duration(y.get("start"), y.get("end"))
            gap = duration(y.get("end"), ar.get("end"))
            if sp is not None and gap is not None and 240 <= sp <= 310 and 65 <= gap <= 120 and str(y.get("filed") or "") <= str(ar.get("filed") or ""):
                cands.append(y)
        if cands:
            y = max(cands, key=lambda z: (str(z.get("filed") or ""), str(z.get("end") or "")))
            keep[pe] = (str(ar.get("filed") or ""), float(ar.get("val")) - float(y.get("val")))
    return [(pe, x[1]) for pe, x in sorted(keep.items())]


def fund_from_sec(facts, asof, exempt):
    rev_choices = []
    for tag in REVENUE_TAGS:
        qs = quarter_series_sec(sec_fact(facts, (tag,)), asof)
        if qs:
            rev_choices.append(qs)
    rev = max(rev_choices, key=lambda q: (q[-1][0], len(q))) if rev_choices else []
    gp = quarter_series_sec(sec_fact(facts, GROSS_TAGS), asof)
    rv = [v for _, v in rev[-8:]]
    gp_map = dict(gp)
    latest_ends = [pe for pe, _ in rev[-4:]]
    gv = [gp_map.get(pe) for pe in latest_ends]
    gv_clean = None if len(latest_ends) < 4 or any(v is None for v in gv) else [float(v) for v in gv]
    return evaluate_fundamentals(rv if len(rv) >= 8 else None, gv_clean, gross_margin_exempt=exempt)


class Limiter:
    def __init__(self, rps):
        self.dt = 1.0 / float(rps)
        self.lock = threading.Lock()
        self.next = 0.0

    def wait(self):
        with self.lock:
            now = time.monotonic()
            if now < self.next:
                time.sleep(self.next - now)
            self.next = time.monotonic() + self.dt


def fetch_sec_companyfacts(cik, limiter):
    limiter.wait()
    return request_json(SEC_COMPANYFACTS.format(cik), attempts=4, headers={"User-Agent": UA})


@dataclass
class Position:
    symbol: str
    shares: int
    avg_cost: float
    peak: float
    stop: float
    opened: date
    last_verified: str = "UNKNOWN"


@dataclass
class Order:
    symbol: str
    side: str
    shares: int
    reason: str
    rank: int
    kind: str
    created: date
    earliest: date


def target_qty(target_value, signal_price):
    if target_value <= 0 or signal_price <= 0:
        return 0
    q = int(math.floor(target_value / signal_price))
    while q > 0:
        modeled = q * signal_price * (1.0 + MARKET_DRAG) + estimated_commission(q)
        if modeled <= target_value + 1e-9:
            return q
        q -= 1
    return 0


def benchmark_stats(chart, start, end):
    rows = [r for r in chart.rows if start <= r["date"] <= end]
    if not rows:
        raise RuntimeError("benchmark has no rows")
    first = float(rows[0]["adjclose"])
    last = float(rows[-1]["adjclose"])
    years = (rows[-1]["date"] - rows[0]["date"]).days / 365.25
    total = last / first - 1.0
    cagr = (last / first) ** (1.0 / years) - 1.0
    peak = 0.0
    mdd = 0.0
    yearly = {}
    byyear = defaultdict(list)
    for r in rows:
        v = float(r["adjclose"])
        peak = max(peak, v)
        if peak:
            mdd = min(mdd, v / peak - 1.0)
        byyear[r["date"].year].append(v)
    prev = first
    for y in sorted(byyear):
        yend = byyear[y][-1]
        yearly[str(y)] = yend / prev - 1.0
        prev = yend
    return {
        "start_date": rows[0]["date"].isoformat(),
        "end_date": rows[-1]["date"].isoformat(),
        "end_value": STARTING_CASH * last / first,
        "total_return": total,
        "cagr": cagr,
        "max_drawdown": mdd,
        "annual": yearly,
    }


def main():
    print("DM5_STAGE membership", flush=True)
    intervals, membership_source = load_membership()
    overlapping = [x for x in intervals if x.overlaps(START, END)]
    symbols = sorted({x.symbol for x in overlapping})
    by_symbol_intervals = defaultdict(list)
    for x in intervals:
        by_symbol_intervals[x.symbol].append(x)
    for s in by_symbol_intervals:
        by_symbol_intervals[s].sort(key=lambda x: x.added)

    staged = load_staged_prices()
    print("DM5_STAGE prices symbols={}".format(len(symbols)), flush=True)
    charts = {}
    price_failed = {}

    def price_task(sym):
        try:
            return sym, fetch_chart(sym, PRICE_START, END + timedelta(days=3), staged=staged), None
        except Exception as exc:
            return sym, None, "{}: {}".format(type(exc).__name__, exc)

    with ThreadPoolExecutor(max_workers=6) as pool:
        futs = [pool.submit(price_task, s) for s in symbols]
        for n, fut in enumerate(as_completed(futs), 1):
            sym, ch, err = fut.result()
            if ch:
                charts[sym] = ch
            else:
                price_failed[sym] = err
            if n % 75 == 0 or n == len(futs):
                print("DM5_PRICE {}/{} ok={} fail={}".format(n, len(futs), len(charts), len(price_failed)), flush=True)

    spy = fetch_chart("SPY", SPY_START, END + timedelta(days=3), staged=None)
    try:
        bench = fetch_chart("^SP500TR", START - timedelta(days=10), END + timedelta(days=3), staged=None)
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
    if not month_ends or month_ends[-1] != END:
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
    print("DM5_STAGE momentum months={}".format(len(month_ends)), flush=True)
    for mnum, d in enumerate(month_ends, 1):
        active = active_intervals(d)
        sigs = []
        for sym, mem in active.items():
            ch = charts.get(sym)
            if not ch:
                continue
            z = signal(ch, d, "{}:{}".format(mem.cik or sym, sym))
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
            "positive_count": len(positive),
        }
        print("DM5_MONTH {} {}/{} regime={} active={} signals={} positive={}".format(
            d.isoformat(), mnum, len(month_ends), reg, len(active), len(sigs), len(positive)
        ), flush=True)

    valuein = load_valuein()
    needs_sec = set()
    for d, snap in snapshots.items():
        if snap["regime"] != "BULL":
            continue
        for sym in snap["top35"]:
            mem = snap["active"].get(sym)
            exempt = bool(mem and mem.sector in GM_EXEMPT)
            ck = fund_from_valuein(valuein, sym, d, exempt)
            if ck.status == FundamentalStatus.REVIEW:
                needs_sec.add(sym)

    cik_by_symbol = {}
    for sym in top35_union:
        rows = by_symbol_intervals.get(sym) or []
        cik = next((x.cik for x in reversed(rows) if x.cik), "")
        if cik:
            cik_by_symbol[sym] = cik

    print("DM5_STAGE fundamentals top35_union={} sec_fallback_candidates={}".format(len(top35_union), len(needs_sec)), flush=True)
    secfacts = {}
    sec_failed = {}
    limiter = Limiter(6.0)

    def sec_task(sym):
        cik = cik_by_symbol.get(sym)
        if not cik:
            return sym, None, "CIK missing"
        try:
            return sym, fetch_sec_companyfacts(cik, limiter), None
        except Exception as exc:
            return sym, None, "{}: {}".format(type(exc).__name__, exc)

    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = [pool.submit(sec_task, s) for s in sorted(needs_sec)]
        for n, fut in enumerate(as_completed(futs), 1):
            sym, fact, err = fut.result()
            if fact:
                secfacts[sym] = fact
            else:
                sec_failed[sym] = err
            if n % 40 == 0 or n == len(futs):
                print("DM5_SEC {}/{} ok={} fail={}".format(n, len(futs), len(secfacts), len(sec_failed)), flush=True)

    fund_cache = {}
    fund_counts = defaultdict(int)

    def fund_check(sym, d, sector):
        key = (sym, d)
        if key in fund_cache:
            return fund_cache[key]
        exempt = sector in GM_EXEMPT
        ck = fund_from_valuein(valuein, sym, d, exempt)
        source = "valuein"
        if ck.status == FundamentalStatus.REVIEW and sym in secfacts:
            ck2 = fund_from_sec(secfacts[sym], d, exempt)
            if ck2.status != FundamentalStatus.REVIEW or ck.status == FundamentalStatus.REVIEW:
                ck = ck2
                source = "sec"
        out = {
            "status": ck.status.value,
            "revenue_growth": ck.revenue_growth_ttm,
            "gross_margin": ck.gross_margin_ttm,
            "exempt": ck.gross_margin_exempt,
            "reason": ck.reason,
            "source": source,
        }
        fund_cache[key] = out
        fund_counts[out["status"]] += 1
        return out

    positions = {}
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

    removal_events = []
    for x in intervals:
        if x.removed and START <= x.removed <= END:
            removal_events.append((x.removed, x.symbol))
    removal_events.sort()
    removal_i = 0

    def native_open(ch, d):
        r = ch.exact(d)
        return None if r is None else ch.native(r, "open", d)

    def native_close(ch, d):
        r = ch.exact(d)
        return None if r is None else ch.native(r, "close", d)

    def commission(q):
        return estimated_commission(int(q))

    def queue_exit(sym, d, reason, kind, rank=9999):
        nonlocal orders
        orders = [o for o in orders if not (o.symbol == sym and o.side == "BUY")]
        if any(o.symbol == sym and o.side == "SELL" and o.kind in ("STOP", "RULE", "BEAR", "MEMBERSHIP") for o in orders):
            return
        p = positions.get(sym)
        if not p:
            return
        orders.append(Order(sym, "SELL", int(p.shares), reason, rank, kind, d, d))

    def execute_orders(day):
        nonlocal cash, orders, total_costs, traded_notional
        if not orders:
            return
        sell_orders = sorted([o for o in orders if o.side == "SELL"], key=lambda o: (o.rank, o.symbol))
        buy_orders = sorted([o for o in orders if o.side == "BUY"], key=lambda o: (o.rank, o.symbol))
        remaining = []
        for o in sell_orders:
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
            fee = commission(q)
            cash += q * fill - fee
            drag = q * (op - fill)
            total_costs += fee + drag
            traded_notional += q * op
            pnl = q * (fill - p.avg_cost) - fee
            trades.append({
                "date": day.isoformat(), "symbol": o.symbol, "side": "SELL", "shares": q,
                "fill": fill, "reference_open": op, "fees": fee, "reason": o.reason, "kind": o.kind, "pnl": pnl,
            })
            p.shares -= q
            if p.shares <= 0:
                positions.pop(o.symbol, None)
        for o in buy_orders:
            if day < o.earliest:
                remaining.append(o)
                continue
            ch = charts.get(o.symbol)
            op = native_open(ch, day) if ch else None
            if op is None or op <= 0:
                remaining.append(o)
                continue
            desired = int(o.shares)
            if desired <= 0:
                continue
            fill = op * (1.0 + MARKET_DRAG)
            q = desired
            while q > 0 and q * fill + commission(q) > cash + 1e-9:
                q -= 1
            if q <= 0:
                continue
            fee = commission(q)
            if o.symbol in positions:
                p = positions[o.symbol]
                newq = p.shares + q
                p.avg_cost = (p.avg_cost * p.shares + fill * q) / newq
                p.shares = newq
            else:
                pi = ch.prior_index(day)
                atr = ch.native_atr_index(pi, ch.rows[pi]["date"]) if pi >= 0 else None
                if atr is None or atr <= 0:
                    unresolved_orders.append({"date": day.isoformat(), "symbol": o.symbol, "reason": "entry ATR unavailable"})
                    continue
                positions[o.symbol] = Position(o.symbol, q, fill, fill, fill - 3.0 * atr, day, "UNKNOWN")
            cash -= q * fill + fee
            drag = q * (fill - op)
            total_costs += fee + drag
            traded_notional += q * op
            trades.append({
                "date": day.isoformat(), "symbol": o.symbol, "side": "BUY", "shares": q,
                "fill": fill, "reference_open": op, "fees": fee, "reason": o.reason, "kind": o.kind,
            })
            if q < desired:
                unresolved_orders.append({"date": day.isoformat(), "symbol": o.symbol, "reason": "funding clip {}->{}".format(desired, q)})
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
        # Monthly orders supersede stale unfilled monthly orders, but never protective/rule exits.
        orders = [o for o in orders if o.kind in ("STOP", "MEMBERSHIP")]
        if snap["regime"] == "BEAR":
            for sym in list(positions):
                queue_exit(sym, day, "SPY total return <= EMA200", "BEAR", 0)
            for o in orders:
                if o.earliest <= day:
                    o.earliest = nextday
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
            if rank is None or rank > RETENTION_CUTOFF:
                exiting.add(sym)
                queue_exit(sym, day, "Raw momentum rank outside Top 35", "RULE", rank or 9999)
                continue
            mem = snap["active"].get(sym)
            if mem is None:
                exiting.add(sym)
                queue_exit(sym, day, "Not in point-in-time S&P 500 membership", "RULE", rank or 9999)
                continue
            fc = fund_check(sym, day, mem.sector)
            if fc["status"] == "FAIL":
                p.last_verified = "FAIL"
                exiting.add(sym)
                queue_exit(sym, day, "Fundamental gate failed", "RULE", rank)
                continue
            if fc["status"] == "PASS":
                p.last_verified = "PASS"
            else:
                review_retained.add(sym)
            retained.append(sym)

        entries = []
        for sym in snap["top35"][:ENTRY_CUTOFF]:
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
            return
        inv = {s["symbol"]: 1.0 / s["atr_pct"] for s in sigs if s["atr_pct"] > 0}
        denom = sum(inv.values())
        exposure = n / 20.0
        weights = {s: exposure * v / denom for s, v in inv.items()} if denom > 0 else {}

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
            tq = target_qty(target_value, sig["signal_price"])
            cq = positions[sym].shares if sym in positions else 0
            rank = snap["ranks"].get(sym) or 9999
            if sym in review_retained and tq > cq:
                tq = cq
            if tq < cq:
                orders.append(Order(sym, "SELL", cq - tq, "Monthly resize to target", rank, "TRIM", day, nextday))
            elif tq > cq:
                orders.append(Order(sym, "BUY", tq - cq, "Monthly resize/new entry", rank, "BUY", day, nextday))

        for o in orders:
            if o.created == day and o.earliest <= day:
                o.earliest = nextday

    calendar = [d for d in spy_test_dates if START <= d <= END]
    month_set = set(month_ends)
    print("DM5_STAGE simulation sessions={}".format(len(calendar)), flush=True)
    for session_n, day in enumerate(calendar, 1):
        # Apply split events before the open on their effective date.
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

        # Dividend entitlement belongs to shares held before today's opening trades.
        for sym, p in list(positions.items()):
            ch = charts.get(sym)
            if ch:
                dv = ch.dividend_native(day)
                if dv:
                    cash += p.shares * dv

        # Membership removals are effective-dated forced exits.
        while removal_i < len(removal_events) and removal_events[removal_i][0] <= day:
            rd, sym = removal_events[removal_i]
            key = (rd, sym)
            if key not in processed_removals and sym in positions:
                queue_exit(sym, day, "Effective S&P 500 removal {}".format(rd.isoformat()), "MEMBERSHIP", 0)
                for o in orders:
                    if o.symbol == sym and o.kind == "MEMBERSHIP":
                        o.earliest = day
                processed_removals.add(key)
            removal_i += 1

        execute_orders(day)

        # Close-triggered stops. Compare close to prior stop before ratcheting.
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

        if session_n % 125 == 0 or session_n == len(calendar):
            print("DM5_SIM {}/{} day={} nav={:.2f} cash={:.2f} holdings={} trades={}".format(
                session_n, len(calendar), day.isoformat(), nav, cash, len(positions), len(trades)
            ), flush=True)

    # Any protective/rule orders still unresolved by end are material.
    for o in orders:
        unresolved_orders.append({
            "date": END.isoformat(), "symbol": o.symbol,
            "reason": "unexecuted {} order: {}".format(o.kind, o.reason),
        })

    if not curve:
        raise RuntimeError("empty equity curve")
    end_value = curve[-1]["equity"]
    total_return = end_value / STARTING_CASH - 1.0
    years = (curve[-1]["date"] - curve[0]["date"]).days / 365.25
    cagr = (end_value / STARTING_CASH) ** (1.0 / years) - 1.0

    peak = 0.0
    max_dd = 0.0
    byyear = defaultdict(list)
    cash_weights = []
    for r in curve:
        peak = max(peak, r["equity"])
        if peak > 0:
            max_dd = min(max_dd, r["equity"] / peak - 1.0)
        byyear[r["date"].year].append(r)
        if r["equity"] > 0:
            cash_weights.append(r["cash"] / r["equity"])
    annual = {}
    prev = STARTING_CASH
    for y in sorted(byyear):
        val = byyear[y][-1]["equity"]
        annual[str(y)] = val / prev - 1.0
        prev = val

    benchmark = benchmark_stats(bench, START, END)
    avg_equity = statistics.mean(r["equity"] for r in curve)
    annual_turnover = (traded_notional / avg_equity / years) if avg_equity > 0 and years > 0 else None
    coverage = member_month_signal / member_month_total if member_month_total else 0.0

    result = {
        "period": {"start": START.isoformat(), "end": END.isoformat(), "years": years},
        "starting_cash": STARTING_CASH,
        "strategy": {
            "end_value": end_value,
            "absolute_profit": end_value - STARTING_CASH,
            "total_return": total_return,
            "cagr": cagr,
            "max_drawdown": max_dd,
            "annual": annual,
            "average_cash_weight": statistics.mean(cash_weights) if cash_weights else None,
            "annualized_turnover": annual_turnover,
            "transaction_costs": total_costs,
            "trade_count": len(trades),
            "ending_cash": cash,
            "ending_holdings": len(positions),
        },
        "benchmark": {
            "name": benchmark_name,
            **benchmark,
            "absolute_profit": benchmark["end_value"] - STARTING_CASH,
        },
        "coverage": {
            "membership_source": membership_source,
            "historical_symbols": len(symbols),
            "price_symbols_ok": len(charts),
            "price_symbols_failed": len(price_failed),
            "price_symbol_coverage": len(charts) / len(symbols) if symbols else 0.0,
            "member_month_signal_coverage": coverage,
            "top35_union": len(top35_union),
            "valuein_symbols": len(valuein),
            "sec_fallback_requested": len(needs_sec),
            "sec_fallback_ok": len(secfacts),
            "sec_fallback_failed": len(sec_failed),
            "fundamental_status_counts": dict(fund_counts),
            "unresolved_order_count": len(unresolved_orders),
            "split_fraction_events": len(split_fraction_events),
            "missing_price_symbols": sorted(price_failed),
            "sec_failed_symbols": sorted(sec_failed),
        },
        "integrity": {
            "future_data_rule": "fundamental filing date must be strictly before decision date",
            "membership": "effective date ranges",
            "momentum": "63/126/252 session adjusted-close total return",
            "regime": "SPY adjusted-close EMA200 seeded from 2015 daily history",
            "execution": "next executable daily open, 7 bps adverse price drag plus commission",
            "whole_shares": True,
            "cash_yield": 0.0,
            "notes": [
                "Yahoo OHLC is split-adjusted; contemporaneous execution-price scale is reconstructed from split events.",
                "Valuein point-in-time facts are supplemented with SEC companyfacts when the offline sample is insufficient.",
                "Missing historical price symbols are never replaced with present-day prices.",
                "This is retrospective public-data research, not CRSP/Norgate institutional-grade replay.",
            ],
        },
        "trades": trades,
        "unresolved_orders": unresolved_orders,
    }

    out = ROOT / "backtests" / "results" / "dual_momentum_5y_2021_2026.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, default=str))
    compact = {
        "period": result["period"],
        "strategy": result["strategy"],
        "benchmark": result["benchmark"],
        "coverage": result["coverage"],
    }
    print("DM5_RESULT_JSON=" + json.dumps(compact, separators=(",", ":"), default=str), flush=True)


if __name__ == "__main__":
    main()
