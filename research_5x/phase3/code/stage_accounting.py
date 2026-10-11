"""Accession-specific SEC staging; deliberately not predictive certification.

No outcome value participates in filing/fact selection. Current API provenance
and original-document certification are separate statuses.
"""
from pathlib import Path
from zoneinfo import ZoneInfo
from datetime import datetime,date
import gzip,json,hashlib
import numpy as np
import pandas as pd
OUT=Path(__file__).resolve().parents[1]
ROOT=OUT.parents[1]
RAW=OUT/'accounting_quality/raw'
SOURCE_REPO=ROOT/'research_repository' if (ROOT/'research_repository/backtests/staged').exists() else ROOT
ET=ZoneInfo('America/New_York')
TAGS={
 'revenue':['RevenueFromContractWithCustomerExcludingAssessedTax','Revenues','SalesRevenueNet','RevenueFromContractWithCustomerIncludingAssessedTax','SalesRevenueGoodsNet'],
 'net_income':['ProfitLoss','NetIncomeLoss'],
 'operating_income':['OperatingIncomeLoss'],
 'gross_profit':['GrossProfit'],
 'cfo':['NetCashProvidedByUsedInOperatingActivities'],
 'gross_ppe_capex':['PaymentsToAcquirePropertyPlantAndEquipment'],
 'sbc':['ShareBasedCompensation','AllocatedShareBasedCompensationExpense'],
 'interest_expense':['InterestExpenseNonOperating','InterestExpenseNonoperating','InterestExpense'],
 'inventory':['InventoryNet'], 'receivables':['AccountsReceivableNetCurrent'],
 'current_assets':['AssetsCurrent'], 'current_liabilities':['LiabilitiesCurrent'],
 'long_term_debt_noncurrent':['LongTermDebtNoncurrent'],
 'debt_current':['LongTermDebtCurrent','DebtCurrent'],
 'diluted_shares':['WeightedAverageNumberOfDilutedSharesOutstanding']}

def submissions(ticker):
    p=RAW/f'{ticker}_submissions.json.gz'
    if not p.exists():return {}
    j=json.load(gzip.open(p));blocks=[j['filings']['recent']]
    for old in j['filings'].get('files',[]):
        p=RAW/f'{ticker}_{old["name"]}.gz'
        if p.exists():blocks.append(json.load(gzip.open(p)))
    result={}
    for q in blocks:
        for i,a in enumerate(q['accessionNumber']):
            x={k:v[i] for k,v in q.items() if isinstance(v,list) and len(v)==len(q['accessionNumber'])}
            if x['form'] not in ['10-Q','10-K']:continue
            s=x.get('acceptanceDateTime','')
            try:
                t=datetime.fromisoformat(s.replace('Z','+00:00'))
                x['api_acceptance_eastern_date']=t.astimezone(ET).date().isoformat() if t.tzinfo else ''
            except ValueError:x['api_acceptance_eastern_date']=''
            result[a]=x
    return result

def eligible(x,cutoff):
    return bool(x.get('api_acceptance_eastern_date')) and x['filingDate']<=cutoff and x['api_acceptance_eastern_date']<=cutoff

def choose(facts,filing,concept,start=None):
    """Exact accession/end; never choose a later comparative or a frame."""
    for tag in TAGS[concept]:
        unit='shares' if concept=='diluted_shares' else 'USD'
        a=[dict(x,tag=tag,unit=unit) for x in facts.get(tag,{}).get('units',{}).get(unit,[]) if x.get('accn')==filing['accessionNumber'] and x.get('end')==filing['reportDate'] and (start is None or x.get('start')==start)]
        if a:
            # Conflicting values within one accession/date/start stay unavailable.
            a=sorted(a,key=lambda x:x.get('start',''),reverse=True)
            same=[x for x in a if x.get('start')==a[0].get('start')]
            if len({x['val'] for x in same})!=1:return None
            return same[0]
    return None

