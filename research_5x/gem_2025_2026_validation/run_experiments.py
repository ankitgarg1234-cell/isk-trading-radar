"""Frozen GEM experiments on archived inputs: explicitly uncertified.

AST instrumentation adds audit fields only. Numerical equivalence with the
unchanged archived simulator is checked before all account experiments.
"""
import ast,inspect,json,pickle,sys,math
from collections import defaultdict
from datetime import date
from pathlib import Path
import pandas as pd,numpy as np
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'research_5x/code'))
import run_research as b
b.REPO=ROOT
import continuation_engine as adapter
STATUS='ARCHIVED_INPUT_REPLAY_UNCERTIFIED'
def instrument():
    tree=ast.parse(adapter.TRANSFORMED_SOURCE)
    class Audit(ast.NodeTransformer):
        count=0
        def visit_Call(self,node):
            self.generic_visit(node)
            if isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name) and node.func.attr=='append' and node.func.value.id=='curve':
                record=node.args[0];assert isinstance(record,ast.Dict)
                record.keys.extend([ast.Constant('holdings_json'),ast.Constant('marks_json')])
                record.values.extend([ast.parse('json.dumps(held,sort_keys=True)',mode='eval').body,ast.parse('json.dumps({s:mark(s,ds) for s in held},sort_keys=True)',mode='eval').body]);self.count+=1
            return node
    transform=Audit();tree=transform.visit(tree);assert transform.count==1
    ast.fix_missing_locations(tree);ns=dict(b.__dict__);exec(compile(tree,'gem_audit_instrumentation','exec'),ns)
    (OUT/'instrumented_simulate.py').write_text(ast.unparse(tree)+'\n')
    return ns['simulate']
SIM=instrument()
def metrics(curve,tr,result,experiment,policy,scenario,bps,delay):
    v=curve.equity.to_numpy();prior=np.r_[10000.,v[:-1]];ret=v/prior-1
    days=(date.fromisoformat(curve.date.iloc[-1])-date.fromisoformat(curve.date.iloc[0])).days
    peak=np.maximum.accumulate(np.r_[10000.,v])[1:];dd=v/peak-1
    ix=int(np.argmin(dd));peakval=peak[ix];prev_indices=[i for i,x in enumerate(v[:ix+1]) if abs(x-peakval)<1e-7]
    peakdate=curve.date.iloc[prev_indices[-1]] if prev_indices else curve.date.iloc[0]
    recovery=next((curve.date.iloc[j] for j in range(ix+1,len(v)) if v[j]>=peakval),None)
    weights=[]
    for row in curve.to_dict('records'):
        if 'holdings_json' not in row:continue
        held=json.loads(row['holdings_json']);marks=json.loads(row['marks_json']);weights.extend(q*marks[s]/row['equity'] for s,q in held.items())
    return {'experiment':experiment,'policy':policy,'scenario':scenario,'status':STATUS,'start':curve.date.iloc[0],'end':curve.date.iloc[-1],'starting_capital':10000,'ending_nav':v[-1],'return_pct':(v[-1]/10000-1)*100,'cagr_pct':None if experiment=='B_2026_YTD' else ((v[-1]/10000)**(365.25/days)-1)*100,'elapsed_trading_sessions':len(curve),'elapsed_calendar_days':days,'max_drawdown_pct':dd.min()*100,'peak_date':peakdate,'trough_date':curve.date.iloc[ix],'recovery_date':recovery,'recovery_calendar_days':(date.fromisoformat(recovery)-date.fromisoformat(peakdate)).days if recovery else None,'annualized_volatility_pct':float(np.std(ret,ddof=1)*np.sqrt(252)*100),'sharpe_zero_cash_rate':float(np.mean(ret)/np.std(ret,ddof=1)*np.sqrt(252)) if np.std(ret)>0 else None,'average_equity_exposure_pct':float(curve.exposure.mean()*100),'minimum_equity_exposure_pct':float(curve.exposure.min()*100),'maximum_position_weight_pct':max(weights)*100 if weights else None,'maximum_industry_weight_pct':None,'industry_attribution_status':'UNAVAILABLE_HISTORICAL_INDUSTRY','trade_count':len(tr),'total_cost_dollars':result.get('total_cost_dollars',0),'turnover_oneway_over_mean_nav':float(tr.gross.sum()/2/curve.equity.mean()) if len(tr) else 0,'cost_bps_per_side':bps,'additional_delay_sessions':delay,'excess_spy_pp':None}
