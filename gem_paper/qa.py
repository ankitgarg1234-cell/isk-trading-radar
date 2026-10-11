"""Evidence-envelope checks. Execution is permanently unavailable here."""
from dataclasses import asdict, dataclass
from .common import ControlError, digest, sha256, utc
from .frozen import RULES_HASH

REQUIRED_CHECKS = frozenset({
    "frozen_rules", "historical_universe", "security_identity", "coverage",
    "sec_publication_time", "quarter_lineage", "price_observation_time",
    "momentum_rank_and_ties", "corporate_actions", "calendar_and_next_open",
    "account_reconciliation", "costs_and_affordability", "ledger_integrity",
    "retries_and_idempotency", "monitoring_and_incident_drill",
})


@dataclass(frozen=True)
class QAEvidence:
    reviewer_id: str
    producer_id: str
    signal_hash: str
    provenance_hash: str
    order_preview_hash: str
    rules_hash: str
    checked_at: str
    expires_at: str
    checks: dict
    evidence_hashes: dict


def validate_qa(qa, signal_hash, provenance_hash, preview_hash, now_at):
    if not isinstance(qa, QAEvidence):
        raise ControlError("Missing independent QA envelope")
    if not qa.reviewer_id or not qa.producer_id or qa.reviewer_id == qa.producer_id:
        raise ControlError("QA reviewer must differ from producer")
    for value in (qa.signal_hash, qa.provenance_hash, qa.order_preview_hash, qa.rules_hash):
        sha256(value)
    if (qa.signal_hash, qa.provenance_hash, qa.order_preview_hash, qa.rules_hash) != (
            signal_hash, provenance_hash, preview_hash, RULES_HASH):
        raise ControlError("QA evidence is bound to different inputs")
    checked, expires, now = utc(qa.checked_at), utc(qa.expires_at), utc(now_at)
    if not checked <= now < expires:
        raise ControlError("Stale or future QA evidence")
    if set(qa.checks) != REQUIRED_CHECKS or any(value != "PASS" for value in qa.checks.values()):
        raise ControlError("QA check missing, unknown, unresolved, or failed")
    if set(qa.evidence_hashes) != REQUIRED_CHECKS:
        raise ControlError("Every QA check requires retained evidence")
    for value in qa.evidence_hashes.values():
        sha256(value)
    return digest(asdict(qa))


def authorize_purchase(*, qa=None, signal_hash="", provenance_hash="", preview_hash="",
                       now_at="", release_signoff=None):
    """Return a denial even when all supplied evidence claims to pass.

    This version cannot authenticate reviewers/signoff or enforce server-side
    isolation and contains no broker/paper simulator submission implementation.
    Arbitrary release_signoff input therefore cannot unlock it.
    """
    reasons = ["EXECUTION_NOT_IMPLEMENTED"]
    if release_signoff is None:
        reasons.append("EXPLICIT_RELEASE_SIGNOFF_MISSING")
    try:
        validate_qa(qa, signal_hash, provenance_hash, preview_hash, now_at)
    except (ControlError, ValueError, TypeError) as exc:
        reasons.append("QA_DENIED: " + str(exc))
    return {"authorized": False, "reasons": reasons}
