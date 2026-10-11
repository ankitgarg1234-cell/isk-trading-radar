"""Append recovered Oct 2–9 prices to a separate prepared replay snapshot.

Original signal dates/rank inputs remain byte-identical. No October month-end
signal exists. Missing held marks fail rather than silently carrying forward.
"""
import pickle,json,hashlib
from pathlib import Path
from datetime import datetime,timezone
import pandas as pd
OUT=Path(__file__).resolve().parent
def main():
    frames,panel,calendar=pickle.load(open(OUT/'archive_prepared.pkl','rb'))
    observed={};audit=[]
    for path in sorted((OUT/'public_sources/prices').glob('*.json')):
        record=json.loads(path.read_text())
        if record['status']!=200:continue
        raw=record['data']['chart']['result'][0];sym=path.stem
        quote=raw['indicators']['quote'][0]
        rows=[]
        for i,ts in enumerate(raw['timestamp']):
            ds=datetime.fromtimestamp(ts,timezone.utc).date().isoformat()
            if ds<='2026-10-01' or ds>'2026-10-09':continue
            if quote['close'][i] is None:continue
            rows.append({'date':ds,**{k:quote[k][i] for k in ['open','high','low','close','volume']}})
        if not rows or sym not in frames:continue
        events=raw.get('events',{})
        for r in rows:
            ds=r['date'];r['raw_open']=r['open'];r['raw_close']=r['close'];r['dividend']=0.;r['split']=1.;r['adv20']=float(frames[sym].loc[frames[sym].index<'2026-10-02','adv20'].iloc[-1]);r['nominal_factor']=1.
            for ev in events.get('dividends',{}).values():
                if datetime.fromtimestamp(ev['date'],timezone.utc).date().isoformat()==ds:r['dividend']+=ev['amount']
            for ev in events.get('splits',{}).values():
                if datetime.fromtimestamp(ev['date'],timezone.utc).date().isoformat()==ds:r['split']*=ev['numerator']/ev['denominator']
            audit.append({'ticker':sym,'date':ds,'raw_open':r['raw_open'],'raw_close':r['raw_close'],'source_url':record['url'],'source_response_sha256':record['sha256'],'available_at':ds+'T20:00:00+00:00','status':'PUBLIC_VENDOR_DAILY_BAR_NOT_EXECUTION_CERTIFICATION'})
        frames[sym]=pd.concat([frames[sym],pd.DataFrame(rows).set_index('date')]);observed[sym]=[r['date'] for r in rows]
    assert observed['SPY'][-1]=='2026-10-09'
    calendar+=observed['SPY']
    with (OUT/'extended_prepared.pkl').open('wb') as stream:pickle.dump((frames,panel,calendar),stream)
    pd.DataFrame(audit).to_csv(OUT/'price_extension_audit.csv',index=False)
    print('Price extension through',calendar[-1],'securities',len(observed))
if __name__=='__main__':main()
