"""Independent recomputation of stored Marketstack receipt integrity, NOT price certification.

No vendor calls and no broker operations. Re-reads compressed observations under
the restricted GEM reader, verifies content and ledger metadata, and persists an
append-only diagnosis under the restricted ingest role. In particular this DOES
NOT prove frozen adjusted-price parity, complete exchange sessions, or action QA.
"""
from __future__ import annotations

import base64
import binascii
from datetime import date, datetime, timezone
from hashlib import sha256
import json
import math
import os
import re
import zlib

import psycopg

from gem_data.gem_public_ingest import EXPERIMENT, write_observation

PREFIX = "gem-price-raw-audit-v1-"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
TICKER = re.compile(r"^[A-Z0-9.\\-]{1,16}$")
MAX_COMPRESSED = 1_000_000
MAX_EXPANDED = 2_000_000


class ReceiptAuditHold(ValueError):
    pass


def _number(row, key, *, zero=False):
    val = row.get(key)
    if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val):
        raise ReceiptAuditHold("BAD_" + key.upper())
    if val < 0 if zero else val <= 0:
        raise ReceiptAuditHold("BAD_" + key.upper())
    return float(val)


def audit_receipt(receipt_id, expected_sha, metadata):
    """Pure bounded verification; never trust reported bar counts or SHA labels."""
    findings = []
    try:
        if not isinstance(receipt_id, str) or not receipt_id.startswith("gem-marketstack-"):
            raise ReceiptAuditHold("INVALID_RECEIPT_ID")
        if not isinstance(metadata, dict) or not isinstance(expected_sha, str):
            raise ReceiptAuditHold("INVALID_RECEIPT_METADATA")
        expected_sha = expected_sha.strip().lower()
        if not HEX64.fullmatch(expected_sha):
            raise ReceiptAuditHold("INVALID_SOURCE_SHA256")
        ticker = metadata.get("ticker")
        if not isinstance(ticker, str) or not TICKER.fullmatch(ticker):
            raise ReceiptAuditHold("INVALID_TICKER")
        encoded = metadata.get("normalized_bars_zlib_base64")
        if not isinstance(encoded, str) or len(encoded) > MAX_COMPRESSED * 2:
            raise ReceiptAuditHold("MISSING_OR_OVERSIZED_BARS")
        packed = base64.b64decode(encoded, validate=True)
        if len(packed) > MAX_COMPRESSED:
            raise ReceiptAuditHold("OVERSIZED_COMPRESSED_BARS")
        decoder = zlib.decompressobj()
        raw = decoder.decompress(packed, MAX_EXPANDED + 1)
        if (len(raw) > MAX_EXPANDED or decoder.unconsumed_tail or
                not decoder.eof or decoder.unused_data):
            raise ReceiptAuditHold("INVALID_COMPRESSED_BARS")
        raw += decoder.flush()
        if len(raw) > MAX_EXPANDED:
            raise ReceiptAuditHold("OVERSIZED_EXPANDED_BARS")
        digest = sha256(raw).hexdigest()
        if digest != expected_sha or digest != metadata.get("normalized_bars_sha256"):
            raise ReceiptAuditHold("BARS_SHA256_MISMATCH")
        bars = json.loads(raw)
        if not isinstance(bars, list) or not 1 <= len(bars) <= 1000:
            raise ReceiptAuditHold("INVALID_BARS_PAYLOAD")
        observed_sessions = set()
        previous = None
        for row in bars:
            if not isinstance(row, dict) or row.get("ticker") != ticker:
                raise ReceiptAuditHold("BAD_BAR_IDENTITY")
            try:
                session = date.fromisoformat(row["session"])
            except (ValueError, TypeError, KeyError):
                raise ReceiptAuditHold("BAD_BAR_SESSION") from None
            if session in observed_sessions or (previous is not None and session <= previous):
                raise ReceiptAuditHold("DUPLICATE_OR_UNSORTED_SESSIONS")
            observed_sessions.add(session)
            previous = session
            op, hi, lo, cl = (_number(row, k) for k in ("open", "high", "low", "close"))
            _number(row, "volume", zero=True)
            _number(row, "vendor_adj_close")
            if hi < max(op, lo, cl) or lo > min(op, hi, cl):
                raise ReceiptAuditHold("INVALID_NOMINAL_OHLC")
            if row.get("split_factor") is not None:
                _number(row, "split_factor")
            if row.get("dividend") is not None:
                _number(row, "dividend", zero=True)
        if str(metadata.get("completed_sessions")) != str(len(bars)):
            raise ReceiptAuditHold("BAR_COUNT_MISMATCH")
        if (metadata.get("first_session") != bars[0]["session"] or
                metadata.get("last_session") != bars[-1]["session"]):
            raise ReceiptAuditHold("SESSION_BOUNDARY_MISMATCH")
        hashes = metadata.get("vendor_page_hashes")
        if not isinstance(hashes, list) or not hashes or any(
                not isinstance(h, str) or not HEX64.fullmatch(h) for h in hashes):
            raise ReceiptAuditHold("MISSING_VENDOR_PAGE_HASHES")
        rejected = metadata.get("rejected_session_count")
        if isinstance(rejected, bool) or not isinstance(rejected, int) or rejected < 0:
            raise ReceiptAuditHold("INVALID_REJECTION_COUNT")
        if rejected != len(metadata.get("rejected_sessions", [])):
            raise ReceiptAuditHold("REJECTION_COUNT_MISMATCH")
        if len(bars) < 127:
            findings.append("INSUFFICIENT_127_SESSIONS")
        if rejected:
            findings.append("VENDOR_REJECTED_ROWS_PRESENT")
        if not findings:
            findings.append("CROSS_PROVIDER_ADJUSTMENT_AND_CALENDAR_QA_PENDING")
        state = ("PARTIAL" if findings == ["CROSS_PROVIDER_ADJUSTMENT_AND_CALENDAR_QA_PENDING"]
                 else "BLOCKED")
        return {"state":state, "ticker":ticker, "bars_recomputed":len(bars),
                "rejected_rows":rejected, "content_sha256":digest,
                "findings":findings, "raw_receipt_integrity_pass":True,
                "independent_price_parity_pass":False,
                "approved_for_trading":False}
    except (ReceiptAuditHold, ValueError, TypeError, UnicodeError, zlib.error, binascii.Error) as exc:
        label = str(exc) if isinstance(exc, ReceiptAuditHold) else "INVALID_RAW_RECEIPT"
        return {"state":"BLOCKED", "ticker":metadata.get("ticker") if isinstance(metadata, dict) else None,
                "bars_recomputed":0,"rejected_rows":None,
                "content_sha256":None,"findings":[label[:90]],
                "raw_receipt_integrity_pass":False,
                "independent_price_parity_pass":False,"approved_for_trading":False}


