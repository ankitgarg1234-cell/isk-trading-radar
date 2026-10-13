"""Independent source-claim ledger for historical membership/corporate actions.

Does not certify secondary data by itself. All source receipts must be
provided externally and human-reviewed; never overwrites frozen archives.
"""
from __future__ import annotations
from collections import defaultdict
import json


def audit_historical_claims(claims: list[dict], evidence: list[dict]) -> dict:
    index = defaultdict(list)
    for item in evidence:
        if item.get("source_sha256") and item.get("claim_id"):
            index[item["claim_id"]].append(item)
    rows = []
    for claim in claims:
        cid = claim["claim_id"]
        matching = index[cid]
        primary = [e for e in matching if e.get("source_class") == "PRIMARY"
                   and e.get("raw_bytes_verified") is True
                   and e.get("effective_date_verified") is True
                   and e.get("human_reviewed") is True
                   and e.get("agrees_with_archive") is True]
        contradictions = [e for e in matching if e.get("raw_bytes_verified") is True
                          and e.get("agrees_with_archive") is False]
        status = ("CONFLICT_HOLD" if contradictions else
                  "SOURCE_RECONCILED" if primary else
                  "EVIDENCE_PENDING")
        rows.append({"claim_id":cid, "kind":claim["kind"],
                     "ticker":claim.get("ticker"),
                     "effective_date":claim.get("effective_date"),
                     "status":status, "evidence_count":len(matching)})
    return {"schema":"gem-historical-claim-audit-v1",
            "certification":"SOURCE_CLAIM_REVIEW_ONLY",
            "total":len(rows),
            "reconciled":sum(r["status"]=="SOURCE_RECONCILED" for r in rows),
            "conflicts":sum(r["status"]=="CONFLICT_HOLD" for r in rows),
            "pending":sum(r["status"]=="EVIDENCE_PENDING" for r in rows),
            "claims":rows}
