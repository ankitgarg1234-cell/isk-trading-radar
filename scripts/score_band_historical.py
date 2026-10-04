"""Resumable, offline historical audit and strict event replay.

No credentials, network requests, broker calls or production database writes.
The existing daily cache is audited, never misrepresented as the intraday model.
Run `python scripts/score_band_historical.py --help` for the interface.
"""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import html
import json
import math
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.analysis_engine import score_bundle
from app.score_band_experiment import advance, equity, experiment_spec, new_state, number, timestamp

NY = ZoneInfo("America/New_York")
VERSION = "score-bands-history-v1"
REQUIRED_EVIDENCE = {"analyst", "fundamentals", "news", "universe", "price"}
HOLIDAYS = {
    2024: {"01-01", "01-15", "02-19", "03-29", "05-27", "06-19", "07-04", "09-02", "11-28", "12-25"},
    2025: {"01-01", "01-09", "01-20", "02-17", "04-18", "05-26", "06-19", "07-04", "09-01", "11-27", "12-25"},
}
EARLY_CLOSES = {2024: {"07-03", "11-29", "12-24"}, 2025: {"07-03", "11-28", "12-24"}}


def sessions(start, end):
    a, b = date.fromisoformat(start), date.fromisoformat(end)
    if a.year not in HOLIDAYS or b.year not in HOLIDAYS:
        raise ValueError("Verified session calendar currently supports 2024 and 2025 only")
    out = []
    while a <= b:
        if a.weekday() < 5 and a.strftime("%m-%d") not in HOLIDAYS[a.year]:
            out.append(a.isoformat())
        a += timedelta(days=1)
    return out


def session_close(dt):
    local = dt.astimezone(NY)
    ds = local.date().isoformat()
    if not sessions(ds, ds):
        return None
    return time(13) if local.strftime("%m-%d") in EARLY_CLOSES[local.year] else time(16)


def regular_market_open(dt):
    close = session_close(dt)
    return close is not None and time(9, 30) <= dt.astimezone(NY).time() < close


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_json(path, value):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    tmp.replace(p)


def load_gzip(path):
    with gzip.open(path, "rt") as f:
        return json.load(f)


def freeze(start, end, price_path, fund_path, archive=None):
    if date.fromisoformat(start) > date.fromisoformat(end):
        raise ValueError("Start is after end")
    return {
        "version": VERSION, "start": start, "end": end, "strategy": experiment_spec("HIGH"),
        "source_hashes": {"prices": file_hash(price_path), "fundamentals": file_hash(fund_path),
                          "archive": file_hash(archive) if archive else None},
        "code_hashes": {name: file_hash(ROOT / name) for name in (
            "scripts/score_band_historical.py", "app/score_band_experiment.py",
            "app/analysis_engine.py", "app/portfolio_engine.py")},
        "policy": "Fixed present-day rules applied retrospectively; no fitting or parameter search. Not an out-of-sample validation.",
        "execution": "Same frozen intraday paper engine; later quotes only; 10-minute buy expiry preserved",
        "benchmark": "S&P 500 total return, USD, previous year-end close to year-end close",
        "stock_dividends": "Omitted to match frozen paper strategy; benchmark includes reinvested dividends",
    }


