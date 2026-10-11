import copy
import json
import tempfile
import unittest
from pathlib import Path

from research_5x.gem_competitor_certification.certify import (
    HERE, build, impact_bound, priority, recheck_use, write_artifacts,
)
from research_5x.gem_competitor_certification.workflow import (
    CHECKS, FROZEN_COMMIT, SCHEMA_VERSION, case_id,
    validate_certification_decision, validate_transition, verify_audit_events,
)
from research_5x.gem_competitor_certification.primary_review import build_primary_review, parse_header, consolidated_quarter_facts, exact_number_match, frozen_earnings_pass
from research_5x.gem_competitor_certification.acquire_primary import acquisition_plan


def retained_fixture():
    use = {"signal_date": "2025-03-31", "signal_timestamp": "2025-03-31T20:01:00+00:00",
           "ticker": "XYZ", "concept": "OperatingIncome", "period_end": "2024-12-31",
           "period_start": "2024-10-01", "accession": "0000000001-25-000001",
           "cik": "0000000001", "used_value": "100", "sec_accepted_at": "2025-02-15T20:00:00Z",
           "sec_facts_url": "https://data.sec.gov/api/xbrl/companyfacts/CIK0000000001.json",
           "sec_raw_response_sha256": "a" * 64,
           "submissions_url": "https://data.sec.gov/submissions/CIK0000000001.json",
           "submissions_response_sha256": "b" * 64, "fact_status": "IGNORED_PRIOR_LABEL"}
    evidence = {k: use[k] for k in ("signal_date", "ticker", "concept", "period_end", "accession", "cik", "sec_accepted_at")}
    evidence["source_sha256"] = "a" * 64
    evidence["direct_quarter_facts"] = [{"accn": use["accession"], "tag": "OperatingIncomeLoss",
                                         "start": "2024-10-01", "end": "2024-12-31", "val": 100,
                                         "form": "10-Q", "filed": "2025-02-15"}]
    manifest = {use["sec_facts_url"]: {"status": "200", "sha256": "a" * 64},
                use["submissions_url"]: {"status": "200", "sha256": "b" * 64}}
    return use, evidence, manifest


def reviewed_decision():
    return {"schema_version": SCHEMA_VERSION, "frozen_commit": FROZEN_COMMIT,
            "case_id": case_id("2025-03-31", "XYZ"), "signal_date": "2025-03-31", "ticker": "XYZ",
            "state": "CERTIFIED_ELIGIBLE_DISPLACING", "collector_id": "collector",
            "reviewer_id": "reviewer-a", "second_reviewer_id": "reviewer-b",
            "evidence_bundle_sha256": "c" * 64,
            "checks": {key: {"passed": True, "verifier_id": "reviewer-a", "evidence_sha256": "d" * 64,
                             "second_passed": True, "second_verifier_id": "reviewer-b", "second_evidence_sha256": "e" * 64}
                       for key in CHECKS},
            "recomputed_result": {"eligible": True, "selected": True},
            "second_recomputed_result": {"eligible": True, "selected": True}}


class EvidenceRecheckTests(unittest.TestCase):
    def test_retained_fields_match_without_certifying_case(self):
        result = recheck_use(*retained_fixture())
        self.assertEqual(result["recheck_status"], "CACHED_ACCESSION_VALUE_TIME_MATCH")
        self.assertFalse(result["strict_case_certified"])
        self.assertFalse(result["raw_acceptance_document_retained"])

    def test_equal_value_in_wrong_accession_never_proves_fact(self):
        use, evidence, manifest = retained_fixture()
        evidence["direct_quarter_facts"][0]["accn"] = "another-accession"
        self.assertEqual(recheck_use(use, evidence, manifest)["recheck_status"], "UNRESOLVED")

    def test_pretax_tag_never_proves_operating_income(self):
        use, evidence, manifest = retained_fixture()
        evidence["direct_quarter_facts"][0]["tag"] = "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"
        self.assertIn("NO_TIMELY_MATCHING_10Q_DIRECT_QUARTER", recheck_use(use, evidence, manifest)["errors"])

    def test_same_end_different_start_requires_lineage_review(self):
        use, evidence, manifest = retained_fixture()
        evidence["direct_quarter_facts"][0]["start"] = "2024-10-02"
        self.assertIn("DIRECT_PERIOD_START_LINEAGE_MISMATCH_OR_ABSENT", recheck_use(use, evidence, manifest)["errors"])

    def test_signal_day_fact_rejected_even_before_closing_signal(self):
        use, evidence, manifest = retained_fixture()
        use["sec_accepted_at"] = evidence["sec_accepted_at"] = "2025-03-31T12:00:00Z"
        evidence["direct_quarter_facts"][0]["filed"] = "2025-03-31"
        errors = recheck_use(use, evidence, manifest)["errors"]
        self.assertIn("ACCEPTANCE_AFTER_PREVIOUS_DAY_CUTOFF", errors)
        self.assertIn("NO_TIMELY_MATCHING_10Q_DIRECT_QUARTER", errors)

    def test_naive_acceptance_timestamp_fail_closed(self):
        use, evidence, manifest = retained_fixture()
        use["sec_accepted_at"] = evidence["sec_accepted_at"] = "2025-02-15T20:00:00"
        self.assertIn("ACCEPTANCE_UNVERIFIED", recheck_use(use, evidence, manifest)["errors"])

    def test_manifest_hash_mismatch_requires_reacquisition(self):
        use, evidence, manifest = retained_fixture()
        manifest[use["sec_facts_url"]]["sha256"] = "f" * 64
        self.assertIn("FACT_SOURCE_MANIFEST_MISMATCH", recheck_use(use, evidence, manifest)["errors"])


