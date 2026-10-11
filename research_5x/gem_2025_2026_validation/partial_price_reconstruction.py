"""Separate sensitivity to EA; AVB vendor 2.793:1 action remains unresolved; not certification."""
import sys,json,pickle
from pathlib import Path
from datetime import datetime,timezone
import pandas as pd
O=Path(__file__).resolve().parent;R=O.parents[1]
sys.path.insert(0,str(R/'research_5x/code'))
import run_research as b
b.REPO=R
import continuation_engine as e
p=b.load_gz(R/'backtests/staged/wf3_prices.json.gz');fund=b.load_gz(R/'backtests/staged/wf3_valuein_fundamentals.json.gz');spy=json.loads((R/'research_5x/data/spy.json').read_text())
for sym in ['EA']:
 rec=json.loads((O/'public_sources/prices'/f'{sym}.json').read_text());raw=rec['data']['chart']['result'][0];q=raw['indicators']['quote'][0];rows=[]
 for i,t in enumerate(raw['timestamp']):
  ds=datetime.fromtimestamp(t,timezone.utc).date().isoformat()
  if ds>'2026-10-01' or q['close'][i] is None:continue
  rows.append({'date':ds,**{k:q[k][i] for k in ['open','high','low','close','volume']}})
 events=raw.get('events',{});assert not events.get('splits'), 'Split adjustment requires separate proof'
 p['market'][sym]={'rows':rows,'splits':[],'dividends':[{'date':datetime.fromtimestamp(v['date'],timezone.utc).date().isoformat(),'amount':v['amount']} for v in events.get('dividends',{}).values()]}
f,panel,c=b.prepare(p,fund,spy)
oldf,oldpanel,oldc=pickle.load(open(O/'extended_prepared.pkl','rb'))
for s in oldf:
 if s not in ['AVB','EA']:f[s]=oldf[s]
c=oldc
cfg=json.loads((O/'frozen_config.json').read_text())['configuration'];out=[]
for name,start,end in [('A_2025','2025-01-02','2025-12-31'),('B_2026_YTD','2026-01-02',c[-1]),('C_continuous','2025-01-02',c[-1])]:
 result,curve,tr,rolling,sig=e.simulate(cfg,f,panel,c,start=start,end=end,cost_bps=20)
 out.append({'experiment':name,'status':'INCOMPLETE_PUBLIC_PRICE_RECONSTRUCTION_EA_ONLY','return_pct':result['net_return_pct'],'max_drawdown_pct':result['max_dd_pct'],'trade_count':result['trade_count']})
pd.DataFrame(out).to_csv(O/'partial_reconstruction_results.csv',index=False)
print(pd.DataFrame(out).to_string(index=False))
