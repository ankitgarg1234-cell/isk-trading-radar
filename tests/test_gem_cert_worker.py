"""Offline regression tests: fail-closed SEC audit and certification."""
import unittest
from unittest.mock import patch
from gem_data.gem_six_fact_gate import assess_six_fact_readiness
from gem_data.gem_cert_audit_worker import check_audit_permissions, process_pending


class GateTests(unittest.TestCase):
    def test_no_evidence_is_unknown(self):
        result = assess_six_fact_readiness([])
        self.assertEqual(result["fact_status"], "UNKNOWN")
        self.assertFalse(result["dashboard_publication_authorized"])

    def test_two_integrity_passes_do_not_certify_facts(self):
        audits = [{"provider": p, "integrity_status": "PASS"}
                  for p in ("SEC_ZIP_COMPANYFACTS", "SEC_ZIP_SUBMISSIONS")]
        result = assess_six_fact_readiness(audits, {"facts": list(range(6))})
        self.assertFalse(result["financial_facts_certified"])
        self.assertIn("SIX_FACT_EXTRACTION_AND_RECONCILIATION_NOT_IMPLEMENTED",
                      result["blockers"])

    def test_audit_worker_disabled_without_credential(self):
        with patch.dict("os.environ", {"GEM_CERT_AUDIT_DATABASE_URL": ""}):
            self.assertFalse(check_audit_permissions()["ready"])
            with self.assertRaises(RuntimeError):
                process_pending()

    def test_invalid_batch_rejected(self):
        with self.assertRaises(ValueError):
            process_pending(11)


if __name__ == "__main__":
    unittest.main()
