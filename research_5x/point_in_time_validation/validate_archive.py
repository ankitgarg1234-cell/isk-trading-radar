"""Reproduce evidence checks and BLOCKED schedules, not strategy simulations.

Standard library only. Never downloads data, imports archived trading engines,
changes their parameters, or connects to paper trading / brokers.
"""
from __future__ import annotations
import argparse
import calendar
import csv
import hashlib
import json
import math
import statistics
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PHASE = ROOT / 'evidence/research_5x/phase2/2026-10-11_earnings_acceleration'

def rows(path):
    with Path(path).open(newline='') as stream:
        return list(csv.DictReader(stream))

def write_csv(name, columns, records):
    with (ROOT / name).open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction='raise')
        writer.writeheader()
        writer.writerows(records)

def write_json(name, value):
    (ROOT / name).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')

def verify_sources():
    manifest = json.loads((ROOT / 'source_manifest.json').read_text())
    for source in manifest:
        raw = (ROOT / source['path']).read_bytes()
        assert len(raw) == source['bytes'], source['path']
        assert hashlib.sha256(raw).hexdigest() == source['sha256'], source['path']
        blob = b'blob ' + str(len(raw)).encode() + b'\0' + raw
        assert hashlib.sha1(blob).hexdigest() == source['git_blob_sha'], source['path']
    return len(manifest)

def check_winner(trades=None, holdings=None, cash_events=None, daily=None):
    """New accountant using archived quotes/events; does not certify their sources.

    Quantities come from archived trades, so this audits capital accounting only,
    not independent ranking, order generation or publication timing.
    """
    trades = trades if trades is not None else rows(PHASE / 'audit/trade_checks.csv')
    holdings = holdings if holdings is not None else rows(PHASE / 'audit/daily_holdings.csv')
    cash_events = cash_events if cash_events is not None else rows(PHASE / 'audit/cash_events.csv')
    daily = daily if daily is not None else rows(PHASE / 'audit/daily_reconciliation.csv')
    bytrade, byhold, byevent = defaultdict(list), defaultdict(list), defaultdict(list)
    for r in trades: bytrade[r['date']].append(r)
    for r in holdings: byhold[r['date']].append(r)
    for r in cash_events: byevent[r['date']].append(r)
    cash, owned, cost, peak = 10000., {}, 0., 10000.
    worst, navs, exposures, out = 0., [], [], []
    max_weight, top_share, residual = 0., 0., 0.
    total_dividends, pnl, purchase_net = 0., defaultdict(float), defaultdict(float)
    def equal(actual, expected):
        nonlocal residual
        assert math.isfinite(actual) and math.isfinite(expected)
        residual = max(residual, abs(actual - expected))
        assert abs(actual - expected) <= 1e-7, (actual, expected)
    for day in daily:
        ds = day['date']
        equal(cash, float(day['opening_cash']))
        for event in byevent[ds]:
            if event['event'] == 'cash_dividend_ex_date':
                amount = float(event['amount'])
                equal(float(event['shares']), owned.get(event['ticker'], 0))
                equal(amount, owned.get(event['ticker'], 0) * float(event['per_share']))
                cash += amount
                pnl[event['ticker']] += amount
                total_dividends += amount
        for trade in bytrade[ds]:
            ticker = trade['ticker']
            q, px = float(trade['shares']), float(trade['nominal_open'])
            assert q > 0 and q.is_integer() and px > 0
            assert trade['signal_date'] < ds, 'Signal not before execution date'
            equal(cash, float(trade['cash_before']))
            gross, fee = q * px, q * px * .002
            equal(gross, float(trade['gross']))
            equal(fee, float(trade['cost']))
            cost += fee
            if trade['side'] == 'BUY':
                assert cash + 1e-7 >= gross + fee
                owned[ticker] = owned.get(ticker, 0) + q
                cash -= gross + fee
                purchase_net[ticker] += gross + fee
            else:
                assert trade['side'] == 'SELL' and owned.get(ticker, 0) >= q
                owned[ticker] -= q
                cash += gross - fee
                pnl[ticker] += gross - fee
                if owned[ticker] == 0: del owned[ticker]
            equal(cash, float(trade['cash_after']))
        marks = {}
        assert len(byhold[ds]) == len(owned)
        for holding in byhold[ds]:
            ticker = holding['ticker']
            equal(float(holding['shares']), owned[ticker])
            assert holding['quote_date'] == ds
            value = owned[ticker] * float(holding['nominal_close'])
            equal(value, float(holding['market_value']))
            marks[ticker] = value
        stock_value = sum(marks.values())
        nav = cash + stock_value
        equal(cash, float(day['cash_reconstructed']))
        equal(stock_value, float(day['stock_value_reconstructed']))
        equal(nav, float(day['equity_reconstructed']))
        equal(cost, float(day['cumulative_cost_reconstructed']))
        assert cash >= -1e-7 and nav > 0
        peak = max(peak, nav)
        drawdown = (nav / peak - 1) * 100
        worst = min(worst, drawdown)
        navs.append(nav)
        exposure = stock_value / nav * 100
        exposures.append(exposure)
        max_weight = max([max_weight] + [v / nav * 100 for v in marks.values()])
        top_share = max(top_share, sum(marks.get(t, 0) for t in ('STX', 'WDC', 'MU', 'SNDK')) / nav * 100)
        out.append({'date': ds, 'nav': nav, 'cash': cash, 'equity_exposure_pct': exposure, 'drawdown_pct': drawdown, 'status': 'ARCHIVED_ARITHMETIC_ONLY'})
    for t, value in marks.items(): pnl[t] += value
    for t, value in purchase_net.items(): pnl[t] -= value
    equal(navs[-1] - 10000, sum(pnl.values()))
    positive = sum(max(v, 0) for v in pnl.values())
    top3 = sum(sorted((max(v, 0) for v in pnl.values()), reverse=True)[:3]) / positive * 100
    return {'status': 'PASS_ARITHMETIC_ONLY', 'start': daily[0]['date'], 'end': daily[-1]['date'], 'sessions': len(daily), 'trades': len(trades), 'ending_nav': navs[-1], 'return_pct': (navs[-1] / 10000 - 1) * 100, 'max_drawdown_pct': worst, 'cost_dollars': cost, 'cash_dividends': total_dividends, 'ending_cash': cash, 'average_equity_exposure_pct': statistics.mean(exposures), 'minimum_equity_exposure_pct': min(exposures), 'maximum_position_weight_pct': max_weight, 'maximum_storage_memory_cluster_weight_pct': top_share, 'top3_share_positive_pnl_pct': top3, 'pnl_by_ticker': dict(pnl), 'maximum_residual_dollars': residual, 'limitations': 'Published quotes/events and trade quantities are inputs. No independent prices, signal selection or PIT data certification. Window extends into 2026, outside requested evaluation.'}, out

