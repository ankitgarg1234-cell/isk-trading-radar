#!/usr/bin/env python3
import json, calendar
from pathlib import Path
from collections import defaultdict

ROOT=Path(__file__).resolve().parents[1]
IN=ROOT/'backtests/results/regime_policy_matrix_2022_2026.json'
OUT=ROOT/'backtests/results/regime_policy_matrix_diagnostic.md'
rep=json.loads(IN.read_text())
names=['SPY gate + monthly exits','Matrix Balanced']
daily=rep['daily']
logs=rep['signal_logs']

def monthly_stats(name):
    by=defaultdict(list)
    for r in daily[name]: by[r['date'][:7]].append(r)
    out={}
    prev_end=None
    for m in sorted(by):
        rows=by[m]
        start=prev_end if prev_end is not None else rows[0]['nav']
        end=rows[-1]['nav']
        ret=end/start-1 if start else 0
        exp=sum(x['equity_exposure'] for x in rows)/len(rows)
        out[m]={'ret':ret,'exp':exp,'end':end}
        prev_end=end
    return out

ms={n:monthly_stats(n) for n in names}
lines=['# Regime-policy diagnostic: where Matrix Balanced helps/hurts','']
for year in ['2022','2023','2024','2025','2026']:
    lines += [f'## {year}','', '| Month | Prior signal state | SPY-gate return | Balanced return | Delta | SPY-gate exp. | Balanced exp. | Exp delta |','|---|---|---:|---:|---:|---:|---:|---:|']
    months=sorted(set(k for n in names for k in ms[n] if k.startswith(year+'-')))
    for m in months:
        y,mo=map(int,m.split('-'))
        if mo==1: py,pm=y-1,12
        else: py,pm=y,mo-1
        prior_prefix=f'{py:04d}-{pm:02d}-'
        state='START'
        candidates=[(d,x) for d,x in logs['Matrix Balanced'].items() if d.startswith(prior_prefix)]
        if candidates: state=candidates[-1][1].get('state','')
        a=ms[names[0]].get(m,{'ret':0,'exp':0})
        b=ms[names[1]].get(m,{'ret':0,'exp':0})
        lines.append(f"| {m} | {state} | {a['ret']*100:+.2f}% | {b['ret']*100:+.2f}% | {(b['ret']-a['ret'])*100:+.2f} pp | {a['exp']*100:.1f}% | {b['exp']*100:.1f}% | {(b['exp']-a['exp'])*100:+.1f} pp |")
    lines.append('')
OUT.write_text('\n'.join(lines)+'\n')
print(OUT.read_text())
