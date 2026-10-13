"""Independent, fail-closed GEM SEC original-member and six-fact candidate QA.

Pure verifier: NO HTTP, DB, Marketstack, order execution, or strategy imports.
A complete candidate set is NOT certified until original accession-specific
10-Q/10-Q/A XBRL context and human signoff are independently established.
"""
from __future__ import annotations

import base64
from datetime import date, timedelta
from hashlib import sha256
import json
import re
import zlib

AS_OF = date(2026, 10, 12)
MAX_COMPRESSED = 650_000
MAX_ORIGINAL = 12_000_000
ACCESSION = re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")
METRICS = {
    "revenue": ("RevenueFromContractWithCustomerExcludingAssessedTax",
                "RevenueFromContractWithCustomerIncludingAssessedTax",
                "Revenues", "SalesRevenueNet"),
    "operating_income": ("OperatingIncomeLoss",),
    # Parent-company net income: ProfitLoss is NOT an equivalent fallback.
    "net_income": ("NetIncomeLoss",),
}


class VerificationHold(ValueError):
    """Evidence is missing, inconsistent, or cannot be independently checked."""


def _iso_date(raw):
    if not isinstance(raw, str):
        raise VerificationHold("Date absent")
    try:
        return date.fromisoformat(raw[:10])
    except ValueError as exc:
        raise VerificationHold("Malformed filing or XBRL date") from exc


def decode_original_receipt(receipt: dict, cik: str, kind: str) -> dict:
    """Independent zlib + original SHA256 + CIK + provenance check."""
    if kind not in ("submissions", "companyfacts"):
        raise VerificationHold("Unexpected SEC source kind")
    if receipt.get("provider") != f"SEC_ZIP_{kind.upper()}":
        raise VerificationHold("Unexpected SEC source provider")
    metadata = receipt.get("metadata")
    if not isinstance(metadata, dict):
        raise VerificationHold("Missing SEC source metadata")
    if metadata.get("zip_member_name") != f"CIK{cik}.json":
        raise VerificationHold("SEC ZIP member CIK mismatch")
    b64 = metadata.get("source_raw_zlib_base64")
    if not isinstance(b64, str) or len(b64) > 900_000:
        raise VerificationHold("SEC compressed source missing or oversized")
    try:
        compressed = base64.b64decode(b64, validate=True)
        if not 0 < len(compressed) <= MAX_COMPRESSED:
            raise VerificationHold("SEC compressed original exceeds bound")
        inflater = zlib.decompressobj()
        raw = inflater.decompress(compressed, MAX_ORIGINAL + 1)
        if (len(raw) > MAX_ORIGINAL or inflater.unconsumed_tail
                or not inflater.eof or inflater.unused_data):
            raise VerificationHold("SEC zlib stream incomplete or exceeds bound")
        raw += inflater.flush()
    except (ValueError, zlib.error) as exc:
        raise VerificationHold("SEC original zlib decompression invalid") from exc
    if len(raw) > MAX_ORIGINAL or len(raw) != metadata.get("member_uncompressed_bytes"):
        raise VerificationHold("SEC original uncompressed byte count differs")
    digest = sha256(raw).hexdigest()
    if (digest != str(receipt.get("source_sha256", "")).strip()
            or digest != metadata.get("member_original_sha256")):
        raise VerificationHold("SEC original SHA256 differs from receipt")
    try:
        original = json.loads(raw)
    except (UnicodeError, ValueError) as exc:
        raise VerificationHold("SEC original JSON invalid") from exc
    if not isinstance(original, dict) or str(original.get("cik", "")).zfill(10) != cik:
        raise VerificationHold("SEC original CIK differs")
    return original


def _submissions(original: dict, as_of: date):
    recent = ((original.get("filings") or {}).get("recent") or {})
    cols = ("form", "accessionNumber", "filingDate", "acceptanceDateTime")
    arrays = [recent.get(k) for k in cols]
    if any(not isinstance(a, list) for a in arrays) or len({len(a) for a in arrays}) != 1:
        raise VerificationHold("SEC accession arrays incomplete")
    acc = {}
    for form, accession, filed, accepted in zip(*arrays):
        if form not in ("10-Q", "10-Q/A") or not isinstance(accession, str):
            continue
        if not ACCESSION.fullmatch(accession):
            raise VerificationHold("SEC accession format invalid")
        fd, ad = _iso_date(filed), _iso_date(accepted)
        if ad < fd:
            raise VerificationHold("SEC acceptance precedes filing")
        if fd <= as_of and ad <= as_of:
            acc[accession] = {"form": form, "filed": fd, "accepted": ad}
    return acc


