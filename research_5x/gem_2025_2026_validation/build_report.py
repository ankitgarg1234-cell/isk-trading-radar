"""Generate transparent research report from outputs, without modifying rules."""
import json,html,gzip,hashlib
from pathlib import Path
import pandas as pd
O=Path(__file__).resolve().parent
m=pd.read_csv(O/'portfolio_comparison.csv');r=pd.read_csv(O/'robustness_results.csv');a=json.loads((O/'source_audit_summary.json').read_text());c=pd.read_csv(O/'stock_profit_contribution.csv');s=pd.read_csv(O/'stock_selection_audit.csv');sig=pd.read_csv(O/'signals.csv');full=pd.read_csv(O/'signal_audit.csv.gz');qual=pd.read_csv(O/'signal_audit.csv')
# Attach actual target choices by account to every eligible/rejected security.
choices={}
for x in sig.itertuples():
 for sym in str(x.tickers).split('|'):
  choices.setdefault((x.date,sym),[]).append(x.experiment+':'+x.policy)
s['actual_target_accounts']=s.apply(lambda x:'|'.join(choices.get((x.signal_date,x.ticker),[])),axis=1)
s['price_available_no_later_than']=s.signal_date+'T21:00:00+00:00'
s.to_csv(O/'stock_selection_audit.csv',index=False)
# Trade scheduling audit: signals precede monthly execution, separate benchmark.
t=pd.read_csv(O/'trades.csv');lookup={(x.experiment,x.policy,x.scheduled_fill_date):x.date for x in sig.itertuples()};out=[]
for x in t.to_dict('records'):
 ds=lookup.get((x['experiment'],x['policy'],x['date']));x['origin_signal_date']=ds;x['execution_price_source']='vendor nominal daily open';x['execution_assumption']='20bps charged per side; no intraday fill certification';x['signal_before_execution']=bool(ds and ds<x['date']) if x['policy']!='SPY' else True;x['decision_type']='monthly_target' if ds else 'benchmark_initial_buy' if x['policy']=='SPY' else 'membership_or_corporate_event_requires_review';out.append(x)
pd.DataFrame(out).to_csv(O/'trade_execution_audit.csv',index=False)
assert all(x['signal_before_execution'] for x in out)
selected_facts=qual[qual.fact_status=='VERIFIED_SAME_ACCESSION_QUARTER'];assert len(selected_facts)==len(qual)==1638
prices_missing=s[~s.price_present].groupby('ticker').signal_date.agg(['min','max','count']);prices_missing.to_csv(O/'missing_price_windows.csv')
provider_diffs=int((~qual.timestamp_matches_provider).sum());signal_day=int((pd.to_datetime(qual.sec_accepted_at,utc=True)>=pd.to_datetime(qual.signal_date,utc=True)).sum())
# Source inventory includes downloaded responses that were not needed in signal extracts.
manifest=[]
for group in ['facts','submissions','submission_parts','prices','probes']:
 for path in (O/'public_sources'/group).glob('*.json'):
  rec=json.loads(path.read_text());manifest.append({'group':group,'file':str(path.relative_to(O)),**{k:rec.get(k) for k in ['url','status','retrieved_at','bytes','sha256','error']}})
pd.DataFrame(manifest).to_csv(O/'acquisition_manifest.csv',index=False)
def table(df):return df.round(3).to_html(index=False,na_rep='Blocked / unavailable',escape=True,border=0)
def mdtable(df):
 cols=list(df);head='| '+' | '.join(cols)+' |\n| '+' | '.join(['---']*len(cols))+' |\n';return head+'\n'.join('| '+' | '.join('—' if pd.isna(x) else f'{x:.2f}' if isinstance(x,float) else str(x) for x in row)+' |' for row in df.itertuples(index=False,name=None))
