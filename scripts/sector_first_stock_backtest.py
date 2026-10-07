#!/usr/bin/env python3
import bisect, json, math, statistics
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import adaptive_entry_policy_backtest as b

ROOT=Path(__file__).resolve().parents[1]
OUTJ=ROOT/'backtests/results/sector_first_stock_backtest.json'
OUTM=ROOT/'backtests/results/sector_first_stock_backtest.md'

SECTOR_ETFS={
 'Materials':'XLB','Communication Services':'XLC','Energy':'XLE','Financials':'XLF',
 'Industrials':'XLI','Information Technology':'XLK','Consumer Staples':'XLP',
 'Real Estate':'XLRE','Utilities':'XLU','Health Care':'XLV','Consumer Discretionary':'XLY'
}

def sector_signal(d,markets):
    rows=[]
    for sec,t in SECTOR_ETFS.items():
        m=markets.get(t)
        if not m: continue
        ind=b.indicators(m,d)
        if not ind: continue
        rows.append({'sector':sec,'ticker':t,'mom':ind['mom'],'above_ema200':ind['above_ema200'],
                     'r63':ind['r63'],'r126':ind['r126'],'r252':ind['r252']})
    rows.sort(key=lambda x:(x['mom'],x['sector']),reverse=True)
    for i,r in enumerate(rows,1): r['rank']=i
    return rows

def add_sectors(snap,sectors):
    for sym,r in snap.items(): r['sector']=sectors.get(sym,'')
    return snap

def selection_plan(st,snap,leadership,secrows,k,market_bull_required,bull):
    eligible=[x for x in secrows if x['mom']>0 and x['above_ema200']]
    entry_secs={x['sector'] for x in eligible[:k]}
    retain_secs={x['sector'] for x in eligible[:min(len(eligible),k+1)]}
    if market_bull_required and not bull:
        return {pk:'BEAR LIQUIDATION' for pk in st.pos},[],[],entry_secs,retain_secs

    sells={}; rot_keep=[]; lead_keep=[]
    for pk,p in list(st.pos.items()):
        r=snap.get(p.symbol)
        if not r:
            sells[pk]='MISSING/UNIVERSE EXIT'; continue
        fp=r['fund']
        if fp is None: fp=p.last_fund
        else: p.last_fund=bool(fp)
        if p.sleeve=='rot':
            if fp is not True or r['mom']<=0 or not r.get('rank') or r['rank']>35:
                sells[pk]='ROT ELIGIBILITY/RANK EXIT'
            elif r.get('sector') not in retain_secs:
                sells[pk]='SECTOR ROTATION EXIT'
            else: rot_keep.append(p.symbol)
        else:
            if fp is not True or p.symbol not in set(leadership):
                sells[pk]='LEADERSHIP QUALIFICATION EXIT'
            elif r.get('sector') not in retain_secs:
                sells[pk]='SECTOR ROTATION EXIT'
            else: lead_keep.append(p.symbol)

    rot_sel=list(dict.fromkeys(rot_keep))
    cands=sorted(
      [(s,r) for s,r in snap.items()
       if r['fund'] is True and r['mom']>0 and r.get('rank') and r['rank']<=20
       and r.get('sector') in entry_secs and s not in rot_sel],
      key=lambda z:z[1]['rank'])
    for s,_ in cands:
        if len(rot_sel)>=b.ROT_MAX: break
        rot_sel.append(s)

    lead_sel=list(dict.fromkeys(lead_keep))
    for s in leadership:
        if len(lead_sel)>=b.LEAD_MAX: break
        rr=snap.get(s) or {}
        if rr.get('sector') in entry_secs and s not in lead_sel:
            lead_sel.append(s)
    return sells,rot_sel[:b.ROT_MAX],lead_sel[:b.LEAD_MAX],entry_secs,retain_secs

def build_orders(st,d,snap,leadership,secrows,k,market_bull_required,bull,markets):
    sells,rot_sel,lead_sel,entry_secs,retain_secs=selection_plan(st,snap,leadership,secrows,k,market_bull_required,bull)
    nav=b.portfolio_nav(st,markets,d)
    targets={}
    for s,w in b.target_weights(rot_sel,b.ROT_BUDGET,b.ROT_MAX,snap).items(): targets[b.key('rot',s)]=(s,'rot',w)
    for s,w in b.target_weights(lead_sel,b.LEAD_BUDGET,b.LEAD_MAX,snap).items(): targets[b.key('lead',s)]=(s,'lead',w)
    orders=[]
    for pk,reason in sells.items():
        p=st.pos.get(pk)
        if p: orders.append({'kind':'sell','pk':pk,'qty':p.shares,'reason':reason,'priority':-10000})
    for pk,(s,sl,w) in targets.items():
        r=snap[s]; est=r['close']; desired=int(math.floor(nav*w/est)) if est and est>0 else 0
        cur=st.pos.get(pk).shares if pk in st.pos else 0
        if desired<cur:
            orders.append({'kind':'sell','pk':pk,'qty':cur-desired,'reason':'MONTHLY RESIZE','priority':r.get('rank') or 999})
        elif desired>cur:
            orders.append({'kind':'buy','pk':pk,'sym':s,'sleeve':sl,'qty':desired-cur,'reason':'MONTHLY TARGET',
                           'priority':r.get('rank') or 999,'atr':r.get('atr'),'fund':r.get('fund')})
    return orders,rot_sel,lead_sel,entry_secs,retain_secs

