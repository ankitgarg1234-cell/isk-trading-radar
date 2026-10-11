"""Offline review of newly retained original SEC bytes; no terminal case closure."""
from __future__ import annotations

import hashlib
import html
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

from .certify import ARCHIVE, HERE, build, csv_rows, utc_time

SEC_TIME_REFERENCE = "https://www.sec.gov/files/about/webmaster-faq.htm"
NS = {"x": "http://www.xbrl.org/2003/instance"}


def retained_bytes(directory: Path, record: dict) -> bytes:
    filename = record["raw_path"]
    if Path(filename).name != filename:
        raise ValueError("Retained path escapes source directory")
    raw = (directory / filename).read_bytes()
    if hashlib.sha256(raw).hexdigest() != record["response_sha256"]:
        raise ValueError("Retained original SEC response changed")
    return raw


def parse_header(raw: bytes) -> dict:
    text = html.unescape(raw.decode())
    result = {}
    for key, pattern in (("acceptance_raw", r"<ACCEPTANCE-DATETIME>(\d{14})"),
                         ("accession", r"<ACCESSION-NUMBER>([^\s<]+)"),
                         ("cik", r"<CIK>(\d+)"), ("form", r"<FORM-TYPE>([^\s<]+)"),
                         ("filing_date_raw", r"<FILING-DATE>(\d{8})")):
        found = set(re.findall(pattern, text))
        if len(found) != 1:
            raise ValueError(f"Missing or conflicting original SEC header field: {key}")
        result[key] = found.pop()
    # SEC FAQ literally describes Time (EST); daylight-aware interpretation is
    # a declared inference, not independently proven exact public availability.
    assumed_local = datetime.strptime(result["acceptance_raw"], "%Y%m%d%H%M%S").replace(tzinfo=ZoneInfo("America/New_York"))
    result["acceptance_utc_under_declared_ny_convention"] = assumed_local.astimezone(timezone.utc).isoformat()
    literal_est = datetime.strptime(result["acceptance_raw"], "%Y%m%d%H%M%S").replace(tzinfo=timezone(timedelta(hours=-5)))
    result["acceptance_utc_under_literal_fixed_est_alternative"] = literal_est.astimezone(timezone.utc).isoformat()
    result["timezone_interpretation_is_inference"] = True
    result["timezone_reference_url"] = SEC_TIME_REFERENCE
    result["proves_first_public_availability"] = False
    return result


def consolidated_quarter_facts(raw: bytes, cik: str) -> list[dict]:
    root = ET.fromstring(raw)
    contexts = {el.attrib["id"]: el for el in root.findall("x:context", NS)}
    units = {el.attrib["id"]: el.findtext("x:measure", namespaces=NS) for el in root.findall("x:unit", NS)}
    wanted_tags = {"RegulatedAndUnregulatedOperatingRevenue", "RevenueFromContractWithCustomerIncludingAssessedTax",
                   "RevenueNotFromContractWithCustomerOther", "OperatingIncomeLoss", "NetIncomeLoss"}
    found = {}
    period_values = {}
    for el in root:
        tag = el.tag.rsplit("}", 1)[-1]
        if tag not in wanted_tags or not el.tag.startswith("{http://fasb.org/us-gaap/"):
            continue
        context = contexts.get(el.attrib.get("contextRef"))
        if context is None or context.find("x:entity/x:segment", NS) is not None or context.find("x:scenario", NS) is not None:
            continue
        identifier = context.findtext("x:entity/x:identifier", namespaces=NS)
        if not identifier or identifier.lstrip("0") != cik.lstrip("0"):
            continue
        start = context.findtext("x:period/x:startDate", namespaces=NS)
        end = context.findtext("x:period/x:endDate", namespaces=NS)
        if (start, end) not in {("2024-07-01", "2024-09-30"), ("2023-07-01", "2023-09-30")}:
            continue
        unit = units.get(el.attrib.get("unitRef"))
        if not unit or unit.rsplit(":", 1)[-1] != "USD":
            continue
        exact_value = Decimal(el.text)
        if not exact_value.is_finite() or exact_value != exact_value.to_integral_value():
            raise ValueError("Noninteger or nonfinite USD fact requires separate review")
        value = int(exact_value)
        # Downstream concept dictionaries use local tag names and normalized
        # USD, so conflict checks must use that identical semantic key.
        period_key = (tag, start, end, "USD")
        if period_key in period_values and period_values[period_key] != value:
            raise ValueError("Conflicting consolidated values for the same tag/period/unit")
        period_values[period_key] = value
        key = (el.tag, start, end, value)
        found[key] = {"tag": tag, "qualified_tag": el.tag, "period_start": start, "period_end": end,
                      "value": value, "context_id": el.attrib["contextRef"], "unit": "USD", "consolidated": True}
    return sorted(found.values(), key=lambda x: (x["tag"], x["period_end"], x["value"]))


def exact_number_match(used: object, actual: object) -> bool:
    try:
        left, right = Decimal(str(used)), Decimal(str(actual))
        return left.is_finite() and right.is_finite() and left == right
    except (InvalidOperation, ValueError):
        return False


