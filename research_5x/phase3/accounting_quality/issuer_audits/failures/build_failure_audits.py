"""Rebuild source-reviewed failure case metrics and lineage from frozen originals.

Manual selections below are analyst-reviewed statement rows. Original inline XBRL
is retained separately; derived metrics use no future financial or outcome data.
"""
from pathlib import Path
from decimal import Decimal
from datetime import date, timedelta
import csv, hashlib, json, re
from lxml import html

ROOT=Path(__file__).resolve().parent
PHASE2=ROOT.parents[3]/"phase2"/"2026-10-11_earnings_acceleration"

def write_csv(name,rows):
    if not rows: return
    keys=list(dict.fromkeys(k for r in rows for k in r))
    with (ROOT/name).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)

def xbrl_facts(sid):
    p=ROOT/'raw'/(sid+'.html')
    raw=re.sub(r'^\s*<\?xml[^>]*\?>','',p.read_text(encoding='utf-8'))
    doc=html.fromstring(raw)
    contexts={}
    for node in doc.iter():
        if isinstance(node.tag,str) and node.tag.lower().endswith(':context'):
            ctxt={"start":None,"end":None,"dimensions":[]}
            for child in node.iter():
                tag=child.tag.lower() if isinstance(child.tag,str) else ''
                if tag.endswith(':startdate'):ctxt['start']=''.join(child.itertext()).strip()
                if tag.endswith(':enddate') or tag.endswith(':instant'):ctxt['end']=''.join(child.itertext()).strip()
                if tag.endswith(':explicitmember') or tag.endswith(':typedmember'):ctxt['dimensions'].append(' '.join(child.itertext()))
            contexts[node.get('id')]=ctxt
    out=[]
    for node in doc.iter():
        if not isinstance(node.tag,str) or not node.tag.lower().endswith(':nonfraction'):continue
        ctxt=contexts.get(node.get('contextref'),{})
        txt=''.join(node.itertext()).strip().replace(',','').replace(' ','')
        try:
            val=Decimal(txt)*Decimal(10)**int(node.get('scale','0'))
            if node.get('sign')=='-':val=-val
        except Exception:continue
        out.append(dict(source_id=sid,name=node.get('name'),context_id=node.get('contextref'),start=ctxt.get('start'),end=ctxt.get('end'),dimensions=json.dumps(ctxt.get('dimensions',[])),unitref=node.get('unitref'),value=str(val),decimals=node.get('decimals'),fact_id=node.get('id'),original_text=''.join(node.itertext()).strip()))
    return out

