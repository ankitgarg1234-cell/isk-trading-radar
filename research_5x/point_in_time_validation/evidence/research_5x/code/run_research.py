"""Offline, research-only factors and self-financing portfolio experiments.

Inputs are never modified. No connection to a broker, database, or deployment.
All portfolio selections use features available at the preceding close and never
filter on future label availability. Corporate-action and universe limits remain.
"""
from __future__ import annotations
import ast, bisect, gzip, hashlib, json, math, sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
import numpy as np
import pandas as pd

BASE=Path(__file__).resolve().parents[2]
OUT=BASE/'research_5x/results'
REPO=BASE/'research_repository'
START='2024-01-02'; END='2026-10-01'; CAPITAL=10000.
SPINOFFS={('WDC','2025-02-24'):('SNDK',1/3),('GE','2024-04-02'):('GEV',.25),('MMM','2024-04-01'):('SOLV',.25)}
def load_gz(p):
    with gzip.open(p,'rt') as f: return json.load(f)
def membership(prices):
    # Verified rename alias: EchoStar entered as SATS on 2026-03-23 and
    # renamed ECHO effective 2026-06-24. Current-symbol reverse reconstruction
    # incorrectly left ECHO in the 2024 starting universe. Economic series
    # alias is used only after inclusion; this does not certify other aliases.
    members=set(prices['membership']['start_members'])-{'ECHO'}
    changes=[]
    for e in prices['membership']['changes']:
        r=dict(e)
        for k in ('added','removed'):
            if r.get(k)=='SATS':r[k]='ECHO'
        changes.append(r)
    return members,sorted(changes,key=lambda x:x['date'])
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def pit_store(raw):
    source=REPO/'scripts/wf3_offline_valuein.py'
    node=next(n for n in ast.parse(source.read_text()).body if isinstance(n,ast.ClassDef) and n.name=='PITFundamentals')
    def d(s):
        try:return date.fromisoformat(str(s)[:10]) if s else None
        except ValueError:return None
    def fv(v):
        try:
            x=float(v);return x if math.isfinite(x) else None
        except (ValueError,TypeError):return None
    ns={'defaultdict':defaultdict,'date':date,'timedelta':timedelta,'d':d,'fv':fv}
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec'),ns)
    return ns['PITFundamentals'](raw)
def yoy(q):
    if not q:return np.nan
    pe,v,_=q[-1]
    old=[(abs((pe-x[0]).days-365),x[1]) for x in q[:-1] if 310<=(pe-x[0]).days<=420]
    if not old:return np.nan
    b=min(old,key=lambda x:x[0])[1]
    return v/b-1 if b>0 else np.nan
def earnings(q):
    if not q:return False
    pe,v,_=q[-1]
    old=[(abs((pe-x[0]).days-365),x[1]) for x in q[:-1] if 310<=(pe-x[0]).days<=420]
    if not old:return False
    b=min(old,key=lambda x:x[0])[1]
    return bool(v>0 and (b<=0 or v/b-1>.2))
def clean(x):
    if isinstance(x,dict):return {k:clean(v) for k,v in x.items()}
    if isinstance(x,list):return [clean(v) for v in x]
    if isinstance(x,(np.integer,)):return int(x)
    if isinstance(x,(np.floating,)):return float(x) if np.isfinite(x) else None
    if isinstance(x,float) and not math.isfinite(x):return None
    return x
def dump(p,x):p.write_text(json.dumps(clean(x),indent=2,allow_nan=False))
def anniversary(ds):
    d=date.fromisoformat(ds)
    try:return d.replace(year=d.year+1)
    except ValueError:return d.replace(year=d.year+1,day=28)
def rolling_windows(c):
    ds=c.date.to_list();a=c.equity.to_numpy();rows=[]
    for i,s in enumerate(ds):
        target=anniversary(s).isoformat()
        if target>ds[-1]:continue
        j=bisect.bisect_right(ds,target)-1
        if j>i:rows.append({'start':s,'anniversary':target,'end':ds[j],'return_pct':(a[j]/a[i]-1)*100,'max_dd_pct':float(np.min(a[i:j+1]/np.maximum.accumulate(a[i:j+1])-1)*100)})
    return pd.DataFrame(rows,columns=['start','anniversary','end','return_pct','max_dd_pct'])
