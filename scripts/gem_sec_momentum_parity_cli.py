#!/usr/bin/env python3
"""Only run SEC B/C parity on a provisional positive-r63 SEC review queue.

Full 500-member current-list price scan precedes each bounded SEC batch.
Read-only GEM database roles only; no paid provider calls, raw document fetching,
writes, trading state, broker orders, price exclusions, or reviewer signatures.
A provisional Marketstack r63 is a WORKLOAD PRIORITY, not frozen-source parity.
Missing market data and all unverified exclusions remain blocking exceptions.

Example, with GEM_READONLY_DATABASE_URL set in an approved operator environment:
  python scripts/gem_sec_momentum_parity_cli.py --signal-day 2026-09-30 --limit 25 --offset 0
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
from scripts.gem_sec_momentum_priority_cli import (
    read_only_run as scan_prices,
    EXPERIMENT,
)

PROVIDERS = ("SEC_ZIP_SUBMISSIONS", "SEC_ZIP_COMPANYFACTS")
CIK_PATTERN = re.compile(r"^[0-9]{10}$")


def read_priority_receipts(conn, ciks):
    """SELECT-only bounded exact issuer IDs; never scan unrelated SEC payloads."""
    if (not isinstance(ciks, list) or not 1 <= len(ciks) <= 25
            or any(not isinstance(c, str) or not CIK_PATTERN.fullmatch(c)
                   for c in ciks) or len(set(ciks)) != len(ciks)):
        raise ValueError("SEC priority batch must contain 1–25 unique CIKs")
    members = ["CIK"+c+".json" for c in ciks]
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT ON (provider, metadata->>'zip_member_name')
                provider, source_uri, source_sha256, metadata,
                metadata->>'zip_member_name'
            FROM gem_source_receipt
            WHERE experiment_id=%s AND provider IN (%s,%s)
              AND metadata->>'zip_member_name' = ANY(%s)
            ORDER BY provider, metadata->>'zip_member_name',
                     observed_at DESC, receipt_id DESC
        """, (EXPERIMENT, *PROVIDERS, members))
        rows = cur.fetchall()
    records = {}
    for provider, uri, digest, metadata, member in rows:
        if provider not in PROVIDERS or member not in members:
            raise ValueError("Unexpected SEC priority original source")
        kind = "submissions" if provider == PROVIDERS[0] else "companyfacts"
        pair = records.setdefault(member,{})
        if kind in pair:
            raise ValueError("Duplicate SEC provider original")
        pair[kind]={"provider":provider,"source_uri":uri,
                    "source_sha256":str(digest).strip(),"metadata":metadata}
    # Include requested issuers even if SEC evidence is absent or incomplete.
    return [(cik, records.get("CIK"+cik+".json",{})) for cik in ciks]


def read_only_priority_parity(*, signal_day, limit=25, offset=0, dsn=None):
    if not isinstance(signal_day,str):
        raise ValueError("Missing month-end session")
    date.fromisoformat(signal_day)
    if (type(limit) is not int or not 1 <= limit <= 25
            or type(offset) is not int or offset < 0):
        raise ValueError("Invalid SEC workload page")
    dsn=dsn if dsn is not None else os.getenv("GEM_READONLY_DATABASE_URL","")
    if not dsn.startswith("postgresql://gem_web_readonly:"):
        raise ValueError("Restricted GEM reader required")
    momentum=scan_prices(signal_day=signal_day,scan_all=True,dsn=dsn)
    positives = [r for r in momentum["rows"] if r["priority"]=="SEC_REVIEW_FIRST"]
    missing_cik = [r["ticker"] for r in positives if not r["cik"]]
    selected = [r for r in positives if r["cik"]][offset:offset+limit]
    reports=[]
    if selected:
        import psycopg
        with psycopg.connect(dsn,connect_timeout=10) as conn:
            with conn.cursor() as cur:
                cur.execute("SET TRANSACTION READ ONLY")
                cur.execute("SET LOCAL statement_timeout=30000")
            for candidate,(cik,pair) in zip(
                    selected,read_priority_receipts(conn,[x["cik"] for x in selected])):
                if len(pair)!=2:
                    reports.append({
                        "ticker":candidate["ticker"],"cik":cik,
                        "status":"HOLD",
                        "blockers":["No paired SEC original receipts for prioritized CIK"],
                        "certified":False,"manual_trading_authorized":False})
                    continue
                diagnostic=diagnose_receipts(pair["submissions"],pair["companyfacts"],
                                             cik,signal_day)
                reports.append({"ticker":candidate["ticker"],"cik":cik,
                                "r63_preliminary":candidate["r63_preliminary"],
                                "sec_diagnostic":diagnostic,
                                "status":diagnostic["status"],
                                "certified":False})
    counts=dict(Counter(row["status"] for row in reports))
    return {
        "schema":"gem-sec-momentum-gated-parity-v1",
        "signal_day":signal_day,
        "current_secondary_universe_count":momentum["universe_count"],
        "priced_momentum_screened":momentum["evaluated"],
        "preliminary_momentum_counts":momentum["counts"],
        "momentum_queue_sha256":momentum["report_sha256"],
        "positive_momentum_priority_count":len(positives),
        "positive_missing_cik":missing_cik,
        "selected_offset":offset,"selected_limit":limit,
        "sec_diagnostic_count":len(reports),"sec_diagnostic_statuses":counts,
        "issuer_reports":reports,
        "price_repair_competitors_not_cleared":momentum["counts"]["PRICE_REPAIR_FIRST"],
        "deferred_negative_competitors_not_certified":momentum["counts"]["DEFER_SEC_PENDING_PRICE_QA"],
        "scope":"PROVISIONAL_MOMENTUM_FIRST_SEC_DIAGNOSTIC_NOT_CERTIFICATION",
        "independent_reviewer_signed":False,"signal_approved":False,
        "final_exclusions_certified":0,"trading_authorized":False,
        "orders_submitted":0,
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--signal-day",required=True)
    p.add_argument("--limit",type=int,default=25)
    p.add_argument("--offset",type=int,default=0)
    args=p.parse_args(argv)
    result=read_only_priority_parity(signal_day=args.signal_day,
                                     limit=args.limit,offset=args.offset)
    print(json.dumps(result,sort_keys=True,allow_nan=False))
    return 0


if __name__=="__main__":
    try:
        sys.exit(main())
    except (ValueError,RuntimeError) as exc:
        print("GEM momentum-gated SEC diagnostic HOLD: "+str(exc),file=sys.stderr)
        sys.exit(2)
