from __future__ import annotations

import html as html_lib
import io
import re
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

import httpx

try:  # Optional at import time so the rest of the radar remains resilient.
    from pypdf import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None

from .config import settings


OFFICIAL_DOMAINS = {
    "whitehouse.gov", "www.whitehouse.gov",
    "sec.gov", "www.sec.gov", "data.sec.gov",
    "oge.gov", "www.oge.gov", "www2.oge.gov", "oge.box.com",
    "usaspending.gov", "www.usaspending.gov", "api.usaspending.gov",
    "commerce.gov", "www.commerce.gov",
    "energy.gov", "www.energy.gov",
    "defense.gov", "www.defense.gov",
    "treasury.gov", "home.treasury.gov", "www.treasury.gov",
    "state.gov", "www.state.gov",
    "transportation.gov", "www.transportation.gov",
    "hhs.gov", "www.hhs.gov",
}

HIGH_CREDIBILITY_PUBLISHERS = {
    "Reuters", "Bloomberg", "Associated Press", "AP Finance", "CNBC",
    "The Wall Street Journal", "Barrons.com", "MarketWatch",
}

GOV_TERMS = {
    "government", "federal", "white house", "administration", "department of defense",
    "department of war", "pentagon", "department of energy", "department of commerce",
    "treasury", "doe", "dod", "commerce department", "federal agency", "procurement",
}
DIRECT_CAPITAL_TERMS = {
    "equity stake", "government stake", "takes stake", "took a stake", "stake in",
    "investment", "invests", "investing", "award", "awards", "contract", "contracts",
    "grant", "grants", "loan", "loan guarantee", "funding", "subsidy", "subsidies",
    "procurement", "purchase agreement", "offtake", "off-take", "warrant", "convertible",
}
POSITIVE_POLICY_TERMS = {
    "support", "supports", "promote", "promotes", "incentive", "incentives", "tax credit",
    "funding", "award", "contract", "grant", "loan", "guarantee", "procurement", "investment",
    "strategic", "domestic production", "onshore", "onshoring",
}
NEGATIVE_POLICY_TERMS = {
    "cancel", "cancels", "cancelled", "canceled", "cut funding", "funding cut", "blocks",
    "blocked", "ban", "bans", "sanction", "sanctions", "export restriction", "export control",
    "revokes", "revoked", "terminates", "terminated", "probe", "investigation", "penalty",
    "tariff", "tariffs", "license restriction", "licensing restriction",
}
TRUMP_ADMIN_TERMS = {"president trump", "donald trump", "trump administration", "white house"}
TRUMP_PERSONAL_FINANCIAL_TERMS = {
    "buys", "bought", "purchases", "purchased", "invests", "invested", "investment",
    "owns", "owned", "ownership", "beneficial owner", "stake", "shares", "stock", "equity",
}
TRUMP_FAMILY_TERMS = {
    "donald trump jr", "donald j. trump jr", "eric trump", "ivanka trump",
    "jared kushner", "trump family",
}
CONNECTED_CAPITAL_TERMS = {
    "affinity partners", "a fin management", "1789 capital",
}


def _norm(text: str) -> str:
    text = re.sub(r"[^a-z0-9 ]+", " ", str(text or "").lower())
    drop = {"inc", "incorporated", "corp", "corporation", "company", "co", "ltd", "limited", "plc", "holdings", "group"}
    return " ".join(t for t in text.split() if t not in drop)


def _domain(url: str) -> str:
    try:
        return urlparse(url or "").netloc.lower().split(":")[0]
    except Exception:
        return ""


def _contains_any(text: str, terms: set[str]) -> bool:
    t = str(text or "").lower()
    return any(term in t for term in terms)


def _money(v: Any) -> float:
    try:
        return float(v or 0)
    except Exception:
        return 0.0


def _event_key(e: dict) -> tuple:
    return (str(e.get("type") or ""), str(e.get("title") or ""), str(e.get("source_url") or ""))


def _company_aliases(company_name: str, symbol: str = "") -> list[str]:
    """Conservative aliases suitable for government-description and disclosure matching."""
    raw = str(company_name or "").strip()
    aliases: list[str] = []
    n = _norm(raw)
    if len(n) >= 4:
        aliases.append(n)
        first = n.split()[0]
        if len(first) >= 5:
            aliases.append(first)
    # Raw legal name without punctuation can be useful when the brand is multiple words.
    legal = re.sub(r"\s+", " ", re.sub(r"[^A-Za-z0-9 ]+", " ", raw)).strip().lower()
    if len(legal) >= 5:
        aliases.append(legal)
    # Tickers are only used for disclosure matching, not broad federal keyword search,
    # because short tickers create too many false positives.
    if symbol and len(symbol) >= 3:
        aliases.append(symbol.lower())
    out = []
    for a in aliases:
        a = " ".join(a.split())
        if a and a not in out:
            out.append(a)
    return out


