from __future__ import annotations

import asyncio
import gc
import hashlib
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import case, cast, func, or_
from sqlalchemy.dialects.postgresql import JSONB

from .config import settings
from .db import SessionLocal, Position, AnalysisRequest, WatchlistItem, AnalysisSnapshot, RadarCandidate, Alert, PortfolioPreference, PaperPosition
from .market import YahooMarketProvider
from .analysis_engine import score_bundle, position_action, position_action_plan, SCORING_VERSION
from .market_evidence import recover_market_evidence, transient_missing, positive
from .trading_rules import entry_status
from .news_scoring import VERSION as NEWS_VERSION
from . import article_news
from .portfolio_engine import candidate_rank_score, build_optimizer_plan, normalise_profile, INVESTABLE_ENTRY_ACTIONS, MIN_ENTRY_RISK_REWARD
from .paper_engine import run_paper_cycle
from .score_band_capture import run_experiment_cycle, experiment_holding_symbols, compact_observation
from .score_diagnostics import scan_score_diagnostics
from .ai_engine import AIEngine

NY = ZoneInfo("America/New_York")
LIVE_DEEP_ANALYSIS_MAX = 12
LIVE_PERSISTED_QUALIFIED_MAX = 6
LIVE_STALE_REFRESH_MAX = 6




def _attention_buy_signal(full: dict, has_position: bool = False) -> tuple[str | None, str | None]:
    """Buy attention uses the canonical paper thresholds and trigger."""
    from .portfolio_engine import entry_attention_signal
    signal = entry_attention_signal(full)
    if signal is None:
        return None, None
    return signal, entry_status(full)["reason"] + f"; deterministic conviction {float(full['deterministic_score']):g}/100"


