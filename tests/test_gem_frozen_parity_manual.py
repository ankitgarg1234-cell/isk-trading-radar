"""Regression tests for frozen GEMv1 growth_margin5 and manual-only operation.

The strategy source is pinned at d59b93d3d9a87d582045b4ae71ff9a6f696a48be.
These tests exercise the standalone operator, not production or broker routes.
"""
import unittest
from unittest.mock import patch

from gem_data.gem_monthly_signal import FROZEN, select_monthly
from gem_data.gem_source_feature_verifier import (
    SourceFeatureHold, verify_financial_features,
)
from gem_data.gem_manual_ops import manual_trade_sheet
from gem_data import gem_monthly_packet


def _feature(ticker, r63):
    return {
        "security_id": "sid-" + ticker,
        "ticker": ticker,
        "r63": r63,
        "nominal_close": 40.0,
        "adv20": 20_000_000.0,
        "revenue_yoy": .25,
        "margin_delta_pp": 4.0,
        "net_income_now": 10.0,
        "net_income_prior": 6.0,
        "earnings_improvement": True,
        "price_last_session": "2026-09-30",
        "price_sessions": 127,
        "price_basis": "FROZEN_VERIFIED",
        "financial_source": "SEC_ORIGINAL_QA_REVIEWED",
        "latest_accepted_at": "2026-08-01T12:00:00+00:00",
        "security_identity_reviewed": True,
    }


def _fact(period_start, period_end, value, *, form="10-Q", filed="2026-08-01"):
    return {
        "form": form,
        "unit": "USD",
        "source_context_reviewed": True,
        "accession": "0000000000-26-000001",
        "period_start": period_start,
        "period_end": period_end,
        "filed": filed,
        "accepted_at": filed + "T14:00:00+00:00",
        "value": value,
    }


