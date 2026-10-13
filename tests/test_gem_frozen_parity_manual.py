"""Regression tests for frozen GEMv1 growth_margin5 and manual-only operation.

The strategy source is pinned at d59b93d3d9a87d582045b4ae71ff9a6f696a48be.
These tests exercise the standalone operator, not production or broker routes.
"""
import unittest
import ast
import hashlib
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
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


def _pinned_original_pit_store(rows):
    # Execute only the original quarterly selector; no app imports or providers.
    path = Path(__file__).resolve().parents[1] / "scripts/wf3_offline_valuein.py"
    source = path.read_bytes()
    expected = "521d6327ba932bde5e548b1b44cc2469afbb69c31e0428f13e2260678468b6d8"
    if hashlib.sha256(source).hexdigest() != expected:
        raise AssertionError("Original GEM PIT selector hash changed")
    cls = next(n for n in ast.parse(source.decode()).body
               if isinstance(n, ast.ClassDef) and n.name == "PITFundamentals")
    def d(v):
        try:
            return date.fromisoformat(str(v)[:10]) if v else None
        except ValueError:
            return None
    def fv(v):
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None
    ns = {"defaultdict": defaultdict, "date": date, "timedelta": timedelta,
          "d": d, "fv": fv}
    exec(compile(ast.Module(body=[cls], type_ignores=[]), str(path), "exec"), ns)
    return ns["PITFundamentals"]({"facts": {"AAA": rows}})


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

    def test_proven_nonpositive_r63_needs_no_sec_quarter_docs(self):
        negative = _feature("NEG", -.10)
        for key in ("revenue_yoy","margin_delta_pp","net_income_now",
                    "net_income_prior","earnings_improvement","latest_accepted_at"):
            negative[key] = None
        negative["financial_source"] = "NOT_REQUIRED_AFTER_FROZEN_R63_FAIL"
        positive = _feature("POS", .12)
        snapshot = {"schema": "gem-monthly-features-v1",
                    "frozen_commit": FROZEN,
                    "signal_session": "2026-09-30", "next_session": "2026-10-01",
                    "calendar_verified": True,
                    "universe": [
                        {"ticker": r["ticker"], "security_id": r["security_id"]}
                        for r in (negative, positive)],
                    "features": [negative, positive],
                    "membership_reviewed": True, "actions_reviewed": True,
                    "benchmark_reviewed": True, "source_manifest_reviewed": True}
        result = select_monthly(snapshot, fixture_min_members=2)
        self.assertEqual(result["data_status"], "REVIEWED_COMPLETE")
        self.assertEqual(result["selected"], ["POS"])
        self.assertFalse(next(r for r in result["candidate_audit"]
                              if r["ticker"] == "NEG")["sec_facts_required"])
        self.assertTrue(next(r for r in result["candidate_audit"]
                             if r["ticker"] == "POS")["sec_facts_required"])

    def test_unverified_negative_momentum_must_not_skip_sec_or_release(self):
        negative = _feature("NEG", -.10)
        negative["price_basis"] = "HOLD"
        negative["financial_source"] = "NOT_REQUIRED_AFTER_FROZEN_R63_FAIL"
        negative["revenue_yoy"] = None
        negative["margin_delta_pp"] = None
        negative["latest_accepted_at"] = None
        positive = _feature("POS", .12)
        snapshot = {"schema": "gem-monthly-features-v1",
                    "frozen_commit": FROZEN,
                    "signal_session": "2026-09-30", "next_session": "2026-10-01",
                    "calendar_verified": True,
                    "universe": [
                        {"ticker": r["ticker"], "security_id": r["security_id"]}
                        for r in (negative, positive)],
                    "features": [negative, positive],
                    "membership_reviewed": True, "actions_reviewed": True,
                    "benchmark_reviewed": True, "source_manifest_reviewed": True}
        result = select_monthly(snapshot, fixture_min_members=2)
        self.assertEqual(result["data_status"], "HOLD")
        self.assertEqual(result["selected"], [])
        self.assertTrue(next(r for r in result["candidate_audit"]
                             if r["ticker"] == "NEG")["sec_facts_required"])

    def test_recompute_source_month_only_verifies_sec_for_positive_momentum(self):
        from gem_data import gem_source_feature_verifier as source_verifier
        members = [{"ticker": t, "security_id": "sid-" + t}
                   for t in ("NEG","POS")]
        bundle = {
            "schema": "gem-source-month-v1",
            "universe": members,
            "candidates": [
                {"ticker": t, "security_id": "sid-" + t,
                 "prices": {"ticker": t}, "facts": None,
                 "identity_reviewed": True} for t in ("NEG","POS")],
            "completed_sessions": [f"DAY{i:03d}" for i in range(126)] + ["2026-09-30"],
            "signal_session": "2026-09-30", "next_session": "2026-10-01",
            "calendar_verified": True,
            "membership_reviewed": True, "actions_reviewed": True,
            "benchmark_reviewed": True, "source_manifest_reviewed": True,
        }
        def price_check(price, **_):
            return {"r63": -.1 if price["ticker"] == "NEG" else .2,
                    "nominal_close": 100.0, "adv20": 20_000_000.0,
                    "price_last_session": "2026-09-30",
                    "price_sessions": 127, "price_basis": "FROZEN_VERIFIED"}
        financial = {
            "revenue_yoy": .25, "margin_delta_pp": 4.0,
            "net_income_now": 12.0, "net_income_prior": 8.0,
            "earnings_improvement": True,
            "financial_source": "SEC_ORIGINAL_QA_REVIEWED",
            "latest_accepted_at": "2026-08-01T12:00:00+00:00"}
        with (patch.object(source_verifier,"verify_price_features",
                           side_effect=price_check) as pv,
              patch.object(source_verifier,"verify_financial_features",
                           return_value=financial) as fv):
            report = source_verifier.recompute_full_month(bundle,
                                                          fixture_min_members=2)
        self.assertEqual(report["selected"], ["POS"])
        self.assertEqual(report["data_status"], "REVIEWED_COMPLETE")
        self.assertEqual(pv.call_count, 2)
        self.assertEqual(fv.call_count, 1)

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

    def test_frozen_pit_latest_amendment_wins_for_same_quarter(self):
        def row(form, filing, value):
            return {"standard_concept": "TotalRevenue",
                    "form_type": form, "filing_date": filing,
                    "accepted_at": filing + "T12:00:00",
                    "period_start": "2026-04-01", "period_end": "2026-06-30",
                    "period_span_days": 90, "numeric_value": value}
        store = _pinned_original_pit_store([
            row("10-Q", "2026-07-20", 111.0),
            row("10-Q/A", "2026-08-20", 125.0)])
        q = store.quarter("AAA", "TotalRevenue", date(2026, 9, 29))
        self.assertEqual(q[-1][1], 125.0)
        self.assertEqual(q[-1][2]["form_type"], "10-Q/A")

    def test_frozen_pit_derived_quarter_remains_unimplemented_in_adapter(self):
        row = {"standard_concept": "TotalRevenue", "form_type": "10-Q",
               "filing_date": "2026-08-01",
               "accepted_at": "2026-08-01T12:00:00",
               "period_start": "2026-01-01", "period_end": "2026-06-30",
               "period_span_days": 180, "numeric_value": 240.0,
               "derived_quarterly_value": 125.0}
        store = _pinned_original_pit_store([row])
        q = store.quarter("AAA", "TotalRevenue", date(2026, 9, 29))
        self.assertEqual(q[-1][1], 125.0)
        derived = _fact("2026-01-01", "2026-06-30", 125.0)
        facts = {k: derived for k in (
            "revenue_now", "revenue_prior", "income_now", "income_prior",
            "operating_now", "operating_prior")}
        # This documents an unresolved parity gap without weakening HOLD.
        with self.assertRaises(SourceFeatureHold):
            verify_financial_features(facts, signal_day="2026-09-30")

    def test_selected_holding_reduces_at_frozen_fee_inclusive_target(self):
        # Frozen simulator: desired=floor(open_equity*0.20/(open*1.002)).
        # At NAV 10,000 and price 100, the desired amount is 19, not 20.
        sheet = manual_trade_sheet(
            {"selected": ["AAA"], "data_status": "REVIEWED_COMPLETE",
             "signal_session": "2026-09-30"},
            {"shares": {"AAA": 20}, "cash": "8000"},
            {"AAA": 100.0},
        )
        self.assertEqual(
            [(ticket["ticker"], ticket["side"], ticket["estimated_shares"])
             for ticket in sheet["tickets"]],
            [("AAA", "SELL", 1)],
            "A selected holding must be reduced to its fee-inclusive frozen target",
        )

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