def stats(g):
    a=g.forward_252d.dropna()
    if len(a)==0:return {'n':0}
    return {'n':len(a),'tickers':g.ticker.nunique(),'months':g.date.nunique(),
      'mean_return_pct':a.mean()*100,'median_return_pct':a.median()*100,
      'p10_pct':a.quantile(.1)*100,'p90_pct':a.quantile(.9)*100,
      'loss_pct':(a<0).mean()*100,'loss30_pct':(a<=-.3).mean()*100,
      'doubler_pct':(a>=1).mean()*100,'fivebagger_pct':(a>=4).mean()*100,
      'false_positive_doubler_pct':(a<1).mean()*100,
      'median_stock_path_dd_pct':g.path_dd.median()*100,'p10_stock_path_dd_pct':g.path_dd.quantile(.1)*100,
      'mean_sector_date_residual_pp':g.residual.mean()*100,
      'mean_after_remove_top3_tickers_pct':g.loc[~g.ticker.isin(g.groupby('ticker').forward_252d.mean().nlargest(3).index),'forward_252d'].mean()*100}

def prepare(prices,funds,spy):
    frames={}
    for sym,obj in {**prices['market'],'SPY':spy}.items():
        f=pd.DataFrame(obj['rows']).drop_duplicates('date').sort_values('date').set_index('date')
        f=f.apply(pd.to_numeric,errors='coerce')
        f=f[(f.close>0)&(f.open>0)]
        if len(f)==0:continue
        factor=pd.Series(1.,index=f.index)
        for e in obj.get('splits',[]):factor.loc[factor.index<e['date']]*=e['numerator']/e['denominator']
        f['nominal_factor']=factor
        for k in ('open','close'):f['raw_'+k]=f[k]*factor
        f['dividend']=0.
        for e in obj.get('dividends',[]):
            if e['date'] in f.index:f.loc[e['date'],'dividend']+=float(e['amount'])*factor.loc[e['date']]
        f['split']=1.
        for e in obj.get('splits',[]):
            if e['date'] in f.index:f.loc[e['date'],'split']*=e['numerator']/e['denominator']
        for n in (21,63,126,252):f['r'+str(n)]=f.close.pct_change(n,fill_method=None)
        lr=np.log(f.close).diff()
        for n in (21,63,126):f['vol'+str(n)]=lr.rolling(n).std()*np.sqrt(252)
        f['compression']=f.vol21/f.vol126
        f['ema200']=f.close.ewm(span=200,adjust=False,min_periods=200).mean()
        f['ema50']=f.close.ewm(span=50,adjust=False,min_periods=50).mean()
        f['adv20']=(f.close*f.volume).rolling(20).mean()
        f['vol_ratio']=f.volume.rolling(21).mean()/f.volume.rolling(63).mean()
        flow=(2*f.close-f.high-f.low)/(f.high-f.low).replace(0,np.nan)
        f['cmf63']=(flow*f.volume).rolling(63).sum()/f.volume.rolling(63).sum()
        f['illiquidity63']=(f.close.pct_change().abs()/(f.close*f.volume).replace(0,np.nan)).rolling(63).mean()
        f['acceleration']=f.r21-f.r63/3
        frames[sym]=f
    store=pit_store(funds)
    dates=[s for s in spy['rows'] if START<=s['date']<=END]
    calendar=[s['date'] for s in dates]
    months={}
    for ds in calendar:months[ds[:7]]=ds
    # Last partial month is not a valid month-end signal.
    monthly=[ds for ds in months.values() if ds<END]
    members,changes=membership(prices);j=0
    allrows=[]
    for ds in monthly:
        while j<len(changes) and changes[j]['date']<=ds:
            e=changes[j];members.discard(e.get('removed'));members.add(e.get('added'));j+=1
        asof=date.fromisoformat(ds)-timedelta(days=1)
        part=[]
        for sym in sorted(members&frames.keys()):
            f=frames[sym]
            if ds not in f.index:continue
            r=f.loc[ds]
            if pd.isna(r.r126) or r.adv20<10000000 or r.raw_close<5:continue
            i=f.index.get_loc(ds);row={'date':ds,'ticker':sym,'sector':prices['membership']['sectors'].get(sym,'Unknown')}
            for k in ('r21','r63','r126','r252','vol21','vol63','vol126','compression','adv20','vol_ratio','cmf63','illiquidity63','acceleration'):row[k]=r[k]
            row['above200']=bool(r.close>r.ema200);row['above50']=bool(r.close>r.ema50)
            row['momentum_multi']=np.nanmean([r.r63,r.r126,r.r252])
            row['rel_spy63']=r.r63-frames['SPY'].loc[ds,'r63']
            market=frames['SPY'];bi=market.index.get_loc(ds)
            row['regime']='risk_on' if bi>=199 and market.loc[ds,'close']>market.close.iloc[bi-199:bi+1].mean() else 'risk_off'
            qr=store.quarter(sym,'TotalRevenue',asof);qi=store.quarter(sym,'NetIncome',asof);qo=store.quarter(sym,'OperatingIncome',asof)
            if qr and (asof-qr[-1][2]['_filing_date']).days>210:qr=[]
            if qi and (asof-qi[-1][2]['_filing_date']).days>210:qi=[]
            row['revenue_yoy']=yoy(qr);row['revenue_acceleration']=yoy(qr)-yoy(qr[:-1]) if len(qr)>1 else np.nan
            row['earnings_improvement']=earnings(qi);row['earnings_reported']=bool(qi) and not pd.isna(yoy(qi))
            row['margin_delta_pp']=np.nan;row['operating_leverage']=np.nan
            if qr and qo:
                rev={e[0]:e[1] for e in qr};op={e[0]:e[1] for e in qo};pe=qr[-1][0]
                old=[s for s in rev if 310<=(pe-s).days<=420]
                if old:
                    s=min(old,key=lambda z:abs((pe-z).days-365))
                    if pe in op and s in op and rev[pe]>0 and rev[s]>0:
                        row['margin_delta_pp']=100*(op[pe]/rev[pe]-op[s]/rev[s])
                        salesgrowth=rev[pe]/rev[s]-1
                        if op[s]>0 and salesgrowth>.05:
                            row['operating_leverage']=(op[pe]/op[s]-1)/salesgrowth
            shares=store.instant(sym,'CommonSharesOutstanding',asof)
            sharefacts=[e for e in store.eligible(sym,'CommonSharesOutstanding',asof) if e['_period_end'] and e.get('numeric_value') is not None]
            if shares and sharefacts:
                sr=max(sharefacts,key=lambda e:(e['_period_end'],e['_filing_date'],str(e.get('accepted_at') or '')))
                for event in prices['market'][sym].get('splits',[]):
                    ratio=event['numerator']/event['denominator']
                    ordinary=abs(ratio-round(ratio))<1e-6 or abs(1/ratio-round(1/ratio))<1e-6 or ratio==1.5
                    if ordinary and sr['_period_end'].isoformat()<event['date']<=ds:shares*=ratio
            row['marketcap_proxy']=shares*r.raw_close if shares and shares>0 else np.nan
            ani=store.annual(sym,'NetIncome',asof)
            row['earnings_yield_proxy']=ani[-1][1]/row['marketcap_proxy'] if ani and row['marketcap_proxy']>0 and ani[-1][1]>0 else np.nan
            row['annual_earnings_growth']=ani[-1][1]/ani[-2][1]-1 if len(ani)>1 and ani[-2][1]>0 else np.nan
            row['forward_252d']=np.nan;row['label_end']=None;row['path_dd']=np.nan;row['path_min_return']=np.nan
            if i+252<len(f):
                path=f.close.iloc[i:i+253].to_numpy();row['forward_252d']=path[-1]/path[0]-1
                row['label_end']=f.index[i+252];row['path_dd']=np.min(path/np.maximum.accumulate(path)-1);row['path_min_return']=np.min(path/path[0]-1)
            part.append(row)
        g=pd.DataFrame(part)
        if len(g):
            g['mom_pct']=g.r63.rank(pct=True);g['sector_mom_pct']=g.groupby('sector').r63.rank(pct=True)
            g['size_pct']=g.marketcap_proxy.rank(pct=True)
            allrows.extend(g.to_dict('records'))
    panel=pd.DataFrame(allrows)
    panel['residual']=panel.forward_252d-panel.groupby(['date','sector']).forward_252d.transform('mean')
    panel['V']=panel.vol63>.5;panel['M']=panel.mom_pct>=.8;panel['G']=panel.revenue_yoy>.2;panel['E']=panel.earnings_improvement
    return frames,panel,calendar

