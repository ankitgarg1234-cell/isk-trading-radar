"""Outcome-blind matching and complete Phase 2 cohort preservation."""
from pathlib import Path
import hashlib, json
import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parents[1]
BASE = OUT.parent / 'phase2/2026-10-11_earnings_acceleration'

def category(r):
    if pd.isna(r): return 'censored_or_missing'
    if r >= 1: return 'exceptional'
    if r >= .30: return 'moderate'
    if r >= -.10: return 'flat_modest'
    if r <= -.30: return 'severe_loser'
    return 'material_loser'

def match(a, spec):
    pairs, unmatched = [], []
    for _, x in a.sort_values(['date','ticker']).iterrows():
        if x.sector == 'Unknown' or pd.isna(x.marketcap_proxy) or x.marketcap_proxy <= 0:
            unmatched.append({'date':x.date,'ticker':x.ticker,'specification':spec,'reason':'unknown_sector_or_size'});continue
        p = a[(a.date == x.date) & (a.sector == x.sector) & (a.ticker != x.ticker)].copy()
        p = p[p.marketcap_proxy > 0]
        p['size_gap_log2'] = abs(np.log2(p.marketcap_proxy / x.marketcap_proxy))
        p['momentum_gap'] = abs(p.r63 - x.r63)
        if spec == 'strict':
            p = p[(p.size_bucket == x.size_bucket) & (p.momentum_gap <= .20)]
        else: p = p[(p.size_gap_log2 <= 1) & (p.momentum_gap <= .30)]
        if p.empty:
            unmatched.append({'date':x.date,'ticker':x.ticker,'specification':spec,'reason':'no_other_issuer_within_predeclared_calipers'});continue
        p['distance'] = p.size_gap_log2 + p.momentum_gap / (.20 if spec == 'strict' else .30)
        p = p.sort_values(['distance','ticker'])
        for n, (_, y) in enumerate(p.iterrows()):
            pairs.append({'specification':spec,'date':x.date,'ticker':x.ticker,'peer':y.ticker,'nearest':n==0,'sector':x.sector,'size_bucket':x.size_bucket,'peer_size_bucket':y.size_bucket,'size_gap_log2':y.size_gap_log2,'momentum_gap':y.momentum_gap,'distance':y.distance,'outcome':x.outcome,'peer_outcome':y.outcome,'return':x.forward_252d,'peer_return':y.forward_252d,'return_difference':x.forward_252d-y.forward_252d,'cross_outcome':x.outcome!=y.outcome})
    return pd.DataFrame(pairs), pd.DataFrame(unmatched)

def main():
    source=OUT/'frozen_inputs/all_qualified.csv'
    a = pd.read_csv(source).sort_values(['date','ticker']).reset_index(drop=True)
    a['outcome'] = a.forward_252d.map(category)
    a['material_loss_overall'] = a.forward_252d < -.10
    a['first_observed_company_signal'] = ~a.duplicated('ticker')
    a['signal_cutoff'] = (pd.to_datetime(a.date)-pd.Timedelta(days=1)).dt.strftime('%Y-%m-%d')
    m = a[a.forward_252d.notna()].copy()
    m['earliest_mature_company_signal'] = ~m.duplicated('ticker')
    d=OUT/'accounting_quality';d.mkdir(exist_ok=True)
    a.to_csv(d/'all_qualified_with_labels.csv',index=False)
    m.to_csv(d/'mature_cohorts.csv',index=False)
    a[a.first_observed_company_signal].to_csv(d/'first_company_signals.csv',index=False)
    m[m.earliest_mature_company_signal].to_csv(d/'earliest_mature_company_signals.csv',index=False)
    stats=[]
    for name,s in [('all_mature',m),('first_observed_mature',a[a.first_observed_company_signal & a.forward_252d.notna()]),('earliest_mature_per_company',m[m.earliest_mature_company_signal])]:
        for cat,g in s.groupby('outcome'):
            stats.append({'sample':name,'outcome':cat,'observations':len(g),'issuers':g.ticker.nunique(),'signal_months':g.date.nunique(),'mean_return_pct':100*g.forward_252d.mean(),'median_return_pct':100*g.forward_252d.median(),'median_path_drawdown_pct':100*g.path_dd.median()})
    pd.DataFrame(stats).to_csv(d/'cohort_summary.csv',index=False)
    summary=[]
    for spec in ['strict','relaxed']:
        p,u=match(m,spec);p.to_csv(d/f'{spec}_eligible_pairs.csv',index=False);u.to_csv(d/f'{spec}_unmatched.csv',index=False)
        nearest=p[p.nearest];nearest.to_csv(d/f'{spec}_nearest_pairs.csv',index=False)
        # Undirected pairs are diagnostic only; issuer/date repetition persists.
        unique=nearest[nearest.ticker<nearest.peer]
        summary.append({'specification':spec,'matched_observations':len(nearest),'unmatched_observations':len(u),'matched_issuers':nearest.ticker.nunique(),'cross_outcome_nearest_rows':int(nearest.cross_outcome.sum()),'median_momentum_gap':nearest.momentum_gap.median(),'median_size_gap_log2':nearest.size_gap_log2.median(),'unique_directed_nearest_rows':len(nearest),'note':'Directed nearest pairs can reuse peers; not independent trials. Sector classifications are current proxies.'})
        first=m[m.first_observed_company_signal]
        fp,fu=match(first,spec)
        fp.to_csv(d/f'{spec}_first_company_pairs.csv',index=False)
        fu.to_csv(d/f'{spec}_first_company_unmatched.csv',index=False)
    pd.DataFrame(summary).to_csv(d/'match_summary.csv',index=False)
    inventory={'qualified':len(a),'mature':len(m),'censored':len(a)-len(m),'mature_issuers':m.ticker.nunique(),'all_issuers':a.ticker.nunique(),'first_observed_mature':int((a.first_observed_company_signal&a.forward_252d.notna()).sum()),'earliest_mature_issuers':m.ticker.nunique(),'phase2_input_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'matching_uses_outcomes':False}
    (d/'cohort_inventory.json').write_text(json.dumps(inventory,indent=2)+'\n')
    print(json.dumps(inventory));print(pd.DataFrame(summary).to_string(index=False))
if __name__=='__main__': main()
