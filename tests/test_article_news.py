import gzip
import json
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import httpx
import pytest

from app import article_news as queue
from app.article_content import ArticleUnavailable, decode_article, assess_document, fetch_article, public_url
from app.analysis_engine import news_analysis, score_bundle, thesis_assessment
from app.db import SessionLocal, NewsArticleAssessment as Article, RadarCandidate
from .helpers import bundle

FILLER = "The report compares the companies and discusses growth, valuation and customer concentration. " * 4


def document(sentence, selector="article-body"):
    html = f'<html><title>Research</title><div class="{selector}"><p>{FILLER}</p><p>{sentence}</p></div></html>'.encode()
    doc = decode_article(html[i:i+8192] for i in range(0, len(html), 8192))
    doc["source_url"] = "https://example.com/research"
    return doc


def assess(sentence, symbol="CRDO", company="Credo Technology Group Holding Ltd"):
    return assess_document(document(sentence), symbol=symbol, company_name=company)


def raw(symbol="CRDO", company="Credo", **extra):
    return {"title": f"{company} vs another company: which is the better buy?", "relatedTickers": [symbol],
            "publisher": "Example Research", "published": queue.utcnow().timestamp()-60,
            "link": "https://example.com/research", **extra}


@pytest.mark.parametrize("symbol,company", [("CRDO", "Credo"), ("WDC", "Western Digital"), ("NVDA", "Nvidia"), ("MSFT", "Microsoft"), ("AAPL", "Apple"), ("TSM", "Taiwan Semiconductor")])
@pytest.mark.parametrize("verb,expected", [("I'd go with", "positive"), ("I prefer", "positive"), ("Our pick is", "positive"), ("I would not buy", "negative"), ("I avoid", "negative")])
def test_author_stance_is_company_specific_not_ticker_hardcoded(symbol, company, verb, expected):
    result = assess(f"{verb} {company}.", symbol, company)
    assert result["status"] == "assessed" and result["sentiment"] == expected
    assert result["article_type"] == "opinion" and result["fresh_catalysts"] == []
    assert sum(len(e["text"].split()) for e in result["evidence"]) <= 20


@pytest.mark.parametrize("sentence", [
    "I'd buy Arm rather than Credo.", "I recommend buying Arm and avoiding Credo.",
    "I recommend either Arm or Credo.", "Would I buy Credo?", "If earnings improve, I'd buy Credo.",
    "I would buy Credo if its price fell.", 'The analyst said "I prefer Credo."',
    "Last year I chose Credo.", "Credo has impressive growth but also concentration risk.",
    "I would not recommend Credo.", "I recommend not buying Credo.", "I prefer buying Arm over Credo.",
    "I prefer the price of Credo.", "I buy the hardware used by Credo.",
])
def test_ambiguous_competitor_question_attribution_or_conditional_not_bullish(sentence):
    assert assess(sentence)["status"] == "unassessed"


def test_mixed_author_stance_and_truncation_are_conservative():
    result = assess("I prefer Credo. I avoid Credo.")
    assert result["sentiment"] == "mixed"
    assert assess_document({"text": FILLER+"I buy Credo.", "truncated": True}, symbol="CRDO", company_name="Credo")["status"] == "unassessed"


@pytest.mark.parametrize("selector", ["article-body", "caas-body", "articleBody", "story-content"])
def test_body_selection_ignores_author_bio_and_trailing_ad_payload(selector):
    body = f'<html><article>Author biography: I prefer Credo.</article><div class="{selector}"><script>I avoid Credo.</script><p>{FILLER}</p><p>I prefer Credo.</p></div>'.encode()
    chunks = [body] + [b"advertising"*1000]*200
    doc = decode_article(chunks)
    assert doc["decoded_bytes"] < 10000
    assert "Author biography" not in doc["text"] and "I avoid Credo" not in doc["text"]
    assert assess_document(doc, symbol="CRDO", company_name="Credo")["sentiment"] == "positive"


