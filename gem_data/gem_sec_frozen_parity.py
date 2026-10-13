"""Offline GEMv1 original SEC-to-frozen PIT parity diagnostic.

NO database, HTTP, status updates, brokerage, release approval or trading.
Input = already-collected original SEC submissions and companyfacts receipts.
Receipt bytes/CIK/official source hashes are verified before reading figures.
Outputs are diagnostic MATCH/HOLD records, never investment certification.

The pinned original selector consumes vendor-normalized PIT quarterly data. Its
upstream derivation cannot be proven from that code alone; this tool *only*
derives cumulative SEC Q2/Q3 when both original cumulative observations and
their metadata are available and uniquely reconcilable. It intentionally HOLDs
unsupported issuer-specific concepts, ambiguous reporting or missing sources.
"""
from __future__ import annotations

import ast
from collections import defaultdict
from datetime import date, timedelta
from hashlib import sha256
import json
import math
from pathlib import Path

from gem_data.sec_independent_fact_verify import (
    decode_original_receipt, VerificationHold,
)

PINNED_SHA256 = "521d6327ba932bde5e548b1b44cc2469afbb69c31e0428f13e2260678468b6d8"
TAGS = {
    "TotalRevenue": (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "Revenues", "SalesRevenueNet"),
    "NetIncome": ("NetIncomeLoss",),
    "OperatingIncome": ("OperatingIncomeLoss",),
}
ALLOWED_FORMS = {"10-Q", "10-Q/A"}


class SECParityHold(ValueError):
    pass


def _day(value):
    if not isinstance(value, str):
        raise SECParityHold("Original SEC date missing")
    try:
        return date.fromisoformat(value[:10])
    except ValueError as exc:
        raise SECParityHold("Original SEC date malformed") from exc


def _original_store(rows):
    """Execute only SHA-pinned original PIT class; unrelated imports never run."""
    src = Path(__file__).resolve().parents[1] / "scripts/wf3_offline_valuein.py"
    data = src.read_bytes()
    if sha256(data).hexdigest() != PINNED_SHA256:
        raise SECParityHold("Frozen PIT reference code hash mismatch")
    tree = ast.parse(data.decode("utf-8"))
    cls = next((n for n in tree.body if isinstance(n, ast.ClassDef)
                and n.name == "PITFundamentals"), None)
    if cls is None:
        raise SECParityHold("Frozen PIT selector not present")
    def parsed(v):
        try:
            return date.fromisoformat(str(v)[:10]) if v else None
        except (ValueError, TypeError):
            return None
    def finite(v):
        try:
            n = float(v)
            return n if math.isfinite(n) else None
        except (ValueError, TypeError):
            return None
    ns = {"defaultdict": defaultdict, "date": date, "timedelta": timedelta,
          "d": parsed, "fv": finite}
    # The code is a checked-in, exact-hash-pinned reference, never user data.
    exec(compile(ast.Module(body=[cls], type_ignores=[]), str(src), "exec"), ns)
    return ns["PITFundamentals"]({"facts": {"GEM": rows}})


def _accessions(submissions, cutoff):
    recent = ((submissions.get("filings") or {}).get("recent") or {})
    fields = ("form", "accessionNumber", "filingDate", "acceptanceDateTime")
    cols = [recent.get(f) for f in fields]
    if any(not isinstance(col, list) for col in cols) or len(set(map(len, cols))) != 1:
        raise SECParityHold("SEC accession metadata missing or misaligned")
    out = {}
    for form, accession, filed, accepted in zip(*cols):
        if form not in ALLOWED_FORMS:
            continue
        if not isinstance(accession, str) or len(accession) != 20:
            raise SECParityHold("SEC accession invalid")
        f, a = _day(filed), _day(accepted)
        if f < a or (f-a).days > 4:
            raise SECParityHold("SEC filing/acceptance metadata inconsistent")
        if f <= cutoff and a <= cutoff:
            out[accession] = (form, f, accepted)
    return out


