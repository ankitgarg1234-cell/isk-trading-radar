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
    return {
        "provider": "SEC_ZIP_" + kind.upper(),
        "source_sha256": digest,
        "metadata": {
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