class FrozenGemManualParityTests(unittest.TestCase):
    def test_negative_momentum_never_enters_frozen_growth_margin5_ranking(self):
        features = [_feature("NEG", -.05), _feature("POS", .12)]
        snapshot = {
            "schema": "gem-monthly-features-v1",
            "frozen_commit": FROZEN,
            "signal_session": "2026-09-30",
            "next_session": "2026-10-01",
            "calendar_verified": True,
            "universe": [
                {"ticker": row["ticker"], "security_id": row["security_id"]}
                for row in features
            ],
            "features": features,
            "membership_reviewed": True,
            "actions_reviewed": True,
            "benchmark_reviewed": True,
            "source_manifest_reviewed": True,
        }
        ranked = select_monthly(snapshot, fixture_min_members=2)
        self.assertEqual(ranked["data_status"], "REVIEWED_COMPLETE")
        self.assertEqual(ranked["selected"], ["POS"])
        self.assertEqual(ranked["qualified_count"], 1)
        self.assertFalse(next(x for x in ranked["candidate_audit"] if x["ticker"] == "NEG")["eligible"])

    def test_independent_latest_revenue_and_income_quarters_and_10qa(self):
        # The archived PIT store selects latest revenue and income periods independently.
        # Operating income must align with REVENUE periods for margin.
        facts = {
            "revenue_now": _fact("2026-04-01", "2026-06-30", 125.0, form="10-Q/A"),
            "revenue_prior": _fact("2025-04-01", "2025-06-30", 100.0, filed="2025-08-01"),
            "income_now": _fact("2026-01-01", "2026-03-31", 12.0, filed="2026-05-01"),
            "income_prior": _fact("2025-01-01", "2025-03-31", 8.0, filed="2025-05-01"),
            "operating_now": _fact("2026-04-01", "2026-06-30", 30.0),
            "operating_prior": _fact("2025-04-01", "2025-06-30", 20.0, filed="2025-08-01"),
        }
        result = verify_financial_features(facts, signal_day="2026-09-30")
        self.assertAlmostEqual(result["revenue_yoy"], .25)
        self.assertTrue(result["earnings_improvement"])
        self.assertAlmostEqual(result["margin_delta_pp"], 4.0)

    def test_10k_is_not_quarterly_evidence(self):
        fact = _fact("2026-04-01", "2026-06-30", 125.0, form="10-K")
        facts = {key: fact for key in (
            "revenue_now", "revenue_prior", "income_now", "income_prior",
            "operating_now", "operating_prior")}
        with self.assertRaises(SourceFeatureHold):
            verify_financial_features(facts, signal_day="2026-09-30")

    def test_fewer_than_five_positions_leave_cash(self):
        sheet = manual_trade_sheet(
            {"selected": ["AAA", "BBB"], "data_status": "REVIEWED_COMPLETE",
             "signal_session": "2026-09-30"},
            {"shares": {}, "cash": "10000"},
            {"AAA": 100.0, "BBB": 200.0},
        )
        self.assertEqual(sheet["status"], "INDICATIVE_USER_REVIEW_REQUIRED")
        self.assertEqual([t["side"] for t in sheet["tickets"]], ["BUY", "BUY"])
        self.assertGreater(float(sheet["estimated_cash_after"]), 5900.0)
        self.assertEqual(sheet["broker_orders_sent"], 0)

    def test_missing_competitor_source_holds_all_top5_publication(self):
        features = [_feature("VALID", .12), _feature("UNKNOWN", .22)]
        features[1]["financial_source"] = "HOLD"
        snapshot = {
            "schema": "gem-monthly-features-v1",
            "frozen_commit": FROZEN,
            "signal_session": "2026-09-30",
            "next_session": "2026-10-01",
            "calendar_verified": True,
            "universe": [
                {"ticker": row["ticker"], "security_id": row["security_id"]}
                for row in features
            ],
            "features": features,
            "membership_reviewed": True,
            "actions_reviewed": True,
            "benchmark_reviewed": True,
            "source_manifest_reviewed": True,
        }
        ranked = select_monthly(snapshot, fixture_min_members=2)
        self.assertEqual(ranked["data_status"], "HOLD")
        self.assertEqual(ranked["selected"], [])
        self.assertEqual(ranked["provisional_top5"], ["VALID"])

    def test_end_to_end_manual_packet_permits_cash_slots(self):
        signal = {"selected": ["AAA", "BBB"], "data_status": "REVIEWED_COMPLETE",
                  "signal_session": "2026-09-30"}
        ledger = {"statement_status": "NO_STATEMENT_ENTERED",
                  "shares": {}, "cash": "10000"}
        bundle = {
            "schema": "gem-manual-month-packet-v1",
            "source_month": {"signal_session": "2026-09-30"},
            "initial_cash": 10000,
            "manual_events": [],
            "reference_prices": {"AAA": 100, "BBB": 200},
        }
        with (patch.object(gem_monthly_packet, "recompute_full_month", return_value=signal),
              patch.object(gem_monthly_packet, "audit_historical_claims",
                           return_value={"certification": "NOT_CERTIFIED"}),
              patch.object(gem_monthly_packet, "replay_manual_events", return_value=ledger)):
            result = gem_monthly_packet.build_monthly_packet(bundle)
        self.assertEqual(result["status"], "INDICATIVE_SHEET_READY_FOR_USER_REVIEW")
        self.assertEqual(len(result["manual_trade_sheet"]["tickets"]), 2)
        self.assertFalse(result["automatic_execution"])

    def test_no_qualifiers_can_sell_to_cash_without_broker(self):
        sheet = manual_trade_sheet(
            {"selected": [], "data_status": "REVIEWED_COMPLETE",
             "signal_session": "2026-09-30"},
            {"shares": {"OLD": 1}, "cash": "1000"},
            {"OLD": 50.0},
        )
        self.assertEqual([t["side"] for t in sheet["tickets"]], ["SELL"])
        self.assertEqual(sheet["broker_orders_sent"], 0)


if __name__ == "__main__":
    unittest.main()
