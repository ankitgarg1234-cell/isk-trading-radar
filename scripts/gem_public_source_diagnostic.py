#!/usr/bin/env python3
"""Safe, read-only GEM public-source connectivity and identity diagnostic.

Never supplies GEM trading inputs or places orders. Probes only public
secondary S&P catalogues and the official NYSE hours page, with bounded HTTP
requests. Other inputs (IBKR licensed feed, original SEC raw filing validation,
entitled primary membership, and corporate actions) remain explicit NOT_READY.
Run with:
    python scripts/gem_public_source_diagnostic.py --out /tmp/gem-source-probe.json
Do NOT point --out at a portfolio DB, live signal or trading configuration.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx

URLS = {
    "membership_current_secondary": "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/master/data/constituents.csv",
    "membership_history_secondary": "https://raw.githubusercontent.com/lawcal/sp500-components-history/main/data/components_history.csv",
    "nyse_official_calendar": "https://www.nyse.com/markets/hours-calendars",
}
USER_AGENT = "GEM-FrozenResearch/1.0 (read-only diagnostic; no trading)"
MAX_BYTES = 5_000_000


def retrieve(client, key, url):
    try:
        r = client.get(url, follow_redirects=True)
        r.raise_for_status()
        body = r.content
        if len(body) == 0 or len(body) > MAX_BYTES:
            raise ValueError("empty or oversized source response")
        return {
            "source_key": key, "status": "RESPONDED_UNCERTIFIED",
            "uri": str(r.url), "http_status": r.status_code,
            "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }, body
    except (httpx.HTTPError, OSError, ValueError) as exc:
        return {"source_key": key, "status": "UNAVAILABLE",
                "issue": type(exc).__name__,
                "collected_at": datetime.now(timezone.utc).isoformat()}, b""


def analyze_constituents(body):
    if not body:
        return {"status": "NOT_READY", "issue": "secondary constituent source inaccessible"}
    rows = list(csv.DictReader(io.StringIO(body.decode("utf-8-sig"))))
    observed = []
    for row in rows:
        ticker = (row.get("Symbol") or "").strip()
        cik = (row.get("CIK") or "").strip()
        if ticker:
            observed.append((ticker, cik))
    symbols = [x[0] for x in observed]
    return {
        "observed_rows": len(rows), "nonempty_tickers": len(symbols),
        "cik_present": sum(bool(x[1]) for x in observed),
        "unique_tickers": len(set(symbols)),
        "status": "DIAGNOSTIC_ONLY",
        "cannot_prove": "effective-dated full S&P membership, primary issuer/share-class identity, any historical selection",
    }


def analyze_history(body):
    if not body:
        return {"status": "NOT_READY", "issue": "secondary S&P history unavailable"}
    rows = list(csv.DictReader(io.StringIO(body.decode("utf-8-sig"))))
    if not rows:
        return {"status": "NOT_READY", "issue": "no history rows"}
    fields = list(rows[0].keys())
    return {
        "observed_intervals": len(rows), "columns": fields,
        "status": "DIAGNOSTIC_ONLY",
        "cannot_prove": "licensed complete official S&P index constituent event history or pre-publication timing",
    }


def run(out_path):
    with httpx.Client(timeout=15.0, headers={"User-Agent": USER_AGENT, "Accept": "*/*"}) as client:
        receipts = {}
        payloads = {}
        for key, url in URLS.items():
            receipts[key], payloads[key] = retrieve(client, key, url)
    report = {
        "schema": "gem-public-diagnostic-v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "strategy_ref": "d59b93d3d9a87d582045b4ae71ff9a6f696a48be",
        "environment": "NO_TRADING_DIAGNOSTIC",
        "execution_enabled": False,
        "sources": receipts,
        "secondary_constituents": analyze_constituents(payloads["membership_current_secondary"]),
        "secondary_membership_intervals": analyze_history(payloads["membership_history_secondary"]),
        "open_items": {
            "official_s_and_p_effective_membership": "PRIMARY_DATA_ACCESS_REQUIRED",
            "full_universe_ibkr_ohlcv": "UNATTENDED_MARKETDATA_GATEWAY_NOT_CONFIGURED",
            "raw_10q_semantic_availability": "ALL_COMPETITORS_NOT_QUALIFIED",
            "corporate_actions": "PRIMARY_COVERAGE_NOT_VERIFIED",
            "nyse_early_close_emergency_status": "INDEPENDENT_RELEASE_QA_REQUIRED",
            "spy_total_return": "SPY_PRICE_PROBE_IS_NOT_TOTAL_RETURN",
        },
    }
    path = Path(out_path).resolve()
    if path.exists():
        raise SystemExit("Refusing to overwrite existing evidence: " + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = run(args.out)
    print(json.dumps({
        "evidence_path": str(Path(args.out).resolve()),
        "source_states": {k: v["status"] for k, v in result["sources"].items()},
        "trade_authorized": False,
    }, sort_keys=True))