def audit_batch(*, max_receipts=25):
    if type(max_receipts) is not int or not 1 <= max_receipts <= 50:
        raise ReceiptAuditHold("Batch must contain 1..50 receipts")
    reader = os.getenv("GEM_READONLY_DATABASE_URL", "")
    writer = os.getenv("GEM_INGEST_DATABASE_URL", "")
    if (not reader.startswith("postgresql://gem_web_readonly:") or
            not writer.startswith("postgresql://gem_source_ingest_limited:")):
        raise ReceiptAuditHold("Restricted GEM roles unavailable")
    with psycopg.connect(reader, connect_timeout=6) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SET LOCAL statement_timeout = 15000")
            cur.execute("""
                WITH latest AS (
                    SELECT DISTINCT ON (metadata->>'ticker')
                        receipt_id, metadata->>'ticker' ticker
                    FROM gem_source_receipt
                    WHERE experiment_id=%s AND source_type='prices'
                      AND provider='MARKETSTACK' AND metadata->>'ticker' IS NOT NULL
                    ORDER BY metadata->>'ticker', observed_at DESC, receipt_id DESC
                )
                SELECT latest.receipt_id
                FROM latest
                WHERE NOT EXISTS (
                    SELECT 1 FROM gem_source_probe p WHERE
                        p.experiment_id=%s AND p.probe_id=
                            %s || latest.receipt_id
                )
                ORDER BY latest.ticker LIMIT %s
            """, (EXPERIMENT, EXPERIMENT, PREFIX, max_receipts))
            keys = [x[0] for x in cur.fetchall()]
            rows = []
            if keys:
                cur.execute("""
                    SELECT receipt_id, source_sha256, metadata
                    FROM gem_source_receipt
                    WHERE experiment_id=%s AND receipt_id=ANY(%s)
                """, (EXPERIMENT, keys))
                rows = cur.fetchall()
    now = datetime.now(timezone.utc)
    outcome = {"checked":0, "raw_integrity_pass":0, "requires_resolution":0,
               "price_parity_approved":0, "remaining_estimate":None}
    with psycopg.connect(writer, connect_timeout=6) as conn:
        for receipt_id, digest, metadata in rows:
            result = audit_receipt(receipt_id, str(digest).strip(), metadata)
            audit_json = {"schema":"gem-marketstack-receipt-diagnostic-v1",
                          "original_receipt_id":receipt_id,
                          "source_provider":"MARKETSTACK",
                          "audit_algorithm":"independent-recompute-from-stored-bars-v1",
                          **result}
            audit_hash = sha256(json.dumps(audit_json, sort_keys=True).encode()).hexdigest()
            probe = {
                "probe_id":PREFIX + receipt_id,
                "source_type":"prices","state":result["state"],
                "observed_at":now,"diagnostic_hash":audit_hash,
                "sample_count":result["bars_recomputed"],
                "details":audit_json,
            }
            write_observation(conn, None, probe)
            conn.commit()
            outcome["checked"] += 1
            outcome["raw_integrity_pass"] += int(result["raw_receipt_integrity_pass"])
            outcome["requires_resolution"] += int(result["state"] == "BLOCKED")
    return outcome
