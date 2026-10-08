#!/usr/bin/env python3
"""2022 Energy-opportunity reconciliation, independent of SEC stock eligibility."""
from datetime import date
import bisect, json, math
from collections import defaultdict
from pathlib import Path
import sector_etf_rotation_diagnostic as old

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'backtests/results/energy_2022_sector_bridge.md'
OUTJ=ROOT/'backtests/results/energy_2022_sector_bridge.json'
FIRST=date(2022,1,3)
LAST=date(2022,12,30)

def continuous_ema(rows, i):
    if i<199: return None
    e=sum(r['tr'] for r in rows[:200])/200
    a=2.0/201.0
    for j in range(200,i+1):
        e=a*rows[j]['tr']+(1-a)*e
    return e

def signal(markets,day,topk=2):
    vals=[]
    for ticker, m in markets.items():
        i=old.idx_before(m,day)
        if i is None or i<252: continue
        n=[old.ret_n(m,day,j) for j in (63,126,252)]
        if any(v is None for v in n): continue
        momentum=sum(n)/3
        ema=continuous_ema(m['rows'],i)
        if momentum>0 and m['rows'][i]['tr']>ema:
            vals.append((momentum,ticker))
    vals.sort(reverse=True)
    return [ticker for _,ticker in vals[:topk]]

def px(markets,t,d,kind):
    m=markets[t]
    i=old.idx_before(m,d)
    assert i is not None and m['rows'][i]['date']==d.isoformat()
    p=m['rows'][i][kind]
    assert p is not None and p>0
    return p

def run(markets, k):
    ds=[date.fromisoformat(r['date']) for r in markets['XLE']['rows']
        if FIRST<=date.fromisoformat(r['date'])<=LAST]
    sigs=[date(2021,12,31)]
    months={}
    for d in ds: months[(d.year,d.month)]=d
    sigs+=list(months.values())
    pending={}
    for sig in sigs:
        next_day_idx=bisect.bisect_right(ds,sig)
        if next_day_idx<len(ds):
            pending[ds[next_day_idx]]={'signal':sig,'selected':signal(markets,sig,k)}
    holdings={}; cash=10000.0; fees=0.0; logs=[]; daily=[]
    for d in ds:
        if d in pending:
            cmd=pending[d]
            # Liquidate prior holdings and allocate equal capital to all selected.
            for t,qty in list(holdings.items()):
                openp=px(markets,t,d,'open'); executed=openp*(1-0.0007)
                commission=max(1.0,0.005*qty)
                cash+=qty*executed-commission; fees+=qty*(openp-executed)+commission
            holdings={}
            selections=cmd['selected']
            per=cash/len(selections) if selections else 0
            for t in selections:
                openp=px(markets,t,d,'open'); executed=openp*(1+0.0007)
                qty=int(math.floor(max(0,per-1.0)/executed))
                while qty>0 and qty*executed+max(1.0,0.005*qty)>cash:
                    qty-=1
                if qty:
                    commission=max(1.0,0.005*qty)
                    cash-=qty*executed+commission
                    holdings[t]=qty
                    fees+=qty*(executed-openp)+commission
            logs.append({'signal':cmd['signal'].isoformat(),
                'executed':d.isoformat(),'sectors':selections,
                'cash_after_rebalance':cash})
        # Dividend cash recorded on ex-dates, not falsely included twice in NAV.
        for t,qty in holdings.items():
            i=old.idx_before(markets[t],d)
            rows=markets[t]['rows']
            prev_idx=i-1
            if prev_idx>=0:
                prev=rows[prev_idx]
                if prev['tr']>0 and prev['close']>0:
                    cash+=qty*max(0.0,(rows[i]['tr']/prev['tr'])*prev['close']-rows[i]['close'])
        nav=cash+sum(qty*px(markets,t,d,'close') for t,qty in holdings.items())
        daily.append((d.isoformat(),nav))
    return {'k':k,'return_2022_pct':(daily[-1][1]/10000-1)*100,
        'ending_nav':daily[-1][1],'costs':fees,'selections':logs}

def main():
    markets={s:old.fetch(s) for s in old.SECTORS}
    results=[run(markets,k) for k in (1,2,3)]
    initial=results[1]['selections'][0]
    assert initial['signal']=='2021-12-31' and initial['executed']=='2022-01-03'
    for r in results:
        assert len(r['selections'])==12
    rep={'method':'2022 sector ETF allocation only; warm-start on 2021-12-31, next open 2022-01-03; continuous EMA200; top-K equal weight; monthly sell-and-rebuy; cash dividends and transaction cost, no ATR or stock fundamental filter.',
        'results':results,
        'note':'NOT a simulation of the frozen 75/25 stock strategy and NOT a verification of the user-proposed +16.4%.',
        'acceptance_test':'The full stock-engine result requires original frozen execution and eligibility ledger.'}
    OUTJ.parent.mkdir(parents=True,exist_ok=True);OUTJ.write_text(json.dumps(rep,indent=2)+'\n')
    lines=['# 2022 sector-rotation return bridge','',
        'This is a test of the **opportunity capture in sector ETFs**, not a replication of the 75/25 stock portfolio.',
        'Monthly 63/126/252 total-return momentum, sector own EMA200 (continuous, SMA-200-seeded), invest equally in Top-K sectors that are positive and above trend. Next-session open execution, whole shares, $1 minimum commission, 7 bps adverse price adjustment on each side. December 2021 signal is invested on January 3, 2022. No stock fundamental gates, SPY veto, ATR stops or sector concentration caps.','',
        '| ETF sector strategy | 2022 return | Dec 2022 NAV on $10k | Transaction costs |',
        '|---|---:|---:|---:|']
    for r in results:
        lines.append(f"| Top-{r['k']} BULL sectors | {r['return_2022_pct']:+.2f}% | ${r['ending_nav']:,.2f} | ${r['costs']:,.2f} |")
    lines+=['','## Monthly decisions, Top-2 sector ETFs','',
        '| Signal after close | Next-session open | Allocated sector ETFs |','|---|---|---|']
    for sig in results[1]['selections']:
        sectors=', '.join(f"{s} ({old.SECTORS[s]})" for s in sig['sectors']) or 'Cash'
        lines.append(f"| {sig['signal']} | {sig['executed']} | {sectors} |")
    lines+=['','## Interpretation','',
            'The previously quoted ~15.75% sector-ETF test had an initialization defect and rolling-window EMA200; do not treat that value as certified. This run corrects both and reports an ETF-only diagnostic.',
            'Any stock-portfolio return such as +16.4% requires an explicit allocation/eligibility/exit specification and trade-level attribution; this test cannot establish that number.']
    OUT.write_text('\n'.join(lines)+'\n');print(OUT.read_text())

if __name__=='__main__':main()
