"""Meaningful accounting-corruption and blocked-result integrity checks."""
import copy
import csv
import json
import subprocess
import sys
import unittest
from pathlib import Path
import validate_archive as audit

class ValidationTests(unittest.TestCase):
    def test_all_sources_match_git_objects(self):
        self.assertEqual(audit.verify_sources(), 27)

    def test_archived_winner_accounting(self):
        result, curve = audit.check_winner()
        self.assertEqual(result['trades'], 23)
        self.assertEqual(result['sessions'], 252)
        self.assertAlmostEqual(result['ending_nav'], 51081.807571243284)
        self.assertAlmostEqual(result['cost_dollars'], 136.8615806732178)
        self.assertAlmostEqual(result['max_drawdown_pct'], -17.99519606906851)
        self.assertEqual(curve[0]['cash'], 10000)

    def test_corrupted_accounting_is_rejected(self):
        trades = audit.rows(audit.PHASE / 'audit/trade_checks.csv')
        holdings = audit.rows(audit.PHASE / 'audit/daily_holdings.csv')
        daily = audit.rows(audit.PHASE / 'audit/daily_reconciliation.csv')
        mutations = [
            ('cash_after', '0'), ('nominal_open', '1'),
            ('shares', '999999'), ('signal_date', trades[0]['date']),
        ]
        for field, value in mutations:
            with self.subTest(field=field):
                changed = copy.deepcopy(trades)
                changed[0][field] = value
                with self.assertRaises(AssertionError): audit.check_winner(trades=changed)
        changed = copy.deepcopy(holdings)
        changed[0]['nominal_close'] = '0.01'
        with self.assertRaises(AssertionError): audit.check_winner(holdings=changed)
        changed = copy.deepcopy(daily)
        changed[-1]['equity_reconstructed'] = '60000'
        with self.assertRaises(AssertionError): audit.check_winner(daily=changed)

    def test_missing_results_are_not_zero_backtests(self):
        accounts = audit.rows(audit.ROOT / 'annual_comparison.csv')
        self.assertEqual(len(accounts), 30)
        self.assertEqual(sum(r['account_type'] == 'independent_calendar' for r in accounts), 24)
        self.assertEqual({r['strategy'] for r in accounts}, set('ABCDEF'))
        for record in accounts:
            self.assertEqual(record['status'], 'NOT_RUN_BLOCKED')
            for metric in audit.METRICS: self.assertEqual(record[metric], '')
        monthly = audit.rows(audit.ROOT / 'monthly_leadership.csv')
        self.assertEqual(len(monthly), 288)
        self.assertEqual(len({r['month'] for r in monthly}), 48)
        for record in monthly:
            self.assertEqual(record['status'], 'NOT_RUN_BLOCKED')
            self.assertEqual(record['actual_decision'], '')
        for name in ('trades.csv', 'stock_selection_audit.csv', 'daily_portfolio_nav.csv', 'holdings.csv'):
            self.assertEqual(audit.rows(audit.ROOT / name), [])

    def test_gate_cannot_claim_a_simulation(self):
        config = json.loads((audit.ROOT / 'config.json').read_text())
        gate = audit.evaluate_gate(config)
        self.assertEqual(gate['status'], 'BLOCKED')
        self.assertEqual(len(gate['blocking_gates']), 13)
        self.assertEqual(gate['strategy_simulations_executed'], 0)
        forged = copy.deepcopy(config)
        for g in forged['gates']: g['pass'] = True
        self.assertEqual(audit.evaluate_gate(forged)['status'], 'ADMISSION_REVIEW_REQUIRED')
        self.assertFalse(gate['untouched_2022_2025'])

    def test_retention_aggregates_match_archived_summary(self):
        original = audit.rows(audit.PHASE / 'retention/summary.csv')
        new = audit.rows(audit.ROOT / 'archived_retention_recheck.csv')
        lookup = {(r['policy'], r['bps']): r for r in original}
        self.assertEqual(sum(int(r['overlapping_accounts']) for r in new), 264)
        for record in new:
            prior = lookup[record['policy'], record['bps']]
            for metric in ('median_return_pct', 'worst_return_pct'):
                self.assertAlmostEqual(float(record[metric]), float(prior[metric]))
            self.assertEqual(int(record['at_least_400_pct']), int(prior['fivefold_accounts']))

if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ValidationTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    audit.write_json('test_results.json', {'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors), 'pass': result.wasSuccessful(), 'deliberate_corruptions_caught': 6 if result.wasSuccessful() else None, 'strategy_validation': 'BLOCKED', 'scope': 'Source provenance, archived capital-accounting arithmetic, and no-fabricated-result guards only; not investment strategy validation'})
    raise SystemExit(0 if result.wasSuccessful() else 1)
