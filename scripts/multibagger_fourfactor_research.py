#!/usr/bin/env python3
"""Research only: past-filed revenue/earnings plus momentum/volatility vs forward 252-session returns."""
import sys,gzip,json,math,bisect
from pathlib import Path
from datetime import date,timedelta
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from wf3_offline_valuein import PITFundamentals
OUT=ROOT/'backtests/results/fourfactor_research'
def load(path):
    with gzip.open(path,'rt') as f:return json.load(f)
def ff(x):
    try:
        a=float(x)
        return a if math.isfinite(a) else None
    except (TypeError,ValueError):return None
def getprices(src):
    rows=sorted((r['date'],ff(r.get('close'))) for r in src.get('rows',[]) if ff(r.get('close')) is not None and ff(r.get('close'))>0)
    ev=sorted((e['date'],ff(e.get('numerator'))/ff(e.get('denominator'))) for e in src.get('splits',[])
              if ff(e.get('numerator')) and ff(e.get('denominator')))
    dates=[];prices=[];fac=1.;j=0
    for dt,p in rows:
        while j<len(ev) and ev[j][0]<=dt:
            fac*=ev[j][1];j+=1
        dates.append(dt);prices.append(p*fac)
    return dates,np.asarray(prices,dtype=float)
def yoy(q):
    if not q:return (None,None,None)
    pe,val,_=q[-1]
    candidates=[(abs((pe-peold).days-365),old) for peold,old,_ in q[:-1] if 310<=(pe-peold).days<=420]
    if not candidates:return (None,val,pe)
    base=min(candidates,key=lambda t:t[0])[1]
    return ((val/base-1) if base>0 else None,val,pe)
def earn(q):
    if not q:return None
    pe,v,_=q[-1]
    candidates=[(abs((pe-peold).days-365),old) for peold,old,_ in q[:-1] if 310<=(pe-peold).days<=420]
    if not candidates:return None
    base=min(candidates,key=lambda x:x[0])[1]
    return bool(v>0 and (base<=0 or v/base-1>0.2))
def stats(z):
    if not len(z):return {'n':0}
    a=z.forward_252d
    return {'n':int(len(z)),'unique':int(z.ticker.nunique()),'doubler_pct':round(100*(a>=1).mean(),2),
    'tripler_pct':round(100*(a>=2).mean(),2),'fivebagger_pct':round(100*(a>=4).mean(),2),
    'loss30_pct':round(100*(a<=-.3).mean(),2),'median_pct':round(100*a.median(),2),
    'mean_pct':round(100*a.mean(),2),'p10_pct':round(100*a.quantile(.1),2),'p90_pct':round(100*a.quantile(.9),2)}
