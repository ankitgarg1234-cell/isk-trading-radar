"""GEM autonomous production-readiness controller (evidence-driven, fail closed).

Read-only sources and append-only diagnostic probes. Never treats collection,
Yahoo research, SEC machine candidates, or a robot-written claim as independent
source certification. A release is possible only after distinct external QA,
a full-universe rank, prospective shadow evidence, and explicit broker review.
This controller is incapable of routing orders or granting source approvals.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os

import psycopg

from gem_data.gem_public_ingest import EXPERIMENT, write_observation

SOURCE_KEYS = ("membership", "prices", "sec", "actions", "calendar", "benchmark")
REVISION = "gem-autonomous-release-20261014-v1"
PROBE_PREFIX = "gem-release-readiness-v1-"
FROZEN_COMMIT = "d59b93d3d9a87d582045b4ae71ff9a6f696a48be"


class ReadinessHold(RuntimeError):
    pass


def _gate(key, ready, evidence, action, owner):
    return {"key":key, "passed":bool(ready), "evidence":str(evidence)[:200],
            "next_action":action, "owner":owner}


def evaluate_release(integrity, gap, ledger, *, at=None):
    """Independent pure cross-check of essential production gate evidence.

    Values are derived from the current isolated database, not approved
    labels from a machine status snapshot. Source signoffs must be provided by
    a separate reviewer process; this robot never creates them.
    """
    at=at or datetime.now(timezone.utc)
    if at.tzinfo is None:
        raise ReadinessHold("Timezone-aware release clock required")
    if (integrity.get("data_access") != "CONNECTED"
            or gap.get("data_access") != "CONNECTED"):
        raise ReadinessHold("Read-only independent data inventory unavailable")
    sources=integrity.get("sources")
    if (not isinstance(sources,list) or len(sources)!=6
            or {x.get("key") for x in sources if isinstance(x,dict)}!=set(SOURCE_KEYS)):
        raise ReadinessHold("Exactly six valid independent source sections required")
    if not isinstance(ledger,dict):
        raise ReadinessHold("GEM release ledger unavailable")
    by={x["key"]:x for x in sources}
    required=("experiment_frozen_commit","mode","execution_enabled",
              "qa_approved_valid","prospective_shadow_sessions")
    if any(key not in ledger for key in required):
        raise ReadinessHold("Incomplete release ledger")
    qa=ledger["qa_approved_valid"]
    sessions=ledger["prospective_shadow_sessions"]
    if any(type(x) is not int or x<0 for x in (qa,sessions)):
        raise ReadinessHold("Invalid QA / prospective shadow counts")
    if type(ledger["execution_enabled"]) is not bool:
        raise ReadinessHold("Invalid execution permission flag")
    price=gap.get("collection")
    audit=gap.get("stored_receipt_audit")
    verification=gap.get("verification")
    if not isinstance(price,dict) or not isinstance(audit,dict) or not isinstance(verification,dict):
        raise ReadinessHold("Unverified price coverage")
    target=price.get("security_lines_target")
    observed=price.get("marketstack_histories_stored")
    certified=verification.get("independently_certified_price_histories")
    if any(type(n) is not int or n<0 for n in (target,observed,certified)):
        raise ReadinessHold("Invalid price evidence counts")
    if target != integrity.get("membership_security_lines"):
        raise ReadinessHold("Membership and price universe disagree")
    frozen=(ledger["experiment_frozen_commit"]==FROZEN_COMMIT)
    gates=[_gate("frozen_strategy",frozen,
                 "Strategy commit "+str(ledger["experiment_frozen_commit"])[:45],
                 "Restore immutable strategy version; do not change the frozen ranking",
                 "AUTOMATED_CONSISTENCY_CHECK")]
    execution_disabled=(ledger["execution_enabled"] is False
                        and ledger["mode"]=="SHADOW")
    gates.append(_gate("research_account_execution_isolated",execution_disabled,
                       f"Experiment mode {ledger['mode']}; DB execution_enabled={ledger['execution_enabled']}",
                       "Restore isolated SHADOW-only experiment, revoke direct broker"
                       " permissions and validate kill-switch before source research continues",
                       "AUTOMATED_PAPER_ISOLATION_CHECK"))
    for key in SOURCE_KEYS:
        source=by[key]
        # The source inspector is NOT an approver. Two distinct attributes
        # are necessary, and the independent QA review remains a separate gate.
        passed=(source.get("source_approval")=="APPROVED"
                and source.get("status") in ("VERIFIED","SOURCE_RECONCILED"))
        action=source.get("next_step") or "Obtain independently reviewed original evidence"
        owner=("EXTERNAL_INDEPENDENT_EVIDENCE" if key in
               ("prices","membership","actions","benchmark") else
               "AUTOMATED_COLLECTION_THEN_INDEPENDENT_REVIEW")
        gates.append(_gate("source_"+key,passed,
                           source.get("progress_tag") or source.get("status","UNKNOWN"),
                           action,owner))
    price_complete=(target>=480 and certified==target and
                    integrity.get("prices",{}).get("overall_fully_verified")==target)
    gates.append(_gate("complete_verified_price_universe",price_complete,
                       f"{certified}/{target} source-approved; {observed} vendor histories; "+
                       f"{audit.get('raw_integrity_pass',0)} intact stored receipts",
                       "Run licensed independent OHLCV and split/dividend reconciliation; "
                       "resolve all competitor identity and point-in-time gaps",
                       "AUTO_DIAGNOSIS_EXTERNAL_PROVIDER_QA"))
    sec=integrity.get("sec",{})
    qa_sec=sec.get("independently_certified")
    sec_complete=(type(qa_sec) is int and qa_sec>=500
                  and type(sec.get("source_pairs")) is int
                  and sec["source_pairs"]>=500)
    gates.append(_gate("original_sec_six_fact_qa",sec_complete,
                       f"{qa_sec} independently certified / 500 issuer contexts",
                       "Reconcile original SEC filing 10-Q facts, resolve every exception, "
                       "and obtain distinct independent reviewer signoffs",
                       "AUTO_SEC_WORKERS_PLUS_INDEPENDENT_REVIEW"))
    gates.append(_gate("reviewer_independent_qa",qa>0,
                       f"{qa} current independent, unexpired QA reviews",
                       "Independent reviewer must approve source-manifest-bound monthly "
                       "selection; collector and robot cannot sign their own output",
                       "INDEPENDENT_REVIEWER"))
    signal_count=integrity.get("approved_monthly_signals")
    ready_signal=(type(signal_count) is int and signal_count>0 and qa>0)
    gates.append(_gate("full_universe_rank_release",ready_signal,
                       f"{signal_count} approved monthly signals",
                       "Run immutable complete-universe ranking; verify competing "
                       "securities and original input SHA256 against reviewed signal",
                       "AUTO_RANKING_THEN_INDEPENDENT_QA"))
    gates.append(_gate("prospective_shadow_20_sessions",sessions>=20,
                       f"{sessions} prospective shadow sessions; retrospective not counted",
                       "Observe >=20 distinct prospective completed NYSE sessions "
                       "after approved month end, reconcile simulated fills and failures",
                       "AUTOMATED_SHADOW_TRIAL"))
    broker_ready=False  # No trading API in this deliberately read-only service.
    gates.append(_gate("separate_execution_controls",broker_ready,
                       "This GEM service has no broker gateway, order risk layer or signed release",
                       "Implement isolated broker adapters, pre-trade risk, reconcile, "
                       "kill switch, rollback drills; explicit user approval required",
                       "SEPARATE_PRODUCTION_EXECUTION_REVIEW"))
    blocked=[g["key"] for g in gates if not g["passed"]]
    # Research source QA and readiness can progress, but this component
    # deliberately has no ability to authorize broker orders.
    return {
        "schema":"gem-autonomous-production-gates-v1",
        "revision":REVISION,
        "checked_at":at.astimezone(timezone.utc).isoformat(),
        "experiment":EXPERIMENT,
        "robot_can_certify_sources":False,
        "robot_can_authorize_trades":False,
        "trading_enabled":False,
        "research_inputs_ready":all(g["passed"] for g in gates
                                    if g["key"]!="separate_execution_controls"),
        "production_trading_ready":False,
        "mode":"DIAGNOSTICS_AND_BOUNDED_REMEDIATION",
        "blocked_gates":blocked,
        "gates":gates,
        "next_repair_priority":next((g for g in gates if not g["passed"]),None),
    }


def read_release_ledger():
    readonly=os.getenv("GEM_READONLY_DATABASE_URL","")
    if not readonly.startswith("postgresql://gem_web_readonly:"):
        raise ReadinessHold("Restricted GEM reader role unavailable")
    with psycopg.connect(readonly,connect_timeout=6) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SET LOCAL statement_timeout=10000")
            cur.execute("""
                SELECT frozen_commit,mode,execution_enabled
                FROM gem_experiment WHERE experiment_id=%s LIMIT 1
            """,(EXPERIMENT,))
            row=cur.fetchone()
            if not row:
                raise ReadinessHold("Missing frozen GEM experiment")
            cur.execute("""
                SELECT COUNT(DISTINCT r.signal_id)
                FROM gem_qa_review r
                JOIN gem_signal s ON s.signal_id=r.signal_id
                WHERE s.experiment_id=%s AND s.state IN ('APPROVED','RELEASED')
                  AND r.decision='APPROVED'
                  AND r.reviewer_id IS NOT NULL
                  AND r.producer_id IS NOT NULL
                  AND r.reviewer_id<>r.producer_id
                  AND r.expires_at>%s
                  AND r.evidence_sha256=s.manifest_sha256
            """,(EXPERIMENT,datetime.now(timezone.utc)))
            qa=int(cur.fetchone()[0])
            cur.execute("""
                SELECT COUNT(DISTINCT session_date)
                FROM gem_shadow_observation
                WHERE experiment_id=%s
                  AND observation_type='PROSPECTIVE_COMPLETED_SESSION'
                  AND source_manifest_sha256 IS NOT NULL
            """,(EXPERIMENT,))
            shadow=int(cur.fetchone()[0])
    return {"experiment_frozen_commit":str(row[0]),"mode":str(row[1]),
            "execution_enabled":bool(row[2]),"qa_approved_valid":qa,
            "prospective_shadow_sessions":shadow}


def append_release_diagnostic(report):
    """Append one machine-reported snapshot, never a source certification."""
    writer=os.getenv("GEM_INGEST_DATABASE_URL","")
    if not writer.startswith("postgresql://gem_source_ingest_limited:"):
        raise ReadinessHold("Restricted GEM append-only role unavailable")
    raw=json.dumps(report,sort_keys=True,separators=(",",":"),allow_nan=False)
    digest=sha256(raw.encode()).hexdigest()
    now=datetime.fromisoformat(report["checked_at"])
    stamp=now.strftime("%Y%m%dT%H%M%S")
    probe={"probe_id":PROBE_PREFIX+stamp+"-"+digest[:16],
           "source_type":"prices", "state":"PARTIAL",
           "observed_at":now,"diagnostic_hash":digest,"sample_count":len(report["gates"]),
           "details":report}
    with psycopg.connect(writer,connect_timeout=6) as conn:
        write_observation(conn,None,probe)
    return probe["probe_id"]


def read_latest_release_diagnostic():
    reader=os.getenv("GEM_READONLY_DATABASE_URL","")
    if not reader.startswith("postgresql://gem_web_readonly:"):
        raise ReadinessHold("Restricted GEM reader role unavailable")
    with psycopg.connect(reader,connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SET LOCAL statement_timeout=8000")
            cur.execute("""
                SELECT details FROM gem_source_probe
                WHERE experiment_id=%s AND probe_id LIKE %s
                ORDER BY observed_at DESC,probe_id DESC LIMIT 1
            """,(EXPERIMENT,PROBE_PREFIX+"%"))
            row=cur.fetchone()
    if not row or not isinstance(row[0],dict):
        return {"schema":"gem-autonomous-production-gates-v1",
                "mode":"NOT_YET_EVALUATED","trading_enabled":False,
                "production_trading_ready":False,"gates":[]}
    result=row[0]
    if (result.get("schema")!="gem-autonomous-production-gates-v1"
            or result.get("production_trading_ready") is not False):
        raise ReadinessHold("Malformed or unauthorized release snapshot")
    return result
