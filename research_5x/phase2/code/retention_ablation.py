"""Same initial basket and sizing; isolate later holding, trimming and exits."""
from phase2_bootstrap import e, ROOT, OUT
import ast, inspect, json, bisect, time
from datetime import datetime,timezone
import pandas as pd
import numpy as np

DEST=OUT/'retention';DEST.mkdir(parents=True,exist_ok=True)
tree=ast.parse(inspect.getsource(e.simulate));fn=tree.body[0]
def st(s):return ast.parse(s).body
class FixedBasket(ast.NodeTransformer):
    def __init__(self):self.locations={}
    def visit_Constant(self,node):
        if isinstance(node.value,float) and node.value==.25:
            return ast.parse("cfg.get('concentration_cap', 1.)",mode='eval').body
        return node
    def visit_If(self,node):
        self.generic_visit(node)
        if ast.unparse(node.test)=="ds in monthg":
            self.locations['monthly']=1
            node.body[:0]=st("""
if initial_basket is not None and cfg.get('rotation_frequency')=='quarterly' and int(ds[5:7]) not in (3,6,9,12):continue
if initial_basket is not None and cfg.get('rotation_frequency')=='never':continue
""")
        return node
    def visit_Assign(self,node):
        self.generic_visit(node)
        if len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id=='w' and isinstance(node.value,ast.Call) and ast.unparse(node.value.func)=='np.full':
            # This lies inside the equal-weight else. Override targets before weight creation.
            self.locations['target_override']=1
            return st("""
if initial_basket is None:
    initial_basket=tuple(targets)
    allowed=set(initial_basket)
else:
    raw=monthg[ds]
    for symbol in list(allowed):
        if symbol not in raw.index:
            allowed.discard(symbol);continue
        row=raw.loc[symbol]
        if cfg.get('exit_rule')=='reported_fundamental' and not (row.G and row.E and row.margin_delta_pp>3):allowed.discard(symbol)
        if cfg.get('exit_rule')=='relative_strength' and not (row.rel_spy63>0):allowed.discard(symbol)
    targets=[s for s in initial_basket if s in allowed]
""")+[node]
        if len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id=='pending' and isinstance(node.value,ast.Tuple):
            self.locations['dispatch_policy']=1
            node.value.elts[-1]=ast.parse("bool(cfg.get('preserve_initial_weights')) and bool(held)",mode='eval').body
        return node
    def visit_Expr(self,node):
        self.generic_visit(node)
        if isinstance(node.value,ast.Call) and ast.unparse(node.value.func)=='curve.append':
            self.locations['holdings']=1
            return [node]+st("""
position_snapshots.extend({'date':ds,'ticker':s,'shares':q,'value':q*mark(s,ds),'weight':q*mark(s,ds)/eq} for s,q in held.items())
""")
        return node
x=FixedBasket();fn=x.visit(fn)
fn.body[1:1]=st('initial_basket=None\nallowed=set()\nposition_snapshots=[]')
fn.body[-1:-1]=st("result['initial_basket']=list(initial_basket or [])\nresult['position_snapshots']=position_snapshots")
ast.fix_missing_locations(tree)
if x.locations!={'holdings':1,'monthly':1,'target_override':1,'dispatch_policy':1}:raise RuntimeError(x.locations)
ns=dict(e.__dict__);exec(compile(tree,'fixed_basket_simulate','exec'),ns);simulate=ns['simulate']
POLICIES={
 'monthly_equal':{},
 'quarterly_equal':{'rotation_frequency':'quarterly'},
 'untouched_hold':{'rotation_frequency':'never'},
 'monthly_cap25_only':{'preserve_initial_weights':True,'concentration_cap':.25},
 'fundamental_exit_only':{'preserve_initial_weights':True,'exit_rule':'reported_fundamental'},
 'relative_strength_exit_only':{'preserve_initial_weights':True,'exit_rule':'relative_strength'}}