def evaluate_gate(config):
    missing = [g['id'] for g in config['gates'] if g['pass'] is not True]
    assert config.get('not_a_backtest') is True
    return {'status': 'BLOCKED' if missing else 'ADMISSION_REVIEW_REQUIRED', 'blocking_gates': missing, 'strategy_simulations_executed': 0, 'classification': 'Insufficient data', 'untouched_2022_2025': False, 'note': 'Passing declared gates never constitutes a simulated or independently validated result; this program has no strategy execution engine.'}

METRICS = ['ending_nav', 'return_pct', 'cumulative_return_pct', 'cagr_pct', 'best_rolling12_return_pct', 'median_rolling12_return_pct', 'worst_rolling12_return_pct', 'worst_complete_calendar_year_return_pct', 'max_drawdown_pct', 'average_equity_exposure_pct', 'minimum_equity_exposure_pct', 'trade_count', 'turnover', 'transaction_cost_dollars', 'largest_stock_contributor', 'largest_industry_contributor', 'maximum_position_weight_pct', 'maximum_industry_weight_pct', 'excess_spy_pp']

def blocked_outputs(config):
    columns = ['strategy', 'strategy_name', 'account_type', 'start', 'end', 'starting_capital', 'status', 'reason'] + METRICS
    accounts = []
    for strategy in config['strategies']:
        for year in config['evaluation']['years'] + ['continuous']:
            start, end = (f'{year}-01-01', f'{year}-12-31') if year != 'continuous' else ('2022-01-01', '2025-12-31')
            accounts.append({'strategy': strategy['id'], 'strategy_name': strategy['name'], 'account_type': 'independent_calendar' if year != 'continuous' else 'continuous_four_year', 'start': start, 'end': end, 'starting_capital': 10000, 'status': 'NOT_RUN_BLOCKED', 'reason': strategy['blocking_reason']})
    write_csv('annual_comparison.csv', columns, accounts)
    monthly = []
    for year in config['evaluation']['years']:
        for month in range(1, 13):
            for strategy in config['strategies']:
                monthly.append({'month': f'{year}-{month:02}', 'strategy': strategy['id'], 'status': 'NOT_RUN_BLOCKED', 'archive_panel_coverage': 'absent' if year < 2024 else 'proxy_only', 'reason': strategy['blocking_reason']})
    write_csv('monthly_leadership.csv', ['month', 'strategy', 'status', 'archive_panel_coverage', 'signal_timestamp', 'price_available_at', 'fundamental_available_at', 'membership_available_at', 'industry_available_at', 'sector_ranks', 'improving_industries', 'stock_ranks', 'emerging_leaders', 'deteriorating_holdings', 'allocation', 'retention', 'exit', 'actual_decision', 'subsequent_return_pct', 'reason'], monthly)
    write_csv('drawdown_analysis.csv', ['strategy', 'account_type', 'start', 'end', 'status', 'max_drawdown_pct', 'peak_date', 'trough_date', 'recovery_date', 'reason'], [{k: a[k] for k in ('strategy', 'account_type', 'start', 'end', 'status', 'reason')} for a in accounts])
    write_csv('stock_selection_audit.csv', ['strategy', 'account_id', 'security_id', 'ticker', 'signal_timestamp', 'feature', 'value', 'source_id', 'source_hash', 'available_at', 'period_end', 'publication_timestamp', 'membership_effective_at', 'rank', 'eligible', 'decision', 'reason'], [])
    write_csv('trades.csv', ['strategy', 'account_id', 'signal_timestamp', 'execution_timestamp', 'security_id', 'ticker', 'side', 'shares', 'raw_price', 'commission', 'slippage', 'gross', 'cash_after', 'reason'], [])
    write_csv('daily_portfolio_nav.csv', ['strategy', 'account_id', 'date', 'nav', 'cash', 'dividend_receivables', 'equity_value', 'equity_exposure_pct', 'cumulative_costs', 'status'], [])
    write_csv('holdings.csv', ['strategy', 'account_id', 'date', 'security_id', 'ticker', 'shares', 'raw_close', 'market_value', 'weight_pct', 'sector', 'industry'], [])

