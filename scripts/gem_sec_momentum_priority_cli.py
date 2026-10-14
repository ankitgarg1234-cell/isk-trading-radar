#!/usr/bin/env python3
"""Read-only GEMv1 momentum-first SEC review queue from existing GEM Neon.

No SEC filing downloads, vendor API requests, DB writes, reviewer certificates,
brokerage orders, or new costs. Current secondary membership is NOT official
point-in-time membership. Marketstack vendor_adj_close is NOT frozen-vendor
parity; negative provisional r63 only defers detailed SEC work, never causes
a final frozen eligibility exclusion.

Usage (set read-only GEM DSN securely):
  python scripts/gem_sec_momentum_priority_cli.py --signal-day 2026-09-30 --all
  python scripts/gem_sec_momentum_priority_cli.py --signal-day 2026-09-30 --all --include-rows
"""
from __future__ import annotations

import argparse
import base64
import binascii
import csv
from datetime import date
from hashlib import sha256
from io import StringIO
import json
import os
import re
import sys
import zlib

from gem_data.gem_sec_momentum_priority import preliminary_momentum

EXPERIMENT = "gem-v1-forward-2026-10"
SECURITY = re.compile(r"^[A-Z0-9.-]{1,16}$")


def _members(source_hash, metadata):
    if not isinstance(metadata, dict):
        raise ValueError("Source membership metadata missing")
    encoded = metadata.get("source_raw_zlib_base64")
    if not isinstance(encoded, str) or len(encoded) > 700000:
        raise ValueError("No bounded current membership original")
    try:
        compressed = base64.b64decode(encoded, validate=True)
        inflater = zlib.decompressobj()
        raw = inflater.decompress(compressed, 600001)
        if (len(raw) > 600000 or not inflater.eof or
                inflater.unconsumed_tail or inflater.unused_data):
            raise ValueError("Membership decompression incomplete")
        raw += inflater.flush()
        if len(raw) > 600000 or sha256(raw).hexdigest() != source_hash:
            raise ValueError("Membership source hash mismatch")
        csv_rows = list(csv.DictReader(StringIO(raw.decode("utf-8-sig"))))
    except (ValueError, TypeError, UnicodeError, binascii.Error,
            zlib.error, csv.Error) as exc:
        raise ValueError("Membership source bytes invalid") from exc
    members = {}
    for record in csv_rows:
        ticker = str(record.get("Symbol") or "").upper()
        raw_cik = str(record.get("CIK") or "").strip()
        if not SECURITY.fullmatch(ticker) or ticker in members:
            raise ValueError("Duplicate or malformed current member ticker")
        cik = raw_cik.zfill(10) if raw_cik.isdigit() and len(raw_cik) <= 10 else None
        members[ticker] = cik
    if not 480 <= len(members) <= 600:
        raise ValueError("Current secondary membership incomplete")
    return members


def _read_prices(conn, tickers):
    if not 1 <= len(tickers) <= 25:
        raise ValueError("Bound each original price read to 25 symbols")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT ON (metadata->>'ticker')
                metadata->>'ticker', provider, source_sha256, metadata
            FROM gem_source_receipt
            WHERE experiment_id=%s AND provider='MARKETSTACK'
              AND source_type='prices'
              AND metadata->>'ticker' = ANY(%s)
            ORDER BY metadata->>'ticker', observed_at DESC, receipt_id DESC
        """, (EXPERIMENT, list(tickers)))
        rows = cur.fetchall()
    result = {}
    for ticker, provider, digest, metadata in rows:
        if ticker not in tickers or ticker in result:
            raise ValueError("Unexpected or duplicate vendor receipt")
        result[ticker] = {
            "provider": provider, "source_sha256": str(digest).strip(),
            "metadata": metadata,
        }
    return result


def read_only_run(*, signal_day, limit=25, offset=0, scan_all=False, dsn=None):
    if not isinstance(signal_day, str):
        raise ValueError("Missing signal date")
    date.fromisoformat(signal_day)
    if (type(limit) is not int or not 1 <= limit <= 25
            or type(offset) is not int or offset < 0
            or type(scan_all) is not bool):
        raise ValueError("Invalid bounded review scan")
    dsn = dsn if dsn is not None else os.getenv("GEM_READONLY_DATABASE_URL", "")
    if not dsn.startswith("postgresql://gem_web_readonly:"):
        raise ValueError("Restricted GEM-only read role required")
    import psycopg
    with psycopg.connect(dsn, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SET LOCAL statement_timeout=30000")
            cur.execute("""
                SELECT source_sha256, metadata
                FROM gem_source_receipt
                WHERE experiment_id=%s AND provider='SECONDARY_GITHUB_SP500'
                ORDER BY observed_at DESC, receipt_id DESC LIMIT 1
            """, (EXPERIMENT,))
            source = cur.fetchone()
        if not source:
            raise ValueError("Current membership source not present")
        current_members = _members(str(source[0]).strip(), source[1])
        universe = sorted(current_members)
        selected = universe if scan_all else universe[offset:offset+limit]
        if not selected:
            raise ValueError("Requested review offset beyond membership")
        rows = []
        for start in range(0, len(selected), 25):
            block = selected[start:start+25]
            price_receipts = _read_prices(conn, block)
            for ticker in block:
                result = preliminary_momentum(price_receipts.get(ticker), ticker, signal_day)
                result["cik"] = current_members[ticker]
                rows.append(result)
    order = {"SEC_REVIEW_FIRST":0, "PRICE_REPAIR_FIRST":1,
             "DEFER_SEC_PENDING_PRICE_QA":2}
    rows.sort(key=lambda r:(order[r["priority"]],
                            -r["r63_preliminary"] if r["r63_preliminary"] is not None else 0,
                            r["ticker"]))
    counts = {key: sum(r["priority"] == key for r in rows) for key in order}
    result = {
        "schema":"gem-sec-momentum-readonly-priority-v1",
        "signal_day":signal_day, "universe_count":len(universe),
        "evaluated":len(rows), "scan_all":scan_all,
        "counts":counts, "rows":rows,
        "ranking_basis":"UNCERTIFIED_MARKETSTACK_ADJUSTED_CLOSE_64_OBSERVATIONS",
        "membership_basis":"CURRENT_SECONDARY_NOT_PIT_CERTIFIED",
        "excluded_as_proven_negative_momentum":0,
        "source_verified":False, "strategy_rank_verified":False,
        "sec_facts_verified":False, "trade_authorized":False,
        "orders_submitted":0,
    }
    result["report_sha256"] = sha256(
        json.dumps(result, sort_keys=True, separators=(",", ":"),allow_nan=False).encode()
    ).hexdigest()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signal-day", required=True)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--all", action="store_true", dest="scan_all")
    parser.add_argument("--include-rows", action="store_true")
    args = parser.parse_args(argv)
    report = read_only_run(signal_day=args.signal_day, limit=args.limit,
                           offset=args.offset, scan_all=args.scan_all)
    if not args.include_rows:
        report["sec_review_first"] = [
            {"ticker":r["ticker"],"cik":r["cik"],"r63":r["r63_preliminary"]}
            for r in report["rows"] if r["priority"]=="SEC_REVIEW_FIRST"]
        report.pop("rows")
    print(json.dumps(report,sort_keys=True,allow_nan=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, RuntimeError) as exc:
        print("GEM momentum SEC priority HOLD: "+str(exc),file=sys.stderr)
        sys.exit(2)
