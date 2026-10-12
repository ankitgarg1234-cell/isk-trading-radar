"""Bounded SEC original issuer-submissions discovery; NO factor certification.

A valid organization/contact SEC_USER_AGENT is required. This is a separately
gated research-only pipeline, not an alternative way to approve GEM trades.
Uses current secondary membership CIKs for **discovery only**, never frozen
historical point-in-time index membership. 90 issuers/day, ~6-day rotation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import base64
import csv
from io import StringIO
import json
import math
import re
import zlib

import psycopg

from gem_data.gem_public_ingest import EXPERIMENT, write_observation
from gem_data.sec_original_collector import (
    SecOriginalCollector, SEC_SUBMISSIONS, normalize_cik,
    validate_sec_user_agent, SourceUnavailable,
)

SEC_BATCH_LIMIT = 90


def select_ciks(current_secondary_csv: bytes, observed_at: datetime) -> tuple[list[str], int]:
    if observed_at.tzinfo is None:
        raise ValueError("SEC discovery clock must be aware")
    try:
        table = list(csv.DictReader(StringIO(current_secondary_csv.decode("utf-8-sig"))))
        ids = sorted({normalize_cik(row["CIK"].strip()) for row in table})
    except (KeyError, UnicodeError, ValueError, csv.Error) as exc:
        raise ValueError("Secondary issuer CIK manifest unavailable") from exc
    if not 450 <= len(ids) <= 550:
        raise ValueError("Secondary issuer set implausibly incomplete")
    count = math.ceil(len(ids) / SEC_BATCH_LIMIT)
    cohort = observed_at.astimezone(timezone.utc).date().toordinal() % count
    selected = ids[cohort * SEC_BATCH_LIMIT:(cohort + 1) * SEC_BATCH_LIMIT]
    if not selected or len(selected) > SEC_BATCH_LIMIT:
        raise ValueError("SEC issuer batch selection invalid")
    return selected, len(ids)


def _snapshot(raw: bytes, cik: str) -> dict:
    """Validate original submissions JSON before extracting accession metadata."""
    try:
        source = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise SourceUnavailable("Invalid SEC source JSON") from exc
    if not isinstance(source, dict) or str(source.get("cik", "")).zfill(10) != cik:
        raise SourceUnavailable("Original SEC issuer CIK mismatch")
    recent = ((source.get("filings") or {}).get("recent") or {})
    names = ("form", "accessionNumber", "filingDate", "acceptanceDateTime")
    arrays = [recent.get(n) for n in names]
    if any(not isinstance(a, list) for a in arrays) or len(set(len(a) for a in arrays)) != 1:
        raise SourceUnavailable("Malformed SEC accession array alignment")
    quarter = []
    for form, acc, filed, accepted in zip(*arrays):
        if form not in ("10-Q", "10-Q/A"):
            continue
        if not all(isinstance(v, str) for v in (acc, filed, accepted)):
            raise SourceUnavailable("Malformed SEC original accession record")
        if not re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", acc):
            raise SourceUnavailable("Malformed SEC accession")
        quarter.append({"form": form, "accession": acc,
                        "filed_date_raw": filed,
                        "accepted_clock_raw": accepted})
        if len(quarter) >= 24:
            break
    return {
        "cik": cik, "filing_count_in_recent": len(arrays[0]),
        "quarter_accessions_found": len(quarter),
        "recent_quarter_discovery": quarter,
        "six_financial_facts_certified": False,
        "primary_issuer_identity_vs_index_membership_verified": False,
    }


def probe_batch(csv_bytes: bytes, observed: datetime, user_agent: str,
                *, transport=None) -> tuple[list[tuple[dict | None, dict]], dict]:
    ua = validate_sec_user_agent(user_agent)
    if not observed.tzinfo:
        raise ValueError("SEC discovery requires aware timestamp")
    observed = observed.astimezone(timezone.utc)
    ciks, total = select_ciks(csv_bytes, observed)
    failures = []
    evidence: list[tuple[dict | None, dict]] = []
    with SecOriginalCollector(ua, transport=transport) as collector:
        for cik in ciks:
            uri = SEC_SUBMISSIONS.format(cik=cik)
            try:
                source_receipt, raw = collector.get(uri)
                description = _snapshot(raw, cik)
                digest = source_receipt.sha256
                receipt = {
                    "receipt_id": f"gem-sec-submissions-{cik}-{digest[:20]}",
                    "observed_at": observed,
                    "source_uri": uri,
                    "source_sha256": digest,
                    "coverage_status": "UNKNOWN",
                    "provider": "SEC_ORIGINAL_SUBMISSIONS",
                    "metadata": {
                        "source_raw_zlib_base64": base64.b64encode(zlib.compress(raw, 9)).decode(),
                        "source_raw_length": len(raw), "source_sha256": digest,
                        "issuer_cik": cik, "discovery": description,
                        "original_xbrl_facts_verified": False,
                        "source_publication_asof_certified": False,
                    },
                }
                state = "PARTIAL"
            except (SourceUnavailable, ValueError) as exc:
                receipt = None
                digest = sha256(f"sec:{cik}:{type(exc).__name__}".encode()).hexdigest()
                failures.append({"cik": cik, "reason": type(exc).__name__})
                state = "BLOCKED"
            probe = {
                "probe_id": f"gem-sec-scan-{observed:%Y%m%d}-{cik}-{digest[:16]}",
                "source_type": "sec", "state": state,
                "observed_at": observed, "diagnostic_hash": digest,
                "sample_count": 1 if receipt else 0,
                "details": {"source": uri, "scope": "Original submissions for one current-secondary-list CIK",
                            "proof": "Six original financial fact contexts/publication cutoff and eligible universe NOT independently verified",
                            "certified": False, "trading_authorized": False},
            }
            evidence.append((receipt, probe))

    failed = len(failures)
    summary = {
        "ciks_in_secondary_current_list": total,
        "ciks_attempted": len(ciks),
        "ciks_source_fetch_passed": len(ciks) - failed,
        "ciks_failed": failed,
        "failure_categories": sorted(set(f["reason"] for f in failures)),
        "full_eligible_universe_certified": False,
        "six_original_quarter_facts_certified": False,
        "point_in_time_membership_certified": False,
    }
    digest = sha256(json.dumps(summary, sort_keys=True).encode()).hexdigest()
    evidence.append((None, {
        "probe_id": f"gem-sec-batch-{observed:%Y%m%d}-{digest[:16]}",
        "source_type": "sec", "state": "BLOCKED" if failed else "PARTIAL",
        "observed_at": observed.replace(microsecond=observed.microsecond + 1 if observed.microsecond < 999999 else 999999),
        "diagnostic_hash": digest, "sample_count": len(ciks)-failed,
        "details": {"source": "https://data.sec.gov/submissions/",
                    "scope": f"{len(ciks)} of {total} current secondary-list issuers",
                    "proof": "Current CIK scan only, no original 10-Q XBRL context/qualified full-universe factors",
                    "counts": summary, "certified": False, "trading_authorized": False},
    }))
    return evidence, summary


def store_sec_discovery(conn, evidence: list[tuple[dict | None, dict]]) -> None:
    """One database connection, individual small transactions, inserts only."""
    for receipt, probe in evidence:
        write_observation(conn, receipt, probe)
        conn.commit()