def run(name,k,market_bull_required,trading_dates,signal_dates,snapshots,markets,spy):
    st=b.State(name,False); pending={}; logs=[]; signals=set(signal_dates)
    for d in trading_dates:
        for p in list(st.pos.values()):
            m=markets.get(p.symbol)
            if not m: continue
            i=b.idx_on_or_before(m,d)
            if i is not None and m['rows'][i]['date']==d.isoformat():
                div=m['rows'][i].get('dividend') or 0.0
                if div: st.cash += p.shares*div

        for pk,p in list(st.pos.items()):
            if not p.pending_stop: continue
            m=markets.get(p.symbol)
            if not m: continue
            i=b.idx_on_or_after(m,d)
            if i is not None and m['rows'][i]['date']==d.isoformat() and m['rows'][i]['open'] is not None:
                b.execute_sell(st,pk,p.shares,m['rows'][i]['open'],d,'ATR STOP')

        if d in pending:
            orders=pending.pop(d)
            for o in [x for x in orders if x['kind']=='sell']:
                p=st.pos.get(o['pk'])
                if not p: continue
                m=markets.get(p.symbol); i=b.idx_on_or_after(m,d) if m else None
                if i is not None and m['rows'][i]['date']==d.isoformat() and m['rows'][i]['open'] is not None:
                    b.execute_sell(st,o['pk'],o['qty'],m['rows'][i]['open'],d,o['reason'])
            stopped={p.symbol for p in st.pos.values() if p.pending_stop}
            buys=sorted([x for x in orders if x['kind']=='buy' and x['sym'] not in stopped],key=lambda x:(x['priority'],x['sym']))
            for o in buys:
                m=markets.get(o['sym']); i=b.idx_on_or_after(m,d) if m else None
                if i is not None and m['rows'][i]['date']==d.isoformat() and m['rows'][i]['open'] is not None:
                    b.execute_buy(st,o['sleeve'],o['sym'],o['qty'],m['rows'][i]['open'],d,o['reason'],o.get('atr'),o.get('fund'))

        for pk,p in list(st.pos.items()):
            m=markets.get(p.symbol); i=b.idx_on_or_before(m,d) if m else None
            if i is None or m['rows'][i]['date']!=d.isoformat(): continue
            row=m['rows'][i]; c=row['close']; atr=row['atr']
            if c is None: continue
            if c<=p.stop: p.pending_stop=True
            else:
                p.high=max(p.high,c)
                if atr is not None: p.stop=max(p.stop,p.high-3.0*atr)

        nav=b.portfolio_nav(st,markets,d); eq=max(0.0,nav-st.cash)
        st.daily.append({'date':d.isoformat(),'nav':nav,'cash':st.cash,'equity_exposure':eq/nav if nav>0 else 0.0,'positions':len(st.pos)})

        if d in signals:
            snap,leadership,secrows=snapshots[d]
            bull=bool(b.regime(spy,d))
            orders,rot,lead,entry_secs,retain_secs=build_orders(st,d,snap,leadership,secrows,k,market_bull_required,bull,markets)
            ni=bisect.bisect_right(trading_dates,d)
            if ni<len(trading_dates): pending[trading_dates[ni]]=orders
            logs.append({'date':d.isoformat(),'bull':bull,'entry_sectors':sorted(entry_secs),'retain_sectors':sorted(retain_secs),
                         'rotational':rot,'leadership':lead,
                         'sector_ranking':[{'sector':x['sector'],'rank':x['rank'],'mom':x['mom'],'above_ema200':x['above_ema200']} for x in secrows]})
    m=b.metrics(st); m['logs']=logs
    return m

