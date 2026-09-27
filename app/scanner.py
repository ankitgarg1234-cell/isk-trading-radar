from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .config import settings
from .db import SessionLocal, Position, AnalysisRequest, WatchlistItem, AnalysisSnapshot, RadarCandidate, Alert
from .market import YahooMarketProvider
from .analysis_engine import score_bundle, position_action
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
        action, reason = position_action(result, bundle["price"], pd)
        ai = self.ai.analyze(symbol, bundle, result)
        full = {**bundle, **result, **ai, "action": action, "action_reason": reason, "position": pd}
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
            if alert_type and old_action != full.get("action"):
                db.add(Alert(
                    symbol=symbol, alert_type=alert_type, severity=severity, title=title,
                    message=full.get("action_reason", ""), action=full.get("action", "REVIEW"),
                ))
            db.commit()

    def candidate_symbols(self):
        """Prioritize current holdings/watchlist, then continuously add cross-sector discovered names."""
        with SessionLocal() as db:
            positions = [p.symbol for p in db.query(Position).all()]
            watch = [w.symbol for w in db.query(WatchlistItem).all()]
            manual = [a.symbol for a in db.query(AnalysisRequest).order_by(AnalysisRequest.created_at.desc()).limit(30).all()]
        discovered = self.provider.discover(60)
        ranked = [
            d["symbol"]
            for d in sorted(discovered, key=lambda x: abs(float(x.get("change_pct") or 0)), reverse=True)
        ]
        ordered = positions + watch + manual + list(settings.radar_symbols) + ranked
        return list(dict.fromkeys(s.upper() for s in ordered if s))

    def scan_once(self, force: bool = False):
        if not force and not self.market_open():
            return {"status": "market_closed", "analyzed": 0}
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
        self.last_error = "; ".join(errors[:5]) if errors else None
        return {"status": "ok", "analyzed": ok, "errors": errors, "candidates": len(syms)}

    async def loop(self):
        self.running = True
        while True:
            try:
                await asyncio.to_thread(self.scan_once, False)
            except Exception as e:
                self.last_error = f"{type(e).__name__}: {e}"
            await asyncio.sleep(max(30, settings.scan_interval_seconds))


radar = RadarService()