def _strategic_fingerprint(signal: dict | None) -> str:
    signal = signal or {}
    material = {
        "direction": signal.get("direction"),
        "strength": signal.get("evidence_strength", 0),
        "government_equity_stake": signal.get("government_equity_stake"),
        "trump_administration_action": signal.get("trump_administration_action"),
        "trump_personal": (signal.get("trump_personal_disclosure") or {}).get("status"),
        "federal_total": round(float((signal.get("federal_awards") or {}).get("total_amount") or 0), 2),
        "events": [
            (e.get("type"), e.get("title"), e.get("direction"), e.get("materiality"))
            for e in (signal.get("events") or [])[:8]
        ],
    }
    return hashlib.sha1(json.dumps(material, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _compact_payload(full: dict) -> dict:
    """Return the current decision state without heavy historical arrays.

    The live dashboard, alert drill-down and portfolio engine only need the
    latest scores/levels/evidence summary. One-year price histories and sector
    benchmark histories can be re-fetched on an explicit full-analysis refresh.
    Keeping them out of Postgres cuts network egress by orders of magnitude.
    """
    compact = dict(full)
    compact.pop("history", None)
    sector = compact.get("sector_benchmark")
    if isinstance(sector, dict):
        sector = dict(sector)
        sector.pop("history", None)
        compact["sector_benchmark"] = sector
    news = compact.get("news")
    if isinstance(news, dict):
        news = dict(news)
        items = news.get("items")
        if isinstance(items, list):
            news["items"] = items[:15] if news.get("version") in {NEWS_VERSION, "headline-context-v2", "article-context-v3", "article-context-v4"} else items[:5]
        compact["news"] = news
    strategic = compact.get("strategic_capital")
    if isinstance(strategic, dict):
        strategic = dict(strategic)
        strategic["events"] = list(strategic.get("events") or [])[:6]
        federal = strategic.get("federal_awards")
        if isinstance(federal, dict):
            federal = dict(federal)
            federal["events"] = list(federal.get("events") or [])[:5]
            strategic["federal_awards"] = federal
        compact["strategic_capital"] = strategic
    # This is used only for deterioration comparison and should never chain
    # historical snapshots recursively.
    prior = compact.get("previous_snapshot")
    if isinstance(prior, dict):
        compact["previous_snapshot"] = {
            "breakdown": prior.get("breakdown") or {},
            "deterministic_score": prior.get("deterministic_score"),
            "action": prior.get("action"),
        }
    return compact


def _snapshot_key(payload: dict) -> str:
    thesis = payload.get("thesis_assessment") or {}
    news = payload.get("news") or {}
    material = {
        "action": payload.get("action"),
        "deterministic_score": round(float(payload.get("deterministic_score") or 0), 1),
        "ai_score": round(float(payload.get("ai_score") or 0), 1),
        "fundamentals": (payload.get("breakdown") or {}).get("Fundamentals"),
        "news_label": news.get("label"),
        "material_events": news.get("material_events", 0),
        "thesis_invalidated": bool(thesis.get("invalidated")),
        "strategic_capital": _strategic_fingerprint(payload.get("strategic_capital")),
    }
    raw = json.dumps(material, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()


class RadarService:
    def __init__(self, provider=None, ai=None):
        self.provider = provider or YahooMarketProvider()
        self.ai = ai or AIEngine()
        self.running = False
        self.last_scan = None
        self.last_error = None
        self.last_result = None
        self.scan_in_progress = False
        self.scan_started_at = None
        self.last_scan_duration_seconds = None
        self._scan_lock = threading.Lock()
        self.scan_count = 0
        self.universe_size = 0
        self.last_universe_prefiltered = 0
        self.last_universe_candidates = 0
        self.last_universe_core_candidates = 0
        self.last_universe_explosive_candidates = 0
        self.last_deep_analyzed = 0
        self.last_experiment_result = {"status": "waiting_for_market_open", "version": "score-bands-paper-v1"}
        self.last_universe_start = 0
        self._universe_cursor = None
        self._deferred_analysis_symbols: list[str] = []
        # Process-local material state used only to decide whether the paper
        # optimizer needs an immediate event-driven run.  It is intentionally
        # not stored in Neon; a service restart may cause one harmless recheck.
        self._paper_entry_state: dict[str, tuple] = {}
        # Portfolio eligibility/config state is deliberately separate from the
        # per-symbol BUY state. A service restart or a material optimizer-policy
        # change must force one full Top-20 re-evaluation even when a stock stays
        # BUY -> BUY (the GWRE missed-entry failure mode).
        self._paper_optimizer_policy_state: str | None = None
        self._last_strategic_enrich_at: datetime | None = None
        self._preopen_warmup_date: str | None = None
        self._preopen_warmed_symbols: set[str] = set()

    def market_open(self, now=None):
        """Regular-session V1 gate: Mon-Fri, 09:30-16:00 America/New_York.

        Production feed should replace this with the exchange calendar to account for holidays/early closes.
        """
        now = (now or datetime.now(timezone.utc)).astimezone(NY)
        if now.weekday() >= 5:
            return False
        mins = now.hour * 60 + now.minute
        return 570 <= mins < 960

    def preopen_warmup(self, now=None):
        """Reserve scanner/provider capacity for the 30 minutes before the U.S. open.

        The overnight full-universe audit yields from 09:00 New York time so the
        actionable radar can refresh holdings, persisted qualifiers and fresh movers
        before the opening bell. This window is analysis-only; paper execution still
        requires market_open().
        """
        now = (now or datetime.now(timezone.utc)).astimezone(NY)
        if now.weekday() >= 5:
            return False
        mins = now.hour * 60 + now.minute
        return 540 <= mins < 570

    def live_priority_window(self, now=None):
        """True from 09:00 through the regular close in New York."""
        now = now or datetime.now(timezone.utc)
        return self.preopen_warmup(now) or self.market_open(now)

    def analyze_symbol(self, symbol: str, persist: bool = True, strategic_refresh: bool = False, contextual_ai: bool = True):
        symbol = symbol.upper().strip()
        bundle = self.provider.bundle(symbol)
        prior_payload = {}
        with SessionLocal() as db:
            prior = db.query(RadarCandidate).filter(RadarCandidate.symbol == symbol).first()
            if prior and prior.current_json:
                try:
                    prior_payload = json.loads(prior.current_json)
                except (ValueError, TypeError):
                    pass
            recover_market_evidence(bundle, [prior_payload])
            f = bundle.get("fundamentals") or {}
            old_f = prior_payload.get("fundamentals") or {}
            for prefix, field in (("valuation", "trailingPE"), ("market_cap", "marketCap")):
                if f.get(field) is not None or not transient_missing(f, prefix):
                    continue
                # A definitive missing/invalid newer observation supersedes any
                # older positive history. Only recover after transient failures.
                if old_f.get(field) is not None and not positive(old_f.get(field)):
                    continue
                if "positive TTM P/E not returned" in str(old_f.get(f"_{prefix}_status") or ""):
                    continue
                checked_key = f"_{prefix}_history_checked_at"
                try:
                    checked = datetime.fromisoformat(str(old_f.get(checked_key)).replace("Z", "+00:00"))
                    if 0 <= (datetime.now(timezone.utc)-checked).total_seconds() < 600:
                        f[checked_key] = old_f[checked_key]
                        continue
                except (ValueError, TypeError):
                    pass
                recent = db.query(AnalysisSnapshot.payload_json).filter(
                    AnalysisSnapshot.symbol == symbol,
                    AnalysisSnapshot.created_at >= datetime.now(timezone.utc)-timedelta(hours=6),
                ).order_by(AnalysisSnapshot.created_at.desc()).limit(5).all()
                saved = []
                for (payload_json,) in recent:
                    try:
                        saved.append(json.loads(payload_json))
                    except (ValueError, TypeError):
                        continue
                recover_market_evidence(bundle, saved)
                f[checked_key] = datetime.now(timezone.utc).isoformat()
        try:
            bundle["news"] = article_news.attach(bundle.get("news") or [], symbol,
                (bundle.get("fundamentals") or {}).get("companyName") or bundle.get("company_name") or symbol)
        except Exception:
            # News queue outage must not block price analysis or exits.
            logging.getLogger(__name__).exception("Article cache unavailable for %s", symbol)
        result = score_bundle(bundle)
        with SessionLocal() as db:
            p = db.query(Position).filter(Position.symbol == symbol).order_by(Position.created_at.desc()).first()
            pp = db.query(PaperPosition).filter(PaperPosition.symbol == symbol).order_by(PaperPosition.opened_at.desc()).first() if not p else None
            pos_obj = p or pp
            if pos_obj and getattr(pos_obj, "entry_target", None) in (None, 0):
                target_plan = result.get("target_plan") or {}
                horizon = result.get("holding_horizon") or {}
                pos_obj.entry_target = target_plan.get("base_target")
                pos_obj.entry_stretch_target = target_plan.get("stretch_target")
                pos_obj.entry_stop = (result.get("levels") or {}).get("stop")
                pos_obj.entry_horizon_days = horizon.get("max_days")
                pos_obj.entry_plan_version = result.get("scoring_version")
                db.commit()
            pd = (
                {
                    "shares": p.shares, "avg_cost": p.avg_cost, "account": p.account,
                    "opened_at": p.created_at,
                    "entry_target": p.entry_target, "entry_stretch_target": p.entry_stretch_target,
                    "entry_stop": p.entry_stop, "entry_horizon_days": p.entry_horizon_days,
                    "entry_plan_version": p.entry_plan_version,
                }
                if p else
                {
                    "shares": pp.shares, "avg_cost": pp.avg_cost, "account": "Paper",
                    "opened_at": pp.opened_at,
                    "entry_target": pp.entry_target, "entry_stretch_target": pp.entry_stretch_target,
                    "entry_stop": pp.entry_stop, "entry_horizon_days": pp.entry_horizon_days,
                    "entry_plan_version": pp.entry_plan_version,
                }
                if pp else None
            )
            prior = db.query(RadarCandidate).filter(RadarCandidate.symbol == symbol).first()
            if prior and prior.current_json:
                try:
                    prior_payload=json.loads(prior.current_json)
                    # A calculation repair is not a deterioration in the company.
                    # Compare fundamentals only within the same scoring version.
                    result["previous_snapshot"]={
                        "breakdown": prior_payload.get("breakdown") or {},
                        "deterministic_score": prior_payload.get("deterministic_score"),
                        "action": prior_payload.get("action"),
                    } if prior_payload.get("scoring_version") == SCORING_VERSION else {}
                except Exception:
                    prior_payload = {}
                    result["previous_snapshot"] = {}
        # Preserve the last official government/OGE check between normal market scans.
        # Light news classification refreshes every analysis; structured official
        # sources are deliberately refreshed on a slower Top-20 cadence.
        if settings.strategic_capital_enabled and hasattr(self.provider, "strategic"):
            try:
                news_items = bundle.get("news") or []
                bundle["strategic_capital"] = self.provider.strategic.assess(
                    symbol,
                    company_name=(bundle.get("fundamentals") or {}).get("companyName") or symbol,
                    news=news_items if isinstance(news_items, list) else (news_items.get("items") or []),
                    annual_revenue=(bundle.get("fundamentals") or {}).get("totalRevenue"),
                    prior=prior_payload.get("strategic_capital") or {},
                    fetch_official=bool(strategic_refresh),
                    force_official=bool(strategic_refresh),
                )
                if isinstance(bundle.get("data_sources"), dict):
                    bundle["data_sources"]["strategic_capital"] = {
                        "source": "USAspending.gov + OGE annual/periodic disclosures + White House investment tracker + classified news",
                        "status": "shadow evidence",
                        "asof": bundle["strategic_capital"].get("official_checked_at") or bundle.get("asof"),
                    }
            except Exception:
                pass
        action, reason = position_action(result, bundle["price"], pd)
        plan = position_action_plan(action, result, bundle["price"], pd)
        if contextual_ai:
            ai = self.ai.analyze(symbol, bundle, result)
        else:
            from .analysis_engine import heuristic_ai
            ai = heuristic_ai(result)
        full = {**bundle, **result, **ai, "action": action, "action_reason": reason, "action_plan": plan, "position": pd}
        full["entry_qualification"] = entry_status(full)
        if persist:
            self.persist(full)
            if prior_payload.get("scoring_version") != SCORING_VERSION:
                f = full.get("fundamentals") or {}
                print("FUNDAMENTALS_REFRESH " + json.dumps({
                    "symbol": symbol, "scoring_version": SCORING_VERSION,
                    "quarterlyRevenueGrowth": f.get("quarterlyRevenueGrowth"),
                    "quarterly_period": f.get("_quarterly_period"),
                    "quarterly_status": f.get("_quarterly_status"),
                    "quarterly_method": f.get("_quarterly_method"),
                }, sort_keys=True), flush=True)
        return full

    def persist(self, full: dict):
        symbol = full["symbol"]
        compact = _compact_payload(full)
        compact_json = json.dumps(compact, default=str, separators=(",", ":"))
        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            cand = db.query(RadarCandidate).filter(RadarCandidate.symbol == symbol).first()
            old_action = cand.action if cand else None
            old_score = float(cand.score or 0) if cand else 0.0
            old_ai = float(cand.ai_score or 0) if cand else 0.0
            old_payload = {}
            if cand and cand.current_json:
                try: old_payload = json.loads(cand.current_json)
                except Exception: old_payload = {}
            if not cand:
                cand = RadarCandidate(symbol=symbol)
                db.add(cand)
            if old_action and old_action != full.get("action", "WATCH"):
                cand.previous_action = old_action
            cand.category = full.get("category", "Watch")
            cand.action = full.get("action", "WATCH")
            cand.score = full.get("deterministic_score", 0)
            cand.ai_score = full.get("ai_score", 0)
            cand.price = full.get("price", 0)
            rank = candidate_rank_score(full)
            cand.portfolio_rank_score = rank.get("score", 0)
            cand.rank_version = rank.get("version", "rank-v2-lanes")
            cand.lane = full.get("lane") if full.get("lane_qualified") is True else None
            cand.lane_qualified = bool(full.get("lane_qualified") is True)
            cand.current_json = compact_json
            cand.updated_at = now

            # Historical snapshots are compact and throttled. Priority names
            # (holdings/watchlist/manual requests) get an hourly checkpoint; broad
            # market candidates get a six-hour checkpoint unless something material
            # changes first.
            is_priority = bool(
                db.query(Position.id).filter(Position.symbol == symbol).first()
                or db.query(PaperPosition.id).filter(PaperPosition.symbol == symbol).first()
                or db.query(WatchlistItem.id).filter(WatchlistItem.symbol == symbol).first()
                or db.query(AnalysisRequest.id).filter(AnalysisRequest.symbol == symbol).first()
            )
            interval = settings.snapshot_interval_seconds if is_priority else settings.snapshot_interval_seconds * 6
            last_at = cand.last_snapshot_at
            if last_at and last_at.tzinfo is None:
                last_at = last_at.replace(tzinfo=timezone.utc)
            due = last_at is None or (now - last_at).total_seconds() >= interval
            score_changed = abs(float(cand.score or 0) - old_score) >= settings.snapshot_score_delta or abs(float(cand.ai_score or 0) - old_ai) >= settings.snapshot_score_delta
            old_news = old_payload.get("news") or {}
            new_news = compact.get("news") or {}
            old_thesis = old_payload.get("thesis_assessment") or {}
            new_thesis = compact.get("thesis_assessment") or {}
            material_change = bool(
                old_action != cand.action
                or score_changed
                or old_news.get("material_events", 0) != new_news.get("material_events", 0)
                or bool(old_thesis.get("invalidated")) != bool(new_thesis.get("invalidated"))
            )
            key = _snapshot_key(compact)
            if due or material_change or not cand.last_snapshot_key:
                db.add(AnalysisSnapshot(
                    symbol=symbol,
                    price=full.get("price", 0),
                    deterministic_score=full.get("deterministic_score", 0),
                    analyst_score=full.get("analyst_score") or 0,
                    ai_score=full.get("ai_score", 0),
                    expected_yield_pct=full.get("expected_yield_pct", 0),
                    ai_expected_yield_pct=full.get("ai_expected_yield_pct", 0),
                    category=full.get("category", "Watch"),
                    action=full.get("action", "WATCH"),
                    payload_json=compact_json,
                ))
                cand.last_snapshot_at = now
                cand.last_snapshot_key = key

            # Attention queue: actionable events only. WAIT/WATCH/HOLD states remain
            # visible in the Radar but are deliberately excluded from the interruptive
            # "What needs attention now" queue.
            alert_type = None
            severity = "info"
            title = ""
            alert_action = None
            buy_action, buy_reason = _attention_buy_signal(full, has_position=bool(full.get("position")))
            if buy_action:
                alert_type, severity, alert_action = "buy_level", "high", buy_action
                prefix = "Add level reached" if full.get("position") else "Entry level reached"
                title = f"{symbol}: {prefix} — {buy_action}"
            elif full.get("action") in {"TAKE PARTIAL PROFIT", "REDUCE", "EXIT"}:
                # REDUCE/EXIT are already thesis-gated by position_action().
                alert_type, severity, alert_action = "position_review", "high", full.get("action")
                title = f"{symbol}: {alert_action}"
            if alert_type and alert_action:
                plan = full.get("action_plan") or {}
                qty_text = ""
                if plan.get("suggested_shares"):
                    qty_text = f" Suggested: {plan['suggested_shares']:g} shares ({plan.get('actual_percent', 0):.1f}% of position)."
                message=((buy_reason if buy_action else full.get("action_reason", "")) + qty_text).strip()
                active = db.query(Alert).filter(
                    Alert.symbol == symbol, Alert.alert_type == alert_type,
                    Alert.action == alert_action, Alert.acknowledged == False,
                ).order_by(Alert.created_at.desc()).first()
                if active:
                    active.severity=severity; active.title=title; active.message=message
                    active.created_at=now; active.snoozed_until=None
                else:
                    # One active attention state per symbol. Old WAIT and superseded
                    # attention states are retained historically as acknowledged rows.
                    for stale in db.query(Alert).filter(Alert.symbol==symbol, Alert.acknowledged==False).all():
                        stale.acknowledged=True
                    db.add(Alert(
                        symbol=symbol, alert_type=alert_type, severity=severity, title=title,
                        message=message, action=alert_action,
                    ))
            else:
                # If the symbol is no longer actionable, close any stale live alerts
                # (including legacy WAIT MORE alerts) without deleting their history.
                for stale in db.query(Alert).filter(Alert.symbol==symbol, Alert.acknowledged==False).all():
                    stale.acknowledged=True
            db.commit()

    def _enrich_strategic_top_candidates(self) -> tuple[bool, list[str]]:
        """Refresh official strategic-capital evidence for a few Top-20 names.

        This is intentionally rate-limited and shadow-only: it prevents the scanner
        from hammering USAspending/OGE and prevents a new political factor from
        silently changing the validated rank-v2 portfolio rules.
        """
        if not settings.strategic_capital_enabled or not hasattr(self.provider, "strategic"):
            return False, []
        now = datetime.now(timezone.utc)
        if self._last_strategic_enrich_at:
            elapsed = (now - self._last_strategic_enrich_at).total_seconds()
            if elapsed < settings.strategic_enrich_interval_seconds:
                return False, []
        self._last_strategic_enrich_at = now
        changed_symbols: list[str] = []
        refreshed = 0
        ttl = max(1, settings.strategic_official_refresh_hours) * 3600
        with SessionLocal() as db:
            rows = db.query(RadarCandidate).order_by(
                RadarCandidate.portfolio_rank_score.desc(), RadarCandidate.updated_at.desc()
            ).limit(settings.optimizer_visible_limit).all()
            for cand in rows:
                if refreshed >= max(1, settings.strategic_enrich_per_cycle):
                    break
                try:
                    payload = json.loads(cand.current_json or "{}")
                except Exception:
                    payload = {}
                if not isinstance(payload, dict) or not payload.get("symbol"):
                    continue
                prior_signal = payload.get("strategic_capital") or {}
                checked = prior_signal.get("official_checked_at")
                if checked:
                    try:
                        dt = datetime.fromisoformat(str(checked).replace("Z", "+00:00"))
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        check_status = str(prior_signal.get("official_check_status") or "").upper()
                        federal = prior_signal.get("federal_awards") or {}
                        partial_or_failed = (
                            check_status in {"PARTIAL", "FAILED"}
                            or bool(federal.get("retry_recommended"))
                            or "UNAVAILABLE" in str(federal.get("status") or "").upper()
                            or "PARTIAL" in str(federal.get("status") or "").upper()
                        )
                        effective_ttl = max(60, settings.strategic_error_retry_seconds) if partial_or_failed else ttl
                        if (now - dt).total_seconds() < effective_ttl:
                            continue
                    except Exception:
                        pass
                fundamentals = payload.get("fundamentals") or {}
                company = fundamentals.get("companyName") or cand.symbol
                news = payload.get("news") or {}
                items = news.get("items") if isinstance(news, dict) else news
                try:
                    enriched = self.provider.strategic.assess(
                        cand.symbol, company_name=company, news=items or [],
                        annual_revenue=fundamentals.get("totalRevenue"),
                        prior=prior_signal, fetch_official=True, force_official=False,
                    )
                except Exception:
                    continue
                before = _strategic_fingerprint(prior_signal)
                after = _strategic_fingerprint(enriched)
                payload["strategic_capital"] = enriched
                src = payload.setdefault("data_sources", {})
                src["strategic_capital"] = {
                    "source": "USAspending.gov + OGE annual/periodic disclosures + White House investment tracker + classified news",
                    "status": "shadow evidence / official sources checked",
                    "asof": enriched.get("official_checked_at"),
                }
                compact = _compact_payload(payload)
                cand.current_json = json.dumps(compact, default=str, separators=(",", ":"))
                cand.updated_at = now
                refreshed += 1
                if before != after:
                    changed_symbols.append(cand.symbol)
                    db.add(AnalysisSnapshot(
                        symbol=cand.symbol, price=float(payload.get("price") or cand.price or 0),
                        deterministic_score=float(payload.get("deterministic_score") or cand.score or 0),
                        analyst_score=float(payload.get("analyst_score") or 0),
                        ai_score=float(payload.get("ai_score") or cand.ai_score or 0),
                        expected_yield_pct=float(payload.get("expected_yield_pct") or 0),
                        ai_expected_yield_pct=float(payload.get("ai_expected_yield_pct") or 0),
                        category=payload.get("category") or cand.category or "Watch",
                        action=payload.get("action") or cand.action or "WATCH",
                        payload_json=cand.current_json,
                    ))
                    cand.last_snapshot_at = now
                    cand.last_snapshot_key = _snapshot_key(compact)
            db.commit()
        return bool(changed_symbols), changed_symbols

    def _sync_rotation_alerts(self, blocked_symbols: set[str] | None = None):
        """Gate live attention only after the optimizer and paper executor agree.

        A signal that cannot produce a paper order because of target-size, cash,
        risk or whole-share constraints is not shown as an actionable alert.
        """
        if not settings.optimizer_live_gating:
            return
        blocked_symbols = {str(s).upper() for s in (blocked_symbols or set())}
        with SessionLocal() as db:
            position_rows = db.query(Position).all()
            paper_rows = db.query(PaperPosition).all()
            owned = {p.symbol for p in position_rows} | {p.symbol for p in paper_rows}
            pref = db.query(PortfolioPreference).filter(PortfolioPreference.account == "Main").first()
            profile = normalise_profile(pref.risk_profile if pref else "MEDIUM")
            rows = db.query(RadarCandidate).order_by(
                RadarCandidate.portfolio_rank_score.desc(), RadarCandidate.updated_at.desc()
            ).limit(60).all()
            have = {r.symbol for r in rows}
            missing = [s for s in owned if s not in have]
            if missing:
                rows += db.query(RadarCandidate).filter(RadarCandidate.symbol.in_(missing)).all()
            analyses = {}
            for c in rows:
                try:
                    a = json.loads(c.current_json or "{}")
                except Exception:
                    a = {}
                if isinstance(a, dict):
                    a.setdefault("symbol", c.symbol); a.setdefault("price", c.price)
                    a.setdefault("deterministic_score", c.score); a.setdefault("ai_score", c.ai_score)
                    a.setdefault("action", c.action); a.setdefault("category", c.category)
                    analyses[c.symbol] = a
            plan = build_optimizer_plan(
                analyses, owned, profile=profile,
                visible_limit=settings.optimizer_visible_limit,
                shortlist_limit=settings.optimizer_shortlist_limit,
                target_positions=settings.optimizer_target_positions,
                max_positions=settings.optimizer_max_positions,
                min_rank_score=settings.optimizer_min_rank_score,
                rotation_gap=settings.optimizer_rotation_gap,
                rotation_yield_gap=settings.optimizer_rotation_yield_gap,
            )
            approved = {r["symbol"]: r for r in plan["selected_new"] if r["symbol"] not in blocked_symbols}
            for r in plan["visible"]:
                if r.get("owned") and r.get("optimizer_action") == "ADD" and r["symbol"] not in blocked_symbols:
                    approved[r["symbol"]] = r
            now = datetime.now(timezone.utc)

            # Price reaching a buy zone is no longer enough to interrupt the user.
            # Only the 5-7-position optimizer can approve an entry alert.
            for alert in db.query(Alert).filter(Alert.alert_type == "buy_level", Alert.acknowledged == False).all():
                if alert.symbol not in approved:
                    alert.acknowledged = True
            for sym, r in approved.items():
                action = "ADD" if r.get("optimizer_action") == "ADD" else (r.get("entry_signal") or "BUY")
                title = f"{sym}: Optimizer approved — {action}"
                message = f"Portfolio rank #{r.get('market_rank')}/{settings.optimizer_visible_limit} • priority {r.get('rank_score',0):.1f}/100 • {r.get('risk_fit')} • AI {r.get('ai_confirmation')} / Analyst {r.get('analyst_confirmation')} (confirmation only)."
                active = db.query(Alert).filter(
                    Alert.symbol == sym, Alert.alert_type == "buy_level", Alert.acknowledged == False
                ).order_by(Alert.created_at.desc()).first()
                if active:
                    active.action = action; active.title = title; active.message = message
                    active.severity = "high"; active.created_at = now; active.snoozed_until = None
                else:
                    db.add(Alert(symbol=sym, alert_type="buy_level", severity="high", title=title, message=message, action=action))

            rotation_titles = set()
            for rot in plan["rotations"]:
                src, dst = rot["symbol_from"], rot["symbol_to"]
                title = f"SWAP CANDIDATE: {src} → {dst}"
                rotation_titles.add(title)
                active = db.query(Alert).filter(
                    Alert.symbol == src, Alert.alert_type == "portfolio_swap", Alert.action == "ROTATE", Alert.acknowledged == False
                ).order_by(Alert.created_at.desc()).first()
                if active:
                    active.title = title; active.message = rot["detail"]; active.severity = "high"
                    active.created_at = now; active.snoozed_until = None
                else:
                    db.add(Alert(symbol=src, alert_type="portfolio_swap", severity="high", title=title, message=rot["detail"], action="ROTATE"))
            for stale in db.query(Alert).filter(Alert.alert_type == "portfolio_swap", Alert.acknowledged == False).all():
                if stale.title not in rotation_titles:
                    stale.acknowledged = True
            db.commit()

    def holding_symbols(self) -> list[str]:
        """All open manual + paper holdings; never subject to the priority cap."""
        with SessionLocal() as db:
            positions = [p.symbol for p in db.query(Position).all()]
            paper_positions = [p.symbol for p in db.query(PaperPosition).all()]
        return list(dict.fromkeys(s.upper() for s in (positions + paper_positions + experiment_holding_symbols()) if s))

    def priority_symbols(self) -> list[str]:
        """Non-holding symbols that deserve full analysis before broad-market candidates."""
        with SessionLocal() as db:
            watch = [w.symbol for w in db.query(WatchlistItem).all()]
            manual = [a.symbol for a in db.query(AnalysisRequest).order_by(AnalysisRequest.created_at.desc()).limit(20).all()]
        holdings = set(self.holding_symbols())
        ordered = manual + watch + list(settings.radar_symbols)
        return [s for s in dict.fromkeys(x.upper() for x in ordered if x) if s not in holdings]

    def _refresh_universe_size(self) -> int:
        """Refresh the eligible U.S. universe count without running a market scan.

        This keeps dashboard metadata accurate after a deploy/restart even while
        the regular session is closed. The full rotating prefilter/deep-analysis
        path still runs only when the scanner is allowed to scan the market.
        """
        universe = self.provider.us_equity_universe()
        self.universe_size = len(universe)
        return self.universe_size

    def _universe_slice(self) -> list[dict]:
        universe = self.provider.us_equity_universe()
        self.universe_size = len(universe)
        if not universe:
            self.last_universe_start = 0
            return []
        batch_size = max(1, min(settings.universe_prefilter_batch_size, len(universe)))
        now = datetime.now(timezone.utc).astimezone(NY)
        if self.market_open(now):
            seconds_from_open = max(0, (now.hour * 60 + now.minute - 570) * 60 + now.second)
            slot = seconds_from_open // max(30, settings.scan_interval_seconds)
        else:
            slot = self.scan_count
        # Initialize near the current session slot, then advance by batches that
        # actually ran. Wall-clock slots skip names whenever a cycle runs long.
        start = int((slot * batch_size) % len(universe)) if self._universe_cursor is None else self._universe_cursor % len(universe)
        self._universe_cursor = (start + batch_size) % len(universe)
        self.last_universe_start = start
        if start + batch_size <= len(universe):
            return universe[start:start + batch_size]
        return universe[start:] + universe[:(start + batch_size) % len(universe)]

    def _prefilter_universe(self, entries: list[dict]) -> list[dict]:
        """Build balanced cheap-discovery queues for both investment lanes.

        Core exploration deliberately uses liquidity rather than momentum so quiet,
        high-quality businesses are still deep-analysed. Explosive exploration
        requires positive momentum/volume and never rewards large negative moves.
        Full lane qualification still happens after fundamentals/news analysis.
        """
        if not entries:
            self.last_universe_prefiltered = 0
            self.last_universe_candidates = 0
            self.last_universe_core_candidates = 0
            self.last_universe_explosive_candidates = 0
            return []

        results: list[dict] = []
        workers = max(1, min(settings.quick_scan_workers, 16))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(self.provider.quick_scan, e["symbol"]): e for e in entries}
            for fut in as_completed(futures):
                try:
                    q = fut.result()
                    q["name"] = futures[fut].get("name")
                    results.append(q)
                except Exception:
                    continue
        self.last_universe_prefiltered = len(results)

        limit = max(2, settings.universe_deep_candidates)
        explosive_quota = max(1, limit // 2)
        core_quota = max(1, limit - explosive_quota)

        explosive_pool = [
            r for r in results
            if float(r.get("price") or 0) >= 5
            and float(r.get("avg_dollar_volume_20") or r.get("dollar_volume") or 0) >= 20_000_000
            and (
                float(r.get("change_5_pct") or 0) >= 3
                or float(r.get("change_20_pct") or 0) >= 7
                or float(r.get("relative_volume") or 0) >= 1.5
                or float(r.get("near_20d_high") or 0) >= 0.985
            )
        ]
        explosive_pool.sort(key=lambda r: float(r.get("scan_score") or 0), reverse=True)

        # Core lane exploration is intentionally not a second momentum list.
        # Prefer liquid names from each rotating slice, then let the full
        # fundamentals/valuation model decide whether they qualify.
        core_pool = [
            r for r in results
            if float(r.get("price") or 0) >= 5
            and float(r.get("avg_dollar_volume_20") or r.get("dollar_volume") or 0) >= 10_000_000
        ]
        core_pool.sort(
            key=lambda r: (
                float(r.get("avg_dollar_volume_20") or r.get("dollar_volume") or 0),
                float(r.get("near_20d_high") or 0),
            ),
            reverse=True,
        )

        chosen: list[dict] = []
        seen: set[str] = set()
        for r in explosive_pool[:explosive_quota]:
            chosen.append(r); seen.add(r["symbol"])
        for r in core_pool:
            if r["symbol"] in seen:
                continue
            chosen.append(r); seen.add(r["symbol"])
            if len(chosen) >= explosive_quota + core_quota:
                break

        # If one lane is sparse, fill the remaining deep-analysis budget with the
        # strongest eligible names from either lane, never with sub-$5 illiquid dust.
        if len(chosen) < limit:
            fallback = sorted(
                [
                    r for r in results
                    if float(r.get("price") or 0) >= 5
                    and float(r.get("avg_dollar_volume_20") or r.get("dollar_volume") or 0) >= 10_000_000
                ],
                key=lambda r: (
                    float(r.get("scan_score") or 0),
                    float(r.get("avg_dollar_volume_20") or r.get("dollar_volume") or 0),
                ),
                reverse=True,
            )
            for r in fallback:
                if r["symbol"] in seen:
                    continue
                chosen.append(r); seen.add(r["symbol"])
                if len(chosen) >= limit:
                    break

        explosive_symbols = {r["symbol"] for r in explosive_pool[:explosive_quota]}
        self.last_universe_explosive_candidates = sum(1 for r in chosen if r["symbol"] in explosive_symbols)
        self.last_universe_core_candidates = max(0, len(chosen) - self.last_universe_explosive_candidates)
        self.last_universe_candidates = len(chosen)
        return chosen[:limit]

    def stale_scoring_symbols(self, limit: int = 20) -> list[str]:
        """Prioritize persisted candidates produced by an older scoring engine.

        A deploy that changes target/R-R logic must not leave the dashboard showing
        an old cached target until that symbol happens to rotate through discovery.
        """
        if limit <= 0:
            return []
        stale: list[str] = []
        with SessionLocal() as db:
            # Filter JSON versions inside the database and return symbols only.
            # Iterating full candidate payloads downloaded the entire scored
            # universe every cycle when all saved versions were already current.
            # Guard malformed legacy JSON before extraction on both backends.
            payload = RadarCandidate.current_json
            if db.bind.dialect.name == "postgresql":
                # Production uses PostgreSQL 18; pg_input_is_valid is available
                # from PostgreSQL 16 and avoids errors on corrupt legacy rows.
                version = case(
                    (func.pg_input_is_valid(payload, "jsonb"),
                     cast(payload, JSONB)["scoring_version"].astext),
                    else_=None,
                )
            else:
                version = case(
                    (func.json_valid(payload), func.json_extract(payload, "$.scoring_version")),
                    else_=None,
                )
            rows = db.query(RadarCandidate.symbol).filter(
                or_(version.is_(None), version != SCORING_VERSION)
            ).order_by(
                RadarCandidate.portfolio_rank_score.desc(), RadarCandidate.updated_at.desc()
            ).limit(limit).all()
            stale = [row.symbol for row in rows]
        if len(stale) < limit:
            stale.extend(s for s in article_news.dirty_symbols(limit) if s not in stale)
        return stale[:limit]

    def persisted_qualified_symbols(self, limit: int = 8) -> list[str]:
        """Current best lane-qualified names, ranked from persisted analysis."""
        if limit <= 0:
            return []
        with SessionLocal() as db:
            rows = (
                db.query(RadarCandidate.symbol)
                .filter(RadarCandidate.lane_qualified == True)
                .order_by(RadarCandidate.portfolio_rank_score.desc(), RadarCandidate.updated_at.desc())
                .limit(limit)
                .all()
            )
            return [r.symbol for r in rows]

    def preopen_warmup_symbols(self, limit: int = 32) -> list[str]:
        """Highest-value analysis queue for the 30-minute pre-open handoff.

        Do not wait for the exhaustive overnight audit to finish. Refresh existing
        holdings and persisted qualified names first, then stale-version rows,
        explicit priority/watchlist names and fresh discovery movers. This gives
        the first regular-session optimizer cycle current inputs without allowing
        any pre-open paper execution.
        """
        limit = max(1, limit)
        session_date = datetime.now(timezone.utc).astimezone(NY).date().isoformat()
        if self._preopen_warmup_date != session_date:
            self._preopen_warmup_date = session_date
            self._preopen_warmed_symbols.clear()

        holdings = self.holding_symbols()
        persisted = self.persisted_qualified_symbols(limit=max(8, limit // 2))
        stale = self.stale_scoring_symbols(limit=max(8, limit // 3))
        priority = self.priority_symbols()[: settings.priority_deep_limit]
        discovered: list[str] = []
        try:
            movers = self.provider.discover(100)
            movers.sort(key=lambda x: float(x.get("change_pct") or 0), reverse=True)
            discovered = [d["symbol"] for d in movers[: settings.discovery_deep_candidates]]
        except Exception:
            pass

        # Holdings are deliberately refreshed every pre-open cycle. Other names
        # rotate across the 30-minute window instead of repeatedly consuming the
        # whole batch with the same persisted Top 20.
        ordered = list(dict.fromkeys(
            s.upper() for s in holdings + persisted + priority + discovered + stale if s
        ))
        holdings_set = {s.upper() for s in holdings}
        fresh = [
            s for s in ordered
            if s in holdings_set or s not in self._preopen_warmed_symbols
        ]
        return fresh[:limit]


    def candidate_symbols(self):
        """Return the live deep-analysis queue in decision-value order.

        A market-open cycle must not spend its first minute repairing a long stale
        backlog. Holdings and already-qualified names are refreshed first, followed
        by fresh movers/priority names; stale-version and rotating broad-universe
        work is carried behind them.
        """
        holdings = self.holding_symbols()
        persisted = self.persisted_qualified_symbols(limit=LIVE_PERSISTED_QUALIFIED_MAX)
        priority = self.priority_symbols()[: settings.priority_deep_limit]
        discovered = self.provider.discover(100)
        discovered.sort(key=lambda x: float(x.get("change_pct") or 0), reverse=True)
        discovery_symbols = [d["symbol"] for d in discovered[: settings.discovery_deep_candidates]]
        stale = self.stale_scoring_symbols(limit=LIVE_STALE_REFRESH_MAX)
        broad = self._prefilter_universe(self._universe_slice())
        broad_symbols = [q["symbol"] for q in broad]
        ordered = holdings + persisted + discovery_symbols + priority + stale + broad_symbols
        return list(dict.fromkeys(s.upper() for s in ordered if s))

    def _deep_analysis_batch(self, symbols: list[str]) -> tuple[list[str], int]:
        """Keep each live cycle bounded while preserving deferred coverage.

        Fresh decision-relevant names take precedence over yesterday's overflow;
        the remainder is deduplicated and carried into later cycles. With current
        provider latency a 12-name ceiling keeps a normal live cycle near the
        sub-minute target instead of allowing a 40-48 name multi-minute block.
        """
        holdings = self.holding_symbols()
        fresh = list(dict.fromkeys(holdings + symbols))
        deferred = [s for s in self._deferred_analysis_symbols if s not in fresh]
        queued = fresh + deferred
        budget = min(LIVE_DEEP_ANALYSIS_MAX, max(1, settings.scan_batch_size), len(queued))
        batch = queued[:budget]
        self._deferred_analysis_symbols = queued[budget:]
        return batch, len(queued)

    def _paper_optimizer_policy_fingerprint(self) -> str:
        """Fingerprint every rule that can change paper-entry eligibility.

        This is intentionally independent of ticker signal transitions. Removing
        a sector/tier restriction, changing risk profile or changing optimizer
        thresholds must invalidate the prior portfolio selection even if GWRE (or
        any other candidate) remains BUY before and after the change.
        """
        with SessionLocal() as db:
            pref = db.query(PortfolioPreference).filter(PortfolioPreference.account == "Main").first()
            profile = normalise_profile(pref.risk_profile if pref else "MEDIUM")
        material = {
            "policy_version": "eligibility-v5-shared-min-rr",
            "risk_profile": profile,
            "visible_limit": settings.optimizer_visible_limit,
            "paper_trade_cost_bps": settings.paper_trade_cost_bps,
            "investable_entry_actions": sorted(INVESTABLE_ENTRY_ACTIONS),
            "min_entry_risk_reward": MIN_ENTRY_RISK_REWARD,
            # Explicitly encode the uncapped policy. These values are intentionally
            # absent as eligibility gates and changing legacy env vars must not
            # change which qualified Top-20 names are bought.
            "holding_count_cap": None,
            "sector_position_cap": None,
            "per_tier_max_positions": None,
            "shortlist_entry_gate": None,
            "min_rank_entry_gate": None,
            "risk_fit_entry_gate": None,
        }
        return hashlib.sha1(json.dumps(material, sort_keys=True, default=str).encode("utf-8")).hexdigest()

    def _paper_optimizer_invalidation_event(self) -> bool:
        """Return True once when optimizer eligibility/config becomes stale.

        The first open-market scan after a service restart intentionally returns
        True. That one harmless recheck prevents stale portfolio decisions after a
        deployment that changes eligibility rules.
        """
        current = self._paper_optimizer_policy_fingerprint()
        previous = self._paper_optimizer_policy_state
        self._paper_optimizer_policy_state = current
        return previous != current

    def _paper_entry_event(self, full: dict) -> bool:
        """True when an investable candidate materially changes this scan.

        Multiple changes in one scanner cycle are coalesced by ``scan_once``
        into a single paper-optimizer run.  Rank is bucketed in 5-point steps so
        tiny intraday fluctuations do not churn the paper portfolio.
        """
        symbol = str(full.get("symbol") or "").upper()
        if not symbol:
            return False
        rank = candidate_rank_score(full)
        signal = rank.get("entry_signal")
        zone = str(full.get("entry_zone_status") or "").upper()
        rank_score = float(rank.get("score") or 0)
        state = (
            signal if signal in INVESTABLE_ENTRY_ACTIONS else None,
            zone if signal in INVESTABLE_ENTRY_ACTIONS else None,
            int(rank_score // 5) if signal in INVESTABLE_ENTRY_ACTIONS else -1,
            bool((full.get("thesis_assessment") or {}).get("invalidated")),
            bool(full.get("negative_news_override")),
        )
        previous = self._paper_entry_state.get(symbol)
        if signal in INVESTABLE_ENTRY_ACTIONS:
            self._paper_entry_state[symbol] = state
            return previous != state
        self._paper_entry_state.pop(symbol, None)
        return False

    def scan_once(self, force: bool = False):
        if not self._scan_lock.acquire(blocking=False):
            return {
                "status": "busy",
                "message": "A scanner cycle is already in progress",
                "started_at": self.scan_started_at.isoformat() if self.scan_started_at else None,
                "last_scan": self.last_scan.isoformat() if self.last_scan else None,
            }
        self.scan_in_progress = True
        self.scan_started_at = datetime.now(timezone.utc)
        started = time.perf_counter()
        result = None
        try:
            result = self._scan_once_impl(force)
            self.last_result = result
            return result
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"
            self.last_result = {"status": "error", "error": self.last_error}
            raise
        finally:
            self.last_scan_duration_seconds = round(time.perf_counter() - started, 2)
            summary = dict(self.last_result or {})
            summary.update({
                "scan_count": self.scan_count,
                "force": force,
                "duration_seconds": self.last_scan_duration_seconds,
                "market_open": self.market_open(),
                "last_error": self.last_error,
            })
            print("SCAN_CYCLE " + json.dumps(summary, default=str, sort_keys=True), flush=True)
            self.scan_in_progress = False
            self.scan_started_at = None
            self._scan_lock.release()

    def _scan_once_impl(self, force: bool = False):
        audit = getattr(self, "full_universe_scan", None)
        market_open = self.market_open()
        preopen = self.preopen_warmup()
        # Overnight audit owns provider capacity only until 09:00 ET. From then
        # through the close, the actionable radar has priority even if the audit
        # thread remains alive in a paused state.
        if not force and not market_open and not preopen and audit and audit.active():
            return {"status": "full_universe_audit_running", "execution_enabled": False}
        if not force and not market_open:
            # Universe metadata is safe to refresh while the market is closed.
            # Without this, a fresh process starts at universe_size=0 and the
            # dashboard misleadingly says "loading" until the next open scan.
            errors: list[str] = []
            # A data/scoring repair must also reach saved tickers outside trading
            # hours. Refresh analyses only; this path never runs the paper cycle.
            refreshed_symbols: list[str] = []
            refresh_symbols = (
                self.preopen_warmup_symbols(limit=settings.scan_batch_size)
                if preopen else self.stale_scoring_symbols(limit=20)
            )
            for symbol in refresh_symbols:
                try:
                    self.analyze_symbol(symbol)
                    refreshed_symbols.append(symbol)
                    if preopen:
                        self._preopen_warmed_symbols.add(symbol)
                except Exception as e:
                    errors.append(f"{symbol}: {type(e).__name__}")
            if self.universe_size <= 0:
                try:
                    self._refresh_universe_size()
                except Exception as e:
                    errors.append(f"universe metadata: {type(e).__name__}")
            # Official-source evidence is not market-data dependent. Keep the
            # Top-20 strategic-capital queue moving even while U.S. equities are
            # closed so users do not have to open every stock and click Refresh.
            strategic_changed = False
            strategic_symbols: list[str] = []
            # Strategic-capital evidence is shadow-only and can be relatively
            # expensive. During the pre-open handoff, spend the limited window on
            # price/fundamental/target refreshes that affect opening decisions.
            if not preopen:
                try:
                    strategic_changed, strategic_symbols = self._enrich_strategic_top_candidates()
                except Exception as e:
                    errors.append(f"strategic capital: {type(e).__name__}")
            self.last_scan = datetime.now(timezone.utc)
            self.scan_count += 1
            self.last_deep_analyzed = len(refreshed_symbols)
            self.last_error = "; ".join(errors[:5]) if errors else None
            return {
                "status": "preopen_warmup" if preopen else "market_closed",
                "analyzed": len(refreshed_symbols), "refreshed_symbols": refreshed_symbols, "universe_size": self.universe_size,
                "strategic_enriched": strategic_symbols, "strategic_changed": strategic_changed,
                "execution_enabled": False,
                "preopen": preopen,
                "errors": errors,
            }
        syms = self.candidate_symbols()
        batch, queued_count = self._deep_analysis_batch(syms)
        effective_batch_size = len(batch)
        # Fetch scores before optional P/E/profile enrichment consumes requests.
        analyst_provider = getattr(self.provider, "analyst", None)
        if hasattr(analyst_provider, "prefetch_recommendations"):
            analyst_provider.prefetch_recommendations(batch)
        ok = 0
        errors: list[str] = []
        lane_core = 0
        lane_explosive = 0
        lane_qualified = 0
        core_quality_pass = 0
        rr_below_min_analyzed = 0
        rr_entry_eligible_analyzed = 0
        rr_below_min_symbols: list[dict] = []
        rr_entry_eligible_symbols: list[dict] = []
        qualified_symbols: list[str] = []
        qualified_owned_symbols: list[str] = []
        qualified_new_symbols: list[str] = []
        core_blocker_counts: dict[str, int] = {}
        explosive_blocker_counts: dict[str, int] = {}
        # Portfolio-rule/config changes remain diagnostic events, but paper
        # allocation now re-evaluates the complete current Top 20 on every open-
        # market scanner cycle. This guarantees that a stock which stays BUY while
        # moving into the Top 20 is not missed because no BUY -> BUY transition
        # occurred.
        optimizer_policy_event = self._paper_optimizer_invalidation_event()
        paper_entry_event = optimizer_policy_event
        paper_top20_recheck = True
        paper_event_symbols: list[str] = []
        holding_set = set(self.holding_symbols())
        holding_quotes: list[dict] = []
        experiment_observations: list[dict] = []
        for sym in batch:
            try:
                full = self.analyze_symbol(sym)
                experiment_observations.append(full)
                if sym in holding_set:
                    current_price = float(full.get("price") or 0)
                    previous_close = float(full.get("previous_close") or 0)
                    holding_quotes.append({
                        "symbol": sym,
                        "price": round(current_price, 4),
                        "previous_close": round(previous_close, 4) if previous_close else None,
                        "day_change_pct": round(((current_price / previous_close) - 1) * 100, 2) if current_price and previous_close else None,
                    })
                if full.get("core_quality_qualified") is True:
                    core_quality_pass += 1
                if full.get("lane_qualified") is True:
                    lane_qualified += 1
                    rr_value = float(full.get("risk_reward") or 0)
                    if rr_value >= MIN_ENTRY_RISK_REWARD:
                        rr_entry_eligible_analyzed += 1
                        rr_entry_eligible_symbols.append({"symbol": sym, "risk_reward": round(rr_value, 2)})
                    else:
                        rr_below_min_analyzed += 1
                        rr_below_min_symbols.append({"symbol": sym, "risk_reward": round(rr_value, 2)})
                    qualified_symbols.append(sym)
                    if full.get("position"):
                        qualified_owned_symbols.append(sym)
                    else:
                        qualified_new_symbols.append(sym)
                if full.get("lane") == "CORE_QUALITY":
                    lane_core += 1
                elif full.get("lane") == "EXPLOSIVE":
                    lane_explosive += 1
                for blocker in full.get("core_blockers") or []:
                    core_blocker_counts[blocker] = core_blocker_counts.get(blocker, 0) + 1
                for blocker in full.get("explosive_blockers") or []:
                    explosive_blocker_counts[blocker] = explosive_blocker_counts.get(blocker, 0) + 1
                if self._paper_entry_event(full):
                    paper_entry_event = True
                    paper_event_symbols.append(sym)
                ok += 1
            except Exception as e:
                errors.append(f"{sym}: {type(e).__name__}")
        try:
            strategic_changed, strategic_symbols = self._enrich_strategic_top_candidates()
            if strategic_changed:
                # Re-run the paper optimizer once so the latest evidence is present
                # in the forward-test decision record. Portfolio Priority v2 itself is unchanged.
                paper_entry_event = True
                paper_event_symbols.extend(s for s in strategic_symbols if s not in paper_event_symbols)
        except Exception as e:
            errors.append(f"strategic capital: {type(e).__name__}")
        paper_result: dict = {"status": "not_run", "executed_orders": [], "blocked_orders": []}
        try:
            # Re-evaluate the complete current qualified Top 20 every market-open
            # scan. Paper execution runs before alert reconciliation so "attention
            # now" reflects what actually executed or what is genuinely blocked.
            paper_result = run_paper_cycle(self.provider, entry_event=paper_top20_recheck)
        except Exception as e:
            errors.append(f"paper trading: {type(e).__name__}")
        try:
            # The agreed paper account consumes the same corrected analysis
            # that is persisted and displayed on the dashboard.
            self.last_experiment_result = run_experiment_cycle(
                experiment_observations, market_open=self.market_open())
        except Exception as e:
            errors.append(f"score-band experiment: {type(e).__name__}")
        try:
            blocked_symbols = {
                str(x.get("symbol") or "").upper()
                for x in (paper_result.get("blocked_orders") or [])
                if x.get("symbol")
            }
            self._sync_rotation_alerts(blocked_symbols)
        except Exception as e:
            errors.append(f"portfolio optimizer: {type(e).__name__}")
        # Release cyclic/transient analysis objects promptly between cycles. This
        # is a secondary guard; the primary 502 fix is keeping heavyweight PDF
        # parsing out of the live process.
        gc.collect()
        self.last_scan = datetime.now(timezone.utc)
        self.scan_count += 1
        self.last_deep_analyzed = ok
        self.last_error = "; ".join(errors[:5]) if errors else None
        persisted_qualified_symbols: list[str] = []
        persisted_qualified_owned: list[str] = []
        persisted_qualified_new: list[str] = []
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=4)
            with SessionLocal() as db:
                rows = (
                    db.query(RadarCandidate)
                    .filter(RadarCandidate.lane_qualified == True, RadarCandidate.updated_at >= cutoff)
                    .order_by(RadarCandidate.portfolio_rank_score.desc(), RadarCandidate.updated_at.desc())
                    .limit(max(20, settings.optimizer_visible_limit))
                    .all()
                )
                owned_now = {p.symbol for p in db.query(Position).all()} | {p.symbol for p in db.query(PaperPosition).all()}
                persisted_qualified_symbols = [r.symbol for r in rows]
                persisted_qualified_owned = [r.symbol for r in rows if r.symbol in owned_now]
                persisted_qualified_new = [r.symbol for r in rows if r.symbol not in owned_now]
        except Exception as e:
            errors.append(f"persisted qualified telemetry: {type(e).__name__}")
        return {
            "status": "ok", "analyzed": ok, "errors": errors, "candidates": len(syms),
            "score_diagnostics": scan_score_diagnostics(experiment_observations),
            "universe_size": self.universe_size,
            "universe_prefiltered": self.last_universe_prefiltered,
            "universe_deep_candidates": self.last_universe_candidates,
            "universe_core_candidates": self.last_universe_core_candidates,
            "universe_explosive_candidates": self.last_universe_explosive_candidates,
            "universe_start": self.last_universe_start,
            "lane_qualified_analyzed": lane_qualified,
            "rr_entry_eligible_analyzed": rr_entry_eligible_analyzed,
            "rr_below_min_analyzed": rr_below_min_analyzed,
            "rr_entry_eligible_symbols": rr_entry_eligible_symbols,
            "rr_below_min_symbols": rr_below_min_symbols,
            "min_entry_risk_reward": MIN_ENTRY_RISK_REWARD,
            "effective_batch_size": effective_batch_size,
            "deep_analysis_queued": queued_count,
            "deep_analysis_deferred": len(self._deferred_analysis_symbols),
            "universe_coverage_basis": "listed universe; one sequential quick-scan batch per completed cycle, selected names fully analyzed",
            "lane_core_analyzed": lane_core,
            "lane_explosive_analyzed": lane_explosive,
            "core_quality_pass_analyzed": core_quality_pass,
            "qualified_symbols": qualified_symbols,
            "qualified_owned_symbols": qualified_owned_symbols,
            "qualified_new_symbols": qualified_new_symbols,
            "persisted_qualified_symbols": persisted_qualified_symbols,
            "persisted_qualified_owned_symbols": persisted_qualified_owned,
            "persisted_qualified_new_symbols": persisted_qualified_new,
            "core_top_blockers": [
                {"label": label, "count": count}
                for label, count in sorted(core_blocker_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
            ],
            "explosive_top_blockers_cycle": [
                {"label": label, "count": count}
                for label, count in sorted(explosive_blocker_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
            ],
            "paper_entry_event": paper_entry_event,
            "paper_top20_recheck": paper_top20_recheck,
            "paper_optimizer_invalidated": optimizer_policy_event,
            "paper_event_symbols": paper_event_symbols,
            "holding_quotes": holding_quotes,
            "holding_count": len(holding_set),
            "paper_cash": paper_result.get("cash"),
            "paper_executed_orders": paper_result.get("executed_orders") or [],
            "paper_blocked_orders": paper_result.get("blocked_orders") or [],
            "paper_forced_lane_exits": paper_result.get("forced_lane_exits") or [],
        }

    async def loop(self):
        self.running = True
        while True:
            cycle_started = time.monotonic()
            try:
                await asyncio.to_thread(self.scan_once, False)
            except Exception as e:
                self.last_error = f"{type(e).__name__}: {e}"
            # scan_interval_seconds is a start-to-start cadence, not an extra
            # post-scan delay. A ~70s scan with a 120s interval should sleep
            # ~50s, otherwise the wall-clock universe slicer skips 200-name slots.
            elapsed = time.monotonic() - cycle_started
            await asyncio.sleep(max(5, settings.scan_interval_seconds - elapsed))


radar = RadarService()
