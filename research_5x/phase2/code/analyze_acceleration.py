"""Frozen, retrospective all-panel comparisons. No trading or external writes."""
from phase2_bootstrap import e, ROOT, OUT
from datetime import datetime, timezone
import json, math
import numpy as np
import pandas as pd

P = OUT/'panel'; P.mkdir(parents=True, exist_ok=True)

def stats(g):
    x=g.forward_252d.dropna()
    if not len(x): return {'observations':len(g),'matured':0}
    return {'observations':len(g),'matured':len(x),'tickers':g.ticker.nunique(),'cohort_months':g.date.nunique(),
      'mean_pct':x.mean()*100,'median_pct':x.median()*100,'p10_pct':x.quantile(.1)*100,'p90_pct':x.quantile(.9)*100,
      'loss_pct':(x<0).mean()*100,'loss30_pct':(x<=-.3).mean()*100,'gain100_pct':(x>=1).mean()*100,
      'gain400_pct':(x>=4).mean()*100,'median_path_dd_pct':g.path_dd.median()*100,
      'mean_control_residual_pp':g.control_residual.mean()*100,
      'mean_ex_top3_pct':g.loc[~g.ticker.isin(g.groupby('ticker').forward_252d.mean().nlargest(3).index),'forward_252d'].mean()*100}