def main():
    p=load(ROOT/'backtests/staged/wf3_prices.json.gz')
    f=load(ROOT/'backtests/staged/wf3_valuein_fundamentals.json.gz')
    print('CACHE_COVERAGE',json.dumps({'prices':p.get('coverage'),'funds':{k:v for k,v in f['meta'].items() if k!='coverage'}}),flush=True)
    store=PITFundamentals(f)
    px={sym:getprices(src) for sym,src in p['market'].items()}
    dates=sorted(set(r['date'] for r in p['benchmark']['rows']))
    monthly={}
    for dt in dates:monthly[dt[:7]]=dt
    months=[dt for m,dt in sorted(monthly.items()) if '2024-01'<=m<='2025-08']
    members=set(p['membership']['start_members'])
    changes=sorted(p['membership']['changes'],key=lambda r:r['date'])
    j=0;panel=[]
    for dt in months:
        while j<len(changes) and changes[j]['date']<=dt:
            e=changes[j]
            if e.get('removed'):members.discard(e['removed'])
            if e.get('added'):members.add(e['added'])
            j+=1
        part=[]
        cutoff=date.fromisoformat(dt)-timedelta(days=1)
        for sym in sorted(members&px.keys()):
            day,cl=px[sym];i=bisect.bisect_left(day,dt)
            if i>=len(day) or day[i]!=dt or i<126 or i+252>=len(day):continue
            vol=float(np.std(np.diff(np.log(cl[i-63:i+1])),ddof=1)*np.sqrt(252))
            if not math.isfinite(vol):continue
            ret=float(cl[i+252]/cl[i]-1)
            qr=store.quarter(sym,'TotalRevenue',cutoff)
            qi=store.quarter(sym,'NetIncome',cutoff)
            qo=store.quarter(sym,'OperatingIncome',cutoff)
            rev,_,rpe=yoy(qr)
            eg=earn(qi)
            # Recent quarterly reports only; do not treat stale filings as active signals.
            if qr and (cutoff-qr[-1][2]['_filing_date']).days>210:rev=None
            if qi and (cutoff-qi[-1][2]['_filing_date']).days>210:eg=None
            margin=None
            if qr and qo:
                revenue=dict((e[0],e[1]) for e in qr)
                op=dict((e[0],e[1]) for e in qo)
                pe=qr[-1][0]
                previous=[s for s in revenue if 310<=(pe-s).days<=420]
                if previous:
                    old=min(previous,key=lambda z:abs((pe-z).days-365))
                    if pe in op and old in op and revenue[pe]>0 and revenue[old]>0:
                        margin=100*(op[pe]/revenue[pe]-op[old]/revenue[old])
            part.append({'date':dt,'ticker':sym,'forward_252d':ret,'vol63':vol,
            'r63':float(cl[i]/cl[i-63]-1),'r126':float(cl[i]/cl[i-126]-1),
            'revenue_yoy':rev,'earnings_improvement':eg,'operating_margin_delta_pp':margin,
            'reported_revenue':rev is not None,'reported_earnings':eg is not None})
        if part:
            df=pd.DataFrame(part)
            df['top20_mom']=df.r63.rank(pct=True)>=0.80
            panel.extend(df.to_dict('records'))
    df=pd.DataFrame(panel)
    if df.empty:raise RuntimeError('No observations; check cache start and end')
    df['growth']=df.revenue_yoy>0.20
    df['earn']=df.earnings_improvement==True
    df['vol']=df.vol63>0.50
    df['momentum']=df.top20_mom
    df['VM']=df.vol&df.momentum
    df['VMG']=df.VM&df.growth
    df['VME']=df.VM&df.earn
    df['VMGE']=df.VM&df.growth&df.earn
    df['EG']=df.growth&df.earn
    matched=df[df.reported_revenue&df.reported_earnings]
    groups={'All':df,'Both fundamentals reported':matched,
      'High volatility':df[df.vol],'Top 20% momentum':df[df.momentum],
      'V+M':df[df.VM],'V+M+Growth':df[df.VMG],
      'V+M+Earnings':df[df.VME],'V+M+Growth+Earnings':df[df.VMGE],
      'Earnings+Growth':df[df.EG],
      'V+M matched':matched[matched.VM],'V+M+G+E matched':matched[matched.VMGE]}
    byyear={}
    for y,s in df.groupby(df.date.str[:4]):
        m=s[s.reported_revenue&s.reported_earnings]
        byyear[y]={'All':stats(s),'V+M':stats(s[s.VM]),'V+M+G+E':stats(s[s.VMGE]),
        'Both fundamental observations':stats(m),'V+M matched':stats(m[m.VM])}
    snapshots={}
    for month in ['2024-05','2025-05','2024-08','2025-08']:
        s=df[df.date.str[:7]==month]
        snapshots[month]={'All':stats(s),'V+M':stats(s[s.VM]),'V+M+G+E':stats(s[s.VMGE])}
    result={'dates':[str(df.date.min()),str(df.date.max())],'total_observations':len(df),
       'unique_stocks':df.ticker.nunique(),'fundamentals_observation_coverage':{
        'revenue_yoy':int(df.reported_revenue.sum()),'net_income_yoy':int(df.reported_earnings.sum()),
        'both':int(len(matched))},'screens':{k:stats(v) for k,v in groups.items()},
        'by_start_year':byyear,'single_month_checks':snapshots,
        'caveats':['Quarterly 10-Q revenue and net income, filing-date gated one day before signal; excludes Q4-only annual filings.',
        'Earnings improvement means NI yoy >20% with positive base or profitable turnaround from nonpositive prior-year NI.',
        'Growth means revenue yoy >20%; no historical consensus estimates or earnings-surprise data.',
        'Volatility annualized 63 sessions >50%; momentum 63-day top 20% among priced eligible names.',
        'Split-adjusted Yahoo historical closes, dividends excluded; missing delisted securities, survivorship and corporate actions remain.',
        'Monthly labels overlap heavily; 2024 and 2025 outcome cohorts are highly regime-dependent.',
        'Outcomes 252 stock trading sessions forward; no investable or causal claims.']}
    OUT.mkdir(parents=True,exist_ok=True)
    df.to_csv(OUT/'fourfactor_monthly_panel.csv',index=False)
    (OUT/'fourfactor_summary.json').write_text(json.dumps(result,indent=2))
    print('FOURFACTOR_RESULTS='+json.dumps(result,separators=(',',':')),flush=True)
if __name__=='__main__':main()