class PriorityAndImpactTests(unittest.TestCase):
    def test_below_cutoff_can_fill_empty_slot(self):
        selected = [{"ticker": "A", "r63": "0.3"}]
        self.assertEqual(priority({"r63": ".1"}, selected)[0], "P1_CAN_FILL_ARCHIVED_CASH_SLOT")

    def test_missing_momentum_not_treated_as_zero(self):
        self.assertEqual(priority({"r63": ""}, [])[0], "P1_UNKNOWN_MOMENTUM")

    def test_count_replacements_by_combined_ranking_not_number_of_competitors(self):
        selected = [{"ticker": t, "r63": str(v)} for t, v in zip("ABCDE", [.9, .8, .7, .6, .5])]
        cases = [{"ticker": f"X{n}", "archived_r63": .55} for n in range(50)]
        result = impact_bound(selected, cases, False)
        self.assertEqual(result["archived_selected_replacements_upper"], 1)
        self.assertFalse(result["is_certified_or_realized_impact"])

    def test_unknown_momenta_cannot_displace_more_than_five_slots(self):
        selected = [{"ticker": t, "r63": str(v)} for t, v in zip("ABCDE", [.9, .8, .7, .6, .5])]
        cases = [{"ticker": f"X{n}", "archived_r63": None} for n in range(50)]
        self.assertEqual(impact_bound(selected, cases, True)["changed_target_slots_upper"], 5)

    def test_tie_uses_frozen_sorted_ticker_stable_order(self):
        selected = [{"ticker": t, "r63": ".5"} for t in "BCDEF"]
        result = impact_bound(selected, [{"ticker": "A", "archived_r63": .5}], False)
        self.assertEqual(result["hypothetical_top5"], list("ABCDE"))


class ReviewWorkflowTests(unittest.TestCase):
    def test_candidate_cannot_jump_from_evidence_required_to_certified(self):
        with self.assertRaises(ValueError):
            validate_transition("EVIDENCE_REQUIRED", "CERTIFIED_INELIGIBLE")

    def test_terminal_evidence_can_be_revoked_without_erasing_history(self):
        validate_transition("CERTIFIED_INELIGIBLE", "QUARANTINED")
        validate_transition("CERTIFIED_ELIGIBLE_DISPLACING", "EVIDENCE_REQUIRED")
        with self.assertRaises(ValueError):
            validate_transition("CERTIFIED_INELIGIBLE", "CERTIFIED_ELIGIBLE_DISPLACING")

    def test_two_independent_reviewers_are_mandatory(self):
        decision = reviewed_decision()
        validate_certification_decision(decision)
        decision["second_reviewer_id"] = decision["reviewer_id"]
        with self.assertRaises(ValueError):
            validate_certification_decision(decision)

    def test_every_review_check_and_second_reproduction_required(self):
        for mutation in ("missing_check", "second_failed", "different_result", "wrong_state"):
            decision = reviewed_decision()
            if mutation == "missing_check":
                del decision["checks"][CHECKS[0]]
            elif mutation == "second_failed":
                decision["checks"][CHECKS[0]]["second_passed"] = False
            elif mutation == "different_result":
                decision["second_recomputed_result"]["selected"] = False
            else:
                decision["state"] = "CERTIFIED_INELIGIBLE"
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_certification_decision(decision)


class FrozenArchiveIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = build()

    def test_exact_943_cases_all_remain_open_and_return_impact_is_unknown(self):
        summary = self.result["summary"]
        self.assertEqual(summary["cases"], 943)
        self.assertEqual(len({r["case_id"] for r in self.result["cases"]}), 943)
        self.assertEqual(summary["new_strictly_certified_cases"], 0)
        self.assertTrue(all(r["state"] == "EVIDENCE_REQUIRED" for r in self.result["cases"]))
        self.assertIsNone(summary["return_impact"])

    def test_frozen_input_drift_stops_before_analysis(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.lock.json"
            path.write_text(json.dumps({"frozen_commit": FROZEN_COMMIT, "input_sha256": {}}))
            with self.assertRaises(ValueError):
                build(lock_path=path)

    def test_deterministic_rebuild_matches_published_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            write_artifacts(build(), path)
            for file in path.iterdir():
                self.assertEqual(file.read_bytes(), (HERE / "artifacts" / file.name).read_bytes(), file.name)

    def test_hash_chain_detects_payload_or_order_corruption(self):
        events = self.result["audit_events"]
        verify_audit_events(events)
        changed = copy.deepcopy(events)
        changed[0]["to_state"] = "CERTIFIED_INELIGIBLE"
        with self.assertRaises(ValueError):
            verify_audit_events(changed)


class NewPrimaryEvidenceTests(unittest.TestCase):
    def test_new_retained_headers_and_awk_facts_reproduce_without_case_closure(self):
        result = build_primary_review()
        self.assertEqual(result["original_headers_acquired"], 3)
        self.assertEqual(result["acceptance_normalization_discrepancies"], 2)
        self.assertTrue(result["timezone_policy_is_inference"])
        self.assertFalse(result["header_proves_public_availability"])
        self.assertEqual(result["new_full_case_certifications"], 0)
        awk = result["awk_original_accession"]
        self.assertEqual(len(awk["revenue_value_reconciliations"]), 4)
        self.assertTrue(all(r["exact_value_match"] for r in awk["revenue_value_reconciliations"]))
        self.assertTrue(awk["observed_frozen_gate_diagnostic"]["all_three_observed_gates_fail"])
        self.assertEqual(result, json.loads((HERE / "artifacts/primary_review.json").read_text()))

    def test_conflicting_header_fields_fail_closed(self):
        raw = b"<ACCEPTANCE-DATETIME>20241024161313\n<ACCEPTANCE-DATETIME>20241024161314"
        with self.assertRaises(ValueError):
            parse_header(raw)

    def test_fractional_value_disagreement_is_not_truncated_away(self):
        self.assertFalse(exact_number_match("1323000000.75", 1323000000))
        self.assertTrue(exact_number_match("1323000000.0", 1323000000))

    def test_conflicting_consolidated_values_fail_closed(self):
        raw = b'''<x:xbrl xmlns:x="http://www.xbrl.org/2003/instance" xmlns:g="http://fasb.org/us-gaap/2024">
        <x:context id="c"><x:entity><x:identifier scheme="http://www.sec.gov/CIK">0001410636</x:identifier></x:entity>
        <x:period><x:startDate>2024-07-01</x:startDate><x:endDate>2024-09-30</x:endDate></x:period></x:context>
        <x:unit id="usd"><x:measure>iso4217:USD</x:measure></x:unit>
        <g:RegulatedAndUnregulatedOperatingRevenue contextRef="c" unitRef="usd">1323000000</g:RegulatedAndUnregulatedOperatingRevenue>
        <g:RegulatedAndUnregulatedOperatingRevenue contextRef="c" unitRef="usd">1323000001</g:RegulatedAndUnregulatedOperatingRevenue></x:xbrl>'''
        with self.assertRaises(ValueError):
            consolidated_quarter_facts(raw, "0001410636")

    def test_conflicting_namespace_or_currency_prefix_cannot_bypass_check(self):
        raw = b'''<x:xbrl xmlns:x="http://www.xbrl.org/2003/instance" xmlns:g="http://fasb.org/us-gaap/2024" xmlns:h="http://fasb.org/us-gaap/2023">
        <x:context id="c"><x:entity><x:identifier scheme="http://www.sec.gov/CIK">0001410636</x:identifier></x:entity>
        <x:period><x:startDate>2024-07-01</x:startDate><x:endDate>2024-09-30</x:endDate></x:period></x:context>
        <x:unit id="usd"><x:measure>iso4217:USD</x:measure></x:unit><x:unit id="other"><x:measure>currency:USD</x:measure></x:unit>
        <g:RegulatedAndUnregulatedOperatingRevenue contextRef="c" unitRef="usd">1323000000</g:RegulatedAndUnregulatedOperatingRevenue>
        <h:RegulatedAndUnregulatedOperatingRevenue contextRef="c" unitRef="other">1323000001</h:RegulatedAndUnregulatedOperatingRevenue></x:xbrl>'''
        with self.assertRaises(ValueError):
            consolidated_quarter_facts(raw, "0001410636")

    def test_frozen_earnings_gate_retains_loss_to_profit_rule_and_positive_current(self):
        self.assertTrue(frozen_earnings_pass(1, 0))
        self.assertTrue(frozen_earnings_pass(1, -1))
        self.assertFalse(frozen_earnings_pass(0, -1))
        self.assertFalse(frozen_earnings_pass(-1, -2))
        self.assertFalse(frozen_earnings_pass(120, 100))
        self.assertTrue(frozen_earnings_pass(121, 100))

    def test_instance_plan_uses_exact_documents_named_in_acquired_headers(self):
        plan = acquisition_plan(HERE / "primary_acquisition_system")
        self.assertEqual(len(plan), 3)
        self.assertTrue(all(r["url"].endswith("_htm.xml") for r in plan))
        self.assertEqual([r["ticker"] for r in plan], ["NEM", "LLY", "AWK"])


if __name__ == "__main__":
    unittest.main()