def _original_rows(submissions, companyfacts, cutoff):
    """Extract all relevant *original* USD XBRL candidate contexts."""
    accessions = _accessions(submissions, cutoff)
    gaap = ((companyfacts.get("facts") or {}).get("us-gaap") or {})
    if not isinstance(gaap, dict):
        raise SECParityHold("SEC original us-gaap missing")
    result = []
    for concept, tags in TAGS.items():
        for tag in tags:
            raw_tag = gaap.get(tag)
            if raw_tag is None:
                continue
            entries = ((raw_tag.get("units") or {}).get("USD") or [])
            if not isinstance(entries, list):
                raise SECParityHold("SEC USD XBRL concept malformed")
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                accession = entry.get("accn")
                if accession not in accessions:
                    continue
                form, filed, accepted = accessions[accession]
                if entry.get("form") != form or _day(entry.get("filed")) != filed:
                    raise SECParityHold("Accession-specific SEC fact form/date mismatch")
                try:
                    start, end = _day(entry.get("start")), _day(entry.get("end"))
                except SECParityHold:
                    # Instant contexts are not quarterly revenue/earnings facts.
                    continue
                if end > cutoff or start >= end:
                    continue
                if entry.get("fp") not in ("Q1", "Q2", "Q3"):
                    continue
                val = entry.get("val")
                if isinstance(val, bool) or not isinstance(val, (int,float)) or not math.isfinite(val):
                    raise SECParityHold("SEC fact is nonfinite or not numeric")
                result.append({
                    "standard_concept": concept, "source_tag": tag,
                    "filing_date": filed.isoformat(), "accepted_at": accepted,
                    "form_type": form, "accession": accession,
                    "period_start": start.isoformat(), "period_end": end.isoformat(),
                    "period_span_days": (end-start).days, "fiscal_period": entry["fp"],
                    "numeric_value": float(val), "derived_quarterly_value": None,
                })
    return result


def _derive_observed_quarters(raw, cutoff):
    """Derive 6M-3M / 9M-6M only with uniquely observed same-FY YTD operands.

    SEC cumulative amounts cannot be treated as quarter amounts directly.
    If exact required earlier YTD evidence is unavailable, that issuer/concept
    remains unresolved. Source provenance of both operands is retained.
    """
    result = []
    for row in raw:
        duration = row["period_span_days"]
        if 60 <= duration <= 125:
            result.append(dict(row, derivation="DIRECT_10Q", operands=[
                {"accession": row["accession"], "value": row["numeric_value"],
                 "start": row["period_start"], "end": row["period_end"]}]))
            continue
        if not 125 < duration <= 310 or row["fiscal_period"] not in ("Q2","Q3"):
            continue
        start, end = _day(row["period_start"]), _day(row["period_end"])
        eligible = [
            old for old in raw
            if old["standard_concept"] == row["standard_concept"]
            and old["source_tag"] == row["source_tag"]
            and old["period_start"] == row["period_start"]
            and 60 <= (end - _day(old["period_end"])).days <= 125
            and old["period_end"] < row["period_end"]
            and old["filing_date"] <= cutoff.isoformat()
            and old["accepted_at"][:10] <= cutoff.isoformat()
        ]
        # Latest earlier fiscal-quarter endpoint, then newest admissible filing.
        if not eligible:
            # The SAME SEC accession may also disclose a directly measured
            # three-month quarter. In that case the unsupported cumulative
            # presentation is unnecessary; otherwise we must HOLD.
            direct_same_filing = any(
                x["standard_concept"] == row["standard_concept"]
                and x["source_tag"] == row["source_tag"]
                and x["accession"] == row["accession"]
                and x["period_end"] == row["period_end"]
                and 60 <= x["period_span_days"] <= 125
                for x in raw
            )
            if direct_same_filing:
                continue
            raise SECParityHold("Cumulative SEC YTD fact lacks proven prior-period operand")
        endpoint = max(x["period_end"] for x in eligible)
        same = [x for x in eligible if x["period_end"] == endpoint]
        latest_filing = max((x["filing_date"], x["accepted_at"]) for x in same)
        strongest = [x for x in same
                     if (x["filing_date"], x["accepted_at"]) == latest_filing]
        if len({x["numeric_value"] for x in strongest}) != 1:
            raise SECParityHold("Conflicting cumulative SEC operand values")
        old = strongest[0]
        derived = row["numeric_value"] - old["numeric_value"]
        if not math.isfinite(derived):
            raise SECParityHold("Nonfinite derived quarterly SEC value")
        output = dict(row)
        output["derived_quarterly_value"] = derived
        output["derivation"] = "OBSERVED_SEC_YTD_DIFFERENCE_NOT_CERTIFIED"
        output["operands"] = [
            {"accession": row["accession"], "value": row["numeric_value"],
             "start": row["period_start"], "end": row["period_end"]},
            {"accession": old["accession"], "value": old["numeric_value"],
             "start": old["period_start"], "end": old["period_end"]},
        ]
        result.append(output)
    return result


def _independent_quarter(rows, concept, cutoff):
    """Separate, non-PITFundamentals grouping/precedence implementation."""
    by_end = defaultdict(list)
    for r in rows:
        if (r["standard_concept"] != concept
                or r["filing_date"] > cutoff.isoformat()):
            continue
        val = r["numeric_value"] if r["derivation"] == "DIRECT_10Q" else r["derived_quarterly_value"]
        quality = 3 if r["derivation"] == "DIRECT_10Q" else 2
        by_end[r["period_end"]].append((r, val, quality))
    chosen = []
    for end in sorted(by_end):
        candidates = by_end[end]
        # Differing revenue tags asserting different amounts within the latest
        # filing context must HOLD, rather than arbitrary tag precedence.
        latest = max((r["filing_date"], r["accepted_at"]) for r,v,q in candidates)
        top = [(r,v,q) for r,v,q in candidates
               if (r["filing_date"], r["accepted_at"]) == latest]
        if len({round(v, 6) for r,v,q in top}) > 1:
            raise SECParityHold("Competing SEC concepts or contexts disagree")
        best = max(top, key=lambda x: x[2])
        chosen.append((end, best[1], best[0]))
    return chosen


