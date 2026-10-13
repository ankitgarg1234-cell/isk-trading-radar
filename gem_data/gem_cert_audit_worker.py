"""Independent, opt-in GEM receipt audit worker. No collection or trading.

Requires a separate role with SELECT on source receipts and INSERT on receipt audits.
The receipt audit is append-only: existing rows are never overwritten.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import os

import psycopg
from psycopg.types.json import Jsonb

from gem_data.gem_independent_certification import EXPERIMENT, SEC_KINDS, verify_receipt

MAX_BATCH = 10
QA_IDENTITY = "gem-independent-sec-worker-v1"


def check_audit_permissions() -> dict:
    """Check the configured role without attempting a write."""
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
            source_read, audit_read, audit_write = cur.fetchone()
    return {"ready": bool(source_read and audit_read and audit_write),
            "source_read": bool(source_read), "audit_read": bool(audit_read),
            "audit_insert": bool(audit_write)}


def process_pending(limit: int = MAX_BATCH) -> dict:
    if not 1 <= limit <= MAX_BATCH:
        raise ValueError("bounded batch required")
    url = os.getenv("GEM_CERT_AUDIT_DATABASE_URL", "")
    if not url.startswith(("postgresql://", "postgres://")):
        raise RuntimeError("Dedicated GEM audit credential not configured")
    code_hash = hashlib.sha256(inspect.getsource(verify_receipt).encode()).hexdigest()
    processed = passed = failed = blocked = 0
    with psycopg.connect(url, connect_timeout=6, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout = 20000")
            cur.execute(
                """SELECT r.receipt_id, r.provider, r.source_sha256, r.metadata
                   FROM gem_source_receipt r
                   WHERE r.experiment_id=%s AND r.provider=ANY(%s)
                     AND NOT EXISTS (
                       SELECT 1 FROM gem_sec_independent_receipt_audit a
                       WHERE a.receipt_id=r.receipt_id
                     )
                   AND (r.metadata->>'zip_member_name') ~ 'CIK[0-9]{10}\\.json""",
                (EXPERIMENT, sorted(SEC_KINDS), limit),
            )
            receipts = cur.fetchall()
            for rid, provider, source_hash, metadata in receipts:
                result = verify_receipt({
                    "receipt_id": rid, "provider": provider,
                    "source_sha256": source_hash, "metadata": metadata,
                })
                checks = result["checks"]
                cik = str(checks.get("cik") or (metadata or {}).get("zip_member_name", "")).replace("CIK", "").replace(".json", "")
                if not (len(cik) == 10 and cik.isdigit()):
                    # The DB requires a CIK. Unattributable receipts must stay
                    # pending/blocked rather than be given a fabricated identity.
                    blocked += 1
                    continue
                status = "PASS" if result["status"] == "INTEGRITY_PASS" else "FAIL"
                independent_hash = checks.get("sha256")
                evidence = {
                    "receipt_id": rid, "provider": provider, "source_sha256": source_hash,
                    "independent_sha256": independent_hash, "status": status,
                    "checks": checks, "code_sha256": code_hash,
                }
                evidence_hash = hashlib.sha256(
                    json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest()
                cur.execute(
                    """INSERT INTO gem_sec_independent_receipt_audit
                       (receipt_id, experiment_id, provider, cik, source_sha256,
                        independent_sha256, integrity_status, checks, evidence_sha256,
                        qa_identity, audit_code_sha256)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (receipt_id) DO NOTHING""",
                    (rid, EXPERIMENT, provider, cik, source_hash, independent_hash,
                     status, Jsonb(checks), evidence_hash, QA_IDENTITY, code_hash),
                )
                if cur.rowcount:
                    processed += 1
                    passed += status == "PASS"
                    failed += status == "FAIL"
    return {"audited": processed, "integrity_pass": passed, "integrity_fail": failed, "blocked_unattributable": blocked,
            "financial_facts_certified": False, "dashboard_publication_authorized": False}


if __name__ == "__main__":
    print(json.dumps(process_pending()))

                   ORDER BY r.collected_at, r.receipt_id LIMIT %s""",
                (EXPERIMENT, sorted(SEC_KINDS), limit),
            )
            receipts = cur.fetchall()
            for rid, provider, source_hash, metadata in receipts:
                result = verify_receipt({
                    "receipt_id": rid, "provider": provider,
                    "source_sha256": source_hash, "metadata": metadata,
                })
                checks = result["checks"]
                cik = str(checks.get("cik") or (metadata or {}).get("zip_member_name", "")).replace("CIK", "").replace(".json", "")
                if not (len(cik) == 10 and cik.isdigit()):
                    # The DB requires a CIK. Unattributable receipts must stay
                    # pending/blocked rather than be given a fabricated identity.
                    continue
                status = "PASS" if result["status"] == "INTEGRITY_PASS" else "FAIL"
                independent_hash = checks.get("sha256")
                evidence = {
                    "receipt_id": rid, "provider": provider, "source_sha256": source_hash,
                    "independent_sha256": independent_hash, "status": status,
                    "checks": checks, "code_sha256": code_hash,
                }
                evidence_hash = hashlib.sha256(
                    json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest()
                cur.execute(
                    """INSERT INTO gem_sec_independent_receipt_audit
                       (receipt_id, experiment_id, provider, cik, source_sha256,
                        independent_sha256, integrity_status, checks, evidence_sha256,
                        qa_identity, audit_code_sha256)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (receipt_id) DO NOTHING""",
                    (rid, EXPERIMENT, provider, cik, source_hash, independent_hash,
                     status, Jsonb(checks), evidence_hash, QA_IDENTITY, code_hash),
                )
                if cur.rowcount:
                    processed += 1
                    passed += status == "PASS"
                    failed += status == "FAIL"
    return {"audited": processed, "integrity_pass": passed, "integrity_fail": failed,
            "financial_facts_certified": False, "dashboard_publication_authorized": False}


if __name__ == "__main__":
    print(json.dumps(process_pending()))