def prior_ytd(facts,files,concept,current,cutoff):
    candidates=[]
    for tag in [current['tag']]:
        for x in facts.get(tag,{}).get('units',{}).get('USD',[]):
            if x.get('start')!=current.get('start') or x.get('accn') not in files:continue
            end=x.get('end',''); gap=(date.fromisoformat(current['end'])-date.fromisoformat(end)).days
            f=files[x['accn']]
            if 60<=gap<=125 and eligible(f,cutoff):candidates.append(dict(x,tag=tag,unit='USD',filing=f))
        if candidates:break
    if not candidates:return None
    candidates.sort(key=lambda x:(x['end'],x['filing']['filingDate'],x['filing'].get('acceptanceDateTime','')),reverse=True)
    c=candidates[0]
    same=[x for x in candidates if x['end']==c['end'] and x['accn']==c['accn']]
    if len({x['val'] for x in same})!=1:return None
    return c

def main():
    a=pd.read_csv(OUT/'accounting_quality/mature_cohorts.csv')
    frozen=json.load(open(OUT/'frozen_inputs/frozen_acceptance_map.json'))
    rows=[];lineage=[];accessions={}; timestamp_conflicts=[]
    for ticker,g in a.groupby('ticker'):
        path=RAW/f'{ticker}_companyfacts.json.gz'
        if not path.exists():
            rows.extend({'date':x.date,'ticker':ticker,'extraction_status':'missing_SEC_snapshot'} for _,x in g.iterrows());continue
        j=json.load(gzip.open(path));facts=j['facts']['us-gaap'];files=submissions(ticker)
        cache_times={}
        for accession,timestamp in frozen[ticker]:
            cache_times.setdefault(accession,set()).add(timestamp)
        for acc,f in files.items():
            times=cache_times.get(acc,set())
            for t in times:
                try:delta=(datetime.fromisoformat(f['acceptanceDateTime'].replace('Z','+00:00'))-datetime.fromisoformat(t)).total_seconds()
                except (ValueError,KeyError):continue
                if delta:timestamp_conflicts.append({'ticker':ticker,'accession':acc,'api_acceptance':f['acceptanceDateTime'],'frozen_cache_acceptance':t,'delta_seconds':delta,'authority':'neither source is silently substituted; original index required'})
        for _,obs in g.iterrows():
            cutoff=obs.signal_cutoff
            usable=[f for f in files.values() if eligible(f,cutoff)]
            if not usable:
                rows.append({'date':obs.date,'ticker':ticker,'extraction_status':'missing_eligible_timestamped_filing'});continue
            f=max(usable,key=lambda x:(x['filingDate'],x['acceptanceDateTime']))
            acc=f['accessionNumber']; url=f'https://www.sec.gov/Archives/edgar/data/{int(j["cik"])}/{acc.replace("-","")}/{f["primaryDocument"]}'
            accessions[ticker,acc]={'ticker':ticker,'accession':acc,'form':f['form'],'report_date':f['reportDate'],'filing_date':f['filingDate'],'api_acceptance':f['acceptanceDateTime'],'url':url,'original_index_url':url.rsplit('/',1)[0]+'/'+acc+'-index.html','document_certification':'not_automatically_certified'}
            row={'date':obs.date,'ticker':ticker,'signal_cutoff':cutoff,'accession':acc,'report_date':f['reportDate'],'filing_date':f['filingDate'],'api_acceptance':f['acceptanceDateTime'],'api_eastern_date':f['api_acceptance_eastern_date'],'filing_url':url,'filing_form':f['form'],'filing_age_days':(date.fromisoformat(obs.date)-date.fromisoformat(f['reportDate'])).days,'extraction_status':'API_staging_only','original_release_alignment':'not_certified','quarter_cash_scope_certified':False,'predictive_use_allowed':False}
            selected={}
            cash=choose(facts,f,'cfo')
            ytd_start=cash.get('start') if cash else None
            row['ytd_start']=ytd_start
            for concept in TAGS:
                is_balance=concept in ['inventory','receivables','current_assets','current_liabilities','long_term_debt_noncurrent','debt_current']
                wanted=choose(facts,f,concept,start=None if is_balance else ytd_start) if (is_balance or ytd_start) else None
                selected[concept]=wanted
                if not wanted:
                    row[concept+'_ytd_usd']=None;continue
                suffix='_instant_usd' if is_balance else '_ytd_shares' if concept=='diluted_shares' else '_ytd_usd'
                row[concept+suffix]=wanted['val']
                lineage.append({'date':obs.date,'ticker':ticker,'metric':concept+suffix,'source_id':f'{ticker}:{acc}:{wanted["tag"]}:{wanted.get("start","")}:{wanted["end"]}','accession':acc,'tag':wanted['tag'],'period_start':wanted.get('start'),'period_end':wanted['end'],'value':wanted['val'],'unit':wanted['unit'],'api_filed':wanted['filed'],'filing_date':f['filingDate'],'api_acceptance':f['acceptanceDateTime'],'url':url,'evidence':'fact_provider_standardized','scope_certification':'pending_original_document','raw_source_sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
            ni=selected['net_income']
            row['net_income_tag']=ni['tag'] if ni else None
            row['net_income_scope']='consolidated_profit_loss_tag_pending_original_scope_check' if ni and ni['tag']=='ProfitLoss' else 'NetIncomeLoss_may_be_parent_attributable_pending_original_scope_check'
            # Quarterly derivation is a separate staging series, never mixed with YTD.
            for concept in ['cfo','gross_ppe_capex','sbc','revenue','net_income','operating_income','gross_profit']:
                cur=selected[concept]
                if not cur or not cur.get('start'):continue
                span=(date.fromisoformat(cur['end'])-date.fromisoformat(cur['start'])).days
                if 60<=span<=125:
                    row[concept+'_quarter_usd']=cur['val'];row[concept+'_quarter_method']='direct_Q1_or_quarter'
                else:
                    prev=prior_ytd(facts,files,concept,cur,cutoff)
                    if prev:
                        row[concept+'_quarter_usd']=cur['val']-prev['val'];row[concept+'_quarter_method']='annual_minus_9m' if f['form']=='10-K' else 'YTD_subtraction'
                        row[concept+'_prior_accession']=prev['accn']
                        lineage.append({'date':obs.date,'ticker':ticker,'metric':concept+'_quarter_subtraction_operand','source_id':f'{ticker}:{prev["accn"]}:{prev["tag"]}:{prev["start"]}:{prev["end"]}','accession':prev['accn'],'tag':prev['tag'],'period_start':prev['start'],'period_end':prev['end'],'value':prev['val'],'unit':'USD','api_filed':prev['filed'],'filing_date':prev['filing']['filingDate'],'api_acceptance':prev['filing']['acceptanceDateTime'],'evidence':'derived_calculation_operand','scope_certification':'pending_original_document'})
            if ticker=='NVDA':
                # Original source combines PPE and intangibles; no pure-PPE backsolve.
                for period in ['ytd','quarter']:
                    key='gross_ppe_capex_'+period+'_usd'
                    row['unverified_ppe_tag_'+period+'_usd']=row.get(key)
                    row[key]=None
            # API-derived ratios are audit-only; no ranking, correlations or return fit.
            for period in ['ytd','quarter']:
                def val(k):return row.get(k+'_'+period+'_usd')
                c,n,r,k,s,o=map(val,['cfo','net_income','revenue','gross_ppe_capex','sbc','operating_income'])
                if c is not None and k is not None:row['analyst_fcf_'+period+'_usd']=c-k
                fc=row.get('analyst_fcf_'+period+'_usd')
                for name,num,den in [('cfo_to_earnings',c,n),('fcf_to_earnings',fc,n),('cfo_margin',c,r),('fcf_margin',fc,r),('capex_intensity',k,r),('sbc_burden',s,r),('operating_margin',o,r)]:
                    row[name+'_'+period]=num/den if num is not None and den is not None and den>0 else None
                row['earnings_nonpositive_'+period]=n<=0 if n is not None else None
                # A tag name does not prove that NI matches consolidated CFO.
                if not ni or ni['tag']!='ProfitLoss':
                    row['cfo_to_earnings_'+period]=None
                    row['fcf_to_earnings_'+period]=None
            row['scope_warning']='No uniform recurring-profit or scope certification.'
            if ticker=='WDC' and f['reportDate']>='2025-03-28':
                row['scope_warning']='Continuing HDD income versus consolidated cash including Flash: cash-conversion ratios are INVALID.'
                for k in list(row):
                    if any(x in k for x in ['cfo_to_earnings','fcf_to_earnings','cfo_margin','fcf_margin']):row[k]=None
            if ticker=='APP' and f['reportDate']>='2025-06-30':
                row['scope_warning']='Apps divestiture/discontinued scope: consolidated cash cannot certify continuing cash conversion.'
                for k in list(row):
                    if any(x in k for x in ['cfo_to_earnings','fcf_to_earnings','cfo_margin','fcf_margin']):row[k]=None
            if ticker=='NVDA':row['scope_warning']='PPE cash tag requires original line check: filing may include intangible purchases; not certified gross-PPE-only capex.'
            if ticker=='STX':row['scope_warning']='FY24 cash includes divestiture receipts; accounting classification requires recurring-cash bridge.'
            if ticker=='MU':row['scope_warning']='Inventory lower-cost effects, patent/tax gains and incentive/equipment-contract cash require release bridge.'
            rows.append(row)
    d=OUT/'accounting_quality';p=pd.DataFrame(rows);p.to_csv(d/'sec_metrics_staging.csv',index=False)
    pd.DataFrame(lineage).to_csv(d/'sec_fact_lineage.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    pd.DataFrame(accessions.values()).sort_values(['ticker','filing_date']).to_csv(d/'original_accession_lineage.csv',index=False)
    pd.DataFrame(timestamp_conflicts).to_csv(d/'timestamp_conflicts.csv',index=False)
    merged=a[['date','ticker','outcome','sector','first_observed_company_signal']].merge(p,on=['date','ticker'],validate='one_to_one')
    cov=[]
    metrics=['cfo_ytd_usd','net_income_ytd_usd','revenue_ytd_usd','gross_ppe_capex_ytd_usd','sbc_ytd_usd','cfo_quarter_usd','gross_ppe_capex_quarter_usd','sbc_quarter_usd']
    for group,values in [('all',merged),*[(f'outcome:{k}',g) for k,g in merged.groupby('outcome')],*[(f'sector:{k}',g) for k,g in merged.groupby('sector')],*[(f'date:{k}',g) for k,g in merged.groupby('date')]]:
        for metric in metrics:
            good=values[metric].notna() if metric in values else pd.Series(False,index=values.index)
            cov.append({'group':group,'metric':metric,'observations':len(values),'values_present':int(good.sum()),'coverage_pct':100*good.mean(),'issuers_present':values.loc[good,'ticker'].nunique(),'certified_predictive_rows':0,'note':'Present API value does not certify original release/period/scope.'})
    pd.DataFrame(cov).to_csv(d/'missingness_coverage.csv',index=False)
    issuer=p.groupby('ticker').agg(observations=('date','size'),filings=('accession','nunique'),cfo_present=('cfo_ytd_usd','count'),capex_present=('gross_ppe_capex_ytd_usd','count'),sbc_present=('sbc_ytd_usd','count'),source_certified_rows=('predictive_use_allowed','sum')).reset_index()
    issuer.to_csv(d/'company_coverage.csv',index=False)
    print({'rows':len(p),'issuers':p.ticker.nunique(),'selected_accessions':len(accessions),'timestamp_conflicts':len(timestamp_conflicts),'certified_predictive_rows':0});print(pd.DataFrame(cov).query('group == "all"').to_string(index=False))
if __name__=='__main__':main()
