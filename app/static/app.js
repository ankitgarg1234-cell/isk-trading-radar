const $=(s)=>document.querySelector(s); const $$=(s)=>[...document.querySelectorAll(s)];
function toast(msg){const t=$('#toast'); if(!t)return; t.textContent=msg;t.classList.remove('hidden');setTimeout(()=>t.classList.add('hidden'),4500)}
function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
async function jsonFetch(url,opts={}){const r=await fetch(url,opts);if(!r.ok)throw new Error(`${r.status} ${await r.text()}`);return await r.json()}
function money(price,currency){const n=Number(price||0);return currency==='SEK'?`${n.toFixed(2)} SEK`:`$${n.toFixed(2)}`}
function signalClass(s){return `signal-${String(s||'watch').toLowerCase().replace(/\s+/g,'-')}`}
function fitClass(s){return `risk-${String(s||'unknown').toLowerCase().replace(/\s+/g,'-')}`}
function num(v,d=0){const n=Number(v);return Number.isFinite(n)?n:d}

function candidateRowsHtml(candidates,baseCurrency='SEK'){
  if(!candidates?.length)return '<tr><td colspan="10" class="empty">Radar will populate after analysis/scan runs.</td></tr>';
  return candidates.map(c=>{
    const ownedBadge=c.owned?`<span class="mini-badge">OWN ${esc(c.owned_shares)}</span>`:'';
    const changed=c.changed?`<span class="mini-badge change">CHANGED ${esc(c.changed)}</span>`:'';
    const isBuy=['STRONG BUY','BUY','STARTER BUY'].includes(c.system_signal);const sizing=c.suggested_shares?`<b>${isBuy?`${esc(c.suggested_shares)} shares`:`Plan ${esc(c.suggested_shares)} @ trigger`}</b><small>≈ ${Math.round(num(c.suggested_capital))} ${esc(baseCurrency)}${c.projected_risk!=null?` • acct risk → ${Math.round(num(c.projected_risk))}`:''}</small>`:`<b>—</b><small>${esc(c.sizing_reason||'')}</small>`;
    const analyst=c.analyst_score!=null?`${Math.round(num(c.analyst_score))}/100`:'No consensus score';
    const exp=c.expected_yield_pct!=null?`${num(c.expected_yield_pct).toFixed(1)}%`:'—';
    return `<tr class="radar-row" data-symbol="${esc(c.symbol)}" data-search="${esc(`${c.symbol} ${c.name||''}`.toLowerCase())}" data-signal="${esc(c.system_signal)}" data-category="${esc(c.category)}" data-risk="${esc(c.risk_band)}" data-owned="${c.owned?'owned':'new'}" data-ai="${num(c.ai_score)}" data-system="${num(c.score)}" data-distance="${num(c.distance_pct,999)}" data-yield="${num(c.expected_yield_pct,-999)}">
      <td><div class="stock-cell"><b class="ticker">${esc(c.symbol)}</b><small>${esc((c.name&&c.name!==c.symbol)?c.name:c.category)}</small>${ownedBadge}${changed}</div></td>
      <td><b>${money(c.price,c.currency)}</b><small>${esc(c.category)} • Sys ${Math.round(num(c.score))} / AI ${Math.round(num(c.ai_score))}</small></td>
      <td><span class="signal-chip ${signalClass(c.system_signal)}">${esc(c.system_signal)}</span><small>${esc(c.action)}</small></td>
      <td><b>${esc(c.level_label)}</b><small>${esc(c.level_value)}</small></td>
      <td><span class="distance-chip ${c.distance==='NOW'?'now':''}">${esc(c.distance)}</span></td>
      <td><b>${c.target?num(c.target).toFixed(2):'—'}</b><small>Stop ${c.stop?num(c.stop).toFixed(2):'—'} • R/R ${c.risk_reward??'—'}×</small></td>
      <td><b>${esc(c.analyst_label)}</b><small>${esc(analyst)}</small></td>
      <td><span class="risk-fit ${fitClass(c.risk_fit)}">${esc(c.risk_fit)}</span><small>${esc(c.risk_band)} stock risk • ${Math.round(num(c.stock_risk))}/100</small></td>
      <td>${sizing}</td>
      <td><a class="text-link" href="/analysis/${encodeURIComponent(c.symbol)}">Full details</a><button type="button" class="icon-btn row-expand" aria-label="Expand ${esc(c.symbol)}">⌄</button></td>
    </tr>
    <tr class="radar-detail-row hidden" data-detail-for="${esc(c.symbol)}"><td colspan="10"><div class="radar-detail-grid">
      <div><span>Why this action</span><b>${esc(c.action_reason||'Open full details for the evidence breakdown.')}</b></div>
      <div><span>Expected return</span><b>${esc(exp)}</b></div>
      <div><span>Position sizing</span><b>${esc(c.sizing_reason||'—')}</b></div>
      <div><span>What changed</span><b>${esc(c.changed||'No action-state change in the latest snapshot')}</b></div>
      ${c.owned?`<div><span>Current position</span><b>${esc(c.owned_shares)} shares @ ${esc(c.owned_avg)}</b></div>`:''}
      <div><span>Target profile fit</span><b>${esc(c.risk_fit)}</b></div>
    </div></td></tr>`;
  }).join('');
}

