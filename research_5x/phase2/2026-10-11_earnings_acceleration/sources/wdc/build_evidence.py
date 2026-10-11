"""Rebuild WDC source fact/timing/definition ledgers from bounded manual primary extraction.

No network requests; no changes to prior research inputs or trading implementation.
All dollar facts are USD millions except diluted EPS (USD/share).
"""
from pathlib import Path
import csv, json, hashlib
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SESSIONS = sorted(r['date'] for r in json.loads((ROOT/'data/spy.json').read_text())['rows'])
def next_session(day):
    return next(x for x in SESSIONS if x > day)

# Original released vintages. Later comparatives are separate revision records below.
# quarter, end, release, R, priorR, OI, priorOI, consolidated NI, prior NI,
# GAAP EPS, adjusted EPS, adjusted OI, CFO, company FCF,
# HDD R, prior HDD R, HDD segment gross margin, prior margin,
# next guide revenue low/high, adjusted EPS low/high, source URL.
RAW = [
 ['FY2023Q2','2022-12-30','2023-01-31',3107,4833,-321,727,-446,564,-1.40,-.42,-119,35,-240,1450,2213,20.7,30.6,2600,2800,-1.70,-1.40,'https://investor.wdc.com/news-releases/news-release-details/western-digital-reports-fiscal-second-quarter-2023-financial'],
 ['FY2023Q3','2023-03-31','2023-05-08',2803,4381,-472,324,-572,25,-1.82,-1.37,-304,-381,-527,1496,2138,24.3,27.7,2400,2600,-2.20,-1.90,'https://www.sec.gov/Archives/edgar/data/106040/000010604023000014/ex991-pressreleaseq323.htm'],
 ['FY2023Q4','2023-06-30','2023-07-31',2672,4528,-650,562,-715,301,-2.27,-1.98,-478,-68,-219,1295,2128,20.7,28.2,2550,2750,-2.10,-1.80,'https://investor.wdc.com/node/24981'],
 ['FY2024Q1','2023-09-29','2023-10-30',2750,3736,-596,158,-685,27,-2.17,-1.76,-443,-626,-544,1194,2014,22.9,28.5,2850,3050,-1.35,-1.05,'https://investor.wdc.com/news-releases/news-release-details/western-digital-reports-fiscal-first-quarter-2024-financial'],
 ['FY2024Q2','2023-12-29','2024-01-25',3032,3107,-210,-321,-268,-446,-.87,-.69,-91,-92,-176,1367,1450,24.8,20.7,3200,3400,-.10,.20,'https://investor.wdc.com/news-releases/news-release-details/western-digital-reports-fiscal-second-quarter-2024-financial'],
 ['FY2024Q3','2024-03-29','2024-04-25',3457,2803,273,-472,135,-571,.34,.63,380,58,91,1752,1496,31.1,24.3,3600,3800,.90,1.20,'https://investor.wdc.com/node/25676'],
 ['FY2024Q4','2024-06-28','2024-07-31',3764,2672,507,-650,330,-709,.88,1.44,666,366,282,2003,1295,36.1,20.7,4000,4200,1.55,1.85,'https://investor.wdc.com/news-releases/news-release-details/western-digital-reports-fiscal-fourth-quarter-and-fiscal-year-1'],
 ['FY2025Q1','2024-09-27','2024-10-24',4095,2750,742,-596,493,-685,1.35,1.78,884,34,-14,2211,1194,38.1,22.9,4200,4400,1.75,2.05,'https://investor.wdc.com/node/26101'],
 ['FY2025Q2','2024-12-27','2025-01-29',4285,3032,852,-210,594,-287,1.63,1.77,864,403,335,2409,1367,38.6,24.8,3750,3950,.90,1.20,'https://investor.wdc.com/node/26351'],
 ['FY2025Q3','2025-03-28','2025-04-30',2294,1752,760,94,520,135,2.11,1.36,596,508,436,None,None,None,None,2300,2600,1.25,1.65,'https://investor.wdc.com/node/26681'],
]
FILINGS = [
 ['0000106040-23-000010','2023-02-03','2023-02-02 18:36:21','10-Q','wdc-20221230.htm'],
 ['0000106040-23-000017','2023-05-10','2023-05-10 13:41:02','10-Q','wdc-20230331.htm'],
 ['0000106040-23-000024','2023-08-22','2023-08-21 19:53:42','10-K','wdc-20230630.htm'],
 ['0000106040-23-000034','2023-11-07','2023-11-06 19:44:44','10-Q','wdc-20230929.htm'],
 ['0000106040-24-000014','2024-02-12','2024-02-12 16:29:29','10-Q','wdc-20231229.htm'],
 ['0000106040-24-000022','2024-04-30','2024-04-29 18:55:39','10-Q','wdc-20240329.htm'],
 ['0000106040-24-000031','2024-08-20','2024-08-19 17:39:43','10-K','wdc-20240628.htm'],
 ['0000106040-24-000040','2024-10-31','2024-10-30 19:49:57','10-Q','wdc-20240927.htm'],
 ['0000106040-25-000008','2025-01-31','2025-01-30 19:53:33','10-Q','wdc-20241227.htm'],
 ['0000106040-25-000026','2025-05-02','2025-05-02 16:34:25','10-Q','wdc-20250328.htm'],
]
NOTES = [
 'Cloud inventory digestion and weak flash pricing. HDD utilization charges included. Negative earnings growth rates are not meaningful.',
 'HDD volumes partly offset weak flash; underutilization charges. No sustained recovery proven.',
 'Flash inventory normalization and slowing price declines were management claims; combined revenue and HDD revenue still declined.',
 'Combined recovery first appeared sequentially; HDD revenue still fell. No positive YoY demand confirmation.',
 'Nearline shipments/pricing improved; original preliminary NI/EPS later revised. Positive HDD gross-margin YoY improvement with revenue still negative.',
 'Combined revenue growth and GAAP operating profit turned positive. Revisions to Flash Ventures comparatives were known in this release.',
 'HDD revenue and segment gross margin accelerated. Original GAAP figures precede the subsequent litigation charge in the annual filing.',
 'Nearline and enterprise SSD growth. Release disclosed unresolved accounting assessment of a $316m verdict; actual quarterly filing kept OI/NI/EPS unchanged.',
 'Combined revenue grew while flash pricing weakened. $113m divestiture gain is below operating income. Guidance remains combined HDD+Flash.',
 'HDD continuing income statement; consolidated total NI/CFO/FCF still include discontinued Flash. Litigation reversal, tax benefit and Sandisk mark loss distort GAAP profit.',
]
FIELDS = ['fiscal_quarter','period_end','release_date','revenue_usdm','prior_year_revenue_usdm','operating_income_gaap_usdm','prior_year_operating_income_gaap_usdm','net_income_consolidated_usdm','prior_year_net_income_consolidated_usdm','eps_gaap_diluted_usd','eps_non_gaap_diluted_usd','operating_income_non_gaap_usdm','operating_cash_flow_consolidated_usdm','fcf_company_defined_usdm','hdd_segment_revenue_usdm','prior_year_hdd_segment_revenue_usdm','hdd_segment_gross_margin_non_gaap_pct','prior_year_hdd_segment_gross_margin_non_gaap_pct','next_quarter_revenue_guide_low_usdm','next_quarter_revenue_guide_high_usdm','next_quarter_eps_guide_low_non_gaap_usd','next_quarter_eps_guide_high_non_gaap_usd','release_url']
QUARTERS=[]
for i,(raw,filing) in enumerate(zip(RAW,FILINGS)):
    q=dict(zip(FIELDS,raw)); accession,filed,accepted,form,doc=filing
    at = datetime.strptime(accepted,'%Y-%m-%d %H:%M:%S').replace(tzinfo=ZoneInfo('America/New_York'))
    base=f'https://www.sec.gov/Archives/edgar/data/106040/{accession.replace("-","")}/'
    q.update(source_id=f'WDC-RELEASE-{q["fiscal_quarter"]}',security='WDC',currency='USD',retrieved_client_date='2026-10-11',release_vintage='original_preliminary_unaudited',release_time_utc=None,
             conservative_release_eligible_session=next_session(q['release_date']),filing_accession=accession,filing_date=filed,filing_form=form,
             filing_acceptance_edgar_eastern=accepted,filing_accepted_at_utc=at.astimezone(timezone.utc).isoformat(),
             conservative_filing_eligible_session=next_session(max(filed,at.date().isoformat())),filing_index_url=base+accession+'-index.htm',filing_document_url=base+doc,
             filing_review_scope='index_metadata_verified; numbers primarily original release',economic_scope='HDD+Flash_combined' if i<9 else 'HDD_continuing_income_statement',
             guidance_evidence_label='issuer_management_claim',actual_evidence_label='fact_source_reported',adjusted_evidence_label='management_adjusted',confidence='high',qa_notes=NOTES[i])
    q['revenue_yoy_pct']=100*(q['revenue_usdm']/q['prior_year_revenue_usdm']-1)
    q['operating_margin_gaap_pct']=100*q['operating_income_gaap_usdm']/q['revenue_usdm']
    q['prior_year_operating_margin_gaap_pct']=100*q['prior_year_operating_income_gaap_usdm']/q['prior_year_revenue_usdm']
    q['operating_margin_yoy_change_pp']=q['operating_margin_gaap_pct']-q['prior_year_operating_margin_gaap_pct']
    q['operating_margin_non_gaap_pct']=100*q['operating_income_non_gaap_usdm']/q['revenue_usdm']
    q['hdd_segment_revenue_yoy_pct']=100*(q['hdd_segment_revenue_usdm']/q['prior_year_hdd_segment_revenue_usdm']-1) if q['hdd_segment_revenue_usdm'] is not None else None
    q['net_income_continuing_usdm']=772 if i==9 else q['net_income_consolidated_usdm']
    q['prior_year_net_income_continuing_usdm']=-8 if i==9 else q['prior_year_net_income_consolidated_usdm']
    q['eps_scope']='continuing_operations' if i==9 else 'combined_company'
    q['cash_flow_scope']='consolidated_including_Sandisk_through_2025-02-21' if i==9 else 'combined_company'
    q['guidance_scope']=q['economic_scope']
    q['ni_yoy_robust_change_usdm']=q['net_income_continuing_usdm']-q['prior_year_net_income_continuing_usdm']
    q['ni_yoy_pct']=100*(q['net_income_continuing_usdm']/q['prior_year_net_income_continuing_usdm']-1) if q['prior_year_net_income_continuing_usdm']>0 else None
    QUARTERS.append(q)