def test_limits_compression_incomplete_body_and_markup_depth():
    bomb = gzip.compress(b"x"*(32*1024*1024))
    with pytest.raises(ArticleUnavailable, match="decoded limit"):
        decode_article([bomb], encoding="gzip")
    with pytest.raises(ArticleUnavailable):
        decode_article([b'<div class="article-body">'+FILLER.encode()])
    with pytest.raises(ArticleUnavailable, match="nesting"):
        decode_article([b"<div>"*300])
    with pytest.raises(ArticleUnavailable, match="deadline"):
        decode_article([b"<html>"], deadline=1)
    with pytest.raises(ArticleUnavailable, match="wire limit"):
        decode_article([b"x"*(1024*1024+1)])


def test_fetch_streams_complete_body_and_closes_response():
    html = ('<div class="caas-body">'+FILLER+"I prefer Credo.</div>").encode()
    transport = httpx.MockTransport(lambda r: httpx.Response(200, headers={"content-type": "text/html"}, stream=httpx.ByteStream(html)))
    with httpx.Client(transport=transport) as client:
        doc = fetch_article("https://example.com/research", client=client, validate=lambda u: u)
    assert doc["source_url"] == "https://example.com/research"


def test_fetch_rejects_redirect_private_address_and_non_html(monkeypatch):
    monkeypatch.setattr("app.article_content.socket.getaddrinfo", lambda *a, **kw: [(2, 1, 6, "", ("127.0.0.1", 443))])
    with pytest.raises(ArticleUnavailable, match="non-public"):
        public_url("https://example.com")
    for url in ["http://example.com", "https://me:password@example.com", "https://example.com:22"]:
        with pytest.raises(ArticleUnavailable):
            public_url(url)
    transport = httpx.MockTransport(lambda r: httpx.Response(302, headers={"location": "https://127.0.0.1/private"}))
    with httpx.Client(transport=transport) as client, pytest.raises(ArticleUnavailable):
        fetch_article("https://example.com", client=client, validate=lambda u: public_url(u) if "127.0.0.1" in u else u)
    transport = httpx.MockTransport(lambda r: httpx.Response(200, headers={"content-type": "application/pdf"}, stream=httpx.ByteStream(b"PDF")))
    with httpx.Client(transport=transport) as client, pytest.raises(ArticleUnavailable, match="HTML"):
        fetch_article("https://example.com", client=client, validate=lambda u: u)


def test_opinion_points_are_deduped_without_catalysts_or_thesis_sell():
    article = raw(article_assessment=assess("I'd go with Credo Technology."))
    n = news_analysis([article, {**article, "publisher": "Duplicate publisher"}], symbol="CRDO", company_name="Credo", asof=queue.utcnow().isoformat())
    assert n["score"] == 9.0 and n["duplicate_count"] == 1
    assert n["material_events"] == 0 and n["catalysts"] == []
    assert n["items"][0]["article_sentiment"] == "positive" and n["body_assessed_count"] == 1
    negative = news_analysis([raw(article_assessment=assess("I avoid Credo because bankruptcy remains a risk."))], symbol="CRDO", company_name="Credo", asof=queue.utcnow().isoformat())
    assert negative["score"] == 6.0 and not thesis_assessment({"news": negative})["invalidated"]
    assert negative["high_negative_events"] == 0


def test_queued_or_unassessed_body_does_not_change_frozen_headline_points():
    a = raw(title="Credo raises guidance", publisher="Reuters")
    before = news_analysis([a], symbol="CRDO", company_name="Credo", asof=queue.utcnow().isoformat())
    for status in ["queued", "unassessed", "unavailable"]:
        after = news_analysis([{**a, "article_assessment": {"status": status}}], symbol="CRDO", company_name="Credo", asof=queue.utcnow().isoformat())
        assert before["score"] == after["score"] and before["catalysts"] == after["catalysts"]