class StrategicCapitalProvider:
    """Shadow evidence layer for government / political strategic-capital signals.

    The layer is deliberately separate from the deterministic score and portfolio
    rank. It records point-in-time evidence for forward/walk-forward validation.
    """

    _award_cache: dict[str, tuple[float, dict]] = {}
    _document_cache: dict[str, tuple[float, str, str]] = {}
    _html_cache: dict[str, tuple[float, str]] = {}

    def __init__(self, timeout: float = 12.0):
        self.client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": settings.sec_user_agent, "Accept": "application/json,text/html,*/*"},
            follow_redirects=True,
        )

    @staticmethod
    def _source_quality(item: dict) -> str:
        domain = _domain(item.get("link") or item.get("source_url") or "")
        publisher = str(item.get("publisher") or item.get("source") or "")
        if domain in OFFICIAL_DOMAINS or any(domain.endswith("." + d) for d in OFFICIAL_DOMAINS):
            return "OFFICIAL"
        if publisher in HIGH_CREDIBILITY_PUBLISHERS:
            return "HIGH-CREDIBILITY MEDIA"
        return "SECONDARY"

    def classify_news(self, symbol: str, news: list[dict]) -> list[dict]:
        events: list[dict] = []
        for item in news or []:
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            # If a provider later adds summaries, classify title + summary without needing a new parser.
            text = f"{title} {item.get('summary') or item.get('description') or ''}".lower()
            quality = self._source_quality(item)
            government_context = _contains_any(text, GOV_TERMS | TRUMP_ADMIN_TERMS)
            family_context = _contains_any(text, TRUMP_FAMILY_TERMS)
            connected_capital_context = _contains_any(text, CONNECTED_CAPITAL_TERMS)
            direct_capital = _contains_any(text, DIRECT_CAPITAL_TERMS)
            negative = _contains_any(text, NEGATIVE_POLICY_TERMS)
            positive = _contains_any(text, POSITIVE_POLICY_TERMS)

            etype = None
            direction = "NEUTRAL"
            materiality = "LOW"
            verified = quality in {"OFFICIAL", "HIGH-CREDIBILITY MEDIA"}

            exact_personal = bool(
                not family_context
                and (
                    re.search(r"\bdonald(?: j\.?)? trump\b.{0,45}\b(?:buys|bought|purchases|purchased|invests|invested|owns|owned|acquires|acquired)\b", text)
                    or re.search(r"\bdonald(?: j\.?)? trump(?:'s)?\b.{0,45}\b(?:personal|personally|ownership|shares|stock|equity|stake)\b", text)
                )
            )
            if exact_personal:
                etype = "TRUMP_PERSONAL_INTEREST_MENTION"
                materiality = "HIGH" if quality == "OFFICIAL" else "MEDIUM"
                direction = "CONTEXT"
            elif family_context and _contains_any(text, TRUMP_PERSONAL_FINANCIAL_TERMS):
                etype = "TRUMP_FAMILY_INTEREST"
                materiality = "MEDIUM"
                direction = "CONTEXT"
            elif connected_capital_context and _contains_any(text, TRUMP_PERSONAL_FINANCIAL_TERMS | DIRECT_CAPITAL_TERMS):
                etype = "CONNECTED_CAPITAL_INTEREST"
                materiality = "MEDIUM"
                direction = "CONTEXT"
            elif government_context and direct_capital:
                if any(term in text for term in ("equity stake", "government stake", "takes stake", "took a stake", "stake in")):
                    etype = "GOVERNMENT_EQUITY_STAKE"
                    materiality = "VERY HIGH"
                elif any(term in text for term in ("contract", "award", "grant", "loan", "funding", "subsidy", "procurement", "offtake", "off-take")):
                    etype = "GOVERNMENT_CAPITAL_OR_DEMAND"
                    materiality = "HIGH"
                else:
                    etype = "ADMINISTRATION_STRATEGIC_ACTION"
                    materiality = "MEDIUM"
                direction = "NEGATIVE" if negative else "POSITIVE" if positive else "CONTEXT"
            elif government_context and (positive or negative):
                etype = "POLICY_OR_ADMINISTRATION_SIGNAL"
                materiality = "MEDIUM" if verified else "LOW"
                direction = "NEGATIVE" if negative else "POSITIVE"

            if etype:
                events.append({
                    "type": etype,
                    "title": title,
                    "direction": direction,
                    "materiality": materiality,
                    "verification": "VERIFIED SOURCE" if verified else "UNVERIFIED / SECONDARY",
                    "source_quality": quality,
                    "source": item.get("publisher") or _domain(item.get("link") or "") or "News",
                    "source_url": item.get("link") or "",
                    "published": item.get("published"),
                    "symbol": symbol,
                })
        return events

    def _usa_spending_awards(self, company_name: str, symbol: str = "", *, force: bool = False) -> dict:
        """Fetch direct and indirect federal spending evidence resiliently.

        USAspending can reject a mixed award-type query when type-specific fields or
        sort keys are combined.  Query contracts, non-loan assistance and loans
        separately so one bad component cannot erase all coverage.  Transient API
        failures are retried briefly and cached for only the short error TTL.
        """
        key = _norm(company_name)
        if not key or len(key) < 3:
            return {"status": "UNAVAILABLE", "reason": "company name unavailable", "events": [], "retry_recommended": False}
        cache_key = f"{key}|{symbol.upper()}"
        cached = self.__class__._award_cache.get(cache_key)
        normal_ttl = max(1, settings.strategic_official_refresh_hours) * 3600
        error_ttl = max(60, settings.strategic_error_retry_seconds)
        if not force and cached:
            cached_ttl = error_ttl if (cached[1] or {}).get("retry_recommended") else normal_ttl
            if time.time() - cached[0] < cached_ttl:
                return cached[1]

        end = date.today()
        start = end - timedelta(days=max(30, settings.strategic_usaspending_lookback_days))
        period = [{"start_date": start.isoformat(), "end_date": end.isoformat()}]
        events: list[dict] = []
        total = 0.0
        indirect_total = 0.0
        component_status: dict[str, str] = {}
        errors: list[str] = []
        retryable_http = {408, 425, 429, 500, 502, 503, 504}

        def _error_detail(resp) -> str:
            try:
                payload = resp.json() or {}
                detail = payload.get("detail") or payload.get("message") or ""
                if isinstance(detail, (list, dict)):
                    detail = str(detail)
                detail = re.sub(r"\s+", " ", str(detail)).strip()
                return f": {detail[:180]}" if detail else ""
            except Exception:
                return ""

        def _post(label: str, body: dict) -> dict | None:
            attempts = max(1, min(3, int(settings.strategic_usaspending_max_attempts)))
            for attempt in range(attempts):
                try:
                    resp = self.client.post("https://api.usaspending.gov/api/v2/search/spending_by_award/", json=body)
                    status_code = int(getattr(resp, "status_code", 200) or 200)
                    if status_code in retryable_http and attempt + 1 < attempts:
                        time.sleep(0.35 * (attempt + 1))
                        continue
                    resp.raise_for_status()
                    component_status[label] = "CHECKED"
                    return resp.json() or {}
                except httpx.HTTPStatusError as exc:
                    code = exc.response.status_code if exc.response is not None else 0
                    if code in retryable_http and attempt + 1 < attempts:
                        time.sleep(0.35 * (attempt + 1))
                        continue
                    component_status[label] = f"HTTP {code or 'ERROR'}"
                    errors.append(f"{label}: HTTP {code or 'ERROR'}{_error_detail(exc.response) if exc.response is not None else ''}")
                    return None
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    if attempt + 1 < attempts:
                        time.sleep(0.35 * (attempt + 1))
                        continue
                    component_status[label] = "NETWORK/TIMEOUT"
                    errors.append(f"{label}: {type(exc).__name__}")
                    return None
                except Exception as exc:
                    component_status[label] = "ERROR"
                    errors.append(f"{label}: {type(exc).__name__}")
                    return None
            return None

        def _direct_rows(payload: dict | None, *, event_type: str, amount_field: str, date_field: str, relationship: str = "DIRECT RECIPIENT"):
            nonlocal total
            if not payload:
                return
            for row in payload.get("results") or []:
                recip = str(row.get("Recipient Name") or "")
                if key not in _norm(recip) and (_norm(recip) and _norm(recip) not in key):
                    continue
                amount = _money(row.get(amount_field))
                total += max(0.0, amount)
                events.append({
                    "type": event_type,
                    "title": f"{row.get('Awarding Agency') or 'U.S. Government'} {'loan/guarantee' if event_type == 'FEDERAL_LOAN_OR_GUARANTEE' else 'award'} {row.get('Award ID') or ''}".strip(),
                    "direction": "POSITIVE" if amount > 0 else "CONTEXT",
                    "materiality": "HIGH" if amount >= 100_000_000 else "MEDIUM" if amount >= 10_000_000 else "LOW",
                    "verification": "VERIFIED SOURCE", "source_quality": "OFFICIAL", "source": "USAspending.gov",
                    "source_url": "https://www.usaspending.gov/", "published": row.get(date_field),
                    "amount": amount, "description": row.get("Description") or "", "recipient": recip,
                    "relationship": relationship,
                })

        # Split award classes so type-specific fields/sorts are always valid.
        direct_specs = [
            ("direct_contracts", ["A", "B", "C", "D"]),
            ("direct_assistance", ["02", "03", "04", "05", "06", "09", "10", "11"]),
        ]
        for label, codes in direct_specs:
            body = {
                "subawards": False, "limit": 25, "page": 1, "order": "desc", "sort": "Award Amount",
                "filters": {"recipient_search_text": [company_name], "time_period": period, "award_type_codes": codes},
                "fields": ["Award ID", "Recipient Name", "Start Date", "Award Amount", "Awarding Agency", "Description"],
            }
            _direct_rows(_post(label, body), event_type="FEDERAL_AWARD", amount_field="Award Amount", date_field="Start Date")

        loan = {
            "subawards": False, "limit": 25, "page": 1, "order": "desc", "sort": "Loan Value",
            "filters": {"recipient_search_text": [company_name], "time_period": period, "award_type_codes": ["07", "08"]},
            "fields": ["Award ID", "Recipient Name", "Issued Date", "Loan Value", "Awarding Agency"],
        }
        _direct_rows(_post("direct_loans", loan), event_type="FEDERAL_LOAN_OR_GUARANTEE", amount_field="Loan Value", date_field="Issued Date")

        # Product/vendor mentions: split contracts and assistance for the same reason.
        aliases = [a for a in _company_aliases(company_name, "") if len(a) >= 5][:2]
        if aliases:
            alias_norm = [_norm(a) for a in aliases]
            seen_indirect_awards: set[str] = set()
            for label, codes in [
                ("product_mentions_contracts", ["A", "B", "C", "D"]),
                ("product_mentions_assistance", ["02", "03", "04", "05", "06", "09", "10", "11"]),
            ]:
                kw = {
                    "subawards": False, "limit": 25, "page": 1, "order": "desc", "sort": "Award Amount",
                    "filters": {"keywords": aliases, "time_period": period, "award_type_codes": codes},
                    "fields": ["Award ID", "Recipient Name", "Start Date", "Award Amount", "Awarding Agency", "Description"],
                }
                payload = _post(label, kw)
                if not payload:
                    continue
                for row in payload.get("results") or []:
                    recip = str(row.get("Recipient Name") or "")
                    desc = str(row.get("Description") or "")
                    recip_n, desc_n = _norm(recip), _norm(desc)
                    if key in recip_n or (recip_n and recip_n in key):
                        continue
                    if not any(a and (a in desc_n or a in recip_n) for a in alias_norm):
                        continue
                    award_id = str(row.get("Award ID") or "").strip()
                    dedupe_key = award_id or f"{recip_n}|{desc_n[:120]}|{row.get('Start Date')}"
                    if dedupe_key in seen_indirect_awards:
                        continue
                    seen_indirect_awards.add(dedupe_key)
                    amount = _money(row.get("Award Amount"))
                    indirect_total += max(0.0, amount)
                    events.append({
                        "type": "FEDERAL_PRODUCT_OR_VENDOR_MENTION",
                        "title": f"{row.get('Awarding Agency') or 'U.S. Government'} procurement mentions {company_name}",
                        "direction": "CONTEXT",
                        "materiality": "HIGH" if amount >= 100_000_000 else "MEDIUM" if amount >= 10_000_000 else "LOW",
                        "verification": "VERIFIED SOURCE", "source_quality": "OFFICIAL", "source": "USAspending.gov",
                        "source_url": "https://www.usaspending.gov/", "published": row.get("Start Date"),
                        "amount": amount, "description": desc[:700], "recipient": recip,
                        "relationship": "INDIRECT / PRIME AWARD TO ANOTHER RECIPIENT",
                    })

        expected = 5 if aliases else 3
        checked = sum(v == "CHECKED" for v in component_status.values())
        retry_recommended = checked < expected
        if checked == expected:
            status = "CHECKED"
        elif checked:
            status = "PARTIAL — AUTO RETRY"
        else:
            status = "TEMPORARILY UNAVAILABLE — AUTO RETRY"
        coverage_labels = [k.replace("_", " ") for k, v in component_status.items() if v == "CHECKED"]
        out = {
            "status": status,
            "coverage": ", ".join(coverage_labels),
            "component_status": component_status,
            "retry_recommended": retry_recommended,
            "retry_after_seconds": error_ttl if retry_recommended else None,
            "last_error": errors[-1] if errors else None,
            "total_amount": round(total, 2),
            "indirect_mention_award_amount": round(indirect_total, 2),
            "events": events[:16],
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        self.__class__._award_cache[cache_key] = (time.time(), out)
        return out

    def _html_text(self, url: str, *, force: bool = False) -> tuple[str, str]:
        if not url:
            return "", "NOT CONFIGURED"
        ttl = max(1, settings.strategic_official_refresh_hours) * 3600
        cached = self.__class__._html_cache.get(url)
        if not force and cached and time.time() - cached[0] < ttl:
            return cached[1], "CACHED"
        try:
            r = self.client.get(url, headers={"Accept": "text/html,*/*"})
            r.raise_for_status()
            raw = str(r.text or "")
            raw = re.sub(r"<script\b[^>]*>.*?</script>", " ", raw, flags=re.I | re.S)
            raw = re.sub(r"<style\b[^>]*>.*?</style>", " ", raw, flags=re.I | re.S)
            text = html_lib.unescape(re.sub(r"<[^>]+>", " ", raw))
            text = re.sub(r"\s+", " ", text).strip()
            self.__class__._html_cache[url] = (time.time(), text)
            return text, "CHECKED"
        except Exception as exc:
            return "", f"UNAVAILABLE ({type(exc).__name__})"

    def _whitehouse_investment_tracker(self, company_name: str, symbol: str, *, force: bool = False) -> dict:
        """Detect company mentions on the official White House investment tracker.

        A hit is administration-highlighted *private investment / strategic interest*.
        It is explicitly not treated as U.S. government capital or a Trump personal holding.
        """
        url = settings.whitehouse_investments_url
        text, source_status = self._html_text(url, force=force)
        if not text:
            return {"status": "UNKNOWN", "source_status": source_status, "source_url": url, "events": []}
        normalized = _norm(text)
        aliases = [a for a in _company_aliases(company_name, "") if len(a) >= 5]
        hit = next((a for a in aliases if _norm(a) in normalized), None)
        if not hit:
            return {"status": "NOT FOUND IN CHECKED TRACKER", "source_status": source_status, "source_url": url, "events": []}
        # Grab a small local context and an amount if the page places it near the company.
        low = text.lower()
        pos = low.find(hit.lower())
        context = text[max(0, pos - 120): min(len(text), pos + len(hit) + 260)] if pos >= 0 else ""
        amt = re.search(r"\$\s?[\d,.]+\s*(?:million|billion|trillion|m|b|t)?", context, flags=re.I)
        event = {
            "type": "ADMINISTRATION_HIGHLIGHTED_INVESTMENT",
            "title": f"White House investment tracker lists {company_name}",
            "direction": "CONTEXT",
            "materiality": "MEDIUM",
            "verification": "VERIFIED SOURCE",
            "source_quality": "OFFICIAL",
            "source": "The White House — Investments",
            "source_url": url,
            "published": None,
            "amount_text": amt.group(0) if amt else None,
            "description": "Administration-highlighted private investment / strategic interest; not U.S. government investment.",
        }
        return {
            "status": "EVIDENCE FOUND", "source_status": source_status, "source_url": url,
            "match": hit, "amount_text": event.get("amount_text"), "events": [event],
        }

    def _document_text(self, url: str, *, force: bool = False) -> tuple[str, str]:
        if not url:
            return "", "NOT CONFIGURED"
        ttl = max(1, settings.strategic_official_refresh_hours) * 3600
        cached = self.__class__._document_cache.get(url)
        if not force and cached and time.time() - cached[0] < ttl:
            return cached[1], "CACHED"
        if PdfReader is None:
            return "", "PYPDF UNAVAILABLE"
        try:
            r = self.client.get(url, headers={"Accept": "application/pdf,*/*"})
            r.raise_for_status()
            reader = PdfReader(io.BytesIO(r.content))
            text = "\n".join((p.extract_text() or "") for p in reader.pages)
            self.__class__._document_cache[url] = (time.time(), text, "CHECKED")
            return text, "CHECKED"
        except Exception as exc:
            return "", f"UNAVAILABLE ({type(exc).__name__})"

    @staticmethod
    def _match_disclosure_text(text: str, company_name: str, symbol: str) -> list[dict]:
        """Return conservative row-local matches from an OGE disclosure PDF.

        Transaction reports often contain many adjacent rows. Fields are therefore
        read *after* each company match, rather than from a wide context window, so
        a nearby NVIDIA sale cannot be mistaken for a different NVIDIA purchase.
        """
        raw = str(text or "")
        lower = raw.lower()
        cname = _norm(company_name)
        patterns: list[tuple[str, str]] = []
        if cname and len(cname) >= 5:
            words = [w for w in cname.split() if len(w) >= 4]
            if words:
                patterns.append((r"\b" + r"\s+".join(re.escape(w) for w in words[:3]) + r"\b", "company"))
            if len(words) > 1:
                patterns.append((rf"\b{re.escape(words[0])}\b", "brand"))
        if symbol and len(symbol) >= 3:
            patterns.append((rf"\({re.escape(symbol.lower())}\)", "ticker"))
            if len(symbol) >= 4:
                patterns.append((rf"\b{re.escape(symbol.lower())}\b", "ticker"))

        matches: list[dict] = []
        seen_positions: list[int] = []
        for pattern, kind in patterns:
            for m in re.finditer(pattern, lower, flags=re.I):
                # Multiple aliases can point at the same table row. Keep nearby alias
                # hits once, while preserving genuinely separate transactions.
                if any(abs(m.start() - p) < 40 for p in seen_positions):
                    continue
                seen_positions.append(m.start())
                after = re.sub(r"\s+", " ", raw[m.end(): min(len(raw), m.end() + 360)]).strip()
                snippet = re.sub(r"\s+", " ", raw[max(0, m.start() - 80): min(len(raw), m.end() + 420)]).strip()
                action = None
                action_match = re.search(r"\b(purchase|purchased|buy|bought|sale|sold|sell|exchange)\b", after, flags=re.I)
                if action_match:
                    word = action_match.group(1).lower()
                    action = "PURCHASE" if word in {"purchase", "purchased", "buy", "bought"} else "SALE" if word in {"sale", "sold", "sell"} else "EXCHANGE"
                date_match = re.search(r"\b(?:0?[1-9]|1[0-2])[/-](?:0?[1-9]|[12]\d|3[01])[/-](?:20)?\d{2}\b", after)
                amount_match = re.search(r"\$\s?[\d,]+(?:\.\d+)?\s*(?:-|–|—|to)\s*\$\s?[\d,]+(?:\.\d+)?", after, flags=re.I)
                matches.append({
                    "match": kind, "action": action,
                    "date": date_match.group(0) if date_match else None,
                    "amount_range": amount_match.group(0) if amount_match else None,
                    "snippet": snippet[:900],
                })
                if len(matches) >= 12:
                    return matches
        return matches

    def _trump_personal_disclosure(self, company_name: str, symbol: str, *, force: bool = False) -> dict:
        if not settings.strategic_disclosure_pdf_enabled:
            return {
                "status": "DEFERRED — BACKGROUND PDF CHECK",
                "source_status": "DISABLED IN LIVE WEB PROCESS",
                "sources_checked": 0,
                "matched_reports": 0,
                "source_results": [],
                "events": [],
                "source_url": "",
            }
        urls: list[str] = []
        for u in [settings.trump_oge_disclosure_url, *settings.trump_periodic_transaction_urls]:
            u = str(u or "").strip()
            if u and u not in urls:
                urls.append(u)
        if not urls:
            return {"status": "UNKNOWN", "source_status": "NOT CONFIGURED", "sources_checked": 0, "events": []}

        source_results = []
        events = []
        matched_reports = 0
        transaction_reports = 0
        any_checked = False
        for url in urls:
            text, source_status = self._document_text(url, force=force)
            if source_status in {"CHECKED", "CACHED"}:
                any_checked = True
            matches = self._match_disclosure_text(text, company_name, symbol) if text else []
            is_transaction_report = "periodic transaction report" in text.lower() if text else "periodic-transaction-report" in url.lower()
            if matches:
                matched_reports += 1
                if is_transaction_report:
                    transaction_reports += 1
                for idx, match in enumerate(matches[:5]):
                    action = match.get("action")
                    title = f"Donald Trump disclosure mentions {company_name}"
                    if is_transaction_report and action:
                        title = f"Donald Trump periodic disclosure: {action.title()} involving {company_name}"
                    elif is_transaction_report:
                        title = f"Donald Trump periodic transaction disclosure mentions {company_name}"
                    events.append({
                        "type": "TRUMP_PERSONAL_DISCLOSURE_TRANSACTION" if is_transaction_report else "TRUMP_PERSONAL_DISCLOSURE_INTEREST",
                        "title": title,
                        "direction": "CONTEXT",
                        "materiality": "HIGH" if is_transaction_report else "MEDIUM",
                        "verification": "VERIFIED SOURCE", "source_quality": "OFFICIAL",
                        "source": "White House / OGE disclosure",
                        "source_url": url,
                        "published": match.get("date"),
                        "transaction_action": action,
                        "amount_range": match.get("amount_range"),
                        "match": match.get("match"),
                        "description": match.get("snippet"),
                    })
            source_results.append({"url": url, "status": source_status, "matches": len(matches), "report_type": "PERIODIC TRANSACTION" if is_transaction_report else "ANNUAL / OTHER"})

        if events:
            if transaction_reports:
                status = f"VERIFIED TRANSACTION DISCLOSURE — {len(events)} MATCH{'ES' if len(events) != 1 else ''}"
            else:
                status = "DISCLOSURE MENTION — REVIEW SOURCE"
        elif any_checked:
            status = "NOT FOUND IN CHECKED DISCLOSURES"
        else:
            status = "UNKNOWN"
        return {
            "status": status,
            "source_status": "CHECKED" if any_checked else "UNAVAILABLE",
            "sources_checked": sum(1 for x in source_results if x["status"] in {"CHECKED", "CACHED"}),
            "matched_reports": matched_reports,
            "source_results": source_results,
            "events": events[:10],
            "source_url": next((e.get("source_url") for e in events), urls[0] if urls else ""),
        }

    @staticmethod
    def _summary(events: list[dict], annual_revenue: float | None, federal_amount: float) -> dict:
        positive = sum(e.get("direction") == "POSITIVE" for e in events)
        negative = sum(e.get("direction") == "NEGATIVE" for e in events)
        very_high = sum(e.get("materiality") == "VERY HIGH" for e in events)
        high = sum(e.get("materiality") == "HIGH" for e in events)
        official = sum(e.get("source_quality") == "OFFICIAL" for e in events)
        if positive and negative:
            direction = "MIXED"
        elif negative:
            direction = "NEGATIVE"
        elif positive:
            direction = "POSITIVE"
        elif events:
            direction = "CONTEXT"
        else:
            direction = "NONE"
        strength = min(100, very_high * 35 + high * 20 + max(0, len(events) - high - very_high) * 7 + official * 5)
        ratio = None
        if annual_revenue and annual_revenue > 0 and federal_amount > 0:
            ratio = federal_amount / annual_revenue * 100
        label = "VERY STRONG" if strength >= 75 else "STRONG" if strength >= 50 else "MODERATE" if strength >= 25 else "LOW" if strength else "NONE"
        return {"direction": direction, "evidence_strength": strength, "label": label, "federal_amount_to_revenue_pct": round(ratio, 2) if ratio is not None else None}

    def assess(
        self,
        symbol: str,
        *,
        company_name: str = "",
        news: list[dict] | None = None,
        annual_revenue: float | None = None,
        prior: dict | None = None,
        fetch_official: bool = False,
        force_official: bool = False,
    ) -> dict:
        symbol = str(symbol or "").upper().strip()
        company_name = company_name or symbol
        events = self.classify_news(symbol, news or [])
        prior = prior or {}

        federal = prior.get("federal_awards") or {"status": "NOT CHECKED", "total_amount": 0.0, "events": []}
        personal = prior.get("trump_personal_disclosure") or {"status": "NOT CHECKED", "events": []}
        wh_tracker = prior.get("whitehouse_investment_tracker") or {"status": "NOT CHECKED", "events": []}
        checked_at = prior.get("official_checked_at")
        if fetch_official and settings.strategic_capital_enabled and not symbol.endswith(".ST"):
            # TypeError fallbacks keep older test/provider stubs compatible while the
            # production provider uses the richer symbol + force-refresh signature.
            try:
                federal = self._usa_spending_awards(company_name, symbol, force=force_official)
            except TypeError:
                federal = self._usa_spending_awards(company_name)
            try:
                personal = self._trump_personal_disclosure(company_name, symbol, force=force_official)
            except TypeError:
                personal = self._trump_personal_disclosure(company_name, symbol)
            wh_tracker = self._whitehouse_investment_tracker(company_name, symbol, force=force_official)
            checked_at = datetime.now(timezone.utc).isoformat()

        events.extend(federal.get("events") or [])
        events.extend(personal.get("events") or [])
        events.extend(wh_tracker.get("events") or [])
        deduped: list[dict] = []
        seen = set()
        for event in events:
            key = _event_key(event)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(event)

        federal_amount = _money(federal.get("total_amount"))
        summary = self._summary(deduped, annual_revenue, federal_amount)
        trump_admin = [e for e in deduped if e.get("type") == "ADMINISTRATION_HIGHLIGHTED_INVESTMENT" or (e.get("type") in {"ADMINISTRATION_STRATEGIC_ACTION", "POLICY_OR_ADMINISTRATION_SIGNAL", "GOVERNMENT_EQUITY_STAKE", "GOVERNMENT_CAPITAL_OR_DEMAND"} and _contains_any(str(e.get("title") or ""), TRUMP_ADMIN_TERMS))]
        family = [e for e in deduped if e.get("type") == "TRUMP_FAMILY_INTEREST"]
        connected_capital = [e for e in deduped if e.get("type") in {"TRUMP_FAMILY_INTEREST", "CONNECTED_CAPITAL_INTEREST"}]
        government_equity = [e for e in deduped if e.get("type") == "GOVERNMENT_EQUITY_STAKE"]
        sector_policy = [e for e in deduped if e.get("type") == "POLICY_OR_ADMINISTRATION_SIGNAL" and e.get("direction") in {"POSITIVE", "NEGATIVE"}]
        government_demand = [e for e in deduped if e.get("type") in {"FEDERAL_AWARD", "FEDERAL_LOAN_OR_GUARANTEE", "FEDERAL_PRODUCT_OR_VENDOR_MENTION", "GOVERNMENT_CAPITAL_OR_DEMAND"}]

        shadow_adjustment = 0.0
        if summary["direction"] == "POSITIVE":
            shadow_adjustment = min(8.0, summary["evidence_strength"] / 12.5)
        elif summary["direction"] == "NEGATIVE":
            shadow_adjustment = -min(10.0, summary["evidence_strength"] / 10.0)

        fed_components = federal.get("component_status") or {}
        product_components = [
            fed_components.get("product_mentions_contracts"),
            fed_components.get("product_mentions_assistance"),
        ]
        if product_components and all(x == "CHECKED" for x in product_components):
            product_coverage = "CHECKED"
        elif any(x for x in product_components):
            product_coverage = "PARTIAL — AUTO RETRY"
        else:
            product_coverage = "NOT CHECKED"

        personal_sources = personal.get("source_results") or []
        personal_complete = bool(personal_sources) and all(
            str(x.get("status") or "") in {"CHECKED", "CACHED"} for x in personal_sources
        )
        wh_complete = str(wh_tracker.get("source_status") or "") in {"CHECKED", "CACHED"}
        federal_complete = str(federal.get("status") or "") == "CHECKED"
        if fetch_official:
            official_check_status = "COMPLETE" if (federal_complete and personal_complete and wh_complete) else "PARTIAL"
        else:
            official_check_status = prior.get("official_check_status") or "NOT CHECKED"

        return {
            "mode": "SHADOW_ONLY", "symbol": symbol, "company_name": company_name, **summary,
            "shadow_rank_adjustment": round(shadow_adjustment, 1), "events": deduped[:14], "event_count": len(deduped),
            "government_equity_stake": "EVIDENCE FOUND" if government_equity else "NONE FOUND IN CURRENT EVIDENCE",
            "government_capital_or_demand": "EVIDENCE FOUND" if government_demand else "NONE FOUND IN CURRENT EVIDENCE",
            "sector_policy_support": "EVIDENCE FOUND" if sector_policy else "NONE FOUND IN CURRENT EVIDENCE",
            "trump_administration_action": "EVIDENCE FOUND" if trump_admin else "NONE FOUND IN CURRENT EVIDENCE",
            "trump_personal_disclosure": personal,
            "trump_family_interest": "EVIDENCE FOUND" if family else "NONE FOUND IN CURRENT EVIDENCE",
            "connected_capital_interest": "EVIDENCE FOUND" if connected_capital else "NONE FOUND IN CURRENT EVIDENCE",
            "whitehouse_investment_tracker": wh_tracker,
            "federal_awards": federal,
            "official_checked_at": checked_at,
            "official_check_status": official_check_status,
            "official_retry_after_seconds": max(60, settings.strategic_error_retry_seconds) if official_check_status == "PARTIAL" else None,
            "coverage": {
                "direct_federal_awards": federal.get("status") or "NOT CHECKED",
                "federal_product_mentions": product_coverage,
                "trump_disclosures": personal.get("source_status") or "NOT CHECKED",
                "trump_disclosure_sources_checked": personal.get("sources_checked", 0),
                "whitehouse_investment_tracker": wh_tracker.get("source_status") or "NOT CHECKED",
            },
            "source_note": "Official-source evidence and connected-capital news context. Political/family mentions alone never qualify a stock or create a positive rank adjustment.",
        }