REVISIONS = [
 dict(period='FY2024Q2',source_id='WDC-SEC-FY2024Q2',availability_date='2024-02-12',eligible_session='2024-02-13',url=QUARTERS[4]['filing_document_url'],reason='Flash Ventures equity-method corrections',original_net_income_consolidated_usdm=-268,revised_net_income_consolidated_usdm=-287,original_eps_gaap_diluted=-.87,revised_eps_gaap_diluted=-.93,original_net_income_common_usdm=-282,revised_net_income_common_usdm=-301,original_comparator_FY2023Q2_ni=-446,revised_comparator_FY2023Q2_ni=-451,original_comparator_FY2023Q2_eps=-1.40,revised_comparator_FY2023Q2_eps=-1.42),
 dict(period='FY2024Q4',source_id='WDC-SEC-FY2024FY',availability_date='2024-08-20',eligible_session='2024-08-21',url=QUARTERS[6]['filing_document_url'],reason='291m litigation charge after preliminary release',original_operating_income_usdm=507,revised_operating_income_usdm=216,revised_oi_method='FY operating loss -317m minus released nine-month operating loss -533m; subsequent Oct24 release independently reports 216m',original_net_income_consolidated_usdm=330,revised_net_income_consolidated_usdm=39,revised_ni_method='Oct24 subsequent release comparative, also annual-minus-nine-month derivation',original_eps_gaap_diluted=.88,revised_eps_gaap_diluted=.08,eps_value_first_verified_here='2024-10-24',eps_comparative_url=QUARTERS[7]['release_url']),
 dict(period='FY2025Q3',source_id='WDC-RECAST-APR2025',availability_date='2025-04-30',eligible_session='2025-05-01',url=QUARTERS[9]['release_url'],reason='first standalone continuing-operation recast verified in this extraction; February investor-day materials could contain earlier pro forma data',current_revenue_hdd_usdm=2294,prior_quarter_revenue_hdd_usdm=2409,prior_year_revenue_hdd_usdm=1752,current_oi_hdd_gaap_usdm=760,prior_quarter_oi_hdd_gaap_usdm=560,prior_year_oi_hdd_gaap_usdm=94,current_oi_hdd_non_gaap_usdm=596,prior_quarter_oi_hdd_non_gaap_usdm=591,prior_year_oi_hdd_non_gaap_usdm=153,prior_quarter_ni_continuing_usdm=466,prior_year_ni_continuing_usdm=-8),
]
QUALITY=[
 dict(id='WDC-QA-SCOPE',severity='high',finding='Do not splice original 4285m combined December revenue into the continuing HDD March2294m series. Prior HDD segment revenue2409m was already observable, but standalone OI560m became verified here with the April recast. Gross-margin segment series is not standalone operating margin.'),
 dict(id='WDC-QA-NI',severity='high',finding='March2025 cached NetIncome520m vs135m measures consolidated total income, including discontinued Flash. Continuing income772m vs-8m is a different series; post-spin revenue/OI with consolidated NI mixes scopes.'),
 dict(id='WDC-QA-EPS',severity='high',finding='March2025 GAAP OI760m includes201m litigation credit; excluding only that credit gives559m or24.37% margin. Management-adjusted OI596m or25.98% margin also removes other items. GAAP tax benefit698m and retained-Sandisk mark loss606m make GAAP EPS2.11 an unsuitable recurring-profit proxy.'),
 dict(id='WDC-QA-CASH',severity='high',finding='March2025 CFO508m/FCF436m are consolidated and retain Flash until separation. They cannot confirm HDD-only cash conversion. Company-defined FCF includes net activity with Flash Ventures, unlike plain CFO-minus-capex.'),
 dict(id='WDC-QA-VINTAGES',severity='high',finding='Initial release and formal filing figures can differ. Preserve release timestamp/vintage and switch to revised values only after acceptance or conservative filing availability.'),
 dict(id='WDC-QA-CONSENSUS',severity='high',finding='No historical analyst EPS consensus vintage was obtained. Guidance comparisons are company-guidance comparisons; surprise relative to dated sell-side consensus is missing_required_source.'),
 dict(id='WDC-QA-TRANSCRIPT',severity='medium',finding='Primary historical call transcript not retrieved. Narrative evidence comes from official releases and filings; investor-day numerical guidance remains unverified here.'),
]
GUIDE_CHECKS=[]
for i in range(1,len(QUARTERS)):
    now,prev=QUARTERS[i],QUARTERS[i-1]
    comparable=now['economic_scope']==prev['guidance_scope']
    GUIDE_CHECKS.append(dict(result_quarter=now['fiscal_quarter'],actual_source_id=now['source_id'],guide_source_id=prev['source_id'],comparable_economic_scope=comparable,
                            revenue_minus_prior_guide_midpoint_usdm=now['revenue_usdm']-(prev['next_quarter_revenue_guide_low_usdm']+prev['next_quarter_revenue_guide_high_usdm'])/2 if comparable else None,
                            eps_minus_prior_guide_midpoint_usd=now['eps_non_gaap_diluted_usd']-(prev['next_quarter_eps_guide_low_non_gaap_usd']+prev['next_quarter_eps_guide_high_non_gaap_usd'])/2 if comparable else None,
                            evidence_label='derived_calculation',comparison='issuer guidance, not analyst consensus',qa_note='no comparison across separation' if not comparable else 'original guidance vs originally reported adjusted actual; later revisions must be separate'))