main=m[m.policy.isin(['original','SPY'])][['experiment','policy','return_pct','max_drawdown_pct','ending_nav','cagr_pct']]
ret=m[['experiment','policy','return_pct','max_drawdown_pct','total_cost_dollars','trade_count','average_equity_exposure_pct','maximum_position_weight_pct']]
top=[]
for (experiment,policy),g in c.groupby(['experiment','policy']):
 z=g.sort_values('net_profit',ascending=False);positive=g.net_profit.clip(lower=0).sum();top.append({'experiment':experiment,'policy':policy,'largest_contributor':z.ticker.iloc[0],'largest_profit':z.net_profit.iloc[0],'top3_positive_profit_share_pct':z.net_profit.head(3).clip(lower=0).sum()/positive*100})
top=pd.DataFrame(top);top.to_csv(O/'concentration_attribution.csv',index=False)
readme=f'''# GEM 2025–2026 validation

**Final classification: Insufficient data for strict point-in-time validation.** Exact archived accounting/configuration reproduction passed. Narrowed accounts and SPY are **uncertified retrospective replays**, using archived inputs plus public October 2–9 prices. They are not certified performance or independent out-of-sample evidence.

{mdtable(main)}

2026 ends October 9, the latest completed session before the October 11 cutoff: 194 sessions. Its return is YTD, not annualized. Continuous C has 444 sessions /645 elapsed calendar days and no capital reset. A remains a complete calendar-year return; its mechanically calculated elapsed-period CAGR is not the calendar-year return.

All three previously documented retention variants are reported, without choosing one. Original-versus-SPY comparisons use identical $10,000 initial capital, dates, whole shares, 20bps costs and ex-date cash dividends. Independent accounts first wait for a newly generated January month-end signal; SPY buys at the first session open. The continuous account carries gains and positions through January 2026.

## What is verified

* Exact equality of archived return, drawdown, rolling-best, rolling-median, trade-count and costs: +413.531% full archived return, −29.240% MDD, +88.119% rolling median, +275.543% rolling best. This older reproduction includes 2024 only because it is necessary to check the stated archive metrics, not a new strategy comparison.
* Independent daily cash, share/basis, dividend and NAV reconciliation for 15 baseline accounts; profit contributions reconcile to ending NAV less $10,000.
* {a['audited_input_uses']:,} fundamental input uses audited; {a['status_counts']['VERIFIED_SAME_ACCESSION_QUARTER']:,} match direct quarterly values in the same SEC accession with actual acceptance before the signal. All {len(qual):,} qualifying-stock input uses pass these two checks.
* Actual signals precede baseline fills; held marks have exact-date quotes. Public quotes extend the endpoint to October 9.

## What remains incomplete

{a['missing_input_records']:,} missing quarter/period input records, {a['status_counts'].get('MISSING_SEC_DIRECT_QUARTER',0)} unverified direct-quarter uses, {a['status_counts'].get('VALUE_MISMATCH',0)} standard-tag mismatches and {a['status_counts'].get('ACCEPTANCE_UNVERIFIED_OR_AFTER_SIGNAL',0)} unresolved acceptance uses among competing securities; historical membership primary lineage, missing removed-company prices, nonstandard action economics, payable dates and historical industry identifiers. Verified qualifying inputs alone do not establish correct global ranking: omitted competitors could qualify or displace them.

Public EA prices were recovered and tested separately; restoring EA alone leaves the three original outcomes unchanged. AVB's public series has an unexplained 2.793:1 vendor event; it is not silently added. Yahoo and Stooq attempts did not recover usable history for the other active-window missing names. Exact security/date/field requirements appear in `pit_data_coverage.csv` and `missing_price_windows.csv`.

## Reproduce

From this directory, install `requirements.txt`, then run:

```sh
python archive_replay.py
python extend_prices.py
python run_experiments.py
python accounting_checks.py
python partial_price_reconstruction.py
python verify_artifacts.py
```

The committed public price caches reproduce the extension. To regenerate the original-accession source audit: `python acquire_sources.py`, `python audit_sources.py`, `python acquire_missing_submissions.py`, `python audit_sources.py`, `python complete_coverage.py`, `python build_report.py`, `python verify_artifacts.py`. SEC requests are throttled; full raw SEC responses are runtime caches excluded from Git. `sec_minimal_evidence.json.gz` retains exact used accession facts/acceptance times, and manifests retain response hashes and URLs. Source reacquisition may change current response hashes; compare original-accession observations, not today's aggregate statements. No current fundamentals are backfilled into past ranks.

`signal_audit.csv` covers all qualified original rankings; `signal_audit.csv.gz` covers all observed fundamental inputs including rejected names. `stock_selection_audit.csv` lists every reconstructed member at every ranking date, including absent-price names and actual target-account choices. `signals.csv` records original and retention allocations. `trades.csv`, `trade_execution_audit.csv`, `holdings.csv`, `position_pnl.csv`, `daily_nav.csv`, and monthly/contribution files supply account detail. `position_pnl.csv` includes exited names, realized net trading P&L, unrealized P&L and separately identified dividend income; the older `holdings.csv` explicitly labels trade-only basis fields. Industry columns remain blank, not filled from today's classification. Robustness results are diagnostics using the same uncertified inputs.

Production, paper positions, orders, deployment configuration, prior research and original source engines were not modified. Only this new research directory is committed on a dedicated branch.
'''
(O/'README.md').write_text(readme)
source=f'''# Data source audit

## Minimal decision-date reconstruction

The archive contains 539 price series from late 2022 through October 1, 2026, but only 2024+ prices are needed for these entries. The financial archive has 125,709 provider observations. No complete 2022–2023 market-wide reconstruction was demanded. Earlier financial records are used only where quarterly comparators require them. Reconstructed membership rather than current membership governs admission. Current SEC ticker data is an identity aid only. Membership changes recovered from a public historical GitHub CSV are secondary evidence, not issuer/index-provider certification; the attempted S&P announcement endpoint returned 404.

SEC companyfacts and submissions requests succeeded for 525 mapped issuer CIKs (1,050 responses), followed by 17 targeted older submission archive files. {a['public_sources_downloaded']} source responses are actually referenced by the used-input audit. Current companyfacts containers are filtered to the **original same accession, exact period and direct quarter**, never a later revision merely because it matches. Custom extension tags are not available from the standardized companyfacts API; unresolved fields require the original filing's XBRL instance/custom mapping. Direct facts, not silently reconstructed YTD differences, verify archived derived values where possible.

Full input-use results: {json.dumps(a['status_counts'])}. All 1,638 qualified input uses match same-accession direct quarters and are available before their signal. This certifies those individual observations only, not membership, complete rank competition, execution or total returns. The 42 value mismatches are AWK revenue standard-tag discrepancies; a custom-tag/scope bridge is needed before declaring the provider value wrong. The 28 remaining acceptance uses belong to two Citigroup accessions (`0000831001-24-000134`, `0000831001-25-000131`); recent and targeted archived submissions did not establish their acceptance times. See unresolved input extract for exact dates.

## Timestamp findings

{provider_diffs} of 1,638 qualifying input uses have provider timestamps different from SEC acceptance times, commonly a four-hour offset. The frozen original engine gates on filing date <=previous calendar day and uses acceptance text for ordering; it does **not** enforce actual acceptance timestamps. The audit independently checks SEC timestamps. Six COIN input uses at the October 31, 2025 ranking were accepted October 31 00:12:04 UTC, versus provider October 30 20:12:04+00:00. They were public before the signal but violate a literal previous-day UTC acceptance interpretation. Preserve this discrepancy; do not call the archived engine intrinsically timestamp-safe. The report's conservative signal timestamp is 21:01 UTC, after both winter/summer market closes; bars are conservatively available by 21:00 UTC.

## Prices, identifiers, actions and execution

{mdtable(prices_missing.reset_index())}

The table is the **actual decision-window** missing series list, not the archive's global failure list. Some failed names were no longer eligible by 2025 and require no new history. EA recovered successfully and was added only to a separately labeled reconstruction with unchanged results. AVB recovered but has a 2.793:1 vendor event in August 2026; adjustment economics are unresolved. The ten remaining names failed both Yahoo and Stooq probes. Responses are logged. No missing stock is implicitly certified as an ineligible investment.

Only required late-period baskets, qualifying September candidates and SPY were extended through October 9 using vendor OHLC and action records. No October month-end signal is generated; original historical features stay unchanged. Daily open price +cost is a modeled fill, not proof of actual order-book execution. Prior-20 quoted dollar volume participation is in `liquidity_exposure.csv`; vendor volume convention and removed-name liquidity remain uncertified. The actual baseline accounts have no held split/spinoff during this interval, checked independently, but WDC/SNDK pre-entry price continuity and universe corporate-action treatment still need primary reconciliation.

Dividends are actual archived/vendor ex-date amounts credited early on ex-date. For certification, obtain declaration/ex/record/payable dates and model a receivable until payable; do not silently call early cash reinvestment achievable. Delisting/merger economics are essential if a restored candidate enters. Historical identifiers must distinguish corporate events from ticker changes (including P/Everpure and SATS/ECHO). Industry codes are unavailable historically, so industry P&L, concentration and strongest-industry exclusion are explicitly blocked.

## What is needed to finish and costs

1. Resolve each exact missing input use in `pit_data_coverage.csv` using its original SEC accession: original filing/XBRL custom tags, revenue scope, quarter and comparator. Recover acceptance times for the two Citigroup accessions. SEC APIs are public, with no per-call fee; this run incurred no purchase.
2. Obtain the listed removed-name daily OHLCV through each membership exit plus 126-session warmup and any actual held exit/consideration. Primary merger announcements and SEC filings can establish economics; a survivorship-complete vendor such as CRSP can supply prices, permanent identifiers, distributions and delisting returns. CRSP public documentation was recovered, but no public verified quote for the needed slice was established: **commercial price unknown / quote required**, not an invented estimate.
3. Obtain primary historical S&P additions/removals with announcement and effective timestamps, original security identifiers, historical industry assignments, and dividends/payable dates. S&P/vendor licensing may be required; no verified price was found.
4. Compare vendor bars to independent primary/action-adjusted histories, certify WDC/SNDK and AVB discontinuities, and validate auction fills/liquidity under the stated costs.

The connected FinancialDatasets SPY extension request was rejected because the connected account has zero credits. No paid request or credit purchase was authorized or performed; public Yahoo prices supplied the extension instead. No verified unit-price quote was returned. This is a provider/account limitation, not proof that commercial data cannot solve the gaps.

Reconciliation passed independently. Certified PIT portfolio experiments remain blocked. Do not confuse these statuses.
'''
(O/'data_source_audit.md').write_text(source)
nav=pd.read_csv(O/'daily_nav.csv');lines={}
for (experiment,policy),g in nav[nav.policy.isin(['original','SPY'])].groupby(['experiment','policy']):lines[experiment+':'+policy]=g[['date','equity']].values.tolist()
blocks=[('Original versus SPY — uncertified',table(main)),('All documented retention variants — no selection',table(ret)),('Frozen robustness diagnostics — uncertified',table(r[['experiment','scenario','return_pct','max_drawdown_pct','excluded_hindsight_names','status']])),('Stock concentration and profit dependency',table(top)),('Exact missing-price windows',table(prices_missing.reset_index()))]
htmltext='''<!doctype html><html><head><meta charset="utf-8"><title>GEM validation 2025–2026</title><style>body{font:16px system-ui;max-width:1300px;margin:32px auto;padding:0 24px;color:#182131;background:#f7f9fc}h1{font-size:30px}.alert{padding:20px;border:3px solid #b54020;background:#fff0e7}table{border-collapse:collapse;width:100%;font-size:13px;overflow:auto}td,th{padding:9px;border-bottom:1px solid #ccd3df;text-align:left}section{background:white;padding:20px;margin:20px 0;overflow:auto}a{color:#1456a0}svg{width:100%;height:330px}small{color:#526074}</style></head><body><h1>GEM 2025–2026: exact replay, incomplete PIT certification</h1><div class="alert"><b>Final decision: Insufficient data for strict point-in-time validation.</b><p>Verified: exact archived configuration/accounting reproduction; independent cash/NAV reconciliation; qualifying SEC facts and acceptance before signals.</p><p>Uncertified: every reported portfolio return. Missing competitors, primary membership lineage, action/payable-date and execution verification prevent certification. These are retrospective observations, not independent out-of-sample evidence.</p></div><p>All accounts start with $10,000. 2026 ends October 9 (194 sessions); no YTD annualization. Continuous C runs 645 calendar days, with no reset. Original costs 20bps per side. No strategy thresholds were changed.</p><section><h2>Daily NAV — modeled, uncertified</h2><select id="period"><option>A_2025</option><option>B_2026_YTD</option><option>C_continuous</option></select><svg id="chart" viewBox="0 0 1000 330" role="img" aria-label="Original GEM and SPY daily NAV"></svg><p>Blue: original GEM; gray: SPY. Daily CSV contains all documented retention versions. Vertical scale changes by selected period.</p></section>'''
for title,body in blocks:htmltext+='<section><h2>'+html.escape(title)+'</h2>'+body+'</section>'
htmltext+=f'''<section><h2>Evidence and limits</h2><p>{a['status_counts']['VERIFIED_SAME_ACCESSION_QUARTER']:,}/{a['audited_input_uses']:,} audited input uses matched original-accession direct quarters with acceptance before signals. All 1,638 qualifying-stock input uses pass, but {a['missing_input_records']:,} absent quarter/period records and unresolved competitors prevent complete ranking proof. Provider timestamp offsets are disclosed in the source audit.</p><p>In the uncertified replay, 2025 exceeds 80%; removing its largest winner WDC reduces it to 76.44%. 2026 is unfinished and cannot supply a second independent annual result. Continuous CAGR is strong, but overlapping exposure to exceptional stocks and prior research reuse cannot establish sustainable 80% annual returns. Retention benefits depend on the variant and account; some drawdowns deepen beyond 30%.</p><p>EA-only public reconstruction leaves original results unchanged. AVB and removed companies remain unresolved. Strongest-industry exclusion and industry attribution are blocked, not replaced with current sectors.</p><p>No 12-month +400% target was optimized. No paper-trading or production code, positions or orders were changed.</p></section><section><h2>Files</h2>'''
for name in ['README.md','strategy_frozen_spec.md','data_source_audit.md','experiment_log.md','return_attribution.md','portfolio_comparison.csv','daily_nav.csv','monthly_performance.csv','trades.csv','trade_execution_audit.csv','holdings.csv','position_pnl.csv','signal_audit.csv','signal_audit.csv.gz','stock_selection_audit.csv','pit_data_coverage.csv','robustness_results.csv','drawdown_analysis.csv','stock_profit_contribution.csv','liquidity_exposure.csv','accounting_checks.csv','partial_reconstruction_results.csv','public_source_manifest.csv','sec_minimal_evidence.json.gz']:
 htmltext+=f'<p><a href="{name}">{name}</a></p>'
