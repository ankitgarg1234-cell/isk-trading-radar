"""Authenticated GEM SEC reconciliation overview, all 500 issuers and review queue.

This is an evidence inventory only. Recovered original 10-Q candidates do
not confer independent certification, strategy eligibility, or manual trade
authorization. No writes from routes; restricted role and no broker access.
"""
from __future__ import annotations

from collections import Counter
import csv
from html import escape
from io import StringIO
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, Response
import psycopg

from gem_data.sec_fact_audit_worker import qa_as_of

router=APIRouter()
EXPERIMENT="gem-v1-forward-2026-10"


def sec_reconciliation_snapshot():
    url=os.getenv("GEM_READONLY_DATABASE_URL","")
    if not url.startswith("postgresql://gem_web_readonly:"):
        raise RuntimeError("SEC reconciliation role not configured")
    cutoff=qa_as_of().isoformat()
    with psycopg.connect(url,connect_timeout=5) as db:
        with db.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SET LOCAL statement_timeout=10000")
            cur.execute("""
                WITH qa AS(
                  SELECT DISTINCT ON (substring(details->>'scope' FROM 'CIK ([0-9]{10})'))
                    substring(details->>'scope' FROM 'CIK ([0-9]{10})') cik,
                    probe_id qa_id,details->>'fact_status' qa_status
                  FROM gem_source_probe
                  WHERE experiment_id=%s AND source_type='sec'
                    AND details->>'scope' LIKE 'Independent automated recomputation for CIK %%'
                    AND details->>'as_of'=%s
                  ORDER BY substring(details->>'scope' FROM 'CIK ([0-9]{10})'),
                    observed_at DESC,probe_id DESC
                ),
                rect AS(
                  SELECT DISTINCT ON (details->>'cik')
                    details->>'cik' cik,
                    details->>'machine_qa_probe_id' matched_qa,
                    details->>'resolution_code' code,
                    details->'facts_candidate_metrics' candidate,
                    details->'revenue_only_preliminary_screen' revenue_prescreen,
                    details->>'original_review_probe_id' original_id
                  FROM gem_source_probe
                  WHERE experiment_id=%s AND source_type='sec'
                    AND probe_id LIKE 'gem-sec-reconcile-%%'
                    AND details->>'as_of'=%s
                  ORDER BY details->>'cik',observed_at DESC,probe_id DESC
                )
                SELECT qa.cik,qa.qa_status,
                       CASE WHEN qa.qa_id=rect.matched_qa THEN rect.code END resolution,
                       CASE WHEN qa.qa_id=rect.matched_qa THEN rect.candidate END metrics,
                       CASE WHEN qa.qa_id=rect.matched_qa THEN rect.revenue_prescreen END revenue_prescreen
                FROM qa LEFT JOIN rect USING(cik)
                ORDER BY qa.cik
            """,(EXPERIMENT,cutoff,EXPERIMENT,cutoff))
            entries=[{"cik":cik,"machine_status":machine,
                      "resolution":resolution or (
                         "ALREADY_MACHINE_CANDIDATE_NOT_CERTIFIED"
                         if machine=="CANDIDATE_COMPLETE_NOT_CERTIFIED"
                         else "RECONCILIATION_PENDING"),
                      "candidate_metrics":metrics if isinstance(metrics,dict) else None,
                      "preliminary_revenue_screen":prescreen if isinstance(prescreen,dict) else None,
                      "original_filing_detail":"/gem-sec-filing/"+cik}
                     for cik,machine,resolution,metrics,prescreen in cur.fetchall()]
    machine_candidates=sum(x["machine_status"]=="CANDIDATE_COMPLETE_NOT_CERTIFIED"
                           for x in entries)
    recovered=sum(x["resolution"]=="SIX_FACTS_RECOVERED_CONTEXT_QA_REQUIRED"
                  for x in entries)
    unresolved=sum(x["machine_status"]!="CANDIDATE_COMPLETE_NOT_CERTIFIED"
                   for x in entries)
    classified=sum(x["resolution"]!="RECONCILIATION_PENDING"
                   for x in entries if x["machine_status"]!="CANDIDATE_COMPLETE_NOT_CERTIFIED")
    counts=Counter(x["resolution"] for x in entries
                   if x["machine_status"]!="CANDIDATE_COMPLETE_NOT_CERTIFIED")
    preliminary_revenue_fail=sum(
        x["machine_status"]!="CANDIDATE_COMPLETE_NOT_CERTIFIED"
        and isinstance(x["preliminary_revenue_screen"],dict)
        and x["preliminary_revenue_screen"].get("provisional_revenue_gate_fail") is True
        for x in entries
    )
    return {
        "schema":"gem-sec-reconciliation-coverage-v1",
        "as_of":cutoff,
        "issuers_machine_assessed":len(entries),
        "machine_candidate_complete_not_certified":machine_candidates,
        "machine_unresolved":unresolved,
        "original_review_reconciled":classified,
        "original_review_pending":unresolved-classified,
        "original_six_fact_candidates_recovered_not_certified":recovered,
        "combined_machine_or_original_candidates_not_certified":machine_candidates+recovered,
        "still_no_six_fact_set":unresolved-recovered,
        "preliminary_revenue_growth_gate_fail_not_certified":preliminary_revenue_fail,
        "resolution_counts":dict(sorted(counts.items())),
        "independently_certified":0,
        "rankings_approved":False,
        "investment_release":"DATA_HOLD",
        "items":[e for e in entries
                 if e["machine_status"]!="CANDIDATE_COMPLETE_NOT_CERTIFIED"],
    }


