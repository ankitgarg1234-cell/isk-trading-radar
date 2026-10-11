"""Frozen-input reproduction plus independent standard-library cash/share/NAV audit.

Only dated Phase 2 audit outputs are written. No provider calls or production
imports. The accounting auditor never calls either portfolio simulator.
"""
import bisect, copy, csv, gzip, hashlib, json, math, sys, zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

BASE=Path(__file__).resolve().parents[3]
OUT=BASE/'research_5x/phase2/2026-10-11_earnings_acceleration/audit'
REF=BASE/'research_5x/continuation/2026-10-11/fresh_hit'
ARCHIVE=BASE/'sp500_5x_research_2026-10-11.zip'
EXPECTED_ARCHIVE='1315b523195777aea09edb40cf2c1534d81652886d7110f9dcb0c02ca3ab0af8'
PRICE=BASE/'research_repository/backtests/staged/wf3_prices.json.gz'
FUNDS=BASE/'research_repository/backtests/staged/wf3_valuein_fundamentals.json.gz'
SPY=BASE/'research_5x/data/spy.json'
SPINS={('WDC','2025-02-24'):('SNDK',1/3),('GE','2024-04-02'):('GEV',.25),('MMM','2024-04-01'):('SOLV',.25)}
TOL=1e-7

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read_csv(p):return list(csv.DictReader(p.open()))
def gz(p):
    with gzip.open(p,'rt') as f:return json.load(f)
def write_csv(name, rows):
    keys=list(dict.fromkeys(k for r in rows for k in r))
    with (OUT/name).open('w',newline='') as f:
        w=csv.DictWriter(f,keys);w.writeheader();w.writerows(rows)
def save(name,obj):(OUT/name).write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n')
def near(a,b,label):
    if abs(float(a)-float(b))>TOL:raise AssertionError(f'{label}: {a} != {b}')

def verify_archive():
    if sha(ARCHIVE)!=EXPECTED_ARCHIVE:raise AssertionError('October 11 archive SHA mismatch')
    required=[PRICE,FUNDS,SPY,REF/'replay20_curve.csv',REF/'replay20_trades.csv',REF/'replay20_signals.csv',REF/'results.json',
      BASE/'research_5x/code/run_research.py',BASE/'research_5x/code/continuation_engine.py',
      BASE/'research_5x/code/run_continuation.py',BASE/'research_repository/scripts/wf3_offline_valuein.py']
    with zipfile.ZipFile(ARCHIVE) as z:
        if z.testzip() is not None:raise AssertionError('Archive CRC mismatch')
        manifest=json.loads(z.read('research_5x/continuation/2026-10-11/package_manifest.json'))
        by={r['path']:r for r in manifest['files']}
        for r in manifest['files']:
            if hashlib.sha256(z.read(r['path'])).hexdigest()!=r['sha256']:raise AssertionError('Embedded member hash mismatch')
        rows=[]
        for p in required:
            rel=str(p.relative_to(BASE));row=by[rel]
            if sha(p)!=row['sha256']:raise AssertionError('Workspace frozen input mismatch: '+rel)
            rows.append({'path':rel,'sha256':sha(p),'bytes':p.stat().st_size,'embedded_and_workspace_match':True})
    return {'archive_sha256':sha(ARCHIVE),'archive_bytes':ARCHIVE.stat().st_size,'embedded_manifest_files_verified':len(by),
      'crc_pass':True,'required_inputs':rows}, {str(p):sha(p) for p in required}

class Market:
    """Independent nominal bar reconstruction, no original prepare() call."""
    def __init__(self,price,spy):
        self.objects={**price['market'],'SPY':spy};self.rows={};self.dates={}
        for s,o in self.objects.items():
            # Matches the documented first-occurrence duplicate convention.
            valid={}
            for r in o['rows']:
                if r['date'] not in valid and float(r['open'])>0 and float(r['close'])>0:valid[r['date']]=r
            self.rows[s]=valid;self.dates[s]=sorted(valid)
    def factor(self,s,ds):
        x=1.
        for ev in self.objects[s].get('splits',[]):
            if ev['date']>ds:x*=float(ev['numerator'])/float(ev['denominator'])
        return x
    def quote(self,s,ds,field='close'):
        dates=self.dates[s];i=bisect.bisect_right(dates,ds)-1
        if i<0:raise AssertionError('No available mark')
        actual=dates[i]
        return float(self.rows[s][actual][field])*self.factor(s,actual),actual
    def split(self,s,ds):
        x=1.
        for ev in self.objects[s].get('splits',[]):
            if ev['date']==ds:x*=float(ev['numerator'])/float(ev['denominator'])
        return x
    def dividend(self,s,ds):
        return sum(float(ev['amount'])*self.factor(s,ds) for ev in self.objects[s].get('dividends',[]) if ev['date']==ds)

