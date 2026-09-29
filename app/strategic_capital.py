from __future__ import annotations

import io
import re
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

import httpx

try:  # Optional at import time so the rest of the radar remains resilient.
    from pypdf import PdfReader
except Exception:  # pragma: no cover - exercised only when dependency is absent
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
}
TRUMP_ADMIN_TERMS = {
    "president trump", "donald trump", "trump administration", "white house",
}
TRUMP_PERSONAL_FINANCIAL_TERMS = {
    "buys", "bought", "purchases", "purchased", "invests", "invested", "investment",
    "owns", "owned", "ownership", "beneficial owner", "stake", "shares", "stock", "equity",
}
TRUMP_FAMILY_TERMS = {
    "donald trump jr", "donald j. trump jr", "eric trump", "ivanka trump", "trump family",
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


class StrategicCapitalProvider:
    """Shadow evidence layer for government / political strategic-capital signals.

    It deliberately does *not* change the deterministic score or portfolio rank.
    The output is stored point-in-time so it can later be tested for incremental
    predictive value before promotion into the allocation model.
    """

    _award_cache: dict[str, tuple[float, dict]] = {}
    _oge_cache: tuple[float, str] | None = None

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
            text = title.lower()
            quality = self._source_quality(item)
            government_context = _contains_any(text, GOV_TERMS | TRUMP_ADMIN_TERMS)
            family_context = _contains_any(text, TRUMP_FAMILY_TERMS)
            direct_capital = _contains_any(text, DIRECT_CAPITAL_TERMS)
            negative = _contains_any(text, NEGATIVE_POLICY_TERMS)
            positive = _contains_any(text, POSITIVE_POLICY_TERMS)

            etype = None
            direction = "NEUTRAL"
            materiality = "LOW"
            verified = quality in {"OFFICIAL", "HIGH-CREDIBILITY MEDIA"}

            # Donald Trump personally is kept separate from the administration.
            exact_personal = bool(
                not family_context
                and (
                    re.search(r"\bdonald(?: j\.?)? trump\b.{0,35}\b(?:buys|bought|purchases|purchased|invests|invested|owns|owned|acquires|acquired)\b", text)
                    or re.search(r"\bdonald(?: j\.?)? trump(?:'s)?\b.{0,35}\b(?:personal|personally|ownership|shares|stock|equity|stake)\b", text)
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

            if not etype:
                continue
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

    def _usa_spending_awards(self, company_name: str) -> dict:
        key = _norm(company_name)
        if not key or len(key) < 3:
            return {"status": "UNAVAILABLE", "reason": "company name unavailable", "events": []}
        cached = self.__class__._award_cache.get(key)
        ttl = max(1, settings.strategic_official_refresh_hours) * 3600
        if cached and time.time() - cached[0] < ttl:
            return cached[1]

        end = date.today()
        start = end - timedelta(days=max(30, settings.strategic_usaspending_lookback_days))
        common = {
            "subawards": False,
            "limit": 25,
            "page": 1,
            "order": "desc",
            "sort": "Award Amount",
            "filters": {
                "recipient_search_text": [company_name],
                "time_period": [{"start_date": start.isoformat(), "end_date": end.isoformat()}],
            },
        }
        events: list[dict] = []
        total = 0.0
        try:
            # Contracts + non-loan assistance support Award Amount.
            body = dict(common)
            body["filters"] = dict(common["filters"], award_type_codes=["A", "B", "C", "D", "02", "03", "04", "05", "06", "09", "10", "11"])
            body["fields"] = ["Award ID", "Recipient Name", "Start Date", "Award Amount", "Awarding Agency", "Description"]
            resp = self.client.post("https://api.usaspending.gov/api/v2/search/spending_by_award/", json=body)
            resp.raise_for_status()
            for row in (resp.json() or {}).get("results") or []:
                recip = str(row.get("Recipient Name") or "")
                # Recipient search can be fuzzy. Retain only reasonable legal-name matches.
                if key not in _norm(recip) and _norm(recip) not in key:
                    continue
                amount = _money(row.get("Award Amount"))
                total += max(0.0, amount)
                events.append({
                    "type": "FEDERAL_AWARD",
                    "title": f"{row.get('Awarding Agency') or 'U.S. Government'} award {row.get('Award ID') or ''}".strip(),
                    "direction": "POSITIVE" if amount > 0 else "CONTEXT",
                    "materiality": "HIGH" if amount >= 100_000_000 else "MEDIUM" if amount >= 10_000_000 else "LOW",
                    "verification": "VERIFIED SOURCE",
                    "source_quality": "OFFICIAL",
                    "source": "USAspending.gov",
                    "source_url": "https://www.usaspending.gov/",
                    "published": row.get("Start Date"),
                    "amount": amount,
                    "description": row.get("Description") or "",
                    "recipient": recip,
                })

            # Loans/loan guarantees expose Loan Value instead of Award Amount.
            loan = dict(common)
            loan["sort"] = "Loan Value"
            loan["filters"] = dict(common["filters"], award_type_codes=["07", "08"])
            loan["fields"] = ["Award ID", "Recipient Name", "Issued Date", "Loan Value", "Awarding Agency"]
            resp = self.client.post("https://api.usaspending.gov/api/v2/search/spending_by_award/", json=loan)
            resp.raise_for_status()
            for row in (resp.json() or {}).get("results") or []:
                recip = str(row.get("Recipient Name") or "")
                if key not in _norm(recip) and _norm(recip) not in key:
                    continue
                amount = _money(row.get("Loan Value"))
                total += max(0.0, amount)
                events.append({
                    "type": "FEDERAL_LOAN_OR_GUARANTEE",
                    "title": f"{row.get('Awarding Agency') or 'U.S. Government'} loan/guarantee {row.get('Award ID') or ''}".strip(),
                    "direction": "POSITIVE" if amount > 0 else "CONTEXT",
                    "materiality": "HIGH" if amount >= 100_000_000 else "MEDIUM" if amount >= 10_000_000 else "LOW",
                    "verification": "VERIFIED SOURCE",
                    "source_quality": "OFFICIAL",
                    "source": "USAspending.gov",
                    "source_url": "https://www.usaspending.gov/",
                    "published": row.get("Issued Date"),
                    "amount": amount,
                    "recipient": recip,
                })
            out = {"status": "CHECKED", "total_amount": round(total, 2), "events": events[:12], "checked_at": datetime.now(timezone.utc).isoformat()}
        except Exception as exc:
            out = {"status": f"UNAVAILABLE ({type(exc).__name__})", "total_amount": 0.0, "events": [], "checked_at": datetime.now(timezone.utc).isoformat()}
        self.__class__._award_cache[key] = (time.time(), out)
        return out

    def _oge_text(self) -> tuple[str, str]:
        ttl = max(1, settings.strategic_official_refresh_hours) * 3600
        cached = self.__class__._oge_cache
        if cached and time.time() - cached[0] < ttl:
            return cached[1], "CACHED"
        if not settings.trump_oge_disclosure_url:
            return "", "NOT CONFIGURED"
        if PdfReader is None:
            return "", "PYPDF UNAVAILABLE"
        try:
            r = self.client.get(settings.trump_oge_disclosure_url, headers={"Accept": "application/pdf,*/*"})
            r.raise_for_status()
            reader = PdfReader(io.BytesIO(r.content))
            text = "\n".join((p.extract_text() or "") for p in reader.pages)
            self.__class__._oge_cache = (time.time(), text)
            return text, "CHECKED"
        except Exception as exc:
            return "", f"UNAVAILABLE ({type(exc).__name__})"

    def _trump_personal_disclosure(self, company_name: str, symbol: str) -> dict:
        text, status = self._oge_text()
        if not text:
            return {"status": "UNKNOWN", "source_status": status, "source_url": settings.trump_oge_disclosure_url}
        normalized = _norm(text)
        cname = _norm(company_name)
        # Avoid very short/common company names causing spurious matches.
        company_hit = bool(cname and len(cname) >= 5 and cname in normalized)
        ticker_hit = bool(symbol and len(symbol) >= 3 and re.search(rf"\b{re.escape(symbol.lower())}\b", text.lower()))
        if not (company_hit or ticker_hit):
            return {"status": "NOT FOUND IN CHECKED DISCLOSURE", "source_status": status, "source_url": settings.trump_oge_disclosure_url}

        # A text hit in an OGE report is treated as disclosed-interest evidence, not
        # automatically as a stock purchase: the report may describe income or another
        # financial relationship. The UI explicitly tells the user to review the source.
        return {
            "status": "DISCLOSURE MENTION — REVIEW SOURCE",
            "source_status": status,
            "source_url": settings.trump_oge_disclosure_url,
            "match": "company name" if company_hit else "ticker",
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
    ) -> dict:
        symbol = str(symbol or "").upper().strip()
        company_name = company_name or symbol
        events = self.classify_news(symbol, news or [])
        prior = prior or {}

        federal = prior.get("federal_awards") or {"status": "NOT CHECKED", "total_amount": 0.0, "events": []}
        personal = prior.get("trump_personal_disclosure") or {"status": "NOT CHECKED"}
        checked_at = prior.get("official_checked_at")
        if fetch_official and settings.strategic_capital_enabled and not symbol.endswith(".ST"):
            federal = self._usa_spending_awards(company_name)
            personal = self._trump_personal_disclosure(company_name, symbol)
            checked_at = datetime.now(timezone.utc).isoformat()

        events.extend(federal.get("events") or [])
        # De-duplicate a source/event if it appeared both in news and an official feed.
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
        trump_admin = [e for e in deduped if e.get("type") in {"ADMINISTRATION_STRATEGIC_ACTION", "POLICY_OR_ADMINISTRATION_SIGNAL", "GOVERNMENT_EQUITY_STAKE", "GOVERNMENT_CAPITAL_OR_DEMAND"} and _contains_any(str(e.get("title") or ""), TRUMP_ADMIN_TERMS)]
        family = [e for e in deduped if e.get("type") == "TRUMP_FAMILY_INTEREST"]
        government_equity = [e for e in deduped if e.get("type") == "GOVERNMENT_EQUITY_STAKE"]
        sector_policy = [e for e in deduped if e.get("type") == "POLICY_OR_ADMINISTRATION_SIGNAL" and e.get("direction") in {"POSITIVE", "NEGATIVE"}]
        government_demand = [e for e in deduped if e.get("type") in {"FEDERAL_AWARD", "FEDERAL_LOAN_OR_GUARANTEE", "GOVERNMENT_CAPITAL_OR_DEMAND"}]

        # Shadow adjustment is logged for research but is NOT added to rank-v1.
        shadow_adjustment = 0.0
        if summary["direction"] == "POSITIVE":
            shadow_adjustment = min(8.0, summary["evidence_strength"] / 12.5)
        elif summary["direction"] == "NEGATIVE":
            shadow_adjustment = -min(10.0, summary["evidence_strength"] / 10.0)

        return {
            "mode": "SHADOW_ONLY",
            "symbol": symbol,
            "company_name": company_name,
            **summary,
            "shadow_rank_adjustment": round(shadow_adjustment, 1),
            "events": deduped[:12],
            "event_count": len(deduped),
            "government_equity_stake": "EVIDENCE FOUND" if government_equity else "NONE FOUND IN CURRENT EVIDENCE",
            "government_capital_or_demand": "EVIDENCE FOUND" if government_demand else "NONE FOUND IN CURRENT EVIDENCE",
            "sector_policy_support": "EVIDENCE FOUND" if sector_policy else "NONE FOUND IN CURRENT EVIDENCE",
            "trump_administration_action": "EVIDENCE FOUND" if trump_admin else "NONE FOUND IN CURRENT EVIDENCE",
            "trump_personal_disclosure": personal,
            "trump_family_interest": "EVIDENCE FOUND" if family else "NONE FOUND IN CURRENT EVIDENCE",
            "federal_awards": federal,
            "official_checked_at": checked_at,
            "source_note": "Official-source evidence and news context. Political mentions alone do not affect rank-v1.",
        }
