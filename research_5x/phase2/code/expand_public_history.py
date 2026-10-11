"""Append-only Yahoo price capability probe; selected survivors, not a universe."""
import sys,json,hashlib
from pathlib import Path
from datetime import datetime,timezone
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'research_5x/vendor'))
import yfinance as yf
BASE=ROOT/'research_5x/phase2/2026-10-11_earnings_acceleration/history'
OUT=BASE/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');OUT.mkdir(parents=True,exist_ok=False)
yf.set_tz_cache_location(str(BASE/'local_cache'))
# Fixed before downloads; delisted names are intentionally included as capability checks.
symbols=['SPY','MU','STX','WDC','AMD','NVDA','ZBRA','FSLR','DECK','ETN','XOM','UNH','WBA','PXD']
def get(sym):
    try:
        f=yf.Ticker(sym).history(start='2010-01-01',end='2024-01-01',auto_adjust=False,back_adjust=False,actions=True,repair=False,timeout=15,raise_errors=True)
        p=OUT/(sym+'.csv');f.to_csv(p)
        return {'ticker':sym,'status':'ok' if len(f) else 'empty','rows':len(f),'first':str(f.index.min()),'last':str(f.index.max()),'path':str(p.relative_to(ROOT)),
                'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'columns':list(f.columns),
                'splits':int((f['Stock Splits']!=0).sum()) if 'Stock Splits' in f else 0}
    except Exception as ex:return {'ticker':sym,'status':'error','error':str(ex),'investment_return':None}
protocol={'written_before_downloads_utc':datetime.now(timezone.utc).isoformat(),'symbols':symbols,'start':'2010-01-01','end_exclusive':'2024-01-01',
 'purpose':'Earlier-cycle price availability only; selected case studies cannot establish historical screening performance.',
 'options':{'auto_adjust':False,'back_adjust':False,'actions':True,'repair':False},
 'limits':['Same-source Yahoo check cannot independently validate prices','Corporate events/dividend payment dates require separate security master','Chosen live companies are survivor-biased; do not call this historicalS&P500','Missing dead-company data is missing, not zero return','No dated consensus snapshots or fundamental decision factors obtained by this probe']}
(OUT/'protocol.json').write_text(json.dumps(protocol,indent=2))
with ThreadPoolExecutor(max_workers=2) as pool:r=list(pool.map(get,symbols))
result={**protocol,'retrieved_at_utc':datetime.now(timezone.utc).isoformat(),'yfinance_version':yf.__version__,'results':r}
(OUT/'inventory.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
