"""Public secondary S&P membership research; never eligible to certify GEMv1.

The original frozen GEM strategy, official-source readiness gate, paper account,
and execution logic do not import this file. It is intended for diagnostic
historical research and reconciliation before independent primary-source QA.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

SOURCE_HISTORY = "https://raw.githubusercontent.com/lawcal/sp500-components-history/main/data/components_history.csv"
SOURCE_CURRENT = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
SOURCE_APRIL_2026 = "https://raw.githubusercontent.com/pierrebrunelle/sp500-historical-constituents/main/data/spy202604"
MAX_BYTES = 2_000_000
SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9.\-/]{0,12}$")
CIK = re.compile(r"^[0-9]{10}$")


class ResearchSourceError(ValueError):
    pass


def normalize_alias(symbol: str) -> str:
    """Only for cross-source diagnostics, not for strategy symbol mappings."""
    return symbol.strip().upper().replace("/", ".").replace("-", ".")


def fetch_public_source(url: str, *, opener=urllib.request.urlopen) -> bytes:
    if url not in {SOURCE_HISTORY, SOURCE_CURRENT, SOURCE_APRIL_2026}:
        raise ResearchSourceError("Unapproved research source URL")
    req = urllib.request.Request(url, headers={"User-Agent": "GEM-research-source-audit/1.0"})
    with opener(req, timeout=25) as response:
        content = response.read(MAX_BYTES + 1)
    if not content or len(content) > MAX_BYTES:
        raise ResearchSourceError("Public history unavailable or outside size limit")
    return content


def _table(raw: bytes, required: set[str]) -> list[dict[str, str]]:
    try:
        body = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(body))
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise ResearchSourceError("Unexpected constituent CSV schema")
        rows = list(reader)
    except UnicodeDecodeError as exc:
        raise ResearchSourceError("Non-UTF8 constituent source") from exc
    if not rows or any(None in row or None in row.values() for row in rows):
        raise ResearchSourceError("Malformed constituent CSV rows")
    return rows


def _effective_date(value: str, field: str) -> tuple[date, bool]:
    if not isinstance(value, str) or not value:
        raise ResearchSourceError("Missing effective-date field: " + field)
    approximate = value.endswith("*")
    try:
        return date.fromisoformat(value.rstrip("*")), approximate
    except ValueError as exc:
        raise ResearchSourceError("Malformed date in " + field) from exc


def parse_history(raw: bytes) -> list[dict]:
    source = _table(raw, {"symbol", "cik", "name", "sector", "date_added", "date_removed", "created_at"})
    parsed = []
    for item in source:
        ticker = item["symbol"].strip().upper()
        cik = item["cik"].strip()
        if not SYMBOL.fullmatch(ticker) or not CIK.fullmatch(cik):
            raise ResearchSourceError("Invalid ticker or security CIK")
        added, added_approx = _effective_date(item["date_added"], "date_added")
        removed, removed_approx = ((None, False) if not item["date_removed"]
                                   else _effective_date(item["date_removed"], "date_removed"))
        created, _ = _effective_date(item["created_at"], "created_at")
        if removed is not None and removed <= added:
            raise ResearchSourceError("Impossible historical constituent interval")
        parsed.append({
            "ticker": ticker, "cik": cik, "name": item["name"], "sector": item["sector"],
            "effective_from": added, "effective_until": removed,
            "date_approximate": added_approx or removed_approx,
            "first_source_recorded_on": created,
        })
    return parsed


def asof_members(history: list[dict], day: date) -> list[dict]:
    if day < date(2007, 3, 5):
        raise ResearchSourceError("Secondary source cannot reconstruct before March 2007")
    active = [r for r in history if r["effective_from"] <= day
              and (r["effective_until"] is None or day < r["effective_until"])]
    tickers = [r["ticker"] for r in active]
    if len(tickers) != len(set(tickers)):
        raise ResearchSourceError("Ambiguous active intervals for the same ticker")
    return sorted(active, key=lambda x: x["ticker"])


def _current_symbols(raw: bytes) -> set[str]:
    rows = _table(raw, {"Symbol", "CIK"})
    names = [r["Symbol"].strip().upper() for r in rows]
    if len(set(names)) != len(names):
        raise ResearchSourceError("Duplicate secondary current-membership symbol")
    return set(names)


def _april_symbols(raw: bytes) -> set[str]:
    try:
        lines = raw.decode("utf-8-sig").splitlines()
    except UnicodeDecodeError as exc:
        raise ResearchSourceError("Malformed monthly reference") from exc
    names = [line.split("\t")[0].strip().upper() for line in lines if line.strip()]
    if not names or len(names) != len(set(names)):
        raise ResearchSourceError("Malformed monthly reference member list")
    return set(names)


def research_report(history_raw: bytes, snapshots: list[date], *,
                    current_raw: bytes | None = None,
                    april_raw: bytes | None = None,
                    retrieved_at: str | None = None) -> dict:
    history = parse_history(history_raw)
    retrieved = retrieved_at or datetime.now(timezone.utc).isoformat()
    results = []
    for day in snapshots:
        if not isinstance(day, date):
            raise ResearchSourceError("Snapshot date must be explicit")
        active = asof_members(history, day)
        flags = [r for r in active if r["date_approximate"]]
        unknown_at_signal = [r for r in active if r["first_source_recorded_on"] > day]
        results.append({
            "date": day.isoformat(),
            "count": len(active),
            "approximate_date_count": len(flags),
            "not_recorded_by_snapshot_count": len(unknown_at_signal),
            "quality_flags": (["UNUSUAL_COMPONENT_COUNT"] if not 490 <= len(active) <= 510 else [])
                           + (["APPROXIMATE_EFFECTIVE_DATES"] if flags else [])
                           + (["RETROSPECTIVELY_RECONSTRUCTED"] if unknown_at_signal else []),
            "members": [{
                "ticker": r["ticker"], "cik": r["cik"], "sector": r["sector"],
                "effective_from": r["effective_from"].isoformat(),
                "effective_until": r["effective_until"].isoformat() if r["effective_until"] else None,
                "approximate_effective_date": r["date_approximate"],
            } for r in active],
        })
    cross_checks = {}
    if current_raw is not None:
        # This reference is current, never a historical snapshot guarantee.
        current = _current_symbols(current_raw)
        candidate = {r["ticker"] for r in asof_members(history, datetime.fromisoformat(retrieved[:10]).date())}
        cross_checks["other_public_current"] = {
            "source": SOURCE_CURRENT,
            "source_sha256": hashlib.sha256(current_raw).hexdigest(),
            "history_count": len(candidate), "reference_count": len(current),
            "only_in_history": sorted(candidate-current),
            "only_in_reference": sorted(current-candidate),
            "asof_semantics": "LATEST_RETRIEVED_PUBLIC_LIST_NOT_ASOF_SIGNAL",
        }
    if april_raw is not None:
        day = date(2026, 4, 30)
        history_april = {normalize_alias(r["ticker"]) for r in asof_members(history, day)}
        reference_april = {normalize_alias(x) for x in _april_symbols(april_raw)}
        cross_checks["april_2026_monthly"] = {
            "source": SOURCE_APRIL_2026,
            "source_sha256": hashlib.sha256(april_raw).hexdigest(),
            "history_count": len(history_april), "reference_count": len(reference_april),
            "only_in_history": sorted(history_april - reference_april),
            "only_in_reference": sorted(reference_april - history_april),
            "asof_semantics": "PUBLIC_MONTH_END_RECONSTRUCTION_DISAGREEMENTS_UNRESOLVED",
        }
    return {
        "schema": "gem-public-membership-research-v1",
        "classification": "UNVERIFIED_SECONDARY_RESEARCH_NOT_GEM_CERTIFICATION",
        "frozen_gem_strategy_unchanged": True,
        "paper_execution_authorized": False,
        "primary_sp_dji_source": False,
        "retrieved_at": retrieved,
        "source": SOURCE_HISTORY,
        "source_sha256": hashlib.sha256(history_raw).hexdigest(),
        "source_bytes": len(history_raw),
        "history_intervals": len(history),
        "approximate_interval_count": sum(r["date_approximate"] for r in history),
        "snapshots": results,
        "cross_checks": cross_checks,
        "blockers": [
            "Original index constituent effective-date announcements unavailable",
            "Secondary data includes approximate membership dates and retrospective corrections",
            "Separate security ID/share-class actions and independent QA required",
            "Reconstructed research snapshots cannot certify a past observable trading universe",
        ],
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Research only; cannot certify GEM trading inputs")
    parser.add_argument("--date", action="append", required=True,
                        help="Explicit YYYY-MM-DD research snapshot. Repeat for additional dates.")
    parser.add_argument("--out", required=True, help="Path for local JSON research output")
    parser.add_argument("--cross-checks", action="store_true",
                        help="Compare secondary current list and April 2026 monthly snapshot")
    args = parser.parse_args()
    snapshots = [date.fromisoformat(item) for item in args.date]
    historical = fetch_public_source(SOURCE_HISTORY)
    current = fetch_public_source(SOURCE_CURRENT) if args.cross_checks else None
    april = fetch_public_source(SOURCE_APRIL_2026) if args.cross_checks else None
    report = research_report(historical, snapshots, current_raw=current, april_raw=april)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "classification": report["classification"],
        "source_sha256": report["source_sha256"],
        "snapshots": [{k: v for k, v in x.items() if k != "members"} for x in report["snapshots"]],
        "cross_checks": report["cross_checks"],
        "trading_authorized": False,
    }, indent=2))


if __name__ == "__main__":
    main()