def factor_research(panel):
    p=panel[panel.forward_252d.notna()].copy()
    masks={'All':pd.Series(True,index=p.index),'V':p.V,'M':p.M,'G':p.G,'E':p.E,
      'VM':p.V&p.M,'VMG':p.V&p.M&p.G,'VME':p.V&p.M&p.E,'VMGE':p.V&p.M&p.G&p.E,
      'MG':p.M&p.G,'M_margin':p.M&(p.margin_delta_pp>2),'VMGE_margin':p.V&p.M&p.G&p.E&(p.margin_delta_pp>2),
      'M_compression':p.M&(p.compression<.7),'M_revenue_acceleration':p.M&(p.revenue_acceleration>.1),
      'M_operating_leverage':p.M&(p.operating_leverage>1),'M_volume_accumulation':p.M&(p.cmf63>0)&(p.vol_ratio>1.2),
      'M_trend':p.M&p.above200,'early_recovery':(p.r21>0)&(p.r126<0)&p.above50,
      'M_positive_earnings_yield3':p.M&(p.earnings_yield_proxy>.03),
      'late_momentum':p.M&(p.r126>.5),'sector_leader':p.sector_mom_pct>=.9}
    records=[]
    for n,m in masks.items():
        records.append({'screen':n,**stats(p[m])})
        for y,g in p[m].groupby(p.date.str[:4]):records.append({'screen':n,'year':y,**stats(g)})
    pd.DataFrame(records).to_csv(OUT/'factor_results.csv',index=False)
    by=defaultdict(dict)
    for n,m in masks.items():
        by[n]['sector']={k:stats(g) for k,g in p[m].groupby('sector')}
        by[n]['regime']={k:stats(g) for k,g in p[m].groupby('regime')}
        by[n]['size']={k:stats(g) for k,g in p[m].assign(size_bucket=pd.cut(p[m].size_pct,[0,.25,.5,.75,1],labels=['small','mid-small','mid-large','large'])).groupby('size_bucket',observed=True)}
    dump(OUT/'factor_controls.json',dict(by))
    # Month block uncertainty: conservative 12-month moving blocks across cohort means.
    rng=np.random.default_rng(51010);uncertainty=[]
    for n,m in masks.items():
        a=p[m].groupby('date').forward_252d.mean().to_numpy()
        if len(a)<12:continue
        samples=[]
        for _ in range(1000):
            sample=np.concatenate([a[k:k+12] for k in rng.integers(0,len(a)-11,size=math.ceil(len(a)/12))])[:len(a)]
            samples.append(sample.mean())
        uncertainty.append({'screen':n,'cohort_months':len(a),'equal_month_mean_pct':a.mean()*100,'block12_ci_low_pct':np.quantile(samples,.025)*100,'block12_ci_high_pct':np.quantile(samples,.975)*100})
    pd.DataFrame(uncertainty).to_csv(OUT/'factor_block_uncertainty.csv',index=False)
    # Matured-label folds, with exact observed 252-session label ends + 20 SPY sessions.
    spy_dates=sorted(panel.date.unique())
    folds=[]
    for test_start,test_end in [('2025-01-01','2025-06-30'),('2025-07-01','2025-08-31')]:
        # Twenty sessions is conservatively approximated by 35 calendar days here.
        train=p[(pd.to_datetime(p.label_end)+pd.Timedelta(days=35)<pd.Timestamp(test_start))]
        test=p[(p.date>=test_start)&(p.date<=test_end)]
        eligible=[]
        for n,m in masks.items():
            g=train.loc[m.reindex(train.index,fill_value=False)]
            if len(g)>=50 and g.date.nunique()>=3 and g.ticker.nunique()>=10:
                score=g.groupby('date').forward_252d.mean().mean()-.5*(g.forward_252d<0).mean()
                eligible.append((score,n))
        selected=max(eligible)[1] if eligible else None
        folds.append({'test_start':test_start,'test_end':test_end,'train_rows':len(train),'train_months':train.date.nunique(),'selected':selected,'selected_test':stats(test[masks[selected].reindex(test.index,fill_value=False)]) if selected else None,'status':'research pseudo-OOS; thresholds proposed after historical research; tiny training history' if selected else 'no eligible mature training history'})
    dump(OUT/'purged_folds.json',folds)