def holding_time(trades,end):
    # Weighted purchased share-day duration, including still-open lots to final mark;
    # corporate entitlement shares are not discretionary purchases. Split-like units not comparable across issuers.
    lots={};dur=0.;total=0.
    for r in trades.itertuples():
        if r.side=='BUY':lots.setdefault(r.ticker,[]).append([pd.Timestamp(r.date),r.shares])
        else:
            remaining=r.shares
            for lot in lots.get(r.ticker,[]):
                n=min(remaining,lot[1]);dur+=n*(pd.Timestamp(r.date)-lot[0]).days;total+=n;lot[1]-=n;remaining-=n
                if remaining<=0:break
    for seq in lots.values():
        for d,n in seq:dur+=n*(pd.Timestamp(end)-d).days;total+=n
    return dur/total if total else None

def main():
    before=e.sha(ROOT/'research_5x/code/run_research.py')
    e.dump(DEST/'protocol.json',{'written_before_runs_utc':datetime.now(timezone.utc).isoformat(),
      'policies':POLICIES,'cost_bps_per_side':[20,100],'start_policy':'Cash until first new month-end; identical initial basket,20% slots,whole shares across policies for each cost/start. No replacements or reentry after exit.',
      'cap_scope':'25% checked only at monthly execution; can drift between checks.',
      'exit_rule':'Reported fundamental means originalG/E/margin gates, without momentum. Relative strength means63-session stock return exceedsSPY; directional zero boundary, no tuning. Membership removal applies to all.',
      'caveats':['No expectations/thesis exit without released historical expectations','Static baskets are ablations, not implementable proof of repeatable5x selection','Annual accounts overlap; all history reused','All inherited input/corporate-action limitations remain']})
    (DEST/'transformed_simulate.py').write_text(ast.unparse(tree)+'\n')
    prices=e.load_gz(e.REPO/'backtests/staged/wf3_prices.json.gz')
    frames,panel,calendar=e.prepare(prices,e.load_gz(e.REPO/'backtests/staged/wf3_valuein_fundamentals.json.gz'),json.loads((ROOT/'research_5x/data/spy.json').read_text()))
    first={}
    for d in calendar:first.setdefault(d[:7],d)
    starts=[d for d in first.values() if e.anniversary(d).isoformat()<=calendar[-1]]
    base=next(c for c in e.CONFIGS if c['name']=='growth_margin5')
    rows=[];curves=[];ledgers=[];signals=[];holds=[];checks=[]
    for start in starts:
        end=calendar[bisect.bisect_right(calendar,e.anniversary(start).isoformat())-1]
        for bps in [20,100]:
            ref=None
            for name,policy in POLICIES.items():
                cfg={**base,**policy,'name':name}
                z,c,t,r,s=simulate(cfg,frames,panel,calendar,start=start,end=end,cost_bps=bps)
                ident={'start':start,'policy':name,'bps':bps}
                h=pd.DataFrame(z.pop('position_snapshots'))
                firstdate=t.date.min() if len(t) else None
                init=t[(t.date==firstdate)&t.side.eq('BUY')][['ticker','shares','nominal_open','cost']].reset_index(drop=True)
                if ref is None:ref=init
                else:pd.testing.assert_frame_equal(ref,init,check_dtype=False)
                if len(t):
                    assert set(t.loc[t.side=='BUY','ticker'])<=set(z['initial_basket'])
                    if policy.get('preserve_initial_weights') or policy.get('rotation_frequency')=='never':
                        assert t.loc[t.side=='BUY','date'].nunique()==1,'Reentry or replacement changed selection'
                assert abs(z['accounting_residual_dollars'])<1e-6 and c.cash.min()>=-1e-6
                cluster=h[h.ticker.isin(['SNDK','WDC','STX','MU'])].groupby('date').weight.sum() if len(h) else pd.Series(dtype=float)
                terminalcost=(c.equity.iloc[-1]-c.cash.iloc[-1])*bps/10000
                rows.append({**ident,'end':end,'first_buy':firstdate,'initial_basket':'|'.join(z['initial_basket']),
                  'return_pct':z['net_return_pct'],'max_dd_pct':z['max_dd_pct'],
                  'terminal_cost_deduction_return_pct':(c.equity.iloc[-1]-terminalcost)/e.CAPITAL*100-100,
                  'average_exposure_pct':z['average_exposure_pct'],'trade_count':z['trade_count'],
                  'turnover':z['annual_oneway_turnover_over_avg_equity'],'cost_dollars':z['total_cost_dollars'],
                  'max_company_weight_pct':h.weight.max()*100 if len(h) else 0,
                  'max_storage_memory_weight_pct':cluster.max()*100 if len(cluster) else 0,
                  'mean_purchased_share_holding_calendar_days':holding_time(t,end),
                  'accounting_residual_dollars':z['accounting_residual_dollars']})
                for collection,frame in [(curves,c),(ledgers,t),(signals,s),(holds,h)]:
                    for k,v in ident.items():frame[k]=v
                    collection.append(frame)
        checks.append({'start':start,'same_initial_orders_all_policies':True,'no_new_tickers_after_initial_selection':True,'cash_and_pnl_checks':True})
        print('Matched initial baskets through '+start,flush=True)
    for name,seq in [('curves',curves),('trades',ledgers),('signals',signals),('holdings',holds)]:
        pd.concat(seq,ignore_index=True).to_csv(DEST/(name+'.csv.gz'),index=False,compression={'method':'gzip','mtime':0})
    f=pd.DataFrame(rows);f.to_csv(DEST/'accounts.csv',index=False)
    summaries=[];frequencies=[]
    for (policy,bps),g in f.groupby(['policy','bps']):
        summaries.append({'policy':policy,'bps':bps,'accounts':len(g),'median_return_pct':g.return_pct.median(),
          'mean_return_pct':g.return_pct.mean(),'worst_return_pct':g.return_pct.min(),'best_return_pct':g.return_pct.max(),
          'largest_account_dd_pct':g.max_dd_pct.min(),'median_dd_pct':g.max_dd_pct.median(),
          'fivefold_accounts':int((g.return_pct>=400).sum()),'loss_accounts':int((g.return_pct<0).sum()),
          'mean_turnover':g.turnover.mean(),'mean_cost_dollars':g.cost_dollars.mean(),
          'max_company_weight_pct':g.max_company_weight_pct.max(),'max_cluster_weight_pct':g.max_storage_memory_weight_pct.max()})
        for scope,z in [('all',g),*list(g.groupby(g.start.str[:4]))]:
            for threshold in [0,50,100,200,400,-20,-30]:
                n=int((z.return_pct>threshold).sum()) if threshold==0 else int((z.return_pct>=threshold).sum()) if threshold>0 else int((z.return_pct<=threshold).sum())
                frequencies.append({'policy':policy,'bps':bps,'start_year':scope,'threshold_pct':threshold,
                  'comparison':'>' if threshold==0 else '>=' if threshold>0 else '<=','accounts':len(z),'count':n,'empirical_frequency_pct':n/len(z)*100,
                  'future_probability':'unavailable; overlapping accounts and too few regimes'})
    pd.DataFrame(summaries).to_csv(DEST/'summary.csv',index=False)
    pd.DataFrame(frequencies).to_csv(DEST/'empirical_frequencies.csv',index=False)
    # Matched improvement distribution. No winner-picked starts or policy selection.
    diffs=[]
    for bps in [20,100]:
        pivot=f[f.bps.eq(bps)].pivot(index='start',columns='policy',values='return_pct')
        for policy in POLICIES:
            d=pivot[policy]-pivot.monthly_equal
            diffs.append({'policy':policy,'bps':bps,'mean_return_difference_pp':d.mean(),'median_return_difference_pp':d.median(),
                          'starts_better_than_monthly_equal':int((d>1e-8).sum()),'starts_worse':int((d< -1e-8).sum())})
    pd.DataFrame(diffs).to_csv(DEST/'paired_differences.csv',index=False)
    assert e.sha(ROOT/'research_5x/code/run_research.py')==before
    e.dump(DEST/'verification.json',{'pass':True,'accounts':len(f),'initial_order_checks':checks,'source_unchanged':True,
      'highest_absolute_pnl_residual':f.accounting_residual_dollars.abs().max(),
      'source_sha256':before,'ast_locations':x.locations,'posture':'retrospective matched ablations on frozen, incomplete public-source panel'})
    print(pd.DataFrame(summaries).to_string(index=False))
if __name__=='__main__':main()
