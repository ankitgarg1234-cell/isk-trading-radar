import unittest
from research.backtest_metrics import analyze


class MetricsTests(unittest.TestCase):
    def test_accounting_reconciliation_returns_and_attribution(self):
        rows = [dict(date='2024-01-02',at='2024-01-02T17:00:00+00:00',nav=999.,cash=499.,positions={'A':500.},sectors={'A':'Technology'}),
                dict(date='2024-01-03',at='2024-01-03T17:00:00+00:00',nav=1048.,cash=1048.,positions={},sectors={'A':'Technology'})]
        trades = [dict(date='2024-01-02',at='2024-01-02T09:00:00+00:00',symbol='A',side='BUY',shares=5,price_usd=100.,fee=1.,kind='MODELED_NEXT_OPEN'),
                  dict(date='2024-01-03',at='2024-01-03T09:00:00+00:00',symbol='A',side='SELL',shares=5,price_usd=110.,fee=1.,kind='MODELED_STOP')]
        r = analyze(rows,trades,initial_capital=1000.,start_date='2024-01-02',end_date='2024-01-03',data_kind='SYNTHETIC_FIXTURE')
        self.assertAlmostEqual(r['total_return'],.048)
        self.assertEqual(r['stock_pnl'],{'A':48.})
        self.assertEqual(r['fees'],2.)
        self.assertAlmostEqual(r['stop_closed_lot_pnl'],48.)
        self.assertEqual(r['attribution_residual'],0.)
        self.assertIsNone(r['stop_counterfactual_impact'])

    def test_unexplained_cashflow_prevents_attribution_claim(self):
        rows = [dict(date='2024-01-02',at='2024-01-02T17:00:00+00:00',nav=1010.,cash=1010.,positions={},sectors={})]
        with self.assertRaisesRegex(ValueError,'reconcile'):
            analyze(rows,[],initial_capital=1000.,start_date='2024-01-02',end_date='2024-01-02',data_kind='SYNTHETIC_FIXTURE')

    def test_split_adjusts_lots_without_creating_profit(self):
        rows=[dict(date='2024-01-02',at='2024-01-02T17:00:00+00:00',nav=999.,cash=899.,positions={'A':100.},sectors={'A':'Technology'}),
              dict(date='2024-01-03',at='2024-01-03T17:00:00+00:00',nav=1058.,cash=1058.,positions={},sectors={'A':'Technology'})]
        trades=[dict(date='2024-01-02',at='2024-01-02T09:00:00+00:00',symbol='A',side='BUY',shares=1,price_usd=100.,fee=1.,kind='MODELED_NEXT_OPEN'),
                dict(date='2024-01-03',at='2024-01-03T12:00:00+00:00',symbol='A',side='SELL',shares=2,price_usd=80.,fee=1.,kind='MODELED_NEXT_OPEN')]
        actions=[dict(symbol='A',effective_at='2024-01-03T09:00:00+00:00',ratio=2.)]
        r=analyze(rows,trades,initial_capital=1000.,start_date='2024-01-02',end_date='2024-01-03',data_kind='SYNTHETIC_FIXTURE',actions=actions)
        self.assertEqual(r['stock_pnl']['A'],58.)
        self.assertAlmostEqual(r['realized_lots'][0]['pnl'],58.)
