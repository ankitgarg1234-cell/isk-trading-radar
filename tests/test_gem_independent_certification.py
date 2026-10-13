"""Unit tests for independent SEC receipt verification (no external services)."""
import base64
import hashlib
import json
import unittest
import zlib

from gem_data.gem_independent_certification import verify_receipt


def sample(cik="0000320193"):
    raw = json.dumps({"cik": int(cik), "facts": {}}).encode()
    digest = hashlib.sha256(raw).hexdigest()
    return {
        "receipt_id": "test-receipt",
        "provider": "SEC_ZIP_COMPANYFACTS",
        "source_sha256": digest,
        "metadata": {
            "zip_member_name": f"CIK{cik}.json",
            "source_raw_zlib_base64": base64.b64encode(zlib.compress(raw)).decode(),
            "member_original_sha256": digest,
            "member_uncompressed_bytes": len(raw),
        },
    }


class ReceiptVerifierTests(unittest.TestCase):
    def test_original_integrity_pass_not_financial_certification(self):
        self.assertEqual(verify_receipt(sample())["status"], "INTEGRITY_PASS")

    def test_hash_tampering_fails(self):
        r = sample()
        r["source_sha256"] = "0" * 64
        self.assertEqual(verify_receipt(r)["status"], "FAIL")

    def test_cik_mismatch_fails(self):
        r = sample()
        r["metadata"]["zip_member_name"] = "CIK0000789019.json"
        self.assertEqual(verify_receipt(r)["status"], "FAIL")

    def test_corrupt_base64_fails(self):
        r = sample()
        r["metadata"]["source_raw_zlib_base64"] = "invalid!"
        self.assertEqual(verify_receipt(r)["status"], "FAIL")

    def test_oversized_encoded_input_fails(self):
        r = sample()
        r["metadata"]["source_raw_zlib_base64"] = "A" * 18_000_001
        self.assertEqual(verify_receipt(r)["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
