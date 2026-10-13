"""Isolated GEM-only public evidence collector, no signals/orders/paid market APIs.

One scheduled source acquisition reads official NYSE hours and secondary S&P
membership; persist byte-exact compressed evidence in existing GEM-only
Neon receipt metadata with a dedicated INSERT-only role. NOT CERTIFICATION.
"""
from __future__ import annotations

import base64
import csv
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from html.parser import HTMLParser
from io import StringIO
import json
import os
import re
import zlib
from io import BytesIO

import httpx
from pypdf import PdfReader
from gem_data.wiki_membership import URL as WIKIPEDIA, parse_wikipedia_membership, compare_secondary_membership, MembershipHold
import psycopg

EXPERIMENT = "gem-v1-forward-2026-10"
NYSE = "https://www.nyse.com/trade/hours-calendars"
SECONDARY = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/master/data/constituents.csv"
SPY_DISTRIBUTION_SCHEDULE = "https://www.ssga.com/library-content/products/fund-data/etfs/us/distribution/SPDR_Dividend_Distribution_Schedule.pdf"
TARGETS = {"calendar": (NYSE, "text/html", 250000),
           "membership": (SECONDARY, "text/plain", 500000),
           "benchmark": (SPY_DISTRIBUTION_SCHEDULE, "application/pdf", 1000000),
           "membership_wikipedia": (WIKIPEDIA, "text/html", 3000000)}
MARKERS = ("Holidays & Trading Hours", "Core Trading Session",
           "Friday, June 19", "Friday, July 3",
           "Friday, November 27, 2026", "Thursday, December 24, 2026")


class InvalidEvidence(ValueError):
    pass


class _VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.items.append(data)


def _verify(source: str, raw: bytes) -> dict:
    if source == "calendar":
        parser = _VisibleText()
        parser.feed(raw.decode("utf-8", errors="replace"))
        body = " ".join(" ".join(parser.items).split())
        if any(value not in body for value in MARKERS):
            raise InvalidEvidence("published 2026 NYSE markers absent")
        return {"published_calendar_year": 2026, "markers": len(MARKERS),
                "completed_session_independently_verified": False,
                "emergency_market_status_verified": False}
    if source == "membership":
        try:
            reader = csv.DictReader(StringIO(raw.decode("utf-8-sig")))
            if not reader.fieldnames or not {"Symbol", "CIK"} <= set(reader.fieldnames):
                raise InvalidEvidence("secondary membership identity fields absent")
            rows = list(reader)
        except (UnicodeError, csv.Error) as exc:
            raise InvalidEvidence("secondary member CSV invalid") from exc
        symbols = [str(row.get("Symbol", "")).strip() for row in rows]
        ciks = [str(row.get("CIK", "")).strip() for row in rows]
        if (not 480 <= len(rows) <= 600 or len(set(symbols)) != len(symbols)
                or any(not re.fullmatch(r"[A-Za-z0-9.-]{1,16}", s) for s in symbols)
                or any(not re.fullmatch(r"[0-9]{1,10}", c) for c in ciks)):
            raise InvalidEvidence("secondary membership identities inconsistent")
        return {"security_lines": len(rows), "unique_issuers": len(set(ciks)),
                "official_point_in_time_membership": False}
    if source == "membership_wikipedia":
        snapshot = parse_wikipedia_membership(raw)
        return {"security_lines": snapshot["securities"],
                "unique_issuers": snapshot["unique_ciks"],
                "cik_normalized": True,
                "official_point_in_time_membership": False}
    if source == "benchmark":
        if not raw.startswith(b"%PDF-") or b"%%EOF" not in raw[-1024:]:
            raise InvalidEvidence("official SPY distribution schedule is not PDF")
        try:
            pdf = PdfReader(BytesIO(raw), strict=True)
            if not 1 <= len(pdf.pages) <= 20:
                raise ValueError("Unexpected SPY source page count")
            lines = " ".join((page.extract_text() or "") for page in pdf.pages)
        except Exception as exc:
            raise InvalidEvidence("official SPY source PDF unreadable") from exc
        if "SPY" not in lines or "Calendar Year 2026" not in lines or "Dividend Distribution Schedule" not in lines:
            raise InvalidEvidence("official SPY distribution schedule identity absent")
        return {"source_type": "SPY_PROVIDER_DIVIDEND_DATE_SCHEDULE",
                "published_year": 2026,
                "distribution_amounts_verified": False,
                "spy_total_return_certified": False}
    raise InvalidEvidence("unknown GEM source")


