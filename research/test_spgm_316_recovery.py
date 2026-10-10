import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from research import spgm_316_recovery as recovery
from research import spgm_recovery_sources as sources

class RecoveryTests(unittest.TestCase):
    def test_identifier_mapping_cost_is_one_unit(self):
        from research.eodhd_client import ENDPOINT_COSTS
        self.assertEqual(ENDPOINT_COSTS["id-mapping"],1)

    def test_report_tables_are_not_indented_code(self):
        from research.spgm_recovery_reports import clean_markdown
        self.assertEqual(clean_markdown("# Report\n\n    | A | B |\n    Text"), "# Report\n\n| A | B |\nText\n")

    def test_lookbacks_require_endpoint_plus_lookback(self):
        self.assertEqual(recovery.NEEDS['momentum63'],64)
        self.assertEqual(recovery.NEEDS['momentum126'],127)
        self.assertEqual(recovery.NEEDS['momentum252'],253)
        self.assertEqual(recovery.NEEDS['atr14_minimum'],15)

    def test_hole_not_hidden_by_sufficient_bar_count(self):
        dates=recovery.expected_sessions('XNYS')[:70]
        rows=[dict(date=d,open=1,high=1,low=1,close=1,volume=1)for d in dates if d!=dates[-10]]
        with patch.object(recovery,'expected_sessions',return_value=dates):
            result=recovery.gap_audit(rows,'XNYS',[dates[-1]])
        cutoff=result['cutoffs'][0]
        self.assertTrue(cutoff['count_minimum_met']['momentum63'])
        self.assertEqual(cutoff['missing_by_input']['momentum63'],1)

    def test_extraordinary_closure_excluded(self):
        self.assertNotIn('2026-07-10',recovery.expected_sessions('XTAI'))
        bar=dict(date='2026-07-10',open=1,high=1,low=1,close=1,volume=0)
        result=recovery.gap_audit([bar],'XTAI',['2026-07-13'])
        self.assertEqual(result['valid_target_dates'],0)
        self.assertEqual(bar['date'],'2026-07-10')

    def test_provider_join_cannot_transfer_adr_prices_to_ordinary_isin(self):
        adr={'isin':'US8740391003'}
        ordinary={'Code':'2330','Exchange':'TW','Currency':'TWD','Type':'Common Stock','_suffix':'TW'}
        records,n=recovery.provider_candidates(adr,{'TW0002330008':[ordinary]})
        self.assertFalse(records);self.assertEqual(n,0)

    def test_provider_duplicate_venues_remain_ambiguous(self):
        r=dict(Code='AAPL',Exchange='NASDAQ',Currency='USD',Type='Common Stock',_suffix='US')
        records,n=recovery.provider_candidates({'isin':'US0378331005'}, {'US0378331005':[r,r|{'Exchange':'NYSE'}]})
        self.assertEqual(n,2)
        self.assertEqual(len(records),2)

    def test_current_gics_rejects_cik_conflict_and_sic_labels(self):
        row={'isin':'US0378331005','instrument_key':'isin:US0378331005'}
        matched=[dict(Code='AAPL',Isin='US0378331005',Type='Common Stock',_kind='active',_suffix='US')]
        sector={'AAPL':{'CIK':'320193','GICS Sector':'Information Technology'}}
        self.assertIsNone(recovery.build_current_sector(row,matched,{'AAPL':{'cik':1}},sector,{}))
        self.assertIsNone(recovery.build_current_sector(row,matched,{'AAPL':{'cik':320193}},
            {'AAPL':{'CIK':'320193','SIC':'3571'}},{}))
        wrong=[matched[0]|{'Isin':'US5949181045'}]
        self.assertIsNone(recovery.build_current_sector(row,wrong,{'AAPL':{'cik':320193}},sector,{}))

    def test_sourced_current_gics_passes_exploratory_and_stays_strictly_rejected(self):
        from datetime import datetime
        from research.classification_policy import resolve_sector,EXPLORATORY_CURRENT_GICS,STRICT_PIT
        with tempfile.TemporaryDirectory()as root:
            base=Path(root)/'proxy';out=base/'historical_backtest/recovery_316'
            (out/'public_sources').mkdir(parents=True)
            reference=base/'historical_backtest/reference_sources';reference.mkdir()
            (out/'US_active_symbols.json').write_text('[]')
            (out/'public_sources/sec_tickers.html').write_text('{}')
            (reference/'current_sp500.csv').write_text('public source fixture')
            (reference/'retrieval_manifest.json').write_text(json.dumps([
                {'file':'current_sp500.csv','retrieved_at':'2026-10-10T10:00:00+00:00'}]))
            row={'isin':'US0378331005','instrument_key':'isin:US0378331005'}
            matched=[dict(Code='AAPL',Isin='US0378331005',Type='Common Stock',_kind='active',_suffix='US')]
            with patch.object(recovery,'DEFAULT_OUTPUT',base),patch.object(recovery,'OUT',out):
                overlay=recovery.build_current_sector(row,matched,{'AAPL':{'cik':320193}},
                    {'AAPL':{'CIK':'0000320193','GICS Sector':'Information Technology'}},{})
            at=datetime.fromisoformat('2023-09-29T20:20:00+00:00')
            result=resolve_sector(row|overlay,at,EXPLORATORY_CURRENT_GICS)
            self.assertTrue(result['classification_audit']['approximate'])
            self.assertEqual(result['sector_verification'],'exploratory_approximation')
            with self.assertRaises(ValueError):resolve_sector(row|overlay,at,STRICT_PIT)
            record=overlay['current_gics']
            self.assertEqual(recovery.sha(out/record['evidence_file']),record['sha256'])

    def test_public_demo_cannot_probe_undocumented_spy(self):
        with self.assertRaisesRegex(ValueError,'approved'):
            sources.recover_demo('eod','SPY.US')
        for symbol in ('AMZN.US','TSLA.US'):
            with self.assertRaisesRegex(ValueError,'AAPL'):
                sources.recover_demo('div',symbol)

    def test_demo_cache_avoids_network_and_account_quota(self):
        with tempfile.TemporaryDirectory()as root:
            out=Path(root);(out/'demo').mkdir();p=out/'demo/AAPL_US_eod.json';p.write_text('[]')
            with patch.object(sources,'OUT',out),patch.object(sources,'build_opener')as opener:
                self.assertEqual(sources.recover_demo('eod','AAPL.US'),p)
                opener.assert_not_called()
            self.assertFalse((out/'demo_request_manifest.json').exists())

    def test_demo_requests_reserved_before_transport(self):
        with tempfile.TemporaryDirectory()as root:
            out=Path(root);(out/'demo_request_manifest.json').write_text(json.dumps([{}]*9))
            with patch.object(sources,'OUT',out),patch.object(sources,'build_opener')as opener:
                with self.assertRaisesRegex(RuntimeError,'cap'):
                    sources.recover_demo('eod','AAPL.US')
                opener.assert_not_called()

if __name__=='__main__':unittest.main()
