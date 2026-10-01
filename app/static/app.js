const $=(s)=>document.querySelector(s); const $$=(s)=>[...document.querySelectorAll(s)];
function toast(msg){const t=$('#toast'); if(!t)return; t.textContent=msg;t.classList.remove('hidden');setTimeout(()=>t.classList.add('hidden'),4500)}
function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
async function jsonFetch(url,opts={}){const r=await fetch(url,opts);if(!r.ok)throw new Error(`${r.status} ${await r.text()}`);return await r.json()}
function money(price,currency){const n=Number(price||0);return currency==='SEK'?`${n.toFixed(2)} SEK`:`$${n.toFixed(2)}`}
function signalClass(s){return `signal-${String(s||'watch').toLowerCase().replace(/\s+/g,'-')}`}
function fitClass(s){return `risk-${String(s||'unknown').toLowerCase().replace(/\s+/g,'-')}`}
function num(v,d=0){const n=Number(v);return Number.isFinite(n)?n:d}

function laneHeaderHtml(lane,count){
  const label=lane==='EXPLOSIVE'?'Explosive Lane':'Core Quality Lane';
  const note=lane==='EXPLOSIVE'?'Catalyst-driven • max 20 U.S. trading sessions • anti-promotion gate enforced':'Fundamental quality • durable growth • valuation-aware';
  return `<tr class="lane-group-row" data-lane-header="${esc(lane)}"><td colspan="10"><div><b>${label}</b><span>${note}</span><em>${count} stock${count===1?'':'s'}</em></div></td></tr>`;
}
function candidateRowsHtml(candidates,baseCurrency='SEK'){
  if(!candidates?.length)return '<tr><td colspan="10" class="empty">Radar will populate after analysis/scan runs.</td></tr>';
  const grouped=['CORE_QUALITY','EXPLOSIVE'];
  return grouped.map(lane=>{
    const rows=candidates.filter(c=>(c.lane||'CORE_QUALITY')===lane);
    if(!rows.length)return '';
    return laneHeaderHtml(lane,rows.length)+rows.map(c=>{
      const ownedBadge=c.owned?`<span class="mini-badge">OWN ${esc(c.owned_shares)}</span>`:'';
      const changed=c.changed?`<span class="mini-badge change">CHANGED ${esc(c.changed)}</span>`:'';
      const bucket=String(c.optimizer_bucket||'RESERVE');const bucketClass=`optimizer-${bucket.toLowerCase().replace(/\s+/g,'-')}`;const optimizerBadge=`<span class="mini-badge optimizer-badge ${bucketClass}">${esc(bucket)}</span>`;
      const laneLabel=c.lane_label||(lane==='EXPLOSIVE'?'Explosive Lane':'Core Quality Lane');
      const laneBadge=`<span class="lane-badge lane-${lane.toLowerCase().replace(/_/g,'-')}">${esc(laneLabel)}</span>`;
      const isBuy=['STRONG BUY','BUY','STARTER BUY'].includes(c.system_signal);const sizing=c.suggested_shares?`<b>${isBuy?`${esc(c.suggested_shares)} shares`:`Plan ${esc(c.suggested_shares)} @ trigger`}</b><small>≈ ${Math.round(num(c.suggested_capital))} ${esc(baseCurrency)}${c.projected_risk!=null?` • acct risk → ${Math.round(num(c.projected_risk))}`:''}</small>`:`<b>—</b><small>${esc(c.sizing_reason||'')}</small>`;
      const analyst=c.analyst_score!=null?`${Math.round(num(c.analyst_score))}/100`:'No consensus score';
      const exp=c.expected_yield_pct!=null?`${num(c.expected_yield_pct).toFixed(1)}%`:'—';
      return `<tr class="radar-row" data-symbol="${esc(c.symbol)}" data-search="${esc(`${c.symbol} ${c.name||''}`.toLowerCase())}" data-name="${esc(String(c.name||'').toLowerCase())}" data-signal="${esc(c.system_signal)}" data-category="${esc(laneLabel)}" data-lane="${esc(lane)}" data-risk="${esc(c.risk_band)}" data-owned="${c.owned?'owned':'new'}" data-ai="${num(c.ai_score)}" data-system="${num(c.score)}" data-distance="${num(c.distance_pct,999)}" data-distance-label="${esc(c.distance)}" data-yield="${c.expected_yield_pct==null?'':num(c.expected_yield_pct)}" data-price="${num(c.price)}" data-level="${esc(c.level_label)}" data-target="${c.target==null?'':num(c.target)}" data-stop="${c.stop==null?'':num(c.stop)}" data-rr="${c.risk_reward==null?'':num(c.risk_reward)}" data-analyst-label="${esc(c.analyst_label)}" data-analyst-score="${c.analyst_score==null?'':num(c.analyst_score)}" data-risk-fit="${esc(c.risk_fit)}" data-stock-risk="${num(c.stock_risk)}" data-suggested-shares="${num(c.suggested_shares)}" data-suggested-capital="${num(c.suggested_capital)}" data-portfolio-rank="${num(c.portfolio_rank_score)}" data-optimizer-bucket="${esc(c.optimizer_bucket||'RESERVE')}">
        <td><div class="stock-cell"><b class="ticker">#${esc(c.market_rank||'—')} ${esc(c.symbol)}</b><small>${esc((c.name&&c.name!==c.symbol)?c.name:c.category)}</small>${laneBadge}${optimizerBadge}${ownedBadge}${changed}</div></td>
        <td><b>${money(c.price,c.currency)}</b><small>${c.day_change_pct!=null?`<span class="${num(c.day_change_pct)>=0?'pos':'neg'}">Day ${num(c.day_change_pct)>=0?'+':''}${num(c.day_change_pct).toFixed(2)}%</span> • `:''}Priority ${Math.round(num(c.portfolio_rank_score))}/100 • Sys ${Math.round(num(c.score))} / AI ${Math.round(num(c.ai_score))}</small></td>
        <td><span class="signal-chip ${signalClass(c.system_signal)}">${esc(c.system_signal)}</span><small>${esc(c.optimizer_action||'PASS')}</small><small class="subtle">${esc(c.optimizer_decision_reason||'')}</small><small class="subtle">Raw: ${esc(c.action)}</small></td>
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
        <div><span>Portfolio priority</span><b>#${esc(c.market_rank||'—')} • ${num(c.portfolio_rank_score).toFixed(1)}/100 • ${esc(c.optimizer_bucket||'RESERVE')}</b></div>
        <div><span>Lane</span><b>${esc(laneLabel)}</b></div>
        <div><span>Independent confirmation</span><b>AI ${esc(c.ai_confirmation||'UNAVAILABLE')} • Analyst ${esc(c.analyst_confirmation||'UNAVAILABLE')}</b></div>
      </div></td></tr>`;
    }).join('');
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

function optionalNumber(selector){const el=$(selector);if(!el||String(el.value).trim()==='')return null;const n=Number(el.value);return Number.isFinite(n)?n:null}
function optionalDatasetNumber(row,key){const raw=row.dataset[key];if(raw==null||raw==='')return null;const n=Number(raw);return Number.isFinite(n)?n:null}
function textMatch(value,operator,query){if(!query)return true;const v=String(value||'').toLowerCase(),q=String(query||'').toLowerCase();if(operator==='starts')return v.startsWith(q);if(operator==='is')return v===q;if(operator==='not_contains')return !v.includes(q);return v.includes(q)}
function stockMatch(row,operator,query){if(!query)return true;const q=String(query).toLowerCase(),symbol=String(row.dataset.symbol||'').toLowerCase(),name=String(row.dataset.name||'').toLowerCase(),combined=`${symbol} ${name}`.trim();if(operator==='is')return symbol===q||name===q;if(operator==='starts')return symbol.startsWith(q)||name.startsWith(q);if(operator==='not_contains')return !combined.includes(q);return combined.includes(q)}
function discreteMatch(value,operator,expected){if(!expected)return true;const eq=String(value||'')===String(expected);return operator==='is_not'?!eq:eq}
function numericMatch(value,operator,expected){if(expected==null)return true;if(value==null)return false;if(operator==='lte')return value<=expected;if(operator==='gt')return value>expected;if(operator==='lt')return value<expected;if(operator==='eq')return Math.abs(value-expected)<1e-9;return value>=expected}
function activeFilterCount(){
  const ids=['#radarSearch','#radarStockValue','#radarCategoryFilter','#radarOwnedFilter','#radarPriceValue','#radarSignalFilter','#radarSystemMin','#radarAiMin','#radarLevelFilter','#radarDistanceValue','#radarTargetValue','#radarAnalystFilter','#radarAnalystMin','#radarFitFilter','#radarRiskFilter','#radarStockRiskMax','#radarSizeFilter','#radarSizeValue'];
  return ids.reduce((n,sel)=>n+(String($(sel)?.value||'').trim()!==''?1:0),0)
}
function stopDownsidePct(price,stop){return price!=null&&stop!=null&&price>0&&stop<price?((price-stop)/price*100):null}

function applyRadarFilters(){
  const globalQ=($('#radarSearch')?.value||'').trim().toLowerCase();
  const stockQ=($('#radarStockValue')?.value||'').trim();const stockOp=$('#radarStockOperator')?.value||'contains';
  const category=$('#radarCategoryFilter')?.value||'',owned=$('#radarOwnedFilter')?.value||'';
  const priceOp=$('#radarPriceOperator')?.value||'gte',priceValue=optionalNumber('#radarPriceValue');
  const signalOp=$('#radarSignalOperator')?.value||'is',signal=$('#radarSignalFilter')?.value||'';
  const systemMin=optionalNumber('#radarSystemMin'),aiMin=optionalNumber('#radarAiMin');
  const levelOp=$('#radarLevelOperator')?.value||'is',level=$('#radarLevelFilter')?.value||'';
  const distanceOp=$('#radarDistanceOperator')?.value||'within',distanceValue=optionalNumber('#radarDistanceValue');
  const targetMetric=$('#radarTargetMetric')?.value||'yield',targetOp=$('#radarTargetOperator')?.value||'gte',targetValue=optionalNumber('#radarTargetValue');
  const analystOp=$('#radarAnalystOperator')?.value||'is',analyst=$('#radarAnalystFilter')?.value||'',analystMin=optionalNumber('#radarAnalystMin');
  const fitOp=$('#radarFitOperator')?.value||'is',fit=$('#radarFitFilter')?.value||'',riskBand=$('#radarRiskFilter')?.value||'',stockRiskMax=optionalNumber('#radarStockRiskMax');
  const sizeState=$('#radarSizeFilter')?.value||'',sizeMetric=$('#radarSizeMetric')?.value||'shares',sizeOp=$('#radarSizeOperator')?.value||'gte',sizeValue=optionalNumber('#radarSizeValue');
  const mains=$$('.radar-row');let visible=0;
  mains.forEach(row=>{
    const price=optionalDatasetNumber(row,'price'),system=optionalDatasetNumber(row,'system'),ai=optionalDatasetNumber(row,'ai'),distance=optionalDatasetNumber(row,'distance');
    const expectedYield=optionalDatasetNumber(row,'yield'),rr=optionalDatasetNumber(row,'rr'),target=optionalDatasetNumber(row,'target'),stop=optionalDatasetNumber(row,'stop');
    const analystScore=optionalDatasetNumber(row,'analystScore'),stockRisk=optionalDatasetNumber(row,'stockRisk'),shares=optionalDatasetNumber(row,'suggestedShares')||0,capital=optionalDatasetNumber(row,'suggestedCapital')||0;
    const stopRisk=stopDownsidePct(price,stop);
    let targetMetricValue=expectedYield;if(targetMetric==='rr')targetMetricValue=rr;else if(targetMetric==='stop_risk')targetMetricValue=stopRisk;else if(targetMetric==='target')targetMetricValue=target;
    const analystValue=(row.dataset.analystScore==null||row.dataset.analystScore==='')?'__NONE__':row.dataset.analystLabel;
    const analystExpected=analyst==='__NONE__'?'__NONE__':analyst;
    const sizeStateOk=!sizeState||(sizeState==='sized'?shares>0:shares<=0);
    const sizeMetricValue=sizeMetric==='capital'?capital:shares;
    const distanceOk=distanceOp==='now'?(String(row.dataset.distanceLabel||'').toUpperCase()==='NOW'):(distanceValue==null?true:(distanceOp==='at_least'?distance>=distanceValue:distance<=distanceValue));
    const ok=(!globalQ||(row.dataset.search||'').includes(globalQ))
      &&stockMatch(row,stockOp,stockQ)
      &&(!category||row.dataset.category===category)&&(!owned||row.dataset.owned===owned)
      &&numericMatch(price,priceOp,priceValue)
      &&discreteMatch(row.dataset.signal,signalOp,signal)
      &&(systemMin==null||(system!=null&&system>=systemMin))&&(aiMin==null||(ai!=null&&ai>=aiMin))
      &&discreteMatch(row.dataset.level,levelOp,level)&&distanceOk
      &&numericMatch(targetMetricValue,targetOp,targetValue)
      &&discreteMatch(analystValue,analystOp,analystExpected)&&(analystMin==null||(analystScore!=null&&analystScore>=analystMin))
      &&discreteMatch(row.dataset.riskFit,fitOp,fit)&&(!riskBand||row.dataset.risk===riskBand)&&(stockRiskMax==null||(stockRisk!=null&&stockRisk<=stockRiskMax))
      &&sizeStateOk&&numericMatch(sizeMetricValue,sizeOp,sizeValue);
    row.classList.toggle('hidden',!ok);const det=document.querySelector(`[data-detail-for="${CSS.escape(row.dataset.symbol)}"]`);if(det&&!ok)det.classList.add('hidden');if(ok)visible++;
  });
  $('.lane-group-row').forEach(h=>{
    const lane=h.dataset.laneHeader||'';
    const count=$('.radar-row').filter(r=>r.dataset.lane===lane&&!r.classList.contains('hidden')).length;
    h.classList.toggle('hidden',count===0);
    const em=h.querySelector('em');if(em)em.textContent=`${count} stock${count===1?'':'s'}`;
  });
  $('#radarNoResults')?.classList.toggle('hidden',visible!==0);
  if($('#radarResultCount'))$('#radarResultCount').textContent=`${visible} shown`;
  if($('#columnFilterCount'))$('#columnFilterCount').textContent=`${activeFilterCount()} filters`;
}

function sortRadar(){
  const tbody=$('#candidateTable tbody');if(!tbody)return;const mode=$('#radarSort')?.value||'actionable';
  const actionRank={'STRONG BUY':0,'BUY':1,'STARTER BUY':2,'BREAKOUT BUY':3,'TAKE PROFIT':4,'SELL':5,'STRONG SELL':6,'HOLD':7,'WAIT':8,'WATCH':9};
  const rows=$$('.radar-row').map(row=>({row,detail:document.querySelector(`[data-detail-for="${CSS.escape(row.dataset.symbol)}"]`)}));
  const cmp=(a,b)=>{if(mode==='ai')return num(b.row.dataset.ai)-num(a.row.dataset.ai);if(mode==='system')return num(b.row.dataset.system)-num(a.row.dataset.system);if(mode==='distance')return num(a.row.dataset.distance,999)-num(b.row.dataset.distance,999);if(mode==='yield')return num(b.row.dataset.yield,-999)-num(a.row.dataset.yield,-999);if(mode==='price-low')return num(a.row.dataset.price,Infinity)-num(b.row.dataset.price,Infinity);if(mode==='price-high')return num(b.row.dataset.price,-Infinity)-num(a.row.dataset.price,-Infinity);if(mode==='analyst')return num(b.row.dataset.analystScore,-1)-num(a.row.dataset.analystScore,-1);if(mode==='risk-low')return num(a.row.dataset.stockRisk,999)-num(b.row.dataset.stockRisk,999);if(mode==='rr')return num(b.row.dataset.rr,-1)-num(a.row.dataset.rr,-1);if(mode==='size')return num(b.row.dataset.suggestedCapital,0)-num(a.row.dataset.suggestedCapital,0);return (actionRank[a.row.dataset.signal]??99)-(actionRank[b.row.dataset.signal]??99)||num(b.row.dataset.portfolioRank)-num(a.row.dataset.portfolioRank)};
  tbody.querySelectorAll('.lane-group-row').forEach(x=>x.remove());
  ['CORE_QUALITY','EXPLOSIVE'].forEach(lane=>{
    const group=rows.filter(x=>(x.row.dataset.lane||'CORE_QUALITY')===lane).sort(cmp);
    if(!group.length)return;
    const temp=document.createElement('tbody');temp.innerHTML=laneHeaderHtml(lane,group.length);tbody.appendChild(temp.firstElementChild);
    group.forEach(x=>{tbody.appendChild(x.row);if(x.detail)tbody.appendChild(x.detail)});
  });
  applyRadarFilters();
}

function closeOtherHeaderMenus(openDetails){$$('.sn-more[open]').forEach(d=>{if(d!==openDetails)d.removeAttribute('open')})}
function bindRadarControls(){
  const ids=['#radarSearch','#radarStockOperator','#radarStockValue','#radarCategoryFilter','#radarOwnedFilter','#radarPriceOperator','#radarPriceValue','#radarSignalOperator','#radarSignalFilter','#radarSystemMin','#radarAiMin','#radarLevelOperator','#radarLevelFilter','#radarDistanceOperator','#radarDistanceValue','#radarTargetMetric','#radarTargetOperator','#radarTargetValue','#radarAnalystOperator','#radarAnalystFilter','#radarAnalystMin','#radarFitOperator','#radarFitFilter','#radarRiskFilter','#radarStockRiskMax','#radarSizeFilter','#radarSizeMetric','#radarSizeOperator','#radarSizeValue'];
  ids.forEach(sel=>{const el=$(sel);if(el)el.addEventListener((el.tagName==='INPUT')?'input':'change',applyRadarFilters)});
  $('#radarSort')?.addEventListener('change',sortRadar);
  $('#clearRadarFilters')?.addEventListener('click',()=>{
    ids.forEach(sel=>{const el=$(sel);if(!el)return;if(el.tagName==='SELECT')el.selectedIndex=0;else el.value=''});
    if($('#radarSort'))$('#radarSort').value='actionable';$$('.sn-more[open]').forEach(d=>d.removeAttribute('open'));sortRadar();
  });
  $$('.sn-more').forEach(d=>d.addEventListener('toggle',()=>{if(d.open)closeOtherHeaderMenus(d)}));
  document.addEventListener('click',e=>{if(!e.target.closest('.sn-more'))$$('.sn-more[open]').forEach(d=>d.removeAttribute('open'))});
  bindRadarRows();applyRadarFilters();
}

function alertCardHtml(a){
  return `<article class="alert-card ${esc(a.severity)}" data-alert-id="${a.id}">
    <div class="alert-main alert-toggle" tabindex="0" role="button" aria-expanded="false">
      <div class="alert-copy"><b>${esc(a.title)}</b><p>${esc(a.message)}</p></div>
      <div class="alert-actions"><span class="action-chip">${esc(a.action)}</span><button class="btn ghost ack-alert" data-id="${a.id}" type="button">Acknowledge</button><button class="icon-btn dismiss-alert" data-id="${a.id}" type="button" title="Dismiss alert" aria-label="Dismiss alert">×</button></div>
    </div>
    <div class="alert-drilldown hidden" data-alert-detail="${a.id}"><div class="alert-loading">Loading evidence…</div></div>
  </article>`
}
function alertDetailHtml(d){
  const a=d.alert||{},x=d.analysis||{},level=x.active_level||{},position=x.position;
  const thesis=x.thesis_invalidated?`<span class="pill red">INVALIDATED</span>`:`<span class="pill green">INTACT / NOT INVALIDATED</span>`;
  const thesisReasons=(x.thesis_reasons||[]).length?`<ul>${x.thesis_reasons.map(r=>`<li>${esc(r)}</li>`).join('')}</ul>`:'<p class="subtle">No explicit thesis/fundamental invalidation signal is recorded.</p>';
  const news=(x.latest_news||[]).length?`<ul>${x.latest_news.map(n=>`<li><b>${esc(n.sentiment||'neutral')}</b> · ${esc(n.title||'')} <small>${esc(n.publisher||'')}</small></li>`).join('')}</ul>`:'<p class="subtle">No recent news items in the evidence pack.</p>';
  const sens=(x.sensitivity||[]).length?`<ul>${x.sensitivity.slice(0,4).map(r=>`<li>${esc(r.condition)} → modeled AI ${esc(r.new_score)}</li>`).join('')}</ul>`:'<p class="subtle">No sensitivity scenarios available.</p>';
  const pos=position?`${esc(position.shares)} shares @ ${esc(position.avg_cost)}${x.pnl!=null?` · P&L ${num(x.pnl).toFixed(1)}%`:''}`:'No current position';
  const plan=x.action_plan?.suggested_shares?`${esc(x.action_plan.suggested_shares)} shares (${esc(x.action_plan.actual_percent)}%) · ${esc(x.action_plan.rationale||'')}`:'No reduction/size plan attached';
  return `<div class="alert-detail-grid">
    <div><span>Price</span><b>${x.price?num(x.price).toFixed(2):'—'}</b></div>
    <div><span>Day move</span><b class="${x.day_change_pct!=null?(num(x.day_change_pct)>=0?'pos':'neg'):''}">${x.day_change_pct!=null?`${num(x.day_change_pct)>=0?'+':''}${num(x.day_change_pct).toFixed(2)}%`:'—'}</b></div>
    <div><span>System conviction</span><b>${x.system_score??'—'}/100</b></div>
    <div><span>AI conviction</span><b>${x.ai_score??'—'}/100</b></div>
    <div><span>Analyst</span><b>${esc(x.analyst_label||'No consensus')} ${x.analyst_score!=null?`· ${esc(x.analyst_score)}/100`:''}</b></div>
    <div><span>Active level</span><b>${esc(level.label||'—')} · ${esc(level.value||'—')}</b></div>
    <div><span>Evidence confidence</span><b>${esc(x.confidence||'—')}</b></div>
  </div>
  <div class="alert-detail-columns">
    <div><h4>Why this alert</h4><p>${esc(x.reason||a.message||'')}</p><h4>Thesis state</h4>${thesis}${thesisReasons}<p><b>Position:</b> ${pos}</p><p><b>Action plan:</b> ${plan}</p></div>
    <div><h4>Latest relevant news</h4>${news}<h4>What would change the score/action</h4>${sens}</div>
  </div>
  <div class="alert-detail-footer"><button class="btn ghost snooze-alert" data-id="${a.id}" data-minutes="60" type="button">Snooze 1h</button><a class="btn secondary" href="/analysis/${encodeURIComponent(a.symbol||'')}">Open full analysis</a></div>`
}
async function toggleAlertDetail(card){
  const body=card.querySelector('.alert-drilldown'),main=card.querySelector('.alert-toggle');if(!body)return;
  const opening=body.classList.contains('hidden');body.classList.toggle('hidden');main?.setAttribute('aria-expanded',opening?'true':'false');
  if(!opening||body.dataset.loaded==='1')return;
  try{const d=await jsonFetch(`/api/alerts/${card.dataset.alertId}`);body.innerHTML=alertDetailHtml(d);body.dataset.loaded='1';bindAlertActions(body)}catch(e){body.innerHTML='<div class="error-box">Could not load alert evidence.</div>'}
}
function bindAlertActions(scope=document){
  scope.querySelectorAll?.('.ack-alert').forEach(b=>b.onclick=async(e)=>{e.stopPropagation();try{await jsonFetch(`/alerts/${b.dataset.id}/ack`,{method:'POST'});b.closest('.alert-card')?.remove();toast('Alert acknowledged')}catch(e){toast('Could not acknowledge alert')}});
  scope.querySelectorAll?.('.dismiss-alert').forEach(b=>b.onclick=async(e)=>{e.stopPropagation();try{await jsonFetch(`/alerts/${b.dataset.id}/dismiss`,{method:'POST'});b.closest('.alert-card')?.remove();toast('Alert dismissed')}catch(e){toast('Could not dismiss alert')}});
  scope.querySelectorAll?.('.snooze-alert').forEach(b=>b.onclick=async(e)=>{e.stopPropagation();const mins=Number(b.dataset.minutes||60);try{await jsonFetch(`/alerts/${b.dataset.id}/snooze`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({minutes:mins})});b.closest('.alert-card')?.remove();toast(`Alert snoozed for ${mins} minutes`)}catch(e){toast('Could not snooze alert')}});
}
function bindAlerts(){
  $$('.alert-card').forEach(card=>{const main=card.querySelector('.alert-toggle');if(main){main.onclick=(e)=>{if(e.target.closest('button,a'))return;toggleAlertDetail(card)};main.onkeydown=(e)=>{if((e.key==='Enter'||e.key===' ')&&!e.target.closest('button,a')){e.preventDefault();toggleAlertDetail(card)}}}});bindAlertActions(document)
}
async function refreshLive(){
  try{
    const d=await jsonFetch('/api/live');
    const mb=$('#marketBadge'); if(mb){mb.textContent=d.market_open?'US MARKET OPEN':'US MARKET CLOSED';mb.className=`pill ${d.market_open?'green':'muted'}`}
    const ls=$('#lastScan');if(ls)ls.textContent=d.last_scan||'not yet';const us=$('#universeSize');if(us)us.textContent=d.universe_size||'loading';if($('#scannerCoreCount'))$('#scannerCoreCount').textContent=d.universe_core_candidates??0;if($('#scannerExplosiveCount'))$('#scannerExplosiveCount').textContent=d.universe_explosive_candidates??0;
    const list=$('#alertsList');if(list){list.innerHTML=d.alerts.length?d.alerts.map(alertCardHtml).join(''):'<div class="empty">No action required right now.</div>';bindAlerts()}if($('#attentionCount'))$('#attentionCount').textContent=d.alerts.length;
    const tb=$('#candidateTable tbody');if(tb){tb.innerHTML=candidateRowsHtml(d.candidates,d.base_currency||'SEK');bindRadarRows();sortRadar()}
    if($('#buyNowCount'))$('#buyNowCount').textContent=d.summary?.buy_now??0;if($('#deployableCash'))$('#deployableCash').textContent=Math.round(num(d.summary?.deployable_cash));if($('#accountRiskScore'))$('#accountRiskScore').textContent=Math.round(num(d.account_risk?.score));if($('#accountRiskBand'))$('#accountRiskBand').textContent=`${d.account_risk?.band||'—'} • target ${d.account_risk?.target_label||''}`;
    if($('#optimizerVisible'))$('#optimizerVisible').textContent=d.optimizer?.visible??0;if($('#optimizerCore'))$('#optimizerCore').textContent=d.optimizer?.core_quality??0;if($('#optimizerExplosive'))$('#optimizerExplosive').textContent=d.optimizer?.explosive??0;if($('#optimizerShortlist'))$('#optimizerShortlist').textContent=d.optimizer?.shortlist??0;if($('#optimizerInvest'))$('#optimizerInvest').textContent=d.optimizer?.invest_now??0;
    const laneDiag=$('#laneDiagnostics');if(laneDiag){const o=d.optimizer||{},parts=[];if(num(o.lane_refresh_pending)>0)parts.push('<span><b>'+esc(o.lane_refresh_pending)+'</b> pre-v2/stale records excluded until refreshed.</span>');if(num(o.explosive)===0){const blockers=(o.explosive_top_blockers||[]).map(x=>esc(x.label)+' ('+esc(x.count)+')').join(', ');parts.push('<span><b>Explosive: 0 qualified.</b> '+esc(o.explosive_evaluated??0)+' fresh lane records evaluated; '+esc(o.explosive_near_misses??0)+' Core-quality near-misses.'+(blockers?' Top blockers: '+blockers+'.':'')+(d.market_open?'':' U.S. market is closed; broad discovery resumes next regular session, while “Run scan now” forces an after-hours refresh.')+'</span>')}laneDiag.innerHTML=parts.join('');laneDiag.classList.toggle('hidden',parts.length===0)}
    const paper=d.paper||{};if($('#paperEquity'))$('#paperEquity').textContent=paper.started?('$'+Math.round(num(paper.equity))):'$10000';if($('#paperReturn'))$('#paperReturn').textContent=paper.started?`${num(paper.return_pct)>=0?'+':''}${num(paper.return_pct).toFixed(2)}%`:'—';if($('#paperAbsoluteReturn'))$('#paperAbsoluteReturn').textContent=paper.started?('$'+(num(paper.absolute_return)>=0?'+':'')+num(paper.absolute_return).toFixed(2)):'—';if($('#paperDailyPnl'))$('#paperDailyPnl').textContent=paper.started?('$'+(num(paper.daily_pnl)>=0?'+':'')+num(paper.daily_pnl).toFixed(2)+' / '+(num(paper.daily_pnl_pct)>=0?'+':'')+num(paper.daily_pnl_pct).toFixed(2)+'%'):'—';if($('#paperBenchmark'))$('#paperBenchmark').textContent=paper.started?`${num(paper.benchmark_return_pct)>=0?'+':''}${num(paper.benchmark_return_pct).toFixed(2)}%`:'—';if($('#paperExcess'))$('#paperExcess').textContent=paper.started?`${num(paper.excess_return_pct)>=0?'+':''}${num(paper.excess_return_pct).toFixed(2)}%`:'—';if($('#paperPositionCount'))$('#paperPositionCount').textContent=paper.position_count??0;if($('#paperCoreCount'))$('#paperCoreCount').textContent=paper.core_position_count??0;if($('#paperExplosiveCount'))$('#paperExplosiveCount').textContent=paper.explosive_position_count??0;const outside=$('#paperOutsideLaneCount'),outsideWrap=$('#paperOutsideLaneWrap');if(outside)outside.textContent=paper.outside_lane_position_count??0;if(outsideWrap)outsideWrap.classList.toggle('hidden',num(paper.outside_lane_position_count)===0);if($('#paperDrawdown'))$('#paperDrawdown').textContent=paper.started?`${num(paper.drawdown_pct).toFixed(2)}%`:'—';;
    const pp=$('#paperPositionsBody');if(pp&&Array.isArray(paper.positions)){pp.innerHTML=paper.positions.length?paper.positions.map(p=>`<tr><td class="ticker"><a href="/analysis/${encodeURIComponent(p.symbol)}">${esc(p.symbol)}</a></td><td><span class="lane-badge lane-${String(p.lane||'OUTSIDE_LANES').toLowerCase().replace(/_/g,'-')}">${esc(p.lane_label||'Outside Current Lanes')}</span>${p.lane==='EXPLOSIVE'?`<small>Day ${esc(p.trading_sessions_held)}/20 • ${esc(p.explosive_sessions_remaining)} sessions left</small>`:p.graduated_from_explosive?'<small>Graduated from Explosive</small>':p.lane==='OUTSIDE_LANES'?'<small>Existing holding only — not eligible for a new Core/Explosive entry.</small>':''}</td><td>${esc(p.shares)}</td><td>${num(p.avg_cost).toFixed(2)}</td><td>$${num(p.price).toFixed(2)}</td><td class="${p.day_change_pct!=null?(num(p.day_change_pct)>=0?'pos':'neg'):''}">${p.day_change_pct!=null?`${num(p.day_change_pct)>=0?'+':''}${num(p.day_change_pct).toFixed(2)}%`:'—'}</td><td>$${Math.round(num(p.value))}</td><td class="${num(p.pnl)>=0?'pos':'neg'}">$${num(p.pnl)>=0?'+':''}${num(p.pnl).toFixed(2)} / ${num(p.pnl_pct)>=0?'+':''}${num(p.pnl_pct).toFixed(2)}%</td><td>${num(p.weight_pct).toFixed(1)}%</td><td>${num(p.entry_rank_score).toFixed(1)}/100</td><td class="reason-cell">${esc(p.reason||'—')}</td></tr>`).join(''):'<tr><td colspan="11" class="empty">No open paper positions yet.</td></tr>'}
  }catch(e){console.debug('live refresh',e)}
}
bindAlerts();
const scan=$('#scanNow');if(scan)scan.onclick=async()=>{scan.disabled=true;scan.textContent='Scanning…';try{const d=await jsonFetch('/api/scan-now',{method:'POST'});toast(`Scan finished: ${d.analyzed||0} deep analyses; ${d.universe_prefiltered||0}/${d.universe_size||0} universe names prefiltered this cycle`);await refreshLive()}catch(e){toast('Scan failed: '+e.message)}finally{scan.disabled=false;scan.textContent='Run scan now'}};

let importPositions=[];
function renderImport(rows){importPositions=rows||[];const wrap=$('#importPreview'),body=$('#importRows');if(!wrap||!body)return;wrap.classList.remove('hidden');body.innerHTML=importPositions.length?importPositions.map((r,i)=>`<tr data-i="${i}"><td><input data-k="symbol" value="${esc(r.symbol)}"></td><td><input data-k="shares" type="number" step="any" value="${esc(r.shares)}"></td><td><input data-k="avg_cost" type="number" step="any" value="${esc(r.avg_cost)}"></td><td><input data-k="account" value="${esc(r.account||'Screenshot')}"></td><td><button class="icon-btn remove-import" type="button">×</button></td></tr>`).join(''):'<tr><td colspan="5" class="empty">Nothing confidently extracted. Add/correct the OCR text or use manual entry.</td></tr>';$$('.remove-import').forEach(b=>b.onclick=()=>{b.closest('tr').remove()})}
function readImportRows(){return $$('#importRows tr[data-i]').map(tr=>{const obj={};tr.querySelectorAll('input[data-k]').forEach(i=>obj[i.dataset.k]=i.dataset.k==='symbol'||i.dataset.k==='account'?i.value:Number(i.value));return obj}).filter(r=>r.symbol&&r.shares>0&&r.avg_cost>0)}
async function parseOcrText(text){const d=await jsonFetch('/api/import/parse-text',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})});renderImport(d.positions);return d.positions}
const parseBtn=$('#parseText');if(parseBtn)parseBtn.onclick=async()=>{try{await parseOcrText($('#ocrText').value);toast('Text parsed — confirm/edit the rows')}catch(e){toast('Could not parse text')}};
const uploadBtn=$('#uploadScreenshot');if(uploadBtn)uploadBtn.onclick=async()=>{const file=$('#positionScreenshot').files[0];const status=$('#ocrStatus');if(!file){toast('Choose a screenshot first');return}uploadBtn.disabled=true;status.textContent='Uploading and extracting…';try{const fd=new FormData();fd.append('file',file);const r=await fetch('/api/import/screenshot',{method:'POST',body:fd});const d=await r.json();if(d.ok){renderImport(d.positions);status.textContent='Server extraction complete. Confirm/edit before saving.'}else if(d.needs_browser_ocr){if(!window.Tesseract)throw new Error('Browser OCR library is still loading. Try again in a few seconds.');status.textContent='Running free browser OCR locally…';const result=await Tesseract.recognize(file,'eng',{logger:m=>{if(m.status==='recognizing text')status.textContent=`Browser OCR ${Math.round((m.progress||0)*100)}%`}});$('#ocrText').value=result.data.text;await parseOcrText(result.data.text);status.textContent='Browser OCR complete. Confirm/edit extracted positions.'}else throw new Error(d.message||'Extraction failed')}catch(e){status.textContent='Extraction needs manual confirmation.';toast(e.message)}finally{uploadBtn.disabled=false}};
const confirmBtn=$('#confirmImport');if(confirmBtn)confirmBtn.onclick=async()=>{const rows=readImportRows();if(!rows.length){toast('No valid rows to save');return}try{const d=await jsonFetch('/api/import/confirm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({positions:rows})});toast(`${d.saved} positions saved`);setTimeout(()=>location.reload(),700)}catch(e){toast('Could not save positions')}};


function initAnalyzeAutocomplete(){
  const input=$('#analyzeSymbol'),box=$('#symbolSuggestions');
  if(!input||!box)return;
  let timer=null,items=[],active=-1,requestSeq=0;
  const hide=()=>{box.classList.add('hidden');box.innerHTML='';items=[];active=-1;input.setAttribute('aria-expanded','false')};
  const setActive=(idx)=>{
    active=idx;
    box.querySelectorAll('.symbol-suggestion').forEach((el,i)=>{
      el.classList.toggle('active',i===active);
      el.setAttribute('aria-selected',i===active?'true':'false');
    });
    box.querySelector('.symbol-suggestion.active')?.scrollIntoView({block:'nearest'});
  };
  const choose=(idx)=>{
    const item=items[idx];
    if(!item)return;
    input.value=item.symbol;
    input.dataset.selectedName=item.name||'';
    hide();
    input.focus();
  };
  const render=(rows)=>{
    items=Array.isArray(rows)?rows:[];
    active=-1;
    if(!items.length){hide();return}
    box.innerHTML=items.map((x,i)=>`<button type="button" class="symbol-suggestion" role="option" aria-selected="false" data-i="${i}"><span><b>${esc(x.symbol)}</b><small>${esc(x.name||x.symbol)}</small></span><em>${esc(x.exchange||'US')}</em></button>`).join('');
    box.classList.remove('hidden');
    input.setAttribute('aria-expanded','true');
    box.querySelectorAll('.symbol-suggestion').forEach(btn=>{
      btn.addEventListener('mousedown',e=>e.preventDefault());
      btn.addEventListener('click',()=>choose(Number(btn.dataset.i)));
    });
  };
  const load=async()=>{
    const q=input.value.trim();
    if(!q){hide();return}
    const seq=++requestSeq;
    try{
      const d=await jsonFetch('/api/symbol-search?q='+encodeURIComponent(q));
      if(seq!==requestSeq)return;
      render(d.results||[]);
    }catch(e){if(seq===requestSeq)hide()}
  };
  input.addEventListener('input',()=>{
    delete input.dataset.selectedName;
    clearTimeout(timer);
    timer=setTimeout(load,160);
  });
  input.addEventListener('keydown',e=>{
    if(box.classList.contains('hidden')||!items.length){
      if(e.key==='ArrowDown'){clearTimeout(timer);load()}
      return;
    }
    if(e.key==='ArrowDown'){e.preventDefault();setActive((active+1)%items.length)}
    else if(e.key==='ArrowUp'){e.preventDefault();setActive((active-1+items.length)%items.length)}
    else if(e.key==='Enter'&&active>=0){e.preventDefault();choose(active)}
    else if(e.key==='Escape'){e.preventDefault();hide()}
  });
  input.addEventListener('blur',()=>setTimeout(hide,120));
}
initAnalyzeAutocomplete();

bindRadarControls();
const poll=Number(document.body.dataset.livePoll||15)*1000;if($('#candidateTable')){setInterval(refreshLive,Math.max(10000,poll));}
