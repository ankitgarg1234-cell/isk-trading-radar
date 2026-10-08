#!/usr/bin/env python3
from __future__ import annotations

import ast
import bisect
import json
import math
import statistics
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from io import StringIO
from pathlib import Path

import pandas as pd
import requests
from lxml import html as lhtml

ROOT = Path(__file__).resolve().parents[1]
STARTING = 10000.0
START = date(2022, 1, 1)
END = date(2026, 9, 30)
DATA_START = START - timedelta(days=400)
DATA_END = date(2026, 10, 6)

SLIPPAGE_BPS = 5.0
EXTRA_BPS = 2.0
TOTAL_BPS = SLIPPAGE_BPS + EXTRA_BPS
ROT_MAX = 15
LEAD_MAX = 5
ROT_BUDGET = 0.75
LEAD_BUDGET = 0.25

WIKI = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/"
SEC_TICKERS = "https://raw.githubusercontent.com/Ancalagan/sec-data/main/company_tickers.json"
SEC_FACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

OUT_JSON = ROOT / "backtests/results/walkforward_2022_2026.json"
OUT_MD = ROOT / "backtests/results/walkforward_2022_2026.md"

def sf(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None

def norm(v):
    s = str(v or "").strip().upper()
    return "" if not s or s == "NAN" else s.replace(".", "-")

class Cache:
    def __init__(self, p):
        self.p = Path(p)
        self.p.mkdir(parents=True, exist_ok=True)
    def _p(self, g, k):
        d = self.p / g
        d.mkdir(parents=True, exist_ok=True)
        return d / (k.replace("/", "_").replace("^", "IDX_") + ".json")
    def get(self, g, k):
        p = self._p(g, k)
        try:
            return json.loads(p.read_text()) if p.exists() else None
        except Exception:
            return None
    def put(self, g, k, v):
        self._p(g, k).write_text(json.dumps(v))

class Limiter:
    def __init__(self, rps):
        self.dt = 1.0 / rps
        self.lock = threading.Lock()
        self.next = 0.0
    def wait(self):
        with self.lock:
            now = time.monotonic()
            if now < self.next:
                time.sleep(self.next - now)
            self.next = time.monotonic() + self.dt

def jget(s, url, params=None, lim=None):
    err = None
    for i in range(6):
        try:
            if lim:
                lim.wait()
            r = s.get(url, params=params, timeout=40)
            if r.status_code in (429, 500, 502, 503, 504):
                raise RuntimeError(str(r.status_code))
            r.raise_for_status()
            return r.json()
        except Exception as e:
            err = e
            time.sleep(min(12, 1.6 ** i))
    raise RuntimeError(str(err))

def flat(df):
    z = df.copy()
    z.columns = [
        " ".join(dict.fromkeys(str(x) for x in c if str(x) != "nan"))
        if isinstance(c, tuple) else str(c)
        for c in z.columns
    ]
    return z

def col(cols, *parts):
    for c in cols:
        q = c.lower()
        if all(p.lower() in q for p in parts):
            return c
    return None

def sp500_history(s):
    html = s.get(WIKI, headers={"User-Agent": "Mozilla/5.0"}, timeout=40).text
    tabs = [flat(x) for x in pd.read_html(StringIO(html))]
    cur = next(x for x in tabs if col(list(x.columns), "symbol") and col(list(x.columns), "gics", "sector"))
    sc = col(list(cur.columns), "symbol")
    gc = col(list(cur.columns), "gics", "sector")
    current, sectors = set(), {}
    for _, r in cur.iterrows():
        t = norm(r.get(sc))
        if t:
            current.add(t)
            sectors[t] = str(r.get(gc) or "")
    changes_url = "https://raw.githubusercontent.com/chinobing/historical_sp500_constituents/main/sp500_changes_since_1996.csv"
    changes_text = s.get(changes_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=40).text
    ch = pd.read_csv(StringIO(changes_text))
    changes = []
    for _, r in ch.iterrows():
        try:
            d = pd.to_datetime(r.get("date")).date()
        except Exception:
            continue
        def tickers(v):
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return []
            sv = str(v).strip()
            if not sv or sv.lower() == "nan":
                return []
            try:
                x = ast.literal_eval(sv)
                if isinstance(x, str):
                    x = [x]
                return [norm(z) for z in x if norm(z)]
            except Exception:
                return [norm(sv)] if norm(sv) else []
        adds = tickers(r.get("added_tickers"))
        rems = tickers(r.get("removed_tickers"))
        n = max(len(adds), len(rems), 1)
        for i in range(n):
            a = adds[i] if i < len(adds) else ""
            rem = rems[i] if i < len(rems) else ""
            if a or rem:
                changes.append({"date": d.isoformat(), "added": a, "removed": rem})
    changes.sort(key=lambda x: x["date"])
    return current, sectors, changes


def members_at(current, changes, when):
    m = set(current)
    for x in reversed(changes):
        d = date.fromisoformat(x["date"])
        if d <= when:
            continue
        if x["added"]:
            m.discard(x["added"])
        if x["removed"]:
            m.add(x["removed"])
    return m

def epoch(d):
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())

def yahoo(s, cache, sym, start, end):
    key = sym + "_" + start.isoformat() + "_" + end.isoformat()
    c = cache.get("yahoo", key)
    if c is not None:
        return None if c.get("missing") else c
    try:
        data = jget(
            s, YAHOO + sym,
            {"period1": epoch(start), "period2": epoch(end + timedelta(days=3)),
             "interval": "1d", "events": "div,splits"}
        )
        r = ((data.get("chart") or {}).get("result") or [None])[0]
        if not r:
            raise RuntimeError("no chart")
        ts = r.get("timestamp") or []
        q = ((r.get("indicators") or {}).get("quote") or [{}])[0]
        rows = []
        for i, t in enumerate(ts):
            def a(n):
                x = q.get(n) or []
                return x[i] if i < len(x) else None
            if a("close") is None:
                continue
            rows.append({
                "date": datetime.fromtimestamp(t, tz=timezone.utc).date().isoformat(),
                "open": a("open"), "high": a("high"), "low": a("low"),
                "close": a("close"), "volume": a("volume") or 0
            })
        ev = r.get("events") or {}
        div = []
        for x in (ev.get("dividends") or {}).values():
            try:
                div.append({
                    "date": datetime.fromtimestamp(float(x["date"]), tz=timezone.utc).date().isoformat(),
                    "amount": float(x["amount"])
                })
            except Exception:
                pass
        out = {"rows": rows, "dividends": sorted(div, key=lambda x: x["date"])}
        cache.put("yahoo", key, out)
        return out
    except Exception:
        cache.put("yahoo", key, {"missing": True})
        return None

def prepare_market(data):
    if not data or not data.get("rows"):
        return None
    rows = []
    divmap = defaultdict(float)
    for x in data.get("dividends") or []:
        divmap[x["date"]] += sf(x.get("amount")) or 0.0
    tr = 1.0
    prev = None
    atr = None
    trs = []
    for raw in data["rows"]:
        c = sf(raw.get("close"))
        o = sf(raw.get("open"))
        h = sf(raw.get("high"))
        l = sf(raw.get("low"))
        if c is None:
            continue
        if prev is not None and prev > 0:
            tr *= (c + divmap.get(raw["date"], 0.0)) / prev
        if h is not None and l is not None:
            if prev is None:
                true_range = h - l
            else:
                true_range = max(h - l, abs(h - prev), abs(l - prev))
            trs.append(true_range)
            if atr is None and len(trs) >= 14:
                atr = statistics.mean(trs[-14:])
            elif atr is not None:
                atr = (13.0 * atr + true_range) / 14.0
        rows.append({
            "date": raw["date"], "open": o, "high": h, "low": l, "close": c,
            "volume": sf(raw.get("volume")) or 0.0, "tr": tr, "atr": atr,
            "dividend": divmap.get(raw["date"], 0.0)
        })
        prev = c
    # True continuous EMA200, seeded once with the arithmetic mean of the
    # first 200 sessions.  The old last-200-window re-seeding was incorrect.
    if len(rows) >= 200:
        ema = statistics.mean(r["tr"] for r in rows[:200])
        rows[199]["ema200_tr"] = ema
        alpha = 2.0 / 201.0
        for j in range(200, len(rows)):
            ema = alpha * rows[j]["tr"] + (1.0 - alpha) * ema
            rows[j]["ema200_tr"] = ema
    dates = [r["date"] for r in rows]
    return {"rows": rows, "dates": dates}