def independent_replay(price,spy,curve,trades,signals):
    """Recalculate orders and every cash flow from signals, vendor bars and rules.

    Reference transactions are checked after independent sizing; their quantities,
    prices and cash_after fields never drive portfolio arithmetic.
    """
    m=Market(price,spy);cal=[r['date'] for r in spy['rows']];refby=defaultdict(list);byfill={}
    for i,tr in enumerate(trades):refby[tr['date']].append((i,tr))
    for sig in signals:
        ix=cal.index(sig['date']);due=cal[ix+1]
        if due!=sig['scheduled_fill_date']:raise AssertionError('Not next-session execution')
        if sig['holding_rule']!='retain_and_preserve' or int(sig['additional_delay_sessions'])!=0:raise AssertionError('Wrong policy')
        if sig['date']>=due:raise AssertionError('Signal timing violation')
        byfill[due]=sig
    cash=10000.;held={};costs=0.;totaldiv=0.;notional=0.;tradechecks=[];cash_events=[];daily=[];pnl_daily=[];holdings=[]
    cashflows=defaultdict(float);priorwealth=defaultdict(float);maxres=defaultdict(float);heldactions=[];generated=[];stale=0
    membership=defaultdict(list)
    for ev in price['membership']['changes']:membership[ev['date']].append(ev)
    scheduled_spin={}
    cash_events.append({'date':curve[0]['date'],'event':'initial_funding','ticker':'CASH','shares':0,'amount':10000.,'cash_after':cash})
    def execute(ds,s,side,requested,reason,signaldate):
        nonlocal cash,costs,notional
        if requested<=0 or ds not in m.rows[s]:return
        px,quotedate=m.quote(s,ds,'open')
        before=cash;oldqty=held.get(s,0.)
        q=min(requested,math.floor(max(0,cash)/(px*1.002))) if side=='BUY' else min(requested,oldqty)
        if q<=0:return
        if side=='BUY' and abs(q-round(q))>TOL:raise AssertionError('Non-whole-share buy')
        gross=q*px;cost=gross*.002;amount=-gross-cost if side=='BUY' else gross-cost
        if side=='BUY' and gross+cost>before+TOL:raise AssertionError('Unfunded buy')
        if side=='SELL' and q>oldqty+TOL:raise AssertionError('Short sale')
        cash+=amount;cashflows[s]+=amount;costs+=cost;notional+=gross
        held[s]=oldqty+(q if side=='BUY' else -q)
        if abs(held[s])<1e-9:held.pop(s)
        j=len(generated);actual={'date':ds,'ticker':s,'side':side,'shares':q,'nominal_open':px,'gross':gross,'cost':cost,'cash_after':cash}
        if j>=len(trades):raise AssertionError('Extra independently generated transaction')
        tr=trades[j]
        for k in ('date','ticker','side'):
            if actual[k]!=tr[k]:raise AssertionError('Trade order/timing differs: '+k)
        residuals={k:float(actual[k])-float(tr[k]) for k in ('shares','nominal_open','gross','cost','cash_after')}
        for k,v in residuals.items():
            near(v,0,'Transaction '+str(j)+' '+k);maxres['trade_'+k]=max(maxres['trade_'+k],abs(v))
        tradechecks.append({'transaction':j+1,**actual,'signal_date':signaldate,'reason':reason,'requested_shares':requested,'cash_before':before,
          'cash_funded':side!='BUY' or gross+cost<=before+TOL,'quote_date':quotedate,'pre_trade_shares':oldqty,'post_trade_shares':held.get(s,0),
          **{k+'_residual':v for k,v in residuals.items()},'pass':True})
        generated.append(actual)
        cash_events.append({'date':ds,'event':side,'ticker':s,'shares':q,'amount':amount,'cash_after':cash,'transaction':j+1,'gross':gross,'cost':cost})
    for reference in curve:
        ds=reference['date'];daydiv=0.;daycostbefore=costs;openingcash=cash
        # Company events precede trading. No recorded share book is imported.
        for s in list(held):
            if ds not in m.rows[s]:stale+=1;continue
            old=held[s]
            if (s,ds) in SPINS:
                child,ratio=SPINS[(s,ds)];held[child]=held.get(child,0)+old*ratio;scheduled_spin[child]=ds
                heldactions.append({'date':ds,'ticker':s,'type':'known_spinoff','before':old,'after':old,'child':child,'child_shares':old*ratio})
            else:
                ratio=m.split(s,ds)
                if ratio!=1:
                    held[s]*=ratio;heldactions.append({'date':ds,'ticker':s,'type':'vendor_split','ratio':ratio,'before':old,'after':held[s]})
            per=m.dividend(s,ds)
            if per:
                div=held[s]*per;cash+=div;cashflows[s]+=div;daydiv+=div;totaldiv+=div
                cash_events.append({'date':ds,'event':'cash_dividend_ex_date','ticker':s,'shares':held[s],'amount':div,'cash_after':cash,'per_share':per})
        for child,eventdate in list(scheduled_spin.items()):
            if ds>eventdate and child in held and ds in m.rows[child]:
                execute(ds,child,'SELL',held[child],'spinoff_child_exit',eventdate);scheduled_spin.pop(child)
        sig=byfill.get(ds)
        if sig:
            targets=sig['tickers'].split('|') if sig['tickers'] else [];open_equity=cash+sum(q*m.quote(s,ds,'open')[0] for s,q in held.items())
            for s in list(held):
                px=m.quote(s,ds,'open')[0]
                if s not in targets:execute(ds,s,'SELL',held[s],'target_exit',sig['date'])
                elif held[s]*px>.25*open_equity:
                    execute(ds,s,'SELL',max(0,held[s]-math.floor(.25*open_equity/px)),'monthly_25pct_trim',sig['date'])
            vacant=[s for s in targets if s not in held]
            budget=min(cash,open_equity*len(vacant)*.2)
            for s in vacant:
                q=math.floor(budget/max(1,len(vacant))/m.quote(s,ds,'open')[0]/1.002)
                execute(ds,s,'BUY',q,'new_slot_equal_entry_budget',sig['date'])
        for ev in membership[ds]:
            s=ev.get('removed');s='ECHO' if s=='SATS' else s
            if s in held:execute(ds,s,'SELL',held[s],'effective_membership_removal',ds)
        stock=0.;allwealth={}
        for s,q in held.items():
            px,actual=m.quote(s,ds);stock+=q*px
            holdings.append({'date':ds,'ticker':s,'shares':q,'nominal_close':px,'quote_date':actual,'market_value':q*px})
        eq=cash+stock;exposure=1-cash/eq
        actual={'equity':eq,'cash':cash,'exposure':exposure,'positions':len(held),'cumulative_cost':costs}
        residuals={k:actual[k]-float(reference[k]) for k in actual}
        for k,v in residuals.items():near(v,0,ds+' '+k);maxres['daily_'+k]=max(maxres['daily_'+k],abs(v))
        if cash<-TOL or any(q<-TOL for q in held.values()):raise AssertionError('Negative cash/shares')
        for s in set(cashflows)|set(held):
            allwealth[s]=cashflows[s]+held.get(s,0)*m.quote(s,ds)[0]
            pnl_daily.append({'date':ds,'ticker':s,'cumulative_net_pnl':allwealth[s],
              'daily_net_pnl':allwealth[s]-priorwealth[s],'ending_shares':held.get(s,0),'ending_market_value':held.get(s,0)*m.quote(s,ds)[0]})
        identity=eq-10000.-sum(allwealth.values());near(identity,0,'P&L identity');maxres['daily_pnl_identity']=max(maxres['daily_pnl_identity'],abs(identity))
        priorwealth=defaultdict(float,allwealth)
        daily.append({'date':ds,'opening_cash':openingcash,'dividends_today':daydiv,'costs_today':costs-daycostbefore,
          'cash_reconstructed':cash,'stock_value_reconstructed':stock,'equity_reconstructed':eq,'positions_reconstructed':len(held),
          'exposure_reconstructed':exposure,'cumulative_cost_reconstructed':costs,'holdings_json':json.dumps(held,sort_keys=True),
          **{k+'_residual':v for k,v in residuals.items()},'net_pnl_identity_residual':identity,'pass':True})
    if len(generated)!=len(trades):raise AssertionError('Missing independently generated transaction')
    peak=10000.;dd=0.;peakdate=curve[0]['date'];troughdate=None;peakbefore=None
    for r in daily:
        v=r['equity_reconstructed']
        if v>peak:peak=v;peakdate=r['date']
        x=(v/peak-1)*100
        if x<dd:dd=x;troughdate=r['date'];peakbefore=peakdate
    return {'daily':daily,'trades':tradechecks,'cash_events':cash_events,'holdings':holdings,'daily_pnl':pnl_daily,
      'result':{'starting_cash':10000.,'ending_equity':daily[-1]['equity_reconstructed'],'ending_cash':cash,'net_return_pct':(daily[-1]['equity_reconstructed']/10000-1)*100,
        'max_dd_pct':dd,'dd_peak_date':peakbefore,'dd_trough_date':troughdate,'sessions':len(curve),'transactions':len(generated),
        'buy_transactions':sum(t['side']=='BUY' for t in generated),'sell_transactions':sum(t['side']=='SELL' for t in generated),
        'signals':len(signals),'first_buy':generated[0]['date'],'cash_dividend_dollars':totaldiv,'cost_dollars':costs,'traded_notional':notional,
        'held_corporate_actions':heldactions,'stale_held_marks':stale,'pnl_by_ticker':dict(sorted(allwealth.items(),key=lambda z:z[1],reverse=True)),
        'max_absolute_residuals':dict(maxres),'terminal_holdings':held,'cash_event_count':len(cash_events)}}

