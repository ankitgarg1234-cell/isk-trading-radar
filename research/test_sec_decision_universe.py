import unittest
from datetime import datetime
from research.sec_decision_universe import reference_decisions, classify_status


class DecisionUniverseTests(unittest.TestCase):
    def test_actual_monthend_and_dst_cutoffs(self):
        rows={r['selection_month']:r for r in reference_decisions()}
        self.assertEqual(len(rows),48)
        self.assertEqual(rows['2023-09']['signal_date'],'2023-09-29')
        self.assertEqual(rows['2023-09']['selection_cutoff_utc'],'2023-09-29T20:20:00+00:00')
        self.assertEqual(rows['2023-12']['selection_cutoff_utc'],'2023-12-29T21:20:00+00:00')
        self.assertTrue(all(datetime.fromisoformat(r['reference_close_utc'])<datetime.fromisoformat(r['selection_cutoff_utc']) for r in rows.values()))

    def test_membership_is_not_tradability_and_missing_id_is_unresolved(self):
        self.assertEqual(classify_status({'eligibility':'eligible'}),'CONFIRMED')
        self.assertEqual(classify_status({'eligibility':'excluded','asset_category':'EC','eligibility_reason':'missing valid identifier'}),'UNRESOLVED')
        self.assertEqual(classify_status({'eligibility':'excluded','asset_category':'EP'}),'INELIGIBLE')


if __name__=='__main__':unittest.main()
