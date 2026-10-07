#!/usr/bin/env python3
import bisect, csv, json, math
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
import requests
import adaptive_entry_policy_backtest as b

ROOT=Path(__file__).resolve().parents[1]
OUTD=ROOT/'backtests/results/energy_2022_monthly_audit.csv'
OUTS=ROOT/'backtests/results/energy_2022_monthly_summary.csv'
OUTM=ROOT/'backtests/results/energy_2022_monthly_audit.md'

def add_raw_ranks(snap):
    raw=sorted(
        [(s,r) for s,r in snap.items() if r.get('mom') is not None],
        key=lambda z:(z[1]['mom'],z[1].get('adv63') or 0,z[0]), reverse=True
    )
    raw_rank={s:i+1 for i,(s,_) in enumerate(raw)}
    energy=sorted(
        [(s,r) for s,r in snap.items() if r.get('sector')=='Energy' and r.get('mom') is not None],
        key=lambda z:(z[1]['mom'],z[1].get('adv63') or 0,z[0]), reverse=True
    )
    energy_rank={s:i+1 for i,(s,_) in enumerate(energy)}
    return raw_rank,energy_rank

def sym_weight(st,sym,markets,d,nav):
    if nav<=0: return 0.0
    v=0.0
    for p in st.pos.values():
        if p.symbol!=sym: continue
        m=markets.get(sym)
        if not m: continue
        i=b.idx_on_or_before(m,d)
        if i is not None and m['rows'][i]['close'] is not None:
            v += p.shares*m['rows'][i]['close']
    return v/nav

def target_weights(rot_sel,lead_sel,snap):
    out=defaultdict(float)
    for s,w in b.target_weights(rot_sel,b.ROT_BUDGET,b.ROT_MAX,snap).items(): out[s]+=w
    for s,w in b.target_weights(lead_sel,b.LEAD_BUDGET,b.LEAD_MAX,snap).items(): out[s]+=w
    return dict(out)

def reject_reason(sym,r,bull,owned,rot_sel,lead_sel,leadership,st):
    selected = sym in rot_sel or sym in lead_sel
    if selected:
        if sym in rot_sel and sym in lead_sel: return 'SELECTED BOTH SLEEVES'
        if sym in rot_sel: return 'SELECTED ROTATIONAL'
        return 'SELECTED LEADERSHIP'
    if not bull:
        return 'BEAR GATE: liquidate/block equity'
    if r is None:
        return 'DATA GAP: no usable snapshot'
    if r.get('fund') is not True:
        if r.get('fund') is None: return 'FUNDAMENTAL UNRESOLVED'
        return 'FUNDAMENTAL FAIL'
    if (r.get('mom') or 0)<=0:
        return 'NONPOSITIVE MOMENTUM'
    eng=r.get('rank')
    if owned:
        # If it is owned but absent from target under bull, the normal incumbent exit rules explain it.
        if eng is None: return 'INCUMBENT: NO ELIGIBLE GLOBAL RANK'
        if eng>35: return 'INCUMBENT: GLOBAL RANK >35 EXIT'
        # Could be a leadership incumbent that lost leadership qualification.
        if any(p.symbol==sym and p.sleeve=='lead' for p in st.pos.values()) and sym not in set(leadership):
            return 'LEADERSHIP QUALIFICATION EXIT'
    if eng is None:
        return 'NO ELIGIBLE GLOBAL RANK'
    if eng>20:
        return 'GLOBAL RANK >20: NOT NEW-ENTRY ELIGIBLE'
    return 'ROTATIONAL SLEEVE FULL / HIGHER-PRIORITY NAMES'

