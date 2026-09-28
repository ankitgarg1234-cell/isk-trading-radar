from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .config import settings
from .db import SessionLocal, Position, AnalysisRequest, WatchlistItem, AnalysisSnapshot, RadarCandidate, Alert
from .market import YahooMarketProvider
from .analysis_engine import score_bundle, position_action, position_action_plan
from .ai_engine import AIEngine

NY = ZoneInfo("America/New_York")


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

    def market_open(self, now=None):
        """Regular-session V1 gate: Mon-Fri, 09:30-16:00 America/New_York.

        Production feed should replace this with the exchange calendar to account for holidays/early closes.
        """
        now = (now or datetime.now(timezone.utc)).astimezone(NY)
        if now.weekday() >= 5:
            return False
        mins = now.hour * 60 + now.minute
        return 570 <= mins < 960

    def analyze_symbol(self, symbol: str, persist: bool = True):
        symbol = symbol.upper().strip()
        bundle = self.provider.bundle(symbol)
        result = score_bundle(bundle)
        with SessionLocal() as db:
            p = db.query(Position).filter(Position.symbol == symbol).order_by(Position.created_at.desc()).first()
            pd = {"shares": p.shares, "avg_cost": p.avg_cost, "account": p.account} if p else None
            prior = db.query(AnalysisSnapshot).filter(AnalysisSnapshot.symbol == symbol).order_by(AnalysisSnapshot.created_at.desc()).first()
            if prior:
                try:
                    prior_payload=json.loads(prior.payload_json)
                    # Keep only the fields needed for deterioration detection; do
                    # not recursively embed the entire previous snapshot.
                    result["previous_snapshot"]={
                        "breakdown": prior_payload.get("breakdown") or {},
                        "deterministic_score": prior_payload.get("deterministic_score"),
                        "action": prior_payload.get("action"),
                    }
                except Exception:
                    result["previous_snapshot"] = {}
        action, reason = position_action(result, bundle["price"], pd)
        plan = position_action_plan(action, result, bundle["price"], pd)
        ai = self.ai.analyze(symbol, bundle, result)
        full = {**bundle, **result, **ai, "action": action, "action_reason": reason, "action_plan": plan, "position": pd}
        if persist:
            self.persist(full)
        return full

    def persist(self, full: dict):
        symbol = full["symbol"]
        payload = json.dumps(full, default=str)
        with SessionLocal() as db:
            snap = AnalysisSnapshot(
                symbol=symbol,
                price=full.get("price", 0),
                deterministic_score=full.get("deterministic_score", 0),
                analyst_score=full.get("analyst_score") or 0,
                ai_score=full.get("ai_score", 0),
                expected_yield_pct=full.get("expected_yield_pct", 0),
                ai_expected_yield_pct=full.get("ai_expected_yield_pct", 0),
                category=full.get("category", "Watch"),
                action=full.get("action", "WATCH"),
                payload_json=payload,
            )
            db.add(snap)
            cand = db.query(RadarCandidate).filter(RadarCandidate.symbol == symbol).first()
            old_action = cand.action if cand else None
            if not cand:
                cand = RadarCandidate(symbol=symbol)
                db.add(cand)
            cand.category = full.get("category", "Watch")
            cand.action = full.get("action", "WATCH")
            cand.score = full.get("deterministic_score", 0)
            cand.ai_score = full.get("ai_score", 0)
            cand.price = full.get("price", 0)
            cand.updated_at = datetime.now(timezone.utc)

            alert_type = None
            severity = "info"
            title = ""
            if full.get("action") in {"BUY NOW", "BREAKOUT BUY", "ADD"}:
                alert_type, severity, title = "buy_level", "high", f"{symbol}: {full['action']}"
            elif full.get("action") in {"TAKE PARTIAL PROFIT", "REDUCE", "EXIT"}:
                alert_type, severity, title = "position_review", "high", f"{symbol}: {full['action']}"
            elif full.get("action") == "WAIT MORE" and full.get("levels", {}).get("buy_low", 0) <= full.get("price", 0) <= full.get("levels", {}).get("buy_high", 0):
                alert_type, severity, title = "wait_more", "medium", f"{symbol}: Buy level reached — WAIT MORE"
            if alert_type:
                plan = full.get("action_plan") or {}
                qty_text = ""
                if plan.get("suggested_shares"):
                    qty_text = f" Suggested: {plan['suggested_shares']:g} shares ({plan.get('actual_percent', 0):.1f}% of position)."
                message=(full.get("action_reason", "") + qty_text).strip()
                # One active alert per ticker + condition. Repeated scans refresh the
                # existing alert instead of growing the list with duplicates.
                active = db.query(Alert).filter(
                    Alert.symbol == symbol, Alert.alert_type == alert_type,
                    Alert.action == full.get("action", "REVIEW"), Alert.acknowledged == False,
                ).order_by(Alert.created_at.desc()).first()
                if active:
                    active.severity=severity; active.title=title; active.message=message
                    active.created_at=datetime.now(timezone.utc); active.snoozed_until=None
                elif old_action != full.get("action"):
                    # Supersede stale active conditions for the same symbol while
                    # preserving them as acknowledged history.
                    for stale in db.query(Alert).filter(Alert.symbol==symbol, Alert.acknowledged==False).all():
                        stale.acknowledged=True
                    db.add(Alert(
                        symbol=symbol, alert_type=alert_type, severity=severity, title=title,
                        message=message, action=full.get("action", "REVIEW"),
                    ))
            db.commit()

    def priority_symbols(self) -> list[str]:
        """Symbols that deserve full analysis every cycle before broad-market candidates."""
        with SessionLocal() as db:
            positions = [p.symbol for p in db.query(Position).all()]
            watch = [w.symbol for w in db.query(WatchlistItem).all()]
            manual = [a.symbol for a in db.query(AnalysisRequest).order_by(AnalysisRequest.created_at.desc()).limit(20).all()]
        ordered = positions + manual + watch + list(settings.radar_symbols)
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

    def scan_once(self, force: bool = False):
        if not force and not self.market_open():
            return {"status": "market_closed", "analyzed": 0, "universe_size": self.universe_size}
        syms = self.candidate_symbols()
        batch = syms[: settings.scan_batch_size]
        ok = 0
        errors: list[str] = []
        for sym in batch:
            try:
                self.analyze_symbol(sym)
                ok += 1
            except Exception as e:
                errors.append(f"{sym}: {type(e).__name__}")
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