def idx_on_or_before(data, d):
    i = bisect.bisect_right(data["dates"], d.isoformat()) - 1
    return i if i >= 0 else None

def idx_on_or_after(data, d):
    i = bisect.bisect_left(data["dates"], d.isoformat())
    return i if i < len(data["rows"]) else None

def ticker_map(s, cache, lim):
    c = cache.get("sec", "tickers")
    if c:
        return c
    raw = jget(s, SEC_TICKERS, lim=lim)
    out = {}
    if isinstance(raw, dict) and isinstance(raw.get("data"), list):
        fields = list(raw.get("fields") or [])
        for row in raw["data"]:
            x = dict(zip(fields, row))
            t = norm(x.get("ticker"))
            cik = x.get("cik")
            if t and cik is not None:
                out[t] = f"{int(cik):010d}"
    else:
        for x in (raw.values() if isinstance(raw, dict) else raw):
            if not isinstance(x, dict):
                continue
            t = norm(x.get("ticker"))
            cik = x.get("cik_str", x.get("cik"))
            if t and cik is not None:
                out[t] = f"{int(cik):010d}"
    cache.put("sec", "tickers", out)
    return out

def facts(s, cache, lim, sym, cik):
    c = cache.get("facts", sym + "_" + cik)
    if c is not None:
        return None if c.get("missing") else c
    try:
        x = jget(s, SEC_FACTS.format(cik=cik), lim=lim)
        cache.put("facts", sym + "_" + cik, x)
        return x
    except Exception:
        cache.put("facts", sym + "_" + cik, {"missing": True})
        return None

def fact_obj(f, ns, tags):
    z = (f.get("facts") or {}).get(ns) or {}
    for t in tags:
        if t in z:
            return z[t]
    return None

def entries(o, units=("USD",)):
    if not o:
        return []
    u = o.get("units") or {}
    for x in units:
        if x in u:
            return list(u[x] or [])
    return list(next(iter(u.values()), []) or [])

def duration_days(r):
    try:
        return (date.fromisoformat(r["end"]) - date.fromisoformat(r["start"])).days
    except Exception:
        return None

def annual_records(o, units=("USD",)):
    # Preserve EVERY historical filing, including amendments.  Deduplicating
    # by fiscal year *before* the decision-date cut-off silently replaces a
    # then-available filing with a future amendment, causing false UNKNOWN.
    out = []
    for r in entries(o, units):
        if r.get("form") not in ("10-K", "10-K/A", "20-F", "20-F/A"):
            continue
        n = duration_days(r)
        if n is not None and not 300 <= n <= 430:
            continue
        if not r.get("end") or not r.get("filed") or r.get("val") is None:
            continue
        out.append(r)
    return sorted(out, key=lambda x: (str(x["end"]), str(x.get("filed", "")), str(x.get("accn", ""))))