# Every number is USD millions. Reporting scopes are explicit and cannot be
# pooled automatically. Blank cash values below mean unavailable, not zero.
CASES=[
 dict(ticker='DXCM',signal_date='2024-04-30',period_start='2024-01-01',period_end='2024-03-31',release='DXCM_Q1_2024',release_date='2024-04-25',filing='DXCM_Q1_2024_10Q',scope='consolidated',revenue=921.0,prior_year_revenue=741.5,operating_income=101.1,prior_year_operating_income=47.2,gross_profit=561.9,prior_year_gross_profit=462.6,net_income=146.4,cfo=209.2,gross_capex=56.9,sbc=39.0,adjusted_operating_income=140.2,adjusted_net_income=128.2,working_capital_cash_change=19.0,notes='Tax benefit and57.3m non-GAAP tax bridge inflate GAAP NI; positive CFO/FCF persists. Gross margin declines despite OI expansion. CFO and capex are Q1 standalone.'),
 dict(ticker='DECK',signal_date='2024-09-30',period_start='2024-04-01',period_end='2024-06-30',release='DECK_Q1_FY2025',release_date='2024-07-25',filing='DECK_Q1_FY2025_10Q',scope='consolidated',revenue=825.347,prior_year_revenue=675.791,operating_income=132.807,prior_year_operating_income=70.736,gross_profit=470.0,prior_year_gross_profit=346.424,net_income=115.625,cfo=112.650,gross_capex=22.521,sbc=8.346,adjusted_operating_income=None,adjusted_net_income=None,working_capital_cash_change=-25.805,notes='Q1 CFO declined10.1% YoY as seasonal inventory and payable changes offset profit. Positive FCF and modest SBC remain. Separate debt-free liquidity/brand mix from future share returns.'),
 dict(ticker='DECK',signal_date='2024-10-31',period_start='2024-07-01',period_end='2024-09-30',release='DECK_Q2_FY2025',release_date='2024-10-24',filing=None,scope='consolidated',revenue=1311.320,prior_year_revenue=1091.907,operating_income=305.086,prior_year_operating_income=224.617,gross_profit=733.272,prior_year_gross_profit=583.019,net_income=242.321,cfo=None,gross_capex=None,sbc=None,adjusted_operating_income=None,adjusted_net_income=None,working_capital_cash_change=None,notes='Q2 release eligible but Q2 10-Q filedOct31 is after cutoffOct30. Latest comparable Q2 cash conversion unavailable; do not divide Q1 CFO by Q2 NI. Q2 EPS incorporates6-for-1 split; Q1 original EPS does not.'),
 dict(ticker='FSLR',signal_date='2024-05-31',period_start='2024-01-01',period_end='2024-03-31',release='FSLR_Q1_2024',release_date='2024-05-01',filing='FSLR_Q1_2024_10Q',scope='consolidated',revenue=794.108,prior_year_revenue=548.286,operating_income=243.141,prior_year_operating_income=18.002,gross_profit=346.003,prior_year_gross_profit=112.051,net_income=236.616,cfo=267.723,gross_capex=413.456,sbc=6.791,adjusted_operating_income=None,adjusted_net_income=None,working_capital_cash_change=-35.306,notes='480m collection of prior-year45X credits aids CFO; current45X production credit reduces cost of sales. FCF negative due capacity expansion; these credits are policy-linked operating support rather than automatically nonrecurring fraud/gains. Divestiture gain1.115m.'),
 dict(ticker='TTD',signal_date='2025-07-31',period_start='2025-01-01',period_end='2025-03-31',release='TTD_Q1_2025',release_date='2025-05-08',filing='TTD_Q1_2025_10Q',scope='consolidated',revenue=616.021,prior_year_revenue=491.253,operating_income=54.452,prior_year_operating_income=28.657,gross_profit=None,prior_year_gross_profit=None,net_income=50.678,cfo=291.433,gross_capex=59.113,sbc=128.253,adjusted_operating_income=None,adjusted_net_income=164.993,working_capital_cash_change=82.939,notes='SBC expense128.253m exceeds GAAP NI;24m CEO award. Non-GAAP NI bridge adds SBC less13.938m tax adjustment. Strong CFO also includes ad receivable/payable timing. Capitalized software2.660m separate from PPE capex. Earlier Q4 release already admitted missing own expectations, not historical consensus.'),
 dict(ticker='APP',signal_date='2025-09-30',period_start='2025-04-01',period_end='2025-06-30',release='APP_Q2_2025',release_date='2025-08-06',filing='APP_Q2_2025_10Q',scope='continuing_income__consolidated_cash',revenue=1258.754,prior_year_revenue=711.015,operating_income=957.682,prior_year_operating_income=384.422,gross_profit=1103.678,prior_year_gross_profit=589.256,net_income=771.856,cfo=772.226,gross_capex=0.042,sbc=34.552,adjusted_operating_income=None,adjusted_net_income=None,working_capital_cash_change=None,net_income_consolidated=819.531,revenue_discontinued=315.783,operating_income_discontinued=41.909,divestiture_gain_pretax=106.229,notes='Apps divestedJune30. Revenue/OI/NI shown continuing; CFO/FCF consolidated. Continuing CFO/NI intentionally missing. Consolidated CFO/NI is available separately with NI819.531; revenue bridge adds Apps315.783. CFO is not contaminated by divestiture proceeds:424.702m is investingYTD. Continuing SBC2.745% not consolidated SBC.'),
 dict(ticker='DASH',signal_date='2025-09-30',period_start='2025-04-01',period_end='2025-06-30',release='DASH_Q2_2025',release_date='2025-08-06',filing='DASH_Q2_2025_10Q',scope='consolidated_including_noncontrolling_interest',revenue=3284.0,prior_year_revenue=2630.0,operating_income=163.0,prior_year_operating_income=-201.0,gross_profit=1608.0,prior_year_gross_profit=1195.0,net_income=284.0,net_income_common=285.0,cfo=504.0,gross_capex=66.0,sbc=282.0,adjusted_operating_income=None,adjusted_net_income=None,working_capital_cash_change=None,capitalized_software_cash=83.0,issuer_fcf=355.0,derivative_gain_pretax=69.0,notes='Quarter CFO504 is explicitly released; capex66=H1140−Q174; SBC282=H1517−Q1235. Both original filings eligible. CompanyFCF deducts software83 as well as PPE66; protocolFCF438.69m unrealized deal-contingent FX gain below OI; positive operating profit163 is separate. Debt issuance is financing, not CFO.'),
]

