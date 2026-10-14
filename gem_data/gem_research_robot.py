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

def run_once():
    writer = os.getenv("GEM_INGEST_DATABASE_URL", "")
    if not writer.startswith("postgresql://gem_source_ingest_limited:"):
        raise RuntimeError("Append-only GEM evidence role unavailable")
    results = evaluate(read_source_integrity())
    observed = datetime.now(timezone.utc)
    stamp = observed.strftime("%Y%m%dT%H%M%SZ")
    with psycopg.connect(writer, connect_timeout=6) as conn:
        for item in results:
            payload = {"schema":"gem-robot-diagnostic-v1",**item,
                       "observed_at":observed.isoformat(),"release":"DATA_HOLD"}
            digest = sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
            probe = {"probe_id":f"{PREFIX}{stamp}-{item['source']}-{digest[:10]}",
                     "source_type":item["source"],"state":"PARTIAL",
                     "observed_at":observed,"diagnostic_hash":digest,
                     "sample_count":0,"details":payload}
            write_observation(conn,None,probe)
            conn.commit()
    return {"checked":len(results),"blocked":sum(x["status"]=="BLOCKED_EVIDENCE" for x in results),
            "timestamp":observed.isoformat(),"release":"DATA_HOLD"}

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
    return {"schema":"gem-robot-status-v1","release":"DATA_HOLD","trading_enabled":False,
            "checks":[{"observed_at":t.isoformat(),**detail} for t,detail in rows]}
