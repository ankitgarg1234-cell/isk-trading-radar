"""Synthetic offline checks only: never import live app or contact a broker."""
from dataclasses import replace
from decimal import Decimal
import csv
import gzip
import hashlib
import json
import math
from multiprocessing import get_context
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from gem_paper.common import ControlError, digest
from gem_paper.frozen import ARTIFACT_HASHES, RULES_HASH, verify_frozen_artifacts
from gem_paper.ledger import AuditLedger
from gem_paper.provenance import SourceEvidence, validate_evidence
from gem_paper.qa import QAEvidence, REQUIRED_CHECKS, authorize_purchase, validate_qa
from gem_paper.selection import FeatureRow, select_frozen_features
from gem_paper.simulation import preview_orders, reconcile

SIGNAL = "2026-09-30T20:00:00Z"
DEADLINE = "2026-09-30T03:59:59.999999Z"  # previous exchange-local calendar day
NOW = "2026-10-01T13:30:01Z"
OPEN = "2026-10-01T13:30:00Z"
HASH = "a" * 64


def sample_source():
    return SourceEvidence("sec-1", "sec_fact", "stable-security-1", HASH,
                          "https://www.sec.gov/Archives/edgar/data/1/filing.htm",
                          "2026-06-30T00:00:00Z", "2026-08-05T14:02:00Z",
                          "2026-08-05T14:05:00Z", True, "sec-qa-agent", "10-Q",
                          "0000000001-26-000001", HASH, "2026-08-05")


def sample_qa():
    return QAEvidence("qa-agent", "signal-agent", HASH, HASH, HASH, RULES_HASH,
                      OPEN, "2026-10-01T14:00:00Z",
                      {name: "PASS" for name in REQUIRED_CHECKS},
                      {name: HASH for name in REQUIRED_CHECKS})


def concurrent_append(path, key):
    AuditLedger(path).append("TEST", {"key": key}, idempotency_key=key, recorded_at=NOW)


class FrozenTests(unittest.TestCase):
    def test_pinned_repository_and_artifact_drift(self):
        root = Path(__file__).resolve().parents[2]
        self.assertEqual(verify_frozen_artifacts(root)["rules_hash"], RULES_HASH)
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory)
            for relative in ARTIFACT_HASHES:
                target = copied / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(root / relative, target)
            (copied / next(iter(ARTIFACT_HASHES))).write_text("drift")
            with self.assertRaises(ControlError):
                verify_frozen_artifacts(copied)


class ProvenanceTests(unittest.TestCase):
    def validate(self, source, **kwargs):
        return validate_evidence([source], SIGNAL, DEADLINE, **kwargs)

    def test_contemporaneous_and_original_amendment_form(self):
        self.assertEqual(len(self.validate(sample_source())), 64)
        self.validate(replace(sample_source(), sec_form="10-Q/A"))

    def test_no_future_publication_retrieval_or_period(self):
        for field in ("event_at", "published_at", "retrieved_at"):
            with self.subTest(field=field), self.assertRaises(ControlError):
                self.validate(replace(sample_source(), **{field: "2026-10-02T20:00:00Z"}))

    def test_signal_day_filing_and_missing_acceptance_are_blocked(self):
        for source in (replace(sample_source(), published_at="2026-09-30T14:00:00Z", retrieved_at=SIGNAL),
                       replace(sample_source(), filed_date="2026-09-30"),
                       replace(sample_source(), published_at="2026-08-05"),
                       replace(sample_source(), sec_form="10-K"),
                       replace(sample_source(), verified=False),
                       replace(sample_source(), raw_submission_sha256=""),
                       replace(sample_source(), source_url="https://www.sec.gov.evil.example/filing")):
            with self.subTest(source=source), self.assertRaises(ControlError):
                self.validate(source)

    def test_repair_late_retrieval_does_not_change_original_publication(self):
        source = replace(sample_source(), retrieved_at="2026-10-02T20:00:00Z")
        self.validate(source, retrospective=True)
        with self.assertRaises(ControlError):
            self.validate(source)

    def test_empty_duplicate_sources_and_naive_signal_blocked(self):
        with self.assertRaises(ControlError):
            validate_evidence([], SIGNAL, DEADLINE)
        with self.assertRaises(ControlError):
            validate_evidence([sample_source(), sample_source()], SIGNAL, DEADLINE)
        with self.assertRaises(ControlError):
            validate_evidence([sample_source()], "2026-09-30", DEADLINE)

    def test_kind_specific_publication_chronology_and_dst_cutoff(self):
        for kind in ("sec_fact", "price_bar"):
            with self.subTest(kind=kind), self.assertRaises(ControlError):
                self.validate(replace(sample_source(), kind=kind, event_at="2026-09-01T00:00:00Z"))
        # Announcements can legitimately precede effective membership dates.
        self.validate(replace(sample_source(), kind="membership", event_at="2026-09-01T00:00:00Z"))
        with self.assertRaises(ControlError):
            validate_evidence([sample_source()], SIGNAL, "2026-09-30T04:00:00Z")
        validate_evidence([sample_source()], "2026-11-30T21:00:00Z",
                          "2026-11-30T04:59:59.999999Z")


