"""Append-only public SEC discovery snapshots. No production dependencies."""
from pathlib import Path
import argparse,datetime,gzip,hashlib,json,time,urllib.request
import pandas as pd
OUT=Path(__file__).resolve().parents[1]
ROOT=OUT.parents[1]
SOURCE_REPO=ROOT/'research_repository' if (ROOT/'research_repository/backtests/staged').exists() else ROOT

def retrieve(url,path):
    now=datetime.datetime.now(datetime.timezone.utc).isoformat()
    if path.exists():
        b=gzip.open(path,'rb').read();return {'url':url,'file':str(path.relative_to(OUT)),'retrieved_at':now,'status':'cached','bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'ISK historical accounting research','Accept-Encoding':'identity'})
        with urllib.request.urlopen(req,timeout=45) as r:b=r.read()
        json.loads(b)
        with gzip.GzipFile(filename=str(path),mode='wb',mtime=0) as z:z.write(b)
        return {'url':url,'file':str(path.relative_to(OUT)),'retrieved_at':now,'status':'success','bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
    except Exception as e:return {'url':url,'file':str(path.relative_to(OUT)),'retrieved_at':now,'status':'failed','error':str(e)}

def main():
    a=pd.read_csv(OUT/'accounting_quality/mature_cohorts.csv')
    mapping_file=OUT/'accounting_quality/cik_map.csv'
    known=pd.read_csv(mapping_file,dtype=str).set_index('ticker').cik.to_dict()
    entries=[];mapping=[]
    for ticker in sorted(a.ticker.unique()):
        ciks=[known[ticker].zfill(10)]
        if len(ciks)!=1:raise ValueError((ticker,ciks))
        cik=ciks[0];mapping.append({'ticker':ticker,'cik':cik,'source':'frozen_phase2_fundamental_cache'})
        for name,url in [('companyfacts',f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json'),('submissions',f'https://data.sec.gov/submissions/CIK{cik}.json')]:
            p=OUT/f'accounting_quality/raw/{ticker}_{name}.json.gz';r=retrieve(url,p);r.update(ticker=ticker,cik=cik,kind=name);entries.append(r);time.sleep(.2)
        sub=OUT/f'accounting_quality/raw/{ticker}_submissions.json.gz'
        if sub.exists():
            j=json.load(gzip.open(sub))
            for old in j['filings'].get('files',[]):
                if old['filingFrom'] <= '2025-10-01' and old['filingTo'] >= '2023-01-01':
                    name=old['name'];r=retrieve(f'https://data.sec.gov/submissions/{name}',OUT/f'accounting_quality/raw/{ticker}_{name}.gz');r.update(ticker=ticker,cik=cik,kind='older_submissions');entries.append(r);time.sleep(.2)
        print(ticker,[(x['kind'],x['status']) for x in entries[-2:]],flush=True)
    pd.DataFrame(mapping).to_csv(OUT/'accounting_quality/cik_map.csv',index=False)
    inventory=OUT/'accounting_quality/sec_retrieval_inventory.json'
    if inventory.exists():
        history=OUT/'accounting_quality/sec_retrieval_runs.json'
        previous=json.loads(history.read_text()) if history.exists() else [json.loads(inventory.read_text())]
        previous.append(entries);history.write_text(json.dumps(previous,indent=2)+'\n')
    inventory.write_text(json.dumps(entries,indent=2)+'\n')
if __name__=='__main__':main()
