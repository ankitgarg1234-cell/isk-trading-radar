"""Persistence adapter for the canonical strategy paper account."""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from threading import Lock
from zoneinfo import ZoneInfo

from .db import SessionLocal, ScoreBandExperiment, ScoreBandObservation, PortfolioPreference, PaperAccount
from .config import settings
from .market import YahooMarketProvider
from .analysis_engine import SCORING_VERSION
from .trading_rules import signal_geometry
from .portfolio_engine import normalise_profile
from .score_band_experiment import (VERSION, advance, new_state, number, timestamp, summary,
                                    ensure_single_account, arm_trial, experiment_spec)

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
    # VERSION is the stable persistence/account key, not the sizing-policy
    # version. Strategy parameters migrate inside state["spec"] so deployments
    # never fork or reset the existing canonical paper ledger.
    row = db.query(ScoreBandExperiment).filter_by(version=VERSION).with_for_update().first()
    if row:
        state = ensure_single_account(json.loads(row.state_json))
        # Migrate strategy parameters in place without resetting cash, positions or
        # trade history. v23 lowers the deterministic floor to 65 and adds a 5%
        # starter allocation for the new 65-69 band.
        profile = str((state.get("spec") or {}).get("profile") or "MEDIUM")
        current_spec = experiment_spec(profile)
        for key in ("sizing_policy", "continuous_sizing", "min_deterministic", "min_analyst", "min_rr", "risk_per_trade_pct"):
            state.setdefault("spec", {})[key] = current_spec[key]
        state["spec"].pop("bands", None)
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
        "lane", "lane_qualified", "levels", "target_plan", "holding_horizon", "short_horizon_forecast", "technicals",
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
    out["levels"], out["breakout_anchor"] = signal_geometry(full)
    # Avoid archival duplication of full news bodies and one-year price arrays.
    if isinstance(out.get("news"), dict):
        out["news"] = {k: v for k, v in out["news"].items() if k not in {"items", "headlines"}}
    return out


def _recovery_mark_only(state, observations, now, market_open):
    """Refresh marks for reconstructed holdings without creating/canceling orders."""
    book = state["variants"]["complete_strategy"]
    touched = 0
    for a in observations:
        symbol = str(a.get("symbol") or "").upper()
        price = number(a.get("price"))
        observed = str(a.get("asof") or "")
        if symbol not in book["positions"] or price is None or price <= 0:
            continue
        book["marks"][symbol] = float(price)
        if observed and observed > book["seen"].get(symbol, ""):
            book["seen"][symbol] = observed
        touched += 1

    value = book["cash"] + sum(
        p["shares"] * book["marks"].get(symbol, p["avg_cost"])
        for symbol, p in book["positions"].items()
    )
    book["peak_equity"] = max(float(book.get("peak_equity") or value), value)
    if book["peak_equity"] > 0:
        book["max_drawdown_pct"] = min(
            float(book.get("max_drawdown_pct") or 0.0),
            (value / book["peak_equity"] - 1) * 100,
        )
    book["samples"] = int(book.get("samples") or 0) + 1
    book["cash_pct_sum"] = float(book.get("cash_pct_sum") or 0.0) + (
        book["cash"] / value * 100 if value else 0.0
    )
    asof = now.isoformat()
    row = {"asof": asof, "equity": value, "cash": book["cash"], "positions": len(book["positions"])}
    slot = asof[:14] + ("00" if now.minute < 30 else "30")
    if book["curve"] and book["curve"][-1].get("slot") == slot:
        book["curve"][-1] = {**row, "slot": slot}
    else:
        book["curve"].append({**row, "slot": slot})
    state["last_cycle"] = asof
    state["last_market_open"] = bool(market_open)
    state["coverage"]["recovery_mark_cycles"] = state["coverage"].get("recovery_mark_cycles", 0) + 1
    return {"status": "recovery_readonly", "observations": touched, "fills": 0}


def run_experiment_cycle(full_analyses, market_open, now=None):
    now = now or datetime.now(timezone.utc)
    observations = [compact_observation(a) for a in full_analyses]
    benchmark_quote = fresh_benchmark(now) if settings.score_band_trial_armed_at and market_open else (None, None)
    with _LOCK, SessionLocal() as db:
        row, state = _load(db)
        state["spec"]["scoring_version"] = SCORING_VERSION
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
        if getattr(settings, "recovery_readonly_paper", False):
            result = _recovery_mark_only(state, observations, now, market_open)
        else:
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
        state["spec"]["scoring_version"] = SCORING_VERSION
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


