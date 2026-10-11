"""Build a bounded, original-source matched-peer audit. No backtests or fitting.

Run collect_sources.py (optional network), extract_original_facts.py, then this
file with Python 3.9+ and lxml. All output is owned by this case-audit directory.
Curated facts preserve report vintage, currency, scope and duration. Missing
values remain missing. Source timestamps come from original SEC index pages,
not from an unconditional interpretation of current submissions API metadata.
"""
import bisect, csv, datetime as dt, gzip, hashlib, json, math, pathlib, re
from zoneinfo import ZoneInfo
from lxml import html

ROOT = pathlib.Path(__file__).resolve().parent
PHASE3 = ROOT.parents[2]
PANEL = PHASE3 / 'accounting_quality' / 'mature_cohorts.csv'
RAW_API = PHASE3 / 'accounting_quality' / 'raw'
UTC = dt.timezone.utc
ET = ZoneInfo('America/New_York')
CORE = ['revenue', 'gross_profit', 'operating_income', 'net_income', 'cfo',
        'gross_capex', 'sbc_cashflow', 'adjusted_operating_income',
        'adjusted_net_income_parent', 'company_fcf', 'interest_expense']
PAIRS = [('2024-01-31','CCL','RCL'), ('2024-02-29','NOW','SNPS'),
         ('2024-04-30','MU','NVDA'), ('2024-10-31','WDC','ZBRA'),
         ('2024-11-29','WDC','ZBRA'), ('2025-06-30','PLTR','MU'),
         ('2025-09-30','PLTR','MU')]
CORROBORATING = {'NVDA_Q4_release':'NVDA_Q4_SEC_release',
                 'ZBRA_Q3_release':'ZBRA_Q3_SEC_release',
                 'SNPS_Q1_release':'SNPS_Q1_SEC_release'}
MISSING_REASONS = {
 ('NVDA','gross_capex'): 'Cash purchase line combines PPE and intangible assets; no pure PPE split certified.',
 ('RCL','cfo'): 'Latest release cash is nine months; original Q2 same-vintage subtraction bridge not obtained.',
 ('RCL','gross_capex'): 'Exact quarter capex requires original Q2 bridge; nine-month capex is separate.',
 ('RCL','sbc_cashflow'): 'Exact quarter SBC requires original Q2 bridge; nine-month SBC is separate.',
 ('CCL','gross_profit'): 'Gross profit not normalized from differing cruise cost/depreciation conventions.',
 ('CCL','sbc_cashflow'): 'No same-window SBC certified from this source; annual filing SBC retained only in its annual filed row.',
 ('ZBRA','interest_expense'): 'Reported interest expense is net of income; no gross expense split certified.',
 ('ZBRA','adjusted_operating_income'): 'Adjusted consolidated OI not directly reported; implied GP minus Opex retained separately.',
 ('SNPS','adjusted_operating_income'): 'Adjusted segment OI excludes consolidated managed costs; not a comparable consolidated measure.',
}

def write_csv(name, rows):
    keys = list(dict.fromkeys(k for row in rows for k in row))
    with (ROOT/name).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)

def accession(url):
    m = re.search(r'/edgar/data/\d+/(\d{18})/',url)
    if not m:return None
    s=m.group(1);return s[:10]+'-'+s[10:12]+'-'+s[12:]

def safe_ratio(a,b,positive=False):
    if a is None or b is None or b==0 or (positive and b<=0):return None
    return a/b

