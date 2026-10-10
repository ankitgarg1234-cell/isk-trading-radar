"""Regression checks for offline completeness accounting, not performance tests."""
import csv
import gzip
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research import spgm_data_completeness as audit


def member(isin='US0378331005', cusip='037833100', **kwargs):
    return dict(instrument_key='isin:'+isin, isin=isin, cusip=cusip, sedol='',
        source_filing='SEC-accession', source_url='https://www.sec.gov/Archives/example',
        membership_status='CONFIRMED', available_at='2023-08-28T12:00:00+00:00',
        selection_cutoff_utc='2023-10-31T20:20:00+00:00', **kwargs)


class CompletenessTests(unittest.TestCase):
    def test_coobserved_aliases_deduplicate_without_name_join(self):
        a = member()
        b = member(isin='', cusip='037833100')
        b['instrument_key']='cusip:037833100'
        groups, _, conflict = audit.identity_groups([a,b])
        self.assertEqual(len(groups),1)
        self.assertFalse(conflict)

    def test_share_classes_and_adr_are_distinct(self):
        rows = [member(isin='US02079K3059',cusip='02079K305'),
                member(isin='US02079K1079',cusip='02079K107'),
                member(isin='TW0002330008',cusip=''),
                member(isin='US8740391003',cusip='874039100')]
        groups,_,conflict=audit.identity_groups(rows)
        self.assertEqual(len(groups),4)
        self.assertFalse(conflict)

    def test_conflicting_alias_is_quarantined(self):
        rows=[member(),member(isin='US5949181045',cusip='037833100')]
        groups,_,conflict=audit.identity_groups(rows)
        self.assertEqual(len(groups),2)
        self.assertIn(('cusip','037833100'),conflict)
        self.assertFalse(audit.membership_valid(rows,conflict))

    def test_current_or_recent_prices_do_not_make_ready(self):
        flags={r:False for r in audit.REQUIREMENTS}
        flags['pit_membership']=True
        self.assertEqual(audit.primary_status(flags,True,True),'PARTIALLY_READY')
        flags.update({r:True for r in audit.REQUIREMENTS})
        self.assertEqual(audit.primary_status(flags,True,True),'BACKTEST_READY')
        for field in audit.REQUIREMENTS:
            flags[field]=False
            self.assertEqual(audit.primary_status(flags,True,True),'PARTIALLY_READY')
            flags[field]=True

    def test_exactly_one_status_and_identity_priority(self):
        flags={r:True for r in audit.REQUIREMENTS}
        self.assertEqual(audit.primary_status(flags,False,True),'IDENTITY_UNRESOLVED')
        self.assertEqual(audit.primary_status(flags,False,False),'IDENTITY_UNRESOLVED')
        self.assertEqual(audit.primary_status(flags,True,False),'NO_USABLE_PRICE_DATA')

    def test_raw_validity_and_no_invented_actions(self):
        bar=dict(date='2026-07-09',open=10,high=12,low=9,close=11,volume=10)
        self.assertTrue(audit.valid_bar(bar))
        self.assertFalse(audit.valid_bar(bar|{'volume':float('nan')}))
        self.assertFalse(audit.valid_bar(bar|{'low':12}))
        self.assertFalse(audit.valid_bar(bar|{'date':'2026-02-30'}))
        flags=audit.requirement_flags([member()],[], 'USD',True,set())
        self.assertTrue(flags['fx'])
        self.assertFalse(flags['listing'])
        self.assertFalse(flags['ohlcv'])
        self.assertFalse(flags['corporate_actions'])
        self.assertFalse(audit.requirement_flags([member()],[],'TWD',True,set())['fx'])

    def test_future_membership_rejected(self):
        row=member()
        row['available_at']=row['selection_cutoff_utc']
        self.assertFalse(audit.membership_valid([row],set()))
        row['available_at']='2023-08-28T12:00:00'
        self.assertFalse(audit.membership_valid([row],set()))

    def test_closed_session_excluded_without_modifying_observation(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'prices.csv'
            p.write_text('original unchanged')
            bars=[dict(date='2026-07-09',open=10,high=12,low=9,close=11,volume=10),
                  dict(date='2026-07-10',open=11,high=11,low=11,close=11,volume=0)]
            with patch.object(audit,'REPO',Path(root)):
                result=audit.describe_prices('3711.TW',bars,p,'CSV',closed_dates={'2026-07-10'})
            self.assertEqual(result['valid_rows'],1)
            self.assertEqual(result['excluded_closed_sessions'],1)
            self.assertEqual(len(bars),2)
            self.assertEqual(p.read_text(),'original unchanged')

    def test_sector_etf_section_found_and_index_not_spy(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'wf3_prices.json.gz'
            bar=dict(date='2022-11-28',open=10,high=12,low=9,close=11,volume=10)
            data={'market':{'AAPL':{'rows':[bar]}},'sector_etfs':{'XLK':{'rows':[bar]}},
                  'benchmark_symbol':'^SP500TR','benchmark':{'rows':[bar]}}
            with gzip.open(p,'wt') as f:
                json.dump(data,f)
            with patch.object(audit,'REPO',Path(root)):
                prices,_,_=audit.discover_sources()
            self.assertIn('XLK',prices)
            self.assertIn('^SP500TR',prices)
            self.assertNotIn('SPY',prices)
            self.assertEqual(prices['XLK'][0]['source_section'],'sector_etfs')
            self.assertFalse(prices['XLK'][0]['full_seed_span'])

    def test_synthetic_csv_excluded(self):
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root)/'synthetic_parity'
            folder.mkdir()
            (folder/'prices.csv').write_text('date,open,high,low,close,volume\n2021-01-04,1,1,1,1,1\n')
            with patch.object(audit,'REPO',Path(root)):
                prices,candidates,_=audit.discover_sources()
            self.assertFalse(prices)
            self.assertEqual(candidates[0]['kind'],'SYNTHETIC_EXCLUDED')


if __name__=='__main__':
    unittest.main()