class QATests(unittest.TestCase):
    def validate(self, qa):
        return validate_qa(qa, HASH, HASH, HASH, NOW)

    def test_complete_qa_checks_can_only_validate_envelope(self):
        self.assertEqual(len(self.validate(sample_qa())), 64)

    def test_nonindependent_unbound_expired_missing_and_failed(self):
        variants = [replace(sample_qa(), reviewer_id="signal-agent"),
                    replace(sample_qa(), signal_hash="b" * 64),
                    replace(sample_qa(), expires_at=OPEN),
                    replace(sample_qa(), checked_at="2026-10-02T13:30:00Z"),
                    replace(sample_qa(), checks={}),
                    replace(sample_qa(), evidence_hashes={}),
                    replace(sample_qa(), checks={**sample_qa().checks, "coverage": "UNKNOWN"})]
        for qa in variants:
            with self.subTest(qa=qa), self.assertRaises(ControlError):
                self.validate(qa)

    def test_authorization_always_denied_even_with_forged_signoff(self):
        for signoff in (None, True, {"approved": True, "user": "owner"}, "SIGNED"):
            decision = authorize_purchase(qa=sample_qa(), signal_hash=HASH,
                                          provenance_hash=HASH, preview_hash=HASH,
                                          now_at=NOW, release_signoff=signoff)
            self.assertIs(decision["authorized"], False)
            self.assertIn("EXECUTION_NOT_IMPLEMENTED", decision["reasons"])
        self.assertIs(authorize_purchase()["authorized"], False)


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "events.jsonl"
        self.ledger = AuditLedger(self.path)

    def tearDown(self):
        self.directory.cleanup()

    def append(self, key="one", payload=None):
        return self.ledger.append("TEST", payload or {"value": 1}, idempotency_key=key, recorded_at=NOW)

    def test_durable_idempotent_retry_and_conflict(self):
        first = self.append()
        retry = self.ledger.append("TEST", {"value": 1}, idempotency_key="one", recorded_at="2026-10-02T00:00:00Z")
        self.assertEqual(first, retry)
        self.assertEqual(len(self.ledger.read()), 1)
        with self.assertRaises(ControlError):
            self.append(payload={"value": 2})

    def test_ambiguous_post_write_failure_recovers_by_idempotency(self):
        import gem_paper.ledger as ledger_module
        original = ledger_module.os.fsync
        call = [0]

        def fail_after_durable_write(fd):
            original(fd)
            call[0] += 1
            if call[0] == 1:
                raise OSError("Synthetic ambiguous acknowledgment failure")

        with patch.object(ledger_module.os, "fsync", side_effect=fail_after_durable_write):
            with self.assertRaises(OSError):
                self.append()
        recovered = self.append()
        self.assertEqual(recovered["sequence"], 1)
        self.assertEqual(len(self.ledger.read()), 1)

    def test_tamper_partial_tail_and_truncation_checkpoint(self):
        self.append()
        self.append("two")
        checkpoint = self.ledger.checkpoint()
        original = self.path.read_bytes()
        self.path.write_bytes(original.replace(b'"value":1', b'"value":2', 1))
        with self.assertRaises(ControlError):
            self.ledger.read()
        self.path.write_bytes(original[:-1])
        with self.assertRaises(ControlError):
            self.append("three")
        self.path.write_bytes(original.splitlines()[0] + b"\n")
        # A valid prefix requires an externally retained checkpoint to detect.
        with self.assertRaises(ControlError):
            self.ledger.read(expected_checkpoint=checkpoint)

    def test_concurrent_processes_same_and_distinct_keys(self):
        context = get_context("fork")
        keys = ["same", "same", "second", "third"]
        processes = [context.Process(target=concurrent_append, args=(str(self.path), key)) for key in keys]
        for process in processes:
            process.start()
        for process in processes:
            process.join(10)
            self.assertEqual(process.exitcode, 0)
        self.assertEqual(len(self.ledger.read()), 3)

    def test_symlink_blocked_and_nan_rejected(self):
        target = Path(self.directory.name) / "target"
        target.write_text("")
        self.path.symlink_to(target)
        with self.assertRaises(OSError):
            self.append()
        self.path.unlink()
        with self.assertRaises(ValueError):
            self.append(payload={"bad": float("nan")})