def main():
    source=ROOT/'research_5x/results/monthly_features_labels.csv'
    if not source.exists():
        import gzip
        compressed=source.with_suffix('.csv.gz')
        source.write_bytes(gzip.decompress(compressed.read_bytes()))
    p=pd.read_csv(source);prices=e.load_gz(e.REPO/'backtests/staged/wf3_prices.json.gz')
    p=p.sort_values(['ticker','date']).reset_index(drop=True)
    p['qualified']=p.G&p.E&(p.margin_delta_pp>3)&(p.r63>0)
    previous=p.groupby('ticker').qualified.shift(1)
    # An issuer's first observed month cannot establish a prior failure.
    p['fresh_qualification']=p.qualified & previous.eq(False)
    p['persistent_qualification']=p.qualified & previous.eq(True)
    p['left_censored_qualification']=p.qualified & previous.isna()
    p['size_bucket']=pd.cut(p.size_pct,[0,.25,.5,.75,1],labels=['Q1','Q2','Q3','Q4']).astype('string').fillna('missing')
    p['control_residual']=p.forward_252d-p.groupby(['date','sector','size_bucket'],observed=True).forward_252d.transform('mean')
    actions={s:[x['date'] for x in obj.get('splits',[])] for s,obj in prices['market'].items()}
    # All vendor actions flagged, including legitimate ordinary splits. Action-free is conservative.
    p['vendor_action_in_label_horizon']=[bool(pd.notna(r.label_end) and any(r.date<d<=r.label_end for d in actions.get(r.ticker,[]))) for r in p.itertuples()]
    p['label_status']=np.where(p.forward_252d.notna(),'matured_price_only','censored_or_price_missing')
    p.to_csv(P/'annotated_panel.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    valid=p[p.forward_252d.notna()].copy()
    masks={'all':pd.Series(True,index=valid.index),'qualified':valid.qualified,
      'fresh':valid.fresh_qualification,'persistent':valid.persistent_qualification,
      'qualified_revenue_acceleration_positive':valid.qualified&(valid.revenue_acceleration>0),
      'qualified_revenue_acceleration_nonpositive':valid.qualified&(valid.revenue_acceleration<=0),
      'qualified_price_acceleration_positive':valid.qualified&(valid.acceleration>0),
      'qualified_price_acceleration_nonpositive':valid.qualified&(valid.acceleration<=0),
      'qualified_volume_accumulation_positive':valid.qualified&(valid.cmf63>0),
      'qualified_volume_accumulation_nonpositive':valid.qualified&(valid.cmf63<=0),
      'qualified_relative_strength_positive':valid.qualified&(valid.rel_spy63>0),
      'qualified_relative_strength_nonpositive':valid.qualified&(valid.rel_spy63<=0)}
    results=[]
    for name,m in masks.items():
        for scope,part in [('all',valid[m]),('vendor_action_free',valid[m&~valid.vendor_action_in_label_horizon])]:
            results.append({'screen':name,'scope':scope,'stratum':'all',**stats(part)})
            if scope=='all':
                for col in ['sector','regime']:
                    for key,g in part.groupby(col):results.append({'screen':name,'scope':scope,'stratum':col+':'+str(key),**stats(g)})
                for y,g in part.groupby(part.date.str[:4]):results.append({'screen':name,'scope':scope,'stratum':'year:'+y,**stats(g)})
    pd.DataFrame(results).to_csv(P/'screen_results.csv',index=False)
    # Continuous Spearman association, no optimized cut points.
    corr=[]
    features=['revenue_yoy','revenue_acceleration','margin_delta_pp','operating_leverage','r63','r126','acceleration','compression','cmf63','rel_spy63']
    for label,g in [('all',valid),('qualified',valid[valid.qualified])]:
        for col in features:
            z=g[[col,'forward_252d','control_residual']].dropna()
            if len(z)>2:
                corr.append({'scope':label,'factor':col,'n':len(z),
                  'rank_corr_forward':z[col].rank().corr(z.forward_252d.rank()),
                  'rank_corr_control_residual':z[col].rank().corr(z.control_residual.rank())})
    pd.DataFrame(corr).to_csv(P/'continuous_correlations.csv',index=False)
    matches=[]
    selection=p[p.date.eq('2025-06-30')]
    for ticker in ['MU','STX','WDC']:
        target=selection[selection.ticker.eq(ticker)].iloc[0]
        peers=selection[(selection.sector==target.sector)&(selection.size_bucket==target.size_bucket)&selection.qualified]
        for row in peers.to_dict('records'):matches.append({'target':ticker,'is_target':row['ticker']==ticker,**row})
    pd.DataFrame(matches).to_csv(P/'matched_june2025.csv',index=False)
    q=p[p.qualified].copy();q.to_csv(P/'all_qualified.csv',index=False)
    cases=[]
    for ticker in ['MU','STX','WDC','AMD','PLTR','ANET','LRCX','ADI','LITE','SNDK']:
        g=p[p.ticker.eq(ticker)].copy();g.to_csv(P/(ticker+'_timeline.csv'),index=False)
        first=g[g.qualified].head(1)
        for row in first.to_dict('records'):cases.append({'first_observed_only':True,**row})
    pd.DataFrame(cases).to_csv(P/'first_observed_case_signals.csv',index=False)
    # Matched success/failure lists are ALL mature screen-qualified observations.
    q[q.forward_252d.notna() & (q.forward_252d<0)].sort_values(['date','ticker']).to_csv(P/'qualified_failures.csv',index=False)
    # Cohort-level 12-month moving blocks; too few blocks for reliable coverage, explicitly diagnostic.
    rng=np.random.default_rng(20261011);unc=[]
    for name,m in masks.items():
        a=valid[m].groupby('date').forward_252d.mean().to_numpy()
        if len(a)<12:continue
        boot=np.array([np.concatenate([a[k:k+12] for k in rng.integers(0,len(a)-11,size=math.ceil(len(a)/12))])[:len(a)].mean()*100 for _ in range(2000)])
        unc.append({'screen':name,'months':len(a),'block_length_months':12,'equal_month_mean_pct':a.mean()*100,
                    'diagnostic_2_5_pct':np.quantile(boot,.025),'diagnostic_97_5_pct':np.quantile(boot,.975),
                    'independent_cycle_inference':'unavailable; too few distinct cycles, biased source universe and reused history'})
    pd.DataFrame(unc).to_csv(P/'dependence_diagnostics.csv',index=False)
    e.dump(P/'inventory.json',{'generated_utc':datetime.now(timezone.utc).isoformat(),'source_sha256':e.sha(source),
      'rows':len(p),'matured':len(valid),'censored_or_missing':int(p.forward_252d.isna().sum()),'tickers':p.ticker.nunique(),
      'first_date':p.date.min(),'last_date':p.date.max(),'qualified_rows':int(p.qualified.sum()),
      'qualified_matured':int(valid.qualified.sum()),'left_censored_qualified':int(p.left_censored_qualification.sum()),
      'vendor_action_flagged_matured':int(valid.vendor_action_in_label_horizon.sum()),
      'qualified_matured_failures':int((valid.qualified&(valid.forward_252d<0)).sum()),
      'limitations':['252 sessions close price only, not annual total return','all prior source universe/fundamental/sector limitations preserved','descriptive comparisons, not untouched OOS','first observed is not first economically detectable','zero direction splits are hypotheses, not trading-rule additions']})
    print(json.dumps(json.loads((P/'inventory.json').read_text()),indent=2))
if __name__=='__main__':main()