function bindRadarRows(){
  $$('.radar-row').forEach(row=>row.onclick=(e)=>{
    if(e.target.closest('a,button,input,select'))return;
    const detail=document.querySelector(`[data-detail-for="${CSS.escape(row.dataset.symbol)}"]`);if(!detail)return;
    detail.classList.toggle('hidden');row.classList.toggle('expanded');
  });
  $$('.row-expand').forEach(btn=>btn.onclick=(e)=>{e.stopPropagation();const row=btn.closest('.radar-row');const detail=document.querySelector(`[data-detail-for="${CSS.escape(row.dataset.symbol)}"]`);if(detail){detail.classList.toggle('hidden');row.classList.toggle('expanded')}});
}

function applyRadarFilters(){
  const q=($('#radarSearch')?.value||'').trim().toLowerCase();
  const sig=$('#radarSignalFilter')?.value||'';const cat=$('#radarCategoryFilter')?.value||'';const risk=$('#radarRiskFilter')?.value||'';const owned=$('#radarOwnedFilter')?.value||'';
  const tbody=$('#candidateTable tbody');if(!tbody)return;
  const mains=$$('.radar-row');let visible=0;
  mains.forEach(row=>{const ok=(!q||(row.dataset.search||'').includes(q))&&(!sig||row.dataset.signal===sig)&&(!cat||row.dataset.category===cat)&&(!risk||row.dataset.risk===risk)&&(!owned||row.dataset.owned===owned);row.classList.toggle('hidden',!ok);const det=document.querySelector(`[data-detail-for="${CSS.escape(row.dataset.symbol)}"]`);if(det&&!ok)det.classList.add('hidden');if(ok)visible++});
  $('#radarNoResults')?.classList.toggle('hidden',visible!==0);
}

function sortRadar(){
  const tbody=$('#candidateTable tbody');if(!tbody)return;const mode=$('#radarSort')?.value||'actionable';
  const actionRank={'STRONG BUY':0,'BUY':1,'STARTER BUY':2,'BREAKOUT BUY':3,'TAKE PROFIT':4,'SELL':5,'STRONG SELL':6,'HOLD':7,'WAIT':8,'WATCH':9};
  const rows=$$('.radar-row').map(row=>({row,detail:document.querySelector(`[data-detail-for="${CSS.escape(row.dataset.symbol)}"]`)}));
  rows.sort((a,b)=>{if(mode==='ai')return num(b.row.dataset.ai)-num(a.row.dataset.ai);if(mode==='system')return num(b.row.dataset.system)-num(a.row.dataset.system);if(mode==='distance')return num(a.row.dataset.distance,999)-num(b.row.dataset.distance,999);if(mode==='yield')return num(b.row.dataset.yield,-999)-num(a.row.dataset.yield,-999);return (actionRank[a.row.dataset.signal]??99)-(actionRank[b.row.dataset.signal]??99)||num(b.row.dataset.ai)-num(a.row.dataset.ai)});
  rows.forEach(x=>{tbody.appendChild(x.row);if(x.detail)tbody.appendChild(x.detail)});applyRadarFilters();
}

function bindRadarControls(){
  ['#radarSearch','#radarSignalFilter','#radarCategoryFilter','#radarRiskFilter','#radarOwnedFilter'].forEach(sel=>{const el=$(sel);if(el)el.addEventListener(sel==='#radarSearch'?'input':'change',applyRadarFilters)});
  $('#radarSort')?.addEventListener('change',sortRadar);
  $('#clearRadarFilters')?.addEventListener('click',()=>{['#radarSearch','#radarSignalFilter','#radarCategoryFilter','#radarRiskFilter','#radarOwnedFilter'].forEach(sel=>{const el=$(sel);if(el)el.value=''});if($('#radarSort'))$('#radarSort').value='actionable';sortRadar()});
  bindRadarRows();
}

