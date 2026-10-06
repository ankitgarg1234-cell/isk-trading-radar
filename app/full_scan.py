"""Resumable after-hours universe audit. Never invokes either paper engine."""
from __future__ import annotations

import csv
import io
import json
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func

from .analysis_engine import SCORING_VERSION, CORE_MIN_AVG_DOLLAR_VOLUME, technicals, pct, fundamental_input_diagnostics
from .db import SessionLocal, FullScanRun, FullScanResult, RadarCandidate
from .market_evidence import transient_missing, positive
from .trading_rules import entry_status, number

NY = ZoneInfo("America/New_York")
ACTIVE = {"prefilter", "analysis", "paused_market_open", "paused_live_priority"}
KEY = "latest"
# Scoring-only/evidence changes do not alter the exact price/currency/liquidity
# preflight. Same-session quick checks may be reused, but old scores/gates never are.
REUSABLE_PREFILTER_VERSIONS = {
    "2026-10-06-score-evidence-integrity-v19",
    "2026-10-06-sec-filing-coverage-v20",
}


def now():
    return datetime.now(timezone.utc)


def dumps(value):
    return json.dumps(value, default=str, separators=(",", ":"), allow_nan=False)


def compact_result(full, source="fresh_analysis"):
    """Recompute canonical gates; a cached BUY string or rounded R/R is irrelevant."""
    status = entry_status(full)
    f, t = full.get("fundamentals") or {}, full.get("technicals") or {}
    score, analyst, rr = (number(full.get("deterministic_score")),
                          number(full.get("analyst_score")), number(status["risk_reward"]))
    points = {k: number(v) for k, v in (full.get("breakdown") or {}).items()}
    diagnostics = fundamental_input_diagnostics(f)
    price = number(full.get("price"))
    temporary_gap = (analyst is None and transient_missing(f, "analyst")) or (
        not any(positive(f.get(k)) for k in ("forwardPE", "trailingPE")) and transient_missing(f, "valuation")) or (
        not positive(f.get("marketCap")) and transient_missing(f, "market_cap"))
    return {"symbol": full["symbol"], "status": "scored", "source": source,
        "price": price, "deterministic_score": score, "analyst_score": analyst,
        "risk_reward": rr, "qualified": status["qualified"], "ready_at_quote": status["ready"],
        "blocker": status["blocker"], "reason": status["reason"], "lane": full.get("lane"),
        "breakdown": points,
        "score_calibration": full.get("score_calibration"),
        "score_contributions": {k: number(v) for k, v in (full.get("score_contributions") or {}).items()},
        "core_blockers": full.get("core_blockers") or [],
        **diagnostics,
        "fundamental_confidence": full.get("fundamental_confidence"),
        "fundamental_reasons": full.get("fundamental_reasons") or [],
        "sector": f.get("sector"), "fundamental_period": f.get("_fundamental_period"),
        "net_income_tag": f.get("_net_income_tag"), "equity_tag": f.get("_equity_tag"),
        "revenue_growth_pct": pct(f.get("revenueGrowth")), "earnings_growth_pct": pct(f.get("earningsGrowth")),
        "gross_margin_pct": pct(f.get("grossMargins")), "operating_margin_pct": pct(f.get("operatingMargins")),
        "roe_pct": pct(f.get("returnOnEquity")), "debt_to_equity_pct": number(f.get("debtToEquity")),
        "explosive_blockers": full.get("explosive_blockers") or [],
        "gate_pass": {"deterministic_70": score is not None and 70 <= score <= 100,
            "analyst_75": analyst is not None and 75 <= analyst <= 100,
            "risk_reward_0_4": rr is not None and rr + 1e-12 >= .4,
            "fundamentals_14": (points.get("Fundamentals") or 0) >= 14,
            "fundamentals_and_analyst": (points.get("Fundamentals") or 0) >= 14 and analyst is not None and 75 <= analyst <= 100,
            "lane": full.get("lane_qualified") is True,
            "qualified": status["qualified"], "ready_at_quote": status["ready"]},
        "analyst_status": f.get("_analyst_status") or full.get("analyst_data_status"),
        "valuation_status": f.get("_valuation_status"), "market_cap_status": f.get("_market_cap_status"),
        "pe": positive(f.get("forwardPE")) or positive(f.get("trailingPE")),
        "market_cap": number(f.get("marketCap")), "avg_dollar_volume_20": number(t.get("avg_dollar_volume_20")),
        "quote_asof": ((full.get("data_sources") or {}).get("price") or {}).get("quote_asof"),
        "collected_at": full.get("asof"), "scoring_version": full.get("scoring_version"),
        "missing_analyst": analyst is None,
        "transient_data_gap": bool(temporary_gap),
        "target": number((full.get("target_plan") or {}).get("base_target")),
        "stop": number((full.get("levels") or {}).get("stop"))}


