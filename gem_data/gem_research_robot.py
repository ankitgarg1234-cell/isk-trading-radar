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
from gem_data.gem_autonomous_release import (evaluate_release, read_release_ledger,
                                              append_release_diagnostic,
                                              read_latest_release_diagnostic)
from gem_data.gem_price_gap_progress import read_gap_progress
from gem_data.gem_python_machine_qa import (
    project_machine_qa, read_sec_machine_audit, MachineEvidenceUnavailable,
)

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


def _recover_raw_receipts():
    """Run another bounded integrity pass; receipt audit is not market QA."""
    if os.getenv("GEM_PRICE_RECEIPT_AUDIT_ENABLED", "yes") != "yes":
        return {"state":"DISABLED","audited":0}
    try:
        from gem_data.gem_price_receipt_audit import audit_batch, ReceiptAuditHold
        result=audit_batch(max_receipts=5)
        return {"state":"RAW_INTEGRITY_CHECK_ONLY","audited":result["checked"],
                "raw_pass":result["raw_integrity_pass"],
                "held":result["requires_resolution"]}
    except ReceiptAuditHold:
        return {"state":"CONFIGURATION_HOLD","audited":0}
    except Exception as exc:
        return {"state":"RAW_AUDIT_ERROR_"+type(exc).__name__,"audited":0}


def _recover_sec_facts():
    """Independent automated fact *candidates* only; original context QA separate."""
    if os.getenv("GEM_SEC_FACT_AUDIT_ENABLED") != "yes":
        return {"state":"DISABLED","audited":0}
    try:
        from gem_data.sec_fact_audit_worker import audit_batch, QAHold
        result=audit_batch(max_pairs=2)
        return {"state":"MACHINE_CANDIDATES_NOT_CERTIFIED","audited":result["audited"],
                "remaining":result["remaining_after_estimate"]}
    except QAHold:
        return {"state":"CONFIGURATION_HOLD","audited":0}
    except Exception as exc:
        return {"state":"SEC_AUDIT_ERROR_"+type(exc).__name__,"audited":0}


def _reconcile_ibkr_gaps():
    """Optional entitled IBKR historical Web API reconciliation, no orders."""
    if os.getenv("GEM_IBKR_HISTORICAL_READONLY_ENABLED")!="yes":
        return {"state":"READONLY_IBKR_SSO_NOT_CONFIGURED","requested_symbols":0,
                "machine_agreements":0,"trading_authorized":False}
    try:
        from gem_data.gem_ibkr_gap_crosscheck import crosscheck_batch,IBKRGatewayHold
        result=crosscheck_batch(max_symbols=2)
        return {"state":"PROVISIONAL_INDEPENDENT_OHLC_CHECK_ONLY",
                "requested_symbols":result["requested_symbols"],
                "machine_agreements":result["machine_agreements"],
                "price_conflicts":result["price_conflicts"],
                "holds":result["holds"],"trading_authorized":False}
    except IBKRGatewayHold:
        return {"state":"IBKR_READONLY_ENTITLEMENT_OR_SESSION_HOLD",
                "requested_symbols":0,"machine_agreements":0,
                "trading_authorized":False}
    except Exception as exc:
        return {"state":"IBKR_READONLY_ERROR_"+type(exc).__name__,
                "requested_symbols":0,"machine_agreements":0,
                "trading_authorized":False}


def _evaluate_and_record_release():
    """Recompute a separate immutable release gate every unattended cycle."""
    sources=read_source_integrity()
    price=read_gap_progress()
    ledger=read_release_ledger()
    try:
        qa=project_machine_qa(sources,price,read_sec_machine_audit())
    except MachineEvidenceUnavailable:
        qa={"schema":"gem-python-machine-qa-v1","state":"EVIDENCE_UNAVAILABLE",
            "machine_checks_passed":0,"machine_checks_total":0,
            "independent_source_approval":False,"trading_enabled":False,
            "checks":[]}
    report=evaluate_release(sources,price,ledger,machine_qa=qa)
    append_release_diagnostic(report)
    return {"state":"EVALUATED","research_inputs_ready":report["research_inputs_ready"],
            "production_trading_ready":False,
            "machine_passed":qa["machine_checks_passed"],
            "machine_total":qa["machine_checks_total"],
            "blocked_gates":report["blocked_gates"]}


def run_once():
    writer = os.getenv("GEM_INGEST_DATABASE_URL", "")
    if not writer.startswith("postgresql://gem_source_ingest_limited:"):
        raise RuntimeError("Append-only GEM evidence role unavailable")
    results = evaluate(read_source_integrity())
    # Perform one real, bounded recovery step per unattended cycle before
    # writing the diagnostics. Source approval remains exclusively external.
    price_recovery = _recover_prices()
    raw_recovery = _recover_raw_receipts()
    sec_recovery = _recover_sec_facts()
    ibkr_recovery = _reconcile_ibkr_gaps()
    try:
        release = _evaluate_and_record_release()
    except Exception as exc:
        release = {"state": "RELEASE_CHECK_UNAVAILABLE_" + type(exc).__name__,
                   "research_inputs_ready": False,"production_trading_ready": False,
                   "blocked_gates": ["INDEPENDENT_RELEASE_EVIDENCE_UNAVAILABLE"]}
    observed = datetime.now(timezone.utc)
    stamp = observed.strftime("%Y%m%dT%H%M%SZ")
    with psycopg.connect(writer, connect_timeout=6) as conn:
        for item in results:
            payload = {"schema":"gem-robot-diagnostic-v1",**item,
                       "observed_at":observed.isoformat(),"release":"DATA_HOLD"}
            if item["source"] == "prices":
                payload["autonomous_recovery"] = price_recovery
                payload["raw_receipt_recovery"] = raw_recovery
                payload["ibkr_readonly_gap_check"] = ibkr_recovery
                payload["release_check_execution"] = release
            if item["source"] == "sec":
                payload["sec_fact_recovery"] = sec_recovery
            digest = sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
            probe = {"probe_id":f"{PREFIX}{stamp}-{item['source']}-{digest[:10]}",
                     "source_type":item["source"],"state":"PARTIAL",
                     "observed_at":observed,"diagnostic_hash":digest,
                     "sample_count":0,"details":payload}
            write_observation(conn,None,probe)
            conn.commit()
    return {"checked":len(results),"blocked":sum(x["status"]=="BLOCKED_EVIDENCE" for x in results),
            "timestamp":observed.isoformat(),"release":"DATA_HOLD",
            "price_recovery":price_recovery,
            "raw_receipt_recovery":raw_recovery,"sec_fact_recovery":sec_recovery,
            "ibkr_readonly_gap_check":ibkr_recovery,
            "release_readiness":release}

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
    try:
        release_readiness=read_latest_release_diagnostic()
    except Exception:
        release_readiness={"schema":"gem-autonomous-production-gates-v1",
                           "mode":"UNAVAILABLE","trading_enabled":False,
                           "production_trading_ready":False,"gates":[]}
    return {"schema":"gem-robot-status-v1","release":"DATA_HOLD","trading_enabled":False,
            "release_readiness":release_readiness,
            "price_raw_receipt_qa":{
                "audited":int(price_audited),
                "raw_integrity_pass":int(raw_pass),
                "held_for_resolution":int(blocked),
                "independently_certified":0,
                "interpretation":"Raw bar integrity only; independent price parity and completed-session QA outstanding",
            },
            "checks":[{"observed_at":t.isoformat(),**detail} for t,detail in rows]}
