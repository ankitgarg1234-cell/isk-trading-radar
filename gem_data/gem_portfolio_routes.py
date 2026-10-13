"""Authenticated GEMv1 main portfolio and data-integrity dashboard.

This page never publishes a ranked stock until approved source evidence exists.
Holdings imports are review-only drafts; no broker, automatic order or
unreviewed portfolio account mutations.
"""
from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

from gem_data.gem_source_health import IntegrityUnavailable, read_source_integrity, unavailable_integrity
from gem_data.gem_sec_exception_queue import (read_sec_exception_queue,
                                              SECExceptionQueueUnavailable)
from gem_data.gem_positions_import import (
    MAX_BYTES, PositionImportHold, parse_tabular_positions, parse_opted_in_image
)

router = APIRouter()


@router.get("/api/gem-portfolio/integrity")
def source_integrity():
    try:
        return JSONResponse(read_source_integrity(), headers={"Cache-Control": "no-store"})
    except IntegrityUnavailable:
        return JSONResponse(unavailable_integrity(), status_code=503,
                            headers={"Cache-Control": "no-store"})


@router.get("/api/gem-portfolio/sec-exceptions")
def sec_exception_queue():
    try:
        return JSONResponse(read_sec_exception_queue(limit=250),
                            headers={"Cache-Control":"no-store"})
    except SECExceptionQueueUnavailable:
        raise HTTPException(503,"SEC exception details temporarily unavailable") from None


@router.post("/api/gem-portfolio/import")
async def import_positions(file: UploadFile = File(...), image_consent: str = Form("no")):
    try:
        raw = await file.read(MAX_BYTES + 1)
        name = file.filename or ""
        if name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            media_type = {"png": "image/png", "jpg": "image/jpeg",
                          "jpeg": "image/jpeg", "webp": "image/webp"}[name.rsplit(".", 1)[-1].lower()]
            report = parse_opted_in_image(raw, media_type,
                                         explicit_consent=(image_consent == "yes"))
        else:
            report = parse_tabular_positions(name, raw)
        return JSONResponse(report, headers={"Cache-Control": "no-store"})
    except PositionImportHold as exc:
        raise HTTPException(422, "Position import HOLD: " + str(exc)[:200]) from None
    finally:
        await file.close()