async function refreshLive(){
  try{
    const d=await jsonFetch('/api/live');
    const mb=$('#marketBadge'); if(mb){mb.textContent=d.market_open?'US MARKET OPEN':'US MARKET CLOSED';mb.className=`pill ${d.market_open?'green':'muted'}`}
    const ls=$('#lastScan');if(ls)ls.textContent=d.last_scan||'not yet';const us=$('#universeSize');if(us)us.textContent=d.universe_size||'loading';
    const list=$('#alertsList');if(list){list.innerHTML=d.alerts.length?d.alerts.map(a=>`<article class="alert-card ${esc(a.severity)}" data-alert-id="${a.id}"><div><b>${esc(a.title)}</b><p>${esc(a.message)}</p></div><div class="alert-actions"><span class="action-chip">${esc(a.action)}</span><button class="btn ghost ack-alert" data-id="${a.id}">Acknowledge</button></div></article>`).join(''):'<div class="empty">No unacknowledged alerts yet.</div>';bindAck()}
    const tb=$('#candidateTable tbody');if(tb){tb.innerHTML=candidateRowsHtml(d.candidates,d.base_currency||'SEK');bindRadarRows();sortRadar()}
    if($('#buyNowCount'))$('#buyNowCount').textContent=d.summary?.buy_now??0;if($('#portfolioActionCount'))$('#portfolioActionCount').textContent=d.summary?.portfolio_actions??0;if($('#deployableCash'))$('#deployableCash').textContent=Math.round(num(d.summary?.deployable_cash));if($('#accountRiskScore'))$('#accountRiskScore').textContent=Math.round(num(d.account_risk?.score));if($('#accountRiskBand'))$('#accountRiskBand').textContent=`${d.account_risk?.band||'—'} • target ${d.account_risk?.target_label||''}`;
  }catch(e){console.debug('live refresh',e)}
}
function bindAck(){$$('.ack-alert').forEach(b=>b.onclick=async()=>{try{await jsonFetch(`/alerts/${b.dataset.id}/ack`,{method:'POST'});b.closest('.alert-card')?.remove();toast('Alert acknowledged')}catch(e){toast('Could not acknowledge alert')}})}bindAck();
const scan=$('#scanNow');if(scan)scan.onclick=async()=>{scan.disabled=true;scan.textContent='Scanning…';try{const d=await jsonFetch('/api/scan-now',{method:'POST'});toast(`Scan finished: ${d.analyzed||0} deep analyses; ${d.universe_prefiltered||0}/${d.universe_size||0} universe names prefiltered this cycle`);await refreshLive()}catch(e){toast('Scan failed: '+e.message)}finally{scan.disabled=false;scan.textContent='Run scan now'}};

let importPositions=[];
function renderImport(rows){importPositions=rows||[];const wrap=$('#importPreview'),body=$('#importRows');if(!wrap||!body)return;wrap.classList.remove('hidden');body.innerHTML=importPositions.length?importPositions.map((r,i)=>`<tr data-i="${i}"><td><input data-k="symbol" value="${esc(r.symbol)}"></td><td><input data-k="shares" type="number" step="any" value="${esc(r.shares)}"></td><td><input data-k="avg_cost" type="number" step="any" value="${esc(r.avg_cost)}"></td><td><input data-k="account" value="${esc(r.account||'Screenshot')}"></td><td><button class="icon-btn remove-import" type="button">×</button></td></tr>`).join(''):'<tr><td colspan="5" class="empty">Nothing confidently extracted. Add/correct the OCR text or use manual entry.</td></tr>';$$('.remove-import').forEach(b=>b.onclick=()=>{b.closest('tr').remove()})}
function readImportRows(){return $$('#importRows tr[data-i]').map(tr=>{const obj={};tr.querySelectorAll('input[data-k]').forEach(i=>obj[i.dataset.k]=i.dataset.k==='symbol'||i.dataset.k==='account'?i.value:Number(i.value));return obj}).filter(r=>r.symbol&&r.shares>0&&r.avg_cost>0)}
async function parseOcrText(text){const d=await jsonFetch('/api/import/parse-text',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})});renderImport(d.positions);return d.positions}
const parseBtn=$('#parseText');if(parseBtn)parseBtn.onclick=async()=>{try{await parseOcrText($('#ocrText').value);toast('Text parsed — confirm/edit the rows')}catch(e){toast('Could not parse text')}};
const uploadBtn=$('#uploadScreenshot');if(uploadBtn)uploadBtn.onclick=async()=>{const file=$('#positionScreenshot').files[0];const status=$('#ocrStatus');if(!file){toast('Choose a screenshot first');return}uploadBtn.disabled=true;status.textContent='Uploading and extracting…';try{const fd=new FormData();fd.append('file',file);const r=await fetch('/api/import/screenshot',{method:'POST',body:fd});const d=await r.json();if(d.ok){renderImport(d.positions);status.textContent='Server extraction complete. Confirm/edit before saving.'}else if(d.needs_browser_ocr){if(!window.Tesseract)throw new Error('Browser OCR library is still loading. Try again in a few seconds.');status.textContent='Running free browser OCR locally…';const result=await Tesseract.recognize(file,'eng',{logger:m=>{if(m.status==='recognizing text')status.textContent=`Browser OCR ${Math.round((m.progress||0)*100)}%`}});$('#ocrText').value=result.data.text;await parseOcrText(result.data.text);status.textContent='Browser OCR complete. Confirm/edit extracted positions.'}else throw new Error(d.message||'Extraction failed')}catch(e){status.textContent='Extraction needs manual confirmation.';toast(e.message)}finally{uploadBtn.disabled=false}};
const confirmBtn=$('#confirmImport');if(confirmBtn)confirmBtn.onclick=async()=>{const rows=readImportRows();if(!rows.length){toast('No valid rows to save');return}try{const d=await jsonFetch('/api/import/confirm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({positions:rows})});toast(`${d.saved} positions saved`);setTimeout(()=>location.reload(),700)}catch(e){toast('Could not save positions')}};

bindRadarControls();
const poll=Number(document.body.dataset.livePoll||15)*1000;if($('#candidateTable')){setInterval(refreshLive,Math.max(10000,poll));}
