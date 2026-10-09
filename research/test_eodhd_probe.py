"""Network-free checks for the EODHD free-tier coverage probe."""
import json
import tempfile
import unittest
from pathlib import Path

from research.eodhd_probe import claim_call, read_symbols, validate_prices


def row(day):
    return {"date": day, "open": 10.0, "high": 11.0, "low": 9.0,
            "close": 10.5, "adjusted_close": 10.1, "volume": 1000}


class EodhdProbeTests(unittest.TestCase):
    def test_accepts_sorted_daily_prices(self):
        result = validate_prices([row("2026-10-01"), row("2026-10-02")])
        self.assertEqual([x["date"] for x in result], ["2026-10-01", "2026-10-02"])

    def test_duplicate_date_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            validate_prices([row("2026-10-01"), row("2026-10-01")])

    def test_out_of_order_prices_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "ascending"):
            validate_prices([row("2026-10-02"), row("2026-10-01")])

    def test_quota_claims_count_failures_and_reset_daily(self):
        with tempfile.TemporaryDirectory() as temp:
            ledger = Path(temp) / "ledger.json"
            claim_call(ledger, "2026-10-09", 2)
            claim_call(ledger, "2026-10-09", 2)
            with self.assertRaisesRegex(RuntimeError, "cap reached"):
                claim_call(ledger, "2026-10-09", 2)
            self.assertEqual(json.loads(ledger.read_text())["used"], 2)
            claim_call(ledger, "2026-10-10", 2)
            self.assertEqual(json.loads(ledger.read_text())["used"], 1)

    def test_manifest_deduplicates(self):
        with tempfile.TemporaryDirectory() as temp:
            sample = Path(temp) / "sample.csv"
            sample.write_text("eodhd_ticker\\nNVDA.US\\nMU.US\\nNVDA.US\\n")
            self.assertEqual(read_symbols(sample), ["NVDA.US", "MU.US"])


if __name__ == "__main__":
    unittest.main()