def preflight(provider, symbol, session_date):
    """Use the very same 1y daily input and liquidity calculation as scoring."""
    chart = provider.chart(symbol, "1y", "1d")
    rows, price, _, currency, _ = provider._rows_from_chart(chart)
    quote = datetime.fromtimestamp(float(chart["meta"]["regularMarketTime"]), timezone.utc)
    if quote.astimezone(NY).date().isoformat() != session_date:
        raise ValueError("quote_session_mismatch")
    if not rows or number(price) is None or price <= 0:
        raise ValueError("price_or_history_unavailable")
    liquidity = technicals(rows, price)["avg_dollar_volume_20"]
    blocker = ("price_or_currency_invalid" if price < 5 or currency != "USD"
               else "liquidity_below_10m" if liquidity < CORE_MIN_AVG_DOLLAR_VOLUME else None)
    return {"symbol": symbol, "status": "excluded" if blocker else "awaiting_analysis",
        "price": price, "currency": currency, "avg_dollar_volume_20": liquidity,
        "blocker": blocker, "quote_asof": quote.isoformat(), "collected_at": now().isoformat(),
        "source": "same_scoring_price_and_liquidity_inputs", "qualified": False}


def summarize(results):
    summary = {}
    for row in results:
        accumulate(summary, row)
    return summary


def accumulate(summary, row, delta=1):
    if not row.get("status"):
        return
    counters, blockers, gates, missing, points, point_count = (
        summary.setdefault(k, {}) for k in ("counts", "first_blocker_counts", "independent_gate_pass_counts",
                                             "missing_data", "component_sums", "component_counts"))
    def add(target, key, amount=1):
        target[key] = target.get(key, 0) + delta * amount
    if row:
        add(counters, row["status"])
        if row.get("blocker") and not row.get("ready_at_quote"):
            add(blockers, row["blocker"])
        for gate, passed in (row.get("gate_pass") or {}).items():
            add(gates, gate, int(passed))
        if row["status"] == "scored":
            add(counters, "cached_post_close", int(row.get("source") == "cached_post_close"))
            add(missing, "analyst_score", int(row.get("missing_analyst", False)))
            add(missing, "transient_data_gap", int(row.get("transient_data_gap", False)))
            add(missing, "incomplete_fundamental_inputs", int(bool(row.get("fundamental_missing_inputs"))))
            add(missing, "financial_sector_model_limit", int(bool(row.get("fundamental_model_limitation"))))
            add(missing, "fundamental_floor_data_review", int(row.get("fundamental_floor_status") == "data_review"))
            for key in row.get("fundamental_missing_inputs") or []:
                add(missing, "fundamental_input:" + key)
            for k, v in (row.get("breakdown") or {}).items():
                if v is not None:
                    add(points, k, v); add(point_count, k)
    summary["mean_score_components"] = {k: round(v / point_count[k], 3) for k, v in points.items() if point_count[k]}


