import csv
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from research.corporate_actions import price_flags, prepare_split_ohlc, split_events, true_ranges
from research.eodhd_client import NoRedirect, ResearchClient, usage_summary
from research.eodhd_probe import read_cached_prices, validate_prices


def bar(day, close, adjusted=None):
    return {"date": day, "open": close, "high": close * 1.01, "low": close * .99,
            "close": close, "adjusted_close": close if adjusted is None else adjusted,
            "volume": 1000}


class CorporateActionTests(unittest.TestCase):
    def test_reverse_representation_change_has_continuous_split_only_prices(self):
        rows = [bar("2026-01-30", 50, 100), bar("2026-02-02", 101, 101)]
        events = split_events([{"date": "2026-02-02", "split": "1/2"}], source="verified feed")
        flags = price_flags(rows)
        self.assertIn("unusual_raw_close_jump", flags[0]["reasons"])
        result = prepare_split_ohlc(rows, events, history_complete=True, basis_date="2026-02-02")
        self.assertEqual(result["status"], "ready_for_research")
        self.assertEqual(result["rows"][0]["close"], 100)
        self.assertEqual(result["rows"][1]["close"], 101)
        self.assertEqual(result["rows"][0]["volume"], 1000)
        self.assertLess(true_ranges(result)[1]["true_range"], 5)
        self.assertTrue(result["event_checks"][0]["passed"])

    def test_missing_or_incorrect_event_blocks_export(self):
        rows = [bar("2026-01-30", 50, 100), bar("2026-02-02", 100, 100)]
        for events, complete in [([], True), ([], False),
                                  (split_events([{"date": "2026-02-02", "split": "2/1"}], source="feed"), True)]:
            result = prepare_split_ohlc(rows, events, history_complete=complete, basis_date="2026-02-02")
            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["rows"], [])
            with self.assertRaises(ValueError):
                true_ranges(result)

    def test_forward_split_and_multiple_events(self):
        rows = [bar("2026-01-01", 120, 20), bar("2026-01-02", 60, 20), bar("2026-01-05", 20, 20)]
        events = split_events([{"date": "2026-01-02", "split": "2/1"},
                               {"date": "2026-01-05", "split": "3/1"}], source="feed")
        result = prepare_split_ohlc(rows, events, history_complete=True, basis_date="2026-01-05")
        self.assertEqual(result["status"], "ready_for_research")
        self.assertEqual([r["close"] for r in result["rows"]], [20, 20, 20])

    def test_dividends_do_not_enter_ohlc_adjustment(self):
        rows = [bar("2026-01-01", 100, 95), bar("2026-01-02", 98, 94)]
        result = prepare_split_ohlc(rows, [], history_complete=True, basis_date="2026-01-02")
        self.assertEqual([r["close"] for r in result["rows"]], [100, 98])

    def test_unexplained_adjusted_jump_is_not_mistaken_for_split(self):
        result = prepare_split_ohlc([bar("2026-01-01", 100), bar("2026-01-02", 150)],
                                    [], history_complete=True, basis_date="2026-01-02")
        self.assertEqual(result["status"], "blocked")

    def test_verified_extreme_market_return_preserves_prices_and_true_range(self):
        for pct in (26.81, 29.95, 29.92):
            with self.subTest(return_pct=pct):
                rows = [bar("2026-07-30", 100), bar("2026-07-31", 100 + pct)]
                evidence = {"2026-07-31": {"return_pct": pct, "source": "Independent IBKR daily return"}}
                flag = price_flags(rows, verified_returns=evidence)[0]
                self.assertEqual(flag["classification"], "verified_extreme_market_return")
                self.assertFalse(flag["requires_review"])
                result = prepare_split_ohlc(rows, [], history_complete=True, basis_date="2026-07-31",
                                            verified_returns=evidence)
                self.assertEqual(result["status"], "ready_for_research")
                self.assertEqual(result["rows"][1]["close"], 100 + pct)
                self.assertEqual([r["split_price_multiplier"] for r in result["rows"]], [1, 1])
                self.assertGreater(true_ranges(result)[1]["true_range"], pct)

    def test_extreme_return_evidence_cannot_hide_corporate_action_discontinuity(self):
        rows = [bar("2026-07-30", 50, 100), bar("2026-07-31", 100, 100)]
        evidence = {"2026-07-31": {"return_pct": 100, "source": "Independent raw return"}}
        flag = price_flags(rows, verified_returns=evidence)[0]
        self.assertEqual(flag["classification"], "corporate_action_discontinuity")
        self.assertTrue(flag["requires_review"])
        self.assertFalse(flag["independent_return_matches"])
        result = prepare_split_ohlc(rows, [], history_complete=True, basis_date="2026-07-31",
                                    verified_returns=evidence)
        self.assertEqual(result["status"], "blocked")

    def test_wrong_date_return_or_missing_provenance_remains_unverified(self):
        rows = [bar("2026-07-30", 100), bar("2026-07-31", 130)]
        for evidence in ({"2026-07-30": {"return_pct": 30, "source": "IBKR"}},
                         {"2026-07-31": {"return_pct": 29.95, "source": "IBKR"}},
                         {"2026-07-31": {"return_pct": 30}},
                         {"2026-07-31": {"return_pct": float('nan'), "source": "IBKR"}}):
            flag = price_flags(rows, verified_returns=evidence)[0]
            self.assertEqual(flag["classification"], "unverified_extreme_market_return")
            self.assertTrue(flag["requires_review"])

    def test_noninteger_ratio_and_invalid_events(self):
        events = split_events([{"date": "2026-02-02", "split": "104/100"}], source="feed")
        self.assertEqual(events[0]["new_shares_per_old_share"], 1.04)
        for ratio in ("1/0", "-1/2", "nan/1", "1/inf", "bad", "1/2/3"):
            with self.assertRaises(ValueError):
                split_events([{"date": "2026-02-02", "split": ratio}], source="feed")
        with self.assertRaises(ValueError):
            split_events([{"date": "2026-02-02", "split": "1/2"}] * 2, source="feed")

    def test_events_between_sessions_and_after_last_price(self):
        rows = [bar("2026-01-02", 100, 50), bar("2026-01-05", 50, 50)]
        events = split_events([{"date": "2026-01-04", "split": "2/1"},
                               {"date": "2026-01-06", "split": "5/1"}], source="feed")
        result = prepare_split_ohlc(rows, events, history_complete=True, basis_date="2026-01-06")
        self.assertEqual([r["close"] for r in result["rows"]], [10, 10])

    def test_malformed_ohlc_and_boolean_values_rejected(self):
        for key, value in [("high", 1), ("open", True), ("volume", 1.5)]:
            row = bar("2026-01-01", 100)
            row[key] = value
            with self.assertRaises(ValueError):
                validate_prices([row])

    def test_cached_prices_are_validated_and_flagged_without_network(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "prices.csv"
            rows = [bar("2026-01-30", 50, 100), bar("2026-02-02", 101, 101)]
            with path.open("w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            self.assertEqual(len(price_flags(read_cached_prices(path))), 1)
            path.write_text("date,close\n2026-01-30,50\n")
            with self.assertRaisesRegex(ValueError, "Malformed cached"):
                read_cached_prices(path)


class BudgetTests(unittest.TestCase):
    def test_costs_and_request_count_are_separately_capped(self):
        with tempfile.TemporaryDirectory() as d:
            client = ResearchClient(Path(d) / "ledger.json", budget=2, request_limit=3)
            client.reserve("user", "")
            client.reserve("eod", "a")
            client.reserve("splits", "a")
            with self.assertRaises(RuntimeError):
                client.reserve("user", "")
            self.assertEqual(json.loads(client.ledger.read_text())["reserved_units"], 2)
            with self.assertRaises(ValueError):
                client.reserve("technical", "a")

    def test_failed_calls_reserved_and_credential_errors_redacted(self):
        class FailingOpener:
            def open(self, req, timeout):
                raise HTTPError(req.full_url, 403, "private-token", {}, None)
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {"EODHD_API_TOKEN": "private-token"}):
            client = ResearchClient(Path(d) / "ledger.json", opener=FailingOpener())
            with self.assertRaisesRegex(RuntimeError, "EODHD HTTP status 403") as error:
                client.get("eod", "AZN.US")
            self.assertNotIn("private-token", str(error.exception))
            self.assertNotIn("private-token", client.ledger.read_text())
            self.assertEqual(json.loads(client.ledger.read_text())["reserved_units"], 1)

    def test_no_redirect_or_personal_account_data(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.example"))
        summary = usage_summary({"apiRequests": "8", "dailyRateLimit": 20,
                                 "apiRequestsDate": "2000-01-01", "email": "private"})
        self.assertEqual(summary["remaining_units_today"], 20)
        self.assertNotIn("email", summary)


if __name__ == "__main__":
    unittest.main()
