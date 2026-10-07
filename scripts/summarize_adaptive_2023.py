#!/usr/bin/env python3
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
IN=ROOT/'backtests/results/adaptive_market_state_2022_2026.json'
OUT=ROOT/'backtests/results/adaptive_2023_diagnostic.md'
rep=json.loads(IN.read_text())
metric={r['name']:r for r in rep['results']}
lines=['# Adaptive controller - 2023 diagnostic','']
lines.append('| Variant | 2023 return | 2023 avg exposure | Buys | Sells | Unique bought | Re-bought tickers | 2023 costs |')
lines.append('|---|---:|---:|---:|---:|---:|---:|---:|')
details={}
for name,trades in rep['trades'].items():
    t23=[t for t in trades if str(t.get('date','')).startswith('2023-')]
    buys=[t for t in t23 if t.get('side')=='BUY']
    sells=[t for t in t23 if t.get('side')=='SELL']
    bc=Counter(t.get('symbol') for t in buys)
    rebought=sum(1 for v in bc.values() if v>1)
    costs=sum(float(t.get('commission') or 0)+float(t.get('slippage') or 0) for t in t23)
    m=metric[name]
    ret=m['annual_returns_pct'].get('2023')
    exp=m.get('annual_avg_equity_exposure_pct',{}).get('2023')
    lines.append(f'| {name} | {ret:+.2f}% | {exp:.2f}% | {len(buys)} | {len(sells)} | {len(bc)} | {rebought} | USD {costs:,.2f} |')
    reasons=Counter(t.get('reason') or 'UNKNOWN' for t in sells)
    pnl=defaultdict(float)
    for t in sells: pnl[t.get('reason') or 'UNKNOWN']+=float(t.get('pnl') or 0)
    monthly=defaultdict(lambda:{'buy':0,'sell':0,'cost':0.0})
    for t in t23:
        mo=t['date'][:7]
        monthly[mo]['buy']+=1 if t.get('side')=='BUY' else 0
        monthly[mo]['sell']+=1 if t.get('side')=='SELL' else 0
        monthly[mo]['cost']+=float(t.get('commission') or 0)+float(t.get('slippage') or 0)
    details[name]=(reasons,pnl,bc,monthly,sells)

for name in rep['trades']:
    reasons,pnl,bc,monthly,sells=details[name]
    lines+=['',f'## {name}','', '### 2023 sell reasons','', '| Reason | Sell orders | Realized PnL on those sells |','|---|---:|---:|']
    for reason,n in reasons.most_common(): lines.append(f'| {reason} | {n} | USD {pnl[reason]:,.2f} |')
    lines+=['','### Monthly churn','', '| Month | Buys | Sells | Costs |','|---|---:|---:|---:|']
    for mo in sorted(monthly):
        x=monthly[mo]; lines.append(f"| {mo} | {x['buy']} | {x['sell']} | USD {x['cost']:,.2f} |")
    repeats=[(s,n) for s,n in bc.items() if n>1]
    repeats.sort(key=lambda x:(-x[1],x[0]))
    if repeats:
        lines+=['','### Re-bought tickers in 2023','',', '.join(f'{s} x{n}' for s,n in repeats)]
    top=sorted(sells,key=lambda t:float(t.get('pnl') or 0),reverse=True)[:10]
    bot=sorted(sells,key=lambda t:float(t.get('pnl') or 0))[:10]
    lines+=['','### Largest realized sell PnL','', '| Ticker | Date | Reason | PnL |','|---|---|---|---:|']
    for t in top: lines.append(f"| {t.get('symbol')} | {t.get('date')} | {t.get('reason')} | USD {float(t.get('pnl') or 0):,.2f} |")
    lines+=['','### Largest realized sell losses','', '| Ticker | Date | Reason | PnL |','|---|---|---|---:|']
    for t in bot: lines.append(f"| {t.get('symbol')} | {t.get('date')} | {t.get('reason')} | USD {float(t.get('pnl') or 0):,.2f} |")

lines+=['','## Recovery triggers','']
for r in rep['results']:
    if r.get('recovery_log'):
        lines.append('### '+r['name'])
        for x in r['recovery_log']:
            lines.append(f"- {x['date']}: from {x['from_state']} -> {x['weekly_state']}; breadth {x['breadth']*100:.1f}%, leader health {x['leader_health']*100:.1f}%, orders {x['orders']}")
        lines.append('')
OUT.write_text('\n'.join(lines)+'\n')
print(OUT.read_text())
