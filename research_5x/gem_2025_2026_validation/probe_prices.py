"""Public-price recovery probes, rate limited; never replace archive silently."""
import json,pickle,sys,time,gzip,urllib.request,hashlib
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'research_5x/code'))
import run_research as b
b.REPO=ROOT
import continuation_engine as adapter
def main():
    frames,panel,calendar=pickle.load(open(OUT/'archive_prepared.pkl','rb'))
    cfg=next(c for c in b.CONFIGS if c['name']=='growth_margin5')
    wanted={'SPY'}
    for policy in ['original','retain_rank35','preserve_weights','retain_and_preserve']:
        c=dict(cfg)
        if policy!='original':c.update(retain_rank35='retain' in policy,preserve_weights='preserve' in policy,holding_rule=policy)
        z,curve,tr,_,sig=adapter.simulate(c,frames,panel,calendar,start='2025-01-02',end='2026-10-01')
        for s in sig[sig.date>='2026-08-01'].tickers:
            wanted.update(s.split('|'))
    g=panel[panel.date=='2026-09-30'];wanted.update(g[(g.r63>0)&g.G&g.E&(g.margin_delta_pp>3)].ticker)
    p=b.load_gz(ROOT/'backtests/staged/wf3_prices.json.gz')
    wanted.update(p['coverage']['price_failed'])
    audit=OUT/'stock_selection_audit.csv'
    if audit.exists():
        import pandas as pd
        selection=pd.read_csv(audit);wanted.update(selection.loc[~selection.price_present,'ticker'])
    wanted.discard('')
    out=OUT/'public_sources/prices';out.mkdir(exist_ok=True)
    start=int(datetime(2024,1,1,tzinfo=timezone.utc).timestamp());end=int(datetime(2026,10,11,tzinfo=timezone.utc).timestamp())
    for i,sym in enumerate(sorted(wanted),1):
        path=out/(sym+'.json')
        if path.exists():continue
        url=f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={start}&period2={end}&interval=1d&events=div,splits'
        rec={'ticker':sym,'url':url,'retrieved_at':datetime.now(timezone.utc).isoformat()}
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
            with urllib.request.urlopen(req,timeout=20) as r:
                raw=r.read();rec.update(status=r.status,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),data=json.loads(raw))
        except Exception as e:rec.update(status='FAILED',error=str(e))
        path.write_text(json.dumps(rec,separators=(',',':')))
        print(sym,rec['status'],flush=True);time.sleep(1)

if __name__=='__main__':main()