def row(ticker="AAA", **changes):
    return replace(FeatureRow(ticker, "security-" + ticker, 126, True, 5.,
                              10_000_000., .3, .21, True, 3.1), **changes)


class SelectionTests(unittest.TestCase):
    def select(self, rows):
        return select_frozen_features(rows, expected_member_tickers=[item.ticker for item in rows])

    def test_exact_gate_boundaries_and_stable_original_tie_order(self):
        passing = self.select([row("ZZZ"), row("AAA"), row("BBB", r63=.4)])
        self.assertEqual(passing["selected_tickers"], ["BBB", "AAA", "ZZZ"])
        self.assertEqual(passing["unfilled_slots"], 2)
        for field, value in (("prior_price_observations", 125), ("positive_bars", False),
                             ("nominal_close", 4.999), ("adv20", 9_999_999),
                             ("r63", 0), ("revenue_yoy", .2),
                             ("earnings_improvement", False), ("margin_delta_pp", 3)):
            with self.subTest(field=field):
                self.assertEqual(self.select([row(**{field: value})])["selected_tickers"], [])

    def test_unresolved_competitor_blocks_instead_of_promoting(self):
        with self.assertRaises(ControlError):
            select_frozen_features([row()], expected_member_tickers=["AAA", "BBB"])
        for field in ("r63", "adv20", "revenue_yoy", "margin_delta_pp"):
            with self.subTest(field=field), self.assertRaises(ControlError):
                self.select([row(**{field: float("nan")})])

    def test_five_slots_and_unknown_fields_rejected(self):
        result = self.select([row(str(index), r63=index / 10) for index in range(1, 8)])
        self.assertEqual(result["selected_tickers"], ["7", "6", "5", "4", "3"])
        with self.assertRaises(TypeError):
            FeatureRow(**{**row().__dict__, "forward_252d": 5})

    def test_pinned_observed_feature_projection_matches_21_archived_signal_dates(self):
        """Observed-feature regression only; not full raw PIT/universe parity.

        The archived feature table has already passed the original price gates.
        Missing raw history, nominal prices and universe members remain release
        blockers. Only its explicit known GEM-gate-passing rows are projected
        into FeatureRow here. This is not a prospective coverage certificate.
        """
        base = Path(__file__).resolve().parents[2] / "research_5x/gem_2025_2026_validation"
        feature_path, signal_path = base / "archived_signal_features.csv.gz", base / "signals.csv"
        pinned = {
            feature_path: "66a998967d36b18b0e0041cb5c7c1264362ddbe2792564b2860ed69b3efeb3eb",
            signal_path: "bea6b2d166c78ed2dc2cc7b69986d11ae664f7badb8ffa045b0d7fc53a61bb66",
        }
        for path, expected_hash in pinned.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected_hash)
        with signal_path.open(newline="") as handle:
            original = [record for record in csv.DictReader(handle) if record["policy"] == "original"]
        expected_by_date = {}
        for record in original:
            expected = record["tickers"].split("|") if record["tickers"] else []
            if record["date"] in expected_by_date:
                self.assertEqual(expected_by_date[record["date"]], expected)
            expected_by_date[record["date"]] = expected
        self.assertEqual(len(expected_by_date), 21)
        self.assertTrue(all("2025-01-01" <= signal_date <= "2026-10-09"
                            for signal_date in expected_by_date))
        observed_by_date = {signal_date: [] for signal_date in expected_by_date}
        with gzip.open(feature_path, "rt", newline="") as handle:
            for record in csv.DictReader(handle):
                if record["date"] not in observed_by_date:
                    continue
                try:
                    values = {key: float(record[key]) for key in ("r63", "revenue_yoy", "margin_delta_pp", "adv20")}
                except ValueError:
                    continue  # diagnostic projection of known passing archive rows
                if not all(math.isfinite(value) for value in values.values()):
                    continue
                if not (values["r63"] > 0 and values["revenue_yoy"] > .2
                        and values["margin_delta_pp"] > 3 and record["earnings_improvement"] == "True"):
                    continue
                observed_by_date[record["date"]].append(FeatureRow(
                    ticker=record["ticker"], security_id="archive-projection-" + record["ticker"],
                    # These minimum price-gate placeholders are justified only
                    # by the archive's upstream preparation; no raw proof exists
                    # in this regression and nothing receives a QA PASS from it.
                    prior_price_observations=126, positive_bars=True, nominal_close=5.,
                    adv20=values["adv20"], r63=values["r63"], revenue_yoy=values["revenue_yoy"],
                    earnings_improvement=True, margin_delta_pp=values["margin_delta_pp"]))
        for signal_date, rows in observed_by_date.items():
            with self.subTest(signal_date=signal_date):
                projection = select_frozen_features(rows, expected_member_tickers=[item.ticker for item in rows])
                self.assertEqual(projection["selected_tickers"], expected_by_date[signal_date])


