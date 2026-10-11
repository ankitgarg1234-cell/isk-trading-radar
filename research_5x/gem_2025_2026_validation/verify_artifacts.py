"""Offline research integrity checks on committed minimal evidence and accounts."""
import json,hashlib,gzip
from pathlib import Path
import pandas as pd,numpy as np
O=Path(__file__).resolve().parent;R=O.parents[1]
cfg=json.loads((O/'frozen_config.json').read_text())
for r in cfg['engines']:assert hashlib.sha256((R/r['path']).read_bytes()).hexdigest()==r['sha256']
assert cfg['configuration']=={'name':'growth_margin5','n':5,'score':'r63','filter':'growth_margin'}
assert len(cfg['retention_variants'])==3
rep=json.loads((O/'archive_reproduction.json').read_text());assert not rep['pit_certified'];assert all(abs(x['difference'])<1e-7 for x in rep['checks'].values())
for r in rep['original_inputs']:assert hashlib.sha256((R/r['path']).read_bytes()).hexdigest()==r['sha256']
m=pd.read_csv(O/'portfolio_comparison.csv');n=pd.read_csv(O/'daily_nav.csv');a=pd.read_csv(O/'signal_audit.csv.gz');q=pd.read_csv(O/'signal_audit.csv');t=pd.read_csv(O/'trade_execution_audit.csv');p=pd.read_csv(O/'position_pnl.csv');ac=pd.read_csv(O/'accounting_checks.csv');mo=pd.read_csv(O/'monthly_performance.csv')
assert len(m)==15 and len(ac)==15 and ac.max_cash_nav_residual_dollars.max()<1e-6
assert m[m.experiment=='B_2026_YTD'].cagr_pct.isna().all()
assert len(q)==1638 and (q.fact_status=='VERIFIED_SAME_ACCESSION_QUARTER').all() and q.publication_before_signal.all()
assert t.signal_before_execution.all()
evidence=json.load(gzip.open(O/'sec_minimal_evidence.json.gz','rt'));index={(x['ticker'],x['signal_date'],x['concept'],x['accession'],x['period_end']):x for x in evidence}
for r in a[a.fact_status=='VERIFIED_SAME_ACCESSION_QUARTER'].itertuples():
 x=index[r.ticker,r.signal_date,r.concept,r.accession,r.period_end]
 assert pd.Timestamp(x['sec_accepted_at'])<pd.Timestamp(r.signal_timestamp)
 assert any(v['accn']==r.accession and v['end']==r.period_end and abs(v['val']-r.used_value)<=max(.01,abs(r.used_value)*1e-9) and (r.concept!='OperatingIncome' or v['tag']=='OperatingIncomeLoss') for v in x['direct_quarter_facts'])
for r in m.itertuples():
 g=n[(n.experiment==r.experiment)&(n.policy==r.policy)];assert g.date.iloc[0]==r.start and g.date.iloc[-1]==r.end and len(g)==r.elapsed_trading_sessions
 assert abs((g.equity.iloc[-1]/10000-1)*100-r.return_pct)<1e-8
 dd=g.equity.to_numpy()/np.maximum.accumulate(np.r_[10000.,g.equity.to_numpy()])[1:]-1;assert abs(dd.min()*100-r.max_drawdown_pct)<1e-8
 z=p[(p.experiment==r.experiment)&(p.policy==r.policy)&(p.date==r.end)];assert abs(z.total_profit_contribution.sum()-(r.ending_nav-10000))<1e-6
 months=mo[(mo.experiment==r.experiment)&(mo.policy==r.policy)];assert abs(np.prod(1+months.return_pct/100)*10000-r.ending_nav)<1e-6
 assert g.cash.min()>=-1e-6
part=pd.read_csv(O/'partial_reconstruction_results.csv');orig=m[m.policy=='original'];assert np.allclose(part.return_pct.to_numpy(),orig.return_pct.to_numpy(),rtol=0,atol=1e-8)
summary={'status':'PASS_OFFLINE_INTEGRITY_NOT_PIT_CERTIFICATION','archive_metrics':6,'reconciled_baseline_accounts':15,'verified_minimal_source_input_uses':len(a[a.fact_status=='VERIFIED_SAME_ACCESSION_QUARTER']),'qualified_input_uses':len(q),'pit_certified':False,'engine_hashes_unchanged':True,'monthly_compounding_reconciles':True,'ytd_not_annualized':True}
(O/'verification_results.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary))
