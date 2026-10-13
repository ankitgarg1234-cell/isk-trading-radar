"""GEMv1 monthly readiness/alert classifier, manual execution only.

Consumes audited status projections. Never sends orders, claims approvals, or
changes a database. Operators can surface alerts in the authenticated UI.
"""
from __future__ import annotations

from datetime import datetime, timezone


def audit_readiness(status, *, expected_month_end=None, manual_ledger=None):
    alerts=[]
    if not isinstance(status, dict):
        status={}
    names=("membership","prices","sec","actions","calendar","benchmark")
    by_name={s.get("key"):s for s in status.get("sources",[]) if isinstance(s,dict)}
    for name in names:
        item=by_name.get(name,{})
        state=str(item.get("status","MISSING")).upper()
        if state not in ("VERIFIED","SOURCE_RECONCILED"):
            alerts.append({"severity":"HOLD","code":"SOURCE_"+name.upper(),
                           "details":"Source not independently verified: "+state[:45]})
    if status.get("ranking_ready") is not True:
        alerts.append({"severity":"HOLD","code":"RANKING_NOT_APPROVED",
                       "details":"No signed complete-universe source bundle"})
    if status.get("execution") != "DISABLED":
        alerts.append({"severity":"HOLD","code":"AUTOMATED_EXECUTION_MUST_REMAIN_DISABLED",
                       "details":"Manual broker execution is the only supported workflow"})
    if expected_month_end:
        latest=(status.get("next_signal") or {})
        if latest.get("signal_session") != expected_month_end:
            alerts.append({"severity":"HOLD","code":"MISSING_MONTH_END_SIGNAL",
                           "details":"Expected completed monthly selection not published"})
    if manual_ledger is not None:
        if not isinstance(manual_ledger,dict):
            alerts.append({"severity":"HOLD","code":"BAD_MANUAL_LEDGER",
                           "details":"Missing manually entered position statement"})
        else:
            st=manual_ledger.get("statement_status")
            if st!="USER_STATEMENT_RECONCILED":
                alerts.append({"severity":"NOTICE" if st=="NO_STATEMENT_ENTERED" else "HOLD",
                               "code":"MANUAL_BROKER_STATEMENT",
                               "details":"User statement not reconciled: "+str(st)[:45]})
    return {
        "schema":"gem-manual-readiness-v1",
        "mode":"MANUAL_EXECUTION_ONLY",
        "overall":"HOLD" if any(a["severity"]=="HOLD" for a in alerts) else
                  "REVIEW" if alerts else "SOURCE_DIAGNOSTIC_COMPLETE",
        "alerts":alerts,"alert_count":len(alerts),
        "broker_api":False,"broker_orders_sent":0,
        "historical_audit":"PARALLEL_TRACK_NOT_AUTOMATIC_PAPER_GATE",
        "readiness_claim":"SOURCE_PROJECTION_ONLY_NOT_TRADING_CERTIFICATION",
    }