class SimulationTests(unittest.TestCase):
    def preview(self, **changes):
        params = dict(cash="10000", holdings={}, targets=["AAA"], open_prices={"AAA": "100"},
                      signal_at=SIGNAL, execution_at=OPEN, observed_at=NOW, next_session_open_at=OPEN)
        return preview_orders(**{**params, **changes})

    def test_frozen_slot_costs_whole_shares_and_unused_cash(self):
        result = self.preview()
        self.assertEqual(result["orders"][0]["shares"], 19)
        self.assertEqual(Decimal(result["cash"]), Decimal("8096.2"))
        self.assertEqual(Decimal(result["total_cost"]), Decimal("3.8"))
        self.assertIs(result["execution_capability"], False)
        self.assertEqual(result, self.preview())

    def test_sells_before_buys_and_cash_self_financing(self):
        result = self.preview(cash="0", holdings={"OLD": 100},
                              targets=["AAA", "BBB", "CCC", "DDD", "EEE"],
                              open_prices={"OLD": "100", "AAA": "100", "BBB": "100",
                                           "CCC": "100", "DDD": "100", "EEE": "100"})
        self.assertEqual(result["orders"][0]["side"], "SELL")
        self.assertTrue(all(order["side"] == "BUY" for order in result["orders"][1:]))
        self.assertGreaterEqual(Decimal(result["cash"]), 0)
        marked = Decimal(result["cash"]) + sum(result["holdings"].values()) * Decimal(100)
        self.assertEqual(marked + Decimal(result["total_cost"]), Decimal(10000))

    def test_temporal_quote_fractional_position_and_missing_quote_blocked(self):
        for changes in ({"observed_at": SIGNAL}, {"execution_at": SIGNAL},
                        {"next_session_open_at": "2026-10-02T13:30:00Z"},
                        {"holdings": {"AAA": 1.5}}, {"open_prices": {}},
                        {"open_prices": {"AAA": "0"}}, {"cash": "-1"}):
            with self.subTest(changes=changes), self.assertRaises(ControlError):
                self.preview(**changes)

    def test_reconciliation_drift_detected(self):
        self.assertTrue(reconcile(expected_cash="100", observed_cash="100.0",
                                  expected_holdings={"AAA": 2}, observed_holdings={"AAA": 2})["passed"])
        mismatch = reconcile(expected_cash="100", observed_cash="99.99",
                             expected_holdings={"AAA": 2}, observed_holdings={"AAA": 3})
        self.assertFalse(mismatch["passed"])
        self.assertEqual(mismatch["share_deltas"], {"AAA": 1})


if __name__ == "__main__":
    unittest.main()
