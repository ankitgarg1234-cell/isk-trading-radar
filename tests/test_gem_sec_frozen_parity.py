"""Synthetic original-SEC tests for the offline B/C parity diagnostic.

All receipts are constructed in-memory. No live data or external calls;
MATCHED_DIAGNOSTIC_NOT_CERTIFIED is never an authorization.
"""
import base64
from datetime import date
from hashlib import sha256
import json
import zlib

from gem_data.gem_sec_frozen_parity import diagnose_receipts
from gem_data.sec_independent_fact_verify import OFFICIAL_ARCHIVES


CIK = "0001000000"
END = "2026-09-30"
TAGS = {"TotalRevenue": "RevenueFromContractWithCustomerExcludingAssessedTax",
        "NetIncome": "NetIncomeLoss", "OperatingIncome": "OperatingIncomeLoss"}


def accession(year, suffix=1):
    return f"{CIK}-{str(year)[-2:]}-{suffix:06d}"


def fact(accn, year, concept, value, *, fp="Q2", cumulative=False, form="10-Q"):
    period_start = f"{year}-01-01" if cumulative else f"{year}-04-01"
    period_end = f"{year}-06-30"
    if fp == "Q1":
        period_start, period_end = f"{year}-01-01", f"{year}-03-31"
    return {
        "accn": accn, "form": form, "filed": f"{year}-08-01" if fp == "Q2" else f"{year}-05-01",
        "start": period_start, "end": period_end,
        "fp": fp, "val": value,
    }


def originals(*, amended=False, cumulative=False, omit_q1=False):
    forms, accs, filed, accepted, companyfacts = [], [], [], [], {}
    for year in (2025, 2026):
        entries = [(accession(year), "10-Q", "Q2", {
            "TotalRevenue": 205 if year == 2025 else 240,
            "NetIncome": 22 if year == 2025 else 40,
            "OperatingIncome": 40 if year == 2025 else 60,
        } if cumulative else {
            "TotalRevenue": 100 if year == 2025 else 111 if amended else 125,
            "NetIncome": 12 if year == 2025 else 29 if amended else 30,
            "OperatingIncome": 28 if year == 2025 else 39 if amended else 40,
        })]
        if cumulative and not omit_q1:
            entries.insert(0, (accession(year, 2), "10-Q", "Q1", {
                "TotalRevenue": 105 if year == 2025 else 115,
                "NetIncome": 10,
                "OperatingIncome": 12 if year == 2025 else 20,
            }))
        if amended and year == 2026:
            entries.append((accession(year, 3), "10-Q/A", "Q2", {
                "TotalRevenue": 125, "NetIncome": 30, "OperatingIncome": 40,
            }))
        for acc, form, fp, metrics in entries:
            dt = (f"{year}-05-01" if fp == "Q1" else
                  f"{year}-08-20" if form == "10-Q/A" else f"{year}-08-01")
            forms.append(form); accs.append(acc); filed.append(dt)
            accepted.append(dt+"T14:00:00")
            for concept, value in metrics.items():
                ff = fact(acc, year, concept, value, fp=fp,
                          cumulative=cumulative and fp == "Q2",form=form)
                ff["filed"] = dt
                tag = TAGS[concept]
                companyfacts.setdefault(tag, {"units": {"USD": []}})["units"]["USD"].append(ff)
    submissions = {"cik": int(CIK), "filings": {"recent": {
        "form": forms, "accessionNumber": accs,
        "filingDate": filed, "acceptanceDateTime": accepted,
    }}}
    facts = {"cik": int(CIK), "facts": {"us-gaap": companyfacts}}
    return submissions, facts


def receipt(kind, content):
    raw = json.dumps(content, sort_keys=True).encode()
    hash_ = sha256(raw).hexdigest()
    return {
        "provider": "SEC_ZIP_" + kind.upper(),
        "source_uri": OFFICIAL_ARCHIVES[kind] + "#CIK" + CIK + ".json",
        "source_sha256": hash_,
        "metadata": {
            "zip_member_name": "CIK" + CIK + ".json",
            "archive_url": OFFICIAL_ARCHIVES[kind],
            "source_raw_zlib_base64": base64.b64encode(zlib.compress(raw)).decode(),
            "member_original_sha256": hash_,
            "member_uncompressed_bytes": len(raw),
        },
    }


