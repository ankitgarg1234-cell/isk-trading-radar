"""As-of cached released fundamentals; preserve actual accession and scope caveats."""
from phase2_bootstrap import e,ROOT,OUT
from datetime import date,timedelta
import pandas as pd,numpy as np,json
DEST=OUT/'panel'
def old(q):
    if not q:return None
    end=q[-1][0]
    a=[x for x in q[:-1] if 310<=(end-x[0]).days<=420]
    return min(a,key=lambda x:abs((end-x[0]).days-365)) if a else None

def main():
    p=pd.read_csv(DEST/'annotated_panel.csv.gz');store=e.pit_store(e.load_gz(e.REPO/'backtests/staged/wf3_valuein_fundamentals.json.gz'))
    issuers=set(p.loc[p.qualified,'ticker']);rows=[];facts=[]
    for r in p[p.ticker.isin(issuers)].itertuples():
        asof=date.fromisoformat(r.date)-timedelta(days=1);rec={'date':r.date,'ticker':r.ticker}
        series={k:store.quarter(r.ticker,k,asof) for k in ['TotalRevenue','OperatingIncome','NetIncome','GrossProfit']}
        for concept,q in series.items():
            if not q:continue
            end,v,f=q[-1];b=old(q)
            rec[concept+'_period_end']=end.isoformat();rec[concept+'_current']=v
            rec[concept+'_filing_date']=f['_filing_date'].isoformat();rec[concept+'_accession']=f.get('accession_id');rec[concept+'_accepted_at']=f.get('accepted_at')
            rec[concept+'_prior_year']=b[1] if b else None
            assert f['_filing_date']<=asof
            for role,item in [('current',q[-1]),('prior_year',b)]:
                if item:
                    pe,val,fact=item
                    facts.append({'date':r.date,'ticker':r.ticker,'concept':concept,'role':role,'period_end':pe.isoformat(),'value':val,
                                  'filing_date':fact['_filing_date'].isoformat(),'accession':fact.get('accession_id'),'accepted_at':fact.get('accepted_at'),
                                  'derived':not(fact.get('_span') is not None and 60<=float(fact['_span'])<=125)})
        qr=series['TotalRevenue'];qi=series['NetIncome'];qg=series['GrossProfit']
        rec['net_income_yoy']=e.yoy(qi)
        rec['net_income_yoy_acceleration']=e.yoy(qi)-e.yoy(qi[:-1]) if len(qi)>1 else np.nan
        rec['net_income_growth_base_status']='positive' if old(qi) and old(qi)[1]>0 else 'nonpositive_or_missing'
        def scaled_delta(q, rev):
            a=old(q)
            return (q[-1][1]-a[1])/rev if q and a and rev and rev>0 else np.nan
        rec['net_income_yoy_dollar_delta_over_revenue']=scaled_delta(qi,qr[-1][1] if qr and qi and qr[-1][0]==qi[-1][0] else None)
        rec['gross_margin_pct']=100*qg[-1][1]/qr[-1][1] if qg and qr and qg[-1][0]==qr[-1][0] and qr[-1][1]>0 else np.nan
        rows.append(rec)
    f=pd.DataFrame(rows);f.to_csv(DEST/'released_quarter_observables.csv',index=False)
    pd.DataFrame(facts).to_csv(DEST/'released_fact_lineage.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    merged=p.merge(f,on=['date','ticker'],how='left');cols=['net_income_yoy','net_income_yoy_acceleration','net_income_yoy_dollar_delta_over_revenue','gross_margin_pct']
    result=[]
    for name,z in [('qualified',merged[merged.qualified]),('fresh',merged[merged.fresh_qualification])]:
        for col in cols:
            g=z[[col,'forward_252d','control_residual']].dropna()
            result.append({'screen':name,'factor':col,'matured_n':len(g),'rank_corr_price_return':g[col].rank().corr(g.forward_252d.rank()),
                            'rank_corr_control_residual':g[col].rank().corr(g.control_residual.rank())})
    pd.DataFrame(result).to_csv(DEST/'earnings_continuous_correlations.csv',index=False)
    e.dump(DEST/'released_quarter_validation.json',{'pass':True,'observations':len(f),'issuers':len(issuers),'source_fact_roles':len(facts),
       'all_filing_dates_before_signal':True,'scope':'Structural eligibility only; not original-source certification except separately audited cases',
       'missing_fields':['HistoricalconsensusEPS revisions','EPS per share in cachedconcepts','CFO/FCF in cachedconcepts','PITindustry classification'],
       'limits':['NI is GAAP netincome, not adjustedEPS; losses make percent earnings growth unavailable','No recurring-income cleaning except sourcecase report','Later released comparatives admitted only after filing, but sourcevintage trust unresolved globally','10-K Q4 excluded by inheritedquarterstore','WDCscope changes contaminate cache; see sourceaudit rather than rewriting originalinputs']})
    print(pd.DataFrame(result).to_string(index=False))
if __name__=='__main__':main()