def benchmark(frames,calendar,start,end,bps=20):
    f=frames['SPY'];days=[d for d in calendar if start<=d<=end];cash=10000.;qty=math.floor(cash/(f.loc[days[0],'raw_open']*(1+bps/10000)));gross=qty*f.loc[days[0],'raw_open'];cost=gross*bps/10000;cash-=gross+cost
    curve=[]
    for ds in days:
        qty*=float(f.loc[ds,'split']);cash+=qty*float(f.loc[ds,'dividend']);nav=cash+qty*float(f.loc[ds,'raw_close'])
        curve.append({'date':ds,'equity':nav,'cash':cash,'exposure':1-cash/nav,'positions':1,'cumulative_cost':cost,'holdings_json':json.dumps({'SPY':qty}),'marks_json':json.dumps({'SPY':float(f.loc[ds,'raw_close'])})})
    tr=pd.DataFrame([{'date':days[0],'ticker':'SPY','side':'BUY','shares':qty,'nominal_open':f.loc[days[0],'raw_open'],'gross':gross,'cost':cost,'cash_after':10000.-gross-cost}])
    return {'total_cost_dollars':cost},pd.DataFrame(curve),tr
def main():
    prepared=OUT/'extended_prepared.pkl' if (OUT/'extended_prepared.pkl').exists() else OUT/'archive_prepared.pkl'
    frames,panel,calendar=pickle.load(open(prepared,'rb'))
    cfg=json.loads((OUT/'frozen_config.json').read_text());original=cfg['configuration']
    ref,*_=b.simulate(original,frames,panel,calendar)
    checked,*_=SIM(original,frames,panel,calendar)
    for k in ('net_return_pct','max_dd_pct','total_cost_dollars','trade_count'):assert abs(ref[k]-checked[k])<1e-7
    final=calendar[-1]
    periods=[('A_2025','2025-01-02','2025-12-31'),('B_2026_YTD','2026-01-02',final),('C_continuous','2025-01-02',final)]
    nav=[];trades=[];holds=[];summ=[];monthly=[];contributions=[];signals=[];robust=[]
    def run(experiment,start,end,policy='original',scenario='baseline',bps=20,delay=0,exclude=()):
        conf=dict(original,delay_sessions=delay)
        if policy!='original':conf.update(next(v for v in cfg['retention_variants'] if v['name']==policy));conf['name']=original['name']
        result,curve,tr,rolling,sig=SIM(conf,frames,panel,calendar,start=start,end=end,cost_bps=bps,exclude=exclude)
        for row in curve.to_dict('records'):
            for sym in json.loads(row['holdings_json']):assert row['date'] in frames[sym].index,('Missing held mark',sym,row['date'])
        m=metrics(curve,tr,result,experiment,policy,scenario,bps,delay);m['excluded_hindsight_names']='|'.join(exclude)
        if scenario!='baseline':robust.append(m);return result
        summ.append(m)
        nav.extend({'experiment':experiment,'policy':policy,'status':STATUS,**r} for r in curve.drop(columns=['holdings_json','marks_json']).to_dict('records'))
        trades.extend({'experiment':experiment,'policy':policy,'status':STATUS,**r} for r in tr.to_dict('records'))
        signals.extend({'experiment':experiment,'policy':policy,'status':STATUS,**r} for r in sig.to_dict('records'))
        basis=defaultdict(float);realized=defaultdict(float);owned={};bytr={ds:g.to_dict('records') for ds,g in tr.groupby('date')} if len(tr) else {};previous=10000.
        for r in curve.to_dict('records'):
            held=json.loads(r['holdings_json']);marks=json.loads(r['marks_json'])
            for t in bytr.get(r['date'],[]):
                s=t['ticker'];q=t['shares']
                if t['side']=='BUY':basis[s]+=t['gross']+t['cost'];owned[s]=owned.get(s,0)+q
                else:
                    alloc=basis[s]*q/owned[s] if owned.get(s,0) else 0;realized[s]+=t['gross']-t['cost']-alloc;basis[s]-=alloc;owned[s]=owned.get(s,0)-q
            for s,q in held.items():holds.append({'experiment':experiment,'policy':policy,'date':r['date'],'ticker':s,'shares':q,'nominal_close':marks[s],'value':q*marks[s],'weight_pct':q*marks[s]/r['equity']*100,'cost_basis_trade_only':basis[s],'unrealized_pnl_trade_only':q*marks[s]-basis[s],'realized_pnl_trade_only':realized[s],'industry':None,'status':STATUS})
        for month,g in curve.groupby(curve.date.str[:7]):
            tm=tr[tr.date.str[:7]==month] if len(tr) else tr
            monthly.append({'experiment':experiment,'policy':policy,'month':month,'return_pct':(g.equity.iloc[-1]/previous-1)*100,'ending_nav':g.equity.iloc[-1],'average_equity_exposure_pct':g.exposure.mean()*100,'trade_count':len(tm),'turnover_oneway_over_mean_nav':tm.gross.sum()/2/g.equity.mean() if len(tm) else 0,'cost_dollars':tm.cost.sum() if len(tm) else 0,'status':STATUS});previous=g.equity.iloc[-1]
        for s,value in result['pnl_by_ticker'].items():contributions.append({'experiment':experiment,'policy':policy,'ticker':s,'net_profit':value,'industry':None,'status':STATUS})
        return result
    for experiment,start,end in periods:
        results={}
        for policy in ['original']+[v['name'] for v in cfg['retention_variants']]:results[policy]=run(experiment,start,end,policy)
        rr,cc,tt=benchmark(frames,calendar,start,end);mm=metrics(cc,tt,rr,experiment,'SPY','baseline',20,0);summ.append(mm)
        nav.extend({'experiment':experiment,'policy':'SPY','status':STATUS,**r} for r in cc.drop(columns=['holdings_json','marks_json']).to_dict('records'))
        trades.extend({'experiment':experiment,'policy':'SPY','status':STATUS,**r} for r in tt.to_dict('records'))
        prev=10000.
        for month,g in cc.groupby(cc.date.str[:7]):monthly.append({'experiment':experiment,'policy':'SPY','month':month,'return_pct':(g.equity.iloc[-1]/prev-1)*100,'ending_nav':g.equity.iloc[-1],'average_equity_exposure_pct':g.exposure.mean()*100,'trade_count':1 if month==start[:7] else 0,'turnover_oneway_over_mean_nav':None,'cost_dollars':rr['total_cost_dollars'] if month==start[:7] else 0,'status':STATUS});prev=g.equity.iloc[-1]
        for m in summ:
            if m['experiment']==experiment:m['excess_spy_pp']=m['return_pct']-mm['return_pct']
        run(experiment,start,end,scenario='100bps',bps=100)
        for delay in [1,5,20]:run(experiment,start,end,scenario=f'additional_delay_{delay}',delay=delay)
        winner=max(results['original']['pnl_by_ticker'],key=results['original']['pnl_by_ticker'].get)
        run(experiment,start,end,scenario='hindsight_largest_winner_exclusion',exclude=[winner])
        robust.append({'experiment':experiment,'policy':'original','scenario':'hindsight_strongest_industry_exclusion','status':'BLOCKED_HISTORICAL_INDUSTRY','return_pct':None,'max_drawdown_pct':None})
    for name,data in [('daily_nav.csv',nav),('trades.csv',trades),('holdings.csv',holds),('portfolio_comparison.csv',summ),('monthly_performance.csv',monthly),('stock_profit_contribution.csv',contributions),('signals.csv',signals),('robustness_results.csv',robust)]:pd.DataFrame(data).to_csv(OUT/name,index=False)
    pd.DataFrame(summ)[['experiment','policy','status','max_drawdown_pct','peak_date','trough_date','recovery_date','recovery_calendar_days']].to_csv(OUT/'drawdown_analysis.csv',index=False)
    b.dump(OUT/'replay_results.json',{'status':STATUS,'periods':periods,'latest_completed_session_requested':'2026-10-09','latest_available_archive_session':'2026-10-01','extension_status':'PUBLIC_VENDOR_EXTENSION' if final>'2026-10-01' else 'UNAVAILABLE','accounts':summ,'industry_attribution':'BLOCKED; no current sectors relabeled as industries','instrumentation_numerically_equivalent':True})
    print(pd.DataFrame(summ)[['experiment','policy','return_pct','max_drawdown_pct']].to_string(index=False),flush=True)

if __name__=='__main__':main()
