"""Fail-closed reviewer handoff. This does not authenticate a human or agent."""
from __future__ import annotations

import hashlib
import json
import re

FROZEN_COMMIT = "d59b93d3d9a87d582045b4ae71ff9a6f696a48be"
SCHEMA_VERSION = "gem-competitor-case-v1"
CHECKS = (
    "frozen_rules_and_inputs", "historical_security_identity",
    "historical_universe_membership", "complete_eligible_filings",
    "original_accession_quarter_values", "publication_time_and_filing_cutoff",
    "latest_per_period_and_comparator_selection", "financial_gates",
    "price_history_liquidity_and_momentum", "corporate_action_units",
    "stable_ranking_and_impact", "independent_reproduction",
)
TERMINAL = {"CERTIFIED_INELIGIBLE", "CERTIFIED_ELIGIBLE_NONDISPLACING",
            "CERTIFIED_ELIGIBLE_DISPLACING"}
TRANSITIONS = {
    "NEW": {"EVIDENCE_REQUIRED", "QUARANTINED"},
    "EVIDENCE_REQUIRED": {"EVIDENCE_READY", "UNRESOLVED", "QUARANTINED"},
    "UNRESOLVED": {"EVIDENCE_REQUIRED", "QUARANTINED"},
    "EVIDENCE_READY": {"REVIEW_REQUIRED", "EVIDENCE_REQUIRED", "QUARANTINED"},
    "REVIEW_REQUIRED": TERMINAL | {"EVIDENCE_REQUIRED", "QUARANTINED"},
    "QUARANTINED": {"EVIDENCE_REQUIRED"},
    **{state: {"QUARANTINED", "EVIDENCE_REQUIRED"} for state in TERMINAL},
}


def canonical_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def case_id(signal_date: str, ticker: str) -> str:
    """Stable within the frozen archive; CIK remains separately auditable."""
    return "gem-v1-" + canonical_hash({"commit": FROZEN_COMMIT,
                                     "signal_date": signal_date, "ticker": ticker})[:24]


def validate_transition(current: str, new: str) -> None:
    if new not in TRANSITIONS.get(current, set()):
        raise ValueError(f"Forbidden case transition: {current} -> {new}")


def validate_certification_decision(decision: dict) -> None:
    """Validate a review envelope, never infer certification from cache statuses.

    Check evidence and attestations must be independently produced by a reviewer
    service that actually verifies the primary documents. These structural checks
    alone cannot prove the SEC sources or reviewer identity are authentic.
    """
    if decision.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Wrong evidence schema")
    if decision.get("frozen_commit") != FROZEN_COMMIT:
        raise ValueError("Wrong frozen strategy commit")
    if decision.get("case_id") != case_id(decision.get("signal_date", ""),
                                         decision.get("ticker", "")):
        raise ValueError("Case identity does not match the frozen inputs")
    if decision.get("state") not in TERMINAL:
        raise ValueError("Decision is not a certification terminal state")
    collector = decision.get("collector_id")
    reviewer = decision.get("reviewer_id")
    second_reviewer = decision.get("second_reviewer_id")
    identities = (collector, reviewer, second_reviewer)
    if any(not isinstance(item, str) or not item for item in identities) or len(set(identities)) != 3:
        raise ValueError("Collector and two independent reviewer identities required")
    if not re.fullmatch(r"[0-9a-f]{64}", decision.get("evidence_bundle_sha256", "")):
        raise ValueError("Evidence bundle hash required")
    checks = decision.get("checks", {})
    if not isinstance(checks, dict) or set(checks) != set(CHECKS):
        raise ValueError("Exact complete proof checklist required")
    for key, item in checks.items():
        if (not isinstance(item, dict) or item.get("passed") is not True
                or item.get("verifier_id") != reviewer or item.get("second_verifier_id") != second_reviewer
                or item.get("second_passed") is not True):
            raise ValueError(f"Unverified reviewer proof: {key}")
        if not re.fullmatch(r"[0-9a-f]{64}", item.get("evidence_sha256", "")):
            raise ValueError(f"Missing proof hash: {key}")
        if not re.fullmatch(r"[0-9a-f]{64}", item.get("second_evidence_sha256", "")):
            raise ValueError(f"Missing independent proof hash: {key}")
    result = decision.get("recomputed_result", {})
    if not isinstance(result, dict) or type(result.get("eligible")) is not bool or type(result.get("selected")) is not bool:
        raise ValueError("Recomputed eligibility and selection required")
    if result != decision.get("second_recomputed_result"):
        raise ValueError("Independent certification reproductions disagree")
    expected = ("CERTIFIED_INELIGIBLE" if not result["eligible"] else
                "CERTIFIED_ELIGIBLE_DISPLACING" if result["selected"] else
                "CERTIFIED_ELIGIBLE_NONDISPLACING")
    if decision["state"] != expected or (result["selected"] and not result["eligible"]):
        raise ValueError("Terminal state contradicts reproduced eligibility/ranking")


def audit_events(cases: list[dict], input_hashes: dict) -> list[dict]:
    """Deterministic hash chain for a generated review artifact, not a WORM store."""
    previous = "0" * 64
    events = []
    for seq, case in enumerate(cases, 1):
        event = {"sequence": seq, "previous_sha256": previous,
                 "schema_version": SCHEMA_VERSION, "frozen_commit": FROZEN_COMMIT,
                 "case_id": case["case_id"], "from_state": "NEW",
                 "to_state": "EVIDENCE_REQUIRED", "actor_id": "independent-cached-evidence-recheck",
                 "input_manifest_sha256": canonical_hash(input_hashes),
                 "case_payload_sha256": canonical_hash(case)}
        previous = canonical_hash(event)
        event["event_sha256"] = previous
        events.append(event)
    return events


def verify_audit_events(events: list[dict]) -> None:
    previous = "0" * 64
    for seq, event in enumerate(events, 1):
        body = {k: v for k, v in event.items() if k != "event_sha256"}
        if event.get("sequence") != seq or event.get("previous_sha256") != previous or event.get("event_sha256") != canonical_hash(body):
            raise ValueError("Case audit chain is corrupt")
        previous = event["event_sha256"]
