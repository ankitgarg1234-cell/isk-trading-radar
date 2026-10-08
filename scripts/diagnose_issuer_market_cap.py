#!/usr/bin/env python3
"""Diagnostic-only: audit suspicious issuer-cap ranks against raw cached facts."""
import json
from datetime import date
from pathlib import Path
import adaptive_entry_policy_backtest as b

ROOT=Path(__file__).resolve().parents[1]
res=json.loads((ROOT/'backtests/results/spy_sector_hierarchy_2022_2026.json').read_text())
cache=b.Cache(ROOT/'.backtest_cache')
cikmap=cache.get('sec','tickers') or {}
for decision in ('2023-05-31','2023-06-30','2023-07-31','2024-06-28'):
  entry=next(x for x in res['eligibility_audit'] if x['date']==decision)
  top=entry['top15_implied_issuer_caps']
  print(f'DATE {decision}: TOP5_CAPS '+', '.join(f"{e['symbol']}=${e['implied_cap']/1e9:,.1f}bn" for e in top[:5]))
  for symbol in ('PKG','NVDA','AAPL','MSFT'):
    cap=next((x['implied_cap'] for x in top if x['symbol']==symbol),None)
    cik=cikmap.get(symbol)
    data=cache.get('facts',symbol+'_'+str(cik)) if cik else None
    pit=b.preprocess_facts(data) if data and not data.get('missing') else None
    rec=b.shares_record_asof(pit,date.fromisoformat(decision)) if pit else None
    key=symbol+'_'+b.DATA_START.isoformat()+'_'+b.DATA_END.isoformat()
    raw=cache.get('yahoo',key)
    mk=b.prepare_market(raw) if raw and not raw.get('missing') else None
    ind=b.indicators(mk,date.fromisoformat(decision)) if mk else None
    print('ISSUER',decision,symbol,'CIK',cik,'CAP_IN_REPORT_BN',round(cap/1e9,3) if cap else None,
          'SHARES_RECORD', {k:rec.get(k) for k in ('end','filed','val','form','accn')} if rec else None,
          'SPLIT_ADJUSTED_PRICE',round(ind['close'],4) if ind else None,
          'SPLIT_EVENTS',mk.get('splits') if mk else None)
