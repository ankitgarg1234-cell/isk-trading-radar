"""Bounded, append-only GEM SEC receipt integrity auditor. No trading authority."""
from __future__ import annotations

import hashlib
import inspect
import json
import os
import re

import psycopg
from psycopg.types.json import Jsonb
from gem_data.gem_independent_certification import EXPERIMENT, SEC_KINDS, verify_receipt

MAX_BATCH = 10
QA_IDENTITY = "gem-independent-sec-worker-v1"
MEMBER_PATTERN = re.compile(r"CIK([0-9]{10})[.]json")


def check_audit_permissions() -> dict:
    url = os.getenv("GEM_CERT_AUDIT_DATABASE_URL", "")
    if not url.startswith(("postgresql://", "postgres://")):
        return {"ready": False, "reason": "AUDIT_CREDENTIAL_MISSING"}
    with psycopg.connect(url, connect_timeout=6) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SET LOCAL statement_timeout = 5000")
            cur.execute("""SELECT
                has_table_privilege(current_user, 'gem_source_receipt', 'SELECT'),
                has_table_privilege(current_user, 'gem_sec_independent_receipt_audit', 'SELECT'),
                has_table_privilege(current_user, 'gem_sec_independent_receipt_audit', 'INSERT')""")
            source_read, audit_read, audit_insert = cur.fetchone()
    return {"ready": bool(source_read and audit_read and audit_insert),
            "source_read": bool(source_read), "audit_read": bool(audit_read),
            "audit_insert": bool(audit_insert)}


def process_pending(limit: int = MAX_BATCH) -> dict:
    if not isinstance(limit, int) or not 1 <= limit <= MAX_BATCH:
        raise ValueError("batch limit must be 1..10")
    url = os.getenv("GEM_CERT_AUDIT_DATABASE_URL", "")
    if not url.startswith(("postgresql://", "postgres://")):
        raise RuntimeError("Dedicated audit database credential required")
    code_hash = hashlib.sha256(inspect.getsource(verify_receipt).encode()).hexdigest()
    counts = {"audited": 0, "integrity_pass": 0, "integrity_fail": 0}
    with psycopg.connect(url, connect_timeout=6) as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout = 30000")
            cur.execute(
                """SELECT r.receipt_id, r.provider, r.source_sha256, r.metadata
                   FROM gem_source_receipt r
                   WHERE r.experiment_id=%s AND r.provider=ANY(%s)
                     AND NOT EXISTS (
                       SELECT 1 FROM gem_sec_independent_receipt_audit a
                       WHERE a.receipt_id=r.receipt_id
                     )
                     AND (r.metadata->>'zip_member_name') ~ '^CIK[0-9]{10}[.]json$'
                   ORDER BY r.collected_at, r.receipt_id LIMIT %s""",
                (EXPERIMENT, sorted(SEC_KINDS), limit),
            )
            for rid, provider, source_hash, metadata in cur.fetchall():
                member = metadata.get("zip_member_name", "") if isinstance(metadata, dict) else ""
                match = MEMBER_PATTERN.fullmatch(member)
                if not match:
                    continue
                result = verify_receipt({"receipt_id": rid, "provider": provider,
                                         "source_sha256": source_hash, "metadata": metadata})
                status = "PASS" if result["status"] == "INTEGRITY_PASS" else "FAIL"
                checks = result["checks"]
                digest = checks.get("sha256")
                evidence = {"receipt_id": rid, "provider": provider,
                            "source_sha256": source_hash, "independent_sha256": digest,
                            "status": status, "checks": checks, "code_sha256": code_hash}
                evidence_hash = hashlib.sha256(json.dumps(
                    evidence, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                cur.execute(
                    """INSERT INTO gem_sec_independent_receipt_audit
                       (receipt_id, experiment_id, provider, cik, source_sha256,
                        independent_sha256, integrity_status, checks, evidence_sha256,
                        qa_identity, audit_code_sha256)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (receipt_id) DO NOTHING""",
                    (rid, EXPERIMENT, provider, match.group(1), source_hash, digest,
                     status, Jsonb(checks), evidence_hash, QA_IDENTITY, code_hash),
                )
                if cur.rowcount:
                    counts["audited"] += 1
                    counts["integrity_pass" if status == "PASS" else "integrity_fail"] += 1
    return {**counts, "financial_facts_certified": False,
            "dashboard_publication_authorized": False}


if __name__ == "__main__":
    print(json.dumps(process_pending()))
