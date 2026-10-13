"""Evidence-driven display stages for GEMv1's six source pipelines.

Stages describe specific accomplished work, NOT clearance for investment
recommendations. Only a separate validated release process may authorize
a signal; this projection never elevates an audit candidate to certification.
"""
from __future__ import annotations

_STAGE_NAMES = {
    "membership": ("Lists collected", "Current population", "Ticker–CIK cross-check", "Effective dates verified"),
    "prices": ("EOD observations", "Complete 127-day coverage", "Adjustments verified", "Release approved"),
    "sec": ("SEC originals collected", "Six-fact coverage", "Machine audit performed", "PIT certification"),
    "actions": ("SEC events scanned", "Full event coverage", "Economic terms checked", "Ledger certified"),
    "calendar": ("Exchange schedule", "Completed-session coverage", "Session QA", "Calendar certified"),
    "benchmark": ("Distribution schedule", "Prices + cash dividends", "Total return reconciled", "Benchmark certified"),
}


def describe_stages(key, *, providers, membership_count, wiki_metrics,
                    sec_pairs, sec_assessed, sec_candidate_complete,
                    marketstack_observed, verified_tickers, action_scan_count):
    """Pure source-status description backed strictly by supplied evidence."""
    if key not in _STAGE_NAMES:
        raise ValueError("Unsupported GEM source")
    names = _STAGE_NAMES[key]
    secondary = "SECONDARY_GITHUB_SP500" in providers
    wiki = "WIKIPEDIA_SP500_CIK_CURRENT" in providers
    comparison = wiki_metrics.get("secondary_comparison") or {}
    identity_match = (
        secondary and wiki and comparison.get("identity_match") is True
        and 480 <= membership_count <= 600
        and wiki_metrics.get("security_lines") == membership_count
        and comparison.get("wikipedia_count") == membership_count
        and comparison.get("secondary_count") == membership_count
        and not comparison.get("cik_mismatches")
        and not comparison.get("only_wikipedia")
        and not comparison.get("only_secondary")
    )
    exchange = "NYSE_OFFICIAL" in providers
    spy_schedule = "STATE_STREET_OFFICIAL_SPY_SCHEDULE" in providers
    checks = {
        "membership": [
            "COMPLETE" if secondary and wiki else "PARTIAL" if secondary or wiki else "PENDING",
            "COMPLETE" if identity_match else "PARTIAL" if membership_count >= 480 else "PENDING",
            "COMPLETE" if identity_match else "PENDING",
            "PENDING",
        ],
        "prices": [
            "PARTIAL" if marketstack_observed else "PENDING",
            "PARTIAL" if verified_tickers else "PARTIAL" if marketstack_observed else "PENDING",
            "PARTIAL" if verified_tickers else "PENDING",
            "PENDING",
        ],
        "sec": [
            "COMPLETE" if sec_pairs >= 500 else "PARTIAL" if sec_pairs else "PENDING",
            "COMPLETE" if sec_pairs and sec_candidate_complete == sec_pairs else
            "PARTIAL" if sec_candidate_complete else "PENDING",
            "COMPLETE" if sec_pairs >= 500 and sec_assessed >= sec_pairs else
            "PARTIAL" if sec_assessed else "PENDING",
            "PENDING",
        ],
        "actions": [
            "PARTIAL" if action_scan_count else "PENDING",
            "PARTIAL" if action_scan_count else "PENDING",
            "PENDING",
            "PENDING",
        ],
        "calendar": [
            "COMPLETE" if exchange else "PENDING",
            "PENDING",
            "PENDING",
            "PENDING",
        ],
        "benchmark": [
            "COMPLETE" if spy_schedule else "PENDING",
            "PENDING",
            "PENDING",
            "PENDING",
        ],
    }
    captions = {
        "membership": (
            (f"{membership_count} securities: Wikipedia and secondary CIKs match"
             if identity_match else f"{membership_count} current securities; CIK matching pending"),
            "Official additions/removals and effective dates still require verification",
        ),
        "prices": (
            f"{marketstack_observed} Marketstack securities observed; {verified_tickers} reviewed complete histories",
            "Backfill remaining symbols and repair/reconcile invalid dates and adjustments",
        ),
        "sec": (
            f"{sec_pairs} SEC pairs, {sec_assessed} machine-assessed, {sec_candidate_complete} candidate-complete",
            "Resolve missing/ambiguous facts and independently review accession contexts",
        ),
        "actions": (
            f"Original SEC 8-Ks screened for {action_scan_count} issuers",
            "Confirm actual split/dividend/merger economics and payable-date ledger",
        ),
        "calendar": (
            "Official NYSE schedule downloaded" if exchange else "Official NYSE schedule pending",
            "Validate final completed sessions and exceptions against exchange/price observations",
        ),
        "benchmark": (
            "SPY provider distribution schedule downloaded" if spy_schedule else "SPY schedule pending",
            "Fetch actual SPY prices and cash distributions, then reconcile total returns",
        ),
    }
    return {
        "stages": [{"name": name, "state": state}
                   for name, state in zip(names, checks[key])],
        "progress_summary": captions[key][0],
        "next_step": captions[key][1],
        "source_approval": "NOT_APPROVED",
        "current_identity_matched": identity_match if key == "membership" else None,
    }