def test_cache_queue_retry_and_symbol_scope(monkeypatch):
    monkeypatch.setattr(queue, "memory_mb", lambda: 100)
    now = queue.utcnow()
    pending = queue.attach([raw(), raw(link="https://example.com/research?utm_source=x")], "CRDO", "Credo", now=now)
    assert all(n["article_assessment"]["status"] == "queued" for n in pending)
    with SessionLocal() as db:
        assert db.query(Article).count() == 1
    worker = queue.ArticleWorker()
    assert worker.process_one(fetch=lambda u: document("I prefer Credo."), now=now)
    cached = queue.attach([raw()], "CRDO", "Credo", now=now+timedelta(minutes=1))
    assert cached[0]["article_assessment"]["sentiment"] == "positive"
    other = queue.attach([raw(symbol="ARM", company="Arm")], "ARM", "Arm", now=now)
    assert other[0]["article_assessment"]["status"] == "queued"
    refreshed = queue.attach([raw(published=now.timestamp())], "CRDO", "Credo", now=now+timedelta(hours=25))
    assert refreshed[0]["article_assessment"]["status"] == "queued"
    assert worker.process_one(fetch=lambda u: (_ for _ in ()).throw(ArticleUnavailable("publisher returned HTTP 429")), now=now+timedelta(hours=25))
    with SessionLocal() as db:
        failed = db.query(Article).filter(Article.status == "unavailable").first()
        assert failed and len(failed.result_json.encode()) < 4096


def test_queue_cap_and_memory_hysteresis(monkeypatch):
    monkeypatch.setattr(queue, "settings", replace(queue.settings, article_news_max_pending=1))
    items = queue.attach([raw(), raw(link="https://example.com/other")], "CRDO", "Credo")
    assert [n["article_assessment"]["status"] for n in items] == ["queued", "deferred"]
    worker = queue.ArticleWorker()
    monkeypatch.setattr(queue, "memory_mb", lambda: 351)
    assert not worker.process_one() and worker.paused
    monkeypatch.setattr(queue, "memory_mb", lambda: 320)
    assert not worker.process_one() and worker.paused
    monkeypatch.setattr(queue, "memory_mb", lambda: 290)
    assert worker.process_one(fetch=lambda u: document("I prefer Credo.")) and not worker.paused


def test_expired_lease_recovers_and_completed_articles_invalidate_canonical_cache(monkeypatch):
    now = queue.utcnow()
    queue.attach([raw()], "CRDO", "Credo", now=now)
    with SessionLocal() as db:
        row = db.query(Article).first()
        row.status = "processing"
        row.lease_until = now-timedelta(seconds=1)
        # Candidate write can occur after the worker completes; use analysis asof.
        db.add(RadarCandidate(symbol="CRDO", current_json=json.dumps({"asof": now.isoformat()}), updated_at=now+timedelta(minutes=2)))
        db.commit()
    monkeypatch.setattr(queue, "memory_mb", lambda: 100)
    assert queue.ArticleWorker().process_one(fetch=lambda u: document("I prefer Credo."), now=now)
    assert queue.is_dirty("CRDO", now.isoformat()) and queue.dirty_symbols() == ["CRDO"]


def test_canonical_bundle_adds_opinion_once_and_retains_other_scores():
    a = raw(symbol="TEST", company="Example Research", article_assessment=assess("I prefer TEST.", "TEST", "Example Research"))
    b = bundle(news=[a]); b["fundamentals"]["companyName"] = "Example Research"
    scored = score_bundle(b)
    without = score_bundle({**b, "news": [{k:v for k,v in a.items() if k != "article_assessment"}]})
    assert scored["deterministic_score"] == without["deterministic_score"]+1.5
    assert scored["breakdown"]["Fundamentals"] == without["breakdown"]["Fundamentals"]
    assert scored["news"]["catalysts"] == without["news"]["catalysts"]
