"""Regression tests for selection leakage, units, missingness and gate integrity."""
from pathlib import Path
import gzip,hashlib,json,unittest
import pandas as pd
from build_cohorts import match,category
from stage_accounting import eligible,choose,prior_ytd
OUT=Path(__file__).resolve().parents[1]
A=OUT/'accounting_quality'

class Integrity(unittest.TestCase):
    def test_frozen_protocol(self):
        f=json.loads((OUT/'protocol_freeze.json').read_text())
        self.assertEqual(hashlib.sha256((OUT/'PROTOCOL.md').read_bytes()).hexdigest(),f['sha256'])
    def test_all_outcomes_preserved(self):
        a=pd.read_csv(A/'all_qualified_with_labels.csv');m=pd.read_csv(A/'mature_cohorts.csv')
        self.assertEqual(len(a),379);self.assertEqual(len(m),188);self.assertEqual(m.ticker.nunique(),39)
        self.assertEqual((m.forward_252d<0).sum(),58);self.assertEqual((m.forward_252d<=-.30).sum(),13)
        self.assertEqual(m[['date','ticker']].duplicated().sum(),0)
    def test_label_boundaries(self):
        self.assertEqual([category(x) for x in [1,.999,.30,.299,-.10,-.1001,-.30]],['exceptional','moderate','moderate','flat_modest','flat_modest','material_loser','severe_loser'])
    def test_matching_outcome_blind(self):
        a=pd.read_csv(A/'mature_cohorts.csv');b=a.copy();b['forward_252d']=list(reversed(b.forward_252d.tolist()));b['outcome']=b.forward_252d.map(category)
        for s in ['strict','relaxed']:
            p,_=match(a,s);q,_=match(b,s)
            pd.testing.assert_frame_equal(p[['date','ticker','peer','nearest','distance']],q[['date','ticker','peer','nearest','distance']])
    def test_first_company_sample(self):
        a=pd.read_csv(A/'first_company_signals.csv');self.assertEqual(a.ticker.nunique(),len(a));self.assertEqual(len(a),66)
        m=a[a.forward_252d.notna()];self.assertEqual(len(m),39)
    def test_match_calipers(self):
        a=pd.read_csv(A/'relaxed_eligible_pairs.csv');self.assertTrue((a.size_gap_log2<=1).all());self.assertTrue((a.momentum_gap<=.30).all());self.assertTrue((a.ticker!=a.peer).all())
    def test_previous_day_filing_cutoff(self):
        good={'filingDate':'2024-10-30','api_acceptance_eastern_date':'2024-10-30'}
        self.assertTrue(eligible(good,'2024-10-30'))
        self.assertFalse(eligible({**good,'filingDate':'2024-10-31'},'2024-10-30'))
        self.assertFalse(eligible({**good,'api_acceptance_eastern_date':''},'2024-10-30'))
    def test_later_accession_never_backfilled(self):
        f={'accessionNumber':'original','reportDate':'2024-06-30'}
        facts={'Revenues':{'units':{'USD':[{'accn':'later','end':'2024-06-30','start':'2024-04-01','val':900},{'accn':'original','end':'2024-06-30','start':'2024-04-01','val':100}]}}}
        self.assertEqual(choose(facts,f,'revenue')['val'],100)
        facts['Revenues']['units']['USD'].append({'accn':'original','end':'2024-06-30','start':'2024-04-01','val':101})
        self.assertIsNone(choose(facts,f,'revenue'))
    def test_no_scope_alias_ytd_subtraction(self):
        current={'tag':'ProfitLoss','start':'2024-01-01','end':'2024-06-30'}
        files={'old':{'filingDate':'2024-05-01','api_acceptance_eastern_date':'2024-05-01'}}
        facts={'NetIncomeLoss':{'units':{'USD':[{'accn':'old','start':'2024-01-01','end':'2024-03-31','val':100}]}}}
        self.assertIsNone(prior_ytd(facts,files,'net_income',current,'2024-07-30'))
    def test_staging_time_lineage(self):
        a=pd.read_csv(A/'sec_metrics_staging.csv');g=a[a.accession.notna()]
        self.assertTrue((g.filing_date<=g.signal_cutoff).all());self.assertTrue((g.api_eastern_date<=g.signal_cutoff).all())
        self.assertFalse(a.predictive_use_allowed.any())
        f=pd.read_csv(A/'sec_fact_lineage.csv.gz');dates=pd.read_csv(A/'mature_cohorts.csv')[['date','ticker','signal_cutoff']]
        f=f.merge(dates,on=['date','ticker'],validate='many_to_one');self.assertTrue((f.filing_date<=f.signal_cutoff).all())
    def test_scope_and_capex_guards(self):
        a=pd.read_csv(A/'sec_metrics_staging.csv');bad=a[((a.ticker=='WDC')&(a.report_date>='2025-03-28'))|((a.ticker=='APP')&(a.report_date>='2025-06-30'))]
        self.assertTrue(bad[['cfo_to_earnings_ytd','fcf_to_earnings_ytd','cfo_margin_ytd','fcf_margin_ytd']].isna().all().all())
        parent=a[a.net_income_tag=='NetIncomeLoss'];self.assertTrue(parent.cfo_to_earnings_ytd.isna().all())
        nv=a[a.ticker=='NVDA'];self.assertTrue(nv.gross_ppe_capex_ytd_usd.isna().all())
    def test_source_failure_cash_and_availability(self):
        f=pd.read_csv(A/'issuer_audits/failures/case_metrics.csv')
        deck=f[(f.ticker=='DECK')&(f.signal_date=='2024-10-31')].iloc[0];self.assertTrue(pd.isna(deck.cfo));self.assertTrue(pd.isna(deck.cfo_to_ni))
        app=f[f.ticker=='APP'].iloc[0];self.assertTrue(pd.isna(app.cfo_to_ni))
        for _,r in f[f.ticker.isin(['DXCM','TTD','DASH'])].iterrows():
            self.assertAlmostEqual(r.analyst_fcf,r.cfo-r.gross_capex,places=8);self.assertGreater(r.analyst_fcf,0);self.assertLessEqual(r.forward_252d,-.30)
    def test_source_copies(self):
        m=json.loads((OUT/'frozen_inputs/source_copies.json').read_text())
        for f in m['copies']:self.assertEqual(hashlib.sha256((OUT/f['copy']).read_bytes()).hexdigest(),f['sha256'])
    def test_raw_snapshots(self):
        for f in json.loads((A/'raw_snapshot_manifest.json').read_text()):
            b=(OUT/f['path']).read_bytes();self.assertEqual(hashlib.sha256(b).hexdigest(),f['sha256'])
    def test_scientific_gate_has_no_invented_accounts(self):
        j=json.loads((OUT/'VALIDATION_STATUS.json').read_text())
        self.assertFalse(j['gates']['gate_3_entry_timing_and_holding']['new_portfolio_tests_run']);self.assertFalse(j['new_strategy_recommendation'])
        self.assertFalse(j['deployed_or_paper_account_modified']);self.assertFalse(j['trades_executed'])
        self.assertTrue(all(x['classification']!='Validated' for x in j['conclusions'].values()))

if __name__=='__main__':unittest.main()