def diagnose_receipts(submissions_receipt, companyfacts_receipt, cik, signal_day):
    """Full offline comparison. Never returns 'VERIFIED' or trade permission."""
    report = {
        "schema": "gem-sec-frozen-bc-diagnostic-v1", "cik": cik,
        "signal_session": signal_day, "status": "HOLD",
        "certified": False, "manual_trading_authorized": False,
        "broker_orders_sent": 0,
        "submissions_sha256": submissions_receipt.get("source_sha256"),
        "companyfacts_sha256": companyfacts_receipt.get("source_sha256"),
        "comparisons": {}, "blockers": [],
    }
    try:
        signal = _day(signal_day)
        cutoff = signal - timedelta(days=1)
        submissions = decode_original_receipt(submissions_receipt, cik, "submissions")
        companyfacts = decode_original_receipt(companyfacts_receipt, cik, "companyfacts")
        raw = _original_rows(submissions, companyfacts, cutoff)
        transformed = _derive_observed_quarters(raw, cutoff)
        if not transformed:
            raise SECParityHold("No reconstructable 10-Q quarters")
        original = _original_store(transformed)
        for concept in TAGS:
            actual = original.quarter("GEM", concept, cutoff)
            independently = _independent_quarter(transformed, concept, cutoff)
            reduced = lambda items: [(str(p), float(v)) for p,v,*_ in items]
            if reduced(actual) != reduced(independently):
                raise SECParityHold("Frozen/reference quarter precedence disagreement: "+concept)
            if len(actual) < 2:
                raise SECParityHold("Insufficient current/prior-year quarterly source: "+concept)
            if concept in ("TotalRevenue", "NetIncome"):
                latest_filing = _day(actual[-1][2]["filing_date"])
                if (cutoff - latest_filing).days > 210:
                    raise SECParityHold("Stale latest quarterly financial filing: "+concept)
            newest = actual[-1][0]
            previous = [x for x in actual[:-1] if 310 <= (newest-x[0]).days <= 420]
            if not previous:
                raise SECParityHold("Prior YoY SEC period missing: "+concept)
            old = min(previous, key=lambda v: abs((newest-v[0]).days-365))
            report["comparisons"][concept] = {
                "latest_period": newest.isoformat(), "latest_value": actual[-1][1],
                "prior_period": old[0].isoformat(), "prior_value": old[1],
                "latest_accession": actual[-1][2]["accession"],
                "prior_accession": old[2]["accession"],
                "latest_derivation": actual[-1][2]["derivation"],
                "prior_derivation": old[2]["derivation"],
                "latest_operands": actual[-1][2]["operands"],
                "prior_operands": old[2]["operands"],
                "reference_matched": True,
            }
        revenue = report["comparisons"]["TotalRevenue"]
        earnings = report["comparisons"]["NetIncome"]
        ops = report["comparisons"]["OperatingIncome"]
        if ops["latest_period"] != revenue["latest_period"] or ops["prior_period"] != revenue["prior_period"]:
            raise SECParityHold("Operating-income/revenue reporting periods do not align")
        if revenue["prior_value"] <= 0 or revenue["latest_value"] <= 0:
            raise SECParityHold("Nonpositive YoY revenue source")
        report["calculated"] = {
            "revenue_yoy": revenue["latest_value"] / revenue["prior_value"] - 1,
            "earnings_improvement": earnings["latest_value"] > 0 and (
                earnings["prior_value"] <= 0 or
                earnings["latest_value"] / earnings["prior_value"] - 1 > .2),
            "margin_delta_pp": 100 * (
                ops["latest_value"] / revenue["latest_value"] -
                ops["prior_value"] / revenue["prior_value"]),
        }
        report["calculated"]["G_revenue_gate"] = report["calculated"]["revenue_yoy"] > .2
        report["calculated"]["E_earnings_gate"] = report["calculated"]["earnings_improvement"]
        report["calculated"]["operating_margin_gate"] = report["calculated"]["margin_delta_pp"] > 3
        report["status"] = "MATCHED_DIAGNOSTIC_NOT_CERTIFIED"
    except (VerificationHold, SECParityHold, KeyError, ValueError, TypeError, OSError) as exc:
        report["blockers"] = [str(exc)[:240]]
    report["report_sha256"] = sha256(json.dumps(report, sort_keys=True, separators=(",",":"),
                                                allow_nan=False).encode()).hexdigest()
    return report
