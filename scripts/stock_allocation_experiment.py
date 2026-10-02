#!/usr/bin/env python3
"""Predeclared, stock-only allocation experiment; never changes live settings.

Run with requirements-backtest.txt installed. Decisions use only information
available at each historical close; the repaired replay fills on the next open.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date
import hashlib
import json
import math
import os
from pathlib import Path
import pickle
import statistics
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from app.analysis_engine import SCORING_VERSION
from app.portfolio_engine import score_target_allocation_pct
import walkforward_backtest as wf
import wf3_offline_valuein as data


@dataclass(frozen=True)
class Variant:
    name: str
    allocation: str
    profit_taking: bool = True
    cost_bps: float = 10.0


VARIANTS = (
    Variant("Capped / profit taking", "capped"),
    Variant("Uncapped / risk budget / profit taking", "risk"),
    Variant("Full deployment / profit taking", "full"),
    Variant("Capped / no profit taking", "capped", False),
    Variant("Uncapped / risk budget / no profit taking", "risk", False),
    Variant("Full deployment / no profit taking", "full", False),
    Variant("Full deployment / profit taking / 50 bps", "full", True, 50.0),
)


def allocation_policy(mode: str):
    """Normalize conviction weights over deployable cash, with optional risk.

    Continuous targets are redistributed when a candidate hits a ceiling.
    Whole-share orders include fees; leftover cash is used only when another
    eligible share fits both the cash and risk ceilings. No prices after the
    signal date enter this calculation.
    """
    if mode == "capped":
        return None
    if mode not in {"risk", "full"}:
        raise ValueError(mode)

    def allocate(st, day, orders, analyses, market):
        cash = max(0.0, float(st.cash))
        total = wf.equity(st, market, day)
        costs = float(getattr(st, "cost_bps", wf.COST_BPS)) / 10000
        candidates = []
        for row, kind in orders:
            a = row["analysis"]
            symbol = row["symbol"]
            price = float(a.get("price") or 0)
            stop = float((a.get("levels") or {}).get("stop") or 0)
            rank = float(row.get("rank_score") or 0)
            weight = score_target_allocation_pct(rank)
            if weight <= 0 or price <= stop or stop <= 0 or cash <= 0:
                continue
            holding = st.pos.get(symbol)
            held_shares = float(holding.shares) if holding else 0.0
            risk_budget = total * 0.0075 if mode == "risk" else None
            risk_room = max(0.0, risk_budget - held_shares * (price - stop)) if risk_budget is not None else math.inf
            maxq = math.floor(cash / (price * (1 + costs)) + 1e-12)
            if risk_budget is not None:
                maxq = min(maxq, math.floor(risk_room / (price - stop) + 1e-12))
            if maxq <= 0:
                continue
            candidates.append({"symbol": symbol, "analysis": a, "rank": rank,
                               "lane": a.get("lane") or "CORE_QUALITY",
                               "reason": f"{mode.upper()} {kind} {row.get('entry_signal') or row.get('optimizer_action')}",
                               "weight": weight, "unit": price * (1 + costs),
                               "maxq": maxq, "risk_budget": risk_budget})
        if not candidates:
            return []

        # Weighted water filling in dollars, independent of iteration order.
        active = list(range(len(candidates)))
        budget = cash
        targets = [0.0] * len(candidates)
        while active and budget > 1e-9:
            weight_sum = sum(candidates[i]["weight"] for i in active)
            constrained = [i for i in active if budget * candidates[i]["weight"] / weight_sum
                           >= candidates[i]["maxq"] * candidates[i]["unit"]]
            if not constrained:
                for i in active:
                    targets[i] = budget * candidates[i]["weight"] / weight_sum
                break
            for i in constrained:
                targets[i] = candidates[i]["maxq"] * candidates[i]["unit"]
                budget -= targets[i]
                active.remove(i)
        quantities = [min(c["maxq"], math.floor(targets[i] / c["unit"] + 1e-12))
                      for i, c in enumerate(candidates)]
        remaining = cash - sum(q * c["unit"] for q, c in zip(quantities, candidates))
        # Use affordable remainder without ever enlarging a risk ceiling.
        while True:
            choices = [i for i, c in enumerate(candidates)
                       if quantities[i] < c["maxq"] and c["unit"] <= remaining + 1e-9]
            if not choices:
                break
            best = max(choices, key=lambda i: ((targets[i] / candidates[i]["unit"] - quantities[i]),
                                                candidates[i]["rank"], candidates[i]["symbol"]))
            quantities[best] += 1
            remaining -= candidates[best]["unit"]
        return [{"symbol": c["symbol"], "shares": q, "analysis": c["analysis"],
                 "reason": c["reason"], "rank": c["rank"], "lane": c["lane"],
                 "risk_budget": c["risk_budget"], "position_cap": None}
                for q, c in zip(quantities, candidates) if q > 0]

    return allocate


def month_returns(curve):
    by = defaultdict(list)
    for row in curve:
        by[row["date"][:7]].append(row)
    out = {}
    prior = wf.STARTING
    last_month = curve[-1]["date"][:7]
    for month, rows in sorted(by.items()):
        value = float(rows[-1]["equity"])
        # Oct 1 is not a complete October month. Keep it labelled separately.
        out[month] = {"return_pct": (value / prior - 1) * 100,
                      "complete": month != last_month or date.fromisoformat(rows[-1]["date"]).day >= 28}
        prior = value
    return out


def metrics(st, curve, benchmark):
    result = data.stat(st.name, st, curve)
    monthly = month_returns(curve)
    complete = [v["return_pct"] for v in monthly.values() if v["complete"]]
    result.update({
        "alpha_vs_benchmark_total_pct": result["total_return_pct"] - benchmark["total_return_pct"],
        "average_cash_pct": statistics.mean(float(r["cash"]) / float(r["equity"]) * 100 for r in curve),
        "best_complete_month_pct": max(complete) if complete else None,
        "worst_complete_month_pct": min(complete) if complete else None,
        "median_complete_month_pct": statistics.median(complete) if complete else None,
        "months_at_least_30_pct": sum(v >= 30 for v in complete),
        "complete_months": len(complete),
        "fees_paid": sum(float(t.get("fee") or 0) for t in st.trades),
        "buy_count": sum(t["side"] == "BUY" for t in st.trades),
        "sell_count": sum(t["side"] == "SELL" for t in st.trades),
        "profit_sell_count": sum(t["side"] == "SELL" and bool(t.get("profit_stage")) for t in st.trades),
        "cancelled_orders": len(getattr(st, "rejections", [])),
        "peak_position_weight_pct": max((float(r.get("largest_position_pct") or 0) for r in st.curve), default=0),
        "peak_modeled_stop_risk_pct": max((float(r.get("modeled_stop_risk_pct") or 0) for r in st.curve), default=0),
        "monthly_returns": monthly,
    })
    return result


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_manifest():
    files = ["app/analysis_engine.py", "app/portfolio_engine.py", "scripts/walkforward_backtest.py",
             "scripts/wf3_offline_valuein.py", "scripts/stock_allocation_experiment.py"]
    return {"base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "scoring_version": SCORING_VERSION,
            "source_sha256": {name: digest(ROOT / name) for name in files},
            "price_sha256": digest(data.PRICE_PATH), "fundamentals_sha256": digest(data.FUND_PATH)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke-days", type=int, default=0)
    parser.add_argument("--start", default="2024-01-02")
    parser.add_argument("--end", default="2026-10-01")
    parser.add_argument("--output", default="backtests/results/stock_allocation_experiment.json")
    parser.add_argument("--checkpoint", default=".backtest_cache/stock_allocation_experiment.checkpoint")
    parser.add_argument("--resume", action="store_true", help="Resume this script's own trusted local checkpoint")
    parser.add_argument("--max-sessions", type=int, default=0, help="Bound work per invocation; save progress and exit")
    args = parser.parse_args()
    prices = data.load_gz(data.PRICE_PATH)
    funds = data.load_gz(data.FUND_PATH)
    market = prices["market"]
    store = data.PITFundamentals(funds)
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    trading = [date.fromisoformat(r["date"]) for r in prices["benchmark"]["rows"] if start <= date.fromisoformat(r["date"]) <= end]
    if args.smoke_days:
        trading = trading[:args.smoke_days]
    states = [wf.State(v.name, 2.0, False, cost_bps=v.cost_bps) for v in VARIANTS]
    policies = [allocation_policy(v.allocation) for v in VARIANTS]
    membership = set(prices["membership"]["start_members"])
    changes = defaultdict(list)
    for change in prices["membership"]["changes"]:
        changes[date.fromisoformat(change["date"])].append(change)
    diagnostics = Counter()
    blockers = Counter()
    daily_pipeline = []
    manifest = source_manifest()
    protocol = {"version": "stock-allocation-experiment-v1", "variants": [asdict(v) for v in VARIANTS],
                "period": {"start": trading[0].isoformat(), "end": trading[-1].isoformat()},
                "starting_cash_usd": wf.STARTING, "decision_time": "NYSE session close:16:00 ET regular,13:00 ET published half days",
                "execution": "next available session open, quantities frozen at signal close and clipped at fill",
                "universe": "all cached historical S&P 500 members each day; Top20 after lane/RR eligibility",
                "entry_gates": "unchanged current fundamental/lane/action gates, priority>=68, RR>=2 at signal and fill",
                "risk_budget": "capped and risk variants: 0.75% modeled stop risk per holding; full variant removes this ceiling",
                "profit_rule": "frozen base target: cumulative25% original shares; stretch: cumulative50%; each stage once; keep runner",
                "withdrawals": "none: realized sale proceeds stay in account and await next eligible allocation",
                "split_rule": "reconstruct native date prices; adjust share entitlements and frozen anchors once",
                "selection": "predeclared comparison; no parameter fitting to achieve30%",
                "source": manifest}
    out_path = ROOT / args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.with_suffix(".protocol.json").write_text(json.dumps(protocol, indent=2) + "\n")

    checkpoint = Path(args.checkpoint)
    cursor = 0
    if args.resume and checkpoint.exists():
        # This checkpoint is generated by this process, not a user-supplied
        # research file. Never load arbitrary external pickle files.
        with checkpoint.open("rb") as stream:
            saved = pickle.load(stream)
        if saved["manifest"] != manifest or saved["protocol"] != protocol:
            raise ValueError("Checkpoint source/data/protocol changed; start a separate experiment")
        states = saved["states"]
        membership, changes = saved["membership"], saved["changes"]
        diagnostics, blockers = saved["diagnostics"], saved["blockers"]
        daily_pipeline, cursor = saved["daily_pipeline"], saved["cursor"]
        print("ALLOCATION_RESUME", cursor, "/", len(trading), flush=True)

    def save_progress(index):
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        pending_path = checkpoint.with_suffix(checkpoint.suffix + ".tmp")
        with pending_path.open("wb") as stream:
            pickle.dump({"manifest": manifest, "protocol": protocol, "states": states,
                         "membership": membership, "changes": changes, "diagnostics": diagnostics,
                         "blockers": blockers, "daily_pipeline": daily_pipeline, "cursor": index},
                        stream, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(pending_path, checkpoint)

    for index, day in enumerate(trading, 1):
        if index <= cursor:
            continue
        for changeday in sorted(d for d in changes if d <= day):
            for change in changes.pop(changeday):
                if change.get("removed"):
                    membership.discard(change["removed"])
                if change.get("added"):
                    membership.add(change["added"])
        for st in states:
            wf.advance_state(st, market, day)
        held = set().union(*(set(st.pos) for st in states))
        analyses = {}
        for symbol in sorted(membership | held):
            a = data.analyse(symbol, day, market, store, prices["membership"]["sectors"], prices["sector_etfs"])
            if a:
                analyses[symbol] = a
            else:
                diagnostics["unavailable_symbol_days"] += 1
        diagnostics["analyses"] += len(analyses)
        lane = sum(a.get("lane_qualified") is True for a in analyses.values())
        rr = sum(a.get("lane_qualified") is True and float(a.get("risk_reward") or 0) >= 2 for a in analyses.values())
        diagnostics["lane_observations"] += lane
        diagnostics["lane_rr_observations"] += rr
        for a in analyses.values():
            if a.get("lane_qualified") is not True:
                blockers.update(a.get("core_blockers") or ["unspecified lane blocker"])
            elif float(a.get("risk_reward") or 0) < 2:
                blockers["lane passes; R/R below2x"] += 1
        daily_pipeline.append({"date": day.isoformat(), "analyses": len(analyses), "lane": lane, "lane_rr": rr})
        for st, variant, policy in zip(states, VARIANTS, policies):
            wf.run_state(st, day, analyses, membership, market, allocation_policy=policy, profit_taking=variant.profit_taking)
            data.validate(st, analyses)
        if index % 10 == 0 or index == len(trading):
            save_progress(index)
        if index % 25 == 0 or index == len(trading):
            print("ALLOCATION", day, index, "/", len(trading),
                  [(st.name, round(wf.equity(st, market, day)), len(st.pos), round(st.cash)) for st in states[:3]], flush=True)
        if args.max_sessions and index - cursor >= args.max_sessions and index < len(trading):
            save_progress(index)
            print("ALLOCATION_CHECKPOINT", index, "/", len(trading), flush=True)
            return
    benchmark = wf.bench(prices["benchmark"], trading[0], trading[-1])
    bfirst = next(float(r["close"]) for r in prices["benchmark"]["rows"] if r["date"] == trading[0].isoformat())
    bcurve = [{"date": r["date"], "equity": wf.STARTING * float(r["close"]) / bfirst}
              for r in prices["benchmark"]["rows"] if trading[0].isoformat() <= r["date"] <= trading[-1].isoformat()]
    benchmark["monthly_returns"] = month_returns(bcurve)
    curves, results = {}, []
    checks = {}
    for st in states:
        curve = data.daily_curve(st, market, prices["benchmark"], trading[0], trading[-1])
        for a, b in zip(st.curve, curve):
            if abs(float(a["equity"]) - float(b["equity"])) > 0.02 or abs(float(a["cash"]) - float(b["cash"])) > 0.02:
                raise AssertionError(f"Ledger/decision curve mismatch {st.name}: {a} vs {b}")
        checks[st.name] = {"ledger_curve_match": True, "no_negative_cash": all(r["cash"] >= -1e-7 for r in curve),
                           "signal_precedes_execution": all(t.get("signal_date", t["date"]) <= t["date"] for t in st.trades)}
        curves[st.name] = curve
        results.append(metrics(st, curve, benchmark))
    if source_manifest() != manifest:
        raise AssertionError("Experiment source or data changed during run")
    closing = {}
    for st in states:
        closing[st.name] = [{"symbol": symbol, "shares": p.shares, "avg_cost": p.avg,
                             "last_quote_date": (wf.row_before(market[symbol], trading[-1]) or {}).get("date"),
                             "last_price": wf.price_asof(market[symbol], trading[-1]),
                             "profit_taken_stages": sorted(p.profit_taken_stages)} for symbol, p in sorted(st.pos.items())]
    report = {"protocol": protocol, "diagnostics": dict(diagnostics), "pipeline_blockers": dict(blockers), "daily_pipeline": daily_pipeline,
              "coverage": {"prices": prices["coverage"], "fundamentals": {k: v for k, v in funds["meta"].items() if k != "coverage"}},
              "results": results, "benchmark": benchmark, "ledger_checks": checks,
              "trades": {st.name: st.trades for st in states}, "daily_curves": curves, "benchmark_curve": bcurve,
              "cash_events": {st.name: st.cash_events for st in states},
              "rejections": {st.name: st.rejections for st in states}, "closing_positions": closing,
              "unfilled_signals_at_end": {st.name: len(st.pending) for st in states}}
    report["deterministic_hash"] = hashlib.sha256(json.dumps(report, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    out_path.write_text(json.dumps(report, indent=2) + "\n")
    print("ALLOCATION_RESULT", json.dumps({"results": [{k: v for k, v in r.items() if k != "monthly_returns"} for r in results],
                                           "benchmark": {k: v for k, v in benchmark.items() if k != "monthly_returns"},
                                           "hash": report["deterministic_hash"]}), flush=True)


if __name__ == "__main__":
    main()
