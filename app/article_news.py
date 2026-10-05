"""Durable bounded news queue. Scans never download or retain article HTML."""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from sqlalchemy import or_, func, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .article_content import VERSION, fetch_article, assess_document, ArticleUnavailable
from .config import settings
from .db import SessionLocal, NewsArticleAssessment as Article, RadarCandidate, Position, PaperPosition
from .news_scoring import _aliases, _relevance, _time

log = logging.getLogger(__name__)


def utcnow():
    return datetime.now(timezone.utc)


def normalized_url(url):
    try:
        p = urlsplit(str(url or ""))
        if p.scheme != "https" or not p.hostname or p.username or p.password or p.port not in (None, 443):
            return None
        query = [(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith("utm_") and k.lower() not in {"guccounter", "guce_referrer", "guce_referrer_sig"}]
        result = urlunsplit((p.scheme, p.netloc.lower(), p.path, urlencode(query), ""))
        return result if len(result) <= 2048 else None
    except ValueError:
        return None


def article_key(symbol, url):
    return hashlib.sha256(f"{VERSION}|{symbol.upper()}|{url}".encode()).hexdigest()


def attach(news, symbol, company_name, priority=50, now=None):
    """One bounded cache read and durable insert, never a publisher request."""
    now = now or utcnow()
    output = [dict(n) for n in news[:15]]
    if not settings.article_news_enabled:
        return output
    aliases = _aliases(symbol, company_name)
    eligible = {}
    for n in output:
        url = normalized_url(n.get("link"))
        published = _time(n.get("published"))
        relevant, _ = _relevance(n, symbol, aliases)
        if not url or not relevant or (published and (published > now or now-published > timedelta(days=14))):
            n["article_assessment"] = {"status": "unassessed", "reason": "article URL, relevance or publication age is not eligible"}
            continue
        key = article_key(symbol, url)
        eligible[key] = url
        n["article_key"] = key
    if not eligible:
        return output
    with SessionLocal() as db:
        held = db.query(Position.id).filter(Position.symbol == symbol).first() or db.query(PaperPosition.id).filter(PaperPosition.symbol == symbol).first()
        if held:
            priority = 100
        cached = {r.key: r for r in db.query(Article).filter(Article.key.in_(eligible)).all()}
        count = db.query(func.count()).select_from(Article).filter(Article.status.in_(["queued", "processing"])).scalar()
        scheduled = set()
        dialect_insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
        for key, url in eligible.items():
            row = cached.get(key)
            if row:
                due = _time(row.due_at)
                if row.status not in {"queued", "processing"} and due and due <= now and count < settings.article_news_max_pending:
                    row.status = "queued"
                    row.result_json = None
                    row.priority = priority
                    row.requested_at = now
                    count += 1
                continue
            if count >= settings.article_news_max_pending:
                continue
            db.execute(dialect_insert(Article).values(key=key, symbol=symbol.upper(), company_name=str(company_name)[:256],
                url=url, status="queued", priority=priority, attempts=0, requested_at=now, due_at=now)
                .on_conflict_do_nothing(index_elements=["key"]))
            scheduled.add(key)
            count += 1
        db.commit()
        # The first request exposes pending state; completed payloads are small.
        for n in output:
            key = n.pop("article_key", None)
            if not key:
                continue
            row = cached.get(key)
            if row and row.result_json and row.status not in {"queued", "processing"}:
                n["article_assessment"] = json.loads(row.result_json)
            else:
                n["article_assessment"] = {"status": "queued" if row or key in scheduled else "deferred",
                    "reason": "awaiting bounded background assessment"}
    return output


def memory_mb():
    """Whole service memory on small cgroups, process RSS in development."""
    try:
        limit = Path("/sys/fs/cgroup/memory.max").read_text().strip()
        if limit != "max" and int(limit) <= 1024*1024*1024:
            return int(Path("/sys/fs/cgroup/memory.current").read_text()) / (1024*1024)
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1])/1024
    except (OSError, ValueError):
        pass
    return None


