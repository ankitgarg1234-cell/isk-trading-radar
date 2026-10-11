"""Accounting integrity regressions against independently inspected originals.

Run after extract_original_facts.py and build_packet.py. These checks guard
economically material vintage, duration, scope and publication errors. They do
not test a trading strategy or certify independent investment performance.
"""
import csv, gzip, json, pathlib, sys, unittest
from decimal import Decimal
from lxml import html

ROOT=pathlib.Path(__file__).resolve().parent

class OriginalAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e=json.loads((ROOT/'curated_evidence.json').read_text())
        cls.reports={r['id']:r for r in cls.e['reports']+cls.e['supplemental_windows']}
        with (ROOT/'original_inline_facts.csv').open() as f:cls.facts=list(csv.DictReader(f))
        with (ROOT/'normalized_metrics.csv').open() as f:cls.metrics={r['id']:r for r in csv.DictReader(f)}
        with (ROOT/'source_lineage.csv').open() as f:cls.lines={r['source_id']:r for r in csv.DictReader(f)}

    def expect_original_fact(self,source,concept,start,end,dollars):
        rows=[r for r in self.facts if r['source_id']==source and r['concept']=='us-gaap:'+concept
              and r['startdate']==start and r['enddate']==end and r['has_dimensions']=='False'
              and r['status']=='extracted']
        self.assertTrue(rows,(source,concept,start,end))
        self.assertEqual({Decimal(r['value']) for r in rows},{Decimal(str(dollars))})

    def test_consolidated_cash_earnings_scopes(self):
        samples=[('PLTR_Q1_10Q','2025-01-01','2025-03-31',217717000,214031000),
          ('SNPS_Q1_10Q','2023-11-01','2024-01-31',446207000,449112000),
          ('RCL_Q3_10Q','2023-07-01','2023-09-30',1010678000,1009076000),
          ('RCL_Q3_10Q','2023-01-01','2023-09-30',1425078000,1419927000)]
        for source,start,end,consolidated,parent in samples:
            with self.subTest(source=source,start=start):
                self.expect_original_fact(source,'ProfitLoss',start,end,consolidated)
                self.expect_original_fact(source,'NetIncomeLoss',start,end,parent)
                self.assertNotEqual(consolidated,parent)

    def test_negative_cash_not_missing_or_positive(self):
        self.expect_original_fact('SNPS_Q1_10Q','NetCashProvidedByUsedInOperatingActivities',
                                  '2023-11-01','2024-01-31',-87790000)
        self.assertLess(float(self.metrics['SNPS_FY24Q1']['cfo_to_ni']),0)

    def test_CCL_annual_vintages(self):
        self.expect_original_fact('CCL_FY23_10K','NetCashProvidedByUsedInOperatingActivities',
                                  '2022-12-01','2023-11-30',4281000000)
        self.assertEqual(self.reports['CCL_FY23_original']['cfo'],4273)
        self.assertEqual(self.reports['CCL_FY23_filed']['cfo'],4281)
        self.assertEqual(self.reports['CCL_2023Q4_original']['cfo'],915)
        self.assertEqual(self.metrics['CCL_2023Q4_original']['cfo_to_ni'],'')

    def test_cash_duration_never_spliced(self):
        self.assertIsNone(self.reports['RCL_2023Q3']['cfo'])
        self.assertEqual(self.reports['RCL_2023YTD9']['cfo'],3361.005)
        self.expect_original_fact('RCL_Q3_10Q','NetCashProvidedByUsedInOperatingActivities',
                                  '2023-01-01','2023-09-30',3361005000)
        self.assertEqual(self.metrics['RCL_2023Q3']['cfo_to_ni'],'')

    def test_original_index_clock_beats_API(self):
        p=ROOT/'raw'/'NVDA_Q4_SEC_release_index.bin.gz'
        tree=html.fromstring(gzip.open(p,'rb').read())
        head=tree.xpath('//div[@class="infoHead" and normalize-space(.)="Accepted"]')[0]
        self.assertEqual(head.getnext().text_content().strip(),'2024-02-21 16:22:09')
        row=self.lines['NVDA_Q4_SEC_release']
        self.assertEqual(row['original_accepted_UTC'],'2024-02-21T21:22:09+00:00')
        self.assertEqual(float(row['API_minus_original_seconds']),18000)

    def test_combined_capex_not_pure_PPE(self):
        self.assertIsNone(self.reports['NVDA_FY24Q4']['gross_capex'])
        self.assertEqual(self.metrics['NVDA_FY24Q4']['analyst_fcf'],'')
        self.assertEqual(self.reports['NVDA_FY24Q4']['combined_ppe_intangible_spend'],253)

    def test_net_interest_not_gross_expense(self):
        r=self.reports['ZBRA_2024Q3']
        self.assertIsNone(r['interest_expense'])
        self.assertEqual(r['interest_expense_net'],31)
        self.assertEqual(self.metrics['ZBRA_2024Q3']['interest_to_oi'],'')

    def test_source_failure_and_repeated_cases_retained(self):
        manifest=json.loads((ROOT/'download_manifest.json').read_text())
        self.assertTrue(any(r['status']=='failed' and r['source_id']=='NOW_Q4_release' for r in manifest))
        with (ROOT/'signal_case_matrix.csv').open() as f:cases=list(csv.DictReader(f))
        zbra=[r for r in cases if r['ticker']=='ZBRA']
        self.assertEqual(len(zbra),2)
        self.assertEqual({r['report_id'] for r in zbra},{'ZBRA_2024Q3'})
        self.assertEqual(sum(r['first_observed_company_signal']=='True' for r in zbra),1)
        self.assertEqual({r['outcome'] for r in zbra},{'severe_loser'})

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(OriginalAuditTests))
    (ROOT/'unit_test_results.json').write_text(json.dumps(dict(tests_run=result.testsRun,
      failures=len(result.failures),errors=len(result.errors),passed=result.wasSuccessful(),
      purpose='original accounting vintage, scope, sign, duration, timestamps and missingness integrity; no strategy validation'),indent=2)+'\n')
    sys.exit(0 if result.wasSuccessful() else 1)
