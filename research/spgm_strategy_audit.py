"""Offline completeness audit; no downloads, strategy imports or sector guesses."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from research.spgm_proxy import identifier_keys, write_csv
from research.spgm_sources import DEFAULT_OUTPUT, LABEL, ROOT
from research.spgm_universe import lei_valid, queries_for, normalized_name

# Additional aliases were observed in the cached 21 portfolios. Queries only:
# no eligibility, sector, country, listing or price mapping is derived from names.
EXTRA_QUERIES = {
    "Alphabet": r"^ALPHABET INC(?: CL [AC])?$",
    "Amazon": r"^AMAZON COM INC$", "Meta Platforms": r"^META PLATFORMS INC(?: CLASS A)?$",
    "Oracle": r"^ORACLE CORP$", "Adobe": r"^ADOBE INC$",
    "Salesforce": r"^SALESFORCE INC$", "ServiceNow": r"^SERVICENOW INC$",
    "SAP": r"^SAP SE$", "Hon Hai": r"^HON HAI PRECISION (?:INDUSTRY CO LTD|GDR REG S)$",
    "Samsung Electro-Mechanics": r"^SAMSUNG ELECTRO MECHANICS CO$",
}


def audit_queries(row):
    name = normalized_name(row["name"])
    return queries_for(row) + tuple(k for k, pattern in EXTRA_QUERIES.items()
                                   if re.fullmatch(pattern, name))


def dated_verified(row, prefix, cutoff):
    """Current, inferred, undated or future metadata cannot pass a PIT gate."""
    if row.get(prefix + "_verification") != "historically_verified":
        return False
    if not row.get(prefix + "_source_url"):
        return False
    try:
        available = datetime.fromisoformat(row[prefix + "_available_at"])
        decision = datetime.fromisoformat(cutoff)
        start = datetime.fromisoformat(row[prefix + "_effective_from"])
        end = datetime.fromisoformat(row[prefix + "_effective_to"]) if row.get(prefix + "_effective_to") else None
        return bool(available.tzinfo and start.tzinfo and decision.tzinfo
                    and available < decision and start <= decision
                    and (end is None or end.tzinfo and decision < end))
    except (KeyError, ValueError, TypeError):
        return False


def metrics(rows, cutoff):
    identifier_issuers = defaultdict(set)
    for row in rows:
        if lei_valid(row.get("company_lei", "")):
            for key in identifier_keys(row):
                identifier_issuers[key].add(row["company_lei"])
    conflicts = {key for key, values in identifier_issuers.items() if len(values) > 1}
    gics = [r for r in rows if r.get("sector") and r.get("sector_scheme") == "GICS"
            and dated_verified(r, "sector", cutoff)]
    listings = [r for r in rows if r.get("pit_ticker") and r.get("exchange_mic")
                and r.get("currency") and identifier_keys(r)
                and dated_verified(r, "listing", cutoff)]
    return dict(securities=len(rows), valid_typed_identifier=sum(bool(identifier_keys(r)) for r in rows),
                identifier_problem_rows=sum(bool(r.get("identifier_problems")) for r in rows),
                identifier_issuer_conflict_rows=sum(bool(set(identifier_keys(r)) & conflicts) for r in rows),
                missing_verified_issuer_lei=sum(not lei_valid(r.get("company_lei", "")) for r in rows),
                ambiguous_company_identity=sum(r.get("company_lei_resolution") == "ambiguous" for r in rows),
                ticker_observed=sum(bool(r.get("pit_ticker")) for r in rows),
                ticker_ambiguous=sum(r.get("pit_ticker_status") == "ambiguous" for r in rows),
                verified_listing=len(listings), historical_gics_verified=len(gics),
                nonverified_sector_labels=sum(bool(r.get("sector")) for r in rows)-len(gics))


def read_rows(path):
    with gzip.open(path, "rt", newline="") as f:
        return list(csv.DictReader(f))


def run(input_dir):
    input_dir = Path(input_dir).resolve()
    if ROOT.resolve() not in input_dir.parents:
        raise ValueError("Inputs and outputs must stay in ignored research/eodhd_output")
    out = input_dir.parent / "strategy_audit"
    out.mkdir(exist_ok=True)
    monthly = json.loads((input_dir / "monthly_summary.json").read_text())
    if len(monthly) != 48 or len({r["selection_month"] for r in monthly}) != 48:
        raise ValueError("Expected 48 distinct monthly universes")
    results, leaders, hashes = [], [], {}
    for month in monthly:
        path = input_dir / month["eligible_file"]
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        rows = read_rows(path)
        cutoff = month["selection_cutoff_utc"]
        if len(rows) != month["eligible_common_equity_securities"]:
            raise ValueError("Monthly count mismatch")
        if any(datetime.fromisoformat(r["available_at"]) >= datetime.fromisoformat(cutoff) for r in rows):
            raise ValueError("Non-public membership at selection cutoff")
        result = {"month": month["selection_month"], **metrics(rows, cutoff),
                  "provisional_instruments": month["provisional_unclassified_securities"],
                  "age_days": month["source_portfolio_age_days"],
                  "source_snapshot_id": month["source_snapshot_id"],
                  "country_US": json.loads(month["country_distribution_json"]).get("US", 0)}
        results.append(result)
        eligible = defaultdict(list)
        provisional = defaultdict(list)
        for row in rows:
            for company in audit_queries(row):
                eligible[company].append(row)
        for row in read_rows(input_dir / month["provisional_file"]):
            for company in audit_queries(row):
                provisional[company].append(row)
        for company in sorted(eligible.keys() | provisional.keys()):
            leaders.append({"month": result["month"], "company": company,
                            **metrics(eligible[company], cutoff),
                            "provisional_lines": len(provisional[company])})
    totals = {key: sum(r[key] for r in results) for key in metrics([], "2026-01-01T00:00:00+00:00")}
    summary = {"dataset_label": LABEL, "months": 48, "security_month_totals": totals,
               "months_without_any_observed_ticker": sum(r["ticker_observed"] == 0 for r in results),
               "months_with_provisional_instruments": sum(r["provisional_instruments"] > 0 for r in results),
               "eodhd_requests": 0, "strategy_executed": False,
               "ready_for_faithful_exploratory_backtest": False,
               "input_hashes": hashes}
    write_csv(out / "monthly_completeness.csv", results)
    write_csv(out / "priority_completeness.csv", leaders)
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    lines = ["# SPGM strategy input completeness", "", f"**{LABEL} — not official MSCI ACWI IMI constituents.**", "",
             "48 monthly cutoffs, October 2022–September 2026. Counts below are security-month observations, not unique securities. This audit is offline; source observations are preserved and no classifications are assigned.", "",
             "| Metric | Count | Coverage of eligible security-months |", "|---|---:|---:|"]
    for key, count in totals.items():
        lines.append(f"| {key} | {count:,} | {count / totals['securities']:.2%} |")
    lines += ["", "Every eligible row has at least one checksum-valid typed ID; that does not verify a listing. Identifier-problem rows can retain an invalid alternate alongside a valid ID. Zero observed conflicts does not certify issuer identity. Missing issuer LEIs remain unresolved risks; names supply estimated company groups only.", "",
              "Ticker observations are prior-public source evidence, not exchange-qualified symbols. Historical GICS and listings require effective intervals, prior-public timestamps and cited verification. Current/inferred labels fail these gates. Sector coverage by country cannot be estimated because no verified sectors exist in any country.", "",
              "| Month | Securities | Ticker observed | Valid LEI | ID issue rows | ID/issuer conflicts | Ambiguous tickers | Verified listings | Verified GICS | Provisional | US issuer share |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in results:
        n = r["securities"]
        lines.append(f"| {r['month']} | {n} | {r['ticker_observed']} ({r['ticker_observed']/n:.1%}) | {n-r['missing_verified_issuer_lei']} | {r['identifier_problem_rows']} | {r['identifier_issuer_conflict_rows']} | {r['ticker_ambiguous']} | {r['verified_listing']} | {r['historical_gics_verified']} | {r['provisional_instruments']} | {r['country_US']/n:.1%} |")
    lines += ["", "## Priority company diagnostics", "",
              "Historical source-name audit queries only; this list does not filter the universe or establish GICS classifications. Month counts can overlap between eligible and provisional share lines. Technology/memory priorities are a research work order, not a verified sector map.", "",
              "| Company | Eligible months | Provisional months | Eligible security-months | Ticker observations | LEI gaps | Historical GICS | Verified listings |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for company in sorted({r["company"] for r in leaders}):
        group = [r for r in leaders if r["company"] == company]
        lines.append(f"| {company} | {sum(r['securities']>0 for r in group)} | {sum(r['provisional_lines']>0 for r in group)} | {sum(r['securities'] for r in group)} | {sum(r['ticker_observed'] for r in group)} | {sum(r['missing_verified_issuer_lei'] for r in group)} | {sum(r['historical_gics_verified'] for r in group)} | {sum(r['verified_listing'] for r in group)} |")
    (out / "completeness.md").write_text("\n".join(lines) + "\n")
    return out, summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_OUTPUT / "point_in_time_universe")
    out, summary = run(parser.parse_args().input)
    print(json.dumps({"output": str(out), "totals": summary["security_month_totals"]}))