def _eligible_facts(original: dict, accessions: dict, as_of: date):
    gaap = ((original.get("facts") or {}).get("us-gaap") or {})
    if not isinstance(gaap, dict):
        raise VerificationHold("SEC companyfacts us-gaap missing")
    groups = {}
    for metric, tags in METRICS.items():
        for tag in tags:
            concept = gaap.get(tag)
            if not isinstance(concept, dict):
                continue
            usd = (concept.get("units") or {}).get("USD", [])
            if not isinstance(usd, list):
                raise VerificationHold("SEC USD units malformed")
            for f in usd:
                if not isinstance(f, dict):
                    continue
                accession = f.get("accn")
                if accession not in accessions:
                    continue
                meta = accessions[accession]
                if f.get("form") != meta["form"]:
                    continue
                if _iso_date(f.get("filed")) != meta["filed"]:
                    continue
                start, end = _iso_date(f.get("start")), _iso_date(f.get("end"))
                duration = (end-start).days
                if not (60 <= duration <= 125 and end <= as_of):
                    continue
                fp = f.get("fp")
                if fp not in ("Q1", "Q2", "Q3"):
                    continue
                val = f.get("val")
                if isinstance(val, bool) or not isinstance(val, (int, float)):
                    continue
                key = (accession, start, end, fp)
                g = groups.setdefault(key, {"accepted": meta["accepted"],
                                            "filed": meta["filed"], "metrics": {}})
                g["metrics"].setdefault(metric, []).append((tag, val))
    return groups


def _resolve_group(groups, key, blockers, label):
    g = groups[key]
    facts = {}
    for metric in METRICS:
        candidates = g["metrics"].get(metric, [])
        if not candidates:
            blockers.append(f"{label}_missing_{metric}")
            continue
        values = {val for _tag, val in candidates}
        if len(values) != 1:
            blockers.append(f"{label}_ambiguous_{metric}_tags")
            continue
        facts[metric] = {
            "value_usd": candidates[0][1],
            "concept": candidates[0][0],
            "accession": key[0], "start": key[1].isoformat(),
            "end": key[2].isoformat(), "filed": g["filed"].isoformat(),
            "fiscal_period": key[3],
        }
    return facts


def verify_six_candidates(submissions: dict, companyfacts: dict,
                          as_of: date = AS_OF) -> dict:
    """Strictly choose 10-Q quarterly USD contexts, not cumulative YTD.

    All three metrics must come from the SAME original accession and period
    in each year. Amendments, missing prior accession, or competing tags
    are held for original Inline XBRL review, not guessed.
    """
    accessions = _submissions(submissions, as_of)
    groups = _eligible_facts(companyfacts, accessions, as_of)
    blockers, six = [], {}
    if not groups:
        return {"fact_status": "UNKNOWN", "six_facts": {},
                "blockers": ["no_eligible_original_10q_usd_quarter_contexts"],
                "certified": False}
    newest = max(k[2] for k in groups)
    if (as_of-newest).days > 210:
        blockers.append("current_quarter_older_than_210_days")
    current = [k for k in groups if k[2] == newest]
    current.sort(key=lambda k: (groups[k]["accepted"], groups[k]["filed"], k[0]),
                 reverse=True)
    current_key = current[0]
    prior = [k for k in groups if k[3] == current_key[3]
             and 340 <= (newest-k[2]).days <= 390
             and abs(((current_key[2]-current_key[1]) -
                      (k[2]-k[1])).days) <= 10]
    prior.sort(key=lambda k: (abs((newest-k[2]).days-365),
                              -groups[k]["accepted"].toordinal(), k[0]))
    if not prior:
        blockers.append("prior_year_same_quarter_accession_context_missing")
    periods = [("current", current_key)]
    if prior:
        periods.append(("prior", prior[0]))
    for label, key in periods:
        resolved = _resolve_group(groups, key, blockers, label)
        for metric, record in resolved.items():
            six[f"{label}_{metric}"] = record
    # If any 10-Q/A exists for the chosen period after the selected accession,
    # manual amendment-specific XBRL comparison is required.
    for label, key in periods:
        accepted = groups[key]["accepted"]
        for other, g in groups.items():
            if (other[2] == key[2] and other[3] == key[3]
                    and g["accepted"] > accepted):
                blockers.append(f"{label}_later_amendment_requires_xbrl")
                break
    if len(six) != 6 and not blockers:
        blockers.append("six_quarter_facts_incomplete")
    return {
        "fact_status": ("CANDIDATE_COMPLETE_NOT_CERTIFIED"
                        if len(six) == 6 and not blockers else "UNKNOWN"),
        "six_facts": six,
        "blockers": sorted(set(blockers)),
        "certified": False,
        "source_quarter_contexts_only": True,
        "original_accession_inline_xbrl_certified": False,
    }


def verify_receipt_pair(submissions_receipt: dict, companyfacts_receipt: dict,
                        cik: str, as_of: date = AS_OF) -> dict:
    """Return independent machine-check evidence, NEVER source VERIFIED."""
    try:
        submissions = decode_original_receipt(submissions_receipt, cik, "submissions")
        facts = decode_original_receipt(companyfacts_receipt, cik, "companyfacts")
        result = verify_six_candidates(submissions, facts, as_of)
        result["receipt_integrity"] = "PASS"
    except VerificationHold as exc:
        result = {"receipt_integrity": "FAIL", "fact_status": "UNKNOWN",
                  "six_facts": {}, "blockers": [str(exc)],
                  "certified": False}
    evidence = {
        "cik": cik, "as_of": as_of.isoformat(),
        "submissions_sha256": str(submissions_receipt.get("source_sha256", "")).strip(),
        "companyfacts_sha256": str(companyfacts_receipt.get("source_sha256", "")).strip(),
        "receipt_integrity": result["receipt_integrity"],
        "fact_status": result["fact_status"], "six_facts": result["six_facts"],
        "blockers": result["blockers"],
    }
    result["evidence_sha256"] = sha256(
        json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return result
