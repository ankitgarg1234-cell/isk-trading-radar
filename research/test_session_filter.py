import copy
import unittest

from research.session_filter import filter_confirmed_closures


def row(day, close, volume=1000):
    return {"date": day, "open": close, "high": close, "low": close,
            "close": close, "adjusted_close": close, "volume": volume}


CLOSURES = {"XTAI": {"2026-07-10": {"reason": "Confirmed typhoon closure", "source": "Independent evidence"}}}


class SessionFilterTests(unittest.TestCase):
    def test_carry_forward_is_excluded_without_mutation_or_redating(self):
        rows = [row("2026-07-09", 100), row("2026-07-10", 100, 0), row("2026-07-13", 105)]
        original = copy.deepcopy(rows)
        result = filter_confirmed_closures(rows, "XTAI", CLOSURES)
        self.assertEqual(rows, original)
        self.assertEqual([r["date"] for r in result["rows"]], ["2026-07-09", "2026-07-13"])
        audit = result["excluded_observations"][0]
        self.assertEqual(audit["classification"], "consistent_with_carry_forward_placeholder")
        self.assertEqual(audit["original_observation"], original[1])
        self.assertFalse(audit["valid_trading_session"])

    def test_zero_volume_on_open_day_is_not_automatically_removed(self):
        rows = [row("2026-07-09", 100, 0), row("2026-07-13", 105)]
        result = filter_confirmed_closures(rows, "XTAI", CLOSURES)
        self.assertEqual(result["rows"], rows)
        self.assertEqual(result["excluded_observations"], [])

    def test_nonflat_closed_day_bar_is_excluded_without_guessing_a_date(self):
        rows = [row("2026-07-09", 100), row("2026-07-10", 105)]
        result = filter_confirmed_closures(rows, "XTAI", CLOSURES)
        self.assertEqual(result["excluded_observations"][0]["classification"], "bar_on_confirmed_non_trading_session")
        self.assertEqual(len(result["rows"]), 1)

    def test_closure_is_exchange_scoped_and_requires_provenance(self):
        rows = [row("2026-07-10", 100)]
        self.assertEqual(filter_confirmed_closures(rows, "XKRX", CLOSURES)["rows"], rows)
        with self.assertRaises(ValueError):
            filter_confirmed_closures(rows, "XTAI", {"XTAI": {"2026-07-10": {"reason": "Closure"}}})


if __name__ == "__main__":
    unittest.main()
