import copy
import unittest
from datetime import datetime, timezone
from research.classification_policy import (STRICT_PIT,EXPLORATORY_CURRENT_GICS,
    resolve_sector,coverage,decision_sensitivity,SECTORS)
from research.global_backtest_pipeline import verify_member_metadata
from research.strategy_kernel import load_kernel

AT=datetime(2023,9,29,20,20,tzinfo=timezone.utc)


def member():
    return dict(symbol='A',instrument_key='isin:US0378331005',issuer_id='issuer-A',country='US',
        exchange_mic='XNAS',currency='USD',listing_verification='historically_verified',
        listing_source_url='https://example.test/listing',listing_available_at='2022-01-01T00:00:00+00:00',
        listing_effective_from='2020-01-01T00:00:00+00:00',
        membership_available_at='2023-08-01T00:00:00+00:00',membership_source_url='https://example.test/filing',
        current_gics=dict(instrument_key='isin:US0378331005',sector='Information Technology',sector_scheme='GICS',
            source_url='https://example.test/current',evidence_file='current.json',sha256='a'*64,
            retrieved_at='2026-10-10T00:00:00+00:00',classification_asof='2026-10-09T00:00:00+00:00',taxonomy_version='2023'))


class ClassificationTests(unittest.TestCase):
    def test_strict_default_still_rejects_current_fallback(self):
        with self.assertRaisesRegex(ValueError,'Historical GICS'):
            verify_member_metadata(member(),AT)

    def test_current_mode_records_approximation_without_mutating_original(self):
        m=member();original=copy.deepcopy(m)
        row=verify_member_metadata(m,AT,EXPLORATORY_CURRENT_GICS)
        self.assertEqual(m,original)
        self.assertEqual(row['sector_verification'],'exploratory_approximation')
        self.assertTrue(row['classification_audit']['approximate'])
        self.assertEqual(row['classification_audit']['status'],'CURRENT_GICS_BACKFILL')

    def test_current_mode_does_not_relax_listing_or_membership_dates(self):
        for field in ('listing_available_at','membership_available_at'):
            m=member();m[field]='2026-01-01T00:00:00+00:00'
            with self.assertRaises(ValueError):verify_member_metadata(m,AT,EXPLORATORY_CURRENT_GICS)

    def test_historical_verified_assignment_preferred(self):
        m=member();m.update(sector='Financials',sector_scheme='GICS',sector_verification='historically_verified',
            sector_source_url='https://example.test/historic',sector_available_at='2023-01-01T00:00:00+00:00',
            sector_effective_from='2022-01-01T00:00:00+00:00')
        row=resolve_sector(m,AT,EXPLORATORY_CURRENT_GICS)
        self.assertEqual(row['sector'],'Financials');self.assertFalse(row['classification_audit']['approximate'])
        self.assertEqual(resolve_sector(m,AT,STRICT_PIT)['sector'],'Financials')

    def test_retrospective_correction_does_not_gain_historical_verification(self):
        m=member();c=dict(m['current_gics'],sector='Financials',effective_from='2020-01-01T00:00:00+00:00',
            effective_to='2024-01-01T00:00:00+00:00',available_at='2026-01-01T00:00:00+00:00',verification='historically_verified')
        m['historical_gics_corrections']=[c]
        row=resolve_sector(m,AT,EXPLORATORY_CURRENT_GICS)
        self.assertEqual(row['sector'],'Financials');self.assertTrue(row['classification_audit']['approximate'])
        self.assertEqual(row['classification_audit']['status'],'RETROSPECTIVE_CORRECTION')
        c['available_at']='2022-01-01T00:00:00+00:00'
        self.assertFalse(resolve_sector(m,AT,EXPLORATORY_CURRENT_GICS)['classification_audit']['approximate'])

    def test_identity_provenance_scheme_and_correction_ambiguity_rejected(self):
        for field,value in [('instrument_key','isin:wrong'),('source_url',''),('sector_scheme','SIC'),('sector','Unknown')]:
            m=member();m['current_gics'][field]=value
            with self.assertRaises(ValueError):resolve_sector(m,AT,EXPLORATORY_CURRENT_GICS)
        m=member();c=dict(m['current_gics'],effective_from='2020-01-01T00:00:00+00:00',available_at='2022-01-01T00:00:00+00:00')
        m['historical_gics_corrections']=[c,c]
        with self.assertRaisesRegex(ValueError,'Overlapping'):resolve_sector(m,AT,EXPLORATORY_CURRENT_GICS)

    def test_country_denominator_preserves_unresolved_securities(self):
        rows=[]
        for i in range(100):
            m=member();m['instrument_key']=str(i);m['current_gics']['instrument_key']=str(i)
            if i<2:m['country']='KR';m.pop('current_gics')
            rows.append(m)
        report=coverage([dict(decision_at=AT.isoformat(),members=rows)],EXPLORATORY_CURRENT_GICS)
        r=report['snapshots'][0]
        self.assertEqual(r['covered_fraction'],.98)
        self.assertEqual(r['country']['KR']['total'],2)
        self.assertFalse(report['minimum_coverage_pass'])
        self.assertEqual(r['approximate'],98)

    def test_joint_sector_stresses_quantify_rule_sensitivity(self):
        class Engine:
            k=load_kernel();reference=[('2023-09-29',AT)];state=dict(cash=10000.,holdings={},lockouts={},trades=[])
            history={'SPY':[]}
        e=Engine();e.k['_sector_and_cap']=lambda *args:(.5,{'fixture':True})
        e.k['_calculate_targets']=lambda state,rows,stats,cap,marks,**kw:({}, {'A':cap if rows[0]['sector']=='Financials' else .2},['A'],{})
        rows=[resolve_sector(member(),AT,EXPLORATORY_CURRENT_GICS)]
        report=decision_sensitivity(e,'2023-09-29',AT,rows,{}, {'A':100.},1.,{},.1)
        self.assertEqual(report['scenario_count'],11)
        self.assertTrue(any(r['max_absolute_weight_change']>0 for r in report['scenarios']))
        self.assertTrue(report['sensitivity_measured'])


if __name__=='__main__':unittest.main()
