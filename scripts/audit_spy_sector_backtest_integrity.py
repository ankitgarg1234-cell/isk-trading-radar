#!/usr/bin/env python3
"""Integrity diagnostics for the SPY/sector research replay. Does not alter strategy results."""
import sys
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import adaptive_entry_policy_backtest as b
import spy_sector_hierarchy_backtest as h

def rec(end, filed, val, start):
    return {'end':end,'filed':filed,'val':val,'start':start,'form':'10-K'}

# The study precomputes a December 2021 signal, but the trading loop starts in 2022.
dec_signal = date(2021,12,31)
first_trade = date(2022,1,3)
assert dec_signal < first_trade
print("INITIALIZATION: 2021-12 signal precedes 2022 trading loop; no warm-start holdings are created.")

# Later-filed annual amendments replace the original 10-K for the same fiscal year
# before the as-of date filter is applied. The historical observation disappears.
sample={'units':{'USD':[
    rec('2020-12-31','2021-02-20',100,'2020-01-01'),
    rec('2021-12-31','2022-02-20',120,'2021-01-01'),
    rec('2021-12-31','2024-02-20',999,'2021-01-01')
]}}
chosen=b.annual_records(sample)
eligible=b.asof_records(chosen,date(2022,3,31))
print('ANNUAL-FACT-ASOF: original annual observations at Mar 2022 = 2;',
      'after newest-filed preselection =',len(eligible),
      '; chosen 2021 filing =', next(r['filed'] for r in chosen if r['end']=='2021-12-31'))
assert len(eligible)==1
assert len([r for r in sample['units']['USD'] if r['filed']<='2022-03-31'])==2

# A disappeared ticker in positions, but absent from the signal snapshot, generates no sell.
st=b.State('missing-snapshot-test',False)
st.pos[b.key('rot','GHOST')]=b.VPos('rot','GHOST',10,100,date(2022,1,3),100,70,True,False)
sells, rot_sel, lead_sel=h.selection_plan(st,{},[],{'Energy'},True,'bear_exception')
print('MISSING-POSITION: position exists=',bool(st.pos),
      '; exit order=', bool(sells),'; remains held after empty target plan=',not bool(sells))
assert not sells

# Frozen-like rank in this replay is filtered for PASS before ranking.
fake=[('FIRST',{'mom':2.0,'fund':False}),('SECOND',{'mom':1.0,'fund':True})]
filtered=sorted([(s,r) for s,r in fake if r['fund'] is True and r['mom']>0],
                key=lambda z:z[1]['mom'],reverse=True)
raw=sorted(fake,key=lambda z:z[1]['mom'],reverse=True)
print('RANK-DEFINITION: raw SECOND rank =', [s for s,_ in raw].index('SECOND')+1,
      '; filtered SECOND rank =', [s for s,_ in filtered].index('SECOND')+1)
assert len(filtered)==1 and [s for s,_ in raw].index('SECOND')==1

# Existing sizing scales the sector opportunity to number of occupied slots, not sector strength.
w=b.target_weights(['XOM','CVX'],b.ROT_BUDGET,b.ROT_MAX,
  {'XOM':{'pct_atr':0.03},'CVX':{'pct_atr':0.02}})
print('DEPLOYMENT: two qualifying rotational Energy names use',
      f"{100*sum(w.values()):.1f}% of total NAV from rotational sleeve (not 75%).")
assert abs(sum(w.values())-0.10)<1e-9

# Verify identical selection in SPY BULL; the "bear exception" is not active there.
snap={
'A': {'fund':True,'mom':1,'rank':1,'sector':'Energy','pct_atr':0.03},
'B': {'fund':True,'mom':0.5,'rank':2,'sector':'Materials','pct_atr':0.03},
}
control=h.selection_plan(b.State('ctl',False),snap,[],set(h.SECTOR_ETFS),True,'control')
exception=h.selection_plan(b.State('exc',False),snap,[],set(h.SECTOR_ETFS),True,'bear_exception')
assert control==exception
print('BULL-SIGNAL-PARITY: matched for synthetic entry-only basket.')

print('VERDICT: research replay has confirmed implementation/integrity defects; not eligible for production evaluation.')