def dirty_symbols(limit=20):
    with SessionLocal() as db:
        latest = db.query(Article.symbol.label("symbol"), func.max(Article.checked_at).label("checked")).group_by(Article.symbol).subquery()
        rows = db.query(RadarCandidate.symbol, RadarCandidate.current_json, latest.c.checked).join(latest, latest.c.symbol == RadarCandidate.symbol).yield_per(50)
        dirty = []
        for symbol, payload, checked in rows:
            try:
                asof = _time(json.loads(payload or "{}").get("asof"))
                if asof and _time(checked) and _time(checked) > asof:
                    dirty.append(symbol)
                    if len(dirty) >= limit:
                        break
            except (TypeError, ValueError):
                continue
        return dirty


def is_dirty(symbol, asof):
    date = _time(asof)
    if not date or not settings.article_news_enabled:
        return False
    with SessionLocal() as db:
        return db.query(Article.key).filter(Article.symbol == symbol, Article.checked_at > date).first() is not None


class ArticleWorker:
    def __init__(self):
        self.stop_event = threading.Event()
        self.threads = []
        self.paused = False
        self.completed = 0
        self.last_error = None

    def process_one(self, fetch=fetch_article, now=None):
        now = now or utcnow()
        used = memory_mb()
        threshold = settings.article_news_memory_mb - (50 if self.paused else 0)
        if used is None or used >= threshold:
            self.paused = True
            return False
        self.paused = False
        with SessionLocal() as db:
            available = or_(Article.status == "queued", (Article.status == "processing") & (Article.lease_until < now))
            row = db.query(Article).filter(available, Article.due_at <= now).order_by(Article.priority.desc(), Article.requested_at).with_for_update(skip_locked=True).first()
            if not row:
                return False
            # Conditional update also serializes claims on SQLite (no row locks).
            claimed = db.execute(update(Article).where(Article.key == row.key, available).execution_options(synchronize_session=False).values(
                status="processing", lease_until=now+timedelta(seconds=120), attempts=Article.attempts+1))
            if not claimed.rowcount:
                db.rollback()
                return False
            key, url, symbol, company = row.key, row.url, row.symbol, row.company_name
            db.commit()
        try:
            document = fetch(url)
            result = assess_document(document, symbol=symbol, company_name=company)
            del document
        except ArticleUnavailable as exc:
            result = {"version": VERSION, "status": "unavailable", "sentiment": "unassessed", "reason": str(exc)[:200], "evidence": []}
        except Exception as exc:
            log.exception("Article assessment failed for %s", symbol)
            result = {"version": VERSION, "status": "unavailable", "sentiment": "unassessed", "reason": f"assessment failed ({type(exc).__name__})", "evidence": []}
        checked = utcnow()
        result["checked_at"] = checked.isoformat()
        encoded = json.dumps(result, ensure_ascii=True)
        if len(encoded.encode()) > 4096:
            encoded = json.dumps({"version": VERSION, "status": "unassessed", "reason": "assessment metadata exceeds bound", "evidence": []})
            result["status"] = "unassessed"
        hours = settings.article_news_cache_hours if result["status"] == "assessed" else 6
        with SessionLocal() as db:
            db.execute(update(Article).where(Article.key == key).execution_options(synchronize_session=False).values(status=result["status"], result_json=encoded,
                checked_at=checked, due_at=checked+timedelta(hours=hours), lease_until=None))
            # Retain compact cache for 30 days; active feed inserts refresh request time.
            db.query(Article).filter(Article.requested_at < checked-timedelta(days=30), Article.status.notin_(["queued", "processing"])).delete(synchronize_session=False)
            db.commit()
        self.completed += 1
        return True

    def _loop(self):
        while not self.stop_event.is_set():
            try:
                worked = self.process_one()
            except Exception as exc:
                self.last_error = type(exc).__name__
                log.exception("Article queue unavailable")
                worked = False
            self.stop_event.wait(0.05 if worked else 5)

    def start(self):
        if not settings.article_news_enabled or any(t.is_alive() for t in self.threads):
            return
        self.stop_event.clear()
        self.threads = [threading.Thread(target=self._loop, name=f"article-news-{i}", daemon=True)
                        for i in range(settings.article_news_workers)]
        for thread in self.threads:
            thread.start()

    def stop(self):
        self.stop_event.set()

    def status(self):
        return {"enabled": settings.article_news_enabled, "workers": sum(t.is_alive() for t in self.threads),
                "paused_for_memory": self.paused, "memory_mb": memory_mb(), "completed": self.completed, "last_error": self.last_error}


worker = ArticleWorker()
