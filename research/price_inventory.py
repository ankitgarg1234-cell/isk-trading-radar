"""Offline historical-price inventory: cached observations are never changed."""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path

from research.spgm_sources import DEFAULT_OUTPUT, ROOT
from research.spgm_proxy import write_csv

REPO = Path(__file__).resolve().parents[1]
REFERENCES = ['SPY','XLK','XLC','XLY','XLP','XLE','XLF','XLV','XLI','XLB','XLRE','XLU']


def describe(symbol,rows,path,kind):
    dates=sorted(r['date'] for r in rows if r.get('date'))
    return dict(symbol_label=symbol,cache_kind=kind,path=str(path.relative_to(REPO)),rows=len(rows),
        first=dates[0] if dates else '',last=dates[-1] if dates else '',
        prelaunch_bars=sum(d<='2023-09-29' for d in dates),
        target_period_bars=sum('2023-10-01'<=d<='2026-09-30' for d in dates),
        adjusted_close_rows=sum(any(r.get(k) not in (None,'') for k in ('adjusted_close','adjclose','total_return_close')) for r in rows),
        duplicate_dates=len(dates)-len(set(dates)),
        historical_listing_verified=False,historical_gics_verified=False)


def inventory():
    out=DEFAULT_OUTPUT/'historical_backtest'
    out.mkdir(exist_ok=True)
    rows,hashes=[],{}
    for path in sorted(list(ROOT.glob('*.csv'))+list((ROOT/'asia_corporate_actions').glob('*.csv'))):
        data=list(csv.DictReader(path.open()))
        if not data or not {'date','open','high','low','close'}<=data[0].keys():continue
        kind='derived_normalization' if 'split_only' in path.name else 'EODHD_raw_cache'
        rows.append(describe(path.stem,data,path,kind))
        hashes[str(path.relative_to(REPO))]=hashlib.sha256(path.read_bytes()).hexdigest()
    staged=REPO/'backtests/staged/wf3_prices.json.gz'
    with gzip.open(staged,'rt') as stream:data=json.load(stream)
    for symbol,entry in data['market'].items():
        rows.append(describe(symbol,entry.get('rows',[]),staged,'legacy_staged_cache'))
    hashes[str(staged.relative_to(REPO))]=hashlib.sha256(staged.read_bytes()).hexdigest()
    legacy=[r for r in rows if r['cache_kind']=='legacy_staged_cache']
    raw=[r for r in rows if r['cache_kind']=='EODHD_raw_cache']
    summary=dict(legacy_series=len(legacy),raw_eodhd_series=len(raw),
        legacy_prelaunch_253_eligible=sum(r['prelaunch_bars']>=253 for r in legacy),
        legacy_max_prelaunch_bars=max(r['prelaunch_bars'] for r in legacy),
        legacy_missing_reference_symbols=[s for s in REFERENCES if s not in data['market']],
        legacy_explicit_adjusted_close_series=sum(r['adjusted_close_rows']>0 for r in legacy),
        legacy_sector_labels=len(data['membership'].get('sectors',{})),
        legacy_sector_verification='UNDATED; no historical GICS effective/publication intervals',
        legacy_membership_period=data.get('period'),
        legacy_membership_verification='2024 start list and dated changes; publication times absent; no verified October2023 initial list',
        legacy_cache_generated_at=data.get('generated_at'),
        raw_eodhd_prelaunch_253_eligible=sum(r['prelaunch_bars']>=253 for r in raw),
        raw_eodhd_first=min(r['first'] for r in raw),raw_eodhd_last=max(r['last'] for r in raw),
        fx_verified_series=0,historical_reference_prices_complete=False,
        cached_data_sha256=hashes,new_price_requests=0)
    write_csv(out/'price_inventory.csv',rows)
    (out/'price_inventory_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    lines=['# Historical price and FX inventory','',
        'Inventory is offline. Existing cached observations and legacy staged files are unchanged. Series labels do not establish dated listing identity.','',
        '| Cache | Series |253 prelaunch bars | Adjusted/TR field | Readiness limitation |','|---|---:|---:|---|---|',
        f"| Legacy staged price cache | {len(legacy)} | {summary['legacy_prelaunch_253_eligible']} | No explicit adjusted close in any series | Starts too late for prelaunch momentum; all12 reference series absent |",
        f"| EODHD raw cache | {len(raw)} | {summary['raw_eodhd_prelaunch_253_eligible']} | Separate adjusted close present | Approximately one year of history, not2021–26 |",
        '| Verified historical FX |0|0|None|Currency-sensitive ranking/NAV/fills blocked|','',
        f"The legacy539-series cache supplies at most **{summary['legacy_max_prelaunch_bars']}** prelaunch observations versus253 required (254 for the two-close SPY regime). Its503 sector labels lack historical GICS effective/publication dates. A dated membership-change event is not evidence of public-knowledge timing. These records can support data diagnostics, not a silently shortened or survivor-biased October2023 comparison.", '',
        f"Raw EODHD cache span: **{summary['raw_eodhd_first']}–{summary['raw_eodhd_last']}**. Records after September30 2026 are retained in raw storage but cannot enter the requested result period. The separate AZN split-normalized and Taiwan session-filtered derivatives remain preserved; derivatives do not supply missing historical years, FX or sectors.", '',
        'Cached independent IBKR coverage counts are metadata, not downloadable daily OHLC inputs. No verified FX price tape, complete reference ETF histories or full global historical price bundle was found. Detailed per-series counts and original-file SHA256s are stored in ignored `historical_backtest/price_inventory.csv` and `price_inventory_summary.json`.', '',
        'Required acquisition remains January2021–September2026 (subject to actual listing dates), all historically eligible equities including inactive securities, SPY+11 sector ETFs, verified action history, native calendars and timestamped USD-per-local-unit FX. Do not backfill the missing2023 warm-up with current constituents or invented prices.']
    (out/'price_inventory.md').write_text('\n'.join(lines)+'\n')
    return summary


if __name__=='__main__':
    result=inventory();print(json.dumps({k:v for k,v in result.items() if k!='cached_data_sha256'}))
