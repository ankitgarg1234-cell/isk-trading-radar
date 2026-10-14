"""Offline deterministic SEC original receipt and six-quarter-fact QA tests."""
from __future__ import annotations

import base64
from copy import deepcopy
from datetime import date
from hashlib import sha256
import json
import zlib

from gem_data.sec_independent_fact_verify import (
    decode_original_receipt, verify_receipt_pair, verify_six_candidates,
    VerificationHold,
)

CIK = "0001000000"
CUR = "0001000000-26-000001"
PREV = "0001000000-25-000001"


def originals():
    submissions = {
        "cik": int(CIK),
        "filings": {"recent": {
            "form": ["10-Q", "10-Q"],
            "accessionNumber": [CUR, PREV],
            "filingDate": ["2026-08-01", "2025-08-01"],
            "acceptanceDateTime": ["2026-08-01T15:00:00", "2025-08-01T15:00:00"],
        }},
    }
    periods = [
        {"accn": CUR, "form": "10-Q", "filed": "2026-08-01",
         "start": "2026-04-01", "end": "2026-06-30", "fp": "Q2"},
        {"accn": PREV, "form": "10-Q", "filed": "2025-08-01",
         "start": "2025-04-01", "end": "2025-06-30", "fp": "Q2"},
    ]
    facts = {"cik": int(CIK), "facts": {"us-gaap": {
        "RevenueFromContractWithCustomerExcludingAssessedTax": {
            "units": {"USD": [dict(p, val=v) for p, v in zip(periods, (200, 100))]}},
        "OperatingIncomeLoss": {
            "units": {"USD": [dict(p, val=v) for p, v in zip(periods, (50, 20))]}},
        "NetIncomeLoss": {
            "units": {"USD": [dict(p, val=v) for p, v in zip(periods, (30, 10))]}},
    }}}
    return submissions, facts


def receipt(kind, data):
    raw = json.dumps(data, sort_keys=True).encode()
    digest = sha256(raw).hexdigest()
    from gem_data.sec_independent_fact_verify import OFFICIAL_ARCHIVES
    url = OFFICIAL_ARCHIVES[kind]
    return {
        "provider": "SEC_ZIP_" + kind.upper(),
        "source_uri": url + "#" + f"CIK{CIK}.json",
        "source_sha256": digest,
        "metadata": {
            "archive_url": url,
            "zip_member_name": f"CIK{CIK}.json",
            "source_raw_zlib_base64": base64.b64encode(zlib.compress(raw)).decode(),
            "member_original_sha256": digest,
            "member_uncompressed_bytes": len(raw),
        },
    }


def test_complete_six_candidate_facts_are_not_certified():
    subs, facts = originals()
    result = verify_receipt_pair(receipt("submissions", subs),
                                 receipt("companyfacts", facts), CIK)
    assert result["receipt_integrity"] == "PASS"
    assert result["fact_status"] == "CANDIDATE_COMPLETE_NOT_CERTIFIED"
    assert result["certified"] is False
    assert result["original_accession_inline_xbrl_certified"] is False
    assert len(result["six_facts"]) == 6
    assert result["six_facts"]["current_revenue"]["value_usd"] == 200
    assert result["six_facts"]["prior_net_income"]["value_usd"] == 10
    assert len(result["evidence_sha256"]) == 64


def test_year_to_date_values_do_not_replace_quarterly():
    subs, facts = originals()
    for metric in ("RevenueFromContractWithCustomerExcludingAssessedTax",
                   "OperatingIncomeLoss", "NetIncomeLoss"):
        usd = facts["facts"]["us-gaap"][metric]["units"]["USD"]
        usd[0]["start"] = "2026-01-01"  # ~180-day YTD
    result = verify_six_candidates(subs, facts)
    assert result["fact_status"] == "UNKNOWN"
    assert not any(k.startswith("current_") for k in result["six_facts"])


