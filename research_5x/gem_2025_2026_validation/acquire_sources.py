"""Append-only public-source probes and minimal SEC vintage extracts.

SEC requests limited to four/second across threads. No paid service purchased.
Raw response hashes and exact requested URLs retained; extracted observations
never overwrite the frozen vendor input.
"""
import json,gzip,hashlib,time,threading,urllib.request
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
CACHE=OUT/'public_sources';CACHE.mkdir(exist_ok=True)
lock=threading.Lock();next_call=0
def get(url,group,key):
    global next_call
    path=CACHE/group/(key+'.json');path.parent.mkdir(exist_ok=True)
    if path.exists():return json.loads(path.read_text())
    with lock:
        pause=max(0,next_call-time.monotonic())
        if pause:time.sleep(pause)
        next_call=time.monotonic()+.25
    rec={'url':url,'retrieved_at':datetime.now(timezone.utc).isoformat(),'key':key}
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'ISK Trading Radar academic research ankitgarg1234@gmail.com','Accept':'application/json'})
        with urllib.request.urlopen(req,timeout=25) as r:
            raw=r.read();rec.update(status=r.status,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),data=json.loads(raw))
    except Exception as e:rec.update(status='FAILED',error=str(e))
    path.write_text(json.dumps(rec,separators=(',',':')))
    return rec

def probe():
    urls={
      'sec_tickers':'https://www.sec.gov/files/company_tickers.json',
      'historical_changes':'https://raw.githubusercontent.com/chinobing/historical_sp500_constituents/main/sp500_changes_since_1996.csv',
      'spy_latest':'https://query1.finance.yahoo.com/v8/finance/chart/SPY?interval=1d&range=1mo',
      'crsp_cost':'https://www.crsp.org/products/documentation/crsp-us-stock-databases/',
      'sp_global_news':'https://www.spglobal.com/spdji/en/index-announcements/'
    }
    for key,url in urls.items():
        if key in ('sec_tickers','spy_latest'):get(url,'probes',key)
        else:
            path=CACHE/'probes'/(key+'.json')
            if path.exists():continue
            rec={'url':url,'retrieved_at':datetime.now(timezone.utc).isoformat()}
            try:
                with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=25) as r:
                    raw=r.read();rec.update(status=r.status,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),text=raw.decode(errors='replace'))
            except Exception as e:rec.update(status='FAILED',error=str(e))
            path.parent.mkdir(exist_ok=True);path.write_text(json.dumps(rec))

def main():
    funds=json.load(gzip.open(ROOT/'backtests/staged/wf3_valuein_fundamentals.json.gz','rt'))
    prices=json.load(gzip.open(ROOT/'backtests/staged/wf3_prices.json.gz','rt'))
    members=set(prices['membership']['start_members'])
    for e in prices['membership']['changes']:
        if e['date']<'2025-01-01':
            members.discard(e.get('removed'));members.add(e.get('added'))
    for e in prices['membership']['changes']:
        if '2025-01-01'<=e['date']<='2026-10-11':
            if e.get('added'):members.add(e['added'])
    members.discard(None);members.discard('')
    # Exact frozen engine's documented SATS -> ECHO issuer-series alias.
    if 'SATS' in members:members.add('ECHO')
    ticker_rec=get('https://www.sec.gov/files/company_tickers.json','probes','sec_tickers')
    current={v['ticker'].replace('.','-'):str(v['cik_str']).zfill(10) for v in (ticker_rec.get('data') or {}).values()}
    mapping={}
    for sym in sorted(members):
        records=funds['facts'].get(sym,[])
        ciks=sorted({str(x['cik']).zfill(10) for x in records if x.get('cik')})
        mapping[sym]={'cik':ciks[0] if len(ciks)==1 else current.get(sym),'mapping_source':'frozen accession records' if len(ciks)==1 else 'current SEC ticker index; identity aid only, never membership admission','ambiguous_ciks':ciks if len(ciks)>1 else []}
    (OUT/'security_identifier_map.json').write_text(json.dumps(mapping,indent=2))
    tasks=[(cik,'facts') for cik in sorted({v['cik'] for v in mapping.values() if v['cik']})]+[(cik,'submissions') for cik in sorted({v['cik'] for v in mapping.values() if v['cik']})]
    def work(task):
        cik,kind=task
        url=f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json' if kind=='facts' else f'https://data.sec.gov/submissions/CIK{cik}.json'
        return get(url,kind,cik)
    done=0;failed=0
    with ThreadPoolExecutor(max_workers=6) as pool:
        for f in as_completed([pool.submit(work,t) for t in tasks]):
            rec=f.result();done+=1;failed+=rec['status']!='200' and rec['status']!=200
            if done%50==0 or done==len(tasks): print(json.dumps({'completed':done,'requests':len(tasks),'failed':failed}),flush=True)
    probe()
    print('PUBLIC_ACQUISITION_COMPLETE',flush=True)

if __name__=='__main__':main()