def fetch_one(client: httpx.Client, source: str) -> tuple[bytes, dict]:
    if source not in TARGETS:
        raise InvalidEvidence("source not allowlisted")
    url, media_type, limit = TARGETS[source]
    try:
        with client.stream("GET", url, follow_redirects=(source == "membership_wikipedia")) as response:
            if source == "membership_wikipedia" and (
                response.url.scheme != "https" or response.url.host != "en.wikipedia.org"):
                raise InvalidEvidence("Wikipedia source host changed")
            if response.status_code != 200:
                raise InvalidEvidence("source HTTP " + str(response.status_code))
            content_type = response.headers.get("content-type", "").lower()
            if media_type not in content_type:
                raise InvalidEvidence("source media type changed")
            parts, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > limit:
                    raise InvalidEvidence("source response exceeds limit")
                parts.append(chunk)
            raw = b"".join(parts)
    except httpx.HTTPError as exc:
        raise InvalidEvidence("source network error") from exc
    if not raw:
        raise InvalidEvidence("empty source")
    return raw, _verify(source, raw)


def evidence_records(source: str, observed: datetime, raw: bytes | None,
                     metrics: dict | None, reason: str | None = None) -> tuple[dict | None, dict]:
    if observed.tzinfo is None:
        raise ValueError("Observation must have an explicit timezone")
    observed = observed.astimezone(timezone.utc)
    key = observed.strftime("%Y%m%d")
    uri = TARGETS[source][0]
    if raw is None:
        digest = sha256((source + ":" + (reason or "unavailable")).encode()).hexdigest()
        receipt = None
        state = "BLOCKED"
        note = reason or "source unavailable"
        scope = "No validated public response"
        sample = 0
    else:
        if metrics is None:
            raise ValueError("Validated metrics required")
        digest = sha256(raw).hexdigest()
        state = "PARTIAL"
        scope = "Raw response received; official certification and complete-universe QA outstanding"
        note = (
            "Published exchange schedule; emergencies and completed sessions not independently certified"
            if source == "calendar" else
            "Secondary current membership only; authoritative effective dates missing"
            if source in ("membership", "membership_wikipedia") else
            "Provider SPY ex/pay-date schedule only; actual cash amounts, price bars and total returns missing"
        )
        sample = 1
        # Byte-exact raw source survives in existing isolated DB without new
        # schema/migration or a temporary expiring GitHub artifact.
        receipt = {
            "receipt_id": f"gem-{source}-{key}-{digest[:16]}",
            "provider": ("NYSE_OFFICIAL" if source == "calendar" else
                        "SECONDARY_GITHUB_SP500" if source == "membership" else
                        "WIKIPEDIA_SP500_CIK_CURRENT" if source == "membership_wikipedia" else
                        "STATE_STREET_OFFICIAL_SPY_SCHEDULE"),
            "observed_at": observed,
            "source_uri": uri,
            "source_sha256": digest,
            "coverage_status": "UNKNOWN",
            "metadata": {
                "source_raw_zlib_base64": base64.b64encode(zlib.compress(raw, 9)).decode(),
                "source_raw_length": len(raw),
                "source_raw_sha256": digest,
                "metrics": metrics,
                "certified": False,
                "source_only_not_signal": True,
            },
        }
    probe = {
        "probe_id": f"gem-{source}-probe-{key}-{digest[:16]}",
        "source_type": "membership" if source == "membership_wikipedia" else source,
        "state": state,
        "observed_at": observed,
        "diagnostic_hash": digest,
        "sample_count": sample,
        "details": {"source": uri, "scope": scope, "proof": note,
                    "trading_authorized": False, "certified": False},
    }
    return receipt, probe


