from __future__ import annotations

import asyncio
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .config import settings
from .db import SessionLocal, Position, AnalysisRequest, WatchlistItem, AnalysisSnapshot, RadarCandidate, Alert, PortfolioPreference, PaperPosition
from .market import YahooMarketProvider
from .analysis_engine import score_bundle, position_action, position_action_plan
from .portfolio_engine import candidate_rank_score, build_optimizer_plan, normalise_profile, INVESTABLE_ENTRY_ACTIONS
from .paper_engine import run_paper_cycle
from .ai_engine import AIEngine

NY = ZoneInfo("America/New_York")



def _attention_buy_signal(full: dict, has_position: bool = False) -> tuple[str | None, str | None]:
    """Return the attention-queue buy signal for an active primary/better-buy zone.

    The attention queue is intentionally stricter than the general Radar. Price
    reaching an entry band is not itself actionable. Only the agreed deterministic
    conviction ladder is surfaced:
      85-100 -> STRONG BUY
      75-84  -> BUY
      68-74 in BETTER_BUY -> STARTER BUY
      68-74 in PRIMARY_BUY -> CONSIDER BUY
    Monitoring states below 68 stay in the Radar and never become attention alerts.
    Material bearish/thesis-invalidated setups are blocked from buy attention.
    """
    if bool((full.get("thesis_assessment") or {}).get("invalidated")):
        return None, None
    if full.get("negative_news_override"):
        return None, None
    if str(full.get("decision_confidence") or "medium").lower() == "low":
        return None, None
    zone = str(full.get("entry_zone_status") or "").upper()
    if not zone:
        price=float(full.get("price") or 0)
        levels=full.get("levels") or {}
        better_low=float(levels.get("better_low") or 0); better_high=float(levels.get("better_high") or 0)
        buy_low=float(levels.get("buy_low") or 0); buy_high=float(levels.get("buy_high") or 0)
        if better_low and better_low <= price <= better_high:
            zone="BETTER_BUY"
        elif buy_low and buy_low <= price <= buy_high:
            zone="PRIMARY_BUY"
    if zone not in {"PRIMARY_BUY", "BETTER_BUY"}:
        return None, None
    score = float(full.get("deterministic_score") or 0)
    if score >= 85:
        return "STRONG BUY", f"{zone.replace('_', ' ').title()} reached with deterministic conviction {score:.0f}/100"
    if score >= 75:
        return "BUY", f"{zone.replace('_', ' ').title()} reached with deterministic conviction {score:.0f}/100"
    if score >= 68 and zone == "BETTER_BUY":
        return "STARTER BUY", f"Better Buy reached with deterministic conviction {score:.0f}/100"
    if score >= 68 and zone == "PRIMARY_BUY":
        return "CONSIDER BUY", f"Primary Buy reached with deterministic conviction {score:.0f}/100"
    return None, None


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
            news["items"] = items[:5]
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
        self.scan_count = 0
        self.universe_size = 0
        self.last_universe_prefiltered = 0
        self.last_universe_candidates = 0
        self.last_deep_analyzed = 0
        self.last_universe_start = 0
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

    def market_open(self, now=None):
        """Regular-session V1 gate: Mon-Fri, 09:30-16:00 America/New_York.

        Production feed should replace this with the exchange calendar to account for holidays/early closes.
        """
        now = (now or datetime.now(timezone.utc)).astimezone(NY)
        if now.weekday() >= 5:
            return False
        mins = now.hour * 60 + now.minute
        return 570 <= mins < 960

    def analyze_symbol(self, symbol: str, persist: bool = True, strategic_refresh: bool = False):
        symbol = symbol.upper().strip()
        bundle = self.provider.bundle(symbol)
        result = score_bundle(bundle)
        prior_payload = {}
        with SessionLocal() as db:
            p = db.query(Position).filter(Position.symbol == symbol).order_by(Position.created_at.desc()).first()
            pd = {"shares": p.shares, "avg_cost": p.avg_cost, "account": p.account} if p else None
            prior = db.query(RadarCandidate).filter(RadarCandidate.symbol == symbol).first()
            if prior and prior.current_json:
                try:
                    prior_payload=json.loads(prior.current_json)
                    result["previous_snapshot"]={
                        "breakdown": prior_payload.get("breakdown") or {},
                        "deterministic_score": prior_payload.get("deterministic_score"),
                        "action": prior_payload.get("action"),
                    }
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
        ai = self.ai.analyze(symbol, bundle, result)
        full = {**bundle, **result, **ai, "action": action, "action_reason": reason, "action_plan": plan, "position": pd}
        if persist:
            self.persist(full)
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
            cand.rank_version = rank.get("version", "rank-v1")
            cand.current_json = compact_json
            cand.updated_at = now

            # Historical snapshots are compact and throttled. Priority names
            # (holdings/watchlist/manual requests) get an hourly checkpoint; broad
            # market candidates get a six-hour checkpoint unless something material
            # changes first.
            is_priority = bool(
                db.query(Position.id).filter(Position.symbol == symbol).first()
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
        silently changing the validated rank-v1 portfolio rules.
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

    def _sync_rotation_alerts(self):
        """Gate live attention only after the optimizer has passed validation."""
        if not settings.optimizer_live_gating:
            return
        with SessionLocal() as db:
            position_rows = db.query(Position).all()
            owned = {p.symbol for p in position_rows}
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
            approved = {r["symbol"]: r for r in plan["selected_new"]}
            now = datetime.now(timezone.utc)

            # Price reaching a buy zone is no longer enough to interrupt the user.
            # Only the 5-7-position optimizer can approve an entry alert.
            for alert in db.query(Alert).filter(Alert.alert_type == "buy_level", Alert.acknowledged == False).all():
                if alert.symbol not in approved:
                    alert.acknowledged = True
            for sym, r in approved.items():
                action = r.get("entry_signal") or "BUY"
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

    def priority_symbols(self) -> list[str]:
        """Symbols that deserve full analysis every cycle before broad-market candidates."""
        with SessionLocal() as db:
            positions = [p.symbol for p in db.query(Position).all()]
            paper_positions = [p.symbol for p in db.query(PaperPosition).all()]
            watch = [w.symbol for w in db.query(WatchlistItem).all()]
            manual = [a.symbol for a in db.query(AnalysisRequest).order_by(AnalysisRequest.created_at.desc()).limit(20).all()]
        # Paper holdings are priority symbols too, so thesis/exit management is
        # refreshed every scanner cycle without querying historical payloads.
        ordered = positions + paper_positions + manual + watch + list(settings.radar_symbols)
        return list(dict.fromkeys(s.upper() for s in ordered if s))

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
        start = int((slot * batch_size) % len(universe))
        self.last_universe_start = start
        if start + batch_size <= len(universe):
            return universe[start:start + batch_size]
        return universe[start:] + universe[:(start + batch_size) % len(universe)]

    def _prefilter_universe(self, entries: list[dict]) -> list[dict]:
        if not entries:
            self.last_universe_prefiltered = 0
            self.last_universe_candidates = 0
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
        qualified = [r for r in results if r.get("qualifies")]
        qualified.sort(key=lambda r: float(r.get("scan_score") or 0), reverse=True)
        # Always retain a few highest-ranked names even if hard thresholds are narrowly missed.
        if len(qualified) < settings.universe_deep_candidates:
            seen = {r["symbol"] for r in qualified}
            for r in sorted(results, key=lambda x: float(x.get("scan_score") or 0), reverse=True):
                if r["symbol"] not in seen:
                    qualified.append(r); seen.add(r["symbol"])
                if len(qualified) >= settings.universe_deep_candidates:
                    break
        self.last_universe_candidates = min(len(qualified), settings.universe_deep_candidates)
        return qualified[: settings.universe_deep_candidates]

    def candidate_symbols(self):
        """Return the current deep-analysis queue, including a rotating whole-market slice."""
        priority = self.priority_symbols()[: settings.priority_deep_limit]
        discovered = self.provider.discover(100)
        discovered.sort(key=lambda x: abs(float(x.get("change_pct") or 0)), reverse=True)
        discovery_symbols = [d["symbol"] for d in discovered[: settings.discovery_deep_candidates]]
        broad = self._prefilter_universe(self._universe_slice())
        broad_symbols = [q["symbol"] for q in broad]
        ordered = priority + discovery_symbols + broad_symbols
        return list(dict.fromkeys(s.upper() for s in ordered if s))

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
            "policy_version": "eligibility-v2-no-sector-no-tier",
            "risk_profile": profile,
            "visible_limit": settings.optimizer_visible_limit,
            "shortlist_limit": settings.optimizer_shortlist_limit,
            "target_positions": settings.optimizer_target_positions,
            "max_positions": settings.optimizer_max_positions,
            "min_rank_score": settings.optimizer_min_rank_score,
            "rotation_gap": settings.optimizer_rotation_gap,
            "rotation_yield_gap": settings.optimizer_rotation_yield_gap,
            "paper_trade_cost_bps": settings.paper_trade_cost_bps,
            "investable_entry_actions": sorted(INVESTABLE_ENTRY_ACTIONS),
            # Explicitly encode the current policy: these legacy constraints are gone.
            "sector_position_cap": None,
            "per_tier_max_positions": None,
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
        if not force and not self.market_open():
            # Official-source evidence is not market-data dependent. Keep the
            # Top-20 strategic-capital queue moving even while U.S. equities are
            # closed so users do not have to open every stock and click Refresh.
            errors: list[str] = []
            strategic_changed = False
            strategic_symbols: list[str] = []
            try:
                strategic_changed, strategic_symbols = self._enrich_strategic_top_candidates()
            except Exception as e:
                errors.append(f"strategic capital: {type(e).__name__}")
            self.last_scan = datetime.now(timezone.utc)
            self.scan_count += 1
            self.last_deep_analyzed = 0
            self.last_error = "; ".join(errors[:5]) if errors else None
            return {
                "status": "market_closed", "analyzed": 0, "universe_size": self.universe_size,
                "strategic_enriched": strategic_symbols, "strategic_changed": strategic_changed,
                "errors": errors,
            }
        syms = self.candidate_symbols()
        batch = syms[: settings.scan_batch_size]
        ok = 0
        errors: list[str] = []
        # Portfolio-rule/config changes are first-class optimizer events. This is
        # what makes an already-actionable BUY such as GWRE get reconsidered after
        # a blocking restriction is removed; no BUY -> BUY transition is required.
        optimizer_policy_event = self._paper_optimizer_invalidation_event()
        paper_entry_event = optimizer_policy_event
        paper_event_symbols: list[str] = []
        for sym in batch:
            try:
                full = self.analyze_symbol(sym)
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
                # in the forward-test decision record. rank-v1 itself is unchanged.
                paper_entry_event = True
                paper_event_symbols.extend(s for s in strategic_symbols if s not in paper_event_symbols)
        except Exception as e:
            errors.append(f"strategic capital: {type(e).__name__}")
        try:
            self._sync_rotation_alerts()
        except Exception as e:
            errors.append(f"portfolio optimizer: {type(e).__name__}")
        try:
            # Entry decisions are event-driven. A run is triggered by either a
            # material ticker event OR a portfolio-eligibility/config invalidation.
            # The paper engine then reloads and re-ranks the complete current Top 20,
            # so a BUY does not need to leave BUY and become BUY again to be seen.
            # Broader portfolio rotation remains on the daily cadence.
            run_paper_cycle(self.provider, entry_event=paper_entry_event)
        except Exception as e:
            errors.append(f"paper trading: {type(e).__name__}")
        self.last_scan = datetime.now(timezone.utc)
        self.scan_count += 1
        self.last_deep_analyzed = ok
        self.last_error = "; ".join(errors[:5]) if errors else None
        return {
            "status": "ok", "analyzed": ok, "errors": errors, "candidates": len(syms),
            "universe_size": self.universe_size,
            "universe_prefiltered": self.last_universe_prefiltered,
            "universe_deep_candidates": self.last_universe_candidates,
            "universe_start": self.last_universe_start,
            "paper_entry_event": paper_entry_event,
            "paper_optimizer_invalidated": optimizer_policy_event,
            "paper_event_symbols": paper_event_symbols,
        }

    async def loop(self):
        self.running = True
        while True:
            try:
                await asyncio.to_thread(self.scan_once, False)
            except Exception as e:
                self.last_error = f"{type(e).__name__}: {e}"
            await asyncio.sleep(max(30, settings.scan_interval_seconds))


radar = RadarService()