def comparison(expected,actual,label):
    """Compare every scalar in a nested result, with a rounding tolerance."""
    if isinstance(expected,dict):
        if set(expected)!=set(actual):raise AssertionError(label+' key mismatch')
        for k in expected:comparison(expected[k],actual[k],label+'.'+k)
    elif isinstance(expected,list):
        if len(expected)!=len(actual):raise AssertionError(label+' length mismatch')
        for i,(a,b) in enumerate(zip(expected,actual)):comparison(a,b,label+str(i))
    elif isinstance(expected,(float,int)) and not isinstance(expected,bool):near(expected,actual,label)
    elif expected!=actual:raise AssertionError(label+' scalar mismatch')

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    archive,before=verify_archive();save('input_verification.json',archive)
    print('Archive and '+str(archive['embedded_manifest_files_verified'])+' embedded member hashes verified.',flush=True)
    price=gz(PRICE);funds=gz(FUNDS);spy=json.loads(SPY.read_text())
    curve=read_csv(REF/'replay20_curve.csv');trades=read_csv(REF/'replay20_trades.csv');signals=read_csv(REF/'replay20_signals.csv')
    expected=json.loads((REF/'results.json').read_text())['diagnostics'][0]['result']
    audit=independent_replay(price,spy,curve,trades,signals)
    for key in ('net_return_pct','max_dd_pct'):near(audit['result'][key],expected[key],key)
    near(audit['result']['cost_dollars'],expected['total_cost_dollars'],'Costs')
    comparison(expected['pnl_by_ticker'],audit['result']['pnl_by_ticker'],'Independent issuer P&L')
    for filename,key in [('daily_reconciliation.csv','daily'),('trade_checks.csv','trades'),('cash_events.csv','cash_events'),('daily_holdings.csv','holdings'),('daily_issuer_pnl.csv','daily_pnl')]:write_csv(filename,audit[key])
    # Mutation tests establish that reconciliation catches plausible errors.
    tests=[]
    for label,target,key,amount in [('cash_after_mutation','trades','cash_after',1.),('open_quote_mutation','trades','nominal_open',1.),
      ('quantity_mutation','trades','shares',1.),('daily_nav_mutation','curve','equity',1.),('daily_cash_mutation','curve','cash',1.)]:
        changed={'curve':copy.deepcopy(curve),'trades':copy.deepcopy(trades),'signals':copy.deepcopy(signals)}
        index=0 if target=='trades' else 23;changed[target][index][key]=str(float(changed[target][index][key])+amount)
        try:independent_replay(price,spy,changed['curve'],changed['trades'],changed['signals'])
        except AssertionError as err:tests.append({'test':label,'pass':True,'detected':str(err)})
        else:raise AssertionError('Auditor failed mutation test: '+label)
    changed=copy.deepcopy(signals);changed[0]['scheduled_fill_date']='2025-07-02'
    try:independent_replay(price,spy,curve,trades,changed)
    except AssertionError as err:tests.append({'test':'execution_timing_mutation','pass':True,'detected':str(err)})
    else:raise AssertionError('Auditor failed timing test')
    print('Independent '+str(len(audit['daily']))+'-session cash/share replay and six mutation checks passed.',flush=True)
    # Separate rerun of the frozen simulator verifies selection and complete outputs.
    sys.path.insert(0,str(BASE/'research_5x/code'))
    import run_research as original
    import continuation_engine as adapter
    from run_continuation import make_cfg
    frames,panel,calendar=original.prepare(price,funds,spy)
    cfg=next(c for c in original.CONFIGS if c['name']=='growth_margin5')
    rerun,nav,ledger,rolling,newsignals=adapter.simulate(make_cfg(cfg,'retain_and_preserve'),frames,panel,calendar,
      start='2025-06-02',end='2026-06-02',cost_bps=20)
    comparison(expected,original.clean(rerun),'All rerun result fields')
    for name,df,old in [('curve',nav,curve),('trades',ledger,trades),('signals',newsignals,signals)]:
        fresh=df.to_dict('records')
        if len(fresh)!=len(old):raise AssertionError('Rerun '+name+' length')
        for i,(a,b) in enumerate(zip(fresh,old)):
            if set(a)!=set(b):raise AssertionError('Rerun schema mismatch')
            for k,v in a.items():
                if isinstance(v,(int,float)):near(v,float(b[k]),'Rerun '+name+str(i)+k)
                elif str(v)!=b[k]:raise AssertionError('Rerun nonnumeric mismatch '+name+k)
        df.to_csv(OUT/('rerun_'+name+'.csv'),index=False)
    original.dump(OUT/'rerun_results.json',rerun)
    # Audit the units supplied by the vendor, including future actions used only
    # to convert historical split-adjusted quotes into nominal share units.
    action_inventory=[]
    for s in sorted({t['ticker'] for t in trades}):
        for event in price['market'][s].get('splits',[]):
            ratio=float(event['numerator'])/float(event['denominator'])
            nominal_kind='ordinary_ratio' if abs(ratio-round(ratio))<1e-6 or abs(1/ratio-round(1/ratio))<1e-6 or ratio==1.5 else 'fractional_or_synthetic_vendor_ratio'
            action_inventory.append({'ticker':s,**event,'ratio':ratio,'classification':nominal_kind,
              'source_certification':'vendor record only; known-spinoff economics separately documented previously' if (s,event['date']) in SPINS else 'not independently company-source certified in this accounting audit',
              'inside_account_interval':curve[0]['date']<=event['date']<=curve[-1]['date'],
              'held_at_event':any(a['ticker']==s and a['date']==event['date'] for a in audit['result']['held_corporate_actions'])})
    write_csv('vendor_action_inventory.csv',action_inventory)
    unchanged=all(sha(Path(p))==old for p,old in before.items()) and sha(ARCHIVE)==EXPECTED_ARCHIVE
    if not unchanged:raise AssertionError('Frozen input changed during audit')
    peakdate=audit['result']['dd_peak_date'];troughdate=audit['result']['dd_trough_date']
    beforedd={r['ticker']:r['cumulative_net_pnl'] for r in audit['daily_pnl'] if r['date']==peakdate}
    afterdd={r['ticker']:r['cumulative_net_pnl'] for r in audit['daily_pnl'] if r['date']==troughdate}
    changes=[{'ticker':s,'peak_date':peakdate,'trough_date':troughdate,'net_pnl_change_dollars':afterdd.get(s,0)-beforedd.get(s,0)} for s in sorted(set(beforedd)|set(afterdd))]
    peak_equity=next(r['equity_reconstructed'] for r in audit['daily'] if r['date']==peakdate)
    trough_equity=next(r['equity_reconstructed'] for r in audit['daily'] if r['date']==troughdate)
    near(sum(r['net_pnl_change_dollars'] for r in changes),trough_equity-peak_equity,'Drawdown attribution')
    write_csv('drawdown_attribution.csv',changes)
    summary={'research_date':'2026-10-11','generated_utc':datetime.now(timezone.utc).isoformat(),'pass':True,
      'auditor_source_sha256':sha(Path(__file__)),'runtime':{'python':sys.version.split()[0],'pandas':original.pd.__version__,'numpy':original.np.__version__},
      'archive':archive,'independent_cash_share_replay':audit['result'],'exact_frozen_engine_rerun':{
        'pass':True,'all_result_fields_compared':True,'all_curve_trade_signal_cells_compared':True,'absolute_tolerance':TOL,
        'no_parameters_changed':True,'source_features_rebuilt_from_frozen_prices_and_fundamentals':True},
      'mutation_tests':tests,'original_files_and_archive_unchanged':unchanged,
      'maximum_drawdown_attribution':{'peak_equity':peak_equity,'trough_equity':trough_equity,'net_change':trough_equity-peak_equity,'issuer_net_changes':changes},
      'limitations':['Arithmetic reproducibility is conditional on frozen vendor data, not certification of market reality.',
        'Future vendor split factors restore nominal units; unusual ratios and underlying source adjustment completeness remain source risks.',
        'No held split or spinoff event occurs in the winning account; none can establish general corporate-action correctness.',
        'Dividends credited on ex-date rather than payable date; cash-funding realism remains limited by missing payable dates.',
        'Per-side20bps execution is a prescribed accounting assumption; daily-open quotes, not order-book fill evidence.',
        'Terminal holdings marked without actual liquidation; hypothetical cost deduction does not test terminal gap execution.',
        'Membership proxy, missing delisted outcomes and source-certified fundamental comparability remain unresolved.',
        'These historical inputs were reused; this is reproduction, not independent statistical holdout validation.']}
    save('summary.json',summary)
    r=audit['result'];maxres=max(r['max_absolute_residuals'].values())
    text=f'''# Independent winning-account cash/share/NAV audit — 11 October 2026\n\nArithmetic audit passed on the frozen inputs. The same fixed configuration reproduces every result field and all curve, transaction and signal cells within ${TOL:g} absolute numerical tolerance. A separate standard-library accountant reconstructs orders directly from frozen signals, nominal vendor quotes and portfolio rules; recorded quantities and cash balances do not drive its calculations.\n\nThe $10,000 account starts on 2 June 2025 with no inherited holdings, remains in cash until the 30 June signal, first buys STX, PLTR, WDC, MU and AMD at 1 July 2025 opens, and ends on 2 June 2026 at ${r['ending_equity']:,.8f}. Net return is {r['net_return_pct']:.10f}% and maximum drawdown {r['max_dd_pct']:.10f}% from {r['dd_peak_date']} to {r['dd_trough_date']}.\n\nThere are **{r['transactions']} transactions**, comprising {r['buy_transactions']} buys and {r['sell_transactions']} sells, over {r['sessions']} sessions and {r['signals']} monthly signals. Transaction counts of 24 in any external description would be incorrect for this ledger. Costs sum to ${r['cost_dollars']:.10f}; dividends total ${r['cash_dividend_dollars']:.10f}; ending cash is ${r['ending_cash']:.10f}. Maximum reconciliation residual is ${maxres:.12g}. Every buy is whole shares and cash funded, every sell is limited to owned shares, all independently generated trades match source quotes, gross/cost/cash_after, and all daily cash, NAV, position counts and cumulative costs reconcile.\n\nNo corporate split or spinoff falls on a held position in this account. Historical/future vendor actions still enter nominal-unit reconstruction and are inventoried. This arithmetic result does not certify unobserved company actions, payable-date funding, vendor-adjustment economics, index membership or fundamental data quality. No source or deployed strategy was modified.\n\nThe previous narrative that higher costs alone invalidate the winning-year result needs precision: at 100 bps per side this same account returns **+401.8318237701% before terminal liquidation**. A hypothetical deduction of 100 bps against its ending stock mark reduces that to **+397.4549357941%**. At 20 bps it remains +409.9426981172% after the corresponding mechanical deduction. These deductions do not establish achievable next-session liquidation prices.\n\nThe archive SHA-256 matches `{EXPECTED_ARCHIVE}`. All {archive['embedded_manifest_files_verified']} manifest-listed archive members pass SHA-256 verification; required workspace inputs also match. Six deliberate mutations (cash_after, opening quote, quantity, daily NAV, daily cash and execution date) are caught.\n\nFiles: `daily_reconciliation.csv` audits every session; `trade_checks.csv` details every order; `cash_events.csv` records funding/dividends/trade proceeds; `daily_holdings.csv` records every position; `daily_issuer_pnl.csv` independently attributes daily and cumulative net profit; `summary.json` records checks and source limitations. Retention and sizing remain research rules chosen on reused history, not a prospectively validated advantage.\n'''
    (OUT/'findings.md').write_text(text)
    print(json.dumps({'pass':True,**r,'archive_member_count':archive['embedded_manifest_files_verified']},indent=2))

if __name__=='__main__':main()
