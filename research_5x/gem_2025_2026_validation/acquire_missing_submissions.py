"""Recover SEC archived submission parts only where an actual input needs them."""
import json,sys
from pathlib import Path
import pandas as pd
from acquire_sources import get,OUT
def main():
    audit=pd.read_csv(OUT/'signal_audit.csv.gz')
    missing=audit[audit.sec_accepted_at.isna()]
    tasks=set()
    for cik,group in missing.groupby('cik'):
        cik=str(int(cik)).zfill(10);path=OUT/'public_sources/submissions'/(cik+'.json')
        if not path.exists():continue
        data=json.loads(path.read_text()).get('data',{})
        for part in data.get('filings',{}).get('files',[]):
            if any(part.get('filingFrom','')<=ds<=part.get('filingTo','9999') for ds in group.provider_filing_date.astype(str)):
                tasks.add(part['name'])
    for name in sorted(tasks):
        r=get('https://data.sec.gov/submissions/'+name,'submission_parts',name[:-5]);print(name,r['status'],flush=True)
if __name__=='__main__':main()