def frozen_earnings_pass(current: int, prior: int) -> bool:
    return current > 0 and (prior <= 0 or current / prior - 1 > .2)


def build_primary_review() -> dict:
    # Reuse exact frozen-input enforcement before any original-use lookup.
    build()
    uses = csv_rows(ARCHIVE / "signal_audit.csv.gz")
    headers_dir = HERE / "primary_acquisition_system"
    records = json.loads((headers_dir / "acquisition_summary.json").read_text())["records"]
    header_checks = []
    for record in records:
        header = parse_header(retained_bytes(headers_dir, record))
        if header["accession"] != record["accession"] or header["cik"] != record["cik"] or header["form"] != "10-Q":
            raise ValueError("Fetched header identity/form mismatch")
        use = next(x for x in uses if x["ticker"] == record["ticker"] and x["signal_date"] == record["signal_date"])
        interpreted = utc_time(header["acceptance_utc_under_declared_ny_convention"])
        cached = utc_time(use["sec_accepted_at"])
        header_checks.append({**header, "ticker": record["ticker"], "signal_date": record["signal_date"],
                              "source_url": record["url"], "response_sha256": record["response_sha256"],
                              "cached_sec_accepted_at": use["sec_accepted_at"],
                              "cached_minus_interpreted_seconds": int((cached - interpreted).total_seconds()),
                              "both_timestamps_precede_signal": interpreted < utc_time(use["signal_timestamp"]) and cached < utc_time(use["signal_timestamp"]),
                              "strict_case_certified": False,
                              "initial_acquisition_record_time_note": "retrieved_at_utc in original request records denotes request start, not first historical public availability"})
    xbrl_dir = HERE / "primary_xbrl"
    xbrl_records = json.loads((xbrl_dir / "acquisition_summary.json").read_text())["records"]
    awk = next(r for r in xbrl_records if r["ticker"] == "AWK" and r["status"] == "ACQUIRED_PENDING_REVIEW")
    facts = consolidated_quarter_facts(retained_bytes(xbrl_dir, awk), awk["cik"])
    revenue = {r["period_end"]: r["value"] for r in facts if r["tag"] == "RegulatedAndUnregulatedOperatingRevenue"}
    ni = {r["period_end"]: r["value"] for r in facts if r["tag"] == "NetIncomeLoss"}
    op = {r["period_end"]: r["value"] for r in facts if r["tag"] == "OperatingIncomeLoss"}
    resolutions = []
    for use in uses:
        if use["ticker"] == "AWK" and use["accession"] == awk["accession"] and use["concept"] == "TotalRevenue" and use["signal_date"] in {"2025-03-31", "2025-04-30"}:
            matched = exact_number_match(use["used_value"], revenue.get(use["period_end"]))
            resolutions.append({"signal_date": use["signal_date"], "period_end": use["period_end"],
                                "archive_used_value": use["used_value"], "original_accession_tag": "us-gaap:RegulatedAndUnregulatedOperatingRevenue",
                                "original_accession_value": revenue.get(use["period_end"]), "exact_value_match": matched,
                                "status": "FACT_VALUE_RECONCILED_SEMANTIC_MAPPING_PENDING_TWO_REVIEWS", "strict_case_certified": False})
    current, old = "2024-09-30", "2023-09-30"
    revenue_growth = revenue[current] / revenue[old] - 1
    income_growth = ni[current] / ni[old] - 1 if ni[old] > 0 else None
    margin_delta = 100 * (op[current] / revenue[current] - op[old] / revenue[old])
    return {"original_headers_acquired": len(header_checks), "original_xbrl_instances_acquired": 1,
            "header_checks": header_checks, "acceptance_normalization_discrepancies": sum(r["cached_minus_interpreted_seconds"] != 0 for r in header_checks),
            "timezone_policy_is_inference": True, "header_proves_public_availability": False,
            "awk_original_accession": {"accession": awk["accession"], "source_url": awk["url"], "response_sha256": awk["response_sha256"],
                                        "consolidated_original_quarter_facts": facts, "revenue_value_reconciliations": resolutions,
                                        "unique_revenue_periods_reconciled": len({r["period_end"] for r in resolutions if r["exact_value_match"]}),
                                        "affected_backlog_case_dates": sorted({r["signal_date"] for r in resolutions}),
                                        "observed_frozen_gate_diagnostic": {"revenue_yoy": revenue_growth,
                                                                            "net_income_yoy": income_growth,
                                                                            "margin_delta_pp": margin_delta,
                                                                            "all_three_observed_gates_fail": revenue_growth <= .2 and not frozen_earnings_pass(ni[current], ni[old]) and margin_delta <= 3,
                                                                            "complete_latest_filing_selection_certified": False}},
            "new_full_case_certifications": 0, "remaining_full_case_certifications": 943,
            "unresolved_primary_instance_acquisitions": [{k: r.get(k) for k in ("ticker", "accession", "url", "status", "error")} for r in xbrl_records if r["status"] != "ACQUIRED_PENDING_REVIEW"]}


def main() -> None:
    result = build_primary_review()
    (HERE / "artifacts/primary_review.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in {"header_checks", "awk_original_accession", "unresolved_primary_instance_acquisitions"}}, indent=2))


if __name__ == "__main__":
    main()
