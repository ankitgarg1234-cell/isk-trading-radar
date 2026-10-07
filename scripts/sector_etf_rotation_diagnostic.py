#!/usr/bin/env python3
import bisect, json, math, statistics, time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1]
CACHE=ROOT/'.backtest_cache'
CACHE.mkdir(exist_ok=True)
OUTJ=ROOT/'backtests/results/sector_etf_rotation_diagnostic.json'
OUTM=ROOT/'backtests/results/sector_etf_rotation_diagnostic.md'
START=date(2022,1,3); END=date(2026,9,30); DATA_START=date(2020,1,1); DATA_END=date(2026,10,2)

SECTORS={
 'XLB':'Materials','XLC':'Communication Services','XLE':'Energy','XLF':'Financials',
 'XLI':'Industrials','XLK':'Information Technology','XLP':'Consumer Staples',
 'XLRE':'Real Estate','XLU':'Utilities','XLV':'Health Care','XLY':'Consumer Discretionary'
}
YAHOO='https://query1.finance.yahoo.com/v8/finance/chart/'

def epoch(d): return int(datetime(d.year,d.month,d.day,tzinfo=timezone.utc).timestamp())
def cache_path(sym): return CACHE/f'sector_{sym}_{DATA_START}_{DATA_END}.json'

def fetch(sym):
    p=cache_path(sym)
    if p.exists():
        return json.loads(p.read_text())
    s=requests.Session(); s.headers['User-Agent']='Mozilla/5.0 sector rotation research'
    url=YAHOO+sym
    r=s.get(url,params={'period1':epoch(DATA_START),'period2':epoch(DATA_END+timedelta(days=3)),
                        'interval':'1d','events':'div,splits'},timeout=40)
    r.raise_for_status()
    z=r.json()['chart']['result'][0]
    ts=z['timestamp']; q=z['indicators']['quote'][0]
    divmap=defaultdict(float)
    for x in (z.get('events',{}).get('dividends',{}) or {}).values():
        try: divmap[datetime.fromtimestamp(float(x['date']),tz=timezone.utc).date().isoformat()]+=float(x['amount'])
        except: pass
    rows=[]; tr=1.0; prev=None
    for i,t in enumerate(ts):
        c=(q.get('close') or [None]*len(ts))[i]
        o=(q.get('open') or [None]*len(ts))[i]
        if c is None: continue
        d=datetime.fromtimestamp(t,tz=timezone.utc).date().isoformat()
        if prev and prev>0: tr*= (float(c)+divmap.get(d,0.0))/prev
        rows.append({'date':d,'close':float(c),'open':float(o) if o is not None else None,'tr':tr})
        prev=float(c)
    out={'rows':rows,'dates':[x['date'] for x in rows]}
    p.write_text(json.dumps(out))
    return out

def idx_before(m,d):
    i=bisect.bisect_right(m['dates'],d.isoformat())-1
    return i if i>=0 else None

def ret_n(m,d,n):
    i=idx_before(m,d)
    if i is None or i<n: return None
    return m['rows'][i]['tr']/m['rows'][i-n]['tr']-1

def ema200(m,d):
    i=idx_before(m,d)
    if i is None or i<199: return None
    vals=[m['rows'][j]['tr'] for j in range(i-199,i+1)]
    e=vals[0]; a=2/201
    for v in vals[1:]: e=a*v+(1-a)*e
    return e,vals[-1]

def momentum(m,d):
    rs=[ret_n(m,d,n) for n in (63,126,252)]
    if any(x is None for x in rs): return None
    return sum(rs)/3

def signal_table(markets,d):
    rows=[]
    for t,m in markets.items():
        mom=momentum(m,d)
        e=ema200(m,d)
        if mom is None or e is None: continue
        ema,tr=e
        rows.append({'ticker':t,'sector':SECTORS[t],'mom':mom,'above_ema200':tr>ema,
                     'r63':ret_n(m,d,63),'r126':ret_n(m,d,126),'r252':ret_n(m,d,252)})
    rows.sort(key=lambda x:(x['mom'],x['ticker']),reverse=True)
    for i,r in enumerate(rows,1): r['rank']=i
    return rows

def next_date(dates,d):
    i=bisect.bisect_right(dates,d)
    return dates[i] if i<len(dates) else None

