#!/usr/bin/env python3
import ast, bisect, json, math, time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
import pandas as pd
import requests
import adaptive_entry_policy_backtest as b

ROOT=Path(__file__).resolve().parents[1]
OUTJ=ROOT/'backtests/results/spy_sector_hierarchy_2022_2026.json'
OUTM=ROOT/'backtests/results/spy_sector_hierarchy_2022_2026.md'
PIT_CACHE=ROOT/'.backtest_cache'/'pit_sector_monthly'
PIT_CACHE.mkdir(parents=True,exist_ok=True)

SECTOR_ETFS={
 'Materials':'XLB','Communication Services':'XLC','Energy':'XLE','Financials':'XLF',
 'Industrials':'XLI','Information Technology':'XLK','Consumer Staples':'XLP',
 'Real Estate':'XLRE','Utilities':'XLU','Health Care':'XLV','Consumer Discretionary':'XLY'
}
WIKI_API='https://en.wikipedia.org/w/api.php'

def norm(v):
    s=str(v or '').strip().upper()
    return '' if not s or s=='NAN' else s.replace('.','-')

PIT_PARQUET_URL='https://raw.githubusercontent.com/dackclup/quantrank/main/data/historical_sector.parquet'

def load_pit_sector_history(session):
    p=PIT_CACHE/'historical_sector.parquet'
    if not p.exists():
        r=session.get(PIT_PARQUET_URL,timeout=90)
        r.raise_for_status()
        p.write_bytes(r.content)
    df=pd.read_parquet(p)
    df['rebalance_date']=df['rebalance_date'].astype(str)
    return df

def pit_sector_snapshot(history,d):
    ds=history.loc[history['rebalance_date']<=d.isoformat(),'rebalance_date']
    if ds.empty:
        raise RuntimeError(f'No PIT sector snapshot on/before {d}')
    rd=ds.max()
    sub=history.loc[history['rebalance_date']==rd]
    sectors={norm(r.ticker):str(r.sector).strip() for r in sub.itertuples(index=False)}
    ts=''
    if 'revision_timestamp' in sub.columns and not sub.empty:
        ts=str(sub.iloc[0].get('revision_timestamp') or '')
    return {'date':d.isoformat(),'rebalance_date':rd,'revision_timestamp':ts,'sectors':sectors}

def signal_snapshot_pit(d,members,markets,pits,sector_map,cikmap):
    data={}; issuer_caps=defaultdict(list)
    for sym in members:
        m=markets.get(sym); pit=pits.get(sym)
        if not m or not pit: continue
        ind=b.indicators(m,d)
        if not ind: continue
        sec=sector_map.get(sym,'')
        fp=b.fundamental_pass(pit,d,sec)
        sh=b.shares_asof(pit,d)
        cap=sh*ind['close'] if sh and ind['close'] else None
        rec=dict(ind); rec.update({'fund':fp,'cap':cap,'cik':cikmap.get(sym),'sector':sec})
        data[sym]=rec
        if cap and cap>0 and cikmap.get(sym): issuer_caps[cikmap[sym]].append((cap,sym))
    rankable=[(s,r) for s,r in data.items() if r['fund'] is True and r['mom']>0]
    rankable.sort(key=lambda z:(z[1]['mom'],z[1]['adv63'],z[0]),reverse=True)
    ranks={s:i+1 for i,(s,_) in enumerate(rankable)}
    for s in data: data[s]['rank']=ranks.get(s)
    issuers=[]
    for cik,vals in issuer_caps.items():
        cap=max(x[0] for x in vals)
        reps=sorted(vals,key=lambda x:(data[x[1]]['adv63'],x[1]),reverse=True)
        issuers.append((cap,reps[0][1],cik))
    issuers.sort(reverse=True)
    leadership=[]
    for cap,sym,cik in issuers[:15]:
        r=data.get(sym)
        if r and r['fund'] is True and r['mom']>0 and r.get('rank') and r['rank']<=100 and r['r126']>0 and r['above_ema200']:
            leadership.append(sym)
    return data,leadership[:b.LEAD_MAX]

def sector_signal(markets,d):
    rows=[]
    for sec,t in SECTOR_ETFS.items():
        m=markets.get(t)
        if not m: continue
        ind=b.indicators(m,d)
        if not ind: continue
        rows.append({'sector':sec,'ticker':t,'mom':ind['mom'],'above_ema200':ind['above_ema200'],
                     'r63':ind['r63'],'r126':ind['r126'],'r252':ind['r252']})
    rows.sort(key=lambda x:(x['mom'],x['sector']),reverse=True)
    for i,r in enumerate(rows,1):
        r['sector_rank']=i
        r['sector_bull']=bool(r['mom']>0 and r['above_ema200'])
    return rows

