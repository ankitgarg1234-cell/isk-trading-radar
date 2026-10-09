"""Offline point-in-time stock-membership audit; never runs a strategy or API.

Confirmed common-equity membership and unclassified publisher candidates remain
separate. Historical metadata joins use only public observations before cutoff.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path

from research.spgm_proxy import identifier_keys, month_ends, write_csv
from research.spgm_sources import DEFAULT_OUTPUT, LABEL, PublicCache

# Query aliases identify historically observed rows, never establish membership,
# instrument eligibility, company-parent relationships, or sector classifications.
COMPANY_QUERIES = {
    "NVIDIA": r"^NVIDIA CORP$", "Microsoft": r"^MICROSOFT CORP$",
    "Apple": r"^APPLE INC$", "Tesla": r"^TESLA INC$", "Micron": r"^MICRON TECHNOLOGY INC$",
    "TSMC": r"^TAIWAN SEMICONDUCTOR (?:MANUFACTURING CO LTD|MANUFAC|SP ADR)$",
    "SK Hynix": r"^SK HYNIX INC$", "Broadcom": r"^BROADCOM INC$",
    "ASML": r"^ASML HOLDING N ?V$", "AMD": r"^ADVANCED MICRO DEVICES(?: INC)?$",
    "Samsung Electronics": r"^SAMSUNG ELECTRONICS (?:CO LTD|PREF)$",
    "Applied Materials": r"^APPLIED MATERIALS INC$", "Lam Research": r"^LAM RESEARCH CORP$",
    "KLA": r"^KLA CORP$", "Qualcomm": r"^QUALCOMM INC$", "Intel": r"^INTEL CORP$",
    "Texas Instruments": r"^TEXAS INSTRUMENTS INC$", "Tokyo Electron": r"^TOKYO ELECTRON LTD$",
    "NXP": r"^NXP SEMICONDUCTORS N ?V$", "Infineon": r"^INFINEON TECHNOLOGIES AG$",
    "STMicroelectronics": r"^STMICROELECTRONICS N ?V$", "MediaTek": r"^MEDIATEK INC$",
    "United Microelectronics": r"^UNITED MICROELECTRON(?:ICS CORP| SP ADR)$",
    "ASE Technology": r"^ASE TECHNOLOGY HOLDING CO LT[D]?$",
}


def normalized_name(name):
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9]+", " ", name.upper())).strip()


def lei_valid(value):
    if not re.fullmatch(r"[A-Z0-9]{18}[0-9]{2}", value or ""):
        return False
    digits = "".join(str(ord(x) - 55) if x.isalpha() else x for x in value)
    return int(digits) % 97 == 1


def country_usable(value):
    # XX is an observed unspecified/stapled-security placeholder, not a country.
    return bool(re.fullmatch(r"[A-Z]{2}", value or "")) and value not in {"XX", "ZZ"}


def positive_balance(row):
    try:
        value = Decimal(row.get("balance", ""))
        return value.is_finite() and value > 0
    except InvalidOperation:
        return False


def public_before(snapshot, cutoff):
    decision = datetime.fromisoformat(cutoff)
    if decision.tzinfo is None:
        raise ValueError("Decision needs an explicit timezone")
    return (datetime.fromisoformat(snapshot["available_at"]) < decision
            and snapshot["portfolio_date"] <= decision.date().isoformat())


def latest_public(snapshots, cutoff, sec_only=False):
    choices = [s for s in snapshots if public_before(s, cutoff)
               and (not sec_only or s["source_type"] == "SEC NPORT-P")]
    return max(choices, key=lambda s: (s["portfolio_date"], s["available_at"], s["snapshot_id"])) if choices else None


def evidence_index(snapshots, groups, cutoff):
    index = defaultdict(list)
    for s in snapshots:
        if public_before(s, cutoff):
            for row in groups[s["snapshot_id"]]:
                if row["available_at"] != s["available_at"] or row["portfolio_date"] != s["portfolio_date"]:
                    raise ValueError("Holding provenance disagrees with snapshot")
                for key in identifier_keys(row):
                    index[key].append(row)
    return index


def history_candidates(row, index, predicate):
    candidates = {}
    for key in identifier_keys(row):
        for record in index.get(key, []):
            if predicate(record) and record["portfolio_date"] <= row["portfolio_date"]:
                candidates[(record["snapshot_id"], record["row_number"])] = record
    choices = list(candidates.values())
    if not choices:
        return []
    latest = max((r["portfolio_date"], r["available_at"]) for r in choices)
    return [r for r in choices if (r["portfolio_date"], r["available_at"]) == latest]


def provenance(row):
    return {k: row[k] for k in ("snapshot_id", "row_number", "portfolio_date", "publication_date", "available_at")}


def eligibility(row, index):
    if not positive_balance(row):
        return "excluded", "non_positive_or_invalid_units", []
    if not identifier_keys(row):
        return "excluded", "no_valid_typed_security_identifier", []
    asset = row["asset_category"]
    if asset == "EC":
        return "eligible", "SEC common equity", [row]
    if asset != "unclassified":
        return "excluded", "not_SEC_common_equity:" + asset, [row]
    candidates = history_candidates(row, index, lambda r: r["asset_category"] != "unclassified")
    classes = {r["asset_category"] for r in candidates}
    if classes == {"EC"}:
        return "eligible", "prior public SEC common-equity class via exact identifier", candidates
    if len(classes) > 1:
        return "provisional", "conflicting public instrument classes", candidates
    if classes:
        return "excluded", "prior public SEC class:" + next(iter(classes)), candidates
    # A ticker, SEDOL, name or non-zero portfolio weight cannot establish stock
    # type. In particular, do not classify cash/futures from a name blacklist.
    return "provisional", "publisher instrument class unavailable", []


def resolve_field(row, index, field, predicate=lambda _: True):
    if row.get(field) and predicate(row[field]):
        return row[field], "source", [row]
    choices = history_candidates(row, index, lambda r: bool(r.get(field)) and predicate(r[field]))
    values = {r[field] for r in choices}
    if len(values) == 1:
        return values.pop(), "prior public exact-identifier evidence", choices
    return "", "ambiguous" if len(values) > 1 else "missing", choices


def ticker_at_cutoff(row, index):
    # Do not read spgm_proxy's retrospective mapped_ticker column. Only source
    # tickers in strictly prior-public source rows may enter this output.
    choices = history_candidates(row, index, lambda r: bool(r.get("source_ticker")))
    symbols = {r["source_ticker"] for r in choices}
    if len(symbols) == 1:
        symbol = symbols.pop()
        return symbol, "source" if any(r["snapshot_id"] == row["snapshot_id"] for r in choices) else "prior public identifier mapping; venue unverified", choices
    return "", "ambiguous" if len(symbols) > 1 else "missing", choices


def construct(selected, groups, index, cutoff):
    raw = groups[selected["snapshot_id"]]
    eligible, provisional, excluded = [], [], []
    for original in raw:
        status, reason, stock_evidence = eligibility(original, index)
        # Retrospective lookup fields may contain future evidence. Original rows
        # remain untouched; omit those fields from point-in-time derived records.
        row = {k: v for k, v in original.items() if k not in {"mapped_ticker", "ticker_mapping_status",
               "ticker_mapping_portfolio_date", "ticker_mapping_available_at", "ticker_mapping_snapshot"}}
        row.update({"selection_cutoff_utc": cutoff, "eligibility": status, "eligibility_reason": reason,
                    "stock_type_evidence_json": json.dumps([provenance(r) for r in stock_evidence]),
                    "original_country": original["country"], "original_country_basis": original.get("country_basis", ""),
                    "original_company_lei": original["company_lei"]})
        for field, predicate in (("country", country_usable), ("company_lei", lei_valid)):
            value, basis, records = resolve_field(original, index, field, predicate)
            row[field] = value
            row[field + "_resolution"] = basis
            row[field + "_evidence_json"] = json.dumps([provenance(r) for r in records])
        row["country_basis"] = ("SEC issuer organization country, source or disclosed older exact-ID evidence"
                                if row["country"] else "unknown; not inferred from currency, name or ISIN")
        ticker, basis, records = ticker_at_cutoff(original, index)
        row.update({"pit_ticker": ticker, "pit_ticker_status": basis,
                    "pit_ticker_evidence_json": json.dumps([provenance(r) for r in records]),
                    "instrument_key": ":".join(identifier_keys(original)[0]) if identifier_keys(original) else ""})
        (eligible if status == "eligible" else provisional if status == "provisional" else excluded).append(row)
    return deduplicate(eligible), deduplicate(provisional), excluded


def deduplicate(rows):
    # Union identifiers within the chosen portfolio, not companies/share classes.
    parents = {}
    def root(key):
        parents.setdefault(key, key)
        while parents[key] != key:
            parents[key] = parents[parents[key]]
            key = parents[key]
        return key
    for row in rows:
        keys = identifier_keys(row)
        if keys:
            first = root(keys[0])
            for key in keys[1:]:
                parents[root(key)] = first
    groups = defaultdict(list)
    for row in rows:
        groups[root(identifier_keys(row)[0])].append(row)
    result = []
    for key, records in sorted(groups.items()):
        representative = dict(records[0])
        representative["instrument_key"] = ":".join(key)
        representative["source_position_rows_json"] = json.dumps([provenance(r) for r in records])
        representative["source_position_count"] = len(records)
        for field in ("country", "company_lei", "pit_ticker"):
            values = {r[field] for r in records if r[field]}
            if len(values) > 1:
                representative[field] = ""
                representative["pit_ticker_status" if field == "pit_ticker" else field + "_resolution"] = "ambiguous"
        result.append(representative)
    return result


def company_counts(rows):
    name_to_lei = defaultdict(set)
    for row in rows:
        if row["company_lei"]:
            name_to_lei[normalized_name(row["name"])].add(row["company_lei"])
    groups, leis, unlinked, ambiguous = set(), set(), 0, 0
    for row in rows:
        name = normalized_name(row["name"])
        if row["company_lei"]:
            leis.add(row["company_lei"])
            group = "lei:" + row["company_lei"]
        elif len(name_to_lei[name]) == 1:
            group = "lei:" + next(iter(name_to_lei[name]))
            unlinked += 1
        else:
            group = "source_name_estimate:" + (name or row["instrument_key"])
            unlinked += 1
            ambiguous += int(len(name_to_lei[name]) > 1 or row["company_lei_resolution"] == "ambiguous")
        groups.add(group)
        row["company_group_estimate"] = group
    return {"unique_company_count_exact": "unknown_without_complete_issuer_crosswalk",
            "estimated_unique_company_groups": len(groups), "distinct_LEI_identified_issuers": len(leis),
            "securities_without_verified_issuer_lei": unlinked, "ambiguous_company_identity_securities": ambiguous}


@lru_cache(maxsize=32768)
def queries_for_name(value):
    name = normalized_name(value)
    return tuple(company for company, pattern in COMPANY_QUERIES.items() if re.fullmatch(pattern, name))


def queries_for(row):
    return queries_for_name(row["name"])


def gzip_csv(path, rows):
    # Stable gzip timestamps make offline reproductions byte-comparable.
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("wb") as file:
        with gzip.GzipFile(fileobj=file, mode="wb", mtime=0) as zipped:
            with io.TextIOWrapper(zipped, encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)


def build(output=DEFAULT_OUTPUT):
    cache = PublicCache(output)  # Never fetch.
    snapshots = json.loads((cache.output / "snapshots.json").read_text())
    with (cache.output / "holdings.csv").open() as stream:
        holdings = list(csv.DictReader(stream))
    groups = defaultdict(list)
    for row in holdings:
        groups[row["snapshot_id"]].append(row)
    if len(snapshots) != 21 or any(len(groups[s["snapshot_id"]]) != s["holdings_count"] for s in snapshots):
        raise ValueError("Expected all 21 audited portfolios with reconciled position counts")
    out = cache.output / "point_in_time_universe"
    out.mkdir(exist_ok=True)
    monthly, appearances, evidence, country_rows, exclusions = [], [], [], [], []
    for end in month_ends():
        month = end.isoformat()[:7]
        cutoff = end.isoformat() + "T23:59:59+00:00"
        selected = latest_public(snapshots, cutoff)
        if selected is None:
            raise ValueError("No public portfolio for selection month")
        index = evidence_index(snapshots, groups, cutoff)
        eligible, provisional, rejected = construct(selected, groups, index, cutoff)
        companies = company_counts(eligible)
        countries = Counter(r["country"] or "UNKNOWN" for r in eligible)
        for country, count in sorted(countries.items()):
            country_rows.append({"selection_month": month, "country": country, "eligible_securities": count,
                                 "basis": "source investment country or disclosed prior-public exact-ID join; not MSCI country"})
        sec = latest_public(snapshots, cutoff, sec_only=True)
        sec_rows, _, _ = construct(sec, groups, index, cutoff)
        summary = {"selection_month": month, "selection_cutoff_utc": cutoff,
                   "eligible_common_equity_securities": len(eligible), **companies,
                   "source_portfolio_date": selected["portfolio_date"], "source_publication_date": selected.get("publication_date", ""),
                   "source_available_at": selected["available_at"], "source_snapshot_id": selected["snapshot_id"],
                   "source_url": selected["source_url"], "source_sha256": selected["sha256"],
                   "source_portfolio_age_days": (end - datetime.fromisoformat(selected["portfolio_date"]).date()).days,
                   "country_distribution_json": json.dumps(dict(sorted(countries.items())), sort_keys=True),
                   "country_missing": countries["UNKNOWN"],
                   "original_country_unspecified_rows": sum(not country_usable(r["original_country"]) for r in eligible),
                   "country_from_prior_identifier_evidence": sum(r["country_resolution"] == "prior public exact-identifier evidence" for r in eligible),
                   "missing_ticker": sum(r["pit_ticker_status"] == "missing" for r in eligible),
                   "ambiguous_ticker": sum(r["pit_ticker_status"] == "ambiguous" for r in eligible),
                   "unverified_listing_venue": len(eligible),
                   "missing_security_sector": sum(not r["sector"] for r in eligible),
                   "missing_historical_gics": len(eligible),
                   "provisional_unclassified_securities": len(provisional), "excluded_position_rows": len(rejected),
                   "duplicate_position_rows_collapsed": sum(r["source_position_count"] - 1 for r in eligible),
                   "latest_public_SEC_only_securities_alternative": len(sec_rows),
                   "latest_public_SEC_only_portfolio_date": sec["portfolio_date"],
                   "eligible_file": month + "_eligible.csv.gz", "provisional_file": month + "_provisional.csv.gz"}
        monthly.append(summary)
        for rows, suffix in ((eligible, "eligible"), (provisional, "provisional")):
            for row in rows:
                row["source_url"] = selected["source_url"]
                row["source_filing"] = selected["snapshot_id"] if selected["source_type"] == "SEC NPORT-P" else ""
            gzip_csv(out / (month + "_" + suffix + ".csv.gz"), rows)
        excluded_counts = Counter(r["eligibility_reason"] for r in rejected)
        exclusions.extend({"selection_month": month, "exclusion_reason": reason, "position_rows": count}
                          for reason, count in sorted(excluded_counts.items()))
        raw = groups[selected["snapshot_id"]]
        named = []
        for collection in (eligible, provisional, raw, sec_rows):
            by_company = defaultdict(list)
            for row in collection:
                for company in queries_for(row):
                    by_company[company].append(row)
            named.append(by_company)
        for company in COMPANY_QUERIES:
            strict, conditional, observed, alternatives = [lookup[company] for lookup in named]
            appearances.append({"company_query": company, "selection_month": month,
                                "eligible": bool(strict), "eligible_security_lines": len(strict),
                                "provisional": bool(conditional), "observed_in_latest_public_portfolio": bool(observed),
                                "eligible_in_SEC_only_alternative": bool(alternatives),
                                "source_portfolio_date": selected["portfolio_date"], "source_available_at": selected["available_at"],
                                "matching_basis": "explicit historical-source-name query; not a current constituent crosswalk"})
            for row in strict + conditional:
                evidence.append({"company_query": company, "selection_month": month, **row})
    write_csv(out / "monthly_summary.csv", monthly)
    write_csv(out / "country_distribution.csv", country_rows)
    write_csv(out / "company_appearances.csv", appearances)
    write_csv(out / "eligibility_exclusions.csv", exclusions)
    gzip_csv(out / "company_appearance_evidence.csv.gz", evidence)
    (out / "monthly_summary.json").write_text(json.dumps(monthly, indent=2) + "\n")
    manifest = {"dataset_label": LABEL, "universe_label": "strictly prior-public common-equity proxy; not strategy-qualified selections",
                "selection_dates": len(monthly), "portfolios_used_as_input": len(snapshots),
                "cutoff_policy": "calendar month-end 23:59:59 UTC; publication strictly earlier",
                "exact_company_counts_available": False, "eodhd_requests": 0,
                "input_snapshots_sha256": hashlib.sha256((cache.output / "snapshots.json").read_bytes()).hexdigest(),
                "input_holdings_sha256": hashlib.sha256((cache.output / "holdings.csv").read_bytes()).hexdigest(),
                "monthly_files_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                         for p in sorted(out.glob('*.csv.gz'))}}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"selection_dates": len(monthly), "eligible_security_range": [min(r["eligible_common_equity_securities"] for r in monthly), max(r["eligible_common_equity_securities"] for r in monthly)],
                      "output": str(out), "eodhd_requests": 0}, indent=2))
    return monthly, appearances


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    build(args.output)