htmltext+='</section><script>const series='+json.dumps(lines,separators=(',',':'))+''';function draw(){let p=document.getElementById('period').value,a=series[p+':original'],b=series[p+':SPY'],all=a.concat(b),lo=Math.min(10000,...all.map(x=>x[1])),hi=Math.max(...all.map(x=>x[1]));let x=i=>70+i/(a.length-1)*900,y=v=>285-(v-lo)/(hi-lo)*250;let path=(s,col)=>'<polyline fill="none" stroke="'+col+'" stroke-width="2" points="'+s.map((v,i)=>x(i)+','+y(v[1])).join(' ')+'"/>';document.getElementById('chart').innerHTML='<text x="5" y="30">$'+Math.round(hi)+'</text><text x="5" y="285">$'+Math.round(lo)+'</text><text x="70" y="320">'+a[0][0]+'</text><text x="880" y="320">'+a[a.length-1][0]+'</text>'+path(a,'#165ecc')+path(b,'#697789');}document.getElementById('period').onchange=draw;draw();</script></body></html>'''
(O/'validation_report.html').write_text(htmltext)

for name in ['README.md','data_source_audit.md']:
 with (O/name).open('a') as stream:stream.write('\nRanking-gap triage narrows further competitor review to 943 security/date rows; see ranking_gap_review.csv and potentially_displacing_competitors.csv. This is triage, not full eligibility certification. Regenerate with python ranking_gap_review.py.\n')
print('Reports generated')
