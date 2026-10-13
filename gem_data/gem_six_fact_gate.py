"""Frozen GEMv1 six-quarter SEC evidence gate.

Six facts: revenue, parent net income, and operating income for the latest
eligible quarter and same quarter one year earlier. This is NOT a new strategy.
Original accession-specific Inline XBRL and independent provenance remain
mandatory for final certification; candidate extraction alone never grants PASS.
"""
from __future__ import annotations

from datetime import date
from gem_data.sec_independent_fact_verify import verify_receipt_pair

REQUIRED_SOURCES = frozenset(("SEC_ZIP_SUBMISSIONS", "SEC_ZIP_COMPANYFACTS"))
FROZEN_FACT_NAMES = frozenset((
    "current_revenue", "current_net_income", "current_operating_income",
    "prior_revenue", "prior_net_income", "prior_operating_income",
))


def assess_six_fact_readiness(receipt_audits: list[dict],
                              approved_spec: dict | None = None) -> dict:
    """Compatibility status for receipt-only callers; never certifies facts."""
    passed = {r.get("provider") for r in receipt_audits
              if r.get("integrity_status") == "PASS"}
    blockers = []
    if not REQUIRED_SOURCES.issubset(passed):
        blockers.append("BOTH_INDEPENDENT_SEC_RECEIPT_AUDITS_REQUIRED")
    blockers.append("ORIGINAL_ACCESSION_XBRL_RECONCILIATION_REQUIRED")
    return {"fact_status": "UNKNOWN", "blockers": blockers,
            "financial_facts_certified": False,
            "dashboard_publication_authorized": False}


def evaluate_gemv1_frozen_gate(six_facts: dict) -> dict:
    """Recompute original fundamental rules from independently extracted values."""
    if not isinstance(six_facts, dict) or set(six_facts) != FROZEN_FACT_NAMES:
        return {"status": "UNKNOWN", "blockers": ["SIX_FROZEN_FACTS_INCOMPLETE"]}
    try:
        vals = {key: float(record["value_usd"]) for key, record in six_facts.items()}
        rn, rp = vals["current_revenue"], vals["prior_revenue"]
        inc, prev = vals["current_net_income"], vals["prior_net_income"]
        op, opp = vals["current_operating_income"], vals["prior_operating_income"]
        if rn <= 0 or rp <= 0:
            raise ValueError("nonpositive revenue")
        import math
        if not all(math.isfinite(v) for v in vals.values()):
            raise ValueError("nonfinite fact")
        revenue_growth = rn / rp - 1
        earnings_improvement = inc > 0 and (prev <= 0 or inc / prev - 1 > .2)
        margin_delta_pp = 100 * (op / rn - opp / rp)
    except (ValueError, TypeError, KeyError, ZeroDivisionError, OverflowError):
        return {"status": "UNKNOWN", "blockers": ["INVALID_FINANCIAL_FACT_VALUES"]}
    return {"status": "PASS" if (revenue_growth > .2 and earnings_improvement
                                  and margin_delta_pp > 3) else "FAIL",
            "revenue_growth": revenue_growth,
            "earnings_improvement": earnings_improvement,
            "margin_delta_pp": margin_delta_pp,
            "financial_facts_certified": False,
            "dashboard_publication_authorized": False}


def audit_gemv1_receipt_pair(submissions_receipt: dict,
                             companyfacts_receipt: dict,
                             cik: str, as_of: date) -> dict:
    """Verify original stored bytes, extract candidates, recompute frozen gate."""
    result = verify_receipt_pair(submissions_receipt, companyfacts_receipt,
                                 cik, as_of)
    if (result.get("receipt_integrity") != "PASS"
            or result.get("fact_status") != "CANDIDATE_COMPLETE_NOT_CERTIFIED"):
        gate = {"status": "UNKNOWN", "blockers": result.get("blockers", [])}
    else:
        gate = evaluate_gemv1_frozen_gate(result["six_facts"])
    return {**result, "frozen_fundamental_gate": gate,
            "financial_facts_certified": False,
            "dashboard_publication_authorized": False,
            "original_accession_inline_xbrl_certified": False}
