"""Read-only independent GEM source receipt integrity verifier.

No source collection, database writes, trading or dashboard certification.
Runs with a read-only database credential and fails closed.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import zlib

import psycopg

EXPERIMENT = "gem-v1-forward-2026-10"
MAX_ORIGINAL_BYTES = 12_000_000
MAX_ENCODED_BYTES = 18_000_000
SEC_KINDS = {"SEC_ZIP_COMPANYFACTS", "SEC_ZIP_SUBMISSIONS"}


def verify_receipt(receipt: dict) -> dict:
    """Recompute SHA-256 from stored original bytes, independently of collector."""
    provider = receipt["provider"]
    metadata = receipt["metadata"]
    rid = receipt["receipt_id"]
    result = {"receipt_id": rid, "provider": provider, "status": "FAIL", "checks": {}}
    try:
        encoded = metadata["source_raw_zlib_base64"]
        if not isinstance(encoded, str) or len(encoded) > MAX_ENCODED_BYTES:
            raise ValueError("encoded size limit")
        compressed = base64.b64decode(encoded, validate=True)
        inflater = zlib.decompressobj()
        original = inflater.decompress(compressed, MAX_ORIGINAL_BYTES + 1)
        if len(original) > MAX_ORIGINAL_BYTES or inflater.unconsumed_tail:
            raise ValueError("original size limit")
        original += inflater.flush(MAX_ORIGINAL_BYTES + 1 - len(original))
        if len(original) > MAX_ORIGINAL_BYTES or not inflater.eof or inflater.unused_data:
            raise ValueError("compressed payload invalid")
        digest = hashlib.sha256(original).hexdigest()
        if digest != receipt["source_sha256"] or digest != metadata.get("member_original_sha256", digest):
            raise ValueError("original sha mismatch")
        if len(original) != int(metadata.get("member_uncompressed_bytes", -1)):
            raise ValueError("original byte count mismatch")
        if provider in SEC_KINDS:
            member = metadata.get("zip_member_name", "")
            match = re.search(r"CIK(\d{10})\.json$", member)
            if not match:
                raise ValueError("member name invalid")
            payload = json.loads(original)
            if not isinstance(payload, dict) or str(payload.get("cik", "")).zfill(10) != match.group(1):
                raise ValueError("CIK mismatch")
            result["checks"]["cik"] = match.group(1)
        result["checks"]["sha256"] = digest
        result["checks"]["original_bytes"] = len(original)
        result["status"] = "INTEGRITY_PASS"
    except (KeyError, TypeError, ValueError, UnicodeError, zlib.error, OverflowError) as exc:
        result["checks"]["error"] = type(exc).__name__
    return result


def audit_batch(limit: int = 25) -> dict:
    if not 1 <= limit <= 25:
        raise ValueError("batch limit must be 1..25")
    url = os.environ.get("GEM_CERT_READONLY_DATABASE_URL", "")
    if not url.startswith("postgresql://"):
        raise RuntimeError("Dedicated read-only GEM credential required")
    with psycopg.connect(url, connect_timeout=6) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SET LOCAL statement_timeout = 15000")
            cur.execute(
                """SELECT receipt_id, provider, source_sha256, metadata
                   FROM gem_source_receipt
                   WHERE experiment_id=%s AND provider=ANY(%s)
                   ORDER BY collected_at, receipt_id LIMIT %s""",
                (EXPERIMENT, list(SEC_KINDS), limit),
            )
            keys = ("receipt_id", "provider", "source_sha256", "metadata")
            checks = [verify_receipt(dict(zip(keys, row))) for row in cur.fetchall()]
    return {
        "checked": len(checks),
        "integrity_pass": sum(x["status"] == "INTEGRITY_PASS" for x in checks),
        "failed": sum(x["status"] != "INTEGRITY_PASS" for x in checks),
        "results": checks,
        "financial_facts_certified": False,
        "dashboard_publication_authorized": False,
    }


if __name__ == "__main__":
    print(json.dumps(audit_batch()))
