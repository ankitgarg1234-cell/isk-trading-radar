"""Authenticated, stateless GEMv1 manual-only operations workbench.

These endpoints never place orders, request broker credentials, or write
portfolio/account data. Results must be retained by the user or a future
explicitly configured GEM-only append-only store.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from gem_data.gem_manual_cli import calculate

router = APIRouter()
_MAX_BODY = 8_000_000
_OPERATIONS = {"signal", "verify", "gaps", "tickets", "ledger", "history"}


@router.get("/api/gem-manual/mode")
def manual_mode():
    return {
        "strategy": "GEMv1 archived growth_margin5",
        "mode": "MANUAL_BROKER_EXECUTION_ONLY",
        "broker_api": False, "orders_submitted": 0,
        "server_persistence": False,
        "functions": sorted(_OPERATIONS),
        "release": "RESEARCH_DIAGNOSTIC_QA_HOLD",
    }


@router.post("/api/gem-manual/run/{operation}")
async def manual_calculate(operation: str, request: Request):
    if operation not in _OPERATIONS:
        raise HTTPException(404, "Unsupported manual operation")
    size = request.headers.get("content-length")
    if size is not None:
        try:
            if int(size) > _MAX_BODY:
                raise HTTPException(413, "Manual input exceeds size cap")
        except ValueError:
            raise HTTPException(400, "Invalid content-length") from None
    if request.headers.get("content-type", "").split(";")[0] != "application/json":
        raise HTTPException(415, "JSON content type required")
    body = await request.body()
    if not body or len(body) > _MAX_BODY:
        raise HTTPException(413, "Manual input missing or oversized")
    try:
        item = json.loads(body)
        if not isinstance(item, dict):
            raise ValueError("Expected JSON object")
        return calculate(operation, item)
    except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
        raise HTTPException(422, "GEM input HOLD: " + str(exc)[:350]) from None


_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GEMv1 Manual Operations</title>
<style>
:root{font-family:system-ui,Arial,sans-serif;color-scheme:dark;background:#101521;color:#e8edf6}
body{margin:0 auto;max-width:1000px;padding:35px 22px;line-height:1.5}
h1{font-size:29px;margin:0 0 8px}h2{font-size:18px;margin:18px 0 6px}
a{color:#b1d8ff}p{color:#b5bfd0} .bar{border-left:3px solid #b9a36b;padding:8px 14px;background:#242738}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}
@media(max-width:700px){.grid{grid-template-columns:1fr}}
textarea,pre{box-sizing:border-box;width:100%;background:#171d2c;color:#dce7ff;border:1px solid #3d4660;
border-radius:8px;padding:12px;font:13px/1.45 ui-monospace,SFMono-Regular,monospace}
textarea{height:330px;resize:vertical}pre{height:330px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere}
select,button{background:#252f43;color:white;border:1px solid #65758d;border-radius:7px;padding:10px;font-size:14px}
button{cursor:pointer;background:#2e557a} .muted{font-size:13px;color:#9ba8bb} .em{color:#f6cf7c}
</style></head><body>
<a href="/gem-trial">← GEM diagnostic dashboard</a>
<h1>GEMv1 · Manual operations workbench</h1>
<p class="bar"><strong>No broker connection.</strong> You place trades manually. This tool only computes
data-gap reports, month-end rankings, indicative tickets, and ledger reconciliation from JSON you supply.
This page <strong>does not save your data</strong>. Export the report before closing it.
<span class="em">Unverified sources remain on HOLD.</span></p>
<label for="op">Choose the operation</label>
<select id="op">
<option value="verify">Full price/SEC recomputation and ranking</option>\n<option value="signal">Precomputed complete-universe ranking (diagnostic)</option>
<option value="gaps">Vendor price gap reconciliation</option>
<option value="tickets">Indicative manual trade sheet</option>
<option value="ledger">Manual fills and broker statement reconciliation</option>
<option value="history">Historical membership and action QA</option>
</select>
<div class="grid"><section><h2>Input JSON</h2><textarea id="input" spellcheck="false"
placeholder='Paste a source-reviewed JSON bundle. No example stocks are preselected.'>{}</textarea>
<button id="run" type="button">Validate and calculate</button></section>
<section><h2>Result</h2><pre id="output">No calculation made. No trades authorized.</pre>
<button id="copy" type="button">Copy result</button>
<button id="save" type="button">Save JSON report</button></section></div>
<p class="muted">The resulting share counts use reference prices, not guaranteed brokerage fills.
Only the quantities, prices and fees you enter as confirmed fills appear in the manual ledger.
Use original SEC filings, effective-dated S&P membership and reconciled vendor/alternate EOD data.
No scheduled execution is active in this interface.</p>
<script>
const box=document.getElementById("input"),out=document.getElementById("output"),
 op=document.getElementById("op");
document.getElementById("run").onclick=async()=>{
 out.textContent="Validating input...";
 try{
  const obj=JSON.parse(box.value);
  const response=await fetch("/api/gem-manual/run/"+encodeURIComponent(op.value),
   {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(obj)});
  const report=await response.json();
  out.textContent=JSON.stringify(report,null,2);
 }catch(e){out.textContent=String(e)}
};
document.getElementById("copy").onclick=()=>navigator.clipboard.writeText(out.textContent);
document.getElementById("save").onclick=()=>{
 const blob=new Blob([out.textContent],{type:"application/json"});
 const url=URL.createObjectURL(blob),a=document.createElement("a");
 a.href=url;a.download="gemv1-"+op.value+"-report.json";a.click();URL.revokeObjectURL(url);
};
</script>
</body></html>"""


@router.get("/gem-manual", response_class=HTMLResponse)
def manual_workbench():
    return HTMLResponse(_HTML, headers={
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; connect-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'",
    })
