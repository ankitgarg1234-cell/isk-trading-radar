"""Read-only deterministic triage and independent SEC cache rechecks, stdlib only.

No download, trading, strategy mutation, or automatic case certification occurs.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .workflow import FROZEN_COMMIT, SCHEMA_VERSION, audit_events, case_id

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
ARCHIVE = REPO / "research_5x/gem_2025_2026_validation"
INPUT_NAMES = (
    "potentially_displacing_competitors.csv", "stock_selection_audit.csv",
    "signal_audit.csv.gz", "sec_minimal_evidence.json.gz", "pit_data_coverage.csv",
    "public_source_manifest.csv", "security_identifier_map.json",
    "frozen_config.json", "strategy_frozen_spec.md",
)
ALIASES = {
    "TotalRevenue": {"RevenueFromContractWithCustomerExcludingAssessedTax",
                     "RevenueFromContractWithCustomerIncludingAssessedTax", "Revenues",
                     "SalesRevenueNet", "SalesRevenueGoodsNet", "SalesRevenueServicesNet",
                     "RevenueFromContractWithCustomer", "Revenue"},
    "NetIncome": {"NetIncomeLoss", "ProfitLoss", "NetIncomeLossAvailableToCommonStockholdersBasic"},
    "OperatingIncome": {"OperatingIncomeLoss"},
}


def csv_rows(path: Path) -> list[dict]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", newline="") as stream:
        return list(csv.DictReader(stream))


def number(value: object) -> float | None:
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def evidence_key(row: dict) -> tuple:
    return tuple(row.get(key) for key in ("signal_date", "ticker", "concept", "period_end", "accession"))


def utc_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Naive acceptance timestamp prohibited")
    return parsed.astimezone(timezone.utc)


def recheck_use(use: dict, evidence: dict | None, manifest: dict) -> dict:
    """Recheck retained primary-derived facts; do not trust fact_status labels."""
    errors = []
    matched = []
    asof = date.fromisoformat(use["signal_date"]) - timedelta(days=1)
    if evidence is None:
        errors.append("MISSING_RETAINED_ACCESSION_EVIDENCE")
    else:
        if evidence_key(use) != evidence_key(evidence) or evidence.get("cik") != use.get("cik"):
            errors.append("ACCESSION_PERIOD_OR_IDENTITY_MISMATCH")
        fact_url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{use['cik']}.json"
        source_hash = use.get("sec_raw_response_sha256", "")
        source = manifest.get(fact_url, {})
        if (use.get("sec_facts_url") != fact_url or evidence.get("source_sha256") != source_hash
                or source.get("sha256") != source_hash or source.get("status") != "200"):
            errors.append("FACT_SOURCE_MANIFEST_MISMATCH")
        submission = manifest.get(use.get("submissions_url"), {})
        if submission.get("sha256") != use.get("submissions_response_sha256") or submission.get("status") != "200":
            errors.append("ACCEPTANCE_SOURCE_MANIFEST_MISMATCH")
        try:
            actual = utc_time(evidence.get("sec_accepted_at") or "")
            if actual != utc_time(use.get("sec_accepted_at") or ""):
                errors.append("RETAINED_ACCEPTANCE_DISAGREES")
            if actual >= utc_time(use["signal_timestamp"]):
                errors.append("ACCEPTANCE_AT_OR_AFTER_SIGNAL")
            if actual.astimezone(ZoneInfo("America/New_York")).date() > asof:
                errors.append("ACCEPTANCE_AFTER_PREVIOUS_DAY_CUTOFF")
        except (ValueError, TypeError, KeyError):
            errors.append("ACCEPTANCE_UNVERIFIED")
        wanted = number(use.get("used_value"))
        for fact in evidence.get("direct_quarter_facts", []):
            try:
                span = (date.fromisoformat(fact["end"]) - date.fromisoformat(fact["start"])).days
                value = number(fact.get("val"))
                valid = (fact.get("accn") == use["accession"] and fact.get("end") == use["period_end"]
                         and fact.get("tag") in ALIASES.get(use["concept"], set())
                         and fact.get("form") in {"10-Q", "10-Q/A"} and 60 <= span <= 125
                         and date.fromisoformat(fact["filed"]) <= asof
                         and wanted is not None and value is not None
                         and abs(value - wanted) <= max(.01, abs(wanted) * 1e-9))
                if valid:
                    matched.append(fact)
            except (ValueError, TypeError, KeyError):
                pass
        if not matched:
            errors.append("NO_TIMELY_MATCHING_10Q_DIRECT_QUARTER")
        elif not any(fact.get("start") == use.get("period_start") for fact in matched):
            errors.append("DIRECT_PERIOD_START_LINEAGE_MISMATCH_OR_ABSENT")
    return {"ticker": use["ticker"], "signal_date": use["signal_date"],
            "concept": use["concept"], "period_end": use["period_end"],
            "accession": use["accession"], "used_value": use["used_value"],
            "sec_accepted_at": (evidence or {}).get("sec_accepted_at"),
            "source_sha256": (evidence or {}).get("source_sha256"),
            "previous_fact_status": use.get("fact_status"),
            "recheck_status": "CACHED_ACCESSION_VALUE_TIME_MATCH" if not errors else "UNRESOLVED",
            "matched_tags": sorted({x["tag"] for x in matched}),
            "exact_direct_period_start_matches": any(x.get("start") == use.get("period_start") for x in matched),
            "errors": sorted(set(errors)),
            "raw_sec_response_retained": False,
            "raw_acceptance_document_retained": False,
            "strict_case_certified": False}


def priority(row: dict, selected: list[dict]) -> tuple[str, int, float | None]:
    momentum = number(row.get("r63"))
    cutoff = min((number(x["r63"]) for x in selected), default=None)
    if momentum is None:
        return "P1_UNKNOWN_MOMENTUM", 1, None
    if momentum <= 0:
        return "P3_NONPOSITIVE_ARCHIVED_MOMENTUM", 3, momentum - (cutoff or 0)
    if cutoff is not None and momentum > cutoff:
        return "P0_ABOVE_OBSERVED_SELECTED_CUTOFF", 0, momentum - cutoff
    if cutoff is not None and momentum == cutoff:
        return "P1_TIE_REQUIRES_STABLE_ORDER", 1, 0.0
    if len(selected) < 5:
        return "P1_CAN_FILL_ARCHIVED_CASH_SLOT", 1, momentum - (cutoff or 0)
    return "P2_BELOW_OBSERVED_SELECTED_CUTOFF", 2, momentum - (cutoff or 0)


def impact_bound(selected: list[dict], cases: list[dict], include_unknown: bool) -> dict:
    """Conditional set bound with archived selected values held fixed.

    Assume every backlog candidate passes all other gates, not that any does.
    Unknown momenta may outrank all observations in the upper-bound scenario.
    """
    rows = [(number(r["r63"]), r["ticker"], True) for r in selected]
    for r in cases:
        score = number(r.get("archived_r63"))
        if score is None:
            if not include_unknown:
                continue
            score = math.inf
        if score > 0:
            rows.append((score, r["ticker"], False))
    # Archived panel iterates sorted tickers and then uses a stable r63 sort.
    rows.sort(key=lambda r: (-r[0], r[1]))
    top = rows[:5]
    old = {r["ticker"] for r in selected}
    new = {ticker for _, ticker, _ in top}
    return {"archived_selected_replacements_upper": len(old - new),
            "archived_cash_slots_filled_upper": max(0, len(top) - len(selected)),
            "changed_target_slots_upper": len(old - new) + max(0, len(top) - len(selected)),
            "hypothetical_top5": [ticker for _, ticker, _ in top],
            "is_certified_or_realized_impact": False}


def build(archive: Path = ARCHIVE, lock_path: Path = HERE / "frozen_inputs.lock.json") -> dict:
    hashes = {name: hashlib.sha256((archive / name).read_bytes()).hexdigest() for name in INPUT_NAMES}
    lock = json.loads(lock_path.read_text())
    if lock.get("frozen_commit") != FROZEN_COMMIT or hashes != lock.get("input_sha256"):
        raise ValueError("Frozen archive input drift: stop; do not accept replacement sources")
    queue = csv_rows(archive / "potentially_displacing_competitors.csv")
    if len(queue) != 943:
        raise ValueError("Expected the exact 943-case frozen backlog")
    securities = csv_rows(archive / "stock_selection_audit.csv")
    by_key = {(r["signal_date"], r["ticker"]): r for r in securities}
    if len(by_key) != len(securities) or len({(r["signal_date"], r["ticker"]) for r in queue}) != len(queue):
        raise ValueError("Duplicate archived security/date keys")
    selected = defaultdict(list)
    for row in securities:
        if row["selected_original_top5"] == "True":
            selected[row["signal_date"]].append(row)
    with gzip.open(archive / "sec_minimal_evidence.json.gz", "rt") as stream:
        minimal = json.load(stream)
    evidence = {}
    for row in minimal:
        key = evidence_key(row)
        if key in evidence and evidence[key] != row:
            raise ValueError("Contradictory retained SEC evidence")
        evidence[key] = row
    manifest = {r["url"]: r for r in csv_rows(archive / "public_source_manifest.csv")}
    identifiers = json.loads((archive / "security_identifier_map.json").read_text())
    backlog_keys = {(r["signal_date"], r["ticker"]) for r in queue}
    facts = defaultdict(list)
    rechecks = []
    for use in csv_rows(archive / "signal_audit.csv.gz"):
        key = (use["signal_date"], use["ticker"])
        if key in backlog_keys:
            result = recheck_use(use, evidence.get(evidence_key(use)), manifest)
            facts[key].append(result)
            rechecks.append(result)
    gaps = defaultdict(list)
    for row in csv_rows(archive / "pit_data_coverage.csv"):
        key = (row["signal_date"], row["ticker"])
        if key in backlog_keys:
            gaps[key].append({k: row[k] for k in ("field", "status", "required_period")})
    cases = []
    for original in queue:
        key = (original["signal_date"], original["ticker"])
        row = by_key[key]
        chosen = selected[key[0]]
        tier, tier_number, gap = priority(row, chosen)
        matched = sum(x["recheck_status"] == "CACHED_ACCESSION_VALUE_TIME_MATCH" for x in facts[key])
        case = {"schema_version": SCHEMA_VERSION, "case_id": case_id(*key),
                "frozen_commit": FROZEN_COMMIT, "signal_date": key[0], "ticker": key[1],
                "cik": identifiers.get(key[1], {}).get("cik"),
                "state": "EVIDENCE_REQUIRED", "priority_tier": tier,
                "priority_tier_number": tier_number, "archived_r63": number(row.get("r63")),
                "observed_selected_cutoff_r63": min((number(x["r63"]) for x in chosen), default=None),
                "r63_cutoff_gap": gap, "archived_selected_count": len(chosen),
                "selected_tickers_outranked_on_observed_momentum":
                    [x["ticker"] for x in chosen if number(row.get("r63")) is not None and number(row["r63"]) > number(x["r63"])],
                "cached_input_uses": len(facts[key]), "cached_proof_matches": matched,
                "unresolved_cached_input_uses": len(facts[key]) - matched,
                "missing_input_requirements": gaps[key],
                "archived_observed_gate_values": {"revenue_yoy": number(row.get("revenue_yoy")),
                                                 "margin_delta_pp": number(row.get("margin_delta_pp")),
                                                 "earnings_improvement": row.get("earnings_improvement")},
                "strict_case_certified": False,
                "mandatory_blockers": ["primary historical security identity and universe lineage",
                                       "raw original accession and acceptance source retention",
                                       "complete filing set / selected latest-period provenance",
                                       "price/action lineage", "independent reviewer signoff"]}
        cases.append(case)
    # Deterministic: ability to displace, number of incumbents outranked, gap,
    # then date/ticker. No forward performance or strategy threshold enters.
    cases.sort(key=lambda r: (r["priority_tier_number"],
                              -len(r["selected_tickers_outranked_on_observed_momentum"]),
                              -(r["r63_cutoff_gap"] if r["r63_cutoff_gap"] is not None else 0),
                              r["signal_date"], r["ticker"]))
    for index, case in enumerate(cases, 1):
        case["priority_sequence"] = index
    dates = []
    for ds in sorted({r["signal_date"] for r in cases}):
        day = [r for r in cases if r["signal_date"] == ds]
        dates.append({"signal_date": ds, "archived_selected_count": len(selected[ds]),
                      "backlog_cases": len(day), "priority_counts": dict(Counter(r["priority_tier"] for r in day)),
                      "observed_momentum_conditional_bound": impact_bound(selected[ds], day, False),
                      "unknown_momentum_conditional_bound": impact_bound(selected[ds], day, True),
                      "changed_slots_lower": 0, "return_impact": None})
    summary = {"schema_version": SCHEMA_VERSION, "frozen_commit": FROZEN_COMMIT,
               "scope": "943 frozen unresolved security/date cases; fixed archived prices and selected candidates",
               "cases": len(cases), "unique_tickers": len({r["ticker"] for r in cases}),
               "signal_dates": len(dates), "priority_counts": dict(Counter(r["priority_tier"] for r in cases)),
               "cached_input_uses_independently_rechecked": len(rechecks),
               "cached_recheck_status_counts": dict(Counter(r["recheck_status"] for r in rechecks)),
               "cached_recheck_error_counts": dict(Counter(e for r in rechecks for e in r["errors"])),
               "previous_status_counts": dict(Counter(r["previous_fact_status"] for r in rechecks)),
               "new_strictly_certified_cases": 0, "remaining_strict_certification_cases": len(cases),
               "dates_with_fewer_than_five_archived_selections": [r["signal_date"] for r in dates if r["archived_selected_count"] < 5],
               "observed_momentum_changed_slot_upper_sum": sum(r["observed_momentum_conditional_bound"]["changed_target_slots_upper"] for r in dates),
               "unknown_momentum_changed_slot_upper_sum": sum(r["unknown_momentum_conditional_bound"]["changed_target_slots_upper"] for r in dates),
               "changed_slot_lower_sum": 0, "return_impact": None,
               "warnings": ["Cache recheck is not fresh SEC source reacquisition or complete eligibility certification",
                            "Below-cutoff deferral assumes archived selected signals and price units remain fixed",
                            "Slot bounds assume every backlog candidate qualifies; not probabilities or return bounds",
                            "Exact audited historical returns remain uncertified; no tuning or future data used"]}
    return {"input_hashes": hashes, "cases": cases, "fact_rechecks": rechecks,
            "date_impact_bounds": dates, "summary": summary,
            "audit_events": audit_events(cases, hashes)}


def write_artifacts(result: dict, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for key in ("summary", "date_impact_bounds", "input_hashes"):
        (output / f"{key}.json").write_text(json.dumps(result[key], indent=2, sort_keys=True, allow_nan=False) + "\n")
    for key in ("cases", "fact_rechecks", "audit_events"):
        (output / f"{key}.jsonl").write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n" for row in result[key]))
    columns = ("priority_sequence", "case_id", "signal_date", "ticker", "cik", "state", "priority_tier",
               "archived_r63", "observed_selected_cutoff_r63", "r63_cutoff_gap", "archived_selected_count",
               "cached_input_uses", "cached_proof_matches", "unresolved_cached_input_uses", "strict_case_certified")
    with (output / "priority_queue.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(result["cases"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "artifacts")
    args = parser.parse_args()
    result = build()
    write_artifacts(result, args.output)
    print(json.dumps(result["summary"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
