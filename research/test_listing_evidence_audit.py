import unittest
from research.listing_evidence_audit import mapping_index,candidate


class ListingEvidenceTests(unittest.TestCase):
    def test_missing_provider_isin_is_retained_as_unmapped(self):
        self.assertEqual(dict(mapping_index([dict(Isin=None)])),{})
        self.assertEqual(candidate(dict(isin=None),{})['status'],'NO_EXACT_ISIN_MATCH')

    def test_name_and_country_do_not_replace_primary_with_adr(self):
        rows=[dict(Isin='US8740391003',Code='TSM',Exchange='US',Currency='USD',Type='Common Stock',Name='TSMC')]
        self.assertEqual(candidate(dict(isin='TW0002330008',name='TSMC'),mapping_index(rows))['status'],'NO_EXACT_ISIN_MATCH')

    def test_exact_current_mapping_is_never_historically_verified(self):
        rows=[dict(Isin='TW0002330008',Code='2330',Exchange='TW',Currency='TWD',Type='Common Stock')]
        row=candidate(dict(isin='TW0002330008'),mapping_index(rows))
        self.assertEqual(row['symbol'],'2330.TW');self.assertFalse(row['historically_verified'])

    def test_multiple_listing_symbols_are_ambiguous(self):
        rows=[dict(Isin='TW0002330008',Code=s,Exchange='TW',Currency='TWD',Type='Common Stock') for s in ['2330','OTHER']]
        self.assertEqual(candidate(dict(isin='TW0002330008'),mapping_index(rows))['status'],'AMBIGUOUS_CURRENT_LISTING')
