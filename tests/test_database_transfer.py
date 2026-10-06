"""Server-side stale-score filtering must not download analysis payloads."""
import json

from sqlalchemy import event

from app.analysis_engine import SCORING_VERSION
from app.db import RadarCandidate, SessionLocal, engine
from app.scanner import RadarService


def test_stale_check_returns_bounded_symbols_without_fetching_large_current_payloads(monkeypatch):
    monkeypatch.setattr("app.scanner.article_news.dirty_symbols", lambda limit: [])
    with SessionLocal() as db:
        for i in range(80):
            db.add(RadarCandidate(symbol=f"CURRENT{i}", portfolio_rank_score=1000-i,
                current_json=json.dumps({"symbol": f"CURRENT{i}",
                    "scoring_version": SCORING_VERSION, "evidence": "x" * 100_000})))
        for i, payload in enumerate(("not-json", "{}", "null",
                json.dumps({"scoring_version": "legacy"}))):
            db.add(RadarCandidate(symbol=f"STALE{i}", portfolio_rank_score=4-i,
                current_json=payload))
        db.commit()
    selects = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT") and "radar_candidates" in statement:
            selects.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        radar = RadarService()
        assert radar.stale_scoring_symbols(limit=2) == ["STALE0", "STALE1"]
        assert radar.stale_scoring_symbols(limit=10) == [f"STALE{i}" for i in range(4)]
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert len(selects) == 2
    for statement in selects:
        projection = statement.split("FROM", 1)[0]
        assert "radar_candidates.symbol" in projection
        assert "current_json" not in projection
        assert "LIMIT" in statement.upper()


def test_current_version_inside_news_text_does_not_hide_an_old_or_absent_version(monkeypatch):
    monkeypatch.setattr("app.scanner.article_news.dirty_symbols", lambda limit: [])
    with SessionLocal() as db:
        for symbol, version in (("OLD", "legacy"), ("CURRENT", SCORING_VERSION)):
            db.add(RadarCandidate(symbol=symbol, current_json=json.dumps({
                "scoring_version": version,
                "news": {"scoring_version": SCORING_VERSION}})))
        db.add(RadarCandidate(symbol="NESTED", current_json=json.dumps({
            "news": {"scoring_version": SCORING_VERSION}})))
        db.commit()
    assert set(RadarService().stale_scoring_symbols()) == {"OLD", "NESTED"}


def test_zero_stale_limit_does_no_database_read():
    assert RadarService().stale_scoring_symbols(limit=0) == []