_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>GEMv1 | Monthly portfolio &amp; source integrity</title>
<style>
:root{font-family:system-ui,-apple-system,Segoe UI,sans-serif;color-scheme:dark;background:#0c1320;color:#e8eef8}
*{box-sizing:border-box} body{margin:0 auto;max-width:1250px;padding:28px 24px 75px;line-height:1.45}
a{color:#a5ceff} header{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;flex-wrap:wrap}
h1{font-size:29px;margin:5px 0 8px;font-weight:720}h2{font-size:19px;margin:0 0 11px}h3{font-size:15px;margin:0}
p{margin:7px 0;color:#b9c5d5}small,.muted{font-size:12px;color:#9cabc0}
.nav{display:flex;gap:18px;flex-wrap:wrap;font-size:13px;padding-top:10px}
.panel{background:#151e2d;border:1px solid #334157;border-radius:13px;padding:20px;margin-top:22px}
.kpis,.sourcegrid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}
.kpi{background:#1c2839;padding:15px;border-radius:10px}.kpi strong{font-size:25px;display:block;margin:4px 0}
.tag{font-size:12px;border:1px solid #a07e32;border-radius:20px;padding:5px 10px;color:#f0cf7f;background:#332b1b}
.status{font-size:11px;border-radius:5px;background:#493620;color:#ffd393;padding:4px 8px}
.stocklist,.holdings{width:100%;border-collapse:collapse}.stocklist td,.stocklist th,
.holdings td,.holdings th{border-bottom:1px solid #314057;padding:11px 6px;text-align:left}
.stocklist td:last-child,.stocklist th:last-child{text-align:right}
.source{background:#1b2636;border:1px solid #3b4b62;border-radius:11px;padding:16px}
.sourceheader{display:flex;justify-content:space-between;align-items:center;gap:10px}
.flow{display:flex;gap:6px;margin:14px 0 10px}
.step{min-width:0;flex:1;height:8px;border-radius:3px;background:#414c60}
.step.partial{background:#ca9847}.step.pending{background:#465067}.step.verified,.step.complete{background:#2f9879}
.flowtext{display:flex;justify-content:space-between;gap:5px;font-size:10px;color:#a8b8c9}
dl{display:grid;grid-template-columns:auto 1fr;column-gap:12px;row-gap:5px;margin:15px 0 8px;font-size:12px}
dt{color:#9bb0c6}dd{margin:0;overflow-wrap:anywhere}
.milestone{font-size:13px;color:#d7e8f7;font-weight:600;margin:10px 0 1px}details{font-size:12px;color:#c0ccdb}summary{cursor:pointer;color:#b8d9ff}
ul{padding-left:19px;margin:9px 0}li{margin:5px 0}
progress{width:100%;height:15px;accent-color:#3e9e82}
.secsummary{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.secsummary strong{display:block;font-size:24px}
.controls{display:flex;gap:11px;align-items:center;flex-wrap:wrap;margin:12px 0}
button,.linkbutton{background:#29567c;color:#edf6ff;border:1px solid #4c779e;border-radius:7px;cursor:pointer;padding:10px 13px;font-size:13px}
button:disabled{opacity:.5;cursor:not-allowed}input[type=file],input[type=number]{color:#e4edfa}
input[type=number]{background:#202e42;border:1px solid #53647c;padding:6px;border-radius:5px;width:100px}
.warn{background:#302716;border-left:3px solid #c99b43;padding:12px;color:#f0d5a2;font-size:13px;margin:13px 0}
.draft{background:#152e29;border-left:3px solid #529b7d;padding:12px;margin:10px 0;color:#b9ebdc}
#positions{overflow-x:auto}
footer{padding-top:22px;color:#8ea1bb;font-size:12px}
@media(max-width:950px){.sourcegrid{grid-template-columns:repeat(2,1fr)}}
@media(max-width:700px){.kpis,.sourcegrid{grid-template-columns:1fr}.secsummary{grid-template-columns:repeat(2,1fr)}body{padding:20px 14px}}
</style></head>
<body>
<header><div><div class="muted">S&amp;P 500 / Frozen growth_margin5</div>
<h1>GEMv1 · Monthly portfolio</h1>
<p>Monthly stock selections, manual trade review and independently tracked data quality.</p></div>
<div class="nav"><a href="/gem-trial">Legacy diagnostics</a><a href="/gem-manual">Developer workbench</a></div></header>
<div class="warn"><strong>Data HOLD:</strong> No verified five-stock recommendation is currently approved.
You place every trade manually. This dashboard never sends broker orders.</div>
<div class="kpis" style="margin-top:18px">
<div class="kpi"><small>Next evaluation</small><strong>Month end</strong><small>After the official completed NYSE session</small></div>
<div class="kpi"><small>Target portfolio</small><strong>5 stocks</strong><small>20% target allocation each</small></div>
<div class="kpi"><small>Approved monthly signals</small><strong id="approved">—</strong><small>Only independently reviewed signals count</small></div>
</div>
<section class="panel"><h2>Monthly stock recommendations</h2>
<p>Recommendations appear only when all potentially competing S&amp;P 500 securities have sufficiently verified inputs.</p>
<table class="stocklist"><thead><tr><th>Stock</th><th>Data evidence</th><th>Target weight</th></tr></thead><tbody>
<tr><td>Awaiting verified selection 1</td><td>HOLD</td><td>20%</td></tr>
<tr><td>Awaiting verified selection 2</td><td>HOLD</td><td>20%</td></tr>
<tr><td>Awaiting verified selection 3</td><td>HOLD</td><td>20%</td></tr>
<tr><td>Awaiting verified selection 4</td><td>HOLD</td><td>20%</td></tr>
<tr><td>Awaiting verified selection 5</td><td>HOLD</td><td>20%</td></tr>
</tbody></table></section>
<section class="panel"><div class="sourceheader"><div><h2>Data integrity at a glance</h2>
<p>Live evidence inventory from the isolated GEM database. Latest collection and audit times are shown separately.</p></div>
<button id="refresh" type="button">Refresh evidence</button></div>
<div class="muted" id="generated">Reading source records…</div>
<div class="sourcegrid" id="sources"><article class="source" data-source="membership"><div class="sourceheader"><h3>S&P 500 membership</h3><span class="status">Loading</span></div><p class="muted">Checking last collection, coverage, audit and certification…</p><div class="flow"><span class="step pending"></span><span class="step pending"></span><span class="step pending"></span><span class="step pending"></span></div></article><article class="source" data-source="prices"><div class="sourceheader"><h3>Daily prices and liquidity</h3><span class="status">Loading</span></div><p class="muted">Checking last collection, coverage, audit and certification…</p><div class="flow"><span class="step pending"></span><span class="step pending"></span><span class="step pending"></span><span class="step pending"></span></div></article><article class="source" data-source="sec"><div class="sourceheader"><h3>SEC financial statements</h3><span class="status">Loading</span></div><p class="muted">Checking last collection, coverage, audit and certification…</p><div class="flow"><span class="step pending"></span><span class="step pending"></span><span class="step pending"></span><span class="step pending"></span></div></article><article class="source" data-source="actions"><div class="sourceheader"><h3>Corporate actions</h3><span class="status">Loading</span></div><p class="muted">Checking last collection, coverage, audit and certification…</p><div class="flow"><span class="step pending"></span><span class="step pending"></span><span class="step pending"></span><span class="step pending"></span></div></article><article class="source" data-source="calendar"><div class="sourceheader"><h3>NYSE trading calendar</h3><span class="status">Loading</span></div><p class="muted">Checking last collection, coverage, audit and certification…</p><div class="flow"><span class="step pending"></span><span class="step pending"></span><span class="step pending"></span><span class="step pending"></span></div></article><article class="source" data-source="benchmark"><div class="sourceheader"><h3>SPY benchmark</h3><span class="status">Loading</span></div><p class="muted">Checking last collection, coverage, audit and certification…</p><div class="flow"><span class="step pending"></span><span class="step pending"></span><span class="step pending"></span><span class="step pending"></span></div></article></div></section>
<section class="panel"><h2>SEC fundamentals — per-company verification</h2>
<p>Source receipts and machine-complete candidates are not equivalent to independently certified investment inputs.</p>
<div class="secsummary" id="secstats"><div><strong>—</strong><small>Source pairs</small></div></div>
<div style="margin-top:16px"><progress id="secprogress" max="500" value="0"></progress>
<div class="muted" id="sectext">Waiting for SEC audit records</div></div>
<div class="warn">Incomplete/unknown companies do <strong>not</strong> automatically drop out of the investment universe. Their financials must be resolved, or they must be demonstrably unable to displace the top five.</div></section>
<section class="panel"><div class="sourceheader">
<div><h2>SEC remediation queue · 185 original filing exceptions</h2>
<p>Company-level reasons and review actions. Nothing here is certified or silently removed from the investment universe.</p></div>
<button type="button" id="loadsecqueue">Load exception list</button>
</div><div id="secqueuestate" class="muted">Load to see remaining CIKs and what original SEC evidence is required.</div>
<div id="secqueue"></div>
</section>
<section class="panel"><h2>Market-data provider coverage</h2>
<p>Measured as verified 127-session price histories for the full current constituent list — not API requests or isolated sample tickers.</p>
<div class="secsummary" id="pricestats"><div><strong>—</strong><small>Marketstack</small></div></div>
<p class="muted" id="priceexplain"></p>
<p class="muted">Fallback order: Marketstack → independently checked IBKR nominal OHLCV → adjustment reconciliation. Alternate data is not automatically accepted as equivalent to frozen adjusted prices.</p></section>
<section class="panel"><h2>My holdings · manual management</h2>
<p>Import a CSV/Excel holdings export, or an image if image recognition has been enabled. Review and edit the draft below. Nothing is saved to your account or broker by importing.</p>
<div class="controls"><input type="file" id="holdingfile" accept=".csv,.xlsx,.png,.jpg,.jpeg,.webp" aria-label="Select holdings file">
<button id="parse" type="button">Import &amp; review</button>
<button id="export" type="button" disabled>Export reviewed draft</button></div>
<label class="muted"><input type="checkbox" id="consent"> If importing an image, I consent to sending it to OpenAI for position extraction. Do not include account numbers or other personal identifiers.</label>
<div id="importstate" class="muted" style="margin:11px 0">No positions imported. CSV/XLSX requires Ticker or Symbol and Shares or Quantity columns.</div>
<div id="positions"></div>
<p class="muted">Update a quantity or mark a holding closed in this <strong>draft</strong>; this is not a recorded sale. After you trade manually, the confirmed date, quantity, fill price and fees must be entered into the <a href="/gem-manual">manual reconciliation ledger</a>. Persistent brokerage-account synchronization is intentionally disabled.</p></section>
<footer>GEMv1 isolated service · Research diagnostics and manual portfolio planning only · No brokerage API or automatic execution</footer>
<script>
const $=id=>document.getElementById(id);
let draft=[];
const fmt=x=>x?new Date(x).toLocaleString(undefined,{dateStyle:"medium",timeStyle:"short",timeZone:"UTC"})+" UTC":"Not yet recorded";
function el(tag,txt,parent,cls){const node=document.createElement(tag);if(txt!=null)node.textContent=txt;if(cls)node.className=cls;parent.appendChild(node);return node}
function stat(parent,value,label){const div=el("div",null,parent);el("strong",value==null?"Unknown":String(value),div);el("small",label,div)}
async function refresh(){
 $("generated").textContent="Refreshing evidence…";
 try{
 const response=await fetch("/api/gem-portfolio/integrity",{cache:"no-store"});
 const data=await response.json();
 if(!data || !Array.isArray(data.sources) || data.sources.length!==6)
   throw new Error("Six-source integrity response missing");
 const accessible=response.ok&&data.data_access==="CONNECTED";
 $("generated").textContent=accessible
   ?"Snapshot: "+fmt(data.generated_at)+" · Read-only source evidence · Investment release: "+data.investment_release
   :"SOURCE DATA UNAVAILABLE — all six sources shown as UNKNOWN; please retry. No trade approval inferred.";
 $("approved").textContent=data.approved_monthly_signals==null?"Unknown":String(data.approved_monthly_signals);
 const box=$("sources");box.replaceChildren();
 data.sources.forEach(s=>{
  const card=el("article",null,box,"source"),head=el("div",null,card,"sourceheader");
  el("h3",s.title,head);const progress=el("span",s.progress_tag||s.status,head,"muted");progress.title="Overall certification: "+s.status+"; release: "+s.source_approval;
  el("p",s.requirement,card,"muted");
  if(s.progress_summary)el("p",s.progress_summary,card,"milestone");
  const flow=el("div",null,card,"flow"),labels=el("div",null,card,"flowtext");
  s.stages.forEach(t=>{const bar=el("span",null,flow,"step "+t.state.toLowerCase());bar.title=t.name+": "+t.state;const mark=el("span",t.name,labels);mark.title=t.state;});
  const dl=el("dl",null,card);
  [["Last collected",s.last_refreshed],["Last checked",s.last_checked],[s.audit_label||"Last independent audit",s.last_audited]].forEach(pair=>{
   el("dt",pair[0],dl);el("dd",fmt(pair[1]),dl)
  });
  if(s.next_step)el("p","Next: "+s.next_step,card,"muted");
  const details=el("details",null,card);el("summary","Evidence and gaps",details);
  const ul=el("ul",null,details);s.evidence.forEach(line=>el("li",line,ul));
  if(s.key==="membership" && data.wikipedia && data.wikipedia.securities!=null){
   el("li","Wikipedia: "+data.wikipedia.securities+" security lines / "+data.wikipedia.unique_ciks+" unique CIKs",ul);
  }
 });
 const sec=$("secstats");sec.replaceChildren();
 stat(sec,data.sec.source_pairs,"Company source pairs");
 stat(sec,data.sec.machine_assessed,"Machine-assessed");
 stat(sec,data.sec.machine_candidate_complete_not_certified,"Candidate complete (NOT certified)");
 stat(sec,data.sec.independently_certified,"Independently certified");
 $("secprogress").max=Math.max(1,data.sec.source_pairs||1);$("secprogress").value=data.sec.machine_assessed||0;
 $("sectext").textContent=data.data_access!=="CONNECTED"
     ?"SEC coverage UNKNOWN until source database connection is restored"
     :data.sec.machine_incomplete_or_unknown+" assessed incomplete/unknown · "
     +data.sec.not_machine_assessed+" not assessed · "
     +(data.sec.receipt_integrity_pass==null?"Receipt-audit details not readable with the restricted dashboard account":data.sec.receipt_integrity_pass+" independent receipt integrity passes")
     +" · Last machine audit: "+fmt(data.sec.last_machine_audit)
     +" · Top blockers: "+Object.entries(data.sec.exception_categories||{}).sort((a,b)=>b[1]-a[1]).slice(0,4).map(([k,v])=>k+": "+v).join("; ");
 const prices=$("pricestats");prices.replaceChildren();
 stat(prices,data.prices.marketstack_fully_verified,"Marketstack verified");
 stat(prices,data.prices.ibkr_fully_verified,"IBKR verified");
 stat(prices,data.prices.overall_fully_verified,"Overall verified");
 stat(prices,data.prices.security_lines_target,"Security lines targeted");
 stat(prices,data.prices.marketstack_observed_not_certified,"Marketstack observed (QA pending)");
 stat(prices,data.prices.marketstack_monthly_requests_reserved,"Monthly Marketstack requests reserved");
 stat(prices,data.prices.marketstack_rejected_bars,"Marketstack invalid session rows");
 $("priceexplain").textContent=data.prices.coverage_note+(data.prices.ibkr_diagnostic_sample==null?"":" IBKR diagnostic sample: "+data.prices.ibkr_diagnostic_sample+".");
 }catch(err){
  $("generated").textContent="SOURCE STATUS UNAVAILABLE — "+String(err.message)+"; all six categories remain UNKNOWN.";
  $("approved").textContent="Unknown";
  const fallback=$("sources");fallback.replaceChildren();
  [["membership","S&P 500 membership"],["prices","Daily prices and liquidity"],
   ["sec","SEC financial statements"],["actions","Corporate actions"],
   ["calendar","NYSE trading calendar"],["benchmark","SPY benchmark"]].forEach(([key,title])=>{
     const c=el("article",null,fallback,"source"),h=el("div",null,c,"sourceheader");
     el("h3",title,h);el("span","UNAVAILABLE",h,"status");
     el("p","Data source unavailable; no verified status or timestamp can be inferred.",c,"muted");
     const stages=el("div",null,c,"flow");for(let i=0;i<4;i++)el("span",null,stages,"step pending");
   });
  const sec=$("secstats");sec.replaceChildren();stat(sec,null,"Source pairs");stat(sec,null,"Machine-assessed");stat(sec,null,"Certified");
  const price=$("pricestats");price.replaceChildren();stat(price,null,"Marketstack");stat(price,null,"IBKR");stat(price,null,"Overall");
  $("secprogress").value=0;
  $("sectext").textContent="SEC status unavailable";
  $("priceexplain").textContent="Price coverage unavailable";
 }
}
function renderPositions(){
 const root=$("positions");root.replaceChildren();
 if(!draft.length)return;
 const table=el("table",null,root,"holdings"),head=el("thead",null,table),hr=el("tr",null,head);
 ["Ticker","Shares (editable)","Status","Action"].forEach(t=>el("th",t,hr));
 const body=el("tbody",null,table);
 draft.forEach((item,i)=>{
 const tr=el("tr",null,body);el("td",item.ticker,tr);
 const inputcell=el("td",null,tr),input=el("input",null,inputcell);
 input.type="number";input.min="0";input.max="1000000000";input.step="any";input.value=item.shares;
 input.addEventListener("change",()=>{const num=Number(input.value);
 if(!Number.isFinite(num)||num<0||num>1000000000){input.value=item.shares;return}
 item.shares=String(num);if(num>0)item.last_nonzero=String(num);renderPositions()});
 el("td",Number(item.shares)===0?"Draft closed":"Draft open",tr);
 const action=el("td",null,tr),button=el("button",Number(item.shares)===0?"Reopen draft":"Mark closed (draft)",action);
 button.addEventListener("click",()=>{item.shares=Number(item.shares)===0?(item.last_nonzero||"0"):"0";renderPositions()});
 });
 $("export").disabled=false;
}
$("loadsecqueue").onclick=async()=>{
 const root=$("secqueue");root.replaceChildren();
 $("secqueuestate").textContent="Loading exception queue…";
 try{
  const response=await fetch("/api/gem-portfolio/sec-exceptions",{cache:"no-store"});
  if(!response.ok)throw Error("SEC review evidence currently unavailable");
  const data=await response.json();
  if(data.schema!=="gem-sec-exception-review-v1")throw Error("Invalid source review response");
  $("secqueuestate").textContent=data.unresolved+" unresolved / "+data.machine_assessed
    +" machine-assessed; "+data.candidate_complete_not_certified+" candidate-complete (not certified).";
  const details=el("details",null,root);
  const summary=el("summary","Review "+data.review_queue_displayed+" CIK filing exceptions and actions",details);
  const cat=el("p","Categories: "+Object.entries(data.categories).map(
    ([name,count])=>name.replaceAll("_"," ").toLowerCase()+" "+count).join(" · "),details,"muted");
  const table=el("table",null,details,"holdings"),head=el("thead",null,table),hr=el("tr",null,head);
  ["CIK / SEC filing","Issue","Next original-source review"].forEach(t=>el("th",t,hr));
  const body=el("tbody",null,table);
  data.review_queue.forEach(item=>{
   const row=el("tr",null,body),cell=el("td",null,row);
   const link=el("a",item.cik,cell);
   link.href="https://www.sec.gov/edgar/browse/?CIK="+encodeURIComponent(item.cik);
   link.rel="noopener noreferrer";link.target="_blank";
   el("td",item.blockers.join("; "),row);
   el("td",item.actions.join("; ").replaceAll("_"," ").toLowerCase(),row);
  });
 }catch(err){$("secqueuestate").textContent=String(err.message)}
};
$("refresh").onclick=refresh;
$("parse").onclick=async()=>{
 const f=$("holdingfile").files[0];if(!f){$("importstate").textContent="Choose a file first";return}
 const image=/\.(png|jpe?g|webp)$/i.test(f.name);
 if(image&&!$("consent").checked){$("importstate").textContent="Image parsing requires explicit cloud-processing consent. Alternatively upload a CSV/XLSX.";return}
 $("importstate").textContent="Parsing review-only draft…";
 const body=new FormData();body.append("file",f);body.append("image_consent",image?"yes":"no");
 try{
 const res=await fetch("/api/gem-portfolio/import",{method:"POST",body});
 const obj=await res.json();
 if(!res.ok)throw Error(obj.detail||"File import failed");
 draft=obj.holdings.map(item=>({...item,last_nonzero:item.shares}));renderPositions();
 $("importstate").textContent=obj.positions+" positions imported to a draft. Verify tickers and quantities before use; nothing saved.";
 }catch(err){$("importstate").textContent=String(err.message)}
};
$("export").onclick=()=>{
 if(!draft.length)return;
 const obj={schema:"gem-reviewed-holdings-draft-v1",review_required:true,
             not_a_broker_order:true,server_saved:false,holdings:draft.map(item=>({ticker:item.ticker,shares:item.shares}))};
 const a=document.createElement("a"),blob=new Blob([JSON.stringify(obj,null,2)],{type:"application/json"});
 const url=URL.createObjectURL(blob);a.href=url;a.download="gem-positions-reviewed-draft.json";a.click();URL.revokeObjectURL(url);
};
refresh();
</script></body></html>"""


@router.get("/gem-portfolio", response_class=HTMLResponse)
def portfolio_dashboard():
    return HTMLResponse(_HTML, headers={
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; connect-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'",
    })