class Checkpoint:
    """A transaction commits a whole monthly audit / event batch or none of it."""
    def __init__(self, path, protocol):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=20)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS chunks (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        prior = self.db.execute("SELECT value FROM metadata WHERE key='protocol'").fetchone()
        serialized = json.dumps(protocol, sort_keys=True, separators=(",", ":"))
        if prior and prior[0] != serialized:
            self.db.close()
            raise ValueError("Checkpoint inputs or frozen code differ; choose a new checkpoint path")
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO metadata VALUES ('protocol', ?)", (serialized,))

    def get(self, key):
        row = self.db.execute("SELECT value FROM chunks WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, key, value):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO chunks VALUES (?, ?)", (key, json.dumps(value, allow_nan=False)))

    def close(self):
        self.db.close()


def benchmark_years(rows, start, end):
    by_year = defaultdict(list)
    for r in sorted(rows, key=lambda x: x["date"]):
        close = number(r.get("close"))
        if close and close > 0:
            by_year[int(r["date"][:4])].append(r)
    out = []
    for y in range(int(start[:4]), int(end[:4]) + 1):
        prev = by_year.get(y - 1) or []
        current = [r for r in by_year.get(y, []) if start <= r["date"] <= end]
        requested_full = start <= f"{y}-01-01" and end >= f"{y}-12-31"
        expected = sessions(f"{y}-01-01", f"{y}-12-31")
        prior_end = date(y-1, 12, 31)
        while prior_end.weekday() >= 5:
            prior_end -= timedelta(days=1)
        full = requested_full and bool(prev and current) and prev[-1]["date"] == prior_end.isoformat() and current[-1]["date"] == expected[-1]
        baseline = prev[-1] if prev and full else None
        finish = current[-1] if current else None
        out.append({"year": y, "full_calendar_year": full, "baseline_date": baseline["date"] if baseline else None,
            "baseline_level": baseline["close"] if baseline else None,
            "end_date": finish["date"] if finish else None, "end_level": finish["close"] if finish else None,
            "benchmark_return_pct": round(100 * (finish["close"] / baseline["close"] - 1), 4) if baseline and finish else None,
            "strategy_return_pct": None, "excess_return_pp": None})
    return out


def audit_month(month, prices, funds, accepted, start, end):
    rows = [r for r in prices["benchmark"]["rows"] if r["date"].startswith(month) and start <= r["date"] <= end]
    expected = [s for s in sessions(start, end) if s.startswith(month)]
    members = set(prices["membership"]["start_members"])
    changes = sorted(prices["membership"]["changes"], key=lambda x: x["date"])
    missing = Counter()
    for day in sorted(r["date"] for r in rows):
        while changes and changes[0]["date"] <= day:
            change = changes.pop(0)
            members.discard(change.get("removed"))
            if change.get("added"):
                members.add(change["added"])
        for sym in members:
            if sym not in prices["market"]:
                missing[sym] += 1
    # Count distinct accessions, not repeated values for every concept.
    late = {acc for acc, dt in accepted.items() if dt.astimezone(NY).strftime("%Y-%m") == month
            and not regular_market_open(dt)}
    # Separately retain the legacy same-close leaks, excluding before-open
    # acceptance which could legitimately feed a later close decision.
    after_close = {acc for acc, dt in accepted.items() if dt.astimezone(NY).strftime("%Y-%m") == month
        and (not sessions(dt.astimezone(NY).date().isoformat(), dt.astimezone(NY).date().isoformat())
             or dt.astimezone(NY).time() >= (time(13) if dt.astimezone(NY).strftime("%m-%d") in EARLY_CLOSES[dt.astimezone(NY).year] else time(16)))}
    return {"month": month, "sessions": len(rows), "missing_price_member_days": sum(missing.values()),
        "missing_price_symbols": sorted(missing), "filings_after_close_or_weekend": len(after_close),
        "filings_outside_regular_session": len(late),
        "benchmark_missing_dates": sorted(set(expected) - {r["date"] for r in rows}),
        "benchmark_unexpected_dates": sorted({r["date"] for r in rows} - set(expected)),
        "historical_analyst_observations": 0, "strict_strategy_return_pct": None}


def audit_cached(prices, funds, protocol, cp, max_new_chunks=0):
    accepted = {}
    fact_count = 0
    derived_unproven = 0
    for vals in funds["facts"].values():
        for r in vals:
            fact_count += 1
            dt = timestamp(r.get("accepted_at"))
            if dt and protocol["start"] <= dt.astimezone(NY).date().isoformat() <= protocol["end"]:
                accepted[r["accession_id"]] = dt
            if r.get("derived_quarterly_value") is not None and not 60 <= (number(r.get("period_span_days")) or 0) <= 125:
                derived_unproven += 1
    # Plan from the requested range, so a missing month is audited as a gap.
    months = sorted({s[:7] for s in sessions(protocol["start"], protocol["end"])})
    completed = []
    new = 0
    for month in months:
        key = "audit:" + month
        value = cp.get(key)
        if value is None:
            if max_new_chunks and new >= max_new_chunks:
                break
            value = audit_month(month, prices, funds, accepted, protocol["start"], protocol["end"])
            cp.put(key, value)
            new += 1
            print(f"AUDIT {month} saved ({len(completed)+1}/{len(months)})", flush=True)
        completed.append(value)
    ready = len(completed) == len(months)
    blockers = [
        {"code": "analyst_archive_absent", "detail": "No dated historical analyst counts/targets with verified availability and revision history."},
        {"code": "intraday_archive_absent", "detail": "Daily OHLC cannot reproduce next fresh quote fills or ten-minute entry expiry."},
        {"code": "full_universe_absent", "detail": "Historical S&P constituent sample only, not the full U.S. scanner universe."},
        {"code": "delisted_prices_missing", "detail": f"{len(prices['coverage']['price_failed'])} historical symbols have no cached prices; affected member-days are reported rather than silently excluded."},
        {"code": "news_archive_absent", "detail": "General news, publication timestamps and material-negative history are absent; filings alone cannot recreate them."},
        {"code": "corporate_action_basis_unverified", "detail": "Yahoo OHLC is split-adjusted; exact as-traded prices/volume, splits and spinoff/cash events need a verified bridge."},
        {"code": "fundamental_provenance_incomplete", "detail": "Use accepted_at, not filing_date; derived quarters require audited contemporaneous source dependencies."},
        {"code": "sector_history_incomplete", "detail": "Current sector classifications do not establish historical classifications for all former members."},
    ]
    absent_dates = sorted({d for chunk in completed for d in chunk["benchmark_missing_dates"]})
    if absent_dates:
        blockers.append({"code": "benchmark_session_gaps", "detail": f"{len(absent_dates)} expected benchmark sessions are absent."})
    return {"status": "completed_with_data_gaps" if ready else "paused", "run_completed": ready,
        "performance_valid": False, "strategy_yield": None, "protocol": protocol,
        "benchmark_symbol": prices["benchmark_symbol"],
        "annual_comparison": benchmark_years(prices["benchmark"]["rows"], protocol["start"], protocol["end"]),
        "coverage": {"price_universe": prices["coverage"]["universe"], "price_symbols": len(prices["market"]),
            "missing_price_symbols": prices["coverage"]["price_failed"], "fundamental_symbols": len(funds["facts"]),
            "usable_fundamental_symbols": funds["meta"]["usable_fundamental_symbols"], "fact_rows": fact_count,
            "months_completed": len(completed), "months_planned": len(months), "sessions": sum(r["sessions"] for r in completed),
            "benchmark_missing_dates": absent_dates,
            "unproven_derived_quarter_facts": derived_unproven,
            "after_close_or_weekend_accessions": sum(r["filings_after_close_or_weekend"] for r in completed),
            "missing_price_member_days": sum(r["missing_price_member_days"] for r in completed)},
        "monthly_chunks": completed, "blockers": blockers,
        "interpretation": "Audit finished, not an invested strategy result. Missing required inputs are not replaced with present-day data, relaxed gates or a 0% cash return."}


def valid_time(value):
    dt = timestamp(value)
    if dt is None or not str(value).endswith(("Z", "+00:00")):
        raise ValueError("Explicit UTC availability timestamp required")
    return dt


def observation_from_record(record, event_at):
    """Recompute scores from archived raw inputs; never accept supplied scores."""
    now = valid_time(event_at)
    bundle = copy.deepcopy(record["bundle"])
    forbidden = {"thesis_assessment", "negative_news_override", "promotion_risk", "strategic_capital"}
    if forbidden & bundle.keys():
        raise ValueError("Externally derived thesis/strategic overrides are not supported without independent lineage audit")
    quote = valid_time(bundle["data_sources"]["price"]["quote_asof"])
    if not 0 <= (now - quote).total_seconds() <= 600:
        raise ValueError("Missing/stale/future exchange quote")
    kinds = set()
    for e in record.get("evidence", []):
        kinds.add(e["kind"])
        if not e.get("source") or e.get("availability_basis") != "verified_publication":
            raise ValueError("Period labels or today's collection date do not prove historical availability")
        if valid_time(e["available_at"]) > quote:
            raise ValueError("Forward input rejected")
    if not REQUIRED_EVIDENCE <= kinds:
        raise ValueError("Required historical evidence missing")
    prior_bar = None
    for bar in bundle.get("history", []):
        day = str(bar["date"])
        if day > quote.astimezone(NY).date().isoformat() or (prior_bar and day <= prior_bar):
            raise ValueError("Future, unordered or duplicate history date")
        prior_bar = day
        if valid_time(bar.get("available_at")) > quote:
            raise ValueError("Future / unclosed price bar rejected")
    for fact in record.get("fundamental_facts", []):
        if str(fact.get("period_end") or "")[:10] > quote.astimezone(NY).date().isoformat():
            raise ValueError("Future financial period rejected")
        if valid_time(fact["accepted_at"]) > quote:
            raise ValueError("Unaccepted fundamental fact rejected")
        if fact.get("derived") and not fact.get("source_accessions"):
            raise ValueError("Unproven derived fundamental rejected")
    if not record.get("fundamental_facts"):
        raise ValueError("Fundamental calculation lineage is required")
    for article in bundle.get("news", []):
        if float(article["providerPublishTime"]) > quote.timestamp():
            raise ValueError("Future news rejected")
    sector = bundle.get("sector_benchmark") or {}
    prior_bar = None
    for bar in sector.get("history", []):
        day = str(bar["date"])
        if day > quote.astimezone(NY).date().isoformat() or (prior_bar and day <= prior_bar):
            raise ValueError("Future, unordered or duplicate sector date")
        prior_bar = day
        if valid_time(bar.get("available_at")) > quote:
            raise ValueError("Future sector bar rejected")
    scored = score_bundle(bundle)
    out = {**bundle, **scored, "asof": quote.isoformat(), "collected_at": event_at}
    # Breakout anchor excludes the running daily bar exactly as live capture does.
    completed = [r for r in bundle.get("history", []) if r["date"] < quote.astimezone(NY).date().isoformat()]
    atr = number((out.get("technicals") or {}).get("atr"))
    if len(completed) >= 20 and atr and out.get("levels"):
        high = max(float(r["close"]) for r in completed[-20:])
        out["levels"]["breakout"] = round(high + .1 * atr, 4)
        out["levels"]["do_not_chase"] = round(min(out["levels"]["do_not_chase"], high + 1.1 * atr), 4)
    return out


def validate_book(state):
    b = state["variants"]["complete_strategy"]
    if not math.isfinite(b["cash"]) or b["cash"] < -1e-7:
        raise ValueError("Cash invariant failed")
    for p in b["positions"].values():
        if p["shares"] < 1 or p["shares"] != int(p["shares"]):
            raise ValueError("Whole-share position invariant failed")
    for t in b["trades"]:
        if t["side"] == "BUY" and valid_time(t["signal_at"]) >= valid_time(t["observed_at"]):
            raise ValueError("A signal cannot fill at its own or an earlier quote")


def replay_events(path, protocol, cp, max_new_chunks=0):
    """Stream bounded groups; incomplete/invalid archives never yield an ROI."""
    saved = cp.get("replay") or {"index": 0, "state": new_state("HIGH"), "curves": [], "errors": [], "last_time": None}
    manifest = None
    ordinal = 0
    prior = None
    processed = 0
    with Path(path).open() as f:
        manifest = json.loads(next(f))
        required = {"universe": "historical_US_equities", "price_basis": "as_traded",
                    "includes_delisted": True, "coverage_complete": True, "publication_times_verified": True}
        if any(manifest.get(k) != v for k, v in required.items()):
            raise ValueError("Archive coverage/basis manifest does not satisfy full strategy protocol")
        if manifest.get("start") != protocol["start"] or manifest.get("end") != protocol["end"]:
            raise ValueError("Archive period does not match protocol")
        for line in f:
            event = json.loads(line)
            ordinal += 1
            when = valid_time(event["event_at"])
            if prior is not None and when <= prior:
                raise ValueError("Events must be strictly chronological, grouped by polling time")
            prior = when
            if ordinal <= saved["index"]:
                continue
            if max_new_chunks and processed >= max_new_chunks:
                cp.put("replay", saved)
                return {"status": "paused", "run_completed": False, "performance_valid": False, "events": saved["index"]}
            if not protocol["start"] <= when.astimezone(NY).date().isoformat() <= protocol["end"]:
                raise ValueError("Event outside frozen date range")
            # Work on a copy: a bad batch cannot leave partially applied fills.
            candidate = copy.deepcopy(saved)
            try:
                if event.get("kind") == "valuation":
                    b = candidate["state"]["variants"]["complete_strategy"]
                    close = session_close(when)
                    if close is None:
                        raise ValueError("Closing valuation is not on a trading session")
                    if when.astimezone(NY).time() < close:
                        raise ValueError("Closing valuation precedes session close")
                    marks = event.get("marks") or {}
                    if not set(b["positions"]) <= set(marks):
                        raise ValueError("Missing closing mark for held position")
                    for sym, mark in marks.items():
                        mt = valid_time(mark["quote_asof"])
                        if mt > when or (when - mt).total_seconds() > 600 or mt.astimezone(NY).date() != when.astimezone(NY).date() or mt.astimezone(NY).time() < close or number(mark.get("price")) is None or mark["price"] <= 0:
                            raise ValueError("Invalid closing mark")
                        b["marks"][sym] = mark["price"]
                    candidate["curves"].append({"date": when.astimezone(NY).date().isoformat(), "equity": equity(b), "cash": b["cash"]})
                elif event.get("kind", "poll") == "poll":
                    local = when.astimezone(NY)
                    opened = regular_market_open(when)
                    if event.get("market_open") is not opened:
                        raise ValueError("Session flag inconsistent with regular-hours timestamp")
                    rows = [observation_from_record(r, event["event_at"]) for r in event.get("records", [])]
                    if len({r["symbol"] for r in rows}) != len(rows):
                        raise ValueError("Duplicate symbol in event")
                    advance(candidate["state"], rows, event["event_at"], opened)
                else:
                    raise ValueError("Unsupported event kind: corporate actions need a verified integration")
                validate_book(candidate["state"])
            except (ValueError, KeyError, TypeError, OverflowError) as e:
                saved["errors"].append({"event": ordinal, "at": event["event_at"], "error": str(e)})
                # An invalid batch is quarantined. Completion is reported, but
                # performance remains unavailable until all gaps are repaired.
            else:
                saved = candidate
            saved["index"], saved["last_time"] = ordinal, event["event_at"]
            cp.put("replay", saved)
            processed += 1
    expected = manifest.get("expected_valuation_dates") or []
    actual = [r["date"] for r in saved["curves"]]
    good = bool(expected) and actual == expected and not saved["errors"]
    # Timestamps and manifest flags are integrity checks, not independent
    # verification of metric derivations, analyst revisions, source coverage,
    # corporate actions, delisting proceeds or publication-time claims.
    # Never let a self-asserted archive publish an investment result.
    return {"status": "completed_mechanics_only" if good else "completed_with_data_gaps", "run_completed": True,
        "mechanics_valid": good, "performance_valid": False,
        "performance_blocker": "Independent source/derivation audit and corporate-action integration required",
        "events": saved["index"], "errors": saved["errors"],
        "curves": saved["curves"], "trades": saved["state"]["variants"]["complete_strategy"]["trades"],
        "state": saved["state"], "expected_valuation_dates": expected}


def compare_replay(report, replay, benchmark_rows):
    # This version intentionally cannot certify an uploaded archive merely
    # because its header claims to be complete. The cached-data audit verdict
    # and null strategy yield persist after a mechanics-only run.
    valid = replay.get("performance_valid") is True
    required_dates = [r["date"] for r in benchmark_rows if report["protocol"]["start"] <= r["date"] <= report["protocol"]["end"]]
    valid = valid and replay.get("expected_valuation_dates") == required_dates
    report["performance_valid"] = valid
    report["replay"] = {k: v for k, v in replay.items() if k != "state"}
    if not valid:
        return report
    closes = {r["date"]: r["equity"] for r in replay["curves"]}
    prev = 10000.0
    for row in report["annual_comparison"]:
        value = closes.get(row["end_date"])
        if value is None or not row["full_calendar_year"] or row["benchmark_return_pct"] is None:
            report["performance_valid"] = False
            break
        row["strategy_return_pct"] = round(100 * (value / prev - 1), 4)
        row["excess_return_pp"] = round(row["strategy_return_pct"] - row["benchmark_return_pct"], 4)
        prev = value
    if not report["performance_valid"]:
        for row in report["annual_comparison"]:
            row["strategy_return_pct"] = row["excess_return_pp"] = None
    else:
        report["status"] = "completed"
        report["strategy_yield"] = round(100 * (prev / 10000 - 1), 4)
        report["blockers"] = []
        report["interpretation"] = "Completed archived event replay. Validation of supplied source assertions remains required; retrospective rules are not an out-of-sample test."
    return report


def render_report(report, output):
    def pct(v): return "Unavailable" if v is None else f"{v:+.2f}%"
    annual = "".join(f'<tr><td>{r["year"]}</td><td>{pct(r["strategy_return_pct"])}</td><td>{pct(r["benchmark_return_pct"])}</td><td>{pct(r["excess_return_pp"])}</td></tr>' for r in report["annual_comparison"])
    issues = "".join(f'<li>{html.escape(b["detail"])}</li>' for b in report["blockers"])
    c = report["coverage"]
    marks = "".join(f'<tr><td>{r["year"]}</td><td>{r["baseline_date"]}: {r["baseline_level"]:,.4f}</td><td>{r["end_date"]}: {r["end_level"]:,.4f}</td></tr>' for r in report["annual_comparison"] if r["baseline_level"] and r["end_level"])
    verdict = "Backtest completed" if report["performance_valid"] else "Historical audit complete. Full-strategy yield unavailable." if report["run_completed"] else "Historical audit paused. Full-strategy yield unavailable."
    content = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Score-band historical test</title>
<style>body{{font-family:system-ui,sans-serif;background:#f4f6f8;color:#192d38;margin:0;line-height:1.6}}main{{max-width:1040px;margin:auto;padding:42px 24px}}h1{{font-size:34px;line-height:1.2;margin:10px 0 20px}}h2{{font-size:22px;margin-top:32px}}.label{{font-size:13px;letter-spacing:.1em;text-transform:uppercase;color:#526873}}.callout{{background:#fff6df;border-left:4px solid #b87c0a;padding:18px 22px}}.panel{{background:white;border:1px solid #dfe5e8;border-radius:10px;padding:22px;margin-top:22px}}table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;border-bottom:1px solid #e1e7ea;padding:12px}}th{{font-size:13px;color:#42606d}}.scroll{{overflow:auto}}.muted{{color:#526873;font-size:14px}}li{{margin:10px 0}}code{{font-size:12px;overflow-wrap:anywhere}}@media(max-width:600px){{main{{padding:22px 16px}}h1{{font-size:27px}}.panel{{padding:15px}}table{{min-width:510px}}}}</style>
<main><div class="label">Current agreed strategy · historical audit · 4 October 2026</div><h1>{verdict}</h1>
<div class="callout"><strong>{html.escape(report['interpretation'])}</strong><p>The {report['protocol']['start']} to {report['protocol']['end']} cached-data audit completed {c['months_completed']} of {c['months_planned']} monthly chunks, covering {c['sessions']} trading sessions. No production account was used.</p></div>
<section class="panel"><h2>Calendar-year comparison</h2><div class="scroll"><table><thead><tr><th>Year</th><th>Agreed strategy</th><th>S&amp;P 500 total return</th><th>Excess return</th></tr></thead><tbody>{annual}</tbody></table></div>
<p class="muted">Benchmark returns are calculated from cached Yahoo ^SP500TR year-end levels below. USD, dividends reinvested. Strategy returns are not reported as zero when data is missing. Stock dividends remain omitted to reproduce the frozen paper model.</p></section>
<section class="panel"><h2>Data coverage</h2><p>{c['price_symbols']} price histories out of {c['price_universe']} historical S&amp;P symbols; {c['fundamental_symbols']} fundamental symbols, {c['usable_fundamental_symbols']} with usable revenue/equity facts. This is a historical S&amp;P sample, not the full U.S. market.</p>
<p>{c['fact_rows']:,} SEC fact rows audited; {c['after_close_or_weekend_accessions']:,} filing accessions occurred after the regular close or on weekends; {c['missing_price_member_days']:,} historical member-days lack price files.</p>
<h2>What prevents an honest full replay</h2><ul>{issues}</ul></section>
<section class="panel"><h2>Rules frozen before running</h2><p>One $10,000 account. HIGH risk profile: 1.25% planned downside per position. Deterministic ≥70, analyst ≥75, entry R/R ≥0.4×. Score bands: 10%, 15%, 20%, 30%, 40%. Whole shares, highest-score cash priority, 10 bps fees and 5 bps slippage per side. Initial stop, one-time profit-sized withdrawal and momentum trailing stop retained.</p>
<p>Signals and fills are processed chronologically. A buy requires a later quote within ten minutes and rechecks the frozen target, stop and entry gates. Daily next-open fills would change the strategy and are not silently substituted.</p></section>
<section class="panel"><h2>Completion and integrity controls</h2><ul><li>Immutable input and code hashes; changed data or rules require a fresh run.</li><li>Transactional checkpoints after each monthly audit or replay event. An interrupted process resumes from its last committed batch.</li><li>Offline replay: data acquisition happens separately, so provider outages cannot interrupt an already staged simulation.</li><li>Source publication times, SEC acceptance times and completed price bars must precede the decision quote. Month labels alone do not establish availability.</li><li>Rejected batches are quarantined and reported. Missing evidence prevents performance publication.</li><li>Restart equality, future-data rejection, delayed fills, whole shares and annual-return denominator tests run before the full audit.</li></ul></section>
<section class="panel"><h2>Benchmark source levels</h2><div class="scroll"><table><tr><th>Year</th><th>Prior year-end close</th><th>Year-end close</th></tr>{marks}</table></div><p class="muted">Source: backtests/staged/wf3_prices.json.gz, benchmark ^SP500TR. Price-input SHA-256: <code>{report['protocol']['source_hashes']['prices']}</code></p>
<p class="muted">These rules were developed after the test years and earlier experiments used this history. Eliminating future inputs does not eliminate strategy-selection or data-mining bias; this is retrospective validation, not untouched out-of-sample evidence.</p></section>
<section class="panel"><h2>Remaining work for a full strategy backtest</h2><p>An immutable historical observation archive with genuine analyst snapshots and publication/revision timestamps, as-traded intraday quotes, accepted financial facts, timestamped news, historical eligibility including delisted stocks, corporate actions and complete daily closing marks.</p><p>The current event replay tests mechanics using the same paper execution engine. Independent source and metric-derivation checks and corporate-action integration still need to be implemented once suitable historical sources are available. An archive claiming to be complete cannot unlock a strategy return in this version.</p></section></main></html>'''
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(content)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default="2024-01-01")
    ap.add_argument("--end", default="2025-12-31")
    ap.add_argument("--prices", default=str(ROOT / "backtests/staged/wf3_prices.json.gz"))
    ap.add_argument("--fundamentals", default=str(ROOT / "backtests/staged/wf3_valuein_fundamentals.json.gz"))
    ap.add_argument("--archive", help="Immutable, chronologically grouped raw observation JSONL archive")
    ap.add_argument("--checkpoint", default=str(ROOT / "backtests/checkpoints/score_bands_2024_2025.sqlite"))
    ap.add_argument("--output", default=str(ROOT / "backtests/results/score_bands_2024_2025.json"))
    ap.add_argument("--html", default=str(ROOT / "backtests/results/score_bands_2024_2025.html"))
    ap.add_argument("--max-new-chunks", type=int, default=0, help="Bounded invocation; zero processes all remaining chunks")
    args = ap.parse_args()
    cp = None
    try:
        protocol = freeze(args.start, args.end, args.prices, args.fundamentals, args.archive)
        cp = Checkpoint(args.checkpoint, protocol)
        prices, funds = load_gzip(args.prices), load_gzip(args.fundamentals)
        report = audit_cached(prices, funds, protocol, cp, args.max_new_chunks)
        if args.archive and report["run_completed"]:
            replay = replay_events(args.archive, protocol, cp, args.max_new_chunks)
            report = compare_replay(report, replay, prices["benchmark"]["rows"])
            if not replay["run_completed"]:
                report["status"] = "paused"
                report["run_completed"] = False
        report["result_hash"] = digest({k: v for k, v in report.items() if k != "result_hash"})
        atomic_json(args.output, report)
        render_report(report, args.html)
        print(json.dumps({"status": report["status"], "performance_valid": report["performance_valid"], "annual_comparison": report["annual_comparison"], "coverage": report["coverage"], "result_hash": report["result_hash"]}), flush=True)
        return 0
    except Exception as e:
        # Do not overwrite an existing successful result with a resume mismatch.
        atomic_json(str(args.output) + ".error.json", {"status": "needs_attention", "error_type": type(e).__name__, "error": str(e), "checkpoint_preserved": True})
        print(f"NEEDS_ATTENTION {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        return 2
    finally:
        if cp:
            cp.close()


if __name__ == "__main__":
    raise SystemExit(main())