CONFIGS=[
 {'name':'momentum10_monthly','n':10,'score':'r63','filter':'all'},
 {'name':'multihorizon10_monthly','n':10,'score':'momentum_multi','filter':'all'},
 {'name':'momentum3_concentrated','n':3,'score':'r63','filter':'all'},
 {'name':'vol_momentum10','n':10,'score':'r63','filter':'V'},
 {'name':'fourfactor5','n':5,'score':'r63','filter':'VMGE'},
 {'name':'growth_momentum10','n':10,'score':'r63','filter':'MG'},
 {'name':'momentum10_inverse_vol','n':10,'score':'r63','filter':'all','inverse_vol':True},
 {'name':'momentum10_quarterly','n':10,'score':'r63','filter':'all','quarterly':True},
 {'name':'sticky_winners10','n':10,'score':'momentum_multi','filter':'all','sticky':True},
 {'name':'momentum10_regime','n':10,'score':'r63','filter':'all','regime':True},
 {'name':'momentum10_sector_cap','n':10,'score':'r63','filter':'all','sector_cap':.3},
 {'name':'compression_momentum10','n':10,'score':'r63','filter':'compression'},
 {'name':'momentum1_extreme','n':1,'score':'r63','filter':'all'},
 {'name':'growth_margin5','n':5,'score':'r63','filter':'growth_margin'},
 {'name':'momentum10_annual_hold','n':10,'score':'r63','filter':'all','annual':True},
 {'name':'sticky_winners3','n':3,'score':'r63','filter':'all','sticky':True},
]
def simulate(cfg,frames,panel,calendar,start=START,end=END,cost_bps=20.,exclude=()):
    cash=CAPITAL;held={};ledger=[];curve=[];signals=[];pending=None;cum_cost=0.;pnl=defaultdict(float);basis={};notional_sum=0.;stale=0;max_participation=0.;spin_sales={};events=[]
    monthg={ds:g.set_index('ticker') for ds,g in panel.groupby('date')}
    membership_actions=defaultdict(list)
    raw=load_gz(REPO/'backtests/staged/wf3_prices.json.gz')
    for e in membership(raw)[1]:membership_actions[e['date']].append(e)
    def mark(sym,ds,key='raw_close'):
        f=frames[sym]
        if ds in f.index:return float(f.loc[ds,key])
        z=f.loc[f.index<ds]
        return float(z.iloc[-1][key]) if len(z) else None
    def trade(sym,qty,ds,side):
        nonlocal cash,cum_cost,notional_sum,max_participation
        if qty<=0 or ds not in frames[sym].index:return
        px=float(frames[sym].loc[ds,'raw_open']);gross=qty*px;cost=gross*cost_bps/10000
        # cost_bps includes fee and adverse slippage, charged on both sides.
        if side=='BUY':
            qty=min(qty,math.floor(max(0,cash)/(px*(1+cost_bps/10000))))
            if qty<=0:return
            gross=qty*px;cost=gross*cost_bps/10000;cash-=gross+cost
            held[sym]=held.get(sym,0)+qty;basis[sym]=basis.get(sym,0)+gross+cost
        else:
            qty=min(qty,held.get(sym,0));gross=qty*px;cost=gross*cost_bps/10000
            oldqty=held[sym];oldbasis=basis[sym]*qty/oldqty
            cash+=gross-cost;pnl[sym]+=gross-cost-oldbasis;held[sym]-=qty;basis[sym]-=oldbasis
            if held[sym]<1e-9:held.pop(sym);basis.pop(sym,None)
        cum_cost+=cost;notional_sum+=gross
        adv=float(frames[sym].loc[ds,'adv20']);max_participation=max(max_participation,gross/adv if adv>0 else 0)
        ledger.append({'date':ds,'ticker':sym,'side':side,'shares':qty,'nominal_open':px,'gross':gross,'cost':cost,'cash_after':cash})
    for ds in [d for d in calendar if start<=d<=end]:
        # Corporate events occur before ex-date open, with synthetic nonstandard
        # ratios retained as supplied. Spinoff consideration is NOT certified.
        for sym in list(held):
            if ds in frames[sym].index:
                r=frames[sym].loc[ds]
                if (sym,ds) in SPINOFFS:
                    # Source-confirmed spinoffs preserve parent shares and
                    # distribute child shares. Allocate basis at ex-date
                    # observed values; sell child next available open.
                    child,ratio=SPINOFFS[(sym,ds)]
                    childqty=held[sym]*ratio;parentvalue=held[sym]*float(r.raw_close)
                    childvalue=childqty*mark(child,ds)
                    childbasis=basis[sym]*childvalue/(parentvalue+childvalue)
                    basis[sym]-=childbasis;basis[child]=basis.get(child,0)+childbasis
                    held[child]=held.get(child,0)+childqty
                    spin_sales[child]=ds
                    events.append({'date':ds,'parent':sym,'parent_shares':held[sym],'child':child,'child_shares':childqty,'basis_to_child':childbasis,'policy':'sell next available session open; fractional entitlement approximation'})
                else:held[sym]*=float(r.split)
                div=held[sym]*float(r.dividend);cash+=div;pnl[sym]+=div
            else:stale+=1
        for child,eventdate in list(spin_sales.items()):
            if ds>eventdate and child in held and ds in frames[child].index:
                trade(child,held[child],ds,'SELL');spin_sales.pop(child)
        if pending:
            cfg_targets,weights,sticky=pending;pending=None
            eq_open=cash+sum(q*mark(s,ds,'raw_open') for s,q in held.items())
            if sticky:
                for s in list(held):
                    if s not in cfg_targets:trade(s,held[s],ds,'SELL')
                    elif held[s]*mark(s,ds,'raw_open')>.25*eq_open:trade(s,max(0,held[s]-math.floor(.25*eq_open/mark(s,ds,'raw_open'))),ds,'SELL')
                empty=[s for s in cfg_targets if s not in held]
                budget=min(cash,eq_open*len(empty)*min(.25,1/cfg['n']))
                for s in empty:trade(s,math.floor(budget/max(1,len(empty))/mark(s,ds,'raw_open')/(1+cost_bps/10000)),ds,'BUY')
            else:
                desired={s:math.floor(eq_open*w/mark(s,ds,'raw_open')/(1+cost_bps/10000)) for s,w in zip(cfg_targets,weights)}
                for s in list(held):
                    if held[s]>desired.get(s,0):trade(s,held[s]-desired.get(s,0),ds,'SELL')
                for s in cfg_targets:
                    if desired[s]>held.get(s,0):trade(s,desired[s]-held.get(s,0),ds,'BUY')
        # Membership removals are known by their effective dates, exit next open.
        removed=[e['removed'] for e in membership_actions.get(ds,[]) if e.get('removed') in held]
        if removed:
            for s in removed:trade(s,held[s],ds,'SELL')
        eq=cash+sum(q*mark(s,ds) for s,q in held.items())
        if cash < -.00001:raise AssertionError('Negative cash')
        curve.append({'date':ds,'equity':eq,'cash':cash,'exposure':1-cash/eq,'positions':len(held),'cumulative_cost':cum_cost})
        if ds in monthg:
            g=monthg[ds].copy();g=g[~g.index.isin(exclude)]
            g=g[g[cfg['score']].notna() & (g[cfg['score']]>0)]
            if cfg['filter']=='V':g=g[g.V]
            elif cfg['filter']=='VMGE':g=g[g.V&g.M&g.G&g.E]
            elif cfg['filter']=='MG':g=g[g.M&g.G]
            elif cfg['filter']=='compression':g=g[g.M&(g.compression<.7)]
            elif cfg['filter']=='growth_margin':g=g[g.G&g.E&(g.margin_delta_pp>3)]
            if cfg.get('quarterly') and int(ds[5:7]) not in (3,6,9,12):continue
            if cfg.get('annual') and int(ds[5:7])!=1:continue
            ranked=g.sort_values([cfg['score']],ascending=False,kind='stable')
            targets=[]
            if cfg.get('sticky'):
                ranks={s:i+1 for i,s in enumerate(ranked.index)}
                targets=[s for s in held if ranks.get(s,999)<=35]
                targets+= [s for s in list(ranked.index)[:20] if s not in targets][:max(0,cfg['n']-len(targets))]
            else:
                sectors=defaultdict(int)
                for s,r in ranked.iterrows():
                    if cfg.get('sector_cap') and sectors[r.sector]>=round(cfg['n']*cfg['sector_cap']):continue
                    targets.append(s);sectors[r.sector]+=1
                    if len(targets)>=cfg['n']:break
            if cfg.get('inverse_vol') and targets:
                w=np.array([1/max(.1,float(g.loc[s,'vol63'])) for s in targets]);w=w/w.sum()*min(1,len(targets)/cfg['n'])
            else:w=np.full(len(targets),1/cfg['n'])
            if cfg.get('regime'):
                f=frames['SPY'];i=f.index.get_loc(ds)
                # Full warmup predates investment interval in acquired SPY history.
                if i>=199 and f.loc[ds,'close']<f.close.iloc[i-199:i+1].mean():w=w*.25
            signals.append({'date':ds,'tickers':'|'.join(targets),'target_gross':float(sum(w))})
            pending=(targets,list(w),bool(cfg.get('sticky')))
    c=pd.DataFrame(curve);a=c.equity.to_numpy();dd=np.minimum(0,a/np.maximum.accumulate(np.r_[CAPITAL,a])[1:]-1)
    annual={};prev=CAPITAL
    for year,g in c.groupby(c.date.str[:4]):
        annual[year]=(g.equity.iloc[-1]/prev-1)*100;prev=g.equity.iloc[-1]
    r=rolling_windows(c)
    finalpnl=dict(pnl)
    for s,q in held.items():finalpnl[s]=finalpnl.get(s,0)+q*mark(s,c.date.iloc[-1])-basis[s]
    denom=sum(v for v in finalpnl.values() if v>0);top=sorted(finalpnl.items(),key=lambda x:x[1],reverse=True)
    result={'name':cfg['name'],'start':start,'end':end,'cost_bps_per_side':cost_bps,
      'net_return_pct':(a[-1]/CAPITAL-1)*100,'cagr_pct':((a[-1]/CAPITAL)**(365.25/(date.fromisoformat(c.date.iloc[-1])-date.fromisoformat(c.date.iloc[0])).days)-1)*100,
      'max_dd_pct':float(dd.min()*100),'annual_returns_pct':annual,'worst_complete_calendar_year_pct':min(v for k,v in annual.items() if k in ('2024','2025')) if start==START else None,
      'rolling12_max_pct':r.return_pct.max() if len(r) else None,'rolling12_median_pct':r.return_pct.median() if len(r) else None,
      'rolling12_loss_frequency_pct':(r.return_pct<0).mean()*100 if len(r) else None,'rolling12_5x_count':int((r.return_pct>=400).sum()) if len(r) else 0,
      'average_exposure_pct':c.exposure.mean()*100,'trade_count':len(ledger),'traded_notional_over_initial':notional_sum/CAPITAL,
      'annual_oneway_turnover_over_avg_equity':notional_sum/2/c.equity.mean()/((date.fromisoformat(c.date.iloc[-1])-date.fromisoformat(c.date.iloc[0])).days/365.25),
      'total_cost_dollars':cum_cost,'stale_held_marks':stale,'max_trade_adv_fraction_pct':max_participation*100,
      'top3_share_positive_pnl_pct':sum(max(v,0) for s,v in top[:3])/denom*100 if denom else None,'pnl_by_ticker':dict(top),
      'corporate_distributions':events,
      'accounting_residual_dollars':a[-1]-CAPITAL-sum(finalpnl.values())}
    return result,c,pd.DataFrame(ledger),r,pd.DataFrame(signals)

