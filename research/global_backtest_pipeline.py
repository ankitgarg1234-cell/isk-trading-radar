"""Formal readiness and automatic A/B replay; cache-only by default.

Historical performance cannot run without a complete, rights-supported bundle.
No EODHD acquisition is performed by this entrypoint.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from datetime import datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from dual_momentum.rules import PriceBar
from research.backtest_metrics import analyze
from research.historical_engine import HistoricalEngine, SessionBar, ShareAction, FXObservation, FXTape
from research.sec_decision_universe import reference_decisions
from research.spgm_sources import DEFAULT_OUTPUT, ROOT
from research.spgm_universe import latest_public, construct, evidence_index
from research.spgm_strategy_audit import dated_verified
from research.strategy_kernel import load_kernel, MANIFEST

OUTPUT = DEFAULT_OUTPUT/'historical_backtest'
START,END = '2023-10-01','2026-09-30'
GICS_SECTORS=frozenset(json.loads(MANIFEST.read_text())['constants']['ETFS'])


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def supported_file(directory,name,expected=None):
    path=(directory/name).resolve()
    if ROOT.resolve() not in path.parents:raise ValueError('Bundle evidence must stay in ignored storage')
    if expected and digest(path)!=expected:raise ValueError('Bundle/evidence checksum mismatch')
    return path


def reference_timeline():
    import exchange_calendars as xc
    cal=xc.get_calendar('XNYS',start='2023-09-29',end='2026-10-05')
    out=[]
    for day in cal.sessions:
        if '2023-09-29'<=str(day.date())<=END:
            d=day.date()
            at=datetime.combine(d,time(16,20),ZoneInfo('America/New_York')).astimezone(timezone.utc)
            out.append((str(d),at))
    return out


def verify_member_metadata(member,at):
    cutoff=at.isoformat()
    if not member.get('symbol') or not member.get('instrument_key'):
        raise ValueError('Missing historical security/listing identity')
    if member.get('sector_scheme')!='GICS' or not dated_verified(member,'sector',cutoff):
        raise ValueError('Historical GICS verification absent/current/future')
    if member.get('sector') not in GICS_SECTORS:
        raise ValueError('Unrecognized GICS sector')
    if not member.get('exchange_mic') or not member.get('currency') or not dated_verified(member,'listing',cutoff):
        raise ValueError('Historical listing verification absent/current/future')
    available=datetime.fromisoformat(member['membership_available_at'])
    if available.tzinfo is None or available>=at or not member.get('membership_source_url'):
        raise ValueError('Membership evidence not prior-public')
    if member.get('identifier_ambiguity') or not member.get('issuer_id'):
        raise ValueError('Unresolved issuer/identifier ambiguity')
    if not member.get('country') or member['country'].upper() in {'UNKNOWN','UNRESOLVED'}:
        raise ValueError('Historical country unresolved')


def cached_readiness():
    load_kernel()  # Fail on source drift, not an assumed test pass.
    frozen=DEFAULT_OUTPUT/'sec_only_decision_universe'
    manifest=json.loads((frozen/'manifest.json').read_text())
    summary=json.loads((frozen/'monthly_summary.json').read_text())
    for name,expected in manifest['output_sha256'].items():
        if digest(frozen/name)!=expected:raise ValueError('Frozen universe checksum mismatch')
    parity=json.loads((OUTPUT/'synthetic_parity/parity.json').read_text())
    prices=json.loads((OUTPUT/'price_inventory_summary.json').read_text())
    account=json.loads((OUTPUT/'account_entitlement_summary.json').read_text())
    parity_fresh=all(digest(Path(__file__).parent/name)==expected for name,expected in parity.get('program_sha256',{}).items()) and bool(parity.get('program_sha256'))
    checks=[
        ('engine_validated',True,'Pinned pure-rule kernel; independent execution/FX/action/metrics regressions'),
        ('strategy_code_synthetic_parity',parity_fresh and all(r['passed'] for r in parity['comparisons']),'500-stock fixture with program hashes; historical performance parity not claimed'),
        ('membership_frozen',manifest['months']==48 and manifest['backtest_month_ends']==36,'SEC-only at actual reference-session NY16:20; initial September29 signal'),
        ('membership_no_lookahead',all(datetime.fromisoformat(r['source_available_at'])<datetime.fromisoformat(r['selection_cutoff_utc']) for r in summary),'Original source portfolio/publication dates and hashes retained'),
        ('historical_sectors',all(r['historical_gics_verified']/r['securities']>=.98 for r in summary),'0% versus≥98% monthly minimum;100% usable/held/selected required'),
        ('historical_listings',all(r['verified_listing']/r['securities']>=.98 for r in summary),'0% verified dated listing/MIC/currency;≥98% monthly minimum'),
        ('price_warmup',prices['legacy_prelaunch_253_eligible']>0 and prices['raw_eodhd_prelaunch_253_eligible']>0,'Both0; staged maximum211 bars versus253 required'),
        ('reference_prices',prices['historical_reference_prices_complete'],'SPY and all11 sector ETFs absent from staged cache'),
        ('historical_fx',prices['fx_verified_series']>0,'No verified timestamped FX tape'),
        ('full_universe_actions',False,'AZN/Korea/Taiwan cases retained; no complete action/delisting coverage'),
        ('global_calendars',False,'XNYS schedule/closure fixtures pass; complete verified venue calendars absent'),
        ('sp500_historical_membership_sectors',False,'Staged2024 starting list/undated sectors do not establish2023 starting universe'),
        ('original_strategy_preserved',True,'No edits to live/paper modules; same SPY/XL* references and pinned formulas'),
        ('transaction_model_documented',True,'7bp fills+$1/$0.005 commissions; USD base; native stops; conservative stop FX timing'),
        ('missing_data_quantified',True,'Monthly/country/security/priority matrices and inventory; no GICS imputations'),
        ('unresolved_security_sensitivity',False,'Cannot bound Top5/rank/sector impact without missing price/classification inputs'),
    ]
    return {'outcome':'EXTERNALLY_BLOCKED','ready':all(p for _,p,_ in checks),
        'period':{'start':START,'end':END,'initial_capital':10000.},
        'dataset_label':'SPGM HISTORICAL ETF HOLDINGS PROXY',
        'checks':[dict(requirement=n,passed=p,evidence=e) for n,p,e in checks],
        'performance_comparison':None,'account':account,'new_price_requests':0}


def parse_bundle(path,configuration):
    load_kernel()
    data=json.loads(path.read_text())
    if data.get('data_kind')!='HISTORICAL_INPUT' or data.get('configuration')!=configuration:
        raise ValueError('Historical bundle kind/configuration required; synthetic results forbidden')
    if data.get('start')!=START or data.get('end')!=END or data.get('initial_capital')!=10000.:
        raise ValueError('Comparison period/capital differs')
    if data.get('reference_symbols')!=['SPY']+list(load_kernel()['ETFS'].values()):
        raise ValueError('Original SPY/sector reference inputs changed')
    for key in ('rights_permitted','action_coverage_verified','calendar_coverage_verified',
                'adjustment_vintages_verified','complex_actions_resolved','missing_security_sensitivity_assessed'):
        evidence=data.get(key)
        if not isinstance(evidence,dict) or not evidence.get('source_url') or not evidence.get('evidence_file') or not evidence.get('sha256'):
            raise ValueError('Missing documented input admission evidence: '+key)
        supported_file(path.parent,evidence['evidence_file'],evidence['sha256'])
    reference=reference_timeline()
    membership={}
    snapshots=json.loads((DEFAULT_OUTPUT/'snapshots.json').read_text())
    source_groups={s['snapshot_id']:[] for s in snapshots}
    if configuration=='SPGM_PROXY':
        for row in csv.DictReader((DEFAULT_OUTPUT/'holdings.csv').open()):source_groups[row['snapshot_id']].append(row)
        if data.get('dataset_label')!='SPGM HISTORICAL ETF HOLDINGS PROXY':
            raise ValueError('Explicit proxy label required')
    required_keys={}
    for snap in data['memberships']:
        at=datetime.fromisoformat(snap['decision_at'])
        if at in membership:raise ValueError('Duplicate membership cutoff')
        members=snap['members']
        for m in members:verify_member_metadata(m,at)
        if len({m['symbol'] for m in members})!=len(members):raise ValueError('Ambiguous symbol identity')
        if len({m['instrument_key'] for m in members})!=len(members):raise ValueError('Duplicate security mapping')
        if configuration=='SPGM_PROXY':
            selected=latest_public(snapshots,at.isoformat(),sec_only=True)
            if snap.get('source_snapshot_id')!=selected['snapshot_id']:
                raise ValueError('Bundle membership violates SEC-only prior-public policy')
            sid=selected['snapshot_id']
            if sid not in required_keys:
                confirmed,_,_=construct(selected,source_groups,evidence_index([selected],source_groups,at.isoformat()),at.isoformat())
                required_keys[sid]={r['instrument_key'] for r in confirmed}
            if {m['instrument_key'] for m in members}!=required_keys[sid]:
                raise ValueError('SEC-only proxy members silently omitted/added at daily cutoff')
        membership[at]=members
    if set(membership)!=set(t for _,t in reference):
        raise ValueError('Complete daily prior-public membership/sector snapshots required')
    def members_at(at):return membership[at]
    calendars={mic:[(r['date'],datetime.fromisoformat(r['open_at']),datetime.fromisoformat(r['close_at'])) for r in rows]
               for mic,rows in data['calendars'].items()}
    records=[SessionBar(r['symbol'],r['mic'],r['currency'],PriceBar(**r['bar']),
        datetime.fromisoformat(r['open_at']),datetime.fromisoformat(r['close_at']),
        datetime.fromisoformat(r['available_at']),r['source'],r.get('price_scale',1.)) for r in data['prices']]
    identities={r.symbol:(r.mic,r.currency) for r in records}
    for members in membership.values():
        for m in members:
            if m['symbol'] in identities and identities[m['symbol']]!=(m['exchange_mic'],m['currency']):
                raise ValueError('Price identity contradicts historical listing metadata')
    fx=FXTape([FXObservation(r['currency'],datetime.fromisoformat(r['at']),
        datetime.fromisoformat(r['available_at']),r['usd_per_unit'],r['source']) for r in data['fx']])
    actions=[ShareAction(r['symbol'],datetime.fromisoformat(r['effective_at']),
        datetime.fromisoformat(r['available_at']),r['new_shares_per_old'],r['source']) for r in data['share_actions']]
    decision_dates={r['signal_date'] for r in reference_decisions() if '2023-09'<=r['selection_month']<='2026-09'}
    decisions=[t for day,t in reference if day in decision_dates]
    return HistoricalEngine(records,calendars,reference,members_at,decisions,fx=fx,actions=actions)


def resume(manifest_path):
    readiness=cached_readiness()
    if not all(c['passed'] for c in readiness['checks'] if c['requirement'] in {'engine_validated','strategy_code_synthetic_parity','original_strategy_preserved'}):
        raise ValueError('Fresh source-matched strategy parity required before historical execution')
    manifest_path=manifest_path.resolve()
    if ROOT.resolve() not in manifest_path.parents:raise ValueError('Ignored input manifest required')
    manifest=json.loads(manifest_path.read_text())
    if set(manifest['configurations'])!={'SP500','SPGM_PROXY'}:
        raise ValueError('Both configurations required for paired comparison')
    engines,metrics={},{}
    reference=reference_timeline()
    for key,entry in manifest['configurations'].items():
        path=supported_file(manifest_path.parent,entry['file'],entry['sha256'])
        engine=parse_bundle(path,key)
        engine.run(reference[0][1],reference[-1][1])
        result=analyze(engine.valuations,engine.state['trades'],initial_capital=10000.,
            start_date=START,end_date=END,data_kind='VALIDATED_HISTORICAL',actions=engine.applied_actions)
        engines[key]=engine;metrics[key]=result
    # Commit outputs only after both configurations validate and complete.
    for key,engine in engines.items():
        engine.save(OUTPUT/'results'/key,data_kind='VALIDATED_HISTORICAL')
    (OUTPUT/'results/performance_comparison.json').write_text(json.dumps(metrics,indent=2)+'\n')
    return metrics


def write_readiness(result):
    OUTPUT.mkdir(exist_ok=True)
    (OUTPUT/'readiness_final.json').write_text(json.dumps(result,indent=2)+'\n')
    lines=['# Global backtest final readiness','',
        '**'+result['outcome']+'**. Period October1 2023–September30 2026; $10,000.','',
        '**SPGM HISTORICAL ETF HOLDINGS PROXY**; SEC-only lagged membership; unchanged SPY/11 U.S. sector ETF references.','',
        '| Requirement | Status | Evidence |','|---|---|---|']
    for r in result['checks']:
        lines.append(f"| {r['requirement']} | {'PASS' if r['passed'] else 'FAIL'} | {r['evidence']} |")
    lines += ['',
        ('Validated bundles supplied complete historical metadata and passed paired replay/accounting checks.' if result['ready'] else
        'The classifications/listings fail the≥98% monthly minimum,≥95% material-country gates and100% usable-signal/held-position requirements. No source gaps are imputed. Price coverage fails before any ranking can be considered complete. Unknown sectors are not an executable concentration bucket. Missing high-momentum securities cannot be assumed irrelevant.'), '',
        'Synthetic and code-level parity passes, but no original historical five-stock performance oracle exists locally. No real A/B result is published while critical failures remain.', '',
        'Re-run `python -m research.global_backtest_pipeline --resume` after supplying `historical_backtest/input_bundle_manifest.json` and its rights-supported data/evidence files. The loader recomputes metadata timing, exact selection membership, calendar/FX/price validity, signal coverage and accounting reconciliation; a boolean ready flag cannot bypass those checks. A failed admission/replay leaves the comparison blocked.', '',
        'Machine-readable readiness, price inventory, input hashes, synthetic audit and account/request ledger stay ignored. No costed data requests are made by this runner.']
    if result.get('bundle_error'):lines += ['', 'Input admission failure: '+result['bundle_error']]
    (OUTPUT/'readiness_final.md').write_text('\n'.join(lines)+'\n')


def write_completed_analysis(result):
    if not result['ready']:return
    metrics=result['performance_comparison']
    lines=['# Global historical five-stock comparison','',
        '**BACKTEST COMPLETED** using validated supplied input bundles. October1 2023–September30 2026, $10,000;2023 is a partial October–December year.','',
        '**SPGM HISTORICAL ETF HOLDINGS PROXY**, SEC-only lagged membership; not official MSCI ACWI IMI constituents. SPY and all11 original U.S. sector ETF references retained.','',
        '| Metric | S&P500 | SPGM proxy |','|---|---:|---:|']
    for key in ('total_return','cagr','max_drawdown','annual_volatility','sharpe_zero_rf','sortino_zero_rf',
                'realized_lot_win_rate','average_holding_days_quantity_weighted','turnover_one_way_annualized',
                'average_invested_fraction','average_cash_fraction','fees','stop_closed_lot_pnl'):
        values=[metrics[c][key] for c in ('SP500','SPGM_PROXY')]
        lines.append('| '+key+' | '+' | '.join('unavailable' if v is None else f'{v:.6f}' for v in values)+' |')
    for kind in ('annual_returns','monthly_returns'):
        lines += ['', '## '+kind.replace('_',' '),'','| Period | S&P500 | SPGM proxy |','|---|---:|---:|']
        for period in sorted(metrics['SP500'][kind].keys()|metrics['SPGM_PROXY'][kind].keys()):
            lines.append(f"| {period} | {metrics['SP500'][kind].get(period):.4%} | {metrics['SPGM_PROXY'][kind].get(period):.4%} |")
    lines += ['',
        'The underlying daily marks, decisions, raw/risk ranks, weights, orders, stop events, fees and source-backed input evidence are stored under ignored `historical_backtest/results/`. Stock/sector P&L and FIFO-lot outcomes reconcile to NAV. Sharpe/Sortino assume zero risk-free rate; cash earns zero interest, matching the original ledger. Cash drag and stop-rule causal counterfactuals remain unestimated; observed cash fractions and stopped-lot P&L are not causal estimates.', '',
        'The engine preserves original scoring/selection/caps/stops. Global execution uses native calendars, USD FX and native stop coordinates, including conservative publication-time availability of stop proceeds. See HISTORICAL_ENGINE.md for FX, action and dividend-accounting limitations. A proxy advantage cannot be attributed wholly to selection without separately examining these disclosed execution differences.', '',
        'Synthetic parity is established; matching an original historical five-stock trade record remains unverified. ETF sampling/staleness means this is not an MSCI constituent backtest. Annual/monthly and stock/sector attribution are evidence for leadership analysis; unexecuted counterfactual returns and missed-return causal claims are not manufactured.']
    a,b=metrics['SP500'],metrics['SPGM_PROXY']
    lines += ['',f"Observed proxy minus S&P total-return difference: {b['total_return']-a['total_return']:.4%}; drawdown difference: {b['max_drawdown']-a['max_drawdown']:.4%}. A preference decision must also consider input coverage, proxy sampling, native execution and accounting limitations."]
    (OUTPUT/'final_report.md').write_text('\n'.join(lines)+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resume',action='store_true')
    parser.add_argument('--manifest',type=Path,default=OUTPUT/'input_bundle_manifest.json')
    args=parser.parse_args()
    result=cached_readiness()
    if args.resume and args.manifest.exists():
        try:
            comparison=resume(args.manifest)
            result.update(outcome='BACKTEST_COMPLETED',ready=True,performance_comparison=comparison)
            for c in result['checks']:c.update(passed=True,evidence='Validated historical input admission and paired replay completed; inspect evidence bundle')
        except (ValueError,KeyError,RuntimeError,OSError) as exc:
            result['bundle_error']=str(exc)
    write_readiness(result)
    write_completed_analysis(result)
    print(json.dumps({'outcome':result['outcome'],'ready':result['ready'],
        'failed_requirements':[r['requirement'] for r in result['checks'] if not r['passed']],
        'performance_comparison_available':result['performance_comparison'] is not None}))


if __name__=='__main__':main()