extra_sources=[
 dict(source_id='WDC-INVESTOR-DAY-ANNOUNCEMENT',url='https://investor.wdc.com/news-releases/news-release-details/western-digital-host-investor-day-2025-new-york-city',publication_date='2025-01-30',evidence_label='issuer_management_claim',fact='Investor Day announced for February12 2025,9:30am–1:30pmEastern.'),
 dict(source_id='WDC-INVESTOR-DAY-STRATEGY',url='https://www.westerndigital.com/company/newsroom/press-releases/2025/2025-02-12-western-digital-unveiled-go-forward-strategy-at-investor-day-2025',publication_date='2025-02-12',conservative_available_date='2025-02-13',evidence_label='issuer_management_claim',facts={'projected_hdd_exabyte_cagr_2024_2028_pct':23,'forecast_is_internal_estimate':True,'HAMR_testing_hyperscale_customers':2,'supporting_materials_promised_by':'2025-02-13'}),
 dict(source_id='WDC-INVESTOR-DAY-DECK',url='https://investor.wdc.com/static-files/e16a6f3b-49af-4eea-90a2-6220aa24ebc3',event_url='https://investor.wdc.com/events/event-details/western-digital-investor-day-2025',event_date='2025-02-12',numerical_content_verified=False,status='web reports57pages but returns no text/image payload; shell download403; numerical guidance not used'),
 dict(source_id='WDC-2024Q3-SEC-DEMAND',url=QUARTERS[5]['filing_document_url'],available_date='2024-04-30',evidence_label='fact_source_reported',facts={'hdd_exabytes_yoy_pct':25,'hdd_asp_per_gigabyte_yoy_pct':-6,'hdd_underutilization_charges_usdm':16,'prior_hdd_underutilization_charges_usdm':62},interpretation='Per-unit nearline pricing improvement in the release can coexist with lower average price/gigabyte because capacity mix changed.'),
]
payload=dict(schema_version='wdc_earnings_vintage_evidence_v1',created_at_utc=datetime.now(timezone.utc).isoformat(),client_asof_date='2026-10-11',historical_decision_cutoff='2025-06-30',security='WDC',cik='0000106040',scope='Ten quarter releases January2023–April2025; evidence available before June30 2025 selection',owning_workflow='earnings-deep-dive',decision_impact='Tests whether operating acceleration was observable earlier while preventing spin-off and revised-financial leakage',readiness_effect='needs_targeted_fixes',artifact_role='embedded_support_artifact',hidden_unless_requested=True,
             timing_policy='Original release dates verified; exact release timestamp unavailable; eligibility first cached SPY session strictly after date. Filing acceptanceEDGAR shownEastern convertedAmerica/New_York toUTC; conservative eligible first session strictly after later of filing date or local accepteddate.',
             formulas={'revenue_yoy_pct':'100*(revenue/prior_same_scope_revenue-1)','operating_margin_pct':'100*operating_income/revenue','operating_margin_yoy_change_pp':'currentGAAPoperatingmargin-priorGAAPoperatingmargin','hdd_segment_revenue_yoy_pct':'100*(HDDsegmentrevenue/priorHDDsegmentrevenue-1)','earnings_improvement':'absolute same-scope NI change; percent growth only if priorNI>0','guide_delta':'original adjustedactual minus original management-guide midpoint; no scope-spliced comparisons'},
             quarters=QUARTERS,revision_and_scope_bridge=REVISIONS,guide_vs_actual=GUIDE_CHECKS,qa_flags=QUALITY,additional_sources=extra_sources,
             failures=[{'source':'Investor DayPDF','default_shell':'DNSresolution failure','escalated_shell':'HTTP403','web':'PDF57pages detected but no readable content or screenshot image returned; alternateconnector screenshot error','result':'event/narrative only; financialguidance not substituted from thirdparty'}],
             source_posture='Original issuer releases plus SEC indices all10periods; targeted SEC documents read for April2024 demand, February2024 revisions, August2024 litigation, October2024final actual and May2025scope; not global XBRL dimensional audit.')
