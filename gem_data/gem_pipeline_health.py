"""GEM-only authenticated pipeline diagnostics; never marks data certified."""
from __future__ import annotations

from datetime import datetime, timezone
import os
import psycopg

EXPERIMENT = "gem-v1-forward-2026-10"
SOURCES = ("membership", "prices", "sec", "actions", "calendar", "benchmark")


def pipeline_health() -> dict:
    now = datetime.now(timezone.utc).isoformat()
    base = {
        "as_of": now, "status": "BLOCKED",
        "certification_complete": False,
        "dashboard_publication_authorized": False,
        "sources": {s: "UNKNOWN" for s in SOURCES},
    }
    url = os.getenv("GEM_READONLY_DATABASE_URL", "")
    if not url.startswith("postgresql://"):
        return {**base, "reason": "READONLY_DATABASE_NOT_CONFIGURED"}
    try:
        with psycopg.connect(url, connect_timeout=4) as conn:
            with conn.cursor() as cur:
                cur.execute("SET TRANSACTION READ ONLY")
                cur.execute("SET LOCAL statement_timeout = 4500")
                cur.execute(
                    """SELECT source_type, count(*), max(collected_at)
                       FROM gem_source_receipt WHERE experiment_id=%s
                       GROUP BY source_type""", (EXPERIMENT,)
                )
                receipts = {source: {"count": int(count), "latest_collected_at": stamp.isoformat()}
                            for source, count, stamp in cur.fetchall() if source in SOURCES}
                cur.execute(
                    """SELECT count(*), count(*) FILTER (WHERE integrity_status='PASS')
                       FROM gem_sec_independent_receipt_audit WHERE experiment_id=%s""",
                    (EXPERIMENT,),
                )
                audited, passed = (int(x) for x in cur.fetchone())
                cur.execute(
                    "SELECT count(*) FROM gem_sec_independent_fact_audit WHERE experiment_id=%s",
                    (EXPERIMENT,),
                )
                facts = int(cur.fetchone()[0])
        base["receipts"] = receipts
        base["sec_integrity_audits"] = {"total": audited, "passed": passed}
        base["sec_financial_fact_audits"] = facts
        base["reason"] = "INDEPENDENT_CERTIFICATION_INCOMPLETE"
        return base
    except (psycopg.Error, ValueError, TypeError):
        return {**base, "reason": "PIPELINE_HEALTH_QUERY_FAILED"}