def write_observation(conn, receipt: dict | None, probe: dict) -> None:
    """Only INSERT; never update, delete, or touch DM tables."""
    with conn.cursor() as cur:
        # The insert-only role has no UPDATE, DELETE or broker permissions.
        cur.execute("SET TRANSACTION READ WRITE")
        cur.execute("SET LOCAL statement_timeout = 7000")
        if receipt:
            cur.execute("""
                INSERT INTO gem_source_receipt
                    (receipt_id,experiment_id,source_type,provider,observed_at,
                     source_sha256,coverage_status,source_uri,metadata)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                ON CONFLICT (receipt_id) DO NOTHING
            """, (receipt["receipt_id"], EXPERIMENT, probe["source_type"],
                  receipt["provider"], receipt["observed_at"],
                  receipt["source_sha256"], receipt["coverage_status"],
                  receipt["source_uri"], json.dumps(receipt["metadata"])))
        cur.execute("""
            INSERT INTO gem_source_probe
                (probe_id,experiment_id,source_type,state,observed_at,
                 diagnostic_hash,sample_count,approved_for_trading,details)
            VALUES (%s,%s,%s,%s,%s,%s,%s,FALSE,%s::jsonb)
            ON CONFLICT (probe_id) DO NOTHING
        """, (probe["probe_id"], EXPERIMENT, probe["source_type"],
              probe["state"], probe["observed_at"], probe["diagnostic_hash"],
              probe["sample_count"], json.dumps(probe["details"])))


def capture_and_persist(*, observed: datetime | None = None) -> dict:
    """Synchronous bounded worker invoked only from GEM's opt-in scheduler."""
    url = os.environ.get("GEM_INGEST_DATABASE_URL", "")
    if not url or not url.startswith("postgresql://gem_source_ingest_limited:"):
        raise RuntimeError("GEM source collection disabled: restricted writer URL unavailable")
    observed = observed or datetime.now(timezone.utc)
    result = {}
    membership_raw = None
    # Wikimedia and SEC expect a genuine operator contact in automated
    # User-Agent headers. Reuse an operator-configured agent if available;
    # never invent an email address or claim a source was verified on HTTP 403.
    agent = (os.getenv("GEM_PUBLIC_USER_AGENT") or os.getenv("SEC_USER_AGENT")
             or "GEMv1 read-only public source research").strip()
    with httpx.Client(timeout=18.0, follow_redirects=False, headers={
        "User-Agent": agent
    }) as client:
        for source in TARGETS:
            try:
                raw, metrics = fetch_one(client, source)
                if source in ("calendar", "benchmark") and observed.year != 2026:
                    raise InvalidEvidence("2026 published calendar requires year rollover")
                receipt, probe = evidence_records(source, observed, raw, metrics)
                if source == "membership":
                    membership_raw = raw
                if source == "membership_wikipedia" and membership_raw is not None:
                    comparison = compare_secondary_membership(
                        parse_wikipedia_membership(raw), membership_raw)
                    metrics["secondary_comparison"] = comparison
            except (InvalidEvidence, MembershipHold) as exc:
                receipt, probe = evidence_records(
                    source, observed, None, None, reason=str(exc))
            # Isolated per-source transaction: a bad response never becomes
            # a success record; a failed insert must raise and stay visible.
            with psycopg.connect(url, connect_timeout=6) as conn:
                write_observation(conn, receipt, probe)
            result[source] = probe["state"]
    # SEC remains independently gated until the user registers a genuine
    # organizational contact identity. No placeholder agent or unauthenticated
    # SEC API request can be emitted by this application.
    if os.getenv("GEM_SEC_COLLECTION_ENABLED") == "yes":
        from gem_data.sec_daily_discovery import probe_batch, store_sec_discovery
        if membership_raw is None:
            raise RuntimeError("SEC scan held: current secondary CIK discovery missing")
        ua = os.getenv("SEC_USER_AGENT", "")
        evidence, summary = probe_batch(
            membership_raw, observed, ua,
            pilot_limit=int(os.getenv("GEM_SEC_PILOT_LIMIT", "3")),
        )
        with psycopg.connect(url, connect_timeout=6) as conn:
            store_sec_discovery(conn, evidence)
        result["sec"] = "BLOCKED" if summary["ciks_failed"] else "PARTIAL"
    return result


def next_daily_run(now: datetime) -> datetime:
    """23:45 UTC every calendar day after NYSE core close in both DST seasons."""
    if now.tzinfo is None:
        raise ValueError("Need aware UTC clock")
    current = now.astimezone(timezone.utc)
    tick = current.replace(hour=23, minute=45, second=0, microsecond=0)
    if tick <= current:
        tick += timedelta(days=1)
    return tick
