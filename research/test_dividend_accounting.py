import unittest
from dataclasses import replace
from research.historical_engine import CashDividend,HistoricalEngine
from research.test_historical_engine import small_engine
from research.backtest_metrics import analyze


class DividendAccountingTests(unittest.TestCase):
    def test_entitlement_survives_sale_and_does_not_become_spendable_early(self):
        engine,r=small_engine()
        d=CashDividend('A',r.open_at,r.close_at,r.open_at,2.,'USD','synthetic-source')
        engine.state['holdings']['A']=dict(shares=10,cost=100.,peak=100.,stop=90.)
        cash=engine.state['cash'];engine._dividend_ex(d)
        self.assertEqual(engine._receivable_marks(r.open_at),{'A':20.})
        self.assertEqual(engine.state['cash'],cash)
        self.assertEqual(engine._sizing_state(r.open_at)['cash'],cash+20.)
        del engine.state['holdings']['A']
        engine._dividend_pay(d,r.close_at)
        self.assertEqual(engine.state['cash'],cash+20.)
        self.assertFalse(engine.dividend_claims)

    def test_buy_after_entitlement_does_not_receive_dividend(self):
        engine,r=small_engine();d=CashDividend('A',r.open_at,r.close_at,r.open_at,2.,'USD','synthetic-source')
        engine._dividend_ex(d);engine.state['holdings']['A']=dict(shares=10)
        cash=engine.state['cash'];engine._dividend_pay(d,r.close_at)
        self.assertEqual(engine.state['cash'],cash)

    def test_future_evidence_and_duplicate_entitlements_fail(self):
        engine,r=small_engine();d=CashDividend('A',r.open_at,r.close_at,r.close_at,2.,'USD','synthetic-source')
        args=(engine.records,engine.calendars,[],lambda _:[],[])
        with self.assertRaisesRegex(ValueError,'evidence'):HistoricalEngine(*args,cash_dividends=[d])
        d=replace(d,available_at=r.open_at)
        with self.assertRaisesRegex(ValueError,'Duplicate'):HistoricalEngine(*args,cash_dividends=[d,replace(d,source='restated-source')])

    def test_ex_dividend_receivable_and_cash_payment_reconcile_nav(self):
        rows=[dict(date='2024-01-02',at='2024-01-02T20:00:00+00:00',nav=10000.,cash=9000.,positions={'A':1000.},sectors={'A':'Financials'}),
              dict(date='2024-01-03',at='2024-01-03T20:00:00+00:00',nav=10000.,cash=9000.,positions={'A':980.},receivables={'A':20.},sectors={'A':'Financials'}),
              dict(date='2024-01-04',at='2024-01-04T20:00:00+00:00',nav=10000.,cash=9020.,positions={'A':980.},receivables={},sectors={'A':'Financials'})]
        trades=[dict(date='2024-01-02',at='2024-01-02T14:00:00+00:00',symbol='A',side='BUY',shares=10,price_usd=100.,fee=0.,kind='SYNTHETIC')]
        payments=[dict(symbol='A',at='2024-01-04T14:00:00+00:00',amount_usd=20.)]
        m=analyze(rows,trades,initial_capital=10000.,start_date='2024-01-02',end_date='2024-01-04',data_kind='SYNTHETIC_FIXTURE',dividends=payments)
        self.assertEqual(m['total_return'],0.)
        self.assertEqual(m['attribution_residual'],0.)
        self.assertEqual(m['dividend_cash_paid'],20.)
