"""Metadata completeness must not certify current or ambiguous evidence."""
import unittest

from research.spgm_strategy_audit import dated_verified, metrics

CUTOFF = "2024-04-30T23:59:59+00:00"


class MetadataAuditTests(unittest.TestCase):
    def evidence(self, prefix="sector"):
        return {prefix + "_verification": "historically_verified",
                prefix + "_source_url": "https://example.test/historical-record",
                prefix + "_available_at": "2024-03-01T10:00:00+00:00",
                prefix + "_effective_from": "2024-03-01T00:00:00+00:00"}

    def test_current_inferred_and_undated_never_pass(self):
        for status in ("current", "inferred", "", "historically_verified"):
            row = self.evidence()
            row["sector_verification"] = status
            if status == "historically_verified":
                row.pop("sector_available_at")
            self.assertFalse(dated_verified(row, "sector", CUTOFF))

    def test_effective_and_public_dates_are_independent(self):
        row = self.evidence()
        self.assertTrue(dated_verified(row, "sector", CUTOFF))
        row["sector_available_at"] = CUTOFF
        self.assertFalse(dated_verified(row, "sector", CUTOFF))
        row["sector_available_at"] = "2024-03-01T10:00:00+00:00"
        row["sector_effective_from"] = "2024-05-01T00:00:00+00:00"
        self.assertFalse(dated_verified(row, "sector", CUTOFF))

    def test_expired_and_naive_timestamps_rejected(self):
        row = self.evidence()
        row["sector_effective_to"] = CUTOFF
        self.assertFalse(dated_verified(row, "sector", CUTOFF))
        row.pop("sector_effective_to")
        row["sector_available_at"] = "2024-03-01T10:00:00"
        self.assertFalse(dated_verified(row, "sector", CUTOFF))

    def test_sector_name_alone_does_not_prove_gics(self):
        row = dict(sector="Information Technology", **self.evidence())
        self.assertEqual(metrics([row], CUTOFF)["historical_gics_verified"], 0)
        row["sector_scheme"] = "GICS"
        self.assertEqual(metrics([row], CUTOFF)["historical_gics_verified"], 1)

    def test_ticker_and_mic_alone_are_not_verified_listing(self):
        row = {"pit_ticker": "NVDA", "exchange_mic": "XNAS", "currency": "USD", "isin": "US67066G1040"}
        self.assertEqual(metrics([row], CUTOFF)["verified_listing"], 0)
        row.update(self.evidence("listing"))
        self.assertEqual(metrics([row], CUTOFF)["verified_listing"], 1)

    def test_valid_id_does_not_erase_invalid_alternate(self):
        row = {"isin": "US67066G1040", "identifier_problems": "invalid alternate CUSIP"}
        result = metrics([row], CUTOFF)
        self.assertEqual(result["valid_typed_identifier"], 1)
        self.assertEqual(result["identifier_problem_rows"], 1)

    def test_same_id_conflicting_verified_issuers_flagged(self):
        rows = [{"isin": "US67066G1040", "company_lei": lei}
                for lei in ("12345678901234567888", "22345678901234567871")]
        self.assertEqual(metrics(rows, CUTOFF)["identifier_issuer_conflict_rows"], 2)


if __name__ == "__main__":
    unittest.main()
