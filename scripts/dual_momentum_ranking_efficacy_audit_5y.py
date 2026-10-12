#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import statistics
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import dual_momentum_backtest_5y as dm
from dual_momentum.rules import ema_seeded

START = dm.START
END = dm.END
PRICE_START = dm.PRICE_START
SPY_START = dm.SPY_START
CUTOFFS = (20, 35, 50, 100)
WINNER_N = 20
HORIZONS = (63, 126)


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


def percentile_map(values: dict[str, float]) -> dict[str, float]:
    """Tie-neutral percentile in [0,1], larger is better."""
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
    print("RANKEFF_STAGE membership", flush=True)
    intervals, membership_source = dm.load_membership()
    overlapping = [x for x in intervals if x.overlaps(START, END)]
    symbols = sorted({x.symbol for x in overlapping})
    by_symbol_intervals = defaultdict(list)
    for x in intervals:
        by_symbol_intervals[x.symbol].append(x)
    for sym in by_symbol_intervals:
        by_symbol_intervals[sym].sort(key=lambda x: x.added)

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

    print(f"RANKEFF_STAGE prices symbols={len(symbols)}", flush=True)
    with ThreadPoolExecutor(max_workers=6) as pool:
        futs = [pool.submit(price_task, sym) for sym in symbols]
        for n, fut in enumerate(as_completed(futs), 1):
            sym, ch, err, alias = fut.result()
            if ch:
                charts[sym] = ch
                if alias:
                    alias_recoveries[sym] = alias
            else:
                price_failed[sym] = err
            if n % 100 == 0 or n == len(futs):
                print(
                    f"RANKEFF_PRICE {n}/{len(futs)} ok={len(charts)} "
                    f"fail={len(price_failed)} aliases={len(alias_recoveries)}",
                    flush=True,
                )

    spy = dm.fetch_chart("SPY", SPY_START, END + timedelta(days=3), staged=None)
    spy_dates = [r["date"] for r in spy.rows]
    spy_idx = {r["date"]: i for i, r in enumerate(spy.rows)}
    spy_test_dates = [d for d in spy_dates if START <= d <= END]

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

    def active_intervals(d):
        chosen = {}
        for x in intervals:
            if x.active(d):
                prior = chosen.get(x.symbol)
                if prior is None or x.added > prior.added:
                    chosen[x.symbol] = x
        return chosen

    # Point-in-time market-cap proxy requires SEC companyfacts for all historical issuers.
    cik_by_symbol = {}
    symbols_by_cik = defaultdict(list)
    for sym in symbols:
        rows = by_symbol_intervals.get(sym) or []
        cik = next((x.cik for x in reversed(rows) if x.cik), "")
        if cik:
            cik_by_symbol[sym] = cik
            symbols_by_cik[cik].append(sym)

    secfacts_by_cik = {}
    sec_failed = {}
    limiter = Limiter(6.0)

    def sec_task(cik):
        try:
            limiter.wait()
            fact = dm.request_json(
                dm.SEC_COMPANYFACTS.format(cik),
                attempts=4,
                headers={"User-Agent": dm.UA},
            )
            return cik, fact, None
        except Exception as exc:
            return cik, None, f"{type(exc).__name__}: {exc}"

    print(f"RANKEFF_STAGE companyfacts issuers={len(symbols_by_cik)}", flush=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = [pool.submit(sec_task, cik) for cik in sorted(symbols_by_cik)]
        for n, fut in enumerate(as_completed(futs), 1):
            cik, fact, err = fut.result()
            if fact:
                secfacts_by_cik[cik] = fact
            else:
                sec_failed[cik] = err
            if n % 75 == 0 or n == len(futs):
                print(
                    f"RANKEFF_SEC {n}/{len(futs)} ok={len(secfacts_by_cik)} fail={len(sec_failed)}",
                    flush=True,
                )

    def latest_shares_outstanding(cik, asof):
        facts = secfacts_by_cik.get(cik)
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
                # Only information available strictly before the month-end signal.
                if fd >= asof or ed > asof:
                    continue
                candidates.append((ed, fd, float(val)))
        if not candidates:
            return None
        candidates.sort()
        return candidates[-1][2]

    stock_ema200 = {
        sym: ema_seeded([r["adjclose"] for r in ch.rows], 200)
        for sym, ch in charts.items()
    }

    def persistence_inputs(sym, d):
        ch = charts.get(sym)
        if not ch:
            return None
        i = ch.index.get(d)
        if i is None or i < 252:
            return None
        em = stock_ema200.get(sym) or []
        above_ema = bool(i < len(em) and em[i] is not None and ch.rows[i]["adjclose"] > em[i])

        # Six non-overlapping ~1-month (21-session) total-return blocks.
        pos = 0
        valid = 0
        for k in range(6):
            hi = i - 21 * k
            lo = hi - 21
            if lo < 0:
                continue
            den = float(ch.rows[lo]["adjclose"])
            num = float(ch.rows[hi]["adjclose"])
            if den <= 0 or num <= 0:
                continue
            valid += 1
            if num / den - 1.0 > 0:
                pos += 1
        if valid < 6:
            return None
        return {
            "above_ema200": 1.0 if above_ema else 0.0,
            "positive_21d_block_fraction": pos / valid,
        }

    def forward_return(sym, d, sessions):
        ch = charts.get(sym)
        if not ch:
            return None
        i = ch.index.get(d)
        if i is None or i + sessions >= len(ch.rows):
            return None
        # Require a real price observation at the horizon; do not carry stale
        # delisted prices forward.
        den = float(ch.rows[i]["adjclose"])
        num = float(ch.rows[i + sessions]["adjclose"])
        if den <= 0 or num <= 0:
            return None
        horizon_date = ch.rows[i + sessions]["date"]
        # The forward horizon must fall inside the declared audit window.
        if horizon_date > END:
            return None
        return num / den - 1.0

    def make_rank(items, score_field, tie_fields=()):
        rows = [x for x in items if x.get(score_field) is not None]
        rows.sort(
            key=lambda x: tuple(
                [-float(x[score_field])]
                + [-float(x.get(f) or 0.0) for f in tie_fields]
                + [str(x["symbol"])]
            )
        )
        return {x["symbol"]: i + 1 for i, x in enumerate(rows)}

    monthly = []
    aggregate = {
        horizon: {
            target: {
                model: {
                    "months": 0,
                    "future_winners": 0,
                    "momentum_positive": 0,
                    **{f"captured_{k}": 0 for k in CUTOFFS},
                    "ranks": [],
                }
                for model in ("raw", "market_cap", "persistence")
            }
            for target in ("return", "contribution")
        }
        for horizon in HORIZONS
    }
    yearly = defaultdict(
        lambda: {
            horizon: {
                target: {
                    model: {
                        "months": 0,
                        "future_winners": 0,
                        "momentum_positive": 0,
                        **{f"captured_{k}": 0 for k in CUTOFFS},
                        "ranks": [],
                    }
                    for model in ("raw", "market_cap", "persistence")
                }
                for target in ("return", "contribution")
            }
            for horizon in HORIZONS
        }
    )

    focus_symbols = {"NVDA","AAPL","MSFT","TSLA","META","AMZN","GOOG","GOOGL","AVGO","LLY","MU","WDC","STX","SNDK","LRCX"}

    for d in month_ends:
        active = active_intervals(d)
        rows = []
        for sym, mem in active.items():
            ch = charts.get(sym)
            if not ch:
                continue
            z = dm.signal(ch, d, f"{mem.cik or sym}:{sym}")
            if not z:
                continue
            z = dict(z)
            z["sector"] = mem.sector
            z["cik"] = mem.cik or cik_by_symbol.get(sym) or ""
            z["momentum_positive"] = z["score"] > 0

            sh = latest_shares_outstanding(z["cik"], d) if z["cik"] else None
            z["market_cap_proxy"] = sh * z["signal_price"] if sh and z["signal_price"] > 0 else None

            pers = persistence_inputs(sym, d)
            z["above_ema200"] = pers["above_ema200"] if pers else None
            z["positive_21d_block_fraction"] = pers["positive_21d_block_fraction"] if pers else None
            rows.append(z)

        positive = [x for x in rows if x["momentum_positive"]]
        mom_pct = percentile_map({x["symbol"]: x["score"] for x in positive})
        mcap_pct = percentile_map({
            x["symbol"]: x["market_cap_proxy"]
            for x in positive if x["market_cap_proxy"] is not None
        })

        for x in positive:
            x["momentum_percentile"] = mom_pct.get(x["symbol"])
            x["market_cap_percentile"] = mcap_pct.get(x["symbol"])
            if x["market_cap_percentile"] is not None:
                x["market_cap_rank_score"] = statistics.mean([
                    x["momentum_percentile"],
                    x["market_cap_percentile"],
                ])
            else:
                x["market_cap_rank_score"] = None

            if x["positive_21d_block_fraction"] is not None and x["above_ema200"] is not None:
                x["persistence_rank_score"] = statistics.mean([
                    x["momentum_percentile"],
                    1.0 if x["r126"] > 0 else 0.0,
                    x["above_ema200"],
                    x["positive_21d_block_fraction"],
                ])
            else:
                x["persistence_rank_score"] = None

        raw_rank = make_rank(positive, "score", ("adv63",))
        mcap_rank = make_rank(positive, "market_cap_rank_score", ("score","adv63"))
        persistence_rank = make_rank(positive, "persistence_rank_score", ("score","adv63"))
        ranks = {"raw": raw_rank, "market_cap": mcap_rank, "persistence": persistence_rank}

        month_out = {
            "decision_date": d.isoformat(),
            "active_with_signal": len(rows),
            "positive_momentum_count": len(positive),
            "market_cap_rankable_count": len(mcap_rank),
            "persistence_rankable_count": len(persistence_rank),
            "horizons": {},
        }

        for horizon in HORIZONS:
            evaluated = []
            for x in rows:
                fr = forward_return(x["symbol"], d, horizon)
                if fr is None:
                    continue
                contribution = (
                    x["market_cap_proxy"] * fr
                    if x["market_cap_proxy"] is not None
                    else None
                )
                y = dict(x)
                y["forward_return"] = fr
                y["forward_contribution_proxy"] = contribution
                evaluated.append(y)

            if len(evaluated) < WINNER_N:
                continue

            return_winners = sorted(
                evaluated,
                key=lambda x: (-x["forward_return"], x["symbol"]),
            )[:WINNER_N]
            contribution_eligible = [x for x in evaluated if x["forward_contribution_proxy"] is not None]
            contribution_winners = sorted(
                contribution_eligible,
                key=lambda x: (-x["forward_contribution_proxy"], x["symbol"]),
            )[:WINNER_N]

            month_h = {}
            for target, winners in (("return", return_winners), ("contribution", contribution_winners)):
                if len(winners) < WINNER_N:
                    continue
                model_stats = {}
                for model, rankmap in ranks.items():
                    pos_n = sum(1 for x in winners if x["momentum_positive"])
                    captured = {
                        k: sum(
                            1 for x in winners
                            if x["momentum_positive"] and rankmap.get(x["symbol"], 10**9) <= k
                        )
                        for k in CUTOFFS
                    }
                    rank_vals = [
                        rankmap[x["symbol"]]
                        for x in winners
                        if x["symbol"] in rankmap
                    ]
                    model_stats[model] = {
                        "momentum_positive": pos_n,
                        "capture": {str(k): captured[k] for k in CUTOFFS},
                        "median_rank_if_rankable": statistics.median(rank_vals) if rank_vals else None,
                    }

                    for store in (aggregate[horizon][target][model], yearly[str(d.year)][horizon][target][model]):
                        store["months"] += 1
                        store["future_winners"] += WINNER_N
                        store["momentum_positive"] += pos_n
                        for k in CUTOFFS:
                            store[f"captured_{k}"] += captured[k]
                        store["ranks"].extend(rank_vals)

                month_h[target] = {
                    "winners": [
                        {
                            "symbol": x["symbol"],
                            "sector": x["sector"],
                            "forward_return": x["forward_return"],
                            "forward_contribution_proxy": x["forward_contribution_proxy"],
                            "momentum_score": x["score"],
                            "momentum_positive": x["momentum_positive"],
                            "raw_rank": raw_rank.get(x["symbol"]),
                            "market_cap_rank": mcap_rank.get(x["symbol"]),
                            "persistence_rank": persistence_rank.get(x["symbol"]),
                            "market_cap_proxy": x["market_cap_proxy"],
                        }
                        for x in winners
                    ],
                    "model_stats": model_stats,
                }
            month_out["horizons"][str(horizon)] = month_h

        # Compact rank trace for the names that motivated the audit.
        month_out["focus_ranks"] = {}
        by_symbol = {x["symbol"]: x for x in rows}
        for sym in sorted(focus_symbols):
            x = by_symbol.get(sym)
            if x:
                month_out["focus_ranks"][sym] = {
                    "momentum_score": x["score"],
                    "momentum_positive": x["momentum_positive"],
                    "raw_rank": raw_rank.get(sym),
                    "market_cap_rank": mcap_rank.get(sym),
                    "persistence_rank": persistence_rank.get(sym),
                    "market_cap_proxy": x["market_cap_proxy"],
                    "above_ema200": x["above_ema200"],
                    "positive_21d_block_fraction": x["positive_21d_block_fraction"],
                }
        monthly.append(month_out)
        print(
            f"RANKEFF_MONTH {d.isoformat()} signal={len(rows)} positive={len(positive)} "
            f"mcap={len(mcap_rank)} persistence={len(persistence_rank)}",
            flush=True,
        )

    def finalize_store(store):
        n = store["future_winners"]
        return {
            "months": store["months"],
            "future_winners": n,
            "momentum_positive_rate": store["momentum_positive"] / n if n else None,
            "capture_rate": {
                str(k): store[f"captured_{k}"] / n if n else None
                for k in CUTOFFS
            },
            "median_rank_if_rankable": statistics.median(store["ranks"]) if store["ranks"] else None,
        }

    aggregate_final = {
        str(h): {
            target: {
                model: finalize_store(aggregate[h][target][model])
                for model in ("raw","market_cap","persistence")
            }
            for target in ("return","contribution")
        }
        for h in HORIZONS
    }
    yearly_final = {
        year: {
            str(h): {
                target: {
                    model: finalize_store(yearly[year][h][target][model])
                    for model in ("raw","market_cap","persistence")
                }
                for target in ("return","contribution")
            }
            for h in HORIZONS
        }
        for year in sorted(yearly)
    }

    result = {
        "period": {"start": START.isoformat(), "end": END.isoformat()},
        "definitions": {
            "future_winners": "At each month-end, the 20 active S&P constituents with usable current signals and the highest realized forward total return over 63 or 126 stock sessions. A parallel target ranks the top 20 by point-in-time market-cap proxy times forward return.",
            "raw_rank": "Positive-momentum stocks ranked by unchanged M=(R63+R126+R252)/3.",
            "market_cap_rank": "Positive-momentum stocks ranked by equal-weight mean of global momentum percentile and point-in-time market-cap percentile. Market-cap proxy = latest SEC-filed EntityCommonStockSharesOutstanding available before the signal date times contemporaneous tradable close.",
            "persistence_rank": "Positive-momentum stocks ranked by equal-weight mean of global momentum percentile, indicator R126>0, indicator price>EMA200, and fraction of the six preceding non-overlapping 21-session blocks with positive total return.",
            "capture_at_k": "Fraction of realized future top-20 winners that had positive current momentum and were ranked <=K by the model at the decision date.",
            "momentum_positive_rate": "Fraction of realized future top-20 winners whose current 33/33/33 momentum was already >0. If this is low, the momentum signal/floor itself is missing future winners before ranking.",
            "contribution_proxy_caveat": "Market-cap x forward return is not exact S&P 500 contribution because float-adjusted index shares/weights are unavailable; it is a diagnostic proxy.",
        },
        "coverage": {
            "membership_source": membership_source,
            "historical_symbols": len(symbols),
            "price_symbols_ok": len(charts),
            "price_symbols_failed": len(price_failed),
            "price_symbol_coverage": len(charts) / len(symbols) if symbols else None,
            "ticker_alias_recovery_count": len(alias_recoveries),
            "ticker_alias_recoveries": alias_recoveries,
            "missing_price_symbols": sorted(price_failed),
            "companyfact_issuers_requested": len(symbols_by_cik),
            "companyfact_issuers_ok": len(secfacts_by_cik),
            "companyfact_issuers_failed": len(sec_failed),
        },
        "aggregate": aggregate_final,
        "yearly": yearly_final,
        "monthly": monthly,
    }

    out = ROOT / "backtests" / "results" / "dual_momentum_ranking_efficacy_audit_5y.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, default=str))
    print("RANKEFF_FINAL_JSON=" + json.dumps(result, separators=(",", ":"), default=str), flush=True)


if __name__ == "__main__":
    main()
