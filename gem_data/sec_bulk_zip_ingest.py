"""GEM-only SEC nightly ZIP member ingest using strict HTTP byte ranges.

Never download the multi-GB SEC archive into RAM or ephemeral service disk.
Only read original per-CIK members from the ZIP via validated HTTP 206
ranges; record raw selected member bytes and archive provenance. If SEC does
not support ranges the collector HOLDS, it never falls back to a multi-GB GET.
Discovery only; DOES NOT independently certify six quarter facts or ranking.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from hashlib import sha256
import io
import json
import os
import re
import time
import zipfile
import zlib

import httpx
import psycopg

from gem_data.gem_public_ingest import (
    EXPERIMENT, SECONDARY, _verify, write_observation,
)
from gem_data.sec_original_collector import validate_sec_user_agent

ARCHIVES = {
    "submissions": "https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip",
    "companyfacts": "https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip",
}
FINANCIAL_CANDIDATES = {
    "revenue": ("RevenueFromContractWithCustomerExcludingAssessedTax",
                "RevenueFromContractWithCustomerIncludingAssessedTax",
                "Revenues", "SalesRevenueNet"),
    "operating_income": ("OperatingIncomeLoss",),
    "net_income": ("NetIncomeLoss", "ProfitLoss"),
}
MAX_ARCHIVE_BYTES = 5_000_000_000
MAX_RANGE_BYTES = 4_000_000
MAX_MEMBER_BYTES = 12_000_000
MAX_MEMBER_COMPRESSED = 650_000
MAX_BATCH_COMPRESSED = 8_000_000
MAX_BATCH_CIKS = 75


class BulkSourceHold(RuntimeError):
    """Blocked, never convert to a VERIFIED data source."""


class SECByteRangeFile(io.RawIOBase):
    """Bounded read/seek wrapper; zipfile sees only requested HTTP 206 bytes."""

    def __init__(self, client: httpx.Client, url: str,
                 *, max_requests: int = 2000, min_delay: float = 0.15):
        if url not in ARCHIVES.values():
            raise BulkSourceHold("ZIP archive URL not allowlisted")
        self.client, self.url, self.max_requests = client, url, max_requests
        self.min_delay, self.last_request, self.calls = min_delay, 0.0, 0
        self._pos, self._cache_start, self._cache = 0, -1, b""
        try:
            response = client.head(url, follow_redirects=False)
        except httpx.HTTPError as exc:
            raise BulkSourceHold("SEC ZIP header request failed") from exc
        if response.status_code != 200:
            raise BulkSourceHold("SEC ZIP HEAD not available")
        try:
            self.length = int(response.headers.get("content-length", "0"))
        except ValueError as exc:
            raise BulkSourceHold("SEC ZIP content length invalid") from exc
        if not 22 <= self.length <= MAX_ARCHIVE_BYTES:
            raise BulkSourceHold("SEC ZIP size outside safe limits")
        self.etag = response.headers.get("etag", "")[:128]
        self.modified = response.headers.get("last-modified", "")[:128]
        self.archive_id = sha256(
            f"{url}|{self.length}|{self.etag}|{self.modified}".encode()
        ).hexdigest()[:16]

    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self._pos

    def seek(self, offset, whence=io.SEEK_SET):
        new = offset if whence == io.SEEK_SET else (
            self._pos + offset if whence == io.SEEK_CUR
            else self.length + offset if whence == io.SEEK_END else -1)
        if not 0 <= new <= self.length:
            raise BulkSourceHold("Unsafe SEC ZIP seek")
        self._pos = new
        return new

    def _request(self, start: int, end: int) -> bytes:
        if start < 0 or end < start or end >= self.length or end-start+1 > MAX_RANGE_BYTES:
            raise BulkSourceHold("Unsafe SEC ZIP range")
        if self.calls >= self.max_requests:
            raise BulkSourceHold("SEC ZIP request budget reached")
        wait = self.min_delay - (time.monotonic() - self.last_request)
        if wait > 0:
            time.sleep(wait)
        self.calls += 1
        self.last_request = time.monotonic()
        try:
            with self.client.stream("GET", self.url, headers={
                "Range": f"bytes={start}-{end}",
                "Accept-Encoding": "identity",
            }, follow_redirects=False) as response:
                # Check 206 BEFORE reading response body. A 200 is a possible
                # multi-gigabyte full archive: never call client.get() here.
                if response.status_code != 206:
                    raise BulkSourceHold("SEC ZIP HTTP byte ranges unavailable")
                expected = f"bytes {start}-{end}/{self.length}"
                if response.headers.get("content-range", "").lower() != expected:
                    raise BulkSourceHold("SEC ZIP byte range changed")
                parts, total = [], 0
                maximum = end-start+1
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > maximum:
                        raise BulkSourceHold("SEC ZIP body exceeded requested range")
                    parts.append(chunk)
        except httpx.HTTPError as exc:
            raise BulkSourceHold("SEC ZIP byte-range request failed") from exc
        if total != maximum:
            raise BulkSourceHold("SEC ZIP partial range length mismatch")
        return b"".join(parts)

    def read(self, size=-1):
        remaining = self.length - self._pos
        if size is None or size < 0:
            size = remaining
        size = min(size, remaining)
        if size == 0: return b""
        if size > MAX_RANGE_BYTES:
            raise BulkSourceHold("SEC ZIP oversized read")
        pos = self._pos
        cache_end = self._cache_start + len(self._cache)
        if self._cache_start <= pos and pos + size <= cache_end:
            out = self._cache[pos-self._cache_start:pos-self._cache_start+size]
        else:
            amount = min(self.length-pos, max(size, 262144), MAX_RANGE_BYTES)
            out_bytes = self._request(pos, pos+amount-1)
            self._cache_start, self._cache = pos, out_bytes
            out = out_bytes[:size]
        self._pos += len(out)
        return out


def parse_selected_member(kind: str, cik: str, raw: bytes) -> dict:
    try:
        d = json.loads(raw)
    except (UnicodeError, ValueError) as exc:
        raise BulkSourceHold("Malformed original SEC JSON member") from exc
    if not isinstance(d, dict) or str(d.get("cik", "")).zfill(10) != cik:
        raise BulkSourceHold("Original SEC bulk CIK identity mismatch")
    if kind == "submissions":
        recent = ((d.get("filings") or {}).get("recent") or {})
        cols = [recent.get(s) for s in ("form", "accessionNumber", "filingDate", "acceptanceDateTime")]
        if any(not isinstance(c, list) for c in cols) or len({len(c) for c in cols}) != 1:
            raise BulkSourceHold("Malformed original SEC submission accession arrays")
        return {"filing_rows": len(cols[0]),
                "quarter_filing_refs": sum(1 for s in cols[0] if s in ("10-Q", "10-Q/A")),
                "original_10q_xbrl_values_verified": False}
    if kind != "companyfacts":
        raise BulkSourceHold("Unknown SEC original bulk member type")
    facts = d.get("facts")
    if not isinstance(facts, dict):
        raise BulkSourceHold("Original SEC companyfacts missing facts")
    us = facts.get("us-gaap") or {}
    if not isinstance(us, dict):
        raise BulkSourceHold("Malformed SEC US GAAP taxonomy")
    available = {
        metric: [tag for tag in tags if isinstance(us.get(tag), dict)
                 and isinstance(us[tag].get("units"), dict)]
        for metric, tags in FINANCIAL_CANDIDATES.items()
    }
    return {"available_us_gaap_fact_concepts": available,
            "original_per_filing_xbrl_contexts_verified": False,
            "period_cutoff_qa_verified": False,
            "six_financial_fact_values_certified": False}


def _existing_ids(conn, kind: str, archive_id: str) -> set[str]:
    # Collector has only receipt_id column SELECT, not full source-payload read.
    prefix = f"gem-sec-zip-{kind}-{archive_id}-"
    with conn.cursor() as cur:
        cur.execute(
            "SELECT receipt_id FROM gem_source_receipt WHERE receipt_id LIKE %s",
            (prefix+"%",))
        return {row[0] for row in cur.fetchall()}


def capture_bulk_batch(*, client: httpx.Client | None = None,
                       max_ciks: int = 25) -> dict:
    if not isinstance(max_ciks, int) or not 1 <= max_ciks <= MAX_BATCH_CIKS:
        raise BulkSourceHold("SEC bulk CIK batch outside safe bounds")
    url = os.getenv("GEM_INGEST_DATABASE_URL", "")
    if not url.startswith("postgresql://gem_source_ingest_limited:"):
        raise BulkSourceHold("GEM-only restricted ingest credential unavailable")
    user_agent = validate_sec_user_agent(os.getenv("SEC_USER_AGENT", ""))
    supplied_client = client is not None
    if not supplied_client:
        client = httpx.Client(timeout=httpx.Timeout(40, connect=10), headers={
            "User-Agent": user_agent,
            "Accept": "application/json,application/zip,*/*",
        }, follow_redirects=False)
    now = datetime.now(timezone.utc)
    result = {"attempted_ciks": 0, "new_members": 0, "blocked": 0,
              "kind": {}, "certified": False}
    try:
        with client.stream("GET", SECONDARY, follow_redirects=False) as member_resp:
            if member_resp.status_code != 200:
                raise BulkSourceHold("Current secondary identity list unavailable")
            chunks, count = [], 0
            for chunk in member_resp.iter_bytes():
                count += len(chunk)
                if count > 500000:
                    raise BulkSourceHold("Secondary identity list exceeds byte budget")
                chunks.append(chunk)
            manifest = b"".join(chunks)
        _verify("membership", manifest)
        import csv
        from io import StringIO
        rows = list(csv.DictReader(StringIO(manifest.decode("utf-8-sig"))))
        ciks = sorted({str(row["CIK"]).zfill(10) for row in rows})
        if not 450 <= len(ciks) <= 550:
            raise BulkSourceHold("Current secondary issuer count outside contract")
        result["discovery_issuers"] = len(ciks)
        with psycopg.connect(url, connect_timeout=6) as conn:
            for kind, archive_uri in ARCHIVES.items():
                stream = SECByteRangeFile(client, archive_uri)
                # Empty or stale server modification metadata does not count
                # as cryptographic proof of archive identity.
                existing = _existing_ids(conn, kind, stream.archive_id)
                pending = [c for c in ciks if not any(
                    id_.startswith(f"gem-sec-zip-{kind}-{stream.archive_id}-{c}-")
                    for id_ in existing)]
                result["kind"][kind] = {
                    "archive_size": stream.length,
                    "archive_id": stream.archive_id,
                    "already_collected": len(ciks) - len(pending),
                    "remaining_before": len(pending),
                }
                count, spent = 0, 0
                with zipfile.ZipFile(stream, "r", allowZip64=True) as archive:
                    for cik in pending[:max_ciks]:
                        member_name = f"CIK{cik}.json"
                        result["attempted_ciks"] += 1
                        try:
                            info = archive.getinfo(member_name)
                            if (info.is_dir() or info.flag_bits & 1
                                    or info.file_size > MAX_MEMBER_BYTES):
                                raise BulkSourceHold("Original SEC member rejected by size/encryption")
                            with archive.open(info, "r") as f:
                                raw = f.read(MAX_MEMBER_BYTES+1)
                            if len(raw) != info.file_size or len(raw) > MAX_MEMBER_BYTES:
                                raise BulkSourceHold("Original SEC member size mismatch")
                            metrics = parse_selected_member(kind, cik, raw)
                            compressed = zlib.compress(raw, 9)
                            if (len(compressed) > MAX_MEMBER_COMPRESSED
                                    or spent + len(compressed) > MAX_BATCH_COMPRESSED):
                                raise BulkSourceHold("SEC bulk per-member/batch evidence budget reached")
                            spent += len(compressed)
                            sha = sha256(raw).hexdigest()
                            rid = f"gem-sec-zip-{kind}-{stream.archive_id}-{cik}-{sha[:12]}"
                            receipt = {
                                "receipt_id": rid, "provider": f"SEC_ZIP_{kind.upper()}",
                                "observed_at": now,
                                "source_uri": archive_uri + "#" + member_name,
                                "source_sha256": sha, "coverage_status": "UNKNOWN",
                                "metadata": {
                                    "zip_member_name": member_name,
                                    "archive_url": archive_uri,
                                    "archive_content_length": stream.length,
                                    "archive_http_etag": stream.etag,
                                    "archive_http_last_modified": stream.modified,
                                    "archive_identity_not_full_archive_sha": stream.archive_id,
                                    "member_original_sha256": sha,
                                    "member_uncompressed_bytes": len(raw),
                                    "source_raw_zlib_base64": base64.b64encode(compressed).decode("ascii"),
                                    "original_member_metrics": metrics,
                                    "point_in_time_membership_certified": False,
                                    "original_six_fact_values_certified": False,
                                },
                            }
                            state = "PARTIAL"
                            count += 1
                        except (KeyError, BulkSourceHold, zipfile.BadZipFile, OSError) as exc:
                            receipt, state = None, "BLOCKED"
                            sha = sha256((kind+cik+type(exc).__name__).encode()).hexdigest()
                            result["blocked"] += 1
                        probe = {
                            "probe_id": f"gem-sec-bulk-{kind}-{stream.archive_id}-{cik}-{sha[:12]}",
                            "source_type": "sec", "state": state,
                            "observed_at": now, "diagnostic_hash": sha,
                            "sample_count": int(receipt is not None),
                            "details": {"source": archive_uri, "scope": f"{kind} member {cik}",
                                        "certified": False, "trading_authorized": False,
                                        "original_full_xbrl_verified": False,
                                        "proof": "Bulk original member captured; original accession XBRL independent QA outstanding"},
                        }
                        write_observation(conn, receipt, probe)
                        conn.commit()
                result["new_members"] += count
                result["kind"][kind]["new_members"] = count
                result["kind"][kind]["remaining_after_estimate"] = len(pending)-count
                result["kind"][kind]["range_http_calls"] = stream.calls
        return result
    finally:
        if not supplied_client:
            client.close()
