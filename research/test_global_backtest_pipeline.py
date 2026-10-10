import unittest
import tempfile,json
from pathlib import Path
from datetime import datetime,timezone
from research.global_backtest_pipeline import verify_member_metadata,reference_timeline,parse_bundle
from research.spgm_sources import ROOT
from research.strategy_kernel import load_kernel


class ReadinessTests(unittest.TestCase):
    def test_current_sector_cannot_admit_historical_bundle(self):
        row=dict(symbol='A',instrument_key='isin:US0378331005',sector='Information Technology',sector_scheme='GICS')
        with self.assertRaisesRegex(ValueError,'GICS'):
            verify_member_metadata(row,datetime(2023,9,29,20,20,tzinfo=timezone.utc))

    def test_prelaunch_and_end_use_actual_reference_sessions(self):
        rows=reference_timeline()
        self.assertEqual(rows[0][0],'2023-09-29')
        self.assertEqual(rows[1][0],'2023-10-02')
        self.assertEqual(rows[-1][0],'2026-09-30')
        self.assertTrue(all(at.tzinfo for _,at in rows))

    def test_ready_boolean_cannot_replace_source_evidence(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            path=Path(temp)/'bundle.json'
            path.write_text(json.dumps(dict(data_kind='HISTORICAL_INPUT',configuration='SP500',
                start='2023-10-01',end='2026-09-30',initial_capital=10000.,
                reference_symbols=['SPY']+list(load_kernel()['ETFS'].values()),
                rights_permitted=True,ready=True)))
            with self.assertRaisesRegex(ValueError,'admission evidence'):
                parse_bundle(path,'SP500')
