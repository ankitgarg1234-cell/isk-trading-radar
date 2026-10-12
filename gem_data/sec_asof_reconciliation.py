"""SEC as-of reconciliation proposal for frozen GEMv1 six-quarter gates.

An accession appearing in today's SEC submissions is NOT proof that a
specific XBRL fact or issuer quarter was available at an earlier trading
cutoff. This offline gate checks identities, 10-Q provenance, acceptance
day, first observed timestamp, quarter lengths, and document hashes.
It never parses or certifies original XBRL facts and never authorizes orders.
"""
from __future__ import annotations

from datetime import date, datetime, timezone, timedelta
from hashlib import sha256
import json
import math
import re

REQUIRED = (
    "revenue_now", "revenue_prior", "income_now", "income_prior",
    "operating_now", "operating_prior",
)
SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
ACCESSION = re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")
CIK = re.compile(r"^[0-9]{10}$")


class SecEvidenceHold(ValueError):
    """Proposal has incomplete, inconsistent or too-late SEC evidence."""


def _day(value, reason):
    try:
        if not isinstance(value, str) or len(value) != 10:
            raise ValueError
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SecEvidenceHold(reason) from exc


def _timestamp(value, reason):
    try:
        if not isinstance(value, str):
            raise ValueError
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if d.tzinfo is None:
            raise ValueError
        return d.astimezone(timezone.utc)
    except ValueError as exc:
        raise SecEvidenceHold(reason) from exc


def _digest(value):
    return isinstance(value, str) and SHA256.fullmatch(value) is not None