def allowed_sectors(secrows,spy_bull,mode,bear_topk=None):
    bulls=[r for r in secrows if r['sector_bull']]
    if mode=='control':
        return set(SECTOR_ETFS) if spy_bull else set()
    if mode=='bear_exception':
        if spy_bull: return set(SECTOR_ETFS)
        if bear_topk is None: return {r['sector'] for r in bulls}
        return {r['sector'] for r in bulls[:bear_topk]}
    if mode=='full_hierarchy':
        if spy_bull: return {r['sector'] for r in bulls}
        if bear_topk is None: return {r['sector'] for r in bulls}
        return {r['sector'] for r in bulls[:bear_topk]}
    raise ValueError(mode)

def selection_plan(st,snap,leadership,allowed,spy_bull,mode):
    if mode=='control':
        return b.retained_or_targets(st,snap,leadership,spy_bull)

    sells={}; rot_keep=[]; lead_keep=[]
    for sym in [p.symbol for p in st.pos.values() if p.sleeve=='rot']:
        pk=b.key('rot',sym); p=st.pos.get(pk); r=snap.get(sym)
        if not r: continue
        fp=r['fund']
        if fp is None: fp=p.last_fund
        else: p.last_fund=bool(fp)
        if fp is not True or r['mom']<=0 or not r.get('rank') or r['rank']>35:
            sells[pk]='ROT ELIGIBILITY/RANK EXIT'
        elif r.get('sector') not in allowed:
            sells[pk]='SECTOR BEAR/NOT ALLOWED EXIT'
        else: rot_keep.append(sym)

    lead_set=set(leadership)
    for sym in [p.symbol for p in st.pos.values() if p.sleeve=='lead']:
        pk=b.key('lead',sym); p=st.pos.get(pk); r=snap.get(sym)
        if not r: continue
        fp=r['fund']
        if fp is None: fp=p.last_fund
        else: p.last_fund=bool(fp)
        if fp is not True or sym not in lead_set:
            sells[pk]='LEADERSHIP QUALIFICATION EXIT'
        elif r.get('sector') not in allowed:
            sells[pk]='SECTOR BEAR/NOT ALLOWED EXIT'
        else: lead_keep.append(sym)

    rot_sel=list(dict.fromkeys(rot_keep))
    cands=sorted(
      [(s,r) for s,r in snap.items() if r['fund'] is True and r['mom']>0 and r.get('rank')
       and r['rank']<=20 and r.get('sector') in allowed and s not in rot_sel],
      key=lambda z:z[1]['rank'])
    for s,_ in cands:
        if len(rot_sel)>=b.ROT_MAX: break
        rot_sel.append(s)

    lead_sel=list(dict.fromkeys(lead_keep))
    for s in leadership:
        if len(lead_sel)>=b.LEAD_MAX: break
        r=snap.get(s) or {}
        if r.get('sector') in allowed and s not in lead_sel: lead_sel.append(s)
    return sells,rot_sel[:b.ROT_MAX],lead_sel[:b.LEAD_MAX]

def build_orders(st,d,snap,leadership,allowed,spy_bull,mode,markets):
    sells,rot_sel,lead_sel=selection_plan(st,snap,leadership,allowed,spy_bull,mode)
    nav=b.portfolio_nav(st,markets,d); targets={}
    for s,w in b.target_weights(rot_sel,b.ROT_BUDGET,b.ROT_MAX,snap).items():
        targets[b.key('rot',s)]=(s,'rot',w)
    for s,w in b.target_weights(lead_sel,b.LEAD_BUDGET,b.LEAD_MAX,snap).items():
        targets[b.key('lead',s)]=(s,'lead',w)
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
    return orders,rot_sel,lead_sel