def run(markets,k,trend_filter=True):
    ref=markets['XLE']
    dates=[date.fromisoformat(x['date']) for x in ref['rows'] if START<=date.fromisoformat(x['date'])<=END]
    month_last={}
    pool=[date.fromisoformat(x['date']) for x in ref['rows'] if date(2021,12,1)<=date.fromisoformat(x['date'])<=END]
    for d in pool: month_last[(d.year,d.month)]=d
    sigs=sorted(month_last.values())
    nav=10000.0; holdings={}; cash=nav; daily=[]; logs=[]; costs=0.0
    pending={}
    for d in dates:
        # execute scheduled rebalance at next-day open, equal weight among selected.
        if d in pending:
            selected=pending.pop(d)
            # liquidate all
            for t,sh in list(holdings.items()):
                m=markets[t]; i=idx_before(m,d)
                if i is None or m['rows'][i]['date']!=d.isoformat() or m['rows'][i]['open'] is None: continue
                px=m['rows'][i]['open']*(1-0.0007)
                gross=sh*px; fee=max(1.0,0.005*sh); cash += gross-fee; costs+=fee+sh*m['rows'][i]['open']*0.0007
            holdings={}
            if selected:
                alloc=cash/len(selected)
                for t in selected:
                    m=markets[t]; i=idx_before(m,d)
                    if i is None or m['rows'][i]['date']!=d.isoformat() or m['rows'][i]['open'] is None: continue
                    px=m['rows'][i]['open']*(1+0.0007)
                    sh=int(math.floor(max(0,alloc-1)/px))
                    if sh<=0: continue
                    fee=max(1.0,0.005*sh); out=sh*px+fee
                    if out<=cash:
                        cash-=out; holdings[t]=sh; costs+=fee+sh*m['rows'][i]['open']*0.0007
        # NAV at close
        val=cash
        for t,sh in holdings.items():
            m=markets[t]; i=idx_before(m,d)
            if i is not None: val += sh*m['rows'][i]['close']
        daily.append({'date':d.isoformat(),'nav':val,'holdings':list(holdings)})
        if d in sigs and d<END:
            tab=signal_table(markets,d)
            elig=[x for x in tab if x['mom']>0 and (x['above_ema200'] or not trend_filter)]
            sel=[x['ticker'] for x in elig[:k]]
            nd=next_date(dates,d)
            if nd: pending[nd]=sel
            logs.append({'date':d.isoformat(),'selected':sel,'ranking':tab})
    # metrics
    startv=daily[0]['nav']; endv=daily[-1]['nav']
    peak=startv; mdd=0
    byyear=defaultdict(list)
    prev=startv
    annual={}
    for r in daily:
        v=r['nav']; peak=max(peak,v); mdd=min(mdd,v/peak-1); byyear[r['date'][:4]].append(v)
    for y,vals in sorted(byyear.items()):
        annual[y]=vals[-1]/prev-1
        prev=vals[-1]
    years=(date.fromisoformat(daily[-1]['date'])-date.fromisoformat(daily[0]['date'])).days/365.25
    cagr=(endv/startv)**(1/years)-1
    return {'k':k,'trend_filter':trend_filter,'end_value':endv,'cagr':cagr,'mdd':mdd,'annual':annual,'costs':costs,'logs':logs}

def oracle_next_month(markets):
    ref=markets['XLE']; pool=[date.fromisoformat(x['date']) for x in ref['rows'] if date(2021,12,1)<=date.fromisoformat(x['date'])<=date(2023,12,31)]
    month_last={}
    for d in pool: month_last[(d.year,d.month)]=d
    sigs=sorted(month_last.values())
    out=[]
    for a,b in zip(sigs[:-1],sigs[1:]):
        vals=[]
        for t,m in markets.items():
            ia=idx_before(m,a); ib=idx_before(m,b)
            if ia is None or ib is None: continue
            rr=m['rows'][ib]['tr']/m['rows'][ia]['tr']-1
            vals.append((rr,t))
        vals.sort(reverse=True)
        out.append({'signal':a.isoformat(),'next_month_end':b.isoformat(),'best_sector':SECTORS[vals[0][1]],'ticker':vals[0][1],'return':vals[0][0]})
    return out

def main():
    markets={t:fetch(t) for t in SECTORS}
    runs=[run(markets,k,True) for k in (1,2,3)]
    runs += [run(markets,k,False) for k in (1,2,3)]
    rep={'runs':runs,'oracle_2022_2023':oracle_next_month(markets)}
    OUTJ.parent.mkdir(parents=True,exist_ok=True); OUTJ.write_text(json.dumps(rep,indent=2))
    lines=['# Sector ETF momentum diagnostic','',
           'Monthly sector score = equal-weight average of 63/126/252-session total returns. Invest next session in top-K positive-momentum sectors; trend-filter variants also require sector ETF above its EMA200. Whole shares, 7 bps adverse fill per side, commission max($1,$0.005/share).','',
           '| Variant | 2022 | 2023 | 2024 | 2025 | 2026 | CAGR | Max DD | End value |',
           '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for x in runs:
        nm=f"Top-{x['k']} "+('positive + EMA200' if x['trend_filter'] else 'positive momentum only')
        ar=x['annual']
        lines.append(f"| {nm} | {ar.get('2022',0)*100:+.2f}% | {ar.get('2023',0)*100:+.2f}% | {ar.get('2024',0)*100:+.2f}% | {ar.get('2025',0)*100:+.2f}% | {ar.get('2026',0)*100:+.2f}% | {x['cagr']*100:.2f}% | {x['mdd']*100:.2f}% | USD {x['end_value']:,.2f} |")
    lines+=['','## Monthly investable sector selections in 2022-2023 (Top-3 positive + EMA200)','',
            '| Signal date | Selected sectors | Top-ranked sector | Top sector score |','|---|---|---|---:|']
    x=[z for z in runs if z['k']==3 and z['trend_filter']][0]
    for log in x['logs']:
        if log['date'][:4] not in ('2022','2023'): continue
        sels=', '.join(SECTORS[t] for t in log['selected']) or 'Cash'
        top=log['ranking'][0] if log['ranking'] else None
        lines.append(f"| {log['date']} | {sels} | {top['sector'] if top else '-'} | {top['mom']*100 if top else 0:+.2f}% |")
    lines+=['','## Hindsight ceiling: best next-month sector (NOT investable)','',
            '| Signal date | Best next-month sector | Next-month return |','|---|---|---:|']
    for o in rep['oracle_2022_2023']:
        if o['signal'][:4] in ('2022','2023'):
            lines.append(f"| {o['signal']} | {o['best_sector']} | {o['return']*100:+.2f}% |")
    OUTM.write_text('\n'.join(lines)+'\n'); print(OUTM.read_text())

if __name__=='__main__': main()