ANNUAL=[
 ('DXCM','2023-01-01','2023-12-31','2024-02-08','DXCM_FY2023_release','DXCM_FY2023_10K',3622.3,597.7,541.5,748.5,236.6,150.8,1034.5,216.9,256.3),
 ('DECK','2023-04-01','2024-03-31','2024-05-23','DECK_FY2024_release','DECK_FY2024_10K',4287.763,927.514,759.563,1033.184,89.365,37.288,959.758,144.262,127.545),
 ('FSLR','2023-01-01','2023-12-31','2024-02-27','FSLR_FY2023_release','FSLR_FY2023_10K',3318.602,857.266,830.777,602.260,1386.775,34.219,1158.553,397.784,349.239),
 ('TTD','2024-01-01','2024-12-31','2025-02-12','TTD_FY2024_release','TTD_FY2024_10K',2444.831,427.167,393.076,739.456,98.238,494.699,741.012,195.309,182.229),
 ('APP','2024-01-01','2024-12-31','2025-02-12','APP_FY2024_release','APP_FY2024_10K',4709.248,1873.459,1579.776,2099.011,4.776,376.455,1372.779,607.980,599.204),
 ('DASH','2024-01-01','2024-12-31','2025-02-11','DASH_FY2024_release','DASH_FY2024_10K',10722.0,-38.0,117.0,2132.0,104.0,1099.0,2873.0,117.0,139.0),
]

