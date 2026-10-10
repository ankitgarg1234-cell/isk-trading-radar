"""Audit the existing provider's public history without certifying membership."""
from __future__ import annotations
import csv,json
from collections import defaultdict
from datetime import date
from research.global_backtest_pipeline import OUTPUT


def historical_candidates(rows,cutoff):
    date.fromisoformat(cutoff)
    selected=[]
    for row in rows:
        def day(key):
            value=row.get(key,'').rstrip('*')
            if value:date.fromisoformat(value)
            return value
        added,removed,created=day('date_added'),day('date_removed'),day('created_at')
        if not added or not created:raise ValueError('History effective/creation dates absent')
        if added<=cutoff and (not removed or cutoff<removed) and created<=cutoff:selected.append(row)
    return selected


def audit(history,current):
    active=historical_candidates(history,'2023-09-29')
    issuers=defaultdict(list);sectors=defaultdict(set)
    for r in active:issuers[r['cik'].lstrip('0')].append(r['symbol'])
    for r in current:sectors[r['CIK'].lstrip('0')].add(r['GICS Sector'])
    return dict(source_rows=len(history),prelaunch_symbols=len(active),prelaunch_issuers=len(issuers),
        overlapping_issuer_symbols={k:v for k,v in issuers.items() if len(v)>1},
        current_gics_cik_join_candidates=sum(len(sectors[r['cik'].lstrip('0')])==1 for r in active),
        current_gics_source_rows=len(current),sector_conflict_issuers=sum(len(v)>1 for v in sectors.values()),
        starred_prelaunch_date_rows=sum('*' in r['date_added']+r['date_removed'] for r in active),
        faithful_membership_ready=False,public_announcement_timing_verified=False,
        limitations=['Effective-date source has documented overlapping ticker aliases and approximate dates',
            'Current CIK issuer sector matches do not establish dated listing/share-class identity',
            'Source history downloaded today is not evidence of prior-public historical announcements'])


if __name__=='__main__':
    directory=OUTPUT/'reference_sources'
    with (directory/'history.csv').open() as stream:history=list(csv.DictReader(stream))
    with (directory/'current_sp500.csv').open() as stream:current=list(csv.DictReader(stream))
    result=audit(history,current)
    (directory/'us_history_audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