@router.get("/api/gem-portfolio/sec-reconciliation")
def sec_reconciliation_json():
    try:
        return JSONResponse(sec_reconciliation_snapshot(),
                            headers={"Cache-Control":"no-store"})
    except (psycopg.Error,RuntimeError,ValueError):
        raise HTTPException(503,"SEC reconciliation evidence unavailable") from None


@router.get("/gem-sec-reconciliation",response_class=HTMLResponse)
def sec_reconciliation_page():
    try:
        report=sec_reconciliation_snapshot()
    except (psycopg.Error,RuntimeError,ValueError):
        raise HTTPException(503,"SEC reconciliation evidence unavailable") from None
    rows=[]
    for item in report["items"]:
        cik=escape(item["cik"])
        code=escape(item["resolution"].replace("_"," ").title())
        metric=item["candidate_metrics"]
        if isinstance(metric,dict):
            figures=(str(metric.get("revenue_yoy_pct","?"))+"% revenue YoY candidate; "
                     +str(metric.get("operating_margin_delta_pp","?"))+"pp margin candidate")
        else:
            prescreen=item.get("preliminary_revenue_screen")
            if isinstance(prescreen,dict) and prescreen.get("provisional_revenue_gate_fail") is True:
                figures=(str(prescreen.get("revenue_growth_pct_candidate","?"))
                         +"% revenue YoY; provisional gate fail — source QA pending")
            else:
                figures="No complete, comparable six-fact source set"
        rows.append('<tr><td><a href="/gem-sec-filing/'+cik+'">'+cik
                    +'</a></td><td>'+code+'</td><td>'+escape(figures)+'</td></tr>')
    title="GEM SEC issuer reconciliation"
    page='''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>'''+title+'''</title><style>
body{background:#0c1320;color:#e8eef8;font:14px/1.5 system-ui;
max-width:1150px;margin:26px auto;padding:0 22px}
a{color:#a5ceff}h1{font-size:25px}table{width:100%;border-collapse:collapse}
th,td{padding:9px;border-bottom:1px solid #3b4859;text-align:left}
th{position:sticky;top:0;background:#1c2839}
.muted{color:#b6c3d5}.summary{display:flex;gap:15px;flex-wrap:wrap}
.box{background:#182337;border:1px solid #374761;border-radius:10px;padding:12px}
.box strong{display:block;font-size:24px}.scroll{overflow:auto}
</style></head><body><p><a href="/gem-portfolio">← GEM portfolio</a></p>
<h1>All SEC exceptions — financial fact reconciliation</h1>
<div class="summary">
<div class="box"><strong>'''+str(report["issuers_machine_assessed"])+'''</strong>Machine-assessed issuers</div>
<div class="box"><strong>'''+str(report["original_review_reconciled"])+'''</strong>Exceptions classified</div>
<div class="box"><strong>'''+str(report["original_six_fact_candidates_recovered_not_certified"])+'''</strong>Original six-fact sets recovered</div>
<div class="box"><strong>'''+str(report["still_no_six_fact_set"])+'''</strong>No complete six-fact set</div>
<div class="box"><strong>'''+str(report["preliminary_revenue_growth_gate_fail_not_certified"])+'''</strong>Likely revenue-growth gate failures (unverified)</div>
</div><p class="muted">Cutoff '''+escape(report["as_of"])+''' · Machine candidate-complete: '''+str(report["machine_candidate_complete_not_certified"])+''' ·
Reconciliation pending: '''+str(report["original_review_pending"])+''' · Verified for ranking: 0</p>
<p>Source evidence is not financial certification. A financial institution's custom
definitions are NOT silently substituted for GEM's operating income rule. The
investment release remains DATA HOLD. Revenue-only gate failures are
preliminary diagnostics and may not be used to exclude stocks from ranking
until independently verified.</p>
<p><a href="/gem-sec-reconciliation.csv">Download complete unresolved issuer list (CSV)</a></p>
<div class="scroll"><table><thead><tr><th>CIK / original SEC filing</th>
<th>Disposition</th><th>Recovered candidate diagnostics</th></tr></thead><tbody>'''+''.join(rows)+'''</tbody></table></div>
</body></html>'''
    return HTMLResponse(page,headers={"Cache-Control":"no-store",
          "Content-Security-Policy":"default-src 'none'; style-src 'unsafe-inline'",
          "X-Content-Type-Options":"nosniff"})


@router.get("/gem-sec-reconciliation.csv")
def sec_reconciliation_csv():
    try:
        report=sec_reconciliation_snapshot()
    except (psycopg.Error,RuntimeError,ValueError):
        raise HTTPException(503,"SEC reconciliation evidence unavailable") from None
    s=StringIO()
    writer=csv.writer(s)
    writer.writerow(("CIK","Original machine outcome","Reconciliation outcome",
                     "Revenue YoY pct candidate","Operating margin delta pp candidate",
                     "Original filing evidence page","Preliminary revenue gate fail unverified",
                     "Independently certified"))
    for item in report["items"]:
        metrics=item["candidate_metrics"] or {}
        writer.writerow((item["cik"],item["machine_status"],item["resolution"],
                         metrics.get("revenue_yoy_pct",""),
                         metrics.get("operating_margin_delta_pp",""),
                         item["original_filing_detail"],
                         "YES" if (item.get("preliminary_revenue_screen") or {}).get(
                             "provisional_revenue_gate_fail") is True else "NO_OR_UNKNOWN",
                         "NO"))
    return Response(s.getvalue(),media_type="text/csv; charset=utf-8",
         headers={"Content-Disposition":'attachment; filename="gem-sec-reconciliation.csv"',
                  "Cache-Control":"no-store","X-Content-Type-Options":"nosniff"})