def run_variant(cfg,trading_dates,signal_dates,snapshots,markets,spy):
    st=b.State(cfg['name'],False); pending={}; logs=[]; signals=set(signal_dates)
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
            buys=sorted([x for x in orders if x['kind']=='buy' and x.get('sym') not in stopped],
                        key=lambda x:(x['priority'],x['sym']))
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
        st.daily.append({'date':d.isoformat(),'nav':nav,'cash':st.cash,
                         'equity_exposure':eq/nav if nav>0 else 0.0,'positions':len(st.pos)})

        if d in signals:
            snap,leadership,secrows,pitmeta=snapshots[d]
            spy_bull=bool(b.regime(spy,d))
            allowed=allowed_sectors(secrows,spy_bull,cfg['mode'],cfg.get('bear_topk'))
            orders,rot,lead=build_orders(st,d,snap,leadership,allowed,spy_bull,cfg['mode'],markets)
            ni=bisect.bisect_right(trading_dates,d)
            if ni<len(trading_dates): pending[trading_dates[ni]]=orders
            logs.append({'date':d.isoformat(),'spy_bull':spy_bull,'allowed_sectors':sorted(allowed),
                         'sector_states':secrows,'rotational':rot,'leadership':lead,
                         'pit_sector_rebalance_date':pitmeta['rebalance_date'],'pit_revision_timestamp':pitmeta['revision_timestamp']})
    m=b.metrics(st); m['logs']=logs; return m

