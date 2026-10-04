"""Standard-library integrity tests; no provider or production access."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import score_band_historical as replay


def record(price=100, when="2024-01-02T14:30:00+00:00"):
    return {"bundle": {"symbol": "FIXTURE", "price": price, "currency": "USD",
        "data_sources": {"price": {"quote_asof": when}},
        "history": [{"date": "2023-12-29", "close": 99, "available_at": "2023-12-29T21:00:00+00:00"}],
        "fundamentals": {}, "news": []},
        "evidence": [{"kind": k, "source": "synthetic integrity fixture", "availability_basis": "verified_publication",
                      "available_at": "2023-12-29T21:00:00+00:00"} for k in sorted(replay.REQUIRED_EVIDENCE)],
        "fundamental_facts": [{"accepted_at": "2023-12-29T20:00:00+00:00", "accession": "TEST"}]}


def synthetic_score(bundle):
    # Explicit test-only scoring fixture, never used to publish historical yield.
    return {"deterministic_score": 90, "analyst_score": 80, "lane_qualified": True,
        "decision_confidence": "high", "levels": {"stop": 99, "buy_low": 98, "buy_high": 102,
        "breakout": 110, "do_not_chase": 114}, "target_plan": {"base_target": 120},
        "technicals": {"rsi": 55, "ema20": 99, "change20_pct": 2, "relative_volume": 1.6, "atr": 2}}


def archive(path, events, expected=None):
    header = {"universe": "historical_US_equities", "price_basis": "as_traded", "includes_delisted": True,
        "coverage_complete": True, "publication_times_verified": True,
        "start": "2024-01-01", "end": "2024-12-31", "expected_valuation_dates": expected or ["2024-01-02"]}
    path.write_text("\n".join(json.dumps(x) for x in [header] + events) + "\n")


def event(when, price=100):
    return {"event_at": when, "market_open": True, "records": [record(price, when)]}


class HistoricalIntegrity(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dir = Path(self.temp.name)
        self.protocol = {"start": "2024-01-01", "end": "2024-12-31", "fixed": "fixture"}
        self.when = "2024-01-02T14:30:00+00:00"

    def tearDown(self):
        self.temp.cleanup()

    def checkpoint(self, name="checkpoint.sqlite"):
        cp = replay.Checkpoint(self.dir / name, self.protocol)
        self.addCleanup(cp.close)
        return cp

    def test_calendar_return_includes_first_trading_day(self):
        rows = [{"date": "2023-12-29", "close": 100}, {"date": "2024-01-02", "close": 90},
                {"date": "2024-12-31", "close": 125}, {"date": "2025-12-31", "close": 150}]
        out = replay.benchmark_years(rows, "2024-01-01", "2025-12-31")
        self.assertEqual([r["benchmark_return_pct"] for r in out], [25, 20])
        self.assertEqual(out[0]["baseline_date"], "2023-12-29")

    def test_partial_year_does_not_claim_full_yoy(self):
        self.assertIsNone(replay.benchmark_years([{"date": "2024-01-02", "close": 100}], "2024-01-02", "2024-12-31")[0]["benchmark_return_pct"])

    def test_missing_prior_year_baseline_is_unavailable(self):
        self.assertIsNone(replay.benchmark_years([{"date": "2024-12-31", "close": 120}], "2024-01-01", "2024-12-31")[0]["benchmark_return_pct"])

    def test_resume_protocol_mismatch_refuses_reset(self):
        cp = self.checkpoint(); cp.put("proof", {"cash": 9876})
        with self.assertRaisesRegex(ValueError, "differ"):
            replay.Checkpoint(self.dir / "checkpoint.sqlite", {**self.protocol, "fixed": "changed"})
        self.assertEqual(cp.get("proof"), {"cash": 9876})

    def test_checkpoint_transaction_rolls_back_partial_batch(self):
        cp = self.checkpoint(); cp.put("proof", {"cash": 10000})
        with self.assertRaises(RuntimeError):
            with cp.db:
                cp.db.execute("UPDATE chunks SET value='{}' WHERE key='proof'")
                raise RuntimeError("interrupted transaction")
        self.assertEqual(cp.get("proof"), {"cash": 10000})

    def test_future_analyst_rejected(self):
        r = record(); r["evidence"][0]["available_at"] = "2024-01-02T14:31:00+00:00"
        with self.assertRaisesRegex(ValueError, "Forward"):
            replay.observation_from_record(r, self.when)

    def test_month_label_does_not_prove_availability(self):
        r = record(); r["evidence"][0]["availability_basis"] = "month_label"
        with self.assertRaisesRegex(ValueError, "Period labels"):
            replay.observation_from_record(r, self.when)

    def test_missing_analyst_evidence_rejected(self):
        r = record(); r["evidence"] = [e for e in r["evidence"] if e["kind"] != "analyst"]
        with self.assertRaisesRegex(ValueError, "missing"):
            replay.observation_from_record(r, self.when)

    def test_future_price_bar_rejected(self):
        r = record(); r["bundle"]["history"][0]["available_at"] = "2024-01-02T21:00:00+00:00"
        with self.assertRaisesRegex(ValueError, "price bar"):
            replay.observation_from_record(r, self.when)

    def test_future_sec_acceptance_rejected(self):
        r = record(); r["fundamental_facts"][0]["accepted_at"] = "2024-01-02T21:05:00+00:00"
        with self.assertRaisesRegex(ValueError, "Unaccepted"):
            replay.observation_from_record(r, self.when)

    def test_unproven_derived_quarter_rejected(self):
        r = record(); r["fundamental_facts"][0]["derived"] = True
        with self.assertRaisesRegex(ValueError, "Unproven"):
            replay.observation_from_record(r, self.when)

    def test_future_news_rejected(self):
        r = record(); r["bundle"]["news"] = [{"providerPublishTime": replay.valid_time(self.when).timestamp() + 1}]
        with self.assertRaisesRegex(ValueError, "Future news"):
            replay.observation_from_record(r, self.when)

    def test_future_sector_data_rejected(self):
        r = record(); r["bundle"]["sector_benchmark"] = {"history": [{"date": "2024-01-02", "available_at": "2024-01-02T21:00:00+00:00"}]}
        with self.assertRaisesRegex(ValueError, "Future sector"):
            replay.observation_from_record(r, self.when)

    def test_stale_quote_rejected(self):
        with self.assertRaisesRegex(ValueError, "stale"):
            replay.observation_from_record(record(), "2024-01-02T14:41:00+00:00")

    def test_scores_recomputed_not_taken_from_archive(self):
        r = record(); r["bundle"].update(deterministic_score=100, analyst_score=100)
        with patch.object(replay, "score_bundle", synthetic_score):
            out = replay.observation_from_record(r, self.when)
        self.assertEqual((out["deterministic_score"], out["analyst_score"]), (90, 80))

    def test_later_fill_and_restart_equal_uninterrupted(self):
        path = self.dir / "archive.jsonl"
        events = [event(self.when), event("2024-01-02T14:32:00+00:00"),
            {"kind": "valuation", "event_at": "2024-01-02T21:00:00+00:00", "marks": {
                "FIXTURE": {"price": 100, "quote_asof": "2024-01-02T21:00:00+00:00"}}}]
        archive(path, events)
        full, segmented = self.checkpoint("full.sqlite"), self.checkpoint("segmented.sqlite")
        with patch.object(replay, "score_bundle", synthetic_score):
            expected = replay.replay_events(path, self.protocol, full)
            paused = replay.replay_events(path, self.protocol, segmented, max_new_chunks=1)
            self.assertEqual(paused["status"], "paused")
            self.assertEqual(segmented.get("replay")["state"]["variants"]["complete_strategy"]["trades"], [])
            actual = replay.replay_events(path, self.protocol, segmented)
        self.assertEqual(replay.digest(expected), replay.digest(actual))
        self.assertTrue(actual["mechanics_valid"])
        self.assertFalse(actual["performance_valid"])
        trade = actual["trades"][0]
        self.assertEqual(trade["shares"], 39)
        self.assertLess(trade["signal_at"], trade["observed_at"])

    def test_future_suffix_cannot_change_prefix_state(self):
        a, b = self.dir / "a.jsonl", self.dir / "b.jsonl"
        archive(a, [event(self.when), event("2024-01-02T14:32:00+00:00", 100)])
        archive(b, [event(self.when), event("2024-01-02T14:32:00+00:00", 1000)])
        ca, cb = self.checkpoint("a.sqlite"), self.checkpoint("b.sqlite")
        with patch.object(replay, "score_bundle", synthetic_score):
            replay.replay_events(a, self.protocol, ca, 1); replay.replay_events(b, self.protocol, cb, 1)
        self.assertEqual(ca.get("replay"), cb.get("replay"))

    def test_bad_batch_is_quarantined_without_manufactured_roi(self):
        path = self.dir / "bad.jsonl"
        bad = event(self.when); bad["records"][0]["evidence"] = []
        archive(path, [bad])
        out = replay.replay_events(path, self.protocol, self.checkpoint())
        self.assertEqual(out["status"], "completed_with_data_gaps")
        self.assertFalse(out["performance_valid"])
        self.assertEqual(len(out["errors"]), 1)
        self.assertEqual(out["state"]["variants"]["complete_strategy"]["cash"], 10000)

    def test_whole_share_cash_invariants(self):
        s = replay.new_state("HIGH"); s["variants"]["complete_strategy"]["cash"] = -1
        with self.assertRaisesRegex(ValueError, "Cash"):
            replay.validate_book(s)

    def test_sparse_valuation_archive_cannot_publish_annual_return(self):
        report = {"protocol": self.protocol, "annual_comparison": [], "performance_valid": False}
        r = {"performance_valid": True, "expected_valuation_dates": ["2024-01-02"], "curves": [], "state": {}}
        replay.compare_replay(report, r, [{"date": "2024-01-02"}, {"date": "2024-12-31"}])
        self.assertFalse(report["performance_valid"])

    def test_clock_order_reversal_refused(self):
        path = self.dir / "badclock.jsonl"
        archive(path, [event(self.when), event(self.when)])
        with patch.object(replay, "score_bundle", synthetic_score), self.assertRaisesRegex(ValueError, "chronological"):
            replay.replay_events(path, self.protocol, self.checkpoint())

    def test_split_adjusted_basis_is_refused(self):
        path = self.dir / "badbasis.jsonl"; archive(path, [])
        records = path.read_text().splitlines(); m = json.loads(records[0]); m["price_basis"] = "split_adjusted"
        path.write_text(json.dumps(m) + "\n")
        with self.assertRaisesRegex(ValueError, "manifest"):
            replay.replay_events(path, self.protocol, self.checkpoint())

    def test_claimed_complete_archive_does_not_certify_return(self):
        path = self.dir / "claimed.jsonl"
        archive(path, [{"kind": "valuation", "event_at": "2024-01-02T21:00:00+00:00", "marks": {}}])
        out = replay.replay_events(path, self.protocol, self.checkpoint())
        self.assertTrue(out["mechanics_valid"])
        self.assertFalse(out["performance_valid"])
        self.assertIn("Independent", out["performance_blocker"])

    def test_future_bar_date_cannot_be_backdated(self):
        r = record(); r["bundle"]["history"][0]["date"] = "2024-01-03"
        with self.assertRaisesRegex(ValueError, "history date"):
            replay.observation_from_record(r, self.when)

    def test_external_thesis_override_refused(self):
        r = record(); r["bundle"]["thesis_assessment"] = {"invalidated": False}
        with self.assertRaisesRegex(ValueError, "lineage"):
            replay.observation_from_record(r, self.when)

    def test_future_financial_period_cannot_be_backdated(self):
        r = record(); r["fundamental_facts"][0]["period_end"] = "2024-03-31"
        with self.assertRaisesRegex(ValueError, "Future financial"):
            replay.observation_from_record(r, self.when)

    def test_unknown_corporate_action_is_not_silently_ignored(self):
        path = self.dir / "action.jsonl"
        archive(path, [{"kind": "split", "event_at": self.when, "market_open": True, "records": []}])
        out = replay.replay_events(path, self.protocol, self.checkpoint())
        self.assertFalse(out["mechanics_valid"])
        self.assertIn("Unsupported event", out["errors"][0]["error"])

    def test_incomplete_year_tail_is_not_annual_return(self):
        out = replay.benchmark_years([{"date": "2023-12-29", "close": 100}, {"date": "2024-01-02", "close": 105}], "2024-01-01", "2024-12-31")
        self.assertFalse(out[0]["full_calendar_year"])
        self.assertIsNone(out[0]["benchmark_return_pct"])

    def test_verified_calendar_counts_and_carter_closure(self):
        self.assertEqual(len(replay.sessions("2024-01-01", "2024-12-31")), 252)
        self.assertEqual(len(replay.sessions("2025-01-01", "2025-12-31")), 250)
        self.assertFalse(replay.regular_market_open(replay.valid_time("2025-01-09T15:00:00+00:00")))

    def test_early_close_blocks_after_hours_poll(self):
        self.assertTrue(replay.regular_market_open(replay.valid_time("2024-07-03T16:59:00+00:00")))
        self.assertFalse(replay.regular_market_open(replay.valid_time("2024-07-03T17:00:00+00:00")))

    def test_early_close_valuation_is_accepted(self):
        path = self.dir / "earlyclose.jsonl"
        archive(path, [{"kind": "valuation", "event_at": "2024-07-03T17:00:00+00:00", "marks": {}}], ["2024-07-03"])
        out = replay.replay_events(path, self.protocol, self.checkpoint())
        self.assertTrue(out["mechanics_valid"])

    def test_holiday_valuation_is_rejected(self):
        path = self.dir / "holiday.jsonl"
        archive(path, [{"kind": "valuation", "event_at": "2024-07-04T20:00:00+00:00", "marks": {}}], ["2024-07-04"])
        out = replay.replay_events(path, self.protocol, self.checkpoint())
        self.assertFalse(out["mechanics_valid"])
        self.assertIn("not on a trading session", out["errors"][0]["error"])

    def test_preclose_mark_cannot_be_used_as_closing_price(self):
        path = self.dir / "preclosemark.jsonl"
        archive(path, [{"kind": "valuation", "event_at": "2024-01-02T21:00:00+00:00", "marks": {
            "FIXTURE": {"price": 100, "quote_asof": "2024-01-02T20:59:00+00:00"}}}])
        out = replay.replay_events(path, self.protocol, self.checkpoint())
        self.assertFalse(out["mechanics_valid"])
        self.assertIn("Invalid closing mark", out["errors"][0]["error"])


if __name__ == "__main__":
    unittest.main()