def test_competing_revenue_concepts_block_complete():
    subs, facts = originals()
    original = facts["facts"]["us-gaap"]["RevenueFromContractWithCustomerExcludingAssessedTax"]
    different = deepcopy(original)
    different["units"]["USD"][0]["val"] = 999
    facts["facts"]["us-gaap"]["Revenues"] = different
    result = verify_six_candidates(subs, facts)
    assert "current_ambiguous_revenue_tags" in result["blockers"]
    assert result["fact_status"] == "UNKNOWN"


def test_future_filed_fact_cannot_leak_into_frozen_gate():
    subs, facts = originals()
    subs["filings"]["recent"]["filingDate"][0] = "2026-11-01"
    subs["filings"]["recent"]["acceptanceDateTime"][0] = "2026-11-01T10:00:00"
    for tag in ("RevenueFromContractWithCustomerExcludingAssessedTax",
                "OperatingIncomeLoss", "NetIncomeLoss"):
        facts["facts"]["us-gaap"][tag]["units"]["USD"][0]["filed"] = "2026-11-01"
    result = verify_six_candidates(subs, facts, as_of=date(2026, 10, 12))
    assert result["fact_status"] == "UNKNOWN"


def test_tampered_original_receipt_fails_sha():
    subs, facts = originals()
    a = receipt("submissions", subs)
    b = receipt("companyfacts", facts)
    b["source_sha256"] = "0"*64
    result = verify_receipt_pair(a, b, CIK)
    assert result["receipt_integrity"] == "FAIL"
    assert "SHA256" in result["blockers"][0]


def test_wrong_cik_and_missing_parent_income_fail_closed():
    subs, facts = originals()
    b = receipt("companyfacts", facts)
    try:
        decode_original_receipt(b, "0001000001", "companyfacts")
        assert False, "wrong CIK accepted"
    except VerificationHold:
        pass
    facts["facts"]["us-gaap"].pop("NetIncomeLoss")
    facts["facts"]["us-gaap"]["ProfitLoss"] = {
        "units": {"USD": [{"accn": CUR, "form": "10-Q", "filed": "2026-08-01",
                          "start": "2026-04-01", "end": "2026-06-30",
                          "fp": "Q2", "val": 45}]}}
    result = verify_six_candidates(subs, facts)
    assert result["fact_status"] == "UNKNOWN"
    assert "current_missing_net_income" in result["blockers"]



def test_machine_qa_worker_is_append_only_idempotent_and_never_certifies(monkeypatch):
    from gem_data.sec_fact_audit_worker import audit_batch
    subs, facts = originals()
    sub = receipt("submissions", subs)
    fact = receipt("companyfacts", facts)
    raw = {
        "sub-id": ("SEC_ZIP_SUBMISSIONS", sub),
        "fact-id": ("SEC_ZIP_COMPANYFACTS", fact),
    }
    saved = set()
    captured = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def execute(self, query, args=None):
            if "SELECT DISTINCT ON" in query:
                self.rows = [(provider, rid, rec["source_sha256"],
                              f"CIK{CIK}.json")
                             for rid, (provider, rec) in raw.items()]
            elif "SELECT probe_id" in query:
                self.rows = [(p,) for p in saved]
            elif "SELECT receipt_id,provider" in query:
                self.rows = [(rid, raw[rid][0], raw[rid][1]["source_sha256"],
                              raw[rid][1]["source_uri"], raw[rid][1]["metadata"])
                             for rid in args[1]]
            elif "INSERT INTO gem_source_probe" in query:
                captured.append(args)
                saved.add(args[0])
        def fetchall(self): return getattr(self, "rows", [])
    class Conn:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def cursor(self): return Cursor()
        def commit(self): pass
    monkeypatch.setattr("gem_data.sec_fact_audit_worker.psycopg.connect",
                        lambda *args, **kwargs: Conn())
    monkeypatch.setenv("GEM_READONLY_DATABASE_URL",
                       "postgresql://gem_web_readonly:private@localhost/gem_forward")
    monkeypatch.setenv("GEM_INGEST_DATABASE_URL",
                       "postgresql://gem_source_ingest_limited:private@localhost/gem_forward")
    first = audit_batch(max_pairs=1)
    assert first["audited"] == 1
    assert first["integrity_pass"] == 1
    assert first["candidate_complete"] == 1
    assert len(captured) == 1
    assert captured[0][3] == "PARTIAL"
    details = json.loads(captured[0][7])
    assert details["fact_status"] == "CANDIDATE_COMPLETE_NOT_CERTIFIED"
    assert details["human_reviewer_approved"] is False
    assert details["certified"] is False
    second = audit_batch(max_pairs=1)
    assert second["audited"] == 0
    assert len(captured) == 1



