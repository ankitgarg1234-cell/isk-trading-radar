import unittest
from research.ecb_fx import derive_usd_reference


class ECBReferenceTests(unittest.TestCase):
    def test_quote_direction_and_same_day_cross_without_fake_publication_time(self):
        text='TIME_PERIOD,CURRENCY,CURRENCY_DENOM,OBS_VALUE\n2023-09-29,USD,EUR,1.1\n2023-09-29,GBP,EUR,0.8\n'
        rows,missing=derive_usd_reference(text,'SYNTHETIC_FIXTURE')
        rates={r['currency']:r for r in rows}
        self.assertAlmostEqual(rates['GBP']['usd_per_unit'],1.375)
        self.assertEqual(rates['USD']['usd_per_unit'],1.)
        self.assertEqual(rates['EUR']['usd_per_unit'],1.1)
        self.assertIsNone(rates['GBP']['publication_at'])
        self.assertFalse(rates['GBP']['admitted_for_execution'])
        self.assertEqual(missing,[])

    def test_missing_usd_leg_is_not_forward_filled(self):
        text='TIME_PERIOD,CURRENCY,CURRENCY_DENOM,OBS_VALUE\n2023-09-29,USD,EUR,1.1\n2023-10-02,JPY,EUR,160\n'
        rows,missing=derive_usd_reference(text,'SYNTHETIC_FIXTURE')
        self.assertFalse(any(r['reference_date']=='2023-10-02' for r in rows))
        self.assertEqual(len(missing),1)

    def test_bad_denominator_or_duplicate_revision_blocks_derivation(self):
        for text in ('TIME_PERIOD,CURRENCY,CURRENCY_DENOM,OBS_VALUE\n2023-09-29,JPY,USD,160\n',
                     'TIME_PERIOD,CURRENCY,CURRENCY_DENOM,OBS_VALUE\n2023-09-29,USD,EUR,1.1\n2023-09-29,USD,EUR,1.2\n'):
            with self.assertRaises(ValueError):derive_usd_reference(text,'SYNTHETIC_FIXTURE')
