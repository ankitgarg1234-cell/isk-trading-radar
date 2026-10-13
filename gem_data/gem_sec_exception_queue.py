"""Read-only GEM SEC remediation queue from original-accession QA observations.

Companyfacts standard tags can miss issuer extensions and direct-quarter
contexts. This produces a bounded actionable review queue; it neither guesses
facts nor grants SEC/portfolio certification. No writes or external HTTP.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import os
import re

import psycopg

from gem_data.sec_exception_triage import triage

EXPERIMENT = "gem-v1-forward-2026-10"
CIK = re.compile(r"^[0-9]{10}$")

class SECExceptionQueueUnavailable(RuntimeError):
    pass


def _category(blockers):
    text = " ".join(blockers)
    if "ambiguous_revenue_tags" in text:
        return "REVENUE_CONCEPT_RECONCILIATION"
    if "missing_operating_income" in text:
        return "OPERATING_INCOME_EXTENSION_OR_STRUCTURAL_REVIEW"
    if "missing_net_income" in text:
        return "PARENT_NET_INCOME_CONTEXT_REVIEW"
    if "missing_revenue" in text:
        return "ISSUER_SPECIFIC_REVENUE_REVIEW"
    if "older_than_210_days" in text:
        return "FILING_FRESHNESS_REVIEW"
    if "no_eligible_original_10q" in text:
        return "ORIGINAL_QUARTER_OR_DERIVED_QUARTER_REVIEW"
    return "ORIGINAL_ACCESSION_MANUAL_REVIEW"


def categorize(latest, *, captured_at=None, limit=250, inline_reviews=None):
    """Latest audit observations for distinct CIKs, oldest / hardest still visible.

    Caller should supply only one latest observation per CIK after SQL
    DISTINCT ON, but duplicates are rejected to avoid misleading counts.
    """
    if type(limit) is not int or not 1 <= limit <= 600:
        raise ValueError("Invalid review queue limit")
    inline_reviews = inline_reviews or {}
    seen = set()
    items = []
    completed = 0
    for row in latest:
        cik = row.get("cik")
        if not isinstance(cik, str) or not CIK.fullmatch(cik) or cik in seen:
            raise ValueError("Bad or duplicate SEC exception CIK")
        seen.add(cik)
        if row.get("status") == "CANDIDATE_COMPLETE_NOT_CERTIFIED":
            completed += 1
            continue
        blockers = row.get("blockers")
        if not isinstance(blockers, list) or not blockers or any(
                not isinstance(x,str) or len(x) > 180 for x in blockers):
            blockers = ["missing_or_malformed_original_filing_evidence"]
        tasks = triage(blockers)
        inline = inline_reviews.get(cik, {})
        filing_state = inline.get("classification") or "NOT_YET_SCANNED"
        if filing_state == "NOT_YET_SCANNED":
            review_stage = "AWAITING_ORIGINAL_10Q_REVIEW"
        elif filing_state == "ORIGINAL_SEC_FILING_RETRIEVAL_HOLD":
            review_stage = "ORIGINAL_DOCUMENT_RETRIEVAL_HOLD"
        elif filing_state == "SIX_DIRECT_STANDARD_CANDIDATES_NEED_CONTEXT_REVIEW":
            review_stage = "SIX_FACT_CANDIDATES_UNCERTIFIED"
        else:
            review_stage = "ORIGINAL_DOCUMENT_REVIEWED_DISCREPANCY_OPEN"
        items.append({
            "cik": cik,
            "classification": "REVIEW_REQUIRED_NOT_A_FINANCIAL_INELIGIBILITY",
            "category": _category(blockers),
            "blockers": sorted(set(blockers)),
            "actions": [t["action"] for t in tasks],
            "sec_filing_lookup": "https://www.sec.gov/edgar/browse/?CIK=" + cik,
            "source_as_of": row.get("as_of"),
            "last_machine_audit": row.get("last_audit"),
            "resolved_by_machine": False,
            "source_context_certified": False,
            "investment_eligible": None,
            "review_stage": review_stage,
            "original_inline_review_status": filing_state,
            "original_inline_candidate_six": bool(inline.get("six_candidates", False)),
            "original_inline_reviewed_at": inline.get("last_reviewed"),
            "original_filing_urls": inline.get("filing_urls", [])[:2],
        })
    counts = Counter(item["category"] for item in items)
    stages = Counter(item["review_stage"] for item in items)
    items.sort(key=lambda x: (x["review_stage"],x["category"],x["cik"]))
    return {
        "schema": "gem-sec-exception-review-v1",
        "generated_at": (captured_at or datetime.now(timezone.utc)).isoformat(),
        "source": "GEM original SEC source-pair automated observations",
        "machine_assessed": len(seen),
        "candidate_complete_not_certified": completed,
        "unresolved": len(items),
        "categories": dict(sorted(counts.items())),
        "review_stages": dict(sorted(stages.items())),
        "awaiting_original_review": stages["AWAITING_ORIGINAL_10Q_REVIEW"],
        "original_documents_reviewed_still_unresolved": (
            stages["ORIGINAL_DOCUMENT_REVIEWED_DISCREPANCY_OPEN"]
            + stages["SIX_FACT_CANDIDATES_UNCERTIFIED"]),
        "original_retrieval_holds": stages["ORIGINAL_DOCUMENT_RETRIEVAL_HOLD"],
        "review_queue": items[:limit],
        "review_queue_displayed": min(len(items),limit),
        "more_not_displayed": max(0,len(items)-limit),
        "independently_certified": 0,
        "original_inline_scanned": sum(item["original_inline_review_status"] != "NOT_YET_SCANNED"
                                      for item in items),
        "original_inline_six_candidate_sets": sum(item["original_inline_candidate_six"]
                                                for item in items),
        "auto_certification": False,
        "missing_competitors_may_not_be_silently_excluded": True,
        "next_review": "Inspect original accession-specific 10-Q Inline XBRL and validate context, scope and cutoff. Derived YTD quarters remain candidates until reviewed.",
    }


def read_sec_exception_queue(*, limit=250):
    url = os.getenv("GEM_READONLY_DATABASE_URL", "")
    if not url.startswith("postgresql://gem_web_readonly:"):
        raise SECExceptionQueueUnavailable("GEM read-only source database not configured")
    try:
        with psycopg.connect(url,connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute("SET TRANSACTION READ ONLY")
                cur.execute("SET LOCAL statement_timeout=10000")
                cur.execute("""
                    WITH latest AS (
                      SELECT DISTINCT ON (substring(details->>'scope' FROM 'CIK ([0-9]{10})'))
                        substring(details->>'scope' FROM 'CIK ([0-9]{10})') AS cik,
                        details->>'fact_status' AS status,
                        details->'blockers' AS blockers,
                        details->>'as_of' AS as_of,
                        observed_at AS last_audit
                      FROM gem_source_probe
                      WHERE experiment_id=%s AND source_type='sec'
                        AND details->>'scope' LIKE
                          'Independent automated recomputation for CIK %%'
                      ORDER BY substring(details->>'scope' FROM 'CIK ([0-9]{10})'),
                               observed_at DESC,probe_id DESC
                    )
                    SELECT cik,status,blockers,as_of,last_audit
                    FROM latest WHERE cik IS NOT NULL ORDER BY cik
                """,(EXPERIMENT,))
                rows = []
                for cik, status, blockers, as_of, last_audit in cur.fetchall():
                    rows.append({"cik": cik,"status": status,"blockers": blockers,
                                 "as_of": as_of,
                                 "last_audit": last_audit.astimezone(timezone.utc).isoformat()})
                cur.execute("""
                    WITH latest AS (
                      SELECT DISTINCT ON (details->>'cik')
                         details->>'cik' cik,
                         details->>'classification' classification,
                         details->'evidence'->>'all_six_standard_category_candidates'
                            AS six_candidates,
                         details->'filing_urls' AS filing_urls,
                         observed_at AS last_reviewed
                      FROM gem_source_probe
                      WHERE experiment_id=%s AND source_type='sec'
                        AND probe_id LIKE 'gem-sec-inline-review-%%'
                        AND details->>'cik' IS NOT NULL
                      ORDER BY details->>'cik', observed_at DESC, probe_id DESC
                    ) SELECT cik,classification,six_candidates,filing_urls,last_reviewed FROM latest
                """,(EXPERIMENT,))
                reviews={
                   cik:{"classification":classification,
                        "six_candidates":six=="true",
                        "filing_urls":filing_urls if isinstance(filing_urls,list) else [],
                        "last_reviewed":last_reviewed.astimezone(timezone.utc).isoformat()
                                         if last_reviewed is not None else None}
                   for cik,classification,six,filing_urls,last_reviewed in cur.fetchall()
                }
        return categorize(rows, limit=limit, inline_reviews=reviews)
    except (psycopg.Error,ValueError,TypeError) as exc:
        raise SECExceptionQueueUnavailable("SEC exception queue is unavailable") from None
