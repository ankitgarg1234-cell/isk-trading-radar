"""Bounded public article retrieval and auditable company-specific author stance.

No browser, local language model or blanket sentiment keyword count. Ambiguous
body text stays unassessed. Author opinions never manufacture factual catalysts.
"""
from __future__ import annotations

import codecs
import hashlib
import ipaddress
import re
import socket
import time
import zlib
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx

VERSION = "article-stance-v1"
MAX_BYTES = 1024 * 1024
MAX_TEXT = 30000
CHUNK = 8192
DEADLINE_SECONDS = 25


class ArticleUnavailable(Exception):
    pass


def public_url(url):
    p = urlsplit(url)
    if p.scheme != "https" or not p.hostname or p.username or p.password or p.port not in (None, 443):
        raise ArticleUnavailable("unsupported or unsafe article URL")
    try:
        addresses = socket.getaddrinfo(p.hostname, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ArticleUnavailable("publisher DNS unavailable") from exc
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ArticleUnavailable("non-public publisher address")
    return url


class ArticleParser(HTMLParser):
    BODY_NAMES = {"article-body", "article-content", "caas-body", "article__body",
                  "articleBody", "story-body", "story-content", "article-text"}
    VOID = {"br", "img", "meta", "link", "hr", "input", "source", "wbr", "area", "base", "embed"}
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.stack = []
        self.root_depth = None
        self.generic_depth = None
        self.explicit_parts = []
        self.generic_parts = []
        self.explicit_chars = 0
        self.generic_chars = 0
        self.ignored = 0
        self.complete = False
        self.explicit_seen = False
        self.generic_complete = False
        self.truncated = False
        self.links = []
        self.title_parts = []
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag not in self.VOID:
            if len(self.stack) >= 256:
                raise ArticleUnavailable("article markup nesting exceeds bound")
            self.stack.append(tag)
            self.depth += 1
        if tag == "title":
            self.in_title = True
        if tag in {"script", "style", "noscript", "nav", "aside"}:
            self.ignored += 1
        names = set((a.get("class") or "").split()) | {a.get("id"), a.get("data-testid"), a.get("itemprop")}
        if self.root_depth is None and not self.complete and not self.ignored and names & self.BODY_NAMES:
            self.explicit_seen = True
            self.root_depth = self.depth
            self.explicit_parts = []
            self.explicit_chars = 0
        if tag == "article" and self.generic_depth is None and not self.generic_complete:
            self.generic_depth = self.depth
        if tag in {"p", "h1", "h2", "h3", "li", "br"}:
            self._append("\n")
        href = a.get("href") or a.get("content") if tag in {"a", "link", "meta"} else None
        if href and str(href).startswith("https://") and len(self.links) < 32:
            self.links.append(str(href)[:2048])

    def handle_endtag(self, tag):
        if tag in self.VOID or tag not in self.stack:
            return
        closing_depth = len(self.stack) - self.stack[::-1].index(tag)
        if tag == "title":
            self.in_title = False
        if tag in {"p", "h1", "h2", "h3", "li"}:
            self._append("\n")
        if self.root_depth is not None and closing_depth == self.root_depth:
            self.complete = True
            self.root_depth = None
        if self.generic_depth is not None and closing_depth <= self.generic_depth:
            self.generic_complete = True
            self.generic_depth = None
        if tag in {"script", "style", "noscript", "nav", "aside"}:
            self.ignored = max(0, self.ignored - 1)
        del self.stack[closing_depth-1:]
        self.depth = len(self.stack)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def _append(self, text):
        if self.ignored:
            return
        if self.root_depth is not None:
            room = MAX_TEXT - self.explicit_chars
            if len(text) > room:
                self.truncated = True
            if room > 0:
                part = text[:room]
                self.explicit_parts.append(part)
                self.explicit_chars += len(part)
        if self.generic_depth is not None:
            room = MAX_TEXT - self.generic_chars
            if room > 0:
                part = text[:room]
                self.generic_parts.append(part)
                self.generic_chars += len(part)

    def handle_data(self, text):
        if self.in_title and sum(map(len, self.title_parts)) < 512:
            self.title_parts.append(text[:512])
        self._append(text)

    def document(self):
        if self.complete:
            return "".join(self.explicit_parts).strip(), self.truncated, "article body"
        if self.explicit_seen:
            return "", False, "incomplete article body"
        if self.generic_complete:
            return "".join(self.generic_parts).strip(), self.generic_chars >= MAX_TEXT, "article element"
        return "", False, "no complete article body"


def decode_article(chunks, encoding="identity", deadline=None):
    if encoding not in {"identity", "gzip"}:
        raise ArticleUnavailable("unsupported content encoding")
    parser = ArticleParser()
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    inflater = zlib.decompressobj(16 + zlib.MAX_WBITS) if encoding == "gzip" else None
    wire = decoded = 0
    try:
        for raw in chunks:
            if deadline and time.monotonic() > deadline:
                raise ArticleUnavailable("article deadline exceeded")
            wire += len(raw)
            if wire > MAX_BYTES:
                raise ArticleUnavailable("article exceeds 1 MiB wire limit")
            pending = raw
            while pending:
                block = inflater.decompress(pending, min(CHUNK, MAX_BYTES - decoded + 1)) if inflater else pending
                pending = inflater.unconsumed_tail if inflater else b""
                decoded += len(block)
                if decoded > MAX_BYTES:
                    raise ArticleUnavailable("article exceeds 1 MiB decoded limit")
                parser.feed(decoder.decode(block))
                if parser.complete:
                    text, truncated, method = parser.document()
                    return {"text": text, "truncated": truncated, "method": method,
                            "wire_bytes": wire, "decoded_bytes": decoded, "links": parser.links}
        if inflater and not inflater.eof:
            raise ArticleUnavailable("incomplete compressed article")
        parser.feed(decoder.decode(b"", final=True))
        parser.close()
        text, truncated, method = parser.document()
        if len(text) < 200:
            raise ArticleUnavailable("complete article body unavailable")
        return {"text": text, "truncated": truncated, "method": method,
                "wire_bytes": wire, "decoded_bytes": decoded, "links": parser.links}
    except (zlib.error, ValueError) as exc:
        raise ArticleUnavailable("invalid article encoding") from exc


def fetch_article(url, *, client=None, validate=public_url):
    owned = client is None
    client = client or httpx.Client(timeout=httpx.Timeout(5, connect=4),
                                   headers={"Accept-Encoding": "identity", "User-Agent": "ISK Trading Radar article research/1.0"},
                                   follow_redirects=False, limits=httpx.Limits(max_connections=2, max_keepalive_connections=2))
    deadline = time.monotonic() + DEADLINE_SECONDS
    original = url
    try:
        for _ in range(4):
            validate(url)
            if time.monotonic() >= deadline:
                raise ArticleUnavailable("article deadline exceeded")
            with client.stream("GET", url) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise ArticleUnavailable("publisher redirect has no destination")
                    url = urljoin(url, location)
                    continue
                if response.status_code != 200:
                    raise ArticleUnavailable(f"publisher returned HTTP {response.status_code}")
                content_type = response.headers.get("content-type", "").lower()
                if not any(t in content_type for t in ("text/html", "application/xhtml")):
                    raise ArticleUnavailable("publisher did not return HTML")
                doc = decode_article(response.iter_raw(chunk_size=CHUNK),
                                     response.headers.get("content-encoding", "identity"), deadline)
                doc["source_url"] = url
                doc["requested_url"] = original
                return doc
        raise ArticleUnavailable("publisher redirect limit exceeded")
    except httpx.HTTPError as exc:
        raise ArticleUnavailable(f"publisher request failed ({type(exc).__name__})") from exc
    finally:
        if owned:
            client.close()


CHOICE = re.compile(r"\b(?:i|we)(?:'d| would| will)?\s+(?:go with|choose|pick|prefer|buy|recommend)\b", re.I)
AVOID = re.compile(r"\b(?:i|we)(?: would| do| will)?\s+(?:not buy|wouldn't buy|avoid|sell|steer clear of)\b", re.I)
PREFERENCE = re.compile(r"\b(?:my|our)\s+(?:pick|choice|preference|favorite)\s+(?:is|remains)\b", re.I)
COMPARISON = re.compile(r"\b(?:rather than|instead of|over|versus|vs\.?|not|and|or|but|while)\b", re.I)
CONDITIONAL = re.compile(r"\b(?:if|unless|might|could|rumou?r|hypothetically|used to|last year)\b", re.I)
ATTRIBUTION = re.compile(r"\b(?:said|says|quoted|according to|asked|told|wrote)\b", re.I)


def assess_document(document, *, symbol, company_name):
    from .news_scoring import _aliases
    text = str(document.get("text") or "").replace("\u2019", "'")
    base = {"version": VERSION, "status": "unassessed", "sentiment": "unassessed",
            "article_type": "context", "method": "explicit company-specific author-stance rules",
            "source_url": document.get("source_url"), "content_hash": hashlib.sha256(text.encode()).hexdigest(),
            "text_chars": len(text), "evidence": [], "fresh_catalysts": [], "confidence": "limited"}
    if document.get("truncated") or len(text) < 200:
        return {**base, "reason": "incomplete or truncated body; no author stance inferred"}
    aliases = _aliases(symbol, company_name)
    if not any(p.search(text) for p in aliases):
        return {**base, "reason": "article body does not establish company relevance"}
    signals = []
    sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence or "?" in sentence or CONDITIONAL.search(sentence) or ATTRIBUTION.search(sentence):
            continue
        for pattern, direction in ((AVOID, "negative"), (CHOICE, "positive"), (PREFERENCE, "positive")):
            match = pattern.search(sentence)
            if not match:
                continue
            # Narrator stance only, and the chosen object must be the target.
            prefix = sentence[:match.start()]
            if prefix.strip() or re.search(r'["“]', sentence):
                continue
            selected = COMPARISON.split(sentence[match.end():], maxsplit=1)[0]
            selected = re.sub(r"^\s*(?:(?:buying|holding)\s+|(?:the\s+)?(?:stock|shares)\s+(?:of|in)\s+)", "", selected, flags=re.I).strip()
            if not any(p.match(selected) for p in aliases):
                continue
            if direction == "positive" and re.search(r"\b(?:not|never|don't|wouldn't)\b", sentence[:match.end()], re.I):
                continue
            signals.append({"direction": direction, "text": " ".join(sentence.split()[:10])})
    directions = {s["direction"] for s in signals}
    if not directions:
        return {**base, "reason": "body read; no unambiguous current author recommendation for this company"}
    sentiment = "mixed" if len(directions) > 1 else next(iter(directions))
    evidence = []
    for direction in ("positive", "negative"):
        found = next((s for s in signals if s["direction"] == direction), None)
        if found:
            evidence.append(found)
    return {**base, "status": "assessed", "sentiment": sentiment, "article_type": "opinion",
            "confidence": "explicit stance", "evidence": evidence,
            "reason": "author recommendation from article body; contextual opinion, not a new factual catalyst"}
