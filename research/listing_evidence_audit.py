"""Exact-ISIN current listing candidates, never retroactive historical maps."""
from collections import defaultdict
import csv,gzip,json,hashlib
from research.spgm_proxy import isin_valid
from research.spgm_sources import DEFAULT_OUTPUT,ROOT


def mapping_index(records):
    out=defaultdict(list)
    for record in records:
        key=record.get('Isin') or ''
        if isin_valid(key):out[key].append(record)
    return out


def candidate(member,index):
    isin=member.get('isin') or ''
    matches=index.get(isin,[]) if isin_valid(isin) else []
    # Names/issuer country never map an ordinary line onto an ADR.
    if not matches:return dict(status='NO_EXACT_ISIN_MATCH',historically_verified=False)
    identities={(r.get('Code'),r.get('Exchange'),r.get('Currency'),r.get('Type')) for r in matches}
    if len(identities)!=1:return dict(status='AMBIGUOUS_CURRENT_LISTING',historically_verified=False,candidates=matches)
    r=matches[0]
    return dict(status='CURRENT_EXACT_ISIN_CANDIDATE',historically_verified=False,
        symbol=r['Code']+'.'+r['Exchange'],currency=r['Currency'],source_type=r['Type'],
        isin=isin,source_records=matches,
        limitation='Current exchange observation; historical alias/MIC/effective interval not established')


def run():
    records=[];sources={}
    for name in ['KO_symbols.json','TW_symbols.json']:
        p=ROOT/'asia_corporate_actions'/name
        records.extend(json.loads(p.read_text()));sources[name]=hashlib.sha256(p.read_bytes()).hexdigest()
    index=mapping_index(records);rows=[];monthly=[]
    frozen=DEFAULT_OUTPUT/'sec_only_decision_universe'
    for snap in json.loads((frozen/'monthly_summary.json').read_text()):
        with gzip.open(frozen/(snap['selection_month']+'_confirmed.csv.gz'),'rt') as stream:members=list(csv.DictReader(stream))
        n=ambiguous=0
        for member in members:
            result=candidate(member,index)
            if result['status']=='CURRENT_EXACT_ISIN_CANDIDATE':n+=1
            if result['status']=='AMBIGUOUS_CURRENT_LISTING':ambiguous+=1
            if result['status']!='NO_EXACT_ISIN_MATCH':rows.append(dict(month=snap['selection_month'],instrument_key=member['instrument_key'],**result))
        monthly.append(dict(month=snap['selection_month'],securities=len(members),current_exact_isin_candidates=n,
            ambiguous_current_listing=ambiguous,historical_listing_verified=0))
    result=dict(monthly=monthly,current_candidate_security_months=sum(m['current_exact_isin_candidates'] for m in monthly),
        ambiguity_security_months=sum(m['ambiguous_current_listing'] for m in monthly),historical_listing_verified=0,
        cached_exchange_records=len(records),source_sha256=sources,new_api_requests=0)
    out=DEFAULT_OUTPUT/'historical_backtest/listing_audit';out.mkdir(parents=True,exist_ok=True)
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    (out/'current_candidates.json').write_text(json.dumps(rows,indent=2)+'\n')
    return result


if __name__=='__main__':
    result=run();print(json.dumps({k:v for k,v in result.items() if k not in {'monthly','source_sha256'}}))
