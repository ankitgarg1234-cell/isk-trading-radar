#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import statistics
import sys
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


def pct_rank(values, higher_better=True):
    if not values:
        return {}
    rows = sorted(values.items(), key=lambda kv: kv[1], reverse=higher_better)
    n = len(rows)
    if n == 1:
        return {rows[0][0]: 1.0}
    out = {}
    for idx, (k, _) in enumerate(rows):
        out[k] = 1.0 - idx / (n - 1)
    return out


def main():
    print("SECTOR5_STAGE membership", flush=True)
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
            return sym, dm.fetch_chart(sym, PRICE_START, END + timedelta(days=100), staged=staged), None, None
        except Exception as exc:
            primary_error = f"{type(exc).__name__}: {exc}"
        for alias in aliases_by_symbol.get(sym) or []:
            try:
                ach = dm.fetch_chart(alias, PRICE_START, END + timedelta(days=100), staged=staged)
                if chart_overlaps_symbol(ach, sym):
                    return sym, rekey_chart(ach, sym, alias), None, alias
            except Exception:
                pass
        return sym, None, primary_error, None

    print(f"SECTOR5_STAGE prices symbols={len(symbols)}", flush=True)
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
                print(f"SECTOR5_PRICE {n}/{len(futs)} ok={len(charts)} fail={len(price_failed)} aliases={len(alias_recoveries)}", flush=True)

    spy = dm.fetch_chart("SPY", SPY_START, END + timedelta(days=100), staged=None)
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

    stock_ema = {sym: ema_seeded([r["adjclose"] for r in ch.rows], 200) for sym, ch in charts.items()}

    def forward_return(ch, d, sessions):
        i = ch.index.get(d)
        if i is None or i + sessions >= len(ch.rows):
            return None
        a0 = float(ch.rows[i]["adjclose"])
        a1 = float(ch.rows[i + sessions]["adjclose"])
        if a0 <= 0:
            return None
        return a1 / a0 - 1.0

    monthly = []
    sector_names = set()
    total_member_month = 0
    total_signal_month = 0

    for d in month_ends:
        active = active_intervals(d)
        sigs = []
        for sym, mem in active.items():
            ch = charts.get(sym)
            if not ch:
                continue
            z = dm.signal(ch, d, f"{mem.cik or sym}:{sym}")
            if z:
                z = dict(z)
                z["sector"] = mem.sector or "Unknown"
                sigs.append(z)
        total_member_month += len(active)
        total_signal_month += len(sigs)

        sigs.sort(key=lambda z: (-z["score"], -z["adv63"], z["security_id"]))
        positive = [z for z in sigs if z["score"] > 0]
        raw_ranks = {z["symbol"]: i + 1 for i, z in enumerate(positive)}
        top20 = {z["symbol"] for z in positive[:20]}

        si = spy_idx[d]
        spy_r63 = None
        if si >= 63 and spy.rows[si-63]["adjclose"] > 0:
            spy_r63 = spy.rows[si]["adjclose"] / spy.rows[si-63]["adjclose"] - 1.0

        groups = defaultdict(list)
        for z in sigs:
            groups[z["sector"]].append(z)

        raw_sector = {}
        for sector, rows in groups.items():
            sector_names.add(sector)
            scores = [x["score"] for x in rows]
            r63s = [x["r63"] for x in rows]
            pos_breadth = sum(1 for x in rows if x["score"] > 0) / len(rows)

            ema_flags = []
            fwd21 = []
            fwd63 = []
            for x in rows:
                sym = x["symbol"]
                ch = charts.get(sym)
                ii = ch.index.get(d) if ch else None
                em = stock_ema.get(sym) or []
                if ii is not None and ii < len(em) and em[ii] is not None:
                    ema_flags.append(1.0 if ch.rows[ii]["adjclose"] > em[ii] else 0.0)
                fr21 = forward_return(ch, d, 21) if ch else None
                fr63 = forward_return(ch, d, 63) if ch else None
                if fr21 is not None:
                    fwd21.append(fr21)
                if fr63 is not None:
                    fwd63.append(fr63)

            leaders = sorted(rows, key=lambda x: (-x["score"], -x["adv63"], x["security_id"]))[:5]
            raw_sector[sector] = {
                "sector": sector,
                "constituents_with_signal": len(rows),
                "median_momentum": statistics.median(scores),
                "positive_momentum_breadth": pos_breadth,
                "ema200_breadth": statistics.mean(ema_flags) if ema_flags else None,
                "median_r63": statistics.median(r63s),
                "relative_r63_vs_spy": (statistics.median(r63s) - spy_r63) if spy_r63 is not None else None,
                "forward_21d_median_return": statistics.median(fwd21) if fwd21 else None,
                "forward_63d_median_return": statistics.median(fwd63) if fwd63 else None,
                "top20_count": sum(1 for x in rows if x["symbol"] in top20),
                "leaders": [
                    {
                        "symbol": x["symbol"],
                        "score": x["score"],
                        "r63": x["r63"],
                        "r126": x["r126"],
                        "r252": x["r252"],
                        "raw_rank": raw_ranks.get(x["symbol"]),
                        "in_global_top20": x["symbol"] in top20,
                        "forward_21d_return": forward_return(charts[x["symbol"]], d, 21),
                        "forward_63d_return": forward_return(charts[x["symbol"]], d, 63),
                    }
                    for x in leaders
                ],
            }

        metrics = [
            "median_momentum",
            "positive_momentum_breadth",
            "ema200_breadth",
            "relative_r63_vs_spy",
        ]
        pct = {}
        for m in metrics:
            vals = {s: r[m] for s, r in raw_sector.items() if r[m] is not None}
            pct[m] = pct_rank(vals, True)

        ranked = []
        for sector, row in raw_sector.items():
            components = [pct[m].get(sector) for m in metrics if sector in pct[m]]
            composite = statistics.mean(components) if components else None
            out = dict(row)
            out["composite_sector_score"] = composite
            ranked.append(out)
        ranked.sort(key=lambda x: (-(x["composite_sector_score"] if x["composite_sector_score"] is not None else -1), x["sector"]))
        for i, row in enumerate(ranked, 1):
            row["sector_rank"] = i

        monthly.append({
            "decision_date": d.isoformat(),
            "spy_r63": spy_r63,
            "sectors": ranked,
        })
        print(f"SECTOR5_MONTH {d.isoformat()} top={','.join(x['sector'] for x in ranked[:3])}", flush=True)

    # Aggregate predictive persistence: compare top-3 vs bottom-3 sectors by composite rank.
    top21, bot21, top63, bot63 = [], [], [], []
    rank_bucket_returns = defaultdict(lambda: {"f21": [], "f63": []})
    yearly_top_counts = defaultdict(lambda: defaultdict(int))
    yearly_leader_counts = defaultdict(lambda: defaultdict(int))
    year_months = defaultdict(int)

    for m in monthly:
        y = m["decision_date"][:4]
        year_months[y] += 1
        sectors = m["sectors"]
        for row in sectors[:3]:
            yearly_top_counts[y][row["sector"]] += 1
            if row["forward_21d_median_return"] is not None:
                top21.append(row["forward_21d_median_return"])
            if row["forward_63d_median_return"] is not None:
                top63.append(row["forward_63d_median_return"])
            for lead in row["leaders"][:3]:
                yearly_leader_counts[y][lead["symbol"]] += 1
        for row in sectors[-3:]:
            if row["forward_21d_median_return"] is not None:
                bot21.append(row["forward_21d_median_return"])
            if row["forward_63d_median_return"] is not None:
                bot63.append(row["forward_63d_median_return"])
        for row in sectors:
            bucket = row["sector_rank"]
            if row["forward_21d_median_return"] is not None:
                rank_bucket_returns[bucket]["f21"].append(row["forward_21d_median_return"])
            if row["forward_63d_median_return"] is not None:
                rank_bucket_returns[bucket]["f63"].append(row["forward_63d_median_return"])

    yearly_summary = {}
    for y in sorted(year_months):
        top_sectors = sorted(yearly_top_counts[y].items(), key=lambda kv: (-kv[1], kv[0]))
        leaders = sorted(yearly_leader_counts[y].items(), key=lambda kv: (-kv[1], kv[0]))
        yearly_summary[y] = {
            "month_ends": year_months[y],
            "most_frequent_top3_sectors": [{"sector": s, "months": n} for s, n in top_sectors[:6]],
            "most_frequent_top_sector_leaders": [{"symbol": s, "appearances": n} for s, n in leaders[:15]],
        }

    predictive_summary = {
        "top3_sector_avg_forward_21d": statistics.mean(top21) if top21 else None,
        "bottom3_sector_avg_forward_21d": statistics.mean(bot21) if bot21 else None,
        "top3_minus_bottom3_21d": (statistics.mean(top21) - statistics.mean(bot21)) if top21 and bot21 else None,
        "top3_sector_avg_forward_63d": statistics.mean(top63) if top63 else None,
        "bottom3_sector_avg_forward_63d": statistics.mean(bot63) if bot63 else None,
        "top3_minus_bottom3_63d": (statistics.mean(top63) - statistics.mean(bot63)) if top63 and bot63 else None,
        "by_sector_rank": {
            str(rank): {
                "avg_forward_21d": statistics.mean(vals["f21"]) if vals["f21"] else None,
                "avg_forward_63d": statistics.mean(vals["f63"]) if vals["f63"] else None,
                "observations_21d": len(vals["f21"]),
                "observations_63d": len(vals["f63"]),
            }
            for rank, vals in sorted(rank_bucket_returns.items())
        },
    }

    result = {
        "period": {"start": START.isoformat(), "end": END.isoformat()},
        "definitions": {
            "stock_momentum": "(R63 + R126 + R252) / 3 on dividend-reinvested adjusted close.",
            "sector_median_momentum": "Median stock momentum among point-in-time sector constituents with usable signals.",
            "positive_momentum_breadth": "Fraction of sector constituents with momentum > 0.",
            "ema200_breadth": "Fraction of usable sector constituents above their own seeded EMA200.",
            "relative_r63_vs_spy": "Sector median constituent R63 minus SPY R63.",
            "composite_sector_score": "Equal-weight average percentile rank of sector median momentum, positive-momentum breadth, EMA200 breadth, and 63-day relative return vs SPY. Diagnostic only; not a trading rule.",
            "leaders": "Top 5 stocks inside each sector by the same 33/33/33 momentum score.",
            "forward_returns": "Median subsequent total-return of the sector's decision-date constituents over 21 and 63 sessions; diagnostic only.",
        },
        "coverage": {
            "membership_source": membership_source,
            "historical_symbols": len(symbols),
            "price_symbols_ok": len(charts),
            "price_symbols_failed": len(price_failed),
            "price_symbol_coverage": len(charts) / len(symbols) if symbols else 0.0,
            "member_month_signal_coverage": total_signal_month / total_member_month if total_member_month else 0.0,
            "ticker_alias_recovery_count": len(alias_recoveries),
            "ticker_alias_recoveries": alias_recoveries,
            "missing_price_symbols": sorted(price_failed),
        },
        "sectors_seen": sorted(sector_names),
        "predictive_summary": predictive_summary,
        "yearly_summary": yearly_summary,
        "monthly": monthly,
    }

    out = ROOT / "backtests" / "results" / "dual_momentum_sector_leadership_audit_5y.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, default=str))
    print("SECTOR5_FINAL_JSON=" + json.dumps(result, separators=(",", ":"), default=str), flush=True)


if __name__ == "__main__":
    main()