(HERE/'source_evidence.json').write_text(json.dumps(payload,indent=2)+'\n')
with (HERE/'quarter_timeline.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(QUARTERS[0]));w.writeheader();w.writerows(QUARTERS)
with (HERE/'guidance_vs_actual.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(GUIDE_CHECKS[0]));w.writeheader();w.writerows(GUIDE_CHECKS)
checks=[]
def check(name,passed):
    checks.append(dict(check=name,passed=bool(passed))); assert passed,name
check('ten unique original quarter releases',len(QUARTERS)==10 and len({q['fiscal_quarter'] for q in QUARTERS})==10)
check('all releases before historical cutoff',all(q['release_date']<'2025-06-30' for q in QUARTERS))
check('cash flow scope explicitly different after separation',QUARTERS[-1]['cash_flow_scope']!=QUARTERS[-1]['economic_scope'])
check('guidance cross-separation comparison blocked',GUIDE_CHECKS[-1]['revenue_minus_prior_guide_midpoint_usdm'] is None)
check('no denominator-negative earnings percentage generated',all(q['ni_yoy_pct'] is None for q in QUARTERS if q['prior_year_net_income_continuing_usdm']<=0))
check('HDD segment plusFlash total Q2FY2025',2409+1876==QUARTERS[8]['revenue_usdm'])
check('Q3FY2025 consolidatedNI scope reconciliation',772-252==520)
check('Q3FY2025 adjustedOI reconciliation',760+8-172==596)
check('Q4FY2024 laterOI annual-minus-nine-month',-317-(-533)==216)
check('SEC UTC dates are not mistaken for local publication dates',QUARTERS[3]['filing_accepted_at_utc']=='2023-11-07T00:44:44+00:00' and QUARTERS[3]['filing_acceptance_edgar_eastern'].startswith('2023-11-06'))
(HERE/'validation_checks.json').write_text(json.dumps(dict(checks=checks,all_passed=True),indent=2)+'\n')
print(json.dumps(dict(quarters=len(QUARTERS),guide_checks=len(GUIDE_CHECKS),qa_flags=len(QUALITY),validation_checks=len(checks),output_dir=str(HERE))))
