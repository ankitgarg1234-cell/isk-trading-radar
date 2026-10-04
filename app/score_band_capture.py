"""Persistence adapter for the separate experiment; no writes to existing ledgers."""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from threading import Lock

from .db import SessionLocal, ScoreBandExperiment, ScoreBandObservation, PortfolioPreference, PaperAccount
from .config import settings
from .market import YahooMarketProvider
from .analysis_engine import LEGACY_SCORING_VERSION
from .portfolio_engine import normalise_profile
from .score_band_experiment import VERSION, advance, new_state, number, timestamp, summary, ensure_single_account, arm_trial

_LOCK = Lock()
_BENCHMARK_PROVIDER = YahooMarketProvider()


def fresh_benchmark(now):
    """Independent exchange-timed index observation; no prior-close substitution."""
    try:
        meta = _BENCHMARK_PROVIDER.chart("^SP500TR", "1d", "1m").get("meta") or {}
        price = number(meta.get("regularMarketPrice"))
        observed = datetime.fromtimestamp(float(meta["regularMarketTime"]), tz=timezone.utc)
        if price and price > 0 and 0 <= (now - observed).total_seconds() <= 600:
            return price, observed.isoformat()
    except Exception:
        pass
    return None, None


def _load(db):
    row = db.query(ScoreBandExperiment).filter_by(version=VERSION).with_for_update().first()
    if row:
        state = ensure_single_account(json.loads(row.state_json))
        if settings.score_band_trial_armed_at:
            arm_trial(state, settings.score_band_trial_armed_at)
        row.state_json = json.dumps(state, default=str, separators=(",", ":"))
        return row, state
    preference = db.query(PortfolioPreference).filter_by(account="Main").first()
    state = new_state(normalise_profile(preference.risk_profile if preference else "MEDIUM"))
    if settings.score_band_trial_armed_at:
        arm_trial(state, settings.score_band_trial_armed_at)
    row = ScoreBandExperiment(version=VERSION, state_json=json.dumps(state))
    db.add(row)
    db.flush()
    return row, state


def compact_observation(full):
    keys = ("symbol", "price", "currency", "asof", "scoring_version", "deterministic_score",
        "analyst_score", "risk_reward", "fundamental_confidence", "decision_confidence", "breakdown",
        "lane", "lane_qualified", "levels", "target_plan", "holding_horizon", "technicals",
        "news", "negative_news_override", "thesis_assessment", "promotion_risk", "data_sources")
    out = {k: copy.deepcopy(full.get(k)) for k in keys}
    out["collected_at"] = full.get("asof")
    # Retrieval time is not exchange quote time. Missing/stale exchange times
    # must not become simulated fills merely because a cached quote was reread.
    out["asof"] = ((full.get("data_sources") or {}).get("price") or {}).get("quote_asof")
    f = full.get("fundamentals") or {}
    out["analyst_inputs"] = {k: f.get(k) for k in ("targetMeanPrice", "recommendationMean",
        "strongBuy", "buy", "hold", "sell", "strongSell", "_analyst_source", "_analyst_period", "_analyst_status")}
    # Keep entry geometry independent of the current live price. The production
    # high20 includes today's running close, which cannot confirm its own breakout.
    day = str(out.get("asof") or "")[:10]
    completed = [r for r in (full.get("history") or []) if str(r.get("date") or "") < day and number(r.get("close"))]
    atr = number((full.get("technicals") or {}).get("atr"))
    if len(completed) >= 20 and atr and out.get("levels"):
        high20 = max(float(r["close"]) for r in completed[-20:])
        out["levels"]["breakout"] = round(high20 + 0.1 * atr, 4)
        out["levels"]["do_not_chase"] = round(min(float(out["levels"]["do_not_chase"]), high20 + 1.1 * atr), 4)
        out["breakout_anchor"] = {"through_date": completed[-1]["date"], "high20_close": high20}
    # Avoid archival duplication of full news bodies and one-year price arrays.
    if isinstance(out.get("news"), dict):
        out["news"] = {k: v for k, v in out["news"].items() if k not in {"items", "headlines"}}
    return out


def run_experiment_cycle(full_analyses, market_open, now=None):
    now = now or datetime.now(timezone.utc)
    observations = []
    for a in full_analyses:
        locked = a.get("_locked_trial_observation")
        if isinstance(locked, dict) and locked.get("scoring_version") == LEGACY_SCORING_VERSION:
            observations.append(copy.deepcopy(locked))
        elif locked is not None or (a.get("scoring_version") not in (None, LEGACY_SCORING_VERSION)) or (a.get("news") or {}).get("version") == "headline-context-v2":
            # Fail closed: never pass revised scoring into the frozen trial.
            continue
        else:
            observations.append(compact_observation(a))
    benchmark_quote = fresh_benchmark(now) if settings.score_band_trial_armed_at and market_open else (None, None)
    with _LOCK, SessionLocal() as db:
        row, state = _load(db)
        original_seen = dict(state["variants"]["complete_strategy"]["seen"])
        # The existing paper cycle updates this total-return index observation.
        account = db.query(PaperAccount).filter_by(account="Optimizer Paper").first()
        benchmark = account.benchmark_last_price if account else None
        if account and account.updated_at:
            updated = account.updated_at.replace(tzinfo=timezone.utc) if account.updated_at.tzinfo is None else account.updated_at
            if (now - updated).total_seconds() > 1800:
                benchmark = None
        benchmark_asof = None
        if state.get("trial"):
            benchmark, benchmark_asof = benchmark_quote
        result = advance(state, observations, now.isoformat(), market_open, benchmark, benchmark_asof)
        for a in observations:
            observed = a.get("asof") or ""
            sym = a.get("symbol")
            if observed > original_seen.get(sym, "") and state["variants"]["complete_strategy"]["seen"].get(sym) == observed:
                db.add(ScoreBandObservation(version=VERSION, symbol=sym,
                    observed_at=timestamp(observed), payload_json=json.dumps(a, default=str, separators=(",", ":"))))
        row.state_json = json.dumps(state, default=str, separators=(",", ":"))
        row.updated_at = now
        db.commit()
        return {**result, "version": VERSION, "started_at": state["started_at"],
                "coverage": state["coverage"], "profile": state["spec"]["profile"], "trial": summary(state).get("trial")}


def experiment_status(include_history=False):
    with _LOCK, SessionLocal() as db:
        row, state = _load(db)
        if state.get("trial", {}).get("ends_at") and timestamp(state["trial"]["ends_at"]) <= datetime.now(timezone.utc):
            advance(state, [], datetime.now(timezone.utc).isoformat(), False)
            row.state_json = json.dumps(state, default=str, separators=(",", ":"))
        db.commit()
        out = summary(state)
        out["observation_count"] = db.query(ScoreBandObservation).filter_by(version=VERSION).count()
        if include_history:
            out["trades"] = {mode: book["trades"] for mode, book in state["variants"].items()}
            out["curves"] = {mode: book["curve"] for mode, book in state["variants"].items()}
        return out


def experiment_holding_symbols():
    with SessionLocal() as db:
        row = db.query(ScoreBandExperiment).filter_by(version=VERSION).first()
        if not row:
            return []
        state = ensure_single_account(json.loads(row.state_json))
        return sorted({s for book in state["variants"].values()
                       for s in set(book["positions"]) | set(book["pending"])})