def canonical_paper_status(db):
    """Read the dashboard projection from the strategy ledger, without a second account."""
    row, state = _load(db)
    report = summary(state)
    book = state['variants']['complete_strategy']
    metrics = report['variants']['complete_strategy']
    value = metrics['equity']
    positions = []
    for symbol, p in book['positions'].items():
        price = book['marks'].get(symbol, p['avg_cost'])
        shares = float(p.get('shares') or 0)
        fill_price = float(p.get('avg_cost') or 0)
        entry_fee = shares * float(number(p.get('entry_fee_per_share')) or 0)
        fill_cost = shares * fill_price
        # Use economic cost basis (fill + allocated entry commission) for the
        # dashboard P&L. Account equity already includes these commissions, so
        # excluding them here made the sum of open-position P&Ls look materially
        # higher than Absolute Return.
        cost = fill_cost + entry_fee
        net_avg_cost = (cost / shares) if shares else fill_price
        marked = shares * price
        pnl = marked - cost
        entry = next((t for t in book['trades'] if t['symbol'] == symbol and t['side'] == 'BUY' and t['observed_at'] == p['opened_at']), {})
        positions.append({**p, 'symbol': symbol, 'price': price, 'value': marked,
            'fill_price': fill_price, 'avg_cost': net_avg_cost, 'entry_fee': entry_fee,
            'cost_basis': cost, 'pnl': pnl, 'pnl_pct': (pnl/cost)*100 if cost else 0,
            'weight_pct': marked/value*100 if value else 0, 'day_change_pct': None,
            'entry_rank_score': entry.get('deterministic_score', 0),
            'lane': 'SCORE_QUALIFIED', 'lane_label': 'Score qualified',
            'reason': entry.get('reason', 'Agreed paper strategy'), 'graduated_from_explosive': False})
    today = datetime.now(timezone.utc).astimezone(ZoneInfo('America/New_York')).date()
    prior = next((p for p in reversed(book['curve']) if timestamp(p['asof']).astimezone(ZoneInfo('America/New_York')).date() < today), None)
    base = prior['equity'] if prior else state['spec']['starting_cash']
    daily = value-base
    benchmark = report['benchmark_return_pct']
    absolute_return = value-state['spec']['starting_cash']
    open_pnl = sum(float(p.get('pnl') or 0) for p in positions)
    realized_pnl = float(metrics.get('realized_profit') or 0)
    pnl_reconciliation_delta = absolute_return - open_pnl - realized_pnl
    return {'canonical_strategy': True, 'enabled': True, 'started': bool(state['started_at']),
        'starting_cash': state['spec']['starting_cash'], 'cash': metrics['cash'],
        'equity': value, 'invested': round(value-metrics['cash'], 2),
        'return_pct': metrics['return_pct'], 'absolute_return': absolute_return,
        'open_pnl': round(open_pnl, 2), 'realized_pnl': round(realized_pnl, 2),
        'pnl_reconciliation_delta': round(pnl_reconciliation_delta, 6),
        'recovery_mode': bool(getattr(settings, 'recovery_readonly_paper', False)),
        'recovery_adjustment': round(pnl_reconciliation_delta, 2) if getattr(settings, 'recovery_readonly_paper', False) else 0.0,
        'recovery_note': (state.get('recovery') or {}).get('note'),
        'daily_pnl': daily, 'daily_pnl_pct': daily/base*100 if base else 0,
        'benchmark_label': 'S&P 500 Total Return', 'benchmark_return_pct': benchmark,
        'excess_return_pct': metrics['excess_return_pct'], 'drawdown_pct': metrics['max_drawdown_pct'],
        'current_drawdown_pct': (1-value/book['peak_equity'])*100 if book['peak_equity'] else 0,
        'positions': positions, 'position_count': len(positions), 'trade_count': len(book['trades']),
        'trades': [{**t, 'created_at': t['observed_at'], 'rank_score': t.get('deterministic_score', 0)} for t in reversed(book['trades'][-12:])],
        'legacy_trades': [], 'legacy_trade_count': 0, 'core_position_count': 0,
        'explosive_position_count': 0, 'outside_lane_position_count': 0,
        'normalized_legacy_position_count': 0, 'normalized_legacy_symbols': [],
        'current_valid_origin_count': len(positions), 'started_at': state['started_at'],
        'updated_at': state['last_cycle'], 'scoring_version': SCORING_VERSION}