def benchmark(frames,calendar):
    f=frames['SPY'];dates=[d for d in calendar if START<=d<=END];cash=CAPITAL
    cost_bps=20.;px=f.loc[dates[0],'raw_open'];qty=math.floor(cash/px/(1+cost_bps/10000));cash-=qty*px*(1+cost_bps/10000)
    rows=[]
    for ds in dates:
        cash+=qty*f.loc[ds,'dividend'];rows.append({'date':ds,'equity':cash+qty*f.loc[ds,'raw_close'],'cash':cash})
    c=pd.DataFrame(rows);v=c.equity.to_numpy();annual={};prev=CAPITAL
    for y,g in c.groupby(c.date.str[:4]):annual[y]=(g.equity.iloc[-1]/prev-1)*100;prev=g.equity.iloc[-1]
    roll=rolling_windows(c)
    result={'name':'SPY_buy_hold_cash_dividends','net_return_pct':(v[-1]/CAPITAL-1)*100,'max_dd_pct':np.min(v/np.maximum.accumulate(np.r_[CAPITAL,v])[1:]-1)*100,'annual_returns_pct':annual,'rolling12_max_pct':roll.return_pct.max(),'rolling12_median_pct':roll.return_pct.median(),'rolling12_loss_frequency_pct':(roll.return_pct<0).mean()*100,'dividend_policy':'cash dividends, not reinvested','starting_execution':'2024-01-02 open; 20bps entry cost'}
    return result,c

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    pricepath=REPO/'backtests/staged/wf3_prices.json.gz';fundpath=REPO/'backtests/staged/wf3_valuein_fundamentals.json.gz';spypath=BASE/'research_5x/data/spy.json'
    prices=load_gz(pricepath);funds=load_gz(fundpath);spy=json.loads(spypath.read_text())
    frames,panel,calendar=prepare(prices,funds,spy);panel.to_csv(OUT/'monthly_features_labels.csv',index=False)
    print('FEATURES',len(panel),'labelled',panel.forward_252d.notna().sum(),flush=True)
    factor_research(panel)
    results=[]
    for cfg in CONFIGS:
        result,c,tr,r,signals=simulate(cfg,frames,panel,calendar)
        results.append(result);c.to_csv(OUT/(cfg['name']+'_curve.csv'),index=False);tr.to_csv(OUT/(cfg['name']+'_trades.csv'),index=False);r.to_csv(OUT/(cfg['name']+'_rolling12.csv'),index=False);signals.to_csv(OUT/(cfg['name']+'_signals.csv'),index=False)
        print('PORTFOLIO',cfg['name'],round(result['net_return_pct'],2),round(result['max_dd_pct'],2),round(result['rolling12_max_pct'],2),flush=True)
    bench,curve=benchmark(frames,calendar);curve.to_csv(OUT/'spy_curve.csv',index=False)
    # Select on 2024 ONLY; report 2025 and 2026 separately. This is reused historical
    # data, not an untouched holdout. Warm starting every fold tests entry sensitivity.
    train=[]
    for cfg in CONFIGS:
        z,*_=simulate(cfg,frames,panel,calendar,end='2024-12-31');train.append(z)
    valid=[z for z in train if z['max_dd_pct']>=-25]
    selected=max(valid,key=lambda z:z['net_return_pct']) if valid else None
    walk={'train':train,'selected_on_2024':selected,'2025_fresh_start':None,'2026_ytd_fresh_start':None,'posture':'retrospective walk-forward simulation; 2025 and 2026 have been reused by prior research'}
    if selected:
        cfg=next(c for c in CONFIGS if c['name']==selected['name'])
        walk['2025_fresh_start']=simulate(cfg,frames,panel,calendar,start='2025-01-02',end='2025-12-31')[0]
        walk['2026_ytd_fresh_start']=simulate(cfg,frames,panel,calendar,start='2026-01-02')[0]
    dump(OUT/'portfolio_results.json',{'configurations':results,'benchmark':bench,'walkforward':walk})
    # Cost and concentration stress are diagnostics, not re-selection trials.
    best=max(results,key=lambda z:z['rolling12_max_pct']);cfg=next(c for c in CONFIGS if c['name']==best['name'])
    top=list(best['pnl_by_ticker'])[:3]
    stresses=[]
    for bps in (10,50,100):stresses.append(simulate(cfg,frames,panel,calendar,cost_bps=bps)[0])
    for s in top:
        z=simulate(cfg,frames,panel,calendar,exclude=(s,))[0];z['excluded_hindsight_ticker']=s;stresses.append(z)
    weird=[s for s,x in prices['market'].items() if any(abs(e['numerator']/e['denominator']-round(e['numerator']/e['denominator']))>1e-6 and abs(1/(e['numerator']/e['denominator'])-round(1/(e['numerator']/e['denominator'])))>1e-6 and e['numerator']/e['denominator']!=1.5 for e in x.get('splits',[]))]
    z=simulate(cfg,frames,panel,calendar,exclude=weird)[0];z['excluded_hindsight_action_names']=weird;stresses.append(z)
    dump(OUT/'portfolio_stresses.json',{'candidate':best['name'],'diagnostics':stresses})
    # Leverage here is an illustrative daily reset NAV overlay, not a margin
    # account implementation or a recommendation. Apply financing to borrowed
    # exposure and scale already-costed underlying returns, with no daily hedge
    # turnover charge: this is optimistic and labelled as such.
    leverage=[]
    for cfg in [CONFIGS[0],CONFIGS[2]]:
        path=pd.read_csv(OUT/(cfg['name']+'_curve.csv'));base=np.r_[CAPITAL,path.equity.to_numpy()]
        ret=base[1:]/base[:-1]-1
        for lev in (1.5,2.):
            rv=lev*ret-(lev-1)*.06/252
            eq=CAPITAL*np.cumprod(1+rv)
            roll=rolling_windows(pd.DataFrame({'date':path.date,'equity':eq})).return_pct.to_list()
            leverage.append({'underlying':cfg['name'],'leverage':lev,'financing_pct_annual':6.,'net_overlay_return_pct':(eq[-1]/CAPITAL-1)*100,'max_dd_pct':np.min(eq/np.maximum.accumulate(np.r_[CAPITAL,eq])[1:]-1)*100,'max_rolling12_return_pct':max(roll),'rolling12_5x_count':sum(v>=400 for v in roll),'limitations':'no daily rehedge turnover, margin requirement or liquidation model; assumes financing available at 6%; optimistic mathematical overlay'})
    dump(OUT/'illustrative_leverage.json',leverage)
    dump(OUT/'manifest.json',{'research_asof':'2026-10-10','code_sha256':sha(Path(__file__)),'inputs':[{ 'path':str(p.relative_to(BASE)),'sha256':sha(p)} for p in (pricepath,fundpath,spypath)],'start':START,'end':END,'capital':CAPITAL,'configurations':CONFIGS,'fee_bps':10,'slippage_bps':10,'cash_interest':0,'leverage':1,'repairs':['ECHO excluded before2026Mar23; SATS/ECHO issuer alias mapped after index addition','WDC/GE/MMM source-confirmed spinoffs preserve parent shares, distribute children, sell next available open','sticky new holdings capped25% consistently'],'limitations':['Wikipedia-derived membership proxy, not licensed PIT membership','16 failed price tickers excluded; delisting consideration unavailable','current sector map; no PIT industry map','Valuein quarterly derived values not audited against original accession','daily bars only; no order book execution','future split factors restore nominal share units; other nonstandard action ratios are synthetic and uncertified','spinoff reconstructed nominal prices and distribution basis use cached market values, cash-in-lieu/tax details absent','dividends credited on ex-date, not payable date','stock labels exclude dividends; portfolio cash dividends included','end holdings marked, no forced terminal liquidation cost','2026 is incomplete and prior studies reused the historical test interval']})
    print('COMPLETE',flush=True)
if __name__=='__main__':main()