def main():
    cache=b.Cache(ROOT/'.backtest_cache')
    s=requests.Session(); s.headers['User-Agent']='Mozilla/5.0 sector-first stock research'
    current,sectors,changes=b.sp500_history(s)
    members0=b.members_at(current,changes,date(2021,12,31))
    rel=[x for x in changes if date(2021,12,1)<=date.fromisoformat(x['date'])<=b.END]
    union=set(members0)|current
    for x in rel:
        if x['added']: union.add(x['added'])
        if x['removed']: union.add(x['removed'])
    fetchset=union|{'SPY'}|set(SECTOR_ETFS.values())
    raw={}
    def fsym(sym):
        z=requests.Session(); z.headers['User-Agent']='Mozilla/5.0 sector-first stock research'
        return sym,b.yahoo(z,cache,sym,b.DATA_START,b.DATA_END)
    with ThreadPoolExecutor(max_workers=10) as ex:
        fut=[ex.submit(fsym,x) for x in sorted(fetchset)]
        for f in as_completed(fut):
            sym,v=f.result()
            if v: raw[sym]=v
    markets={k:b.prepare_market(v) for k,v in raw.items()}
    markets={k:v for k,v in markets.items() if v}
    spy=markets['SPY']

    lim=b.Limiter(7); ss=requests.Session(); ss.headers['User-Agent']='sector-first research'
    cikmap=b.ticker_map(ss,cache,lim); pits={}
    for sym in sorted(union):
        cik=cikmap.get(sym)
        if cik:
            f=b.facts(ss,cache,lim,sym,cik)
            if f: pits[sym]=b.preprocess_facts(f)

    trading_dates=[date.fromisoformat(r['date']) for r in spy['rows'] if b.START<=date.fromisoformat(r['date'])<=b.END]
    pool=[date.fromisoformat(r['date']) for r in spy['rows'] if date(2021,12,1)<=date.fromisoformat(r['date'])<=b.END]
    ml={}
    for d in pool: ml[(d.year,d.month)]=d
    signal_dates=[d for d in sorted(ml.values()) if d<b.END]
    snapshots={}
    for d in signal_dates:
        members=b.members_at(current,changes,d)
        snap,lead=b.signal_snapshot(d,members,markets,pits,sectors,cikmap)
        add_sectors(snap,sectors)
        snapshots[d]=(snap,lead,sector_signal(d,markets))

    cfgs=[
      ('Sector Top-2 + SPY gate',2,True),
      ('Sector Top-2, no SPY gate',2,False),
      ('Sector Top-3, no SPY gate',3,False),
      ('Sector Top-1, no SPY gate',1,False),
    ]
    results=[run(n,k,g,trading_dates,signal_dates,snapshots,markets,spy) for n,k,g in cfgs]
    rep={'results':results,'notes':{'sector_classification':'Current GICS sector labels for ticker mapping; historical membership is point-in-time but historical GICS reclassifications are not reconstructed.'}}
    OUTJ.parent.mkdir(parents=True,exist_ok=True); OUTJ.write_text(json.dumps(rep,indent=2))
    lines=['# Sector-first stock backtest','',
      'Reconstructed 75/25 stock engine with the same stock momentum, inverse-ATR sizing, 3x ATR stops, whole-share/cost assumptions and point-in-time S&P membership as the research replay. Sector leadership is measured from the 11 SPDR sector ETFs using the same 63/126/252 total-return momentum. New entries require a top-K positive-momentum sector above EMA200; incumbents get one extra sector rank of retention.','',
      '| Variant | 2022 | 2023 | 2024 | 2025 | 2026 | CAGR | Max DD | Avg exposure | Turnover |',
      '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for x in results:
        ar=x['annual_returns_pct']
        lines.append(f"| {x['name']} | {ar.get('2022',0):+.2f}% | {ar.get('2023',0):+.2f}% | {ar.get('2024',0):+.2f}% | {ar.get('2025',0):+.2f}% | {ar.get('2026',0):+.2f}% | {x['cagr_5y_convention_pct']:.2f}% | {x['max_drawdown_pct']:.2f}% | {x['avg_equity_exposure_pct']:.2f}% | {x['annualized_turnover_x']:.2f}x |")
    lines+=['','## 2022-2023 sector choices: Top-2 no SPY gate','',
            '| Month-end | Entry sectors | Top sector | Top sector momentum |','|---|---|---|---:|']
    x=next(z for z in results if z['name']=='Sector Top-2, no SPY gate')
    for log in x['logs']:
        if log['date'][:4] not in ('2022','2023'): continue
        top=log['sector_ranking'][0] if log['sector_ranking'] else None
        lines.append(f"| {log['date']} | {', '.join(log['entry_sectors']) or 'Cash'} | {top['sector'] if top else '-'} | {top['mom']*100 if top else 0:+.2f}% |")
    lines+=['','## Limitation','',
            '- This is still the independent reconstruction, not the exact frozen $19,808 artifact. Use the result for causal A/B evidence only.',
            '- Historical S&P membership is reconstructed point-in-time, but sector labels come from the current GICS mapping and therefore do not reconstruct every historical reclassification.']
    OUTM.write_text('\n'.join(lines)+'\n'); print(OUTM.read_text())

if __name__=='__main__': main()