def build():
    manifest=json.loads((ROOT/'download_manifest.json').read_text())
    sources={}
    for r in manifest:
        if r.get('local_path') and r['source_id'] not in sources:sources[r['source_id']]=r
    indices={r['source_id'].removesuffix('_index'):r for r in json.loads((ROOT/'filing_indices.json').read_text())}
    release_dates={c['release']:c['release_date'] for c in CASES}
    release_dates.update({r[4]:r[3] for r in ANNUAL})
    checks=[]
    for sid,r in sources.items():
        checks.append(dict(check='snapshot_sha256',source_id=sid,passed=hashlib.sha256((ROOT/r['local_path']).read_bytes()).hexdigest()==r['sha256']))
        idx=indices.get(sid.removesuffix('_index'),{})
        r.update(accession=idx.get('accession'),filing_date=idx.get('filing_date'),accepted_eastern=idx.get('accepted_eastern'),index_url=idx.get('url'),snapshot_type='original_filing_index' if sid.endswith('_index') else ('original_accession_document' if '_10' in sid else 'dated_issuer_release'))
        r['publication_date']=release_dates.get(sid)
        r['conservative_available_date']=(date.fromisoformat(release_dates[sid])+timedelta(days=1)).isoformat() if sid in release_dates else idx.get('filing_date')
        r['availability_note']='Release exact timestamp unverified; next-session convention, all selected release+1 dates are trading sessions' if sid in release_dates else 'Original SEC index Eastern acceptance; current submissions feed timestamps not used'
    write_csv('source_index.csv',list(sources.values()))
    facts=[]
    for sid in sources:
        if ('_10Q' in sid or '_10K' in sid) and not sid.endswith('_index'):facts.extend(xbrl_facts(sid))
    write_csv('original_inline_xbrl_facts.csv',facts)
    # Selected cases remain explicit analyst-reviewed selections; extraction has
    # not been automated by outcome label. All labels joined only here.
    panel=list(csv.DictReader((PHASE2/'panel'/'qualified_failures.csv').open()))
    rows=[];lineage=[]
    for c in CASES:
        c=dict(c);cutoff=(date.fromisoformat(c['signal_date'])-timedelta(days=1)).isoformat()
        r=dict(c,cutoff=cutoff,cash_period='quarter',cash_scope='consolidated',quality_certification='case_source_reviewed_not_broad_gate')
        hit=[x for x in panel if x['ticker']==c['ticker'] and x['date']==c['signal_date']]
        assert len(hit)==1,(c['ticker'],c['signal_date'])
        r.update(forward_252d=float(hit[0]['forward_252d']),path_dd=float(hit[0]['path_dd']),return_label_basis='frozen_phase2_price_only')
        income_scope_matches_cash=not c['scope'].startswith('continuing_income')
        cfo=c['cfo'];capex=c['gross_capex'];ni=c['net_income'];rev=c['revenue']
        r['analyst_fcf']=cfo-capex if cfo is not None and capex is not None else None
        for key,a,b in [('cfo_to_ni',cfo,ni),('fcf_to_ni',r['analyst_fcf'],ni),('cfo_to_revenue',cfo,rev),('fcf_to_revenue',r['analyst_fcf'],rev),('capex_to_revenue',capex,rev)]:
            r[key]=a/b if income_scope_matches_cash and a is not None and b>0 else None
        r['sbc_to_revenue']=c['sbc']/rev if c['sbc'] is not None else None
        r['gaap_operating_margin']=c['operating_income']/rev
        r['gaap_margin_change_pp']=100*(r['gaap_operating_margin']-c['prior_year_operating_income']/c['prior_year_revenue'])
        r['revenue_yoy']=rev/c['prior_year_revenue']-1
        r['gross_margin_change_pp']=100*(c['gross_profit']/rev-c['prior_year_gross_profit']/c['prior_year_revenue']) if c['gross_profit'] is not None else None
        if c['ticker']=='APP':
            r.update(revenue_consolidated_bridge=rev+c['revenue_discontinued'],operating_income_consolidated_bridge=c['operating_income']+c['operating_income_discontinued'],cfo_to_consolidated_ni=cfo/c['net_income_consolidated'],cfo_to_consolidated_revenue=cfo/(rev+c['revenue_discontinued']))
        r['missing_cash_reason']='Q2 filing published after previous-day cutoff; Q2 release omits cash statement' if cfo is None else ('Cash covers Apps through divestiture; continuing-only cash conversion unavailable' if not income_scope_matches_cash else '')
        rows.append(r)
        for metric in ['revenue','operating_income','gross_profit','net_income','cfo','gross_capex','sbc','adjusted_operating_income','adjusted_net_income','working_capital_cash_change']:
            sid=c['release'] if metric in ['revenue','operating_income','gross_profit','net_income','adjusted_operating_income','adjusted_net_income'] else c['filing']
            if c['ticker']=='APP' and metric in ['cfo','gross_capex']:sid=c['release']
            if c['ticker']=='DASH' and metric in ['cfo','gross_capex','sbc']:sid=c['release'] if metric=='cfo' else c['filing']+';DASH_Q1_2025_10Q'
            scope=c['scope']
            if c['ticker']=='APP':scope='consolidated' if metric in ['cfo','gross_capex','working_capital_cash_change'] else 'continuing_operations'
            reason=''
            if c.get(metric) is None:
                reason='Particular adjusted measure not disclosed; adjusted EBITDA is not substituted' if metric.startswith('adjusted_') else ('Comparable subtotal not reported' if metric=='gross_profit' else ('Original Q2 filing after cutoff; cash not released' if c['ticker']=='DECK' else 'Standalone-quarter working-capital sum not reconstructed'))
            record=dict(ticker=c['ticker'],signal_date=c['signal_date'],metric=metric,value_musd=c.get(metric),period_start=c['period_start'],period_end=c['period_end'],source_id=sid,scope=scope,evidence_label='fact_source_reported' if c.get(metric) is not None else 'missing_required_source',missing_reason=reason,formula='',locator='Original release statements of operations / original filing cash-flow statement; see issuer audit')
            if metric=='working_capital_cash_change' and c.get(metric) is not None:record.update(evidence_label='derived_calculation',formula='Sum explicitly reported cash-flow changes in operating assets and liabilities; includes lease/tax lines')
            if c['ticker']=='APP' and metric=='gross_profit':record.update(evidence_label='derived_calculation',formula='Continuing revenue1258.754 minus continuing cost of revenue155.076; prior711.015 minus121.759')
            if c['ticker']=='DASH' and metric in ['gross_capex','sbc']:record.update(evidence_label='derived_calculation',formula='H1 minus Q1; same fiscal start and90-day period increment')
            lineage.append(record)
        checks.append(dict(check='release_cutoff',source_id=c['release'],signal_date=c['signal_date'],passed=c['release_date']<c['signal_date']))
        if c['filing']:
            idx=indices[c['filing']]
            checks.append(dict(check='original_filing_cutoff',source_id=c['filing'],signal_date=c['signal_date'],passed=idx['filing_date']<=cutoff and idx['accepted_eastern'][:10]<=cutoff))
        if c['ticker']=='DASH':
            idx=indices['DASH_Q1_2025_10Q']
            checks.append(dict(check='derived_quarter_prior_filing_cutoff',source_id='DASH_Q1_2025_10Q',signal_date=c['signal_date'],passed=idx['filing_date']<=cutoff and idx['accepted_eastern'][:10]<=cutoff))
    write_csv('case_metrics.csv',rows);write_csv('metric_lineage.csv',lineage)
    (ROOT/'case_metrics.json').write_text(json.dumps(rows,indent=2)+"\n")
    attribution=[]
    for r in rows:
        attribution.append(dict(ticker=r['ticker'],signal_date=r['signal_date'],entry_observable_accounting_evidence=r['notes'],entry_revenue_yoy=r['revenue_yoy'],entry_operating_margin_change_pp=r['gaap_margin_change_pp'],entry_protocol_fcf_musd=r['analyst_fcf'],later_forward_252d_label=r['forward_252d'],later_maximum_stock_path_drawdown_label=r['path_dd'],later_data_used_as_predictor=False,causal_failure_attribution='Unresolved: accounting observations and later price losses alone do not establish causation',expectations_and_valuation='No source-certified historical consensus or valuation expectation decomposition',statistical_status='Selected failure case, not independent matched evidence',factor_conclusion='Positive operating profit/CFO/FCF is not sufficient protection; incremental value untested',source_ids=r['release']+(';' + r['filing'] if r['filing'] else '')))
    write_csv('failure_attribution.csv',attribution)
    metric_names=['revenue','operating_income','gross_profit','net_income','cfo','gross_capex','sbc','adjusted_operating_income','adjusted_net_income','working_capital_cash_change']
    coverage=dict(case_observations=len(rows),unique_issuers=len(set(r['ticker'] for r in rows)),matched_or_representative_sample=False,core_metric_coverage={m:dict(available=sum(r.get(m) is not None for r in rows),missing=sum(r.get(m) is None for r in rows),total=len(rows)) for m in metric_names},matching_period_scope_cfo_to_ni=sum(r['cfo_to_ni'] is not None for r in rows),cash_scope_bridge_only_issuers=['APP'],latest_cash_after_cutoff_issuers=['DECK2024-10-31'],original_q4_release_issuers=[r[0] for r in ANNUAL],source_snapshots=len(sources),original_filing_indices=len(indices),release_exact_clock_time_certification=False,broad_phase3_gate_status='blocked',missingness_is_zero=False,unresolved_fields=['Complete recurring earnings adjustments across issuers','Quarterly working-capital sums for APP and DASH','Continuing-only APP CFO and cash PPE','DECK Q2 cash and SBC before cutoff','TTD comparable GAAP gross-profit subtotal','Historical consensus and valuation expectations','Historical sector/industry and company-size matched cohort certification','Complete first-inflection/consecutive-report histories'])
    (ROOT/'coverage.json').write_text(json.dumps(coverage,indent=2)+"\n")
    # Income-row reconciliations compare the original release to original annual
    # filing. Separate Q4 versus FY; no silent10-K-minus-YTD estimate.
    annual=[]
    for ticker,start,end,release_date,rsid,fsid,rev,oi,ni,cfo,capex,sbc,qrev,qoi,qni in ANNUAL:
        for metric,v in [('revenue',rev),('operating_income',oi),('net_income',ni),('cfo',cfo),('gross_capex',capex),('sbc_expense',sbc)]:
            annual.append(dict(ticker=ticker,period_start=start,period_end=end,period_type='full_year',metric=metric,value_musd=v,release_source_id=rsid,filing_source_id=fsid,release_date=release_date,filing_date=indices[fsid]['filing_date'],status='original_filing_source_reviewed',notes='SBC expense may differ from CFO add-back; retain original accounting scope'))
        for metric,v in [('revenue',qrev),('operating_income',qoi),('net_income',qni)]:
            annual.append(dict(ticker=ticker,period_start=str(int(end[:4]))+'-'+('01-01' if ticker=='DECK' else '10-01'),period_end=end,period_type='Q4_original_release',metric=metric,value_musd=v,release_source_id=rsid,filing_source_id=None,release_date=release_date,status='original_Q4_release_source_reviewed',notes='Direct originalQ4 disclosure; not annual-minus-YTD derivative'))
        # Exact manual annual selections must occur among original nondimensional
        # inline XBRL values for matching period and statement role.
        aliases={'revenue':['RevenueFromContractWithCustomerExcludingAssessedTax','RevenueFromContractWithCustomerIncludingAssessedTax','SalesRevenueNet','Revenues'],'operating_income':['OperatingIncomeLoss'],'net_income':['NetIncomeLoss','ProfitLoss'],'cfo':['NetCashProvidedByUsedInOperatingActivities'],'gross_capex':['PaymentsToAcquirePropertyPlantAndEquipment'],'sbc_expense':['ShareBasedCompensation','AllocatedShareBasedCompensationExpense']}
        selected={'revenue':rev,'operating_income':oi,'net_income':ni,'cfo':cfo,'gross_capex':capex,'sbc_expense':sbc}
        for metric,v in selected.items():
            candidates=[f for f in facts if f['source_id']==fsid and f['start']==start and f['end']==end and f['dimensions']=='[]' and f['name'].split(':')[-1] in aliases[metric]]
            matched=any(abs(float(f['value'])/1e6-v)<1e-7 for f in candidates)
            checks.append(dict(check='annual_inline_xbrl_selected_value',source_id=fsid,metric=metric,passed=matched,candidate_values_musd=json.dumps(sorted(set(float(f['value'])/1e6 for f in candidates))),notes='A failed check remains an open taxonomy/scope exception; does not fabricate a replacement.'))
    write_csv('annual_Q4_reconciliation.csv',annual)
    # Permanent negative cutoff test, to protect the known silentcash-lag hazard.
    q2idx=indices['DECK_Q2_FY2025_10Q_INELIGIBLE']
    checks.append(dict(check='exclude_DECK_Q2_after_cutoff',source_id='DECK_Q2_FY2025_10Q_INELIGIBLE',passed=q2idx['filing_date']>'2024-10-30' and next(x for x in rows if x['ticker']=='DECK' and x['signal_date']=='2024-10-31')['cfo'] is None))
    checks.append(dict(check='APP_scope_guard',source_id='APP_Q2_2025',passed=next(x for x in rows if x['ticker']=='APP')['cfo_to_ni'] is None))
    checks.append(dict(check='DASH_software_FCF_bridge',source_id='DASH_Q2_2025',passed=504-66-83==355))
    (ROOT/'validation_checks.json').write_text(json.dumps({'checks':checks,'passed':sum(c['passed'] for c in checks),'failed':sum(not c['passed'] for c in checks),'interpretation':'Arithmetic,original snapshot hashes,cutoff guards and selectedannual XBRL tie-outs. Case evidence does not certify broader matched-cohort validity.'},indent=2)+"\n")
    print(json.dumps({'cases':len(rows),'sources':len(sources),'inline_facts':len(facts),'checks_passed':sum(c['passed'] for c in checks),'open_checks':[c for c in checks if not c['passed']]}))

if __name__=='__main__':build()
