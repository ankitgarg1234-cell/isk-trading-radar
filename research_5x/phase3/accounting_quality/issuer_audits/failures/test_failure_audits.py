"""Offline integrity checks for fixed source audits, not a performance test."""
import csv
import hashlib
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parent

class FailureAuditIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=json.loads((ROOT/'case_metrics.json').read_text())
        cls.coverage=json.loads((ROOT/'coverage.json').read_text())
        with (ROOT/'metric_lineage.csv').open() as stream:
            cls.lineage=list(csv.DictReader(stream))

    def case(self,ticker,signal=None):
        return next(r for r in self.rows if r['ticker']==ticker and (signal is None or r['signal_date']==signal))

    def test_frozen_cases_and_repeated_issuer(self):
        self.assertEqual(len(self.rows),7)
        self.assertEqual(len({r['ticker'] for r in self.rows}),6)
        self.assertFalse(self.coverage['matched_or_representative_sample'])

    def test_original_snapshots_and_all_recorded_checks(self):
        with (ROOT/'source_index.csv').open() as stream:
            sources=list(csv.DictReader(stream))
        for r in sources:
            self.assertEqual(hashlib.sha256((ROOT/r['local_path']).read_bytes()).hexdigest(),r['sha256'],r['source_id'])
        checks=json.loads((ROOT/'validation_checks.json').read_text())
        self.assertEqual(checks['failed'],0)
        self.assertTrue(all(c['passed'] for c in checks['checks']))

    def test_late_DECK_cash_is_missing(self):
        r=self.case('DECK','2024-10-31')
        for field in ['cfo','gross_capex','sbc','analyst_fcf','cfo_to_ni']:
            self.assertIsNone(r[field])

    def test_APP_scope_guard_and_derived_gross_profit(self):
        r=self.case('APP')
        for field in ['cfo_to_ni','cfo_to_revenue','fcf_to_ni','fcf_to_revenue','capex_to_revenue']:
            self.assertIsNone(r[field])
        self.assertAlmostEqual(r['cfo_to_consolidated_ni'],772.226/819.531)
        entry=next(x for x in self.lineage if x['ticker']=='APP' and x['metric']=='gross_profit')
        self.assertEqual(entry['evidence_label'],'derived_calculation')
        self.assertAlmostEqual(r['gross_profit'],r['revenue']-155.076)

    def test_DASH_cash_definition_bridge(self):
        r=self.case('DASH')
        self.assertEqual(r['gross_capex'],140-74)
        self.assertEqual(r['sbc'],517-235)
        self.assertEqual(r['analyst_fcf'],438)
        self.assertEqual(r['analyst_fcf']-r['capitalized_software_cash'],r['issuer_fcf'])
        self.assertEqual(r['net_income'],284)

    def test_cash_and_outcomes_not_sufficient(self):
        compatible=[r for r in self.rows if r['cfo_to_ni'] is not None]
        self.assertEqual(len(compatible),5)
        positive_fcf=[r for r in compatible if r['analyst_fcf']>0]
        self.assertEqual(len(positive_fcf),4)
        self.assertTrue(all(r['forward_252d']<-.3 for r in positive_fcf))

    def test_missingness_counts(self):
        expected={'revenue':7,'operating_income':7,'gross_profit':6,'net_income':7,'cfo':6,'gross_capex':6,'sbc':6,'adjusted_operating_income':1,'adjusted_net_income':2,'working_capital_cash_change':4}
        self.assertEqual({m:v['available'] for m,v in self.coverage['core_metric_coverage'].items()},expected)

if __name__=='__main__':unittest.main()
