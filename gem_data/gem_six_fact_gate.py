"""Fail-closed six-fact readiness gate for independent GEM SEC evidence.

This gate does not infer an approved six-fact specification from raw SEC tags.
It cannot certify until an explicit approved specification is provided.
"""
from __future__ import annotations

REQUIRED_SOURCES = frozenset(("SEC_ZIP_SUBMISSIONS", "SEC_ZIP_COMPANYFACTS"))


def assess_six_fact_readiness(receipt_audits: list[dict], approved_spec: dict | None = None) -> dict:
    passed = {r.get("provider") for r in receipt_audits
              if r.get("integrity_status") == "PASS"}
    blockers = []
    if not REQUIRED_SOURCES.issubset(passed):
        blockers.append("BOTH_INDEPENDENT_SEC_RECEIPT_AUDITS_REQUIRED")
    if not isinstance(approved_spec, dict) or len(approved_spec.get("facts", [])) != 6:
        blockers.append("APPROVED_SIX_FACT_SPECIFICATION_MISSING")
    # Even with a declared specification, source values must be extracted,
    # dated and independently reconciled before any PASS is possible.
    blockers.append("SIX_FACT_EXTRACTION_AND_RECONCILIATION_NOT_IMPLEMENTED")
    return {"fact_status": "UNKNOWN", "blockers": blockers,
            "financial_facts_certified": False,
            "dashboard_publication_authorized": False}