def main():
    cache=b.Cache(ROOT/'.backtest_cache')
    s=requests.Session(); s.headers['User-Agent']='Mozilla/5.0 energy audit research'
    current,sectors,changes=b.sp500_history(s)
    members0=b.members_at(current,changes,date(2021,12,31))
    rel=[x for x in changes if date(2021,12,1)<=date.fromisoformat(x['date'])<=date(2022,12,31)]
    union=set(members0)|current
    for x in rel:
        if x['added']: union.add(x['added'])
        if x['removed']: union.add(x['removed'])

    raw={}
    def fsym(sym):
        z=requests.Session(); z.headers['User-Agent']='Mozilla/5.0 energy audit research'
        return sym,b.yahoo(z,cache,sym,b.DATA_START,b.DATA_END)
    with ThreadPoolExecutor(max_workers=10) as ex:
        fut=[ex.submit(fsym,x) for x in sorted(union|{'SPY'})]
        for f in as_completed(fut):
            sym,v=f.result()
            if v: raw[sym]=v
    markets={k:b.prepare_market(v) for k,v in raw.items()}
    markets={k:v for k,v in markets.items() if v}
    spy=markets['SPY']

    lim=b.Limiter(7); ss=requests.Session(); ss.headers['User-Agent']='energy audit research'
    cikmap=b.ticker_map(ss,cache,lim); pits={}
    for sym in sorted(union):
        cik=cikmap.get(sym)
        if cik:
            f=b.facts(ss,cache,lim,sym,cik)
            if f: pits[sym]=b.preprocess_facts(f)

    trading_dates=[date.fromisoformat(r['date']) for r in spy['rows'] if date(2022,1,3)<=date.fromisoformat(r['date'])<=date(2022,12,30)]
    pool=[date.fromisoformat(r['date']) for r in spy['rows'] if date(2021,12,1)<=date.fromisoformat(r['date'])<=date(2022,12,30)]
    ml={}
    for d in pool: ml[(d.year,d.month)]=d
    signal_dates=[d for d in sorted(ml.values()) if d.year==2022]
    members_by={d:b.members_at(current,changes,d) for d in signal_dates}
    snapshots={}
    for d in signal_dates:
        snap,lead=b.signal_snapshot(d,members_by[d],markets,pits,sectors,cikmap)
        for sym,r in snap.items(): r['sector']=sectors.get(sym,'')
        snapshots[d]=(snap,lead)

    st=b.State('Frozen-like 2022 audit',False)
    pending={}
    detail=[]; summaries=[]
    signals=set(signal_dates)

    for d in trading_dates:
        # dividends
        for p in list(st.pos.values()):
            m=markets.get(p.symbol)
            if not m: continue
            i=b.idx_on_or_before(m,d)
            if i is not None and m['rows'][i]['date']==d.isoformat():
                div=m['rows'][i].get('dividend') or 0.0
                if div: st.cash += p.shares*div

        # pending stop executions
        for pk,p in list(st.pos.items()):
            if not p.pending_stop: continue
            m=markets.get(p.symbol)
            if not m: continue
            i=b.idx_on_or_after(m,d)
            if i is not None and m['rows'][i]['date']==d.isoformat() and m['rows'][i]['open'] is not None:
                b.execute_sell(st,pk,p.shares,m['rows'][i]['open'],d,'ATR STOP')

        # month-start rebalance executions
        if d in pending:
            orders=pending.pop(d)
            for o in [x for x in orders if x['kind']=='sell']:
                p=st.pos.get(o['pk'])
                if not p: continue
                m=markets.get(p.symbol); i=b.idx_on_or_after(m,d) if m else None
                if i is not None and m['rows'][i]['date']==d.isoformat() and m['rows'][i]['open'] is not None:
                    b.execute_sell(st,o['pk'],o['qty'],m['rows'][i]['open'],d,o['reason'])
            stopped={p.symbol for p in st.pos.values() if p.pending_stop}
            buys=sorted([x for x in orders if x['kind']=='buy' and x.get('sym') not in stopped],key=lambda x:(x['priority'],x['sym']))
            for o in buys:
                m=markets.get(o['sym']); i=b.idx_on_or_after(m,d) if m else None
                if i is not None and m['rows'][i]['date']==d.isoformat() and m['rows'][i]['open'] is not None:
                    b.execute_buy(st,o['sleeve'],o['sym'],o['qty'],m['rows'][i]['open'],d,o['reason'],o.get('atr'),o.get('fund'))

        # daily stop update
        for pk,p in list(st.pos.items()):
            m=markets.get(p.symbol); i=b.idx_on_or_before(m,d) if m else None
            if i is None or m['rows'][i]['date']!=d.isoformat(): continue
            row=m['rows'][i]; c=row['close']; atr=row['atr']
            if c is None: continue
            if c<=p.stop: p.pending_stop=True
            else:
                p.high=max(p.high,c)
                if atr is not None: p.stop=max(p.stop,p.high-3.0*atr)

        nav=b.portfolio_nav(st,markets,d)
        eq=max(0.0,nav-st.cash)
        st.daily.append({'date':d.isoformat(),'nav':nav,'cash':st.cash,'equity_exposure':eq/nav if nav>0 else 0.0,'positions':len(st.pos)})

        if d not in signals: continue
        snap,leadership=snapshots[d]
        bull=bool(b.regime(spy,d))
        raw_rank,energy_rank=add_raw_ranks(snap)

        # Use exact reconstructed frozen-like monthly decision logic.
        sell_keys,rot_sel,lead_sel=b.retained_or_targets(st,snap,leadership,bull)
        tw=target_weights(rot_sel,lead_sel,snap)

        energy_members=sorted([sym for sym in members_by[d] if sectors.get(sym,'')=='Energy'])
        reasons=Counter()
        selected_energy=[]
        owned_energy=[]
        owned_w=0.0; target_w=0.0
        for sym in energy_members:
            r=snap.get(sym)
            owned=any(p.symbol==sym for p in st.pos.values())
            ow=sym_weight(st,sym,markets,d,nav) if owned else 0.0
            targ=tw.get(sym,0.0)
            reason=reject_reason(sym,r,bull,owned,rot_sel,lead_sel,leadership,st)
            reasons[reason]+=1
            if owned: owned_energy.append(sym); owned_w+=ow
            if targ>0: selected_energy.append(sym); target_w+=targ
            detail.append({
                'date':d.isoformat(),'spy_bull':bull,'symbol':sym,
                'raw_global_rank':raw_rank.get(sym),'engine_eligible_rank':(r or {}).get('rank'),
                'energy_rank':energy_rank.get(sym),'momentum_pct':None if r is None else r.get('mom')*100,
                'r63_pct':None if r is None else r.get('r63')*100,
                'r126_pct':None if r is None else r.get('r126')*100,
                'r252_pct':None if r is None else r.get('r252')*100,
                'above_ema200':None if r is None else r.get('above_ema200'),
                'fundamental_pass':None if r is None else r.get('fund'),
                'owned_before_signal':owned,'portfolio_weight_pct':ow*100,
                'selected_for_next_month':targ>0,'target_weight_pct':targ*100,
                'rotational_target':sym in rot_sel,'leadership_target':sym in lead_sel,
                'rejection_or_status':reason
            })

        all_energy_snap=[(s,r) for s,r in snap.items() if r.get('sector')=='Energy']
        top20=[s for s,r in all_energy_snap if r.get('rank') and r['rank']<=20]
        rawtop20=[s for s in energy_members if raw_rank.get(s) and raw_rank[s]<=20]
        positive=[s for s,r in all_energy_snap if r.get('mom',0)>0]
        fundpass=[s for s,r in all_energy_snap if r.get('fund') is True]
        summaries.append({
            'date':d.isoformat(),'spy_bull':bull,'energy_members':len(energy_members),
            'energy_with_snapshot':len(all_energy_snap),'energy_positive_momentum':len(positive),
            'energy_fundamental_pass':len(fundpass),'energy_raw_global_top20':len(rawtop20),
            'energy_engine_top20':len(top20),'owned_energy_count':len(owned_energy),
            'owned_energy_weight_pct':owned_w*100,'target_energy_count':len(selected_energy),
            'target_energy_weight_pct':target_w*100,'owned_energy_symbols':','.join(owned_energy),
            'target_energy_symbols':','.join(selected_energy),
            'reason_counts':json.dumps(dict(reasons),sort_keys=True)
        })

        # Schedule actual reconstructed frozen-like orders using the same precomputed selection.
        targets={}
        for sym,w in b.target_weights(rot_sel,b.ROT_BUDGET,b.ROT_MAX,snap).items():
            targets[b.key('rot',sym)]=(sym,'rot',w)
        for sym,w in b.target_weights(lead_sel,b.LEAD_BUDGET,b.LEAD_MAX,snap).items():
            targets[b.key('lead',sym)]=(sym,'lead',w)
        orders=[]
        for pk,reason in sell_keys.items():
            p=st.pos.get(pk)
            if p: orders.append({'kind':'sell','pk':pk,'qty':p.shares,'reason':reason,'priority':-10000})
        for pk,(sym,sleeve,w) in targets.items():
            r=snap[sym]; est=r['close']; desired=int(math.floor(nav*w/est)) if est and est>0 else 0
            cur=st.pos.get(pk).shares if pk in st.pos else 0
            if desired<cur:
                orders.append({'kind':'sell','pk':pk,'qty':cur-desired,'reason':'MONTHLY RESIZE','priority':r.get('rank') or 999})
            elif desired>cur and bull:
                orders.append({'kind':'buy','pk':pk,'sym':sym,'sleeve':sleeve,'qty':desired-cur,'reason':'MONTHLY TARGET',
                               'priority':r.get('rank') or 999,'atr':r.get('atr'),'fund':r.get('fund')})
        stopped={p.symbol for p in st.pos.values() if p.pending_stop}
        if stopped:
            orders=[o for o in orders if not(o['kind']=='buy' and o.get('sym') in stopped)]
        ni=bisect.bisect_right(trading_dates,d)
        if ni<len(trading_dates): pending[trading_dates[ni]]=orders

    OUTD.parent.mkdir(parents=True,exist_ok=True)
    fields=list(detail[0].keys())
    with OUTD.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(detail)
    sfields=list(summaries[0].keys())
    with OUTS.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=sfields); w.writeheader(); w.writerows(summaries)

    # Aggregate diagnosis.
    agg=Counter()
    for r in detail:
        if not r['selected_for_next_month']: agg[r['rejection_or_status']]+=1
    lines=[
      '# 2022 Energy stock capture audit','',
      'Audit basis: the independent reconstructed frozen-like 75/25 engine (global momentum entry Top-20 / incumbent retention Top-35, 25% size-first leadership sleeve, SPY EMA200 BULL/BEAR gate, inverse-ATR sizing, 3x ATR stop). This is not the exact historical $19,808 artifact.','',
      'Global raw rank below is computed across all point-in-time S&P names with a usable momentum score. Engine eligible rank is the reconstruction\'s rank after fundamental PASS and positive momentum. Energy rank is raw momentum rank within point-in-time Energy constituents.','',
      '| Month-end | SPY state | Energy names | Positive mom | Raw global Top-20 | Engine Top-20 | Owned Energy wt | Target Energy wt | Target Energy names |',
      '|---|---|---:|---:|---:|---:|---:|---:|---:|'
    ]
    for x in summaries:
        lines.append(f"| {x['date']} | {'BULL' if x['spy_bull'] else 'BEAR'} | {x['energy_members']} | {x['energy_positive_momentum']} | {x['energy_raw_global_top20']} | {x['energy_engine_top20']} | {x['owned_energy_weight_pct']:.1f}% | {x['target_energy_weight_pct']:.1f}% | {x['target_energy_symbols'] or '-'} |")
    lines+=['','## Non-selection reason counts across all monthly Energy observations','',
            '| Reason | Count |','|---|---:|']
    for reason,n in agg.most_common(): lines.append(f'| {reason} | {n} |')

    lines+=['','## Highest-momentum Energy names by month','',
            '| Month-end | Energy #1 | Raw global rank | Engine rank | Momentum | Owned wt | Next target wt | Status |',
            '|---|---|---:|---:|---:|---:|---:|---|']
    bydate=defaultdict(list)
    for r in detail: bydate[r['date']].append(r)
    for d in sorted(bydate):
        rows=sorted([r for r in bydate[d] if r['energy_rank'] is not None],key=lambda r:r['energy_rank'])
        if not rows: continue
        r=rows[0]
        lines.append(f"| {d} | {r['symbol']} | {r['raw_global_rank'] or '-'} | {r['engine_eligible_rank'] or '-'} | {r['momentum_pct']:+.1f}% | {r['portfolio_weight_pct']:.1f}% | {r['target_weight_pct']:.1f}% | {r['rejection_or_status']} |")

    lines+=['','## Files','',
            '- Detailed row-level audit: backtests/results/energy_2022_monthly_audit.csv',
            '- Month summary: backtests/results/energy_2022_monthly_summary.csv',
            '',
            '## Caveats','',
            '- Historical S&P membership is reconstructed point-in-time, but ticker-to-sector labels use the current GICS mapping and do not reconstruct every historical GICS reclassification.',
            '- The SEC fundamental PASS reconstruction is the largest known mismatch versus the original frozen artifact.',
            '- Therefore use this audit to identify mechanisms and relative bottlenecks; exact frozen-artifact attribution still requires the original ledger/data package.'
    ]
    OUTM.write_text('\n'.join(lines)+'\n')
    print(OUTM.read_text())

if __name__=='__main__': main()
