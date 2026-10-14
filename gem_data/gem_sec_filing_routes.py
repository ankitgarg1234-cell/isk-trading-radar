"""Authenticated read-only SEC filing detail endpoint for GEM financial tickets."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
import json
from gem_data.gem_sec_filing_lookup import lookup_filing, FilingLookupHold

router = APIRouter()


@router.get("/api/gem-portfolio/sec-filing/{cik}")
def sec_filing_details(cik: str):
    try:
        return JSONResponse(lookup_filing(cik),headers={"Cache-Control":"no-store"})
    except FilingLookupHold as exc:
        raise HTTPException(status_code=422,detail="SEC source lookup HOLD: "+str(exc)) from None



@router.get("/gem-sec-filing/{cik}", response_class=HTMLResponse)
def sec_filing_document_page(cik: str):
    from html import escape
    try:
        report=lookup_filing(cik)
    except FilingLookupHold as exc:
        raise HTTPException(status_code=422,detail="SEC source lookup HOLD: "+str(exc)) from None
    rows=[]
    for label,record in (("Latest original 10-Q",report["latest_original_10q"]),
                         ("Latest original 10-K",report["latest_original_10k"])):
        if record is None:
            rows.append("<h3>"+label+"</h3><p>No eligible filing in this cutoff.</p>")
            continue
        original=escape(record["document_url"],quote=True)
        viewer=escape(record["ix_viewer_url"],quote=True)
        rows.append("<h3>"+label+"</h3><p>Filed "
            +escape(record["filed"])+" · period "+escape(record["report_period"])
            +" · accession "+escape(record["accession"])+"</p><p>"
            +'<a href="'+original+'" rel="noopener noreferrer" target="_blank">Original SEC document</a>'
            +" · "+'<a href="'+viewer+'" rel="noopener noreferrer" target="_blank">SEC Inline XBRL viewer</a></p>')
    annual=report.get("original_10k_extracted_facts")
    if isinstance(annual,dict):
        items=annual.get("annual_fact_candidates") or []
        if isinstance(items,list):
            facts=[]
            for f in items[:45]:
                facts.append("<tr><td>"+escape(str(f.get("concept","")))
                    +"</td><td>"+escape(str(f.get("value_usd","")))
                    +"</td><td>"+escape(str(f.get("start","")))
                    +"</td><td>"+escape(str(f.get("end","")))+"</td></tr>")
            rows.append("<h3>Annual 10-K source financial facts</h3>"
                        "<p>Original document SHA256: "
                        +escape(str(annual.get("original_document_sha256","")))
                        +" · original facts are NOT automatically eligible under GEMv1's 10-Q-only quarterly gate.</p>"
                        +"<table><thead><tr><th>Concept</th><th>USD</th><th>Start</th><th>End</th></tr></thead><tbody>"
                        +"".join(facts)+"</tbody></table>")
    else:
        rows.append("<p>10-K numerical source extraction has not yet completed for this CIK.</p>")
    quarterly=report.get("original_10q_six_fact_candidates")
    if isinstance(quarterly,dict):
        rows.append("<h3>Original 10-Q financial candidates</h3><pre>"
                    +escape(json.dumps(quarterly,indent=2))+"</pre>")
    title=escape(str(report.get("company") or cik))
    body=''.join(rows)
    html_doc='''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>GEM SEC original filing</title>
<style>body{font:14px/1.55 system-ui;color:#e8eef8;background:#0c1320;max-width:1050px;margin:30px auto;padding:0 24px}a{color:#9cc7ff}
h3{border-top:1px solid #38475d;padding-top:20px}table{border-collapse:collapse;width:100%}td,th{padding:8px;border-bottom:1px solid #334158;text-align:left}
pre{white-space:pre-wrap;overflow-wrap:anywhere} .note{border-left:4px solid #cfa65b;padding:12px;background:#292418}</style>
</head><body><a href="/gem-portfolio">← GEM portfolio dashboard</a><h1>''' +title+''' · Original SEC filing evidence</h1>
<p>CIK '''+escape(cik)+''' · Signal cutoff '''+escape(report["as_of"])+'''</p>
<p class="note">Source evidence only: discovery and extraction do not certify GEM quarterly financial metrics or release monthly trade rankings.</p>
<p>Extraction state: '''+escape(str(report.get("original_xbrl_review_status")))+'''</p>'''+body+'''</body></html>'''
    return HTMLResponse(html_doc,headers={"Cache-Control":"no-store",
        "Content-Security-Policy":"default-src 'none'; style-src 'unsafe-inline'",
        "X-Content-Type-Options":"nosniff"})


@router.get("/gem-sec-filings", response_class=HTMLResponse)
def sec_original_filings_index():
    from html import escape
    from gem_data.gem_sec_exception_queue import (
        read_sec_exception_queue, SECExceptionQueueUnavailable,
    )
    try:
        report=read_sec_exception_queue(limit=600)
    except SECExceptionQueueUnavailable:
        raise HTTPException(503,"SEC review records unavailable") from None
    cells=[]
    for item in report["review_queue"]:
        cik=escape(item["cik"])
        ref="/gem-sec-filing/"+cik
        issues=escape(", ".join(item["blockers"]))
        stage=escape(item["review_stage"].replace("_"," ").title())
        reviewed=escape(item["original_inline_reviewed_at"] or "Not yet reviewed")
        cells.append('<tr><td><a href="'+ref+'">'+cik+'</a></td><td>'+issues
             +'</td><td>'+stage+'</td><td>'+reviewed+'</td></tr>')
    page='''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GEM original SEC filings</title><style>
body{background:#0c1320;color:#ecf2ff;font:14px/1.5 system-ui;max-width:1050px;margin:30px auto;padding:0 24px}
a{color:#9cc7ff}table{width:100%;border-collapse:collapse}
td,th{padding:10px;border-bottom:1px solid #38465e;text-align:left}
th{position:sticky;top:0;background:#1b2739}
p{color:#becadd}.scroller{overflow:auto}
</style></head><body>
<a href="/gem-portfolio">← GEM portfolio</a><h1>SEC original financial filings — open exceptions</h1>
<p>Click any CIK to inspect original 10-Q, 10-K, accession dates, SEC viewer links,
and successfully extracted source financial facts.</p>
<p>All outstanding source exceptions: '''+str(report["unresolved"])+''' · Original filings reviewed:
'''+str(report["original_inline_scanned"])+''' · Six-fact candidate sets recovered:
'''+str(report["original_inline_six_candidate_sets"])+''' (not independently certified)</p>
<div class="scroller"><table><thead><tr><th>CIK</th><th>Financial-data issue</th>
<th>Review status</th><th>Last original review (UTC)</th></tr></thead><tbody>'''+''.join(cells)+'''</tbody></table></div>
<p>Machine-assessed candidates do not confer investment approval. The frozen GEMv1
quarterly source rule requires separate verification before portfolio ranking.</p>
</body></html>'''
    return HTMLResponse(page,headers={"Cache-Control":"no-store",
        "Content-Security-Policy":"default-src 'none'; style-src 'unsafe-inline'",
        "X-Content-Type-Options":"nosniff"})