def main():
    evidence=json.loads((ROOT/'curated_evidence.json').read_text())
    reports=evidence['reports']+evidence['supplemental_windows']
    manifest=json.loads((ROOT/'download_manifest.json').read_text())
    downloads={r['source_id']:r for r in manifest if r['status']=='downloaded'}
    checks=[]
    def check(name,condition,detail=''):
        checks.append(dict(check=name,passed=bool(condition),detail=detail))

    # Raw source hashes and original index acceptance clocks.
    index_meta={}
    for sid,r in downloads.items():
        raw=gzip.open(ROOT/r['local_path'],'rb').read()
        check('hash_'+sid,hashlib.sha256(raw).hexdigest()==r['raw_sha256'])
        check('bytes_'+sid,len(raw)==r['byte_count'])
        if not sid.endswith('_index'):continue
        tree=html.fromstring(raw);metadata={}
        for e in tree.xpath('//div[@class="infoHead"]'):
            n=e.getnext()
            metadata[e.text_content().strip()]=n.text_content().strip() if n is not None else ''
        index_meta[accession(r['url'])]=metadata

    api={}
    for ticker in sorted({r['ticker'] for r in downloads.values()}):
        p=RAW_API/(ticker+'_submissions.json.gz')
        if not p.exists():continue
        s=json.loads(gzip.open(p,'rt').read())['filings']['recent']
        for i,acc in enumerate(s['accessionNumber']):
            api[acc]={k:s[k][i] for k in ['filingDate','acceptanceDateTime','form','reportDate']}

    lineage=[]
    for sid,r in downloads.items():
        acc=accession(r['url'])
        # IR release aligns to the byte-preserved SEC exhibit for acceptance clock.
        aligned=CORROBORATING.get(sid)
        if not acc and aligned:acc=accession(downloads[aligned]['url'])
        idx=index_meta.get(acc,{})
        clock=idx.get('Accepted','')
        accepted_utc=dt.datetime.fromisoformat(clock).replace(tzinfo=ET).astimezone(UTC).isoformat() if clock else ''
        api_clock=api.get(acc,{}).get('acceptanceDateTime','')
        difference=None
        if api_clock and accepted_utc:
            difference=(dt.datetime.fromisoformat(api_clock.replace('Z','+00:00'))-dt.datetime.fromisoformat(accepted_utc)).total_seconds()
        lineage.append(dict(source_id=sid,ticker=r['ticker'],source_url=r['url'],
          source_kind=('original_SEC_index' if sid.endswith('_index') else 'original_SEC_document' if accession(r['url']) else 'original_IR_release'),
          publication_date=r['publication_date'],accession=acc,SEC_filing_date=idx.get('Filing Date',''),
          original_accepted_Eastern=clock,original_accepted_UTC=accepted_utc,
          API_acceptanceDateTime=api_clock,API_minus_original_seconds=difference,
          timestamp_conflict=bool(difference),IR_SEC_corroborating_id=aligned,
          retrieved_at_UTC=r['retrieved_at_utc'],raw_sha256=r['raw_sha256'],
          original_byte_count=r['byte_count'],raw_local_path=r['local_path']))
    write_csv('source_lineage.csv',lineage)
    lm={r['source_id']:r for r in lineage}
    metrics=[];missing=[];numeric_lineage=[]
    for r in reports:
        sources=list(dict.fromkeys(r['sources']+[CORROBORATING[s] for s in r['sources'] if s in CORROBORATING]))
        check('sources_'+r['id'],all(s in downloads for s in sources))
        d={k:v for k,v in r.items() if not isinstance(v,(dict,list))}
        d.update(currency='USD',units='millions',sources='|'.join(sources),
          net_income_denominator_scope='consolidated including NCI',
          capex_definition='gross PPE cash purchase only',
          evidence_status='original_source_case_only',
          accountant_scope='combined Carnival Corporation and plc' if r['ticker']=='CCL' else 'original consolidated reporting scope')
        R=r.get('revenue');C=r.get('cfo');NI=r.get('net_income');cap=r.get('gross_capex');S=r.get('sbc_cashflow');OI=r.get('operating_income')
        fcf=C-cap if C is not None and cap is not None else None
        d.update(analyst_fcf=fcf,cfo_to_ni=safe_ratio(C,NI,True),fcf_to_ni=safe_ratio(fcf,NI,True),
          earnings_nonpositive=(NI is not None and NI<=0),cfo_to_revenue=safe_ratio(C,R),
          fcf_to_revenue=safe_ratio(fcf,R),capex_to_revenue=safe_ratio(cap,R),sbc_to_revenue=safe_ratio(S,R),
          accrual_to_revenue=safe_ratio(NI-C if NI is not None and C is not None else None,R),
          operating_margin=safe_ratio(OI,R),gross_margin=safe_ratio(r.get('gross_profit'),R),
          revenue_yoy=safe_ratio(R,r.get('prior_revenue'))-1 if r.get('prior_revenue') else None,
          interest_to_oi=safe_ratio(r.get('interest_expense'),OI,True),
          interest_net_to_oi=safe_ratio(r.get('interest_expense_net'),OI,True),
          adjusted_oi_gap_to_revenue=safe_ratio(r.get('adjusted_operating_income')-OI if r.get('adjusted_operating_income') is not None else None,R),
          company_fcf_minus_analyst_fcf=(r['company_fcf']-fcf if r.get('company_fcf') is not None and fcf is not None else None),
          combined_asset_spend_fcf_diagnostic=(C-r['combined_ppe_intangible_spend'] if C is not None and r.get('combined_ppe_intangible_spend') is not None else None))
        if r.get('prior_gross_profit') is not None:
            d['gross_margin_change_pp']=100*(d['gross_margin']-r['prior_gross_profit']/r['prior_revenue'])
        if r.get('prior_operating_income') is not None:
            d['operating_margin_change_pp']=100*(d['operating_margin']-r['prior_operating_income']/r['prior_revenue'])
        for field in CORE:
            value=r.get(field)
            reason='' if value is not None else MISSING_REASONS.get((r['ticker'],field),'Not certified from retrieved original sources for this window; missing, not zero.')
            missing.append(dict(report_id=r['id'],ticker=r['ticker'],window=r['window'],metric=field,
              available=value is not None,missing_reason=reason))
        for field,value in r.items():
            if not isinstance(value,(int,float)) or isinstance(value,bool):continue
            cash_fields=('cfo','gross_capex','sbc_cashflow','combined_ppe_intangible_spend','financing_asset_principal')
            loc='Original consolidated statement of cash flows; explicit Q4 release table or disclosed same-fiscal-year YTD subtraction' if field in cash_fields else 'Original consolidated income statement and release non-GAAP reconciliation'
            if field.startswith('prior_'):loc='Original release prior-year comparative column, same reporting scope'
            numeric_lineage.append(dict(report_id=r['id'],ticker=r['ticker'],metric=field,value=value,
               units='USD_millions',source_ids='|'.join(sources),original_table_locator=loc,
               window=r['window'],period_start=r['period_start'],period_end=r['period_end'],
               actual_fiscal_end=r.get('actual_fiscal_end',''),manual_source_review=True,
               net_income_scope='parent attributable' if field in ('net_income_parent','adjusted_net_income_parent') else 'consolidated' if field=='net_income' else '',
               derivation='same-fiscal-start YTD difference' if 'cash_derivation' in r and field in ('cfo','gross_capex','sbc_cashflow') else 'original reported or original table arithmetic'))
        if 'cash_derivation' in r:
            q=r['cash_derivation']
            for target,prefix in [('cfo','cfo'),('gross_capex','capex'),('sbc_cashflow','sbc')]:
                check('same_vintage_difference_'+r['id']+'_'+target,abs(r[target]-(q[prefix+'_ytd']-q[prefix+'_prior_ytd']))<1e-8)
            days=(dt.date.fromisoformat(r['period_end'])-dt.date.fromisoformat(q['prior_end'])).days
            check('subtraction_duration_'+r['id'],60<=days<=125)
        metrics.append(d)
    write_csv('normalized_metrics.csv',metrics)
    write_csv('metric_lineage.csv',numeric_lineage)
    write_csv('missing_data_coverage.csv',missing)
    byid={r['id']:r for r in metrics}
    with PANEL.open() as f:panel={(r['date'],r['ticker']):r for r in csv.DictReader(f)}
    # Existing SPY price dates supply an actual session calendar only. No prices
    # or outcomes are consulted to set source availability.
    spy_path=PHASE3.parent/'data'/'spy.json'
    spy=json.loads(spy_path.read_text())
    sessions=sorted(r['date'] for r in spy['rows'])
    cases=[];cases_map={}
    for r in evidence['reports']:
        for date in r['signal_dates']:
            p=panel[(date,r['ticker'])];cutoff=(dt.date.fromisoformat(date)-dt.timedelta(days=1)).isoformat()
            m=byid[r['id']];ss=m['sources'].split('|')
            filing_dates=[lm[s]['SEC_filing_date'] for s in ss if lm[s]['SEC_filing_date']]
            acceptance_dates=[lm[s]['original_accepted_Eastern'][:10] for s in ss if lm[s]['original_accepted_Eastern']]
            eligible=all(x<=cutoff for x in filing_dates+acceptance_dates)
            # Conservative next session even when the original exhibit provides
            # an exact morning timestamp. No actual execution is simulated.
            next_session=sessions[bisect.bisect_right(sessions,r['release'])]
            release_eligible=next_session<=cutoff
            check('filing_cutoff_'+date+'_'+r['ticker'],eligible)
            check('conservative_release_cutoff_'+date+'_'+r['ticker'],release_eligible)
            case=dict(signal_date=date,ticker=r['ticker'],signal_cutoff=cutoff,report_id=r['id'],
              release_date=r['release'],all_original_sources_cutoff_eligible=eligible,
              conservative_release_next_session=next_session,release_next_session_cutoff_eligible=release_eligible,
              forward_252_session_price_return=float(p['forward_252d']),stock_path_drawdown=float(p['path_dd']),
              outcome=p['outcome'],first_observed_company_signal=p['first_observed_company_signal'],
              earliest_mature_company_signal=p['earliest_mature_company_signal'],
              current_sector_proxy=p['sector'],marketcap_proxy=float(p['marketcap_proxy']),
              size_bucket=p['size_bucket'],r63=float(p['r63']),market_regime=p['regime'],
              vendor_action_in_label_horizon=p['vendor_action_in_label_horizon'],
              cfo_to_ni=m['cfo_to_ni'],analyst_fcf=m['analyst_fcf'],sbc_to_revenue=m['sbc_to_revenue'],
              evidence_status='retrospective sparse case; no causal or predictive certification')
            cases.append(case);cases_map[(date,r['ticker'])]=case
    write_csv('signal_case_matrix.csv',cases)
    pair_rows=[]
    for date,left,right in PAIRS:
        a=panel[(date,left)];b=panel[(date,right)]
        cap_a=float(a['marketcap_proxy']);cap_b=float(b['marketcap_proxy'])
        momentum=abs(float(a['r63'])-float(b['r63']));ratio=max(cap_a,cap_b)/min(cap_a,cap_b)
        strict=a['sector']==b['sector'] and a['size_bucket']==b['size_bucket'] and momentum<=.20
        relaxed=a['sector']==b['sector'] and ratio<=2 and momentum<=.30
        pair_rows.append(dict(signal_date=date,left_ticker=left,right_ticker=right,
          left_forward_252_session_price_return=float(a['forward_252d']),right_forward_252_session_price_return=float(b['forward_252d']),
          left_stock_path_drawdown=float(a['path_dd']),right_stock_path_drawdown=float(b['path_dd']),
          left_outcome=a['outcome'],right_outcome=b['outcome'],marketcap_proxy_ratio=ratio,
          absolute_r63_difference=momentum,strict_proxy_eligible=strict,relaxed_proxy_eligible=relaxed,
          same_date=True,same_current_sector_proxy=a['sector']==b['sector'],historical_industry_control=False,
          left_report_id=cases_map.get((date,left),{}).get('report_id','parent_mandatory_issuer_audit'),
          right_report_id=cases_map.get((date,right),{}).get('report_id','parent_mandatory_issuer_audit'),
          pair_status='descriptive; same-quartile match does not imply comparable continuous size',
          repeated_pair=left+right in ('WDCZBRA','PLTRMU')))
    write_csv('matched_pair_diagnostics.csv',pair_rows)
    diagnostics = {
      ('MU','NVDA'): ('NVDA has positive original quarter cash; MU accounting adjustments are audited in parent mandatory packet.',
        '17.27x cap proxy ratio; GPU versus memory demand; cash quality and expectations not isolated.',
        'Resolve comparable size/industry and dated expectation information before attribution.'),
      ('WDC','ZBRA'): ('ZBRA quarter CFO294, gross capex17, FCF277, CFO/NI2.146 precede severe loss.',
        'High positive cash is not sufficient; devices versus HDD/Flash scope, WDC corporate action and overlapping windows unresolved.',
        'Preserve severe cash-positive failures; obtain recurring WDC scope bridge and dated industry/expectation evidence.'),
      ('PLTR','MU'): ('PLTR positive recurring GAAP OI/CFO/protocol FCF; adjusted OI/FCF exclude SBC/payroll taxes.',
        'Software versus memory cycle; cap ratio exceeds2x; no dated consensus or valuation causal diagnosis; repeated issuer windows.',
        'Do not infer overvaluation as cause without PIT expectations; certify more software and memory failures.'),
      ('NOW','SNPS'): ('Positive NOW CFO vs negative SNPS CFO accompanies positive vs negative subsequent return at one matched date.',
        'Seasonal subscription billings; NOW tax benefit; SNPS14week scope and investment gain; one observation cannot identify transferability.',
        'Replicate with matched seasonal windows and original cash/earnings scope outside this reused sample.'),
      ('CCL','RCL'): ('CCL negative Q4 NI and positive CFO precede moderate winner; RCL quarterly CFO missing.',
        'Different release periods, deposit-funded cash, dual-listed CCL size and unresolved RCL quarter bridge.',
        'Obtain RCLQ2/CCL9month original vintages; reconcile CCL annual CFO difference and economic market cap.')
    }
    failure_rows=[]
    for row in pair_rows:
        observation,alternatives,next_work=diagnostics[(row['left_ticker'],row['right_ticker'])]
        failure_rows.append(dict(signal_date=row['signal_date'],left_ticker=row['left_ticker'],right_ticker=row['right_ticker'],
          left_outcome=row['left_outcome'],right_outcome=row['right_outcome'],
          left_forward_252_session_price_return=row['left_forward_252_session_price_return'],
          right_forward_252_session_price_return=row['right_forward_252_session_price_return'],
          pre_entry_accounting_observation=observation,unresolved_alternative_explanations=alternatives,
          causal_attribution='NOT_ESTABLISHED',classification='retrospective case evidence; incremental factor effect untested',
          next_evidence_needed=next_work,repeated_company_windows=row['repeated_pair']))
    write_csv('failure_attribution.csv',failure_rows)
    # Meaningful invariants, not model-fitting tests.
    check('distinct_companies',len({r['ticker'] for r in evidence['reports']})==7)
    check('reports_windows',len(reports)==13)
    check('case_signals',len(cases)==9)
    check('pair_dates',len(pair_rows)==7)
    check('missing_is_not_zero',byid['NVDA_FY24Q4']['gross_capex'] is None and byid['RCL_2023Q3']['cfo'] is None)
    check('negative_ni_ratio_excluded',byid['CCL_2023Q4_original']['cfo_to_ni'] is None)
    check('CCL_original_FCF_definition',abs(byid['CCL_FY23_original']['analyst_fcf']-989)<1e-9)
    check('CCL_later_annual_vintage_retained',abs(byid['CCL_FY23_filed']['cfo']-byid['CCL_FY23_original']['cfo']-8)<1e-9)
    check('CCL_issuer_financing_addback',abs(byid['CCL_FY23_original']['company_fcf']-byid['CCL_FY23_original']['analyst_fcf']-1157)<1e-9)
    check('PLTR_Q1_payroll_cash_addback',abs(byid['PLTR_2025Q1']['company_fcf_minus_analyst_fcf']-66.298)<1e-8)
    check('PLTR_Q2_payroll_cash_addback',abs(byid['PLTR_2025Q2']['company_fcf_minus_analyst_fcf']-37.152)<1e-8)
    check('NOW_annual_company_FCF_acquisition_addback',abs(byid['NOW_FY23_annual']['company_fcf_minus_analyst_fcf']-24)<1e-9)
    check('NI_scope_not_parent_substitution',all(byid[k]['net_income']!=byid[k]['net_income_parent'] for k in ['PLTR_2025Q1','PLTR_2025Q2','SNPS_FY24Q1','RCL_2023YTD9']))
    check('API_clock_conflict_preserved',any(r['timestamp_conflict'] for r in lineage))
    check('original_failure_attempts_retained',any(r['status']=='failed' for r in manifest))
    counts={metric:sum(x['available'] for x in missing if x['metric']==metric and next(r for r in reports if r['id']==x['report_id'])['window']=='quarter') for metric in CORE}
    status=dict(status='PASS_BOUNDED_CASE_INTEGRITY; BLOCKED_BROAD_ACCOUNTING_GATE',
      checks_passed=sum(r['passed'] for r in checks),checks_failed=sum(not r['passed'] for r in checks),
      successful_original_sources=len(downloads),download_attempts=len(manifest),
      preserved_failure_attempts=sum(r['status']=='failed' for r in manifest),
      source_clock_conflicts=len({r['accession'] for r in lineage if r['timestamp_conflict']}),
      audited_distinct_companies=7,unique_latest_quarter_reports=8,signal_cases=9,pair_dates=7,
      latest_quarter_metric_coverage_count=counts,coverage_denominator=8,
      signal_case_outcome_counts={k:sum(r['outcome']==k for r in cases) for k in sorted({r['outcome'] for r in cases})},
      selected_case_first_observed_signal_count=sum(r['first_observed_company_signal']=='True' for r in cases),
      selected_case_earliest_mature_signal_count=sum(r['earliest_mature_company_signal']=='True' for r in cases),
      incremental_factor_test='UNTESTED: broad original-source accounting coverage gate failed',
      independent_validation='BLOCKED: reused 2024-2026 development sample and incomplete historical universe',
      session_calendar_source=spy['source_url'],session_calendar_raw_sha256=hashlib.sha256(spy_path.read_bytes()).hexdigest(),
      checks=checks)
    (ROOT/'verification_results.json').write_text(json.dumps(status,indent=2)+'\n')
    print(json.dumps({k:v for k,v in status.items() if k!='checks'},indent=2))
    if status['checks_failed']:raise SystemExit('Source audit verification failed')

if __name__=='__main__':main()
