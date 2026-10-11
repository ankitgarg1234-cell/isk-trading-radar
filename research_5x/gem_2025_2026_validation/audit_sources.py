"""Signal-by-signal original-accession and availability checks, no backfill.

Compare exact frozen quarterly inputs against SEC facts from the SAME accession
and period. Numeric matching across unrelated accessions is prohibited. Missing
standard tags remain unresolved, never automatically false economic gates.
"""
import sys,json,gzip,pickle,hashlib,math
from collections import defaultdict
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'research_5x/code'))
import run_research as b
b.REPO=ROOT
ALIASES={'TotalRevenue':['RevenueFromContractWithCustomerExcludingAssessedTax','RevenueFromContractWithCustomerIncludingAssessedTax','Revenues','SalesRevenueNet','SalesRevenueGoodsNet','SalesRevenueServicesNet','RevenueFromContractWithCustomer','Revenue'],'NetIncome':['NetIncomeLoss','ProfitLoss','NetIncomeLossAvailableToCommonStockholdersBasic'],'OperatingIncome':['OperatingIncomeLoss','IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest']}
def timestamp(value):
    if not value:return None
    try:
        d=datetime.fromisoformat(value.replace('Z','+00:00'));return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)
    except ValueError:return None
def main():
    prices=b.load_gz(ROOT/'backtests/staged/wf3_prices.json.gz');funds=b.load_gz(ROOT/'backtests/staged/wf3_valuein_fundamentals.json.gz');store=b.pit_store(funds)
    frames,panel,calendar=pickle.load(open(OUT/'archive_prepared.pkl','rb'))
    mapping=json.loads((OUT/'security_identifier_map.json').read_text())
    dates=sorted(panel[panel.date>='2025-01-01'].date.unique())
    members,changes=b.membership(prices);ix=0
    candidate={};dependencies=defaultdict(list);selection=[];coverage=[]
    for ds in dates:
        while ix<len(changes) and changes[ix]['date']<=ds:
            e=changes[ix];members.discard(e.get('removed'))
            if e.get('added'):members.add(e['added'])
            ix+=1
        g=panel[panel.date==ds].set_index('ticker')
        qualified=g[(g.r63>0)&g.G&g.E&(g.margin_delta_pp>3)].sort_values('r63',ascending=False,kind='stable');ranks={s:i+1 for i,s in enumerate(qualified.index)}
        asof=date.fromisoformat(ds)-timedelta(days=1)
        for sym in sorted(members):
            if not sym:continue
            price=frames.get(sym);hasprice=price is not None and ds in price.index
            feature=g.loc[sym] if sym in g.index else None
            reason='unknown_missing_prices' if not hasprice else ('failed_price_history_liquidity_or_price_gate' if feature is None else ('selected_original' if ranks.get(sym,999)<=5 else 'qualified_not_top5' if sym in ranks else 'not_qualified_on_archived_features'))
            row={'signal_date':ds,'signal_timestamp':ds+'T21:01:00+00:00','ticker':sym,'historical_membership_status':'UNVERIFIED_RECONSTRUCTED_MEMBER','price_present':hasprice,'feature_row_present':feature is not None,'revenue_yoy':feature.revenue_yoy if feature is not None else None,'earnings_improvement':bool(feature.earnings_improvement) if feature is not None else None,'margin_delta_pp':feature.margin_delta_pp if feature is not None else None,'r63':feature.r63 if feature is not None else None,'rank':ranks.get(sym),'selected_original_top5':ranks.get(sym,999)<=5,'decision_reason':reason,'status':'INCOMPLETE_UNIVERSE_AND_FACTS'}
            selection.append(row);candidate[(ds,sym)]=row
            identifier=mapping.get(sym,{});cik=identifier.get('cik')
            for concept in ['TotalRevenue','NetIncome','OperatingIncome']:
                q=store.quarter(sym,concept,asof)
                if not q:
                    coverage.append({'ticker':sym,'signal_date':ds,'field':concept,'status':'MISSING_QUARTER_INPUT','required_period':'latest 10-Q quarter and 310–420-day comparator','source':'frozen Valuein sample','cik':cik,'price_present':hasprice})
                    continue
                # Operating margins use revenue periods, not necessarily the
                # independently latest operating-income period.
                rev=store.quarter(sym,'TotalRevenue',asof)
                pe=rev[-1][0] if rev and concept=='OperatingIncome' else q[-1][0]
                old=[e for e in (rev if rev and concept=='OperatingIncome' else q) if 310<=(pe-e[0]).days<=420]
                periods=[pe]+([min(old,key=lambda e:abs((pe-e[0]).days-365))[0]] if old else [])
                for period in periods:
                    chosen=next((e for e in q if e[0]==period),None)
                    if chosen is None:
                        coverage.append({'ticker':sym,'signal_date':ds,'field':concept,'status':'MISSING_PERIOD_INPUT','required_period':period.isoformat(),'source':'frozen Valuein sample','cik':cik,'price_present':hasprice});continue
                    pe,value,record=chosen
                    dependencies[cik].append({'ticker':sym,'signal_date':ds,'signal_timestamp':row['signal_timestamp'],'concept':concept,'period_end':pe.isoformat(),'period_start':str(record.get('period_start') or '')[:10],'used_value':value,'numeric_value':record.get('numeric_value'),'derived_quarterly_value':record.get('derived_quarterly_value'),'accession':record.get('accession_id'),'provider_accepted_at':record.get('accepted_at'),'provider_filing_date':str(record.get('filing_date'))[:10],'cik':cik})
    audited=[];minimal=[];source_manifest=[]
    for cik,deps in dependencies.items():
        if not cik:continue
        fpath=OUT/'public_sources/facts'/(cik+'.json');spath=OUT/'public_sources/submissions'/(cik+'.json')
        factsrec=json.loads(fpath.read_text()) if fpath.exists() else {};subrec=json.loads(spath.read_text()) if spath.exists() else {}
        facts=factsrec.get('data',{}).get('facts',{}).get('us-gaap',{});recent=subrec.get('data',{}).get('filings',{}).get('recent',{})
        accepts={a:recent.get('acceptanceDateTime',[None]*len(recent.get('accessionNumber',[])))[i] for i,a in enumerate(recent.get('accessionNumber',[]))}
        for part in subrec.get('data',{}).get('filings',{}).get('files',[]):
            path=OUT/'public_sources/submission_parts'/(part['name'][:-5]+'.json')
            if path.exists():
                rec=json.loads(path.read_text());data=rec.get('data',{})
                accepts.update({a:data.get('acceptanceDateTime',[None]*len(data.get('accessionNumber',[])))[i] for i,a in enumerate(data.get('accessionNumber',[]))})
                source_manifest.append({k:rec.get(k) for k in ['url','status','retrieved_at','bytes','sha256','error']})
        index=defaultdict(list)
        for concept,tags in ALIASES.items():
            for tag in tags:
                for unit,records in facts.get(tag,{}).get('units',{}).items():
                    if unit!='USD':continue
                    for record in records:index[(concept,record.get('accn'),record.get('end'))].append({'tag':tag,**record})
        for d in deps:
            direct=[]
            for x in index[d['concept'],d['accession'],d['period_end']]:
                if not x.get('start'):continue
                span=(date.fromisoformat(x['end'])-date.fromisoformat(x['start'])).days
                if 60<=span<=125:direct.append(x)
            matches=[x for x in direct if abs(float(x['val'])-float(d['used_value']))<=max(.01,abs(float(d['used_value']))*1e-9)]
            # A pretax-income fact cannot certify operating income merely
            # because the value happens to match.
            matches=[x for x in matches if d['concept']!='OperatingIncome' or x['tag']=='OperatingIncomeLoss']
            actual=accepts.get(d['accession']);at=timestamp(actual);cutoff=timestamp(d['signal_timestamp'])
            timing=bool(at and at<cutoff)
            same=bool(at and timestamp(d['provider_accepted_at']) and abs((at-timestamp(d['provider_accepted_at'])).total_seconds())<1)
            status='VERIFIED_SAME_ACCESSION_QUARTER' if matches and timing else 'VALUE_MISMATCH' if direct and not matches else 'MISSING_SEC_DIRECT_QUARTER'
            if matches and not timing:status='ACCEPTANCE_UNVERIFIED_OR_AFTER_SIGNAL'
            record={**d,'sec_accepted_at':actual,'timestamp_matches_provider':same,'publication_before_signal':timing,'matched_sec_tags':'|'.join(sorted({x['tag'] for x in matches})),'sec_direct_values':json.dumps([{'tag':x['tag'],'start':x.get('start'),'val':x['val']} for x in direct]),'fact_status':status,'sec_facts_url':factsrec.get('url'),'sec_raw_response_sha256':factsrec.get('sha256'),'submissions_url':subrec.get('url'),'submissions_response_sha256':subrec.get('sha256')}
            audited.append(record)
            minimal.append({'ticker':d['ticker'],'signal_date':d['signal_date'],'concept':d['concept'],'cik':cik,'accession':d['accession'],'period_end':d['period_end'],'sec_accepted_at':actual,'source_sha256':factsrec.get('sha256'),'direct_quarter_facts':direct})
        for record,path in [(factsrec,fpath),(subrec,spath)]:
            source_manifest.append({k:record.get(k) for k in ['url','status','retrieved_at','bytes','sha256','error']})
    factsdf=pd.DataFrame(audited);factsdf.to_csv(OUT/'signal_audit.csv.gz',index=False)
    # Publish a selected/qualified audit in plain CSV and all inputs compressed.
    keys={(r['signal_date'],r['ticker']) for r in selection if r['rank'] is not None}
    factsdf[[ (r.signal_date,r.ticker) in keys for r in factsdf.itertuples() ]].to_csv(OUT/'signal_audit.csv',index=False)
    pd.DataFrame(selection).to_csv(OUT/'stock_selection_audit.csv',index=False)
    pd.DataFrame(coverage).to_csv(OUT/'pit_data_coverage.csv',index=False)
    with gzip.open(OUT/'sec_minimal_evidence.json.gz','wt') as stream:json.dump(minimal,stream,separators=(',',':'))
    pd.DataFrame(source_manifest).drop_duplicates('url').to_csv(OUT/'public_source_manifest.csv',index=False)
    groups=factsdf.groupby(['signal_date','ticker']).fact_status.apply(lambda x:bool((x=='VERIFIED_SAME_ACCESSION_QUARTER').all()))
    unresolved=factsdf[factsdf.fact_status!='VERIFIED_SAME_ACCESSION_QUARTER']
    unresolved.to_csv(OUT/'unresolved_fact_inputs.csv.gz',index=False)
    summary={'audited_input_uses':len(factsdf),'signal_security_records':len(selection),'status_counts':factsdf.fact_status.value_counts().to_dict(),'ticker_signal_all_used_facts_verified':int(groups.sum()),'ticker_signal_with_used_facts':len(groups),'missing_input_records':len(coverage),'all_signals_certified':False,'certification_blockers':['Missing price/financial competitors can change rankings','Historical membership/identifiers not fully primary-verified','Some exact original-accession values unresolved or disagree with archive','Payable-date dividends and nonstandard corporate-action economics unresolved','Historical industries missing'],'public_sources_downloaded':len(source_manifest)}
    (OUT/'source_audit_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary),flush=True)
if __name__=='__main__':main()
