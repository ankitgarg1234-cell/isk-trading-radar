"""Headline events and bounded company-specific article author opinions.

Factual announcements remain headline rules; explicit author recommendations
are separate opinion signals. Neutral baseline and publisher weights are locked.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from urllib.parse import urlsplit

VERSION = "article-context-v3"

# Each rule describes one event, rather than awarding every substring hit.
RULES = (
    ("guidance", "positive", r"\b(?:rais(?:e[sd]?|ing)|boost(?:s|ed)?|increas(?:e[sd]?|ing)|upward)\b.{0,35}\b(?:guidance|outlook|forecast)\b|\b(?:guidance|outlook|forecast)\b.{0,25}\b(?:raised|increased|boosted)\b"),
    ("guidance", "negative", r"\b(?:cut(?:s|ting)?|lower(?:s|ed|ing)?|slash(?:es|ed)?|withdraw(?:s|n)?)\b.{0,35}\b(?:guidance|outlook|forecast)\b|\b(?:guidance|outlook|forecast)\b.{0,25}\b(?:cut|lowered|withdrawn)\b"),
    ("earnings", "positive", r"\bbeat(?:s)?\b.{0,35}\b(?:earnings|revenue|estimates|expectations)\b|\b(?:earnings|revenue|profit|eps)\b.{0,30}\b(?:beat(?:s)?|surge[sd]?|grow(?:s|th)?|rise[sn]?)\b|\brecord\b.{0,15}\b(?:revenue|earnings|profit)\b"),
    ("earnings", "negative", r"\bmiss(?:es|ed)?\b.{0,35}\b(?:earnings|revenue|estimates|expectations)\b|\b(?:earnings|revenue|profit|eps)\b.{0,30}\b(?:miss(?:es|ed)?|declin(?:e[sd]?|ing)|fall[sn]?|disappoint(?:s|ed)?)\b"),
    ("rating", "positive", r"\bupgrad(?:e[sd]?|ing)\b|\b(?:initiates?|initiated)\b.{0,30}\b(?:buy|outperform)\b"),
    ("rating", "negative", r"\bdowngrad(?:e[sd]?|ing)\b"),
    ("contract", "positive", r"\b(?:wins?|won|secures?|secured|awarded|signs?|signed)\b.{0,35}\bcontract\b"),
    ("contract", "negative", r"\b(?:loses?|lost|cancels?|cancelled|canceled)\b.{0,35}\bcontract\b"),
    ("partnership", "positive", r"\b(?:announces?|announced|signs?|signed|forms?|formed)\b.{0,30}\bpartnership\b|\bpartners? with\b"),
    ("product", "positive", r"\blaunch(?:es|ed)?\b.{0,40}\b(?:product|chip|platform|service)\b"),
    ("regulatory", "positive", r"\b(?:fda|regulator)\b.{0,30}\bapprov(?:es?|ed|al)\b|\b(?:wins?|receives?|received|gets?)\b.{0,20}\bfda approval\b"),
    ("regulatory", "negative", r"\b(?:fda|regulator)\b.{0,30}\b(?:reject(?:s|ed|ion)?|clinical hold)\b"),
    ("legal", "negative", r"\b(?:sec investigation|accounting (?:probe|fraud|warning)|fraud|restatement|bankruptcy|recall)\b|\b(?:faces?|facing|files?|filed)\b.{0,25}\blawsuit\b"),
    ("financing", "negative", r"\b(?:announces?|announced|launches?|launched|prices?|priced)\b.{0,30}\b(?:stock|share|equity|public) offering\b|\bdilution\b"),
    ("buyback", "positive", r"\b(?:announces?|announced|raises?|raised|expands?|expanded|authorizes?|authorized)\b.{0,30}\b(?:buyback|share repurchase)\b"),
)
PATTERNS = [(kind, direction, re.compile(pattern, re.I)) for kind, direction, pattern in RULES]
CATALYSTS = {"guidance": "guidance", "earnings": "earnings", "contract": "contract",
             "partnership": "partnership", "product": "launch", "regulatory": "fda",
             "financing": "offering", "buyback": "buyback"}
MATERIAL_KINDS = set(CATALYSTS) | {"legal"}
OPINION = re.compile(r"\?|\b(?:could|might|may|should|rumou?r|speculat\w*|stocks? to (?:buy|watch)|worth buying|next big|is it time|poised to|expected to|set to)\b", re.I)
NEGATION = re.compile(r"\b(?:not|never|no|without|fails? to|failed to|unlikely to|denies?|denied)\b(?:\W+\w+){0,3}\W*$", re.I)
CONTRADICTS = re.compile(r"\b(?:disappoint\w*|slows?|slowed|weak\w*)\b", re.I)
GENERIC = {"company", "group", "holding", "holdings", "inc", "incorporated", "ltd", "limited", "corporation", "corp", "plc", "the"}
SPLIT = re.compile(r"\s*(?:;|\bbut\b|\bwhile\b|\band\b|\bafter\b|\bwhereas\b|\bas\b)\s*", re.I)


def _time(value):
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, timezone.utc)
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def _aliases(symbol, company):
    names = []
    if symbol:
        # Short tickers must be explicitly capitalised, avoiding ordinary words.
        names.append(re.compile(r"(?<!\w)\$?" + re.escape(symbol.upper()) + r"(?!\w)"))
    words = [w for w in re.findall(r"[\w]+", str(company)) if w.lower() not in GENERIC]
    if words:
        names.append(re.compile(r"\b" + r"\W+".join(map(re.escape, words)) + r"\b", re.I))
        if len(words[0]) >= 4 and words[0].lower() not in {"bank", "american", "united", "first", "national", "global", "international", "technology", "technologies", "financial", "capital", "resources"}:
            names.append(re.compile(r"\b" + re.escape(words[0]) + r"\b", re.I))
    return names


def _relevance(n, symbol, aliases):
    title = str(n.get("title") or "")
    if any(p.search(title) for p in aliases):
        return True, "company or ticker in headline"
    related = n.get("relatedTickers") or n.get("related_tickers") or []
    if isinstance(related, str):
        related = [related]
    if symbol and {str(x).upper() for x in related} == {str(symbol).upper()}:
        return True, "provider explicitly associates ticker"
    return False, "no explicit company or ticker association"


def _signals(title, aliases):
    if OPINION.search(title):
        return set(), "speculation, question or opinion; no asserted event scored"
    found = set()
    clauses = SPLIT.split(title)
    named = any(p.search(title) for p in aliases)
    for clause in clauses:
        # If an explicit company is present, only that company's clauses and
        # subjectless continuations are eligible; another named subject is not.
        target = any(p.search(clause) for p in aliases)
        if named and not target and not re.match(r"^\s*(?:raises?|cuts?|reports?|announces?|wins?|receives?|misses?|beats?|record|earnings|revenue|profit|guidance)\b", clause, re.I):
            continue
        for kind, direction, pattern in PATTERNS:
            for match in pattern.finditer(clause):
                if NEGATION.search(clause[:match.start()]) or re.search(r"\b(?:not|never|no|without)\b", match.group(), re.I):
                    continue
                # A rule cannot turn "profit growth disappoints" bullish.
                if direction == "positive" and kind == "earnings" and CONTRADICTS.search(clause):
                    found.add((kind, "negative"))
                else:
                    found.add((kind, direction))
    return found, "asserted headline events" if found else "no unambiguous event rule matched"


def _canonical_url(link):
    try:
        parts = urlsplit(str(link or ""))
        return (parts.netloc.lower() + parts.path.rstrip("/")) if parts.netloc else ""
    except ValueError:
        return ""


def _same_event(a, b):
    da, db = _time(a.get("published")), _time(b.get("published"))
    if da and db and abs((da - db).total_seconds()) > 36 * 3600:
        return False
    if a["canonical_url"] and a["canonical_url"] == b["canonical_url"]:
        return True
    ta, tb = a["normal_title"], b["normal_title"]
    if ta == tb:
        return True
    # Different or unknown release times cannot support approximate grouping.
    da, db = _time(a.get("published")), _time(b.get("published"))
    if not da or not db or abs((da - db).total_seconds()) > 36 * 3600:
        return False
    periods = lambda s: set(re.findall(r"\b(?:q[1-4]|20\d{2}|fiscal\s+\w+)\b", s))
    if periods(ta) != periods(tb):
        return False
    kinds_a = {k for k, _ in a["signals"]}
    kinds_b = {k for k, _ in b["signals"]}
    if kinds_a != kinds_b or not kinds_a:
        return False
    # Same earnings/ratings release is one event, including conflicting takes.
    if kinds_a <= {"earnings", "guidance", "rating"}:
        return True
    return SequenceMatcher(None, ta, tb).ratio() >= 0.82


def analyze_news(news, *, symbol, company_name, asof, credibility, priced_in):
    aliases = _aliases(symbol, company_name)
    now = _time(asof) or datetime.now(timezone.utc)
    groups, excluded = [], []
    for raw in news[:15]:
        n = dict(raw)
        title = str(n.get("title") or "")
        relevant, reason = _relevance(n, symbol, aliases)
        published = _time(n.get("published"))
        if not relevant or not title.strip() or (published and published > now):
            n["excluded_reason"] = "future publication timestamp" if published and published > now else reason
            excluded.append(n)
            continue
        signals, assessment = _signals(title, aliases)
        body = n.pop("article_assessment", None) or {"status": "unassessed", "reason": "article body has not been assessed"}
        # Body author opinion contributes once to news, never to material events.
        if body.get("status") == "assessed" and body.get("article_type") == "opinion":
            direction = body.get("sentiment")
            if direction in {"positive", "negative", "mixed"}:
                if direction in {"positive", "mixed"}:
                    signals.add(("opinion", "positive"))
                if direction in {"negative", "mixed"}:
                    signals.add(("opinion", "negative"))
                assessment += "; company-specific author opinion assessed from body"
        level, weight = credibility(str(n.get("publisher") or ""))
        item = {**n, "signals": sorted(signals), "relevance": reason, "assessment": assessment,
                "article_status": body.get("status", "unassessed"), "article_sentiment": body.get("sentiment", "unassessed"),
                "article_type": body.get("article_type"), "article_reason": body.get("reason"),
                "article_method": body.get("method"), "article_evidence": body.get("evidence") or [],
                "article_source_url": body.get("source_url"), "article_checked_at": body.get("checked_at"),
                "credibility": level, "weight": weight, "priced_in": priced_in(n.get("published")),
                "canonical_url": _canonical_url(n.get("link")),
                "normal_title": " ".join(re.findall(r"\w+", title.lower()))}
        group = next((g for g in groups if any(_same_event(item, old) for old in g)), None)
        if group is None:
            groups.append([item])
        else:
            group.append(item)
    items, pos, neg, material, high_negative = [], 0.0, 0.0, 0, 0
    catalysts = set()
    for i, group in enumerate(groups):
        # Merge evidence once per event. Contradictory coverage cannot be erased
        # by whichever publisher happened to appear first in the feed.
        evidence = {}
        for item in group:
            for kind, direction in item["signals"]:
                evidence[kind, direction] = max(evidence.get((kind, direction), 0), item["weight"])
        positive = min(2.0 * max(x["weight"] for x in group), sum(w for (_, d), w in evidence.items() if d == "positive"))
        negative = min(2.0 * max(x["weight"] for x in group), sum(w for (_, d), w in evidence.items() if d == "negative"))
        # Mixed reports do not grant bullish credit; preserve negative evidence.
        if positive and negative:
            positive = 0.0
        sentiment = "mixed" if negative and any(d == "positive" for _, d in evidence) else "negative" if negative else "positive" if positive else "neutral"
        kinds = {k for k, _ in evidence}
        important = bool(kinds & MATERIAL_KINDS)
        material += int(important)
        high_negative += int(important and negative > 0)
        catalysts.update(CATALYSTS[k] for k in kinds if k in CATALYSTS)
        pos += positive
        neg += negative
        representative = max(group, key=lambda x: (len(x["signals"]), x["weight"]))
        items.append({**{k:v for k,v in representative.items() if k not in {"normal_title", "canonical_url", "weight", "signals"}},
            "event_id": f"event-{i+1}", "sentiment": sentiment,
            "materiality": "high" if important else "normal",
            "thesis_impact": "weakens" if negative else "supports" if positive else "unknown",
            "matched_events": [{"type": k, "direction": d, "weight": w} for (k, d), w in sorted(evidence.items())],
            "positive_weight": round(positive, 3), "negative_weight": round(negative, 3),
            "points": round(1.5 * (positive-negative), 3), "coverage_count": len(group),
            "sources": [{"title": x["title"], "publisher": x.get("publisher"), "link": x.get("link"), "published": x.get("published"), "negative_events": [kind for kind, direction in x["signals"] if direction == "negative" and kind != "opinion"]} for x in group]})
    raw = pos - neg
    assessed = sum(i["article_status"] == "assessed" for i in items)
    pending = sum(i["article_status"] in {"queued", "processing", "deferred"} for i in items)
    return {"version": VERSION, "score": round(max(0, min(15, 7.5 + 1.5 * raw)), 1),
        "baseline_points": 7.5, "label": "Unavailable" if not items else "Bullish" if raw >= 2 else "Bearish" if raw <= -2 else "Neutral",
        "positive": round(pos, 3), "negative": round(neg, 3), "material_events": material,
        "high_negative_events": high_negative, "catalysts": sorted(catalysts), "items": items,
        "input_count": len(news[:15]), "unique_event_count": len(items),
        "duplicate_count": sum(len(g)-1 for g in groups), "excluded_count": len(excluded), "excluded_items": excluded,
        "coverage": "available" if items else "unavailable", "confidence": "headline and explicit author stance" if assessed else "headline-only",
        "body_assessed_count": assessed, "body_pending_count": pending,
        "body_unassessed_count": len(items)-assessed-pending,
        "method": "Company relevance, headline event rules, deduplication and bounded article author-stance rules. Only explicit company-specific recommendations in complete bodies affect opinion sentiment; other bodies remain unassessed. Opinions do not create factual catalysts. Neutral baseline, weights and age policy preserved."}
