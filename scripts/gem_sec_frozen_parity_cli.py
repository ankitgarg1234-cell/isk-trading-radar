#!/usr/bin/env python3
"""Read-only bounded SEC B/C parity diagnostic from isolated GEM Neon receipts.

EXAMPLE (in an approved environment with a GEM read-only DB role):
  GEM_READONLY_DATABASE_URL='postgresql://gem_web_readonly:...' \
  python scripts/gem_sec_frozen_parity_cli.py --signal-day 2026-09-30 --limit 10

Prints one JSON report per issuer and a final summary. No INSERT/UPDATE/DELETE,
network SEC fetching, source certifications, auto deployment or broker orders.
The result is diagnostic only; no status is eligible to authorize trading.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
import json
import os
import re
import sys

from gem_data.gem_sec_frozen_parity import diagnose_receipts

EXPERIMENT = "gem-v1-forward-2026-10"
ORIGINAL_PROVIDERS = ("SEC_ZIP_SUBMISSIONS", "SEC_ZIP_COMPANYFACTS")
CIK_MEMBER = re.compile(r"^CIK([0-9]{10})\.json$")


def read_pairs(conn, *, limit, offset):
    """Snapshot selected latest *paired* original ZIP evidence, read-only."""
    if type(limit) is not int or not 1 <= limit <= 25:
        raise ValueError("SEC parity batches limited to 1–25 issuers")
    if type(offset) is not int or offset < 0:
        raise ValueError("Negative SEC parity offset")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT metadata->>'zip_member_name' AS original_cik_member
            FROM gem_source_receipt
            WHERE experiment_id=%s AND provider IN (%s,%s)
            GROUP BY metadata->>'zip_member_name'
            HAVING COUNT(DISTINCT provider)=2
            ORDER BY metadata->>'zip_member_name'
            LIMIT %s OFFSET %s
        """, (EXPERIMENT, *ORIGINAL_PROVIDERS, limit, offset))
        members = [row[0] for row in cur.fetchall()]
        if not members:
            return []
        cur.execute("""
            SELECT DISTINCT ON (provider, metadata->>'zip_member_name')
                provider, source_uri, source_sha256, metadata,
                metadata->>'zip_member_name'
            FROM gem_source_receipt
            WHERE experiment_id=%s
              AND provider IN (%s,%s)
              AND metadata->>'zip_member_name' = ANY(%s)
            ORDER BY provider, metadata->>'zip_member_name',
                     observed_at DESC, receipt_id DESC
        """, (EXPERIMENT, *ORIGINAL_PROVIDERS, members))
        selected = {}
        for provider, source_uri, raw_sha, metadata, member in cur.fetchall():
            match = CIK_MEMBER.fullmatch(member or "")
            if not match or provider not in ORIGINAL_PROVIDERS:
                raise ValueError("Unexpected SEC original member/provider")
            kind = "submissions" if provider == ORIGINAL_PROVIDERS[0] else "companyfacts"
            selected.setdefault(member, {})[kind] = {
                "provider": provider, "source_uri": source_uri,
                "source_sha256": str(raw_sha).strip(), "metadata": metadata,
            }
        if any(not CIK_MEMBER.fullmatch(m or "") or len(selected.get(m, {})) != 2
               for m in members):
            raise ValueError("Paired original SEC receipts incomplete or malformed")
        return [(CIK_MEMBER.fullmatch(m).group(1), selected[m])
                for m in members]


def read_only_run(*, signal_day, limit=10, offset=0, dsn=None):
    """Do not reuse the service's ingestion role, even accidentally."""
    date.fromisoformat(signal_day)
    dsn = dsn if dsn is not None else os.getenv("GEM_READONLY_DATABASE_URL","")
    if not dsn.startswith("postgresql://gem_web_readonly:"):
        raise ValueError("GEM scoped read-only Neon connection required")
    import psycopg
    counts = Counter()
    reports = []
    with psycopg.connect(dsn, connect_timeout=10) as conn:
        # Read-only transaction: even compromised code must not change state.
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
        for cik, pair in read_pairs(conn, limit=limit, offset=offset):
            result = diagnose_receipts(pair["submissions"],pair["companyfacts"],
                                       cik, signal_day)
            counts[result["status"]] += 1
            reports.append(result)
    return {
        "schema": "gem-sec-parity-batch-diagnostic-v1",
        "signal_day": signal_day, "limit": limit, "offset": offset,
        "statuses": dict(counts), "issuer_reports": reports,
        "independent_reviewer_signed": False,
        "investment_release_authorized": False, "orders_submitted": 0,
    }


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signal-day", required=True)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--offset", type=int, default=0)
    args=parser.parse_args(argv)
    data=read_only_run(signal_day=args.signal_day, limit=args.limit, offset=args.offset)
    print(json.dumps(data, sort_keys=True, allow_nan=False))
    return 0 if data["issuer_reports"] else 3


if __name__=="__main__":
    try:
        sys.exit(main())
    except (ValueError, RuntimeError) as exc:
        print("GEM SEC parity diagnostic HOLD: " + str(exc), file=sys.stderr)
        sys.exit(2)
