"""Offline regression tests for extraordinary exchange closures."""
import unittest

from research.build_eodhd_quality_report import coverage


CLOSURES = {"XTAI": {"2026-07-10": {"reason": "Typhoon Bavi exchange closure",
                                     "source": "User-supplied independently verified information"}}}


class ExtraordinaryClosureTests(unittest.TestCase):
    def test_typhoon_closure_is_not_a_missing_tsmc_session(self):
        rows = [{"date": "2026-07-09"}, {"date": "2026-07-13"}]
        result = coverage(rows, "XTAI", "2026-07-09", "2026-07-13", exchange_closures=CLOSURES)
        self.assertEqual(result["expected_sessions_after_reconciliation"], 2)
        self.assertEqual(result["missing_expected_dates"], [])
        self.assertEqual(result["session_coverage_pct"], 100)
        self.assertEqual(result["extraordinary_exchange_closures"][0]["date"], "2026-07-10")

    def test_bar_on_verified_closed_day_is_preserved_and_flagged(self):
        rows = [{"date": day} for day in ("2026-07-09", "2026-07-10", "2026-07-13")]
        result = coverage(rows, "XTAI", "2026-07-09", "2026-07-13", exchange_closures=CLOSURES)
        self.assertEqual(len(rows), 3)
        self.assertEqual(result["bars_on_verified_closed_dates"], ["2026-07-10"])
        self.assertEqual(result["unexpected_dates"], ["2026-07-10"])
        self.assertEqual(result["session_coverage_pct"], 100)

    def test_closure_is_exchange_scoped_and_does_not_hide_other_gaps(self):
        rows = [{"date": "2026-07-13"}]
        result = coverage(rows, "XTAI", "2026-07-09", "2026-07-13", exchange_closures=CLOSURES)
        self.assertEqual(result["missing_expected_dates"], ["2026-07-09"])
        korea = coverage(rows, "XKRX", "2026-07-09", "2026-07-13", exchange_closures=CLOSURES)
        self.assertIn("2026-07-10", korea["missing_expected_dates"])
        self.assertEqual(korea["extraordinary_exchange_closures"], [])

    def test_closure_requires_provenance(self):
        with self.assertRaisesRegex(ValueError, "provenance"):
            coverage([{"date": "2026-07-09"}], "XTAI", "2026-07-09", "2026-07-13",
                     exchange_closures={"XTAI": {"2026-07-10": {"reason": "Typhoon"}}})


if __name__ == "__main__":
    unittest.main()