def main():
    cache=b.Cache(ROOT/'.backtest_cache')
    web=requests.Session(); web.headers['User-Agent']='Mozilla/5.0 S&P rotational PIT sector research'
    current,current_sectors,changes=b.sp500_history(web)
    members0=b.members_at(current,changes,date(2021,12,31))
    rel=[x for x in changes if date(2021,12,1)<=date.fromisoformat(x['date'])<=b.END]
    union=set(members0)|current
    for x in rel:
        if x['added']: union.add(x['added'])
        if x['removed']: union.add(x['removed'])

    fetchset=union|{'SPY'}|set(SECTOR_ETFS.values()); raw={}
    def fsym(sym):
        z=requests.Session(); z.headers['User-Agent']='Mozilla/5.0 S&P rotational hierarchy research'
        return sym,b.yahoo(z,cache,sym,b.DATA_START,b.DATA_END)
    with ThreadPoolExecutor(max_workers=10) as ex:
        fut=[ex.submit(fsym,x) for x in sorted(fetchset)]
        for f in as_completed(fut):
            sym,v=f.result()
            if v: raw[sym]=v
    markets={k:b.prepare_market(v) for k,v in raw.items()}; markets={k:v for k,v in markets.items() if v}
    spy=markets['SPY']

    lim=b.Limiter(7); sec=requests.Session(); sec.headers['User-Agent']='S&P rotational hierarchy research'
    cikmap=b.ticker_map(sec,cache,lim); pits={}
    for sym in sorted(union):
        cik=cikmap.get(sym)
        if cik:
            f=b.facts(sec,cache,lim,sym,cik)
            if f: pits[sym]=b.preprocess_facts(f)

    trading_dates=[date.fromisoformat(r['date']) for r in spy['rows'] if b.START<=date.fromisoformat(r['date'])<=b.END]
    pool=[date.fromisoformat(r['date']) for r in spy['rows'] if date(2021,12,1)<=date.fromisoformat(r['date'])<=b.END]
    ml={}
    for d in pool: ml[(d.year,d.month)]=d
    signal_dates=[d for d in sorted(ml.values()) if d<b.END]

    wiki=requests.Session(); wiki.headers['User-Agent']='OpenAI S&P rotational research (historical sector classification)'
    snapshots={}; coverage=[]
    for d in signal_dates:
        pit=pit_sector_snapshot(pit_history,d); sector_map=pit['sectors']
        members=b.members_at(current,changes,d)
        covered=sum(1 for s in members if s in sector_map)
        coverage.append({'date':d.isoformat(),'members':len(members),'sector_covered':covered,
                         'coverage_pct':100*covered/len(members) if members else 0,
                         'rebalance_date':pit['rebalance_date'],'revision_timestamp':pit['revision_timestamp']})
        snap,lead=signal_snapshot_pit(d,members,markets,pits,sector_map,cikmap)
        snapshots[d]=(snap,lead,sector_signal(markets,d),pit)

    cfgs=[
      {'name':'PIT frozen-like control','mode':'control'},
      {'name':'Bear exception: all BULL sectors','mode':'bear_exception','bear_topk':None},
      {'name':'Bear exception: Top-3 BULL sectors','mode':'bear_exception','bear_topk':3},
      {'name':'Bear exception: Top-2 BULL sectors','mode':'bear_exception','bear_topk':2},
      {'name':'Bear exception: Top-1 BULL sector','mode':'bear_exception','bear_topk':1},
      {'name':'Full hierarchy: sector BULL required','mode':'full_hierarchy','bear_topk':None},
      {'name':'Full hierarchy + Top-2 in SPY BEAR','mode':'full_hierarchy','bear_topk':2},
    ]
    results=[run_variant(c,trading_dates,signal_dates,snapshots,markets,spy) for c in cfgs]
    rep={'results':results,'sector_coverage':coverage,
         'rules':{
           'stock_entry':'global eligible rank <=20, positive momentum, fundamental PASS',
           'stock_retention':'eligible rank <=35',
           'leadership':'existing 25% size-first leadership sleeve',
           'sector_bull':'sector ETF momentum >0 AND sector ETF above own EMA200',
           'spy_bull':'SPY total-return series above own EMA200',
           'stops':'original 3x Wilder ATR14 ratchet retained',
           'sizing':'original inverse-percent-ATR occupied-slot sizing retained',
           'pit_sector':'nearest prior committed Wikipedia-revision PIT sector snapshot (quarterly source snapshots)'
         }}
    OUTJ.parent.mkdir(parents=True,exist_ok=True); OUTJ.write_text(json.dumps(rep,indent=2))

    lines=['# SPY + sector hierarchy backtest (2022-Sep 2026)','',
      'Pre-registered architecture test. Stock ranking, 75/25 sleeves, inverse-ATR sizing, 3x ATR stops, costs and monthly cadence are unchanged. The experiment changes only market/sector permission and replaces current-sector labels with dated point-in-time Wikipedia-revision GICS sector snapshots.','',
      'Sector BULL = sector ETF has positive 63/126/252 average total-return momentum and is above its own EMA200. SPY BULL/BEAR is evaluated independently. In the Bear-exception variants, SPY BULL leaves the frozen engine unchanged; only SPY BEAR can admit stocks from BULL sectors.','',
      '| Variant | 2022 | 2023 | 2024 | 2025 | 2026 | CAGR | Max DD | Avg exposure | Turnover | Costs |',
      '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for x in results:
        ar=x['annual_returns_pct']
        lines.append(f"| {x['name']} | {ar.get('2022',0):+.2f}% | {ar.get('2023',0):+.2f}% | {ar.get('2024',0):+.2f}% | {ar.get('2025',0):+.2f}% | {ar.get('2026',0):+.2f}% | {x['cagr_5y_convention_pct']:.2f}% | {x['max_drawdown_pct']:.2f}% | {x['avg_equity_exposure_pct']:.2f}% | {x['annualized_turnover_x']:.2f}x | ${x['costs']:,.0f} |")

    lines+=['','## Point-in-time sector coverage','',
            '| Period | Min coverage | Median coverage | Max coverage |','|---|---:|---:|---:|']
    vals=[x['coverage_pct'] for x in coverage]
    import statistics
    lines.append(f"| 2022-Sep 2026 | {min(vals):.1f}% | {statistics.median(vals):.1f}% | {max(vals):.1f}% |")

    lines+=['','## Monthly state sample: 2022-2023, Top-2 bear exception','',
            '| Month-end | SPY | Allowed sector set | Sector #1 | Sector #1 state |','|---|---|---|---|---|']
    x=next(z for z in results if z['name']=='Bear exception: Top-2 BULL sectors')
    for log in x['logs']:
        if log['date'][:4] not in ('2022','2023'): continue
        top=log['sector_states'][0] if log['sector_states'] else None
        lines.append(f"| {log['date']} | {'BULL' if log['spy_bull'] else 'BEAR'} | {', '.join(log['allowed_sectors']) or 'Cash'} | {top['sector'] if top else '-'} | {'BULL' if top and top['sector_bull'] else 'BEAR'} |")

    lines+=['','## Interpretation guardrail','',
      '- This remains the independent public-data reconstruction, not the exact frozen $19,808.08 artifact. Compare variants within this replay; do not substitute these absolute returns for the frozen 14.66% benchmark.',
      '- The SEC fundamental PASS approximation remains a known mismatch and can suppress otherwise strong stocks. Point-in-time sector classification is corrected using the nearest prior dated PIT sector snapshot, but the exact original fundamental dataset is still unavailable.'
    ]
    OUTM.write_text('\n'.join(lines)+'\n'); print(OUTM.read_text())

if __name__=='__main__': main()
