import unittest
from research.us_reference_audit import historical_candidates,audit


class USHistoryTests(unittest.TestCase):
    def test_future_alias_creation_cannot_backfill_old_symbol(self):
        old=dict(symbol='OLD',cik='001',date_added='2000-01-01',date_removed='2024-01-01*',created_at='2007-01-01')
        new=dict(old,symbol='NEW',date_removed='',created_at='2024-01-01')
        self.assertEqual(historical_candidates([old,new],'2023-09-29'),[old])

    def test_shared_issuer_classes_preserved_and_not_certified(self):
        rows=[dict(symbol=s,cik='001',date_added='2000-01-01',date_removed='',created_at='2007-01-01') for s in ['A','B']]
        report=audit(rows,[dict(CIK='1',**{'GICS Sector':'Financials'})])
        self.assertEqual(report['prelaunch_symbols'],2)
        self.assertEqual(report['prelaunch_issuers'],1)
        self.assertFalse(report['faithful_membership_ready'])

    def test_conflicting_current_issuer_sectors_not_joined(self):
        rows=[dict(symbol='A',cik='001',date_added='2000-01-01',date_removed='',created_at='2007-01-01')]
        report=audit(rows,[dict(CIK='1',**{'GICS Sector':sector}) for sector in ['Financials','Industrials']])
        self.assertEqual(report['current_gics_cik_join_candidates'],0)