def archive_diagnostics():
    path = ROOT / 'evidence/research_5x/continuation/2026-10-11/experiments/results.json'
    result = json.loads(path.read_text())
    fields = ['candidate', 'scenario', 'rule', 'additional_delay_sessions', 'cost_bps_per_side', 'year', 'annual_return_pct', 'status', 'interpretation', 'source']
    annual = []
    experiments = []
    for i, scenario in enumerate(result['continuous_scenarios'], 1):
        spec, stats = scenario['spec'], scenario['result']
        for year, value in stats['annual_returns_pct'].items():
            annual.append({'candidate': spec['candidate'], 'scenario': spec['scenario'], 'rule': spec['rule'], 'additional_delay_sessions': spec['delay'], 'cost_bps_per_side': spec['bps'], 'year': year, 'annual_return_pct': value, 'status': 'INHERITED_UNCERTIFIED_DIAGNOSTIC', 'interpretation': 'Continuous account annual slice; not independent January reset. 2026 incomplete; not a 2022–2025 validation result.', 'source': str(path.relative_to(ROOT))})
        experiments.append({'id': f'ARCHIVE-{i:03}', 'spec': spec, 'status': 'PREVIOUS_RETROSPECTIVE_RESULT_ONLY', 'new_run': False})
    write_csv('archived_annual_diagnostics.csv', fields, annual)
    write_json('archived_experiment_registry.json', experiments)
    retention = rows(PHASE / 'retention/accounts.csv')
    comparison = []
    for policy in sorted({r['policy'] for r in retention}):
        for bps in (20, 100):
            group = [r for r in retention if r['policy'] == policy and int(r['bps']) == bps]
            returns = [float(r['return_pct']) for r in group]
            comparison.append({'policy': policy, 'bps': bps, 'overlapping_accounts': len(group), 'at_least_80_pct': sum(r >= 80 for r in returns), 'at_least_400_pct': sum(r >= 400 for r in returns), 'median_return_pct': statistics.median(returns), 'worst_return_pct': min(returns), 'largest_account_drawdown_pct': min(float(r['max_dd_pct']) for r in group), 'status': 'RETROSPECTIVE_OVERLAPPING_UNCERTIFIED'})
    write_csv('archived_retention_recheck.csv', list(comparison[0]), comparison)
    return len(experiments), comparison

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--strict', action='store_true', help='Exit 2 when strategy validation is blocked, after writing the evidence milestone.')
    args = parser.parse_args()
    verified = verify_sources()
    config = json.loads((ROOT / 'config.json').read_text())
    admission = evaluate_gate(config)
    admission['source_snapshots_verified'] = verified
    write_json('validation_status.json', admission)
    blocked_outputs(config)
    winner, curve = check_winner()
    write_json('archived_winner_recheck.json', winner)
    write_csv('archived_winner_nav.csv', list(curve[0]), curve)
    count, retention = archive_diagnostics()
    write_json('verification.json', {'source_hashes_verified': verified, 'archived_scenarios_indexed': count, 'archived_retention_accounts_reaggregated': sum(r['overlapping_accounts'] for r in retention), 'archived_winner_arithmetic': winner['status'], 'strategy_validation': admission['status'], 'new_strategy_simulations': 0})
    print(json.dumps({'status': admission['status'], 'classification': admission['classification'], 'source_snapshots_verified': verified, 'archive_experiments': count, 'winner_arithmetic': winner['status'], 'new_strategy_simulations': 0}))
    return 2 if args.strict and admission['status'] == 'BLOCKED' else 0

if __name__ == '__main__':
    raise SystemExit(main())