def instant_records(o, units=("shares",)):
    out = []
    for r in entries(o, units):
        if r.get("form") not in ("10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "20-F/A", "8-K"):
            continue
        if not r.get("end") or not r.get("filed") or r.get("val") is None:
            continue
        out.append(r)
    out.sort(key=lambda x: (str(x.get("end")), str(x.get("filed"))))
    return out

def preprocess_facts(f):
    rev = annual_records(fact_obj(f, "us-gaap", (
        "RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"
    )))
    gp = annual_records(fact_obj(f, "us-gaap", ("GrossProfit",)))
    shares = instant_records(fact_obj(f, "dei", ("EntityCommonStockSharesOutstanding",)), ("shares",))
    if not shares:
        shares = instant_records(fact_obj(f, "us-gaap", (
            "WeightedAverageNumberOfDilutedSharesOutstanding",
            "WeightedAverageNumberOfSharesOutstandingBasic"
        )), ("shares",))
    return {"rev": rev, "gp": gp, "shares": shares}

def asof_records(rs, d):
    """Latest actually available filing for each fiscal period at decision date."""
    cutoff = d.isoformat()
    latest = {}
    for r in rs:
        filed = str(r.get("filed", ""))[:10]
        end = str(r.get("end", ""))[:10]
        if not filed or not end or filed > cutoff or end > cutoff:
            continue
        old = latest.get(end)
        if old is None or (filed, str(r.get("accn", ""))) > (
            str(old.get("filed", ""))[:10], str(old.get("accn", ""))
        ):
            latest[end] = r
    return [latest[end] for end in sorted(latest)]

def fundamental_pass(pit, d, sector):
    rev = asof_records(pit.get("rev") or [], d)
    if len(rev) < 2:
        return None
    r1 = sf(rev[-1].get("val"))
    r0 = sf(rev[-2].get("val"))
    if r1 is None or r0 is None or r1 <= 0 or r0 <= 0:
        return False
    if r1 / r0 - 1.0 < 0:
        return False
    if sector == "Financials":
        return True
    gp = asof_records(pit.get("gp") or [], d)
    if not gp:
        return None
    latest_end = rev[-1]["end"]
    same = [x for x in gp if x.get("end") == latest_end]
    g = sf((same[-1] if same else gp[-1]).get("val"))
    return bool(g is not None and g > 0)

def shares_asof(pit, d):
    rs = asof_records(pit.get("shares") or [], d)
    if not rs:
        return None
    return sf(rs[-1].get("val"))

def indicators(mkt, d):
    i = idx_on_or_before(mkt, d)
    if i is None or i < 252:
        return None
    rows = mkt["rows"]
    tr_now = rows[i]["tr"]
    if tr_now is None or tr_now <= 0:
        return None
    def ret(n):
        old = rows[i-n]["tr"]
        return tr_now / old - 1.0 if old and old > 0 else None
    r63, r126, r252 = ret(63), ret(126), ret(252)
    if None in (r63, r126, r252):
        return None
    mom = (r63 + r126 + r252) / 3.0
    ema = ema200_at_index(rows, i)
    close = rows[i]["close"]
    atr = rows[i]["atr"]
    pct_atr = atr / close if atr is not None and close and close > 0 else None
    adv = statistics.mean([
        rows[j]["close"] * rows[j]["volume"] for j in range(max(0, i-62), i+1)
        if rows[j]["close"] is not None
    ])
    return {
        "i": i, "mom": mom, "r63": r63, "r126": r126, "r252": r252,
        "ema200_tr": ema, "above_ema200": tr_now > ema,
        "close": close, "atr": atr, "pct_atr": pct_atr, "adv63": adv
    }

def ema200_at_index(rows, i):
    """Exact continuous 200-session EMA; cache is only a performance shortcut."""
    if i is None or i < 199:
        return None
    cached = rows[i].get("ema200_tr")
    if cached is not None:
        return cached
    ema = statistics.mean(float(r["tr"]) for r in rows[:200])
    alpha = 2.0 / 201.0
    for j in range(200, i+1):
        ema = alpha * float(rows[j]["tr"]) + (1.0-alpha) * ema
    return ema


def regime(spy, d):
    i = idx_on_or_before(spy, d)
    if i is None or i < 199:
        return None
    return spy["rows"][i]["tr"] > ema200_at_index(spy["rows"], i)

@dataclass
class VPos:
    sleeve: str
    symbol: str
    shares: int
    avg: float
    opened: date
    high: float
    stop: float
    last_fund: bool = True
    pending_stop: bool = False

@dataclass
class State:
    name: str
    no_bear_liquidation: bool
    cash: float = STARTING
    pos: dict = field(default_factory=dict)
    costs: float = 0.0
    traded_notional: float = 0.0
    trades: list = field(default_factory=list)
    daily: list = field(default_factory=list)
    leadership_log: dict = field(default_factory=dict)

def key(sleeve, sym):
    return sleeve + ":" + sym

def commission(shares):
    return max(1.0, 0.005 * abs(shares)) if shares else 0.0

def portfolio_nav(st, markets, d):
    """Never silently value a held/delisted name using an arbitrarily old quote."""
    v = st.cash
    for p in st.pos.values():
        m = markets.get(p.symbol)
        if not m:
            raise RuntimeError(f"MISSING_MARKET: held {p.symbol} at {d}")
        i = idx_on_or_before(m, d)
        if i is None:
            raise RuntimeError(f"NO_PREVIOUS_PRICE: held {p.symbol} at {d}")
        quote = m["rows"][i]
        if (d - date.fromisoformat(quote["date"])).days > 7:
            raise RuntimeError(
                f"STALE_HELD_PRICE: {p.symbol}, decision={d}, last_quote={quote['date']}. "
                "Resolve delisting/corporate-action proceeds before publishing NAV."
            )
        px = quote["close"]
        if px is None or px <= 0:
            raise RuntimeError(f"INVALID_MARK: held {p.symbol} at {d}")
        v += p.shares * px
    return v

def execute_sell(st, pkey, qty, open_px, d, reason):
    p = st.pos.get(pkey)
    if not p:
        return
    qty = min(int(qty), p.shares)
    if qty <= 0:
        return
    fill = open_px * (1.0 - TOTAL_BPS / 10000.0)
    gross = qty * fill
    comm = commission(qty)
    slip = qty * open_px * TOTAL_BPS / 10000.0
    st.cash += gross - comm
    st.costs += comm + slip
    st.traded_notional += qty * open_px
    pnl = qty * (fill - p.avg) - comm
    st.trades.append({
        "date": d.isoformat(), "sleeve": p.sleeve, "symbol": p.symbol,
        "side": "SELL", "shares": qty, "open": open_px, "fill": fill,
        "reason": reason, "pnl": pnl, "commission": comm, "slippage": slip,
        "days": (d - p.opened).days
    })
    p.shares -= qty
    if p.shares <= 0:
        st.pos.pop(pkey, None)

def execute_buy(st, sleeve, sym, qty, open_px, d, reason, atr_prev, fund_ok):
    qty = int(qty)
    if qty <= 0:
        return
    fill = open_px * (1.0 + TOTAL_BPS / 10000.0)
    while qty > 0:
        comm = commission(qty)
        total = qty * fill + comm
        if total <= st.cash + 1e-9:
            break
        qty -= 1
    if qty <= 0:
        return
    comm = commission(qty)
    total = qty * fill + comm
    slip = qty * open_px * TOTAL_BPS / 10000.0
    st.cash -= total
    st.costs += comm + slip
    st.traded_notional += qty * open_px
    pk = key(sleeve, sym)
    if pk in st.pos:
        p = st.pos[pk]
        old_cost = p.avg * p.shares
        p.shares += qty
        p.avg = (old_cost + qty * fill) / p.shares
        p.last_fund = fund_ok if fund_ok is not None else p.last_fund
    else:
        stop = fill - 3.0 * atr_prev if atr_prev is not None else -1e99
        st.pos[pk] = VPos(sleeve, sym, qty, fill, d, fill, stop, bool(fund_ok), False)
    st.trades.append({
        "date": d.isoformat(), "sleeve": sleeve, "symbol": sym,
        "side": "BUY", "shares": qty, "open": open_px, "fill": fill,
        "reason": reason, "commission": comm, "slippage": slip
    })

def signal_snapshot(d, members, markets, pits, sectors, cikmap):
    data = {}
    issuer_caps = defaultdict(list)
    for sym in members:
        m = markets.get(sym)
        pit = pits.get(sym)
        if not m:
            continue
        ind = indicators(m, d)
        if not ind:
            continue
        fp = fundamental_pass(pit, d, sectors.get(sym, "")) if pit is not None else None
        sh = shares_asof(pit, d) if pit is not None else None
        cap = sh * ind["close"] if sh and ind["close"] else None
        rec = dict(ind)
        rec.update({"fund": fp, "cap": cap, "cik": cikmap.get(sym)})
        data[sym] = rec
        if cap and cap > 0 and cikmap.get(sym):
            issuer_caps[cikmap[sym]].append((cap, sym))
    # Raw cross-sectional momentum rank must be independent of fund PASS.
    # Fundamentals govern entry eligibility, not the position in the ranking.
    rankable = [(sym, r) for sym, r in data.items() if r["mom"] > 0]
    rankable.sort(key=lambda z: (z[1]["mom"], z[1]["adv63"], z[0]), reverse=True)
    ranks = {sym: i+1 for i, (sym, _) in enumerate(rankable)}
    for sym in data:
        data[sym]["rank"] = ranks.get(sym)
    issuers = []
    for cik, vals in issuer_caps.items():
        cap = max(x[0] for x in vals)
        reps = sorted(vals, key=lambda x: (data[x[1]]["adv63"], x[1]), reverse=True)
        issuers.append((cap, reps[0][1], cik))
    issuers.sort(reverse=True)
    leadership = []
    for cap, sym, cik in issuers[:15]:
        r = data.get(sym)
        if not r:
            continue
        if r["fund"] is True and r["mom"] > 0 and r.get("rank") and r["rank"] <= 100 and r["r126"] > 0 and r["above_ema200"]:
            leadership.append(sym)
    return data, leadership[:LEAD_MAX]

def retained_or_targets(st, snap, leadership, bull):
    current_rot = [p.symbol for p in st.pos.values() if p.sleeve == "rot"]
    current_lead = [p.symbol for p in st.pos.values() if p.sleeve == "lead"]
    sell_keys = {}
    rot_keep = []
    for sym in current_rot:
        pk = key("rot", sym)
        p = st.pos.get(pk)
        r = snap.get(sym)
        if not r:
            sell_keys[pk] = "MISSING SNAPSHOT/UNIVERSE EXIT"
            continue
        fp = r["fund"]
        if fp is None:
            fp = p.last_fund
        else:
            p.last_fund = bool(fp)
        if fp is not True or r["mom"] <= 0 or not r.get("rank") or r["rank"] > 35:
            sell_keys[pk] = "ROT ELIGIBILITY/RANK EXIT"
        else:
            rot_keep.append(sym)
    lead_keep = []
    lead_set = set(leadership)
    for sym in current_lead:
        pk = key("lead", sym)
        p = st.pos.get(pk)
        r = snap.get(sym)
        if not r:
            sell_keys[pk] = "MISSING SNAPSHOT/UNIVERSE EXIT"
            continue
        fp = r["fund"]
        if fp is None:
            fp = p.last_fund
        else:
            p.last_fund = bool(fp)
        if fp is not True or sym not in lead_set:
            sell_keys[pk] = "LEADERSHIP QUALIFICATION EXIT"
        else:
            lead_keep.append(sym)

    if not bull and not st.no_bear_liquidation:
        for pk in list(st.pos):
            sell_keys[pk] = "BEAR LIQUIDATION"
        return sell_keys, [], []

    rot_sel = list(dict.fromkeys(rot_keep))
    if bull:
        candidates = sorted(
            [(sym, r) for sym, r in snap.items()
             if r["fund"] is True and r["mom"] > 0 and r.get("rank") and r["rank"] <= 20 and sym not in rot_sel],
            key=lambda z: z[1]["rank"]
        )
        for sym, _ in candidates:
            if len(rot_sel) >= ROT_MAX:
                break
            rot_sel.append(sym)

    lead_sel = [s for s in lead_keep if s in lead_set]
    if bull:
        for sym in leadership:
            if len(lead_sel) >= LEAD_MAX:
                break
            if sym not in lead_sel:
                lead_sel.append(sym)
    return sell_keys, rot_sel[:ROT_MAX], lead_sel[:LEAD_MAX]

def target_weights(syms, sleeve_budget, max_slots, snap):
    n = len(syms)
    if n == 0:
        return {}
    exposure = sleeve_budget * n / max_slots
    inv = {}
    for s in syms:
        a = (snap.get(s) or {}).get("pct_atr")
        if a and a > 0:
            inv[s] = 1.0 / a
    if len(inv) != n or sum(inv.values()) <= 0:
        return {s: exposure / n for s in syms}
    tot = sum(inv.values())
    return {s: exposure * inv[s] / tot for s in syms}

def build_monthly_orders(st, d, bull, snap, leadership, markets):
    sell_keys, rot_sel, lead_sel = retained_or_targets(st, snap, leadership, bull)
    nav = portfolio_nav(st, markets, d)
    targets = {}
    for sym, w in target_weights(rot_sel, ROT_BUDGET, ROT_MAX, snap).items():
        targets[key("rot", sym)] = (sym, "rot", w)
    for sym, w in target_weights(lead_sel, LEAD_BUDGET, LEAD_MAX, snap).items():
        targets[key("lead", sym)] = (sym, "lead", w)

    orders = []
    for pk, reason in sell_keys.items():
        p = st.pos.get(pk)
        if p:
            orders.append({"kind": "sell", "pk": pk, "qty": p.shares, "reason": reason, "priority": -10000})

    for pk, (sym, sleeve, w) in targets.items():
        r = snap[sym]
        est = r["close"]
        desired = int(math.floor(nav * w / est)) if est and est > 0 else 0
        cur = st.pos.get(pk).shares if pk in st.pos else 0
        if desired < cur:
            orders.append({"kind": "sell", "pk": pk, "qty": cur - desired,
                           "reason": "MONTHLY RESIZE", "priority": r.get("rank") or 999})
        elif desired > cur and bull:
            orders.append({"kind": "buy", "pk": pk, "sym": sym, "sleeve": sleeve,
                           "qty": desired - cur, "reason": "MONTHLY TARGET",
                           "priority": r.get("rank") or 999, "atr": r.get("atr"), "fund": r.get("fund")})
    return orders, rot_sel, lead_sel

def run_variant(name, no_bear, trading_dates, signal_dates, members_by_signal, markets, pits, sectors, cikmap, spy):
    st = State(name, no_bear)
    signals = set(signal_dates)
    pending_monthly = {}
    snapshots = {}
    siglog = {}
    for d in signal_dates:
        snap, leadership = signal_snapshot(d, members_by_signal[d], markets, pits, sectors, cikmap)
        bull = regime(spy, d)
        snapshots[d] = (snap, leadership, bull)
        if d.year == 2023 and d.month in (6, 7):
            st.leadership_log[d.isoformat()] = leadership

    for d in trading_dates:
        for p in list(st.pos.values()):
            m = markets.get(p.symbol)
            if not m:
                continue
            i = idx_on_or_before(m, d)
            if i is not None and m["rows"][i]["date"] == d.isoformat():
                div = m["rows"][i].get("dividend") or 0.0
                if div:
                    st.cash += p.shares * div

        for pk, p in list(st.pos.items()):
            if not p.pending_stop:
                continue
            m = markets.get(p.symbol)
            if not m:
                continue
            i = idx_on_or_after(m, d)
            if i is not None and m["rows"][i]["date"] == d.isoformat() and m["rows"][i]["open"] is not None:
                execute_sell(st, pk, p.shares, m["rows"][i]["open"], d, "ATR STOP")

        if d in pending_monthly:
            orders = pending_monthly.pop(d)
            for o in [x for x in orders if x["kind"] == "sell"]:
                p = st.pos.get(o["pk"])
                if not p:
                    continue
                m = markets.get(p.symbol)
                if not m:
                    continue
                i = idx_on_or_after(m, d)
                if i is not None and m["rows"][i]["date"] == d.isoformat() and m["rows"][i]["open"] is not None:
                    execute_sell(st, o["pk"], o["qty"], m["rows"][i]["open"], d, o["reason"])
            buys = sorted([x for x in orders if x["kind"] == "buy"], key=lambda x: (x["priority"], x["sym"]))
            for o in buys:
                m = markets.get(o["sym"])
                if not m:
                    continue
                i = idx_on_or_after(m, d)
                if i is not None and m["rows"][i]["date"] == d.isoformat() and m["rows"][i]["open"] is not None:
                    execute_buy(st, o["sleeve"], o["sym"], o["qty"], m["rows"][i]["open"], d,
                                o["reason"], o.get("atr"), o.get("fund"))

        for pk, p in list(st.pos.items()):
            m = markets.get(p.symbol)
            if not m:
                continue
            i = idx_on_or_before(m, d)
            if i is None or m["rows"][i]["date"] != d.isoformat():
                continue
            row = m["rows"][i]
            c = row["close"]
            atr = row["atr"]
            if c is None:
                continue
            if c <= p.stop:
                p.pending_stop = True
            else:
                p.high = max(p.high, c)
                if atr is not None:
                    p.stop = max(p.stop, p.high - 3.0 * atr)

        nav = portfolio_nav(st, markets, d)
        eq = max(0.0, nav - st.cash)
        st.daily.append({
            "date": d.isoformat(), "nav": nav, "cash": st.cash,
            "equity_exposure": eq / nav if nav > 0 else 0.0,
            "positions": len(st.pos)
        })

        if d in signals:
            snap, leadership, bull = snapshots[d]
            orders, rot_sel, lead_sel = build_monthly_orders(st, d, bool(bull), snap, leadership, markets)
            stopped_syms = {p.symbol for p in st.pos.values() if p.pending_stop}
            if stopped_syms:
                orders = [o for o in orders if not (o["kind"] == "buy" and o.get("sym") in stopped_syms)]
            ni = bisect.bisect_right(trading_dates, d)
            if ni < len(trading_dates):
                pending_monthly[trading_dates[ni]] = orders
            siglog[d.isoformat()] = {"bull": bool(bull), "rotational": rot_sel, "leadership": lead_sel}
    return st, siglog

def metrics(st):
    ds = st.daily
    endv = ds[-1]["nav"]
    total = endv / STARTING - 1.0
    cagr_5y = (endv / STARTING) ** (1/5.0) - 1.0
    actual_years = (date.fromisoformat(ds[-1]["date"]) - date.fromisoformat(ds[0]["date"])).days / 365.25
    cagr_actual = (endv / STARTING) ** (1/actual_years) - 1.0
    peak = -1e99
    maxdd = 0.0
    byyear = defaultdict(list)
    for r in ds:
        nav = r["nav"]
        peak = max(peak, nav)
        if peak > 0:
            maxdd = min(maxdd, nav / peak - 1.0)
        byyear[int(r["date"][:4])].append(r)
    annual = {}
    prev = STARTING
    for y in sorted(byyear):
        v = byyear[y][-1]["nav"]
        annual[str(y)] = v / prev - 1.0
        prev = v
    avg_nav = statistics.mean([r["nav"] for r in ds])
    avg_exp = statistics.mean([r["equity_exposure"] for r in ds])
    avg_hold = statistics.mean([r["positions"] for r in ds])
    sells = [t for t in st.trades if t["side"] == "SELL"]
    return {
        "name": st.name,
        "end_value": round(endv, 2),
        "total_return_pct": round(total*100, 2),
        "cagr_5y_convention_pct": round(cagr_5y*100, 2),
        "cagr_actual_elapsed_pct": round(cagr_actual*100, 2),
        "max_drawdown_pct": round(maxdd*100, 2),
        "annual_returns_pct": {k: round(v*100, 2) for k, v in annual.items()},
        "avg_equity_exposure_pct": round(avg_exp*100, 2),
        "avg_virtual_positions": round(avg_hold, 2),
        "trade_count": len(st.trades),
        "sell_count": len(sells),
        "costs": round(st.costs, 2),
        "traded_notional": round(st.traded_notional, 2),
        "annualized_turnover_x": round(st.traded_notional / avg_nav / 5.0, 2),
        "leadership_log": st.leadership_log
    }

def benchmark_metrics(spy, trading_dates):
    i0 = idx_on_or_before(spy, trading_dates[0])
    i1 = idx_on_or_before(spy, trading_dates[-1])
    tr0 = spy["rows"][i0]["tr"]
    tr1 = spy["rows"][i1]["tr"]
    ret = tr1 / tr0 - 1.0
    return {"name": "SPY total-return reconstruction", "total_return_pct": round(ret*100, 2)}

def markdown(rep):
    a = []
    a.append("# 75/25 leadership architecture — BEAR liquidation ablation")
    a.append("")
    a.append("Research branch run. The only intended behavioral change between the two variants is the market-regime action:")
    a.append("- Control: BEAR liquidates all equity positions and blocks buys.")
    a.append("- No-new-buys: BEAR blocks new/additional buys but retains incumbents unless their own rank, momentum, leadership qualification, or ATR stop exits them.")
    a.append("")
    a.append("| Metric | Frozen-rule control | No-new-buys in BEAR |")
    a.append("|---|---:|---:|")
    c, n = rep["results"]
    for label, key_, fmt in [
        ("Ending value", "end_value", "${:,.2f}"),
        ("5Y return", "total_return_pct", "{:+.2f}%"),
        ("CAGR (same 5Y convention)", "cagr_5y_convention_pct", "{:.2f}%"),
        ("Actual elapsed CAGR", "cagr_actual_elapsed_pct", "{:.2f}%"),
        ("Max drawdown", "max_drawdown_pct", "{:.2f}%"),
        ("2022", None, None), ("2023", None, None), ("2024", None, None),
        ("2025", None, None), ("2026 Jan-Sep", None, None),
        ("Avg equity exposure", "avg_equity_exposure_pct", "{:.2f}%"),
        ("Annualized turnover", "annualized_turnover_x", "{:.2f}x"),
        ("Costs", "costs", "${:,.2f}"),
        ("Trades", "trade_count", "{:,.0f}")
    ]:
        if label.startswith("202"):
            y = label[:4]
            cv = c["annual_returns_pct"].get(y)
            nv = n["annual_returns_pct"].get(y)
            a.append(f"| {label} | {cv:+.2f}% | {nv:+.2f}% |")
        else:
            a.append(f"| {label} | {fmt.format(c[key_])} | {fmt.format(n[key_])} |")
    a.append("")
    a.append("## Validation against the previously reported control")
    a.append("")
    a.append("Previously reported earlier-25%-leadership control: ending value $19,808.08, 5Y return +98.08%, CAGR 14.66%, max drawdown -33.85%, 2023 +2.91%.")
    a.append("This independent replay uses the public S&P constituent-change table, Yahoo historical prices/dividends, and SEC filing-timestamped annual revenue/gross-profit/share data. Any difference from the prior artifact is reported rather than calibrated away.")
    a.append("")
    a.append("## 2023 leadership validation")
    a.append("")
    a.append("Expected conceptual check from prior research: June/July 2023 should favor mega-cap trend-qualified names such as MSFT, AMZN, NVDA, TSLA and AVGO.")
    a.append("")
    a.append("Control leadership log: " + json.dumps(c.get("leadership_log") or {}, sort_keys=True))
    a.append("")
    a.append("## Data/method notes")
    a.append("")
    a.append("- Point-in-time S&P 500 membership is reconstructed from the public current-constituent and historical-changes tables.")
    a.append("- Momentum and the SPY regime use a dividend-reinvested total-return series reconstructed from split-adjusted Yahoo closes plus cash dividends.")
    a.append("- Fills use next-session opens with 7 bps adverse price drag per side plus max($1, $0.005/share) commission.")
    a.append("- Sizing is inverse percentage Wilder ATR14, with occupied-slot exposure preserved separately for the 15-slot rotational and 5-slot leadership sleeves.")
    a.append("- Fundamental PASS is approximated from filing-timestamped SEC annual revenue growth >=0 and positive gross profit, with Financials gross-profit-exempt. This is the largest potential source of mismatch versus the earlier experiment artifact.")
    a.append("- Whole shares only; no leverage; stopped-out cash waits until a later monthly cycle.")
    return "\n".join(a) + "\n"


ADAPT_OUT_JSON = ROOT / "backtests/results/adaptive_entry_policy_2022_2026.json"
ADAPT_OUT_MD = ROOT / "backtests/results/adaptive_entry_policy_2022_2026.md"

ADAPTIVE_THRESHOLDS = {
    "broad_green": 0.50,
    "systemic_breadth": 0.35,
    "leader_healthy": 0.40,
    "recovery_breadth": 0.40,
    "early_recovery_breadth": 0.45,
    "recovery_breadth_improvement": 0.05,
    "systemic_survivor_scale": 0.50,
    "narrow_rot_budget": 0.65,
    "narrow_lead_budget": 0.35,
}

def _ema200_at(spy, i):
    if i is None or i < 199:
        return None
    vals = [spy["rows"][j]["tr"] for j in range(i-199, i+1)]
    ema = vals[0]
    alpha = 2.0 / 201.0
    for v in vals[1:]:
        ema = alpha * v + (1-alpha) * ema
    return ema

def spy_context(spy, d):
    i = idx_on_or_before(spy, d)
    if i is None or i < 199:
        return None
    tr = spy["rows"][i]["tr"]
    ema = _ema200_at(spy, i)
    r21 = tr / spy["rows"][i-21]["tr"] - 1.0 if i >= 21 and spy["rows"][i-21]["tr"] else None
    r63 = tr / spy["rows"][i-63]["tr"] - 1.0 if i >= 63 and spy["rows"][i-63]["tr"] else None
    ema21 = _ema200_at(spy, i-21) if i >= 220 else None
    slope21 = ema / ema21 - 1.0 if ema21 and ema else None
    return {
        "spy_above": bool(tr > ema),
        "spy_r21": r21,
        "spy_r63": r63,
        "spy_ema_slope21": slope21,
        "spy_tr": tr,
        "spy_ema200": ema,
    }

def top15_from_snapshot(snap):
    by_issuer = {}
    for sym, r in snap.items():
        cap = r.get("cap")
        cik = r.get("cik")
        if cap and cap > 0 and cik:
            cur = by_issuer.get(cik)
            if cur is None or cap > cur[0]:
                by_issuer[cik] = (cap, sym)
    vals = sorted(by_issuer.values(), reverse=True)
    return [sym for _, sym in vals[:15]]

def market_context(spy, d, snap):
    sctx = spy_context(spy, d)
    if not sctx:
        return {
            "state": "CORRECTION", "breadth": 0.0, "leader_health": 0.0,
            "top15": [], "spy_above": False, "spy_r21": None, "spy_r63": None,
            "spy_ema_slope21": None
        }
    valid = [r for r in snap.values() if r.get("mom") is not None]
    breadth = (
        sum(1 for r in valid if r.get("mom", 0) > 0 and r.get("r126", 0) > 0 and r.get("above_ema200"))
        / len(valid)
    ) if valid else 0.0
    top15 = top15_from_snapshot(snap)
    leader_good = 0
    for sym in top15:
        r = snap.get(sym) or {}
        if r.get("mom", 0) > 0 and r.get("r126", 0) > 0 and r.get("above_ema200"):
            leader_good += 1
    leader_health = leader_good / len(top15) if top15 else 0.0

    if sctx["spy_above"]:
        if breadth >= ADAPTIVE_THRESHOLDS["broad_green"]:
            state = "GREEN"
        elif leader_health >= ADAPTIVE_THRESHOLDS["leader_healthy"]:
            state = "NARROW_LEADERSHIP"
        else:
            state = "CORRECTION"
    else:
        if breadth < ADAPTIVE_THRESHOLDS["systemic_breadth"] and leader_health < ADAPTIVE_THRESHOLDS["leader_healthy"]:
            state = "SYSTEMIC_BEAR"
        else:
            state = "CORRECTION"

    out = dict(sctx)
    out.update({
        "state": state,
        "breadth": breadth,
        "leader_health": leader_health,
        "top15": top15,
        "valid_breadth_count": len(valid),
    })
    return out

def _own_rule_plan(st, snap, leadership):
    current_rot = [p.symbol for p in st.pos.values() if p.sleeve == "rot"]
    current_lead = [p.symbol for p in st.pos.values() if p.sleeve == "lead"]
    sell_keys = {}
    rot_keep = []
    for sym in current_rot:
        pk = key("rot", sym)
        p = st.pos.get(pk)
        r = snap.get(sym)
        if not r:
            continue
        fp = r["fund"]
        if fp is None:
            fp = p.last_fund
        else:
            p.last_fund = bool(fp)
        if fp is not True or r["mom"] <= 0 or not r.get("rank") or r["rank"] > 35:
            sell_keys[pk] = "ROT ELIGIBILITY/RANK EXIT"
        else:
            rot_keep.append(sym)

    lead_keep = []
    lead_set = set(leadership)
    for sym in current_lead:
        pk = key("lead", sym)
        p = st.pos.get(pk)
        r = snap.get(sym)
        if not r:
            continue
        fp = r["fund"]
        if fp is None:
            fp = p.last_fund
        else:
            p.last_fund = bool(fp)
        if fp is not True or sym not in lead_set:
            sell_keys[pk] = "LEADERSHIP QUALIFICATION EXIT"
        else:
            lead_keep.append(sym)
    return sell_keys, rot_keep, lead_keep

def _fill_candidates(rot_keep, lead_keep, snap, leadership, allow_new):
    rot_sel = list(dict.fromkeys(rot_keep))
    lead_sel = list(dict.fromkeys(lead_keep))
    if allow_new:
        candidates = sorted(
            [(sym, r) for sym, r in snap.items()
             if r["fund"] is True and r["mom"] > 0 and r.get("rank")
             and r["rank"] <= 20 and sym not in rot_sel],
            key=lambda z: z[1]["rank"]
        )
        for sym, _ in candidates:
            if len(rot_sel) >= ROT_MAX:
                break
            rot_sel.append(sym)
        for sym in leadership:
            if len(lead_sel) >= LEAD_MAX:
                break
            if sym not in lead_sel:
                lead_sel.append(sym)
    return rot_sel[:ROT_MAX], lead_sel[:LEAD_MAX]

def build_adaptive_monthly_orders(st, d, snap, leadership, markets, cfg, ctx):
    sell_keys, rot_keep, lead_keep = _own_rule_plan(st, snap, leadership)
    state = ctx["state"]
    mode = cfg["mode"]

    allow_rot = False
    allow_lead = False
    rot_entry_cutoff = 20

    if mode == "no_bear":
        allow_rot = bool(ctx["spy_above"])
        allow_lead = bool(ctx["spy_above"])
    elif mode == "adaptive_entry":
        if state in ("GREEN", "NARROW_LEADERSHIP"):
            allow_rot = True
            allow_lead = True
        elif state == "CORRECTION":
            allow_lead = True
            if cfg.get("correction_rot_top"):
                allow_rot = True
                rot_entry_cutoff = int(cfg["correction_rot_top"])
        elif state == "SYSTEMIC_BEAR":
            allow_rot = False
            allow_lead = False
    else:
        allow_rot = bool(ctx["spy_above"])
        allow_lead = bool(ctx["spy_above"])

    rot_sel = list(dict.fromkeys(rot_keep))
    if allow_rot:
        candidates = sorted(
            [(sym, r) for sym, r in snap.items()
             if r["fund"] is True and r["mom"] > 0 and r.get("rank")
             and r["rank"] <= rot_entry_cutoff and sym not in rot_sel],
            key=lambda z: z[1]["rank"]
        )
        for sym, _ in candidates:
            if len(rot_sel) >= ROT_MAX:
                break
            rot_sel.append(sym)

    lead_sel = list(dict.fromkeys(lead_keep))
    if allow_lead:
        for sym in leadership:
            if len(lead_sel) >= LEAD_MAX:
                break
            if sym not in lead_sel:
                lead_sel.append(sym)

    rot_sel = rot_sel[:ROT_MAX]
    lead_sel = lead_sel[:LEAD_MAX]

    nav = portfolio_nav(st, markets, d)
    targets = {}
    for sym, w in target_weights(rot_sel, ROT_BUDGET, ROT_MAX, snap).items():
        targets[key("rot", sym)] = (sym, "rot", w)
    for sym, w in target_weights(lead_sel, LEAD_BUDGET, LEAD_MAX, snap).items():
        targets[key("lead", sym)] = (sym, "lead", w)

    orders = []
    for pk, reason in sell_keys.items():
        p = st.pos.get(pk)
        if p:
            orders.append({"kind": "sell", "pk": pk, "qty": p.shares, "reason": reason, "priority": -10000})

    for pk, (sym, sleeve, w) in targets.items():
        r = snap[sym]
        est = r["close"]
        desired = int(math.floor(nav * w / est)) if est and est > 0 else 0
        cur = st.pos.get(pk).shares if pk in st.pos else 0
        if desired < cur:
            orders.append({"kind": "sell", "pk": pk, "qty": cur - desired,
                           "reason": "MONTHLY RESIZE", "priority": r.get("rank") or 999})
        elif desired > cur:
            can_buy = allow_rot if sleeve == "rot" else allow_lead
            if can_buy:
                orders.append({"kind": "buy", "pk": pk, "sym": sym, "sleeve": sleeve,
                               "qty": desired - cur, "reason": "MONTHLY TARGET",
                               "priority": r.get("rank") or 999, "atr": r.get("atr"), "fund": r.get("fund")})
    return orders, rot_sel, lead_sel

def recovery_condition(ctx, monthly_ctx):
    if not ctx or not monthly_ctx:
        return False
    if ctx["spy_above"] and ctx["breadth"] >= ADAPTIVE_THRESHOLDS["recovery_breadth"]:
        return True
    base_breadth = monthly_ctx.get("breadth") or 0.0
    return bool(
        (ctx.get("spy_r21") or 0.0) > 0
        and ctx["breadth"] >= ADAPTIVE_THRESHOLDS["early_recovery_breadth"]
        and ctx["leader_health"] >= ADAPTIVE_THRESHOLDS["leader_healthy"]
        and ctx["breadth"] >= base_breadth + ADAPTIVE_THRESHOLDS["recovery_breadth_improvement"]
    )

def recovery_buy_orders(st, d, snap, leadership, markets, cfg, ctx):
    current_rot = [p.symbol for p in st.pos.values() if p.sleeve == "rot" and p.symbol in snap]
    current_lead = [p.symbol for p in st.pos.values() if p.sleeve == "lead" and p.symbol in snap]
    rot_sel, lead_sel = _fill_candidates(current_rot, current_lead, snap, leadership, True)
    rot_budget, lead_budget = ROT_BUDGET, LEAD_BUDGET
    if cfg.get("narrow_tilt") and ctx.get("state") == "NARROW_LEADERSHIP":
        rot_budget = ADAPTIVE_THRESHOLDS["narrow_rot_budget"]
        lead_budget = ADAPTIVE_THRESHOLDS["narrow_lead_budget"]
    nav = portfolio_nav(st, markets, d)
    orders = []
    for sleeve, syms, budget, max_slots in [
        ("rot", rot_sel, rot_budget, ROT_MAX),
        ("lead", lead_sel, lead_budget, LEAD_MAX),
    ]:
        for sym, w in target_weights(syms, budget, max_slots, snap).items():
            r = snap[sym]
            if r.get("mom", 0) <= 0:
                continue
            est = r.get("close")
            desired = int(math.floor(nav * w / est)) if est and est > 0 else 0
            pk = key(sleeve, sym)
            cur = st.pos.get(pk).shares if pk in st.pos else 0
            if desired > cur:
                orders.append({
                    "kind": "buy", "pk": pk, "sym": sym, "sleeve": sleeve,
                    "qty": desired - cur, "reason": "WEEKLY RECOVERY",
                    "priority": r.get("rank") or 999, "atr": r.get("atr"), "fund": r.get("fund")
                })
    return orders, rot_sel, lead_sel

def run_adaptive_variant(cfg, trading_dates, signal_dates, month_data, week_data, markets):
    st = State(cfg["name"], False)
    st.market_state_log = {}
    st.recovery_log = []
    signals = set(signal_dates)
    pending_orders = {}
    siglog = {}

    def stop_enabled_for(p):
        if cfg.get("atr_mult", 3.0) is None:
            return False
        if cfg.get("disable_lead_stop") and p.sleeve == "lead":
            return False
        return True

    for d in trading_dates:
        for p in list(st.pos.values()):
            m = markets.get(p.symbol)
            if not m:
                continue
            i = idx_on_or_before(m, d)
            if i is not None and m["rows"][i]["date"] == d.isoformat():
                div = m["rows"][i].get("dividend") or 0.0
                if div:
                    st.cash += p.shares * div

        for pk, p in list(st.pos.items()):
            if not p.pending_stop:
                continue
            if not stop_enabled_for(p):
                p.pending_stop = False
                continue
            m = markets.get(p.symbol)
            if not m:
                continue
            i = idx_on_or_after(m, d)
            if i is not None and m["rows"][i]["date"] == d.isoformat() and m["rows"][i]["open"] is not None:
                execute_sell(st, pk, p.shares, m["rows"][i]["open"], d, "ATR STOP")

        if d in pending_orders:
            orders = pending_orders.pop(d)
            for o in [x for x in orders if x["kind"] == "sell"]:
                p = st.pos.get(o["pk"])
                if not p:
                    continue
                m = markets.get(p.symbol)
                if not m:
                    continue
                i = idx_on_or_after(m, d)
                if i is not None and m["rows"][i]["date"] == d.isoformat() and m["rows"][i]["open"] is not None:
                    execute_sell(st, o["pk"], o["qty"], m["rows"][i]["open"], d, o["reason"])
            stopped_syms = {p.symbol for p in st.pos.values() if p.pending_stop and stop_enabled_for(p)}
            buys = sorted(
                [x for x in orders if x["kind"] == "buy" and x.get("sym") not in stopped_syms],
                key=lambda x: (x["priority"], x["sym"])
            )
            for o in buys:
                m = markets.get(o["sym"])
                if not m:
                    continue
                i = idx_on_or_after(m, d)
                if i is not None and m["rows"][i]["date"] == d.isoformat() and m["rows"][i]["open"] is not None:
                    existed = o["pk"] in st.pos
                    execute_buy(st, o["sleeve"], o["sym"], o["qty"], m["rows"][i]["open"], d,
                                o["reason"], o.get("atr"), o.get("fund"))
                    pnew = st.pos.get(o["pk"])
                    if pnew and not existed:
                        mult = cfg.get("atr_mult", 3.0)
                        if mult is None or (cfg.get("disable_lead_stop") and pnew.sleeve == "lead"):
                            pnew.stop = -1e99
                        elif o.get("atr") is not None:
                            pnew.stop = pnew.avg - float(mult) * o["atr"]

        for pk, p in list(st.pos.items()):
            if not stop_enabled_for(p):
                p.pending_stop = False
                continue
            m = markets.get(p.symbol)
            if not m:
                continue
            i = idx_on_or_before(m, d)
            if i is None or m["rows"][i]["date"] != d.isoformat():
                continue
            row = m["rows"][i]
            c = row["close"]
            atr = row["atr"]
            if c is None:
                continue
            if c <= p.stop:
                p.pending_stop = True
            else:
                p.high = max(p.high, c)
                if atr is not None:
                    p.stop = max(p.stop, p.high - float(cfg.get("atr_mult", 3.0)) * atr)

        nav = portfolio_nav(st, markets, d)
        eq = max(0.0, nav - st.cash)
        st.daily.append({
            "date": d.isoformat(), "nav": nav, "cash": st.cash,
            "equity_exposure": eq / nav if nav > 0 else 0.0,
            "positions": len(st.pos)
        })

        if d in signals:
            snap, leadership, ctx = month_data[d]
            orders, rot_sel, lead_sel = build_adaptive_monthly_orders(
                st, d, snap, leadership, markets, cfg, ctx
            )
            ni = bisect.bisect_right(trading_dates, d)
            if ni < len(trading_dates):
                pending_orders.setdefault(trading_dates[ni], []).extend(orders)
            st.market_state_log[d.isoformat()] = ctx
            siglog[d.isoformat()] = {
                "state": ctx["state"], "breadth": ctx["breadth"],
                "leader_health": ctx["leader_health"], "spy_above": ctx["spy_above"],
                "rotational": rot_sel, "leadership": lead_sel
            }

    return st, siglog

def adaptive_metrics(st):
    out = metrics(st)
    byyear = defaultdict(list)
    for r in st.daily:
        byyear[r["date"][:4]].append(r["equity_exposure"])
    out["annual_avg_equity_exposure_pct"] = {
        y: round(statistics.mean(v)*100, 2) for y, v in sorted(byyear.items())
    }
    states = defaultdict(int)
    for v in getattr(st, "market_state_log", {}).values():
        states[v["state"]] += 1
    out["market_state_counts"] = dict(states)
    out["recovery_triggers"] = len(getattr(st, "recovery_log", []))
    out["recovery_log"] = getattr(st, "recovery_log", [])
    out["monthly_state_log"] = getattr(st, "market_state_log", {})
    reasons = defaultdict(int)
    for t in st.trades:
        if t["side"] == "SELL":
            reasons[t.get("reason") or ""] += 1
    out["sell_reason_counts"] = dict(reasons)
    return out

def adaptive_markdown(rep):
    results = rep["results"]
    a = []
    a.append("# Adaptive entry-policy experiment - 2022-2026 research replay")
    a.append("")
    a.append("This is an independent point-in-time research replay using the same reconstructed 75/25 architecture and data pipeline as the prior no-BEAR ablation. Absolute returns do not reproduce the earlier 19,808 artifact, so comparisons below are valid as within-replay ablations, not replacements for the frozen control.")
    a.append("")
    a.append("Pre-registered controller thresholds:")
    a.append("- GREEN: SPY above EMA200 and healthy breadth >= 50%.")
    a.append("- NARROW_LEADERSHIP: SPY above EMA200, breadth < 50%, leadership health >= 40%.")
    a.append("- SYSTEMIC_BEAR: SPY below EMA200, healthy breadth < 35%, leadership health < 40%.")
    a.append("- CORRECTION: all other non-GREEN/non-NARROW states.")
    a.append("- Weekly RECOVERY: SPY back above EMA200 with breadth >= 40%, or positive 21-session SPY return with breadth >= 45%, leadership health >= 40%, and breadth at least 5 points above the defensive month-end.")
    a.append("")
    a.append("| Variant | End value | 5Y return | CAGR | Max DD | 2022 | 2023 | 2024 | 2025 | 2026 | Avg exp. | Turnover | Costs | Recoveries |")
    a.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in results:
        ar = r["annual_returns_pct"]
        a.append(
            f"| {r['name']} | USD {r['end_value']:,.2f} | {r['total_return_pct']:+.2f}% | "
            f"{r['cagr_5y_convention_pct']:.2f}% | {r['max_drawdown_pct']:.2f}% | "
            f"{ar.get('2022',0):+.2f}% | {ar.get('2023',0):+.2f}% | {ar.get('2024',0):+.2f}% | "
            f"{ar.get('2025',0):+.2f}% | {ar.get('2026',0):+.2f}% | "
            f"{r['avg_equity_exposure_pct']:.2f}% | {r['annualized_turnover_x']:.2f}x | "
            f"USD {r['costs']:,.0f} | {r['recovery_triggers']} |"
        )
    a.append("")
    a.append("## 2023 monthly state classifications")
    a.append("")
    for r in results:
        if not r.get("monthly_state_log"):
            continue
        a.append("### " + r["name"])
        a.append("")
        a.append("| Month-end | State | SPY>EMA200 | Breadth | Leader health |")
        a.append("|---|---|---:|---:|---:|")
        for d, ctx in sorted(r["monthly_state_log"].items()):
            if d.startswith("2023-"):
                a.append(
                    f"| {d} | {ctx['state']} | {'Yes' if ctx['spy_above'] else 'No'} | "
                    f"{ctx['breadth']*100:.1f}% | {ctx['leader_health']*100:.1f}% |"
                )
        a.append("")
    a.append("## Interpretation discipline")
    a.append("")
    a.append("- The earlier frozen 75/25 artifact reported USD 19,808.08 ending value, 14.66% CAGR, -33.85% max drawdown and +2.91% in 2023. This replay does not replicate it because its public-data fundamental/share reconstruction differs materially.")
    a.append("- Therefore choose among adaptive variants only on relative changes inside this replay, then confirm the winning controller against the original frozen artifact before production use.")
    return "\n".join(a) + "\n"

def adaptive_main():
    cache = Cache(ROOT / ".backtest_cache")
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 ISK adaptive-market-state research"
    current, sectors, changes = sp500_history(s)
    members0 = members_at(current, changes, date(2021, 12, 31))
    rel = [x for x in changes if date(2021, 12, 1) <= date.fromisoformat(x["date"]) <= END]
    union = set(members0) | current
    for x in rel:
        if x["added"]:
            union.add(x["added"])
        if x["removed"]:
            union.add(x["removed"])
    print("Universe", len(union), flush=True)

    raw = {}
    from concurrent.futures import ThreadPoolExecutor, as_completed
    def fetch_sym(sym):
        z = requests.Session()
        z.headers["User-Agent"] = "Mozilla/5.0 ISK adaptive-market-state research"
        return sym, yahoo(z, cache, sym, DATA_START, DATA_END)
    with ThreadPoolExecutor(max_workers=10) as ex:
        fs = [ex.submit(fetch_sym, x) for x in sorted(union | {"SPY"})]
        for i, f in enumerate(as_completed(fs), 1):
            sym, v = f.result()
            if v:
                raw[sym] = v
            if i % 50 == 0:
                print("Yahoo", i, "/", len(fs), flush=True)
    markets = {k: prepare_market(v) for k, v in raw.items()}
    markets = {k: v for k, v in markets.items() if v}
    spy = markets["SPY"]

    lim = Limiter(7)
    ss = requests.Session()
    ss.headers["User-Agent"] = "ISK adaptive-market-state point-in-time research"
    cikmap = ticker_map(ss, cache, lim)
    pits = {}
    for i, sym in enumerate(sorted(union), 1):
        cik = cikmap.get(sym)
        if cik:
            f = facts(ss, cache, lim, sym, cik)
            if f:
                pits[sym] = preprocess_facts(f)
        if i % 50 == 0:
            print("SEC", i, "/", len(union), flush=True)
    print("Coverage prices", len(markets), "SEC", len(pits), flush=True)

    trading_dates = [
        date.fromisoformat(r["date"]) for r in spy["rows"]
        if START <= date.fromisoformat(r["date"]) <= END
    ]
    signal_pool = [
        date.fromisoformat(r["date"]) for r in spy["rows"]
        if date(2021, 12, 1) <= date.fromisoformat(r["date"]) <= END
    ]
    month_last = {}
    week_last = {}
    for d in signal_pool:
        month_last[(d.year, d.month)] = d
        iso = d.isocalendar()
        week_last[(iso.year, iso.week)] = d
    signal_dates = [d for d in sorted(month_last.values()) if d < END]
    weekly_dates = [d for d in sorted(week_last.values()) if START <= d < END]

    month_data = {}
    for i, d in enumerate(signal_dates, 1):
        members = members_at(current, changes, d)
        snap, leadership = signal_snapshot(d, members, markets, pits, sectors, cikmap)
        month_data[d] = (snap, leadership, market_context(spy, d, snap))
        if i % 12 == 0:
            print("Monthly snapshots", i, "/", len(signal_dates), flush=True)

    week_data = {}
    for i, d in enumerate(weekly_dates, 1):
        if d in month_data:
            week_data[d] = month_data[d]
        else:
            members = members_at(current, changes, d)
            snap, leadership = signal_snapshot(d, members, markets, pits, sectors, cikmap)
            week_data[d] = (snap, leadership, market_context(spy, d, snap))
        if i % 25 == 0:
            print("Weekly snapshots", i, "/", len(weekly_dates), flush=True)

    variants = [
        {"name": "SPY gate + monthly exits", "mode": "no_bear", "atr_mult": None},
        {"name": "Adaptive: correction leadership-only", "mode": "adaptive_entry", "atr_mult": None},
        {"name": "Adaptive: correction leadership + Top5 rot", "mode": "adaptive_entry", "atr_mult": None, "correction_rot_top": 5},
        {"name": "Adaptive: correction leadership + Top10 rot", "mode": "adaptive_entry", "atr_mult": None, "correction_rot_top": 10},
        {"name": "Adaptive: correction leadership + Top20 rot", "mode": "adaptive_entry", "atr_mult": None, "correction_rot_top": 20},
    ]

    states = []
    logs = {}
    for cfg in variants:
        st, siglog = run_adaptive_variant(cfg, trading_dates, signal_dates, month_data, week_data, markets)
        states.append(st)
        logs[cfg["name"]] = siglog
        print(cfg["name"], adaptive_metrics(st), flush=True)

    rep = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period": {"start": START.isoformat(), "end": END.isoformat()},
        "thresholds": ADAPTIVE_THRESHOLDS,
        "coverage": {
            "universe_symbols": len(union),
            "price_symbols": len(markets),
            "sec_symbols": len(pits),
            "monthly_snapshots": len(month_data),
            "weekly_snapshots": len(week_data),
        },
        "results": [adaptive_metrics(x) for x in states],
        "benchmark": benchmark_metrics(spy, trading_dates),
        "signal_logs": logs,
        "trades": {x.name: x.trades for x in states},
        "daily": {x.name: x.daily for x in states},
    }
    ADAPT_OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    ADAPT_OUT_JSON.write_text(json.dumps(rep, indent=2))
    ADAPT_OUT_MD.write_text(adaptive_markdown(rep))
    print(adaptive_markdown(rep), flush=True)

if __name__ == "__main__":
    adaptive_main()
