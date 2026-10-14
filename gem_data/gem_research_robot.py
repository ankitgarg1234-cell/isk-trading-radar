"""Autonomous bounded GEM evidence checks; never source certification or trading.

Uses existing read-only source inventory and append-only GEM probe writer.
Each cycle checks every source even when another is blocked. All outcomes
persist as machine diagnostics and are visible through the dashboard API.
"""
from __future__ import annotations
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
import psycopg
from gem_data.gem_public_ingest import EXPERIMENT, write_observation
from gem_data.gem_source_health import read_source_integrity

KEYS = ("prices", "sec", "membership", "actions", "calendar", "benchmark")
PREFIX = "gem-robot-check-"

def evaluate(report):
    if report.get("data_access") != "CONNECTED" or report.get("investment_release") != "DATA_HOLD":
        raise ValueError("Source integrity not available under DATA HOLD")
    sources = report.get("sources", [])
    if len(sources) != 6 or {s.get("key") for s in sources} != set(KEYS):
        raise ValueError("Exactly six source records required")
    by_key = {s["key"]: s for s in sources}
    results = []
    for key in KEYS:
        row = by_key[key]
        approved = row.get("source_approval") == "APPROVED"
        results.append({"source":key,"status":"INDEPENDENT_REVIEW_COMPLETE" if approved else "BLOCKED_EVIDENCE",
                        "progress":row.get("progress_tag"),"next_step":row.get("next_step"),
                        "source_approval":row.get("source_approval"),
                        "certified_by_robot":False,"trading_authorized":False})
    return results

def _recover_prices():
    """Attempt bounded evidence acquisition, not signal release or certification.

    The shared database reservation lock ensures that the dedicated collector
    and this recovery task cannot double-charge a ticker on the same day.
    Provider failures are recorded as holds; no broker is reachable here.
    """
    if os.getenv("GEM_MARKETSTACK_BACKFILL_ENABLED") != "yes":
        return {"state": "DISABLED", "observed": 0, "reserved": 0}
    try:
        from gem_data.gem_marketstack_backfill import collect_batch, MarketstackBackfillHold
        outcome = collect_batch(max_tickers=3)
        return {"state": outcome["status"],
                "observed": int(outcome.get("observed_symbols", 0)),
                "reserved": int(outcome.get("new_reserved", 0)),
                "retry_eligible": int(outcome.get("retry_eligible", 0)),
                "held_for_source_review": int(outcome.get("held_for_source_review", 0)),
                "local_budget_remaining_before": int(outcome.get("monthly_remaining_local", 0))}
    except MarketstackBackfillHold:
        return {"state": "CONFIGURATION_OR_SOURCE_HOLD", "observed": 0, "reserved": 0}
    except Exception as exc:
        # Never log vendor tokens, URLs, database passwords, or raw responses.
        return {"state": "RECOVERY_ERROR_" + type(exc).__name__,
                "observed": 0, "reserved": 0}


def run_once():
    writer = os.getenv("GEM_INGEST_DATABASE_URL", "")
    if not writer.startswith("postgresql://gem_source_ingest_limited:"):
        raise RuntimeError("Append-only GEM evidence role unavailable")
    results = evaluate(read_source_integrity())
    # Perform one real, bounded recovery step per unattended cycle before
    # writing the diagnostics. Source approval remains exclusively external.
    price_recovery = _recover_prices()
    observed = datetime.now(timezone.utc)
    stamp = observed.strftime("%Y%m%dT%H%M%SZ")
    with psycopg.connect(writer, connect_timeout=6) as conn:
        for item in results:
            payload = {"schema":"gem-robot-diagnostic-v1",**item,
                       "observed_at":observed.isoformat(),"release":"DATA_HOLD"}
            if item["source"] == "prices":
                payload["autonomous_recovery"] = price_recovery
            digest = sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
            probe = {"probe_id":f"{PREFIX}{stamp}-{item['source']}-{digest[:10]}",
                     "source_type":item["source"],"state":"PARTIAL",
                     "observed_at":observed,"diagnostic_hash":digest,
                     "sample_count":0,"details":payload}
            write_observation(conn,None,probe)
            conn.commit()
    return {"checked":len(results),"blocked":sum(x["status"]=="BLOCKED_EVIDENCE" for x in results),
            "timestamp":observed.isoformat(),"release":"DATA_HOLD",
            "price_recovery":price_recovery}

def read_recent():
    readonly = os.getenv("GEM_READONLY_DATABASE_URL", "")
    if not readonly.startswith("postgresql://gem_web_readonly:"):
        raise RuntimeError("Read-only GEM evidence role unavailable")
    with psycopg.connect(readonly, connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SET LOCAL statement_timeout=8000")
            cur.execute("""SELECT DISTINCT ON (details->>'source') observed_at,details
                FROM gem_source_probe
                WHERE experiment_id=%s AND probe_id LIKE %s
                ORDER BY details->>'source', observed_at DESC, probe_id DESC""",
                (EXPERIMENT,PREFIX+"%"))
            rows = cur.fetchall()
            cur.execute("""
                SELECT COUNT(*),
                       COUNT(*) FILTER (WHERE details->>'raw_receipt_integrity_pass'='true'),
                       COUNT(*) FILTER (WHERE state='BLOCKED')
                FROM gem_source_probe
                WHERE experiment_id=%s AND probe_id LIKE %s
            """, (EXPERIMENT, "gem-price-raw-audit-v1-%"))
            price_audited, raw_pass, blocked = cur.fetchone()
    return {"schema":"gem-robot-status-v1","release":"DATA_HOLD","trading_enabled":False,
            "price_raw_receipt_qa":{
                "audited":int(price_audited),
                "raw_integrity_pass":int(raw_pass),
                "held_for_resolution":int(blocked),
                "independently_certified":0,
                "interpretation":"Raw bar integrity only; independent price parity and completed-session QA outstanding",
            },
            "checks":[{"observed_at":t.isoformat(),**detail} for t,detail in rows]}
