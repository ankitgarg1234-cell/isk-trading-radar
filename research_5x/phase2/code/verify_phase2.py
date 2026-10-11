"""Independent ledger accounting and frozen-first-basket checks for Phase 2."""
from phase2_bootstrap import e,ROOT,OUT
from audit_winning_account import Market
import json,math,bisect
import pandas as pd,numpy as np

def main():
    p=e.load_gz(e.REPO/'backtests/staged/wf3_prices.json.gz');spy=json.loads((ROOT/'research_5x/data/spy.json').read_text());market=Market(p,spy)
    d=OUT/'retention';curves=pd.read_csv(d/'curves.csv.gz');trades=pd.read_csv(d/'trades.csv.gz');holdings=pd.read_csv(d/'holdings.csv.gz');accounts=pd.read_csv(d/'accounts.csv')
    keys=['start','policy','bps'];tradeby={k:g for k,g in trades.groupby(keys)};heldby={k:g for k,g in holdings.groupby(keys)}
    maxerr=0.;records=[];actionrecords=[]
    for key,c in curves.groupby(keys):
        c=c.sort_values('date');t=tradeby.get(key,pd.DataFrame());h=heldby.get(key,pd.DataFrame());cost=0.;cash=10000.;held={};count=0
        tby={day:g for day,g in t.groupby('date')} if len(t) else {};hby={day:g for day,g in h.groupby('date')} if len(h) else {}
        for row in c.itertuples():
            ds=row.date
            for symbol in list(held):
                if ds not in market.rows[symbol]:continue
                if (symbol,ds) in e.SPINOFFS:
                    child,ratio=e.SPINOFFS[(symbol,ds)];held[child]=held.get(child,0)+held[symbol]*ratio
                    actionrecords.append({'start':key[0],'policy':key[1],'bps':key[2],'date':ds,'ticker':symbol,'child':child,'known':True})
                else:
                    split=market.split(symbol,ds)
                    if split!=1:actionrecords.append({'start':key[0],'policy':key[1],'bps':key[2],'date':ds,'ticker':symbol,'ratio':split,'known':'ordinary_integer' if abs(split-round(split))<1e-6 or abs(1/split-round(1/split))<1e-6 else 'unclassified_vendor_action'})
                    held[symbol]*=split
                cash+=held[symbol]*market.dividend(symbol,ds)
            for tr in tby.get(ds,pd.DataFrame()).itertuples():
                quote,actual=market.quote(tr.ticker,ds,'open');assert actual==ds
                gross=tr.shares*quote;fee=gross*key[2]/10000
                for a,b in [(quote,tr.nominal_open),(gross,tr.gross),(fee,tr.cost)]:assert abs(a-b)<1e-6
                if tr.side=='BUY':
                    assert tr.shares==math.floor(tr.shares);assert gross+fee<=cash+1e-6
                    cash-=gross+fee;held[tr.ticker]=held.get(tr.ticker,0)+tr.shares
                else:
                    assert tr.shares<=held.get(tr.ticker,0)+1e-6;cash+=gross-fee;held[tr.ticker]-=tr.shares
                if abs(held.get(tr.ticker,0))<1e-8:held.pop(tr.ticker,None)
                cost+=fee;count+=1;assert abs(cash-tr.cash_after)<1e-6
            eq=cash+sum(q*market.quote(s,ds)[0] for s,q in held.items())
            residual=max(abs(eq-row.equity),abs(cash-row.cash),abs(cost-row.cumulative_cost));maxerr=max(maxerr,residual);assert residual<1e-6
            book={tr.ticker:tr.shares for tr in hby.get(ds,pd.DataFrame()).itertuples()}
            assert set(book)==set(held)
            assert all(abs(book[s]-q)<1e-6 for s,q in held.items())
            assert row.positions==len(held) and cash>=-1e-6
        record={'start':key[0],'policy':key[1],'bps':key[2],'sessions':len(c),'transactions':count,'pass':True}
        if key[2]==20:
            old=ROOT/f'research_5x/continuation/2026-10-11/experiments/fresh_accounts/growth_margin5__rebalance__{key[0]}_trades.csv'
            if old.exists():a=pd.read_csv(old)
            else:
                first=pd.read_csv(d/'frozen_initial_orders.csv');a=first[first.start.eq(key[0])]
            b=t[t.date.eq(t.date.min())&t.side.eq('BUY')][['ticker','shares','nominal_open','cost']].reset_index(drop=True)
            a=a[a.date.eq(a.date.min())&a.side.eq('BUY')][['ticker','shares','nominal_open','cost']].reset_index(drop=True)
            pd.testing.assert_frame_equal(a,b,check_dtype=False);record['matches_frozen_original_initial_orders']=True
        records.append(record)
    pd.DataFrame(actionrecords).to_csv(d/'held_action_coverage.csv',index=False)
    e.dump(OUT/'verification.json',{'pass':True,'retention_accounts':len(records),'daily_records':len(curves),'transactions_checked':len(trades),'holdings_checked':len(holdings),
      'max_cash_nav_cost_residual':maxerr,'records':records,'held_corporate_events':actionrecords,
      'independent_scope':'Reconstruct cash/shares/dividends/NAV from recordedorders and independentrawMarket implementation; firstorders also match frozen originalpolicy. Futureselectionstrength notcertified.',
      'audit_pass':json.loads((OUT/'audit/summary.json').read_text())['pass'],
      'sources_pass':[json.loads((OUT/'sources'/s/'validation_checks.json').read_text()) for s in ['memory','wdc']]})
    print(json.dumps({'pass':True,'accounts':len(records),'sessions':len(curves),'transactions':len(trades),'maxresidual':maxerr,'held_events':len(actionrecords)}))
if __name__=='__main__':main()
