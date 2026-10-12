"""Bounded public-source freshness observations for GEMv1 (NOT source QA).

No DB access, secret access, order routing, trading engine imports, or paid APIs.
A successful source fetch is PARTIAL evidence, never VERIFIED. Artifacts expire;
durable GEM-only storage and independent QA must be added separately.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
from io import StringIO
import json
import os
from pathlib import Path
import re

import httpx

NYSE_URL = "https://www.nyse.com/trade/hours-calendars"
MEMBERS_URL = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/master/data/constituents.csv"
FROZEN_REF = "d59b93d3d9a87d582045b4ae71ff9a6f696a48be"
LIMITS = {"calendar": 2_000_000, "membership": 3_000_000}
NYSE_MARKERS = (
    "Holidays & Trading Hours", "Friday, June 19", "Friday, July 3",
    "Friday, November 27, 2026", "Thursday, December 24, 2026",
    "Core Trading Session",
)
SOURCES = ("calendar", "membership", "sec", "prices", "actions", "benchmark")


class BadSource(RuntimeError):
    pass


class _PageText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def fetch_bounded(client: httpx.Client, url: str, *, limit: int, media_type: str) -> bytes:
    """Exactly pinned first-party/secondary URL, never follow redirects."""
    if url not in (NYSE_URL, MEMBERS_URL):
        raise BadSource("Unapproved public source URL")
    try:
        with client.stream("GET", url, follow_redirects=False) as response:
            if response.status_code != 200:
                raise BadSource("Source HTTP status not OK")
            ctype = response.headers.get("content-type", "").lower()
            if media_type not in ctype:
                raise BadSource("Unexpected source content type")
            parts = []
            size = 0
            for part in response.iter_bytes():
                size += len(part)
                if size > limit:
                    raise BadSource("Source response exceeds size bound")
                parts.append(part)
            raw = b"".join(parts)
    except httpx.HTTPError:
        raise BadSource("Source network failure") from None
    if not raw:
        raise BadSource("Source response was empty")
    return raw


def check_nyse(raw: bytes) -> dict:
    p = _PageText()
    p.feed(raw.decode("utf-8", errors="replace"))
    content = " ".join(" ".join(p.parts).split())
    missing = [item for item in NYSE_MARKERS if item not in content]
    if missing:
        raise BadSource("NYSE 2026 publication markers missing")
    return {"publication_year": 2026, "published_markers": len(NYSE_MARKERS),
            "official_extraordinary_closures_checked": False}


def check_secondary_members(raw: bytes) -> dict:
    try:
        reader = csv.DictReader(StringIO(raw.decode("utf-8-sig")))
        if not reader.fieldnames or not {"Symbol", "CIK"} <= set(reader.fieldnames):
            raise BadSource("Secondary membership identity columns missing")
        rows = list(reader)
    except (UnicodeError, csv.Error):
        raise BadSource("Secondary membership CSV malformed") from None
    if not 480 <= len(rows) <= 600:
        raise BadSource("Implausible secondary membership row count")
    ids = [(r.get("Symbol") or "").strip() for r in rows]
    ciks = [(r.get("CIK") or "").strip() for r in rows]
    if (len(set(ids)) != len(ids)
            or any(not re.fullmatch(r"[A-Za-z0-9.\-]{1,16}", s) for s in ids)
            or any(not re.fullmatch(r"[0-9]{1,10}", c) for c in ciks)):
        raise BadSource("Secondary membership CIK/share-class identifiers invalid")
    return {"security_lines": len(rows), "issuer_cik_count": len(set(ciks)),
            "official_effective_dated_membership": False}


def capture_sources(*, client: httpx.Client, observed: datetime) -> tuple[dict, dict[str, bytes]]:
    if not isinstance(observed, datetime) or observed.tzinfo is None:
        raise ValueError("Required aware observed timestamp")
    seen = observed.astimezone(timezone.utc)
    result = {
        "schema": "gem-public-source-freshness-v1",
        "strategy_ref": FROZEN_REF,
        "observed_at": seen.isoformat(),
        "trading_authorized": False,
        "independently_certified_count": 0,
        "sources": {},
    }
    raw_map: dict[str, bytes] = {}
    targets = (
        ("calendar", NYSE_URL, "text/html", "nyse-2026-source.html", check_nyse),
        ("membership", MEMBERS_URL, "text/plain", "secondary-sp500-current.csv", check_secondary_members),
    )
    for source, url, media_type, filename, check in targets:
        try:
            raw = fetch_bounded(client, url, limit=LIMITS[source], media_type=media_type)
            check_summary = check(raw)
            if source == "calendar" and seen.year != 2026:
                raise BadSource("2026 exchange schedule is stale for new calendar year")
            result["sources"][source] = {
                "status": "PARTIAL", "observation_fresh": True,
                "certified": False, "source_url": url,
                "retrieved_at": seen.isoformat(), "bytes": len(raw),
                "raw_sha256": sha256(raw).hexdigest(), **check_summary,
            }
            raw_map[filename] = raw
        except BadSource as exc:
            result["sources"][source] = {
                "status": "BLOCKED", "observation_fresh": False,
                "certified": False, "reason": str(exc),
            }
    blocks = {
        "sec": "Original 10-Q fact collector requires SEC_USER_AGENT and source-context review",
        "prices": "Marketstack cross-exchange 2026-06 null close data; account-wide credit cap not installed",
        "actions": "Full-universe actions feed and issuer reconciliation not connected",
        "benchmark": "SPY total-return actions/dividends not reconciled",
    }
    for source, reason in blocks.items():
        result["sources"][source] = {
            "status": "BLOCKED", "observation_fresh": False,
            "certified": False, "reason": reason,
        }
    return result, raw_map


def run_capture(output_dir: str) -> dict:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    if any(directory.iterdir()):
        raise ValueError("Source evidence directory must be empty")
    with httpx.Client(timeout=20.0, follow_redirects=False,
                      headers={"User-Agent": "GEMv1 research public source audit"}) as client:
        status, raw = capture_sources(client=client, observed=datetime.now(timezone.utc))
    for filename, body in raw.items():
        (directory / filename).write_bytes(body)
    (directory / "freshness.json").write_text(
        json.dumps(status, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: {"status": v["status"], "certified": v["certified"]}
                      for k, v in status["sources"].items()}, sort_keys=True))
    return status


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    status = run_capture(args.output_dir)
    if any(status["sources"][s]["status"] != "PARTIAL" for s in ("calendar", "membership")):
        raise SystemExit("One or more public-source checks failed; see freshness.json")
