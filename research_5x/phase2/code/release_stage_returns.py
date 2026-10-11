"""Case-study event dates, next-session entries and strict calendar-year accounts."""
from phase2_bootstrap import e,ROOT,OUT
import pandas as pd,numpy as np,json,bisect,math

def main():
    prices=e.load_gz(e.REPO/'backtests/staged/wf3_prices.json.gz');funds=e.load_gz(e.REPO/'backtests/staged/wf3_valuein_fundamentals.json.gz')
    spy=json.loads((ROOT/'research_5x/data/spy.json').read_text())
    frames,_,_=e.prepare(prices,funds,spy)
    calendar=sorted(frames['SPY'].index);events=[]
    m=pd.read_csv(OUT/'sources/memory/quarter_timeline.csv')
    for r in m.to_dict('records'):
        events.append({'ticker':r['ticker'],'quarter':r['fiscal_quarter'],'release_date':r['release_date'],'source_url':r['source_url'],
          'revenue_yoy_pct':r['revenue_yoy_pct'],'revenue_acceleration_pp':r['revenue_yoy_acceleration_pp'],
          'operating_margin_pct':r['operating_margin_gaap_pct'],'company_guide_next_revenue_change_pct':r['next_quarter_guided_revenue_vs_actual_qoq_pct']})
    w=pd.read_csv(OUT/'sources/wdc/quarter_timeline.csv')
    for r in w.to_dict('records'):
        events.append({'ticker':'WDC','quarter':r['fiscal_quarter'],'release_date':r['release_date'],'source_url':r['release_url'],
          'revenue_yoy_pct':r['revenue_yoy_pct'],'revenue_acceleration_pp':None,'operating_margin_pct':r['operating_margin_gaap_pct'],
          'scope':r['economic_scope'],'company_guide_next_revenue_change_pct':None})
    rows=[];daily=[];trades=[]
    for event in events:
        ticker=event['ticker'];release=event['release_date'];idx=bisect.bisect_right(calendar,release)
        if idx>=len(calendar):continue
        start=calendar[idx];ann=e.anniversary(start).isoformat();f=frames[ticker]
        row={**event,'entry_date':start,'anniversary':ann,'case_selected_after_outcome':True}
        prior=f.loc[f.index<=release]
        for n in [63,126,252]:row['pre_r'+str(n)+'_pct']=float(prior.iloc[-1]['r'+str(n)]*100) if len(prior) else None
        if ann>calendar[-1]:row['label_status']='censored';rows.append(row);continue
        end=calendar[bisect.bisect_right(calendar,ann)-1];cash=10000.;held={};cost=0.;spins={};actions=[];path=[];stale=0
        def trade(sym,q,ds,side):
            nonlocal cash,cost
            px=float(frames[sym].loc[ds,'raw_open']);gross=q*px;c=gross*.002
            if side=='BUY':cash-=gross+c;held[sym]=held.get(sym,0)+q
            else:cash+=gross-c;held[sym]-=q
            cost+=c;trades.append({'ticker_case':ticker,'release_date':release,'date':ds,'ticker':sym,'side':side,'shares':q,'gross':gross,'cost':c,'cash_after':cash})
        for ds in calendar[idx:bisect.bisect_right(calendar,end)]:
            for sym,q in list(held.items()):
                if ds not in frames[sym].index:stale+=1;continue
                r=frames[sym].loc[ds]
                if (sym,ds) in e.SPINOFFS:
                    child,ratio=e.SPINOFFS[(sym,ds)];held[child]=held.get(child,0)+q*ratio;spins[child]=ds
                    actions.append({'date':ds,'ticker':sym,'child':child,'event':'known spinoff; fraction entitlement approximation'})
                elif r.split!=1:
                    held[sym]*=float(r.split);actions.append({'date':ds,'ticker':sym,'ratio':float(r.split),'event':'vendor split; economics not globally certified'})
                cash+=held[sym]*float(r.dividend)
            for sym,exdate in list(spins.items()):
                if ds>exdate and ds in frames[sym].index:
                    trade(sym,held[sym],ds,'SELL');spins.pop(sym)
            if ds==start:
                if ds not in f.index:break
                qty=math.floor(cash/float(f.loc[ds,'raw_open'])/1.002);trade(ticker,qty,ds,'BUY')
            nav=cash
            for sym,q in held.items():
                z=frames[sym].loc[frames[sym].index<=ds];nav+=q*float(z.iloc[-1].raw_close)
            assert cash>=-1e-6
            path.append(nav);daily.append({'ticker':ticker,'release_date':release,'date':ds,'nav':nav,'cash':cash})
        if not path:row['label_status']='entry_price_missing';rows.append(row);continue
        row.update({'label_status':'matured_case_account','end_date':end,'net_calendar_return_pct':(path[-1]/10000-1)*100,
          'max_dd_pct':float(np.min(np.array(path)/np.maximum.accumulate(np.r_[10000,path])[1:]-1)*100),
          'cost_dollars':cost,'stale_held_marks':stale,'corporate_action_events':json.dumps(actions),
          'terminal_mark_no_exit_cost':True})
        rows.append(row)
    dest=OUT/'stages';dest.mkdir(exist_ok=True)
    pd.DataFrame(rows).to_csv(dest/'release_entry_outcomes.csv',index=False)
    pd.DataFrame(daily).to_csv(dest/'case_nav.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    pd.DataFrame(trades).to_csv(dest/'case_trades.csv',index=False)
    e.dump(dest/'status.json',{'case_release_events':len(rows),'matured_accounts':sum(r['label_status']=='matured_case_account' for r in rows),
       'initial_capital':10000,'cost_bps_per_side':20,'release_policy':'First SPY session strictly after date, unknown release times conservatively ignored',
       'holding_policy':'Buyissueratnextopen,holdparent,knownspinoffchildsoldnextopen;nootherrotation;cashdividendsexdate',
       'inference':'Outcome-selected30events, overlappingreturns. Earlier-entry chronology only, not alpha or annual portfolio optimization.',
       'limits':['All frozen-source limitations','Someearly2023pre252momentum missing','Dividendspayabledateunresolved','Spinofffractionapproximation','WDCpre/postspinscopechanges','Historicalconsensusmissing']})
    print(pd.DataFrame(rows)[['ticker','quarter','release_date','entry_date','pre_r63_pct','net_calendar_return_pct','max_dd_pct']].to_string(index=False))
if __name__=='__main__':main()
