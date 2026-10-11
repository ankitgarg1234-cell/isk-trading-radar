"""Descriptive dependence-aware uncertainty; not future success probabilities."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
OUT=Path(__file__).resolve().parents[1]
SEED=73011
def interval(values):
    x=np.array(values);return {'mean_2_5_pct':float(np.quantile(x[:,0],.025)*100),'mean_97_5_pct':float(np.quantile(x[:,0],.975)*100),'median_2_5_pct':float(np.quantile(x[:,1],.025)*100),'median_97_5_pct':float(np.quantile(x[:,1],.975)*100)}
def main():
    a=pd.read_csv(OUT/'accounting_quality/mature_cohorts.csv');rng=np.random.default_rng(SEED);results=[]
    for name,s in [('all_mature',a),('first_company',a[a.first_observed_company_signal])]:
        blocks=[g.forward_252d.to_numpy() for _,g in s.groupby('ticker')];values=[]
        for _ in range(2000):
            r=np.concatenate([blocks[i] for i in rng.integers(len(blocks),size=len(blocks))]);values.append((r.mean(),np.median(r)))
        results.append({'sample':name,'resampling':'whole_company_with_replacement','draws':2000,'observations':len(s),'issuers':len(blocks),'point_mean_pct':s.forward_252d.mean()*100,'point_median_pct':s.forward_252d.median()*100,**interval(values)})
    dates=sorted(a.date.unique());blocks={d:a.loc[a.date==d,'forward_252d'].to_numpy() for d in dates};values=[]
    for _ in range(2000):
        idx=[]
        while len(idx)<len(dates):
            start=int(rng.integers(len(dates)));idx.extend((start+j)%len(dates) for j in range(12))
        r=np.concatenate([blocks[dates[i]] for i in idx[:len(dates)]]);values.append((r.mean(),np.median(r)))
    results.append({'sample':'all_mature','resampling':'circular_12_signal_month_blocks','draws':2000,'observations':len(a),'issuers':a.ticker.nunique(),'point_mean_pct':a.forward_252d.mean()*100,'point_median_pct':a.forward_252d.median()*100,**interval(values)})
    pd.DataFrame(results).to_csv(OUT/'accounting_quality/descriptive_uncertainty.csv',index=False)
    (OUT/'accounting_quality/uncertainty_limits.json').write_text(json.dumps({'seed':SEED,'interpretation':'Conditional descriptive bootstrap intervals only; 21 reused signal cohorts and two start years cannot estimate independent cycle uncertainty. Cross-issuer/date dependencies persist in any one resampling scheme. No future-probability or causal interpretation.','quality_incremental_tests':'not_run_until_Gate1_certification'},indent=2)+'\n')
    print(pd.DataFrame(results).to_string(index=False))
if __name__=='__main__':main()