def test_malformed_quarter_context_is_unknown_not_sha_failure():
    subs, facts = originals()
    facts["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["USD"][0].pop("start")
    result = verify_receipt_pair(receipt("submissions", subs),
                                 receipt("companyfacts", facts), CIK)
    assert result["receipt_integrity"] == "PASS"
    assert result["fact_status"] == "UNKNOWN"
    assert "financial_context_hold" in result["blockers"][0]



def test_source_uri_provenance_fails_closed():
    subs, facts = originals()
    a = receipt("submissions", subs)
    b = receipt("companyfacts", facts)
    b["source_uri"] = "https://example.com/forged.zip#CIK0001000000.json"
    result = verify_receipt_pair(a, b, CIK)
    assert result["receipt_integrity"] == "FAIL"
    assert "source URI" in result["blockers"][0]



def test_edgar_after_hours_acceptance_before_filing_date_is_valid():
    subs, facts = originals()
    subs["filings"]["recent"]["acceptanceDateTime"][0] = "2026-07-31T21:30:00"
    result = verify_receipt_pair(receipt("submissions", subs),
                                 receipt("companyfacts", facts), CIK)
    assert result["receipt_integrity"] == "PASS"
    assert result["fact_status"] == "CANDIDATE_COMPLETE_NOT_CERTIFIED"
    subs["filings"]["recent"]["acceptanceDateTime"][0] = "2026-07-20T21:30:00"
    bad = verify_receipt_pair(receipt("submissions", subs),
                              receipt("companyfacts", facts), CIK)
    assert bad["receipt_integrity"] == "PASS"
    assert bad["fact_status"] == "UNKNOWN"
    assert "too far before" in bad["blockers"][0]


def test_audit_keys_include_verifier_code_hash():
    from gem_data.sec_fact_audit_worker import _key, CODE_SHA256
    key = _key(CIK, {"submissions": ("sub-id", "a"*64),
                     "companyfacts": ("facts-id", "b"*64)})
    assert CODE_SHA256[:12] in key


def test_malformed_base64_receipt_fails_closed():
    subs, facts = originals()
    bad = receipt("submissions", subs)
    bad["metadata"]["source_raw_zlib_base64"] = "not-valid-base64!!"
    result = verify_receipt_pair(bad, receipt("companyfacts", facts), CIK)
    assert result["receipt_integrity"] == "FAIL"
    assert result["fact_status"] == "UNKNOWN"
    assert result["certified"] is False


def test_recent_quarter_filing_not_mislabeled_stale_when_tagged_facts_older():
    subs, facts = originals()
    subs["filings"]["recent"]["reportDate"]=["2026-06-30","2025-06-30"]
    subs["filings"]["recent"]["primaryDocument"]=["c-20260630.htm","c-20250630.htm"]
    for concept in facts["facts"]["us-gaap"].values():
        concept["units"]["USD"] = concept["units"]["USD"][1:]
    result=verify_six_candidates(subs,facts)
    assert result["fact_status"]=="UNKNOWN"
    assert result["blockers"]==["fresh_10q_exists_but_standard_facts_unrecognized"]
    assert result["latest_original_10q"]["accession"]==CUR
    assert result["latest_original_10q"]["report_period"]=="2026-06-30"
    assert result["certified"] is False


def test_actual_old_original_filing_stays_stale():
    subs, facts=originals()
    subs["filings"]["recent"]["reportDate"]=["2025-06-30","2024-06-30"]
    for concept in facts["facts"]["us-gaap"].values():
        concept["units"]["USD"]=concept["units"]["USD"][1:]
    result=verify_six_candidates(subs,facts)
    assert result["fact_status"]=="UNKNOWN"
    assert result["blockers"]==["current_quarter_older_than_210_days"]
