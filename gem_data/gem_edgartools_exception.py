"""Targeted, fail-closed SEC 10-Q XBRL exception planning and extraction.

Intended after positive-r63 *review priority* and existing SEC ZIP-member parity
checks. This is not a financial-fact certification, nor a source of GEM ranks.

The default path is pure/offline; optional EdgarTools is imported only inside
fetch_filing_xbrl after a separate explicit operator approval flag.
"""
from __future__ import annotations

from datetime import date, timedelta
from hashlib import sha256
import json
import math
import re

from gem_data.sec_independent_fact_verify import decode_original_receipt

ACCESSION = re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")
FACT_PATTERN = re.compile(
    r"revenue|sales|income|earning|profit|loss|margin", re.I)
MAX_XBRL_ROWS = 2500
MAX_XBRL_BYTES = 2_000_000


class SECXBRLHold(ValueError):
    """Unresolved or contradictory original filing evidence."""


def _day(value, label):
    if not isinstance(value, str):
        raise SECXBRLHold(label + " missing")
    try:
        day = date.fromisoformat(value[:10])
    except ValueError as exc:
        raise SECXBRLHold(label + " invalid") from exc
    return day


def plan_filing_exceptions(submissions_receipt, cik, signal_day,
                           *, max_accessions=8):
    """Identify recent and YoY 10-Q/10-Q/A accessions from SEC ORIGINALS only.

    Never use Company(ticker).financials or current company filing versions.
    Include all amendments in chosen periods, limited to a bounded batch.
    """
    if not isinstance(cik, str) or not re.fullmatch(r"[0-9]{10}", cik):
        raise SECXBRLHold("Invalid issuer CIK")
    if type(max_accessions) is not int or not 1 <= max_accessions <= 8:
        raise SECXBRLHold("Excessive filing workload")
    signal = _day(signal_day, "signal date")
    cutoff = signal - timedelta(days=1)
    original = decode_original_receipt(submissions_receipt, cik, "submissions")
    recent = ((original.get("filings") or {}).get("recent") or {})
    keys = ("form", "accessionNumber", "filingDate",
            "acceptanceDateTime", "reportDate")
    arrays = [recent.get(k) for k in keys]
    if any(not isinstance(x, list) for x in arrays) or len(set(map(len, arrays))) != 1:
        raise SECXBRLHold("Original SEC filing arrays absent or misaligned")
    by_period = {}
    for form, accession, filed, accepted, report in zip(*arrays):
        if form not in ("10-Q", "10-Q/A"):
            continue
        if not isinstance(accession, str) or not ACCESSION.fullmatch(accession):
            raise SECXBRLHold("SEC quarterly accession malformed")
        if accession[:10] != cik:
            raise SECXBRLHold("SEC issuer/accession mismatch")
        filing_day = _day(filed, "filed date")
        acceptance_day = _day(accepted, "accepted date")
        report_day = _day(report, "report date")
        if filing_day < acceptance_day or (filing_day-acceptance_day).days > 4:
            raise SECXBRLHold("Filing/acceptance chronology inconsistent")
        if filing_day > cutoff or acceptance_day > cutoff or report_day > cutoff:
            continue
        item = {"accession": accession, "cik": cik, "form": form,
                "filed": filing_day.isoformat(), "accepted_at": accepted,
                "report_period": report_day.isoformat()}
        by_period.setdefault(report_day, []).append(item)
    if not by_period:
        raise SECXBRLHold("No eligible original 10-Q accession before cutoff")
    periods = sorted(by_period, reverse=True)
    recent_periods = periods[:2]
    prior_periods = []
    for current in recent_periods:
        choices = [p for p in periods if 310 <= (current-p).days <= 420]
        if choices:
            prior = min(choices, key=lambda p: (abs((current-p).days-365), -p.toordinal()))
            if prior not in prior_periods:
                prior_periods.append(prior)
    chosen_periods = sorted(set(recent_periods + prior_periods), reverse=True)
    selections = []
    for period in chosen_periods:
        # Preserve every eligible filing version, including original and
        # amendments, for independent supersession analysis.
        for item in sorted(by_period[period],
                           key=lambda v:(v["filed"],v["accepted_at"],
                                         v["accession"]), reverse=True):
            selections.append(item)
    if len(selections) > max_accessions:
        raise SECXBRLHold("Too many original filing versions; inspect manually")
    if not prior_periods:
        raise SECXBRLHold("No eligible YoY comparative quarterly filing")
    return {
        "schema":"gem-edgartools-exception-plan-v1",
        "cik":cik, "signal_day":signal_day,
        "cutoff":cutoff.isoformat(),
        "original_submissions_sha256":submissions_receipt["source_sha256"],
        "filings":selections,
        "status":"PLANNED_UNCERTIFIED",
        "independent_filing_verification":False,
        "trading_authorized":False,
    }