def audit_sec_six_facts(
    *, manifest: dict, facts: dict, signal_session: str,
    original_xbrl_receipts: dict,
) -> dict:
    """Reconcile candidate metadata without claiming XBRL semantic QA.

    Only original SEC source snapshots/bytes may become authenticated by a
    separate reader/reviewer. The SEC 'acceptanceDateTime' is supplied without
    an explicit timezone; comparing its *date* conservatively to the NYSE
    signal date avoids assuming an unverified UTC or ET offset.
    """
    signal = _day(signal_session, "Invalid signal session")
    if not isinstance(manifest, dict) or manifest.get("schema") != "gem-sec-quarter-discovery-v1":
        raise SecEvidenceHold("Missing original SEC discovery manifest")
    cik = manifest.get("cik")
    if not isinstance(cik, str) or not CIK.fullmatch(cik):
        raise SecEvidenceHold("Malformed SEC issuer CIK")
    receipt = manifest.get("raw_submissions_receipt")
    if (not isinstance(receipt, dict) or receipt.get("provider") != "SEC_ORIGINAL"
            or receipt.get("uri") != f"https://data.sec.gov/submissions/CIK{cik}.json"
            or not _digest(receipt.get("sha256"))
            or type(receipt.get("bytes")) is not int or receipt["bytes"] <= 0):
        raise SecEvidenceHold("Missing original SEC submissions receipt")
    filings = manifest.get("discovered_recent_10q")
    if not isinstance(filings, list):
        raise SecEvidenceHold("Missing original SEC filing discovery")
    by_accession = {}
    for filing in filings:
        if not isinstance(filing, dict):
            raise SecEvidenceHold("Malformed SEC accession entry")
        accession = filing.get("accession")
        if not isinstance(accession, str) or not ACCESSION.fullmatch(accession):
            raise SecEvidenceHold("Invalid SEC accession")
        if accession in by_accession:
            raise SecEvidenceHold("Duplicate discovered SEC accession")
        if filing.get("form") not in ("10-Q", "10-Q/A"):
            raise SecEvidenceHold("Non-10-Q form in quarter evidence")
        filed = _day(filing.get("filed_date_raw"), "Invalid SEC filing date")
        accepted = filing.get("acceptance_datetime_raw")
        if (not isinstance(accepted, str) or len(accepted) < 19
                or accepted[10] != "T"):
            raise SecEvidenceHold("Missing SEC acceptance clock value")
        accepted_date = _day(accepted[:10], "Invalid SEC acceptance date")
        try:
            datetime.fromisoformat(accepted)
        except ValueError as exc:
            raise SecEvidenceHold("Malformed SEC acceptance clock") from exc
        if filed >= signal or accepted_date >= signal:
            raise SecEvidenceHold("SEC filing not public by prior-session cutoff")
        if not isinstance(filing.get("primary_document"), str) or not filing["primary_document"]:
            raise SecEvidenceHold("Original SEC primary document missing")
        by_accession[accession] = (filing, filed, accepted_date)

    if not isinstance(facts, dict) or set(facts) != set(REQUIRED):
        raise SecEvidenceHold("Missing a frozen GEM six-quarter fact")
    if not isinstance(original_xbrl_receipts, dict):
        raise SecEvidenceHold("Missing original XBRL source receipts")
    periods = {}
    receipt_hashes = set()
    for name in REQUIRED:
        fact = facts[name]
        if not isinstance(fact, dict):
            raise SecEvidenceHold("Invalid " + name + " fact")
        accession = fact.get("accession")
        if accession not in by_accession:
            raise SecEvidenceHold("Unrecognized original SEC accession for " + name)
        filing, filed, accepted = by_accession[accession]
        if (fact.get("form") != filing["form"] or fact.get("cik") != cik
                or fact.get("unit") != "USD"
                or not isinstance(fact.get("concept"), str)
                or not fact["concept"]):
            raise SecEvidenceHold("Quarter identity/unit/concept mismatch for " + name)
        start = _day(fact.get("start"), "Invalid quarter start")
        end = _day(fact.get("end"), "Invalid quarter end")
        if not 60 <= (end - start).days <= 125 or end > filed:
            raise SecEvidenceHold("Non-quarter or future filing period for " + name)
        val = fact.get("value")
        if type(val) not in (int, float) or not math.isfinite(val):
            raise SecEvidenceHold("Missing/nonfinite fact value for " + name)
        source = original_xbrl_receipts.get(accession)
        if (not isinstance(source, dict)
                or source.get("provider") != "SEC_ORIGINAL"
                or not _digest(source.get("sha256"))
                or fact.get("source_sha256") != source["sha256"]
                or not isinstance(source.get("uri"), str)
                or not source["uri"].startswith(
                    f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/"
                )):
            raise SecEvidenceHold("Missing original accession XBRL byte receipt for " + name)
        first_seen = _timestamp(fact.get("first_public_observed_at"),
                                "First-observed timestamp required for " + name)
        # 'First observed' is discovery evidence, NOT independent publication proof.
        if first_seen.date() >= signal:
            raise SecEvidenceHold("SEC fact first observed too late for " + name)
        if first_seen.date() < accepted:
            raise SecEvidenceHold("Fact observed before SEC acceptance for " + name)
        receipt_hashes.add(source["sha256"].lower())
        periods[name] = (start, end, accession)
    for suffix in ("now", "prior"):
        three = [periods[f"{measure}_{suffix}"] for measure in
                 ("revenue", "income", "operating")]
        if len(set(three)) != 1:
            raise SecEvidenceHold("Mixed quarter periods or SEC accessions")
    if not 310 <= (periods["revenue_now"][1] - periods["revenue_prior"][1]).days <= 420:
        raise SecEvidenceHold("Now/prior comparison is not year-over-year")
    # Same 210-day current-filing freshness window as the frozen offline
    # ranking gate; never loosen it when preparing SEC evidence.
    current_accession = periods["revenue_now"][2]
    current_filed = by_accession[current_accession][1]
    if (signal - timedelta(days=1) - current_filed).days > 210:
        raise SecEvidenceHold("Current SEC quarter filing exceeds 210-day freshness")
    payload = {
        "schema": "gem-sec-six-facts-proposal-v1",
        "signal_session": signal_session,
        "cik": cik,
        "accessions": sorted({row[2] for row in periods.values()}),
        "original_xbrl_sha256": sorted(receipt_hashes),
        "facts_checked": len(REQUIRED),
        "publication_and_xbrl_context_independently_verified": False,
        "ranking_authorized": False,
        "status": "PENDING_INDEPENDENT_SEC_QA",
    }
    payload["proposal_sha256"] = sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    return payload
