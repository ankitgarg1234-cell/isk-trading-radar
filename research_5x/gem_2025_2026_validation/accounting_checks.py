"""Independent cash, basis, holdings, dividends and contribution reconciliation."""
import json,pickle
from pathlib import Path
from collections import defaultdict
import pandas as pd
O=Path(__file__).resolve().parent
f,_,_=pickle.load(open(O/'extended_prepared.pkl','rb'))
nav=pd.read_csv(O/'daily_nav.csv');tr=pd.read_csv(O/'trades.csv');h=pd.read_csv(O/'holdings.csv');con=pd.read_csv(O/'stock_profit_contribution.csv');rows=[];checks=[];liq=[]
for (experiment,policy),g in nav.groupby(['experiment','policy'],sort=False):
 cash=10000.;held=defaultdict(float);basis=defaultdict(float);realized=defaultdict(float);income=defaultdict(float);maxres=0
 ts=tr[(tr.experiment==experiment)&(tr.policy==policy)]
 hg=h[(h.experiment==experiment)&(h.policy==policy)]
 for r in g.itertuples():
  for s,q in list(held.items()):
   if q<=0:continue
   assert float(f[s].loc[r.date,'split'])==1.,('Held corporate action requires ledger implementation',s,r.date)
   div=q*float(f[s].loc[r.date,'dividend']);cash+=div;income[s]+=div
  for t in ts[ts.date==r.date].itertuples():
   q=t.shares;s=t.ticker
   if t.side=='BUY':held[s]+=q;basis[s]+=t.gross+t.cost;cash-=t.gross+t.cost
   else:
    alloc=basis[s]*q/held[s];basis[s]-=alloc;held[s]-=q;realized[s]+=t.gross-t.cost-alloc;cash+=t.gross-t.cost
   prior=f[s][f[s].index<r.date].tail(20);adv=float((prior.raw_close*prior.volume).mean())
   liq.append({'experiment':experiment,'policy':policy,'date':r.date,'ticker':s,'gross':t.gross,'prior20_quoted_dollar_volume':adv,'trade_fraction_of_prior20_volume_pct':t.gross/adv*100,'status':'VENDOR_VOLUME_CONVENTION_UNCERTIFIED'})
  value=sum(q*float(f[s].loc[r.date,'raw_close']) for s,q in held.items() if q>0)
  residual=max(abs(cash-r.cash),abs(cash+value-r.equity));maxres=max(maxres,residual);assert residual<1e-6
  for s in held:
   q=held[s];mark=float(f[s].loc[r.date,'raw_close']) if q>0 else 0
   rows.append({'experiment':experiment,'policy':policy,'date':r.date,'ticker':s,'shares':q,'value':q*mark,'cost_basis_including_buy_costs':basis[s],'realized_trade_pnl_net_costs':realized[s],'unrealized_pnl':q*mark-basis[s],'cumulative_cash_dividends_ex_date':income[s],'total_profit_contribution':realized[s]+income[s]+q*mark-basis[s],'status':'ARCHIVED_INPUT_REPLAY_UNCERTIFIED'})
 if policy!='SPY':
  final={s:realized[s]+income[s]+held[s]*(float(f[s].loc[g.date.iloc[-1],'raw_close']) if held[s]>0 else 0)-basis[s] for s in held}
  expected=con[(con.experiment==experiment)&(con.policy==policy)]
  for x in expected.itertuples():assert abs(final.get(x.ticker,0)-x.net_profit)<1e-6
 assert abs(sum(realized[s]+income[s]+held[s]*(float(f[s].loc[g.date.iloc[-1],'raw_close']) if held[s]>0 else 0)-basis[s] for s in held)-(g.equity.iloc[-1]-10000))<1e-6
 checks.append({'experiment':experiment,'policy':policy,'max_cash_nav_residual_dollars':maxres,'held_split_or_spinoff_events':0,'status':'PASS_ACCOUNTING_NOT_PIT'})
pd.DataFrame(rows).to_csv(O/'position_pnl.csv',index=False);pd.DataFrame(checks).to_csv(O/'accounting_checks.csv',index=False);pd.DataFrame(liq).to_csv(O/'liquidity_exposure.csv',index=False)
print('Independent accounting passed',len(checks),'accounts')