class FullUniverseScan:
    def __init__(self, radar):
        self.radar = radar
        self.worker_id = uuid.uuid4().hex
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = None

    def active(self):
        return bool(self.thread and self.thread.is_alive())

    def _reusable_prechecks(self, db, previous, session_date):
        if not previous or previous.scoring_version not in REUSABLE_PREFILTER_VERSIONS or previous.session_date != session_date:
            return {}
        seed = {}
        for row in db.query(FullScanResult).filter_by(run_id=previous.run_id).yield_per(128):
            old = json.loads(row.payload_json or "{}")
            try:
                quote = datetime.fromisoformat(old["quote_asof"].replace("Z", "+00:00")).astimezone(NY)
                if quote.date().isoformat() != session_date:
                    continue
                price, liquidity = number(old.get("price")), number(old.get("avg_dollar_volume_20"))
                if price is None or price <= 0 or liquidity is None or liquidity < 0:
                    continue
                if row.status == "excluded" and old.get("source") == "same_scoring_price_and_liquidity_inputs":
                    blocker = ("price_or_currency_invalid" if price < 5 or old.get("currency") != "USD"
                               else "liquidity_below_10m" if liquidity < CORE_MIN_AVG_DOLLAR_VOLUME else None)
                    if blocker == old.get("blocker"):
                        seed[row.symbol] = old
                elif row.status in {"scored", "awaiting_analysis"} and price >= 5 and liquidity >= CORE_MIN_AVG_DOLLAR_VOLUME:
                    if row.status == "awaiting_analysis" and old.get("currency") != "USD":
                        continue
                    # Copy the verified precheck only, never an old score/gate.
                    seed[row.symbol] = {"symbol": row.symbol, "status": "awaiting_analysis", "price": price,
                        "currency": "USD", "avg_dollar_volume_20": liquidity, "quote_asof": old["quote_asof"],
                        "collected_at": old.get("collected_at"), "qualified": False, "source": "reused_verified_prior_precheck"}
            except (KeyError, ValueError, TypeError):
                continue
        return seed

    def start(self):
        if getattr(self.radar, "live_priority_window", self.radar.market_open)():
            return {"status": "live_priority_window", "message": "Full audit yields from 09:00 ET through the regular close so pre-open/live scanning has priority."}
        with self.lock:
            if self.active():
                return self.status()
            with SessionLocal() as db:
                run = db.get(FullScanRun, KEY)
                if run and run.status in ACTIVE and run.scoring_version == SCORING_VERSION:
                    run_id = run.run_id
                else:
                    universe = self.radar.provider.us_equity_universe()
                    symbols = list(dict.fromkeys(r["symbol"] for r in universe))
                    if not symbols:
                        return {"status": "error", "message": "Universe directory unavailable"}
                    # Before the open, on weekends and on holidays, calendar
                    # today is not the date of the latest exchange quote. Freeze
                    # the index's observed session instead of rejecting every
                    # stock's perfectly valid previous-session close.
                    try:
                        index = self.radar.provider.chart("^GSPC", "5d", "1d")
                        quote = datetime.fromtimestamp(float(index["meta"]["regularMarketTime"]), timezone.utc)
                        if not now() - timedelta(days=7) <= quote <= now():
                            raise ValueError("index_quote_not_recent")
                        session_date = quote.astimezone(NY).date().isoformat()
                    except Exception:
                        return {"status": "error", "message": "Latest market session unavailable; no audit started"}
                    symbol_set = set(symbols)
                    seed = {s: row for s, row in self._reusable_prechecks(db, run, session_date).items() if s in symbol_set}
                    run_id = uuid.uuid4().hex
                    run = run or FullScanRun(key=KEY)
                    run.run_id, run.status, run.scoring_version = run_id, "prefilter", SCORING_VERSION
                    run.session_date = session_date
                    run.universe_json, run.summary_json = dumps(symbols), dumps(summarize(seed.values()))
                    run.worker_id, run.lease_until = "", None
                    run.started_at = run.updated_at = now(); run.finished_at = None
                    db.add(run)
                    db.add_all([FullScanResult(run_id=run_id, symbol=s, ordinal=i,
                                              status=seed.get(s, {}).get("status", "pending"),
                                              payload_json=dumps(seed[s]) if s in seed else "{}")
                                for i, s in enumerate(symbols)])
                    db.commit()
            self._launch(run_id)
        return self.status()

    def resume(self):
        restart_for_version = False
        with self.lock, SessionLocal() as db:
            run = db.get(FullScanRun, KEY)
            if run and run.status in ACTIVE and not self.active():
                if run.scoring_version == SCORING_VERSION:
                    self._launch(run.run_id)
                else:
                    # A deploy can bump the scoring model while an older audit is
                    # still active. Do not relaunch that obsolete worker and leave
                    # the dashboard stuck on stale results; retire it and create a
                    # clean current-version run after releasing this lock.
                    run.status = "scoring_version_changed"
                    run.worker_id, run.lease_until = "", None
                    run.updated_at = now()
                    db.commit()
                    restart_for_version = True
        if restart_for_version:
            return self.start()
        return self.status()

    def _launch(self, run_id):
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, args=(run_id,), daemon=True, name="full-universe-audit")
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    def _claim(self, run_id):
        with SessionLocal() as db:
            run = db.query(FullScanRun).filter_by(key=KEY).with_for_update().one()
            lease = run.lease_until.replace(tzinfo=timezone.utc) if run.lease_until else None
            if run.run_id != run_id or (lease and lease > now() and run.worker_id != self.worker_id):
                return None
            if run.scoring_version != SCORING_VERSION:
                run.status = "scoring_version_changed"; db.commit(); return None
            run.worker_id, run.lease_until = self.worker_id, now() + timedelta(seconds=180)
            run.updated_at = now(); db.commit()
            return run.session_date

    def _record(self, run_id, changes, phase):
        with SessionLocal() as db:
            run = db.get(FullScanRun, KEY)
            if run.run_id != run_id or run.worker_id != self.worker_id:
                raise RuntimeError("audit_lease_lost")
            symbols = [r["symbol"] for r in changes]
            existing = {r.symbol:r for r in db.query(FullScanResult).filter(
                FullScanResult.run_id == run_id, FullScanResult.symbol.in_(symbols)).all()}
            summary = json.loads(run.summary_json)
            for result in changes:
                row = existing[result["symbol"]]
                accumulate(summary, json.loads(row.payload_json), -1)
                accumulate(summary, result)
                row.status, row.qualified = result["status"], bool(result.get("qualified"))
                row.payload_json = dumps(result)
            run.summary_json = dumps(summary)
            run.status, run.updated_at = phase, now()
            run.lease_until = now() + timedelta(seconds=180)
            db.commit()

    def _pending(self, run_id, status, limit):
        with SessionLocal() as db:
            return [r.symbol for r in db.query(FullScanResult.symbol).filter_by(run_id=run_id, status=status)
                    .order_by(FullScanResult.ordinal).limit(limit).all()]

    def _cached(self, symbol, session_date):
        with SessionLocal() as db:
            row = db.query(RadarCandidate).filter_by(symbol=symbol).first()
            full = json.loads(row.current_json or "{}") if row else {}
        try:
            collected = datetime.fromisoformat(full["asof"].replace("Z", "+00:00")).astimezone(NY)
            quote = datetime.fromisoformat(full["data_sources"]["price"]["quote_asof"].replace("Z", "+00:00")).astimezone(NY)
            f = full.get("fundamentals") or {}
            if (full.get("scoring_version") == SCORING_VERSION and collected.date().isoformat() == session_date
                    and collected.hour >= 16 and quote.date().isoformat() == session_date
                    and (quote.hour * 60 + quote.minute) >= 950):
                result = compact_result(full, "cached_post_close")
                if not result["transient_data_gap"]:
                    return result
        except (KeyError, ValueError, TypeError):
            pass
        return None

    def _budget_wait(self):
        cache = getattr(getattr(self.radar.provider, "analyst", None), "cache", None)
        if cache is None:
            return
        while not self.stop_event.is_set():
            with cache.lock:
                recent = [(ts, ep) for ts, ep in cache.requests if ts > time.monotonic() - 60]
                # Allow room for valuation/profile without turning throttles into failed scores.
                crowded = len(recent) >= 40 or sum(ep != "recommendation" for _, ep in recent) >= 13
            if not crowded:
                return
            self.stop_event.wait(2)

    def _run(self, run_id):
        try:
            session_date = self._claim(run_id)
            if not session_date:
                return
            # The normal after-hours cycle yields to this audit, preserving its provider budget.
            with ThreadPoolExecutor(max_workers=4) as pool:
                while not self.stop_event.is_set():
                    if getattr(self.radar, "live_priority_window", self.radar.market_open)():
                        self._record(run_id, [], "paused_live_priority"); self.stop_event.wait(30); continue
                    batch = self._pending(run_id, "pending", 32)
                    if not batch:
                        break
                    def check(symbol):
                        try:
                            return self._cached(symbol, session_date) or preflight(self.radar.provider, symbol, session_date)
                        except Exception as exc:
                            return {"symbol":symbol, "status":"retry_prefilter", "error":type(exc).__name__}
                    self._record(run_id, list(pool.map(check, batch)), "prefilter")
            for symbol in self._pending(run_id, "retry_prefilter", 10000):
                if self.stop_event.is_set(): return
                try: result = preflight(self.radar.provider, symbol, session_date)
                except Exception as exc: result = {"symbol":symbol,"status":"error","error":type(exc).__name__,"stage":"prefilter"}
                self._record(run_id, [result], "prefilter")
            # Two after-hours workers keep the exhaustive audit moving without
            # turning the 512MB web service into a high-concurrency batch engine.
            # The normal scanner yields while the audit is active, and the shared
            # scan lock prevents a manual/live scanner cycle from overlapping this
            # two-symbol batch.
            with ThreadPoolExecutor(max_workers=2) as analysis_pool:
                while not self.stop_event.is_set():
                    if getattr(self.radar, "live_priority_window", self.radar.market_open)():
                        self._record(run_id, [], "paused_live_priority"); self.stop_event.wait(30); continue
                    symbols = self._pending(run_id, "awaiting_analysis", 2)
                    if not symbols:
                        break
                    self._budget_wait()
                    if self.stop_event.is_set():
                        return

                    def analyze(symbol):
                        result = self._cached(symbol, session_date)
                        if result is not None:
                            return result
                        try:
                            full = self.radar.analyze_symbol(symbol, persist=False, contextual_ai=False)
                            result = compact_result(full)
                            if not str(result.get("quote_asof") or "").startswith(session_date):
                                raise ValueError("quote_session_mismatch")
                            self.radar.persist(full)
                            return result
                        except Exception as exc:
                            return {"symbol":symbol,"status":"error","error":type(exc).__name__,"stage":"analysis"}

                    with self.radar._scan_lock:
                        results = list(analysis_pool.map(analyze, symbols))
                    self._record(run_id, results, "analysis")
            if self.stop_event.is_set(): return
            with SessionLocal() as db:
                run = db.get(FullScanRun, KEY)
                summary = json.loads(run.summary_json)
                gaps = summary.get("counts", {}).get("error", 0) + sum(summary.get("missing_data", {}).values())
                run.status = "completed_with_data_gaps" if gaps else "completed"
                run.finished_at = run.updated_at = now(); run.lease_until = None; db.commit()
        except Exception as exc:
            # Keep pending rows intact. A subsequent start resumes after a worker error.
            with SessionLocal() as db:
                run = db.get(FullScanRun, KEY)
                if run and run.run_id == run_id:
                    summary = json.loads(run.summary_json); summary["worker_error"] = type(exc).__name__
                    run.summary_json = dumps(summary); run.lease_until = None; db.commit()
        finally:
            with SessionLocal() as db:
                run = db.get(FullScanRun, KEY)
                if run and run.worker_id == self.worker_id:
                    run.lease_until = None; db.commit()

    def status(self):
        with SessionLocal() as db:
            run = db.get(FullScanRun, KEY)
            if not run: return {"status":"not_started"}
            counts = dict(db.query(FullScanResult.status, func.count()).filter_by(run_id=run.run_id)
                          .group_by(FullScanResult.status).all())
            qualified = [json.loads(r.payload_json) for r in db.query(FullScanResult)
                         .filter_by(run_id=run.run_id, qualified=True).order_by(FullScanResult.symbol).all()]
            total = sum(counts.values())
            done = counts.get("scored", 0) + counts.get("excluded", 0) + counts.get("error", 0)
            return {"status":run.status, "run_id":run.run_id, "session_date":run.session_date,
                "scoring_version":run.scoring_version,"started_at":run.started_at,"updated_at":run.updated_at,
                "finished_at":run.finished_at,"universe_size":total,"processed":done,
                "progress_pct":round(100*done/total,2) if total else 0,"status_counts":counts,
                "worker_running":self.active(),"qualified_count":len(qualified),"qualified_stocks":qualified,
                "execution_enabled":False,"gates":{"deterministic":70,"analyst":75,"risk_reward":.4},
                "coverage_basis":"Every listed stock checked; exact price/currency/liquidity failures excluded, every survivor fully scored without a top-N limit",
                "entry_basis":"Readiness at the saved quote; closed-market results are not executable orders",
                "summary":json.loads(run.summary_json)}

    def results_csv(self):
        with SessionLocal() as db:
            run = db.get(FullScanRun, KEY)
            if not run: return ""
            fields = ["symbol","status","price","avg_dollar_volume_20","deterministic_score","analyst_score",
                      "risk_reward","qualified","ready_at_quote","lane","blocker","analyst_status",
                      "valuation_status","market_cap_status","quote_asof","collected_at","source","error"]
            component_columns = {"fundamentals_points":"Fundamentals", "catalyst_points":"Catalyst",
                "news_points":"News", "momentum_points":"Momentum", "sector_points":"Sector",
                "valuation_points":"Valuation", "analyst_confirmation_points":"Analyst confirmation",
                "risk_reward_points":"Risk/Reward"}
            contribution_columns = {column.replace("_points", "_contribution"): label
                                    for column, label in component_columns.items()}
            fields += list(component_columns) + list(contribution_columns) + ["scoring_version","score_calibration","sector","fundamental_confidence",
                "fundamental_missing_inputs","fundamental_model_limitation","fundamental_reasons",
                "fundamental_floor_status","fundamental_score_min","fundamental_score_max","fundamental_missing_bonus_inputs",
                "fundamental_period","net_income_tag","equity_tag","revenue_growth_pct","earnings_growth_pct",
                "gross_margin_pct","operating_margin_pct","roe_pct","debt_to_equity_pct"]
            out = io.StringIO(); writer = csv.DictWriter(out, fields, extrasaction="ignore"); writer.writeheader()
            for row in db.query(FullScanResult).filter_by(run_id=run.run_id).order_by(FullScanResult.ordinal):
                data = {"symbol":row.symbol,"status":row.status,**json.loads(row.payload_json)}
                data.update({column:(data.get("breakdown") or {}).get(component)
                             for column,component in component_columns.items()})
                data.update({column:(data.get("score_contributions") or {}).get(component)
                             for column,component in contribution_columns.items()})
                for key in ("fundamental_missing_inputs", "fundamental_reasons", "fundamental_missing_bonus_inputs"):
                    data[key] = "; ".join(data.get(key) or [])
                writer.writerow(data)
            return out.getvalue()