def fetch_filing_xbrl(plan_entry, *, filing_loader=None):
    """Parse ONLY an explicitly planned accession. No automatic certification.

    Dependency-injected loader permits no-network CI. Uses versioned EdgarTools
    5.x public API in operator mode (get_by_accession_number, xbrl.facts).
    """
    accession = plan_entry.get("accession")
    cik = plan_entry.get("cik")
    if (not isinstance(accession, str) or not ACCESSION.fullmatch(accession)
            or not isinstance(cik, str) or not re.fullmatch(r"[0-9]{10}",cik)
            or accession[:10] != cik
            or plan_entry.get("form") not in ("10-Q","10-Q/A")):
        raise SECXBRLHold("Untrusted XBRL fetch identity or form")
    expected_date = _day(plan_entry.get("filed"), "expected filing date")
    if filing_loader is None:
        try:
            from edgar import get_by_accession_number
        except ImportError as exc:
            raise SECXBRLHold(
                "Operator-only edgartools dependency not installed") from exc
        filing_loader = get_by_accession_number
    filing = filing_loader(accession)
    if filing is None:
        raise SECXBRLHold("Filing unavailable at original accession")
    actual_acc = getattr(filing,"accession_number",None)
    actual_form = getattr(filing,"form",None)
    actual_cik = getattr(filing,"cik",None)
    actual_date = str(getattr(filing,"filing_date",""))[:10]
    if (actual_acc != accession or actual_form != plan_entry["form"]
            or not str(actual_cik).isdigit()
            or str(actual_cik).zfill(10) != cik
            or actual_date != expected_date.isoformat()):
        raise SECXBRLHold("EdgarTools filing identity differs from SEC original")
    xbrl = filing.xbrl()
    if xbrl is None:
        raise SECXBRLHold("Accession contains no parseable Inline XBRL")
    facts = getattr(xbrl,"facts",None)
    if facts is None or not hasattr(facts,"to_dataframe"):
        raise SECXBRLHold("Missing accession-scoped XBRL fact view")
    frame = facts.to_dataframe()
    if frame is None or frame.empty:
        raise SECXBRLHold("No original accession facts in parsed XBRL")
    cols = set(str(v) for v in frame.columns)
    if not cols.intersection({"concept","label","original_label"}):
        raise SECXBRLHold("Unrecognized XBRL fact DataFrame schema")
    # Retain every column/context in each relevant row, including custom
    # concepts. Never match a company-specific concept to a GEM metric merely
    # from its label.
    relevant = []
    for record in frame.to_dict(orient="records"):
        labels = " ".join(str(record.get(k,"")) for k in (
            "concept","label","original_label"))
        if FACT_PATTERN.search(labels):
            relevant.append(record)
            if len(relevant)>MAX_XBRL_ROWS:
                raise SECXBRLHold("Too many candidate XBRL facts")
    if not relevant:
        raise SECXBRLHold("No relevant SEC XBRL financial concepts")
    try:
        raw = frame.loc[frame.index[:0]].to_json(orient="records")
        # Pandas serializes dates, decimal-like and missing values consistently.
        # Re-select the subset in original order, without stringifying money.
        indices = [i for i,rec in enumerate(frame.to_dict(orient="records"))
                   if FACT_PATTERN.search(" ".join(str(rec.get(k,"")) for k in
                                          ("concept","label","original_label")))]
        serialized = frame.iloc[indices].to_json(orient="records", date_format="iso")
        if len(serialized.encode()) > MAX_XBRL_BYTES:
            raise SECXBRLHold("Filtered XBRL fact payload too large")
        parsed = json.loads(serialized)
    except (TypeError, ValueError) as exc:
        raise SECXBRLHold("Cannot preserve original XBRL fact columns") from exc
    if not isinstance(parsed, list) or not parsed:
        raise SECXBRLHold("Empty serialized SEC XBRL candidates")
    digest = sha256(serialized.encode()).hexdigest()
    return {
        "schema":"gem-edgartools-accession-exception-v1",
        "cik":cik,"accession":accession,
        "form":plan_entry["form"],
        "filing_date":expected_date.isoformat(),
        "report_period":plan_entry["report_period"],
        "accepted_at":plan_entry["accepted_at"],
        "parsed_candidate_facts":parsed,
        "parsed_candidate_count":len(parsed),
        "parsed_facts_sha256":digest,
        "raw_original_xbrl_bytes_sha256_verified":False,
        "original_inline_xbrl_context_certified":False,
        "metric_mappings_certified":False,
        "quarterly_derivations_certified":False,
        "status":"EXTRACTED_FOR_INDEPENDENT_QA_ONLY",
        "manual_trading_authorized":False,"broker_orders_sent":0,
    }
