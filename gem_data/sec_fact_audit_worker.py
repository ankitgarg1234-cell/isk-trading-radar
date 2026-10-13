"""Read-only original SEC evidence -> independent automated QA -> PARTIAL probe.

This worker never certifies GEM. It uses the GEM read-only role to recompute
original member hashes and quarter candidates, and the pre-existing INSERT-
only source-probe role to append transparent machine QA receipts. No UPDATE,
DELETE, Marketstack, signals, orders, or trading database permissions.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re

import psycopg

from gem_data.gem_public_ingest import EXPERIMENT, write_observation
from gem_data.sec_independent_fact_verify import AS_OF, verify_receipt_pair

CIK_MEMBER = re.compile(r"^CIK([0-9]{10})\.json$")
CODE_SHA256 = sha256(
    Path(__file__).with_name("sec_independent_fact_verify.py").read_bytes()
).hexdigest()
QA_PREFIX = f"gem-sec-fact-qa-{AS_OF:%Y%m%d}-"


class QAHold(RuntimeError):
    pass


def _paired_latest(read_conn):
    with read_conn.cursor() as cur:
        # Metadata is not returned here: read only ten raw receipts at a time.
        cur.execute("""
            SELECT DISTINCT ON (provider, metadata->>'zip_member_name')
                provider, receipt_id, source_sha256,
                metadata->>'zip_member_name'
            FROM gem_source_receipt
            WHERE experiment_id=%s AND provider IN
                ('SEC_ZIP_SUBMISSIONS','SEC_ZIP_COMPANYFACTS')
            ORDER BY provider, metadata->>'zip_member_name',
                     observed_at DESC, receipt_id DESC
        """, (EXPERIMENT,))
        groups = {}
        for provider, receipt_id, digest, member in cur.fetchall():
            m = CIK_MEMBER.fullmatch(member or "")
            if not m:
                continue
            kind = "submissions" if provider == "SEC_ZIP_SUBMISSIONS" else "companyfacts"
            groups.setdefault(m.group(1), {})[kind] = (receipt_id, str(digest).strip())
        cur.execute("SELECT probe_id FROM gem_source_probe WHERE probe_id LIKE %s",
                    (QA_PREFIX+"%",))
        done = {row[0] for row in cur.fetchall()}
    return groups, done


def _key(cik, pair):
    ids = "|".join(pair[k][0] for k in ("submissions", "companyfacts"))
    return QA_PREFIX + cik + "-" + sha256(ids.encode()).hexdigest()[:20]


def audit_batch(*, max_pairs: int = 5) -> dict:
    if type(max_pairs) is not int or not 1 <= max_pairs <= 10:
        raise QAHold("SEC QA batch exceeds bounded 10-CIK budget")
    reader = os.getenv("GEM_READONLY_DATABASE_URL", "")
    writer = os.getenv("GEM_INGEST_DATABASE_URL", "")
    if not reader.startswith("postgresql://gem_web_readonly:"):
        raise QAHold("SEC QA read-only database role unavailable")
    if not writer.startswith("postgresql://gem_source_ingest_limited:"):
        raise QAHold("SEC QA INSERT-only evidence role unavailable")
    now = datetime.now(timezone.utc)
    with psycopg.connect(reader, connect_timeout=6) as conn:
        groups, done = _paired_latest(conn)
        pairs = [(cik, pair, _key(cik, pair)) for cik, pair in sorted(groups.items())
                 if len(pair) == 2 and _key(cik, pair) not in done]
        chosen = pairs[:max_pairs]
        receipt_ids = [pair[k][0] for _cik, pair, _keyid in chosen
                       for k in ("submissions", "companyfacts")]
        rows = {}
        if receipt_ids:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT receipt_id,provider,source_sha256,metadata
                    FROM gem_source_receipt
                    WHERE experiment_id=%s AND receipt_id=ANY(%s)
                """, (EXPERIMENT, receipt_ids))
                rows = {rid: {"receipt_id": rid, "provider": provider,
                              "source_sha256": digest, "metadata": metadata}
                        for rid, provider, digest, metadata in cur.fetchall()}
    result = {"paired_issuers": sum(len(x) == 2 for x in groups.values()),
              "already_audited_current_receipts": len(done),
              "audited": 0, "integrity_pass": 0, "candidate_complete": 0,
              "fact_unknown": 0, "integrity_fail": 0,
              "remaining_after_estimate": len(pairs)}
    if not chosen:
        return result
    with psycopg.connect(writer, connect_timeout=6) as conn:
        for cik, pair, key in chosen:
            sub_id, fact_id = pair["submissions"][0], pair["companyfacts"][0]
            if sub_id not in rows or fact_id not in rows:
                raise QAHold("SEC independent QA original receipt disappeared")
            evidence = verify_receipt_pair(rows[sub_id], rows[fact_id], cik, AS_OF)
            integrity = evidence["receipt_integrity"]
            status = evidence["fact_status"]
            probe = {
                "probe_id": key, "source_type": "sec",
                "state": "BLOCKED" if integrity == "FAIL" else "PARTIAL",
                "observed_at": now,
                "diagnostic_hash": evidence["evidence_sha256"],
                "sample_count": len(evidence["six_facts"]),
                "details": {
                    "source": "SEC original submissions + companyfacts ZIP member pair",
                    "scope": f"Independent automated recomputation for CIK {cik}",
                    "as_of": AS_OF.isoformat(),
                    "submissions_receipt_id": sub_id,
                    "companyfacts_receipt_id": fact_id,
                    "receipt_integrity": integrity,
                    "fact_status": status,
                    "six_facts": evidence["six_facts"],
                    "blockers": evidence["blockers"],
                    "evidence_sha256": evidence["evidence_sha256"],
                    "verifier_code_sha256": CODE_SHA256,
                    "qa_identity": "GEM automated separate read-only recomputation",
                    "original_accession_inline_xbrl_certified": False,
                    "human_reviewer_approved": False,
                    "certified": False,
                    "trading_authorized": False,
                },
            }
            write_observation(conn, None, probe)
            conn.commit()
            result["audited"] += 1
            result["integrity_pass" if integrity == "PASS" else "integrity_fail"] += 1
            result["candidate_complete" if status == "CANDIDATE_COMPLETE_NOT_CERTIFIED"
                   else "fact_unknown"] += 1
    result["remaining_after_estimate"] -= result["audited"]
    return result