def run(*, amended=False, cumulative=False, omit_q1=False):
    submissions, facts = originals(amended=amended,cumulative=cumulative,omit_q1=omit_q1)
    return diagnose_receipts(receipt("submissions", submissions),
                             receipt("companyfacts", facts), CIK, END)


def test_direct_original_quarterly_facts_reproduce_frozen_growth_gates():
    result = run()
    assert result["status"] == "MATCHED_DIAGNOSTIC_NOT_CERTIFIED"
    assert not result["certified"]
    assert not result["manual_trading_authorized"]
    assert result["calculated"]["revenue_yoy"] == .25
    assert result["calculated"]["earnings_improvement"]
    assert abs(result["calculated"]["margin_delta_pp"] - 4) < 1e-8


def test_latest_eligible_amendment_is_used_not_original_older_10q():
    result = run(amended=True)
    assert result["status"] == "MATCHED_DIAGNOSTIC_NOT_CERTIFIED"
    assert result["comparisons"]["TotalRevenue"]["latest_accession"] == accession(2026,3)
    assert result["comparisons"]["TotalRevenue"]["latest_value"] == 125


def test_derived_q2_is_verified_from_two_original_ytd_values():
    result = run(cumulative=True)
    assert result["status"] == "MATCHED_DIAGNOSTIC_NOT_CERTIFIED"
    assert result["comparisons"]["TotalRevenue"]["latest_value"] == 125
    assert result["comparisons"]["TotalRevenue"]["latest_derivation"] == (
        "OBSERVED_SEC_YTD_DIFFERENCE_NOT_CERTIFIED")
    assert abs(result["calculated"]["margin_delta_pp"] - 4) < 1e-8


def test_missing_ytd_operand_stays_on_hold_instead_of_using_older_quarter():
    result = run(cumulative=True, omit_q1=True)
    assert result["status"] == "HOLD"
    assert "operand" in result["blockers"][0]



def test_same_accession_direct_quarter_overrides_unprovable_ytd_presentation():
    submissions, facts = originals(cumulative=True, omit_q1=True)
    direct = {
        "TotalRevenue": (100,125),
        "NetIncome": (12,30),
        "OperatingIncome": (28,40),
    }
    for concept, tag in TAGS.items():
        usd = facts["facts"]["us-gaap"][tag]["units"]["USD"]
        assert len(usd)==2
        for old, value in zip(list(usd), direct[concept]):
            obs = dict(old, start=old["start"][:4]+"-04-01", val=value)
            usd.append(obs)
    result = diagnose_receipts(receipt("submissions",submissions),
                              receipt("companyfacts",facts),CIK,END)
    assert result["status"]=="MATCHED_DIAGNOSTIC_NOT_CERTIFIED"
    assert result["comparisons"]["TotalRevenue"]["latest_value"]==125
    assert result["comparisons"]["TotalRevenue"]["latest_derivation"]=="DIRECT_10Q"


def test_tampered_original_sec_evidence_is_held():
    submissions, facts = originals()
    a, b = receipt("submissions", submissions), receipt("companyfacts", facts)
    b["source_sha256"] = "0"*64
    result = diagnose_receipts(a, b, CIK, END)
    assert result["status"] == "HOLD"
    assert "SHA256" in result["blockers"][0]
    assert not result["certified"]


def test_filing_after_cutoff_does_not_leak_into_original_selected_quarter():
    submissions, facts = originals(amended=True)
    # Release the amendment only in October, after the September signal.
    submissions["filings"]["recent"]["filingDate"][-1] = "2026-10-01"
    submissions["filings"]["recent"]["acceptanceDateTime"][-1] = "2026-10-01T14:00:00"
    for x in facts["facts"]["us-gaap"].values():
        x["units"]["USD"][-1]["filed"] = "2026-10-01"
    result = diagnose_receipts(receipt("submissions", submissions),
                              receipt("companyfacts", facts), CIK, END)
    assert result["status"] == "MATCHED_DIAGNOSTIC_NOT_CERTIFIED"
    assert result["comparisons"]["TotalRevenue"]["latest_value"] == 111
