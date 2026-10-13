"""Pure GEMv1 source-pipeline regression tests; no paid API or broker I/O."""
import base64
from datetime import datetime, timezone
from hashlib import sha256
import zlib

import pytest

from gem_data.wiki_membership import parse_wikipedia_membership, compare_secondary_membership
from gem_data.nyse_session_audit import sessions_2026, completed_session_audit, month_end_from_sessions, NyseAuditHold
from gem_data.spy_total_return import reconstruct_spy, SpyAuditHold
from gem_data.sec_exception_triage import quarter_from_ytd, triage, SECRemediationHold
from gem_data.sec_corporate_event_discovery import discover_sec_event_candidates
from gem_data.gem_marketstack_backfill import _unpack_membership, collect_batch, MarketstackBackfillHold


def wiki_fixture(n=500):
    head="<table id='constituents'><tr><th>Symbol</th><th>Security</th><th>GICS Sector</th><th>Date added</th><th>CIK</th></tr>"
    rows="".join(f"<tr><td>A{i:03d}</td><td>Company {i}</td><td>Industrials</td><td>2020-01-01</td><td>{i+1}</td></tr>" for i in range(n))
    return (head + rows + "</table>").encode()


def test_wikipedia_membership_cik_join_and_drift():
    source = wiki_fixture()
    members = parse_wikipedia_membership(source)
    assert members["securities"] == 500
    assert members["members"][0]["cik"] == "0000000001"
    csv = ("Symbol,CIK\n" + "".join(f"A{i:03d},{i+1}\n" for i in range(500))).encode()
    assert compare_secondary_membership(members,csv)["identity_match"] is True
    wrong = csv.replace(b"A000,1",b"A000,999")
    result = compare_secondary_membership(members,wrong)
    assert result["cik_mismatches"] == ["A000"]
    assert members["certified"] is False


def test_wikipedia_rejects_truncated_current_universe():
    with pytest.raises(ValueError):
        parse_wikipedia_membership(wiki_fixture(10))


def test_nyse_official_month_end_and_early_close():
    days = sessions_2026("2026-11-23","2026-12-02",official_receipt_sha256="a"*64)
    names = [x["session"] for x in days]
    assert "2026-11-26" not in names
    early = next(x for x in days if x["session"]=="2026-11-27")
    assert early["scheduled_close_et"] == "13:00"
    plan = month_end_from_sessions(days)
    assert plan[0]["signal_session"] == "2026-11-30"
    assert plan[0]["next_session"] == "2026-12-01"
    assert plan[0]["status"] == "SCHEDULED_NOT_CONFIRMED"


def test_nyse_requires_two_post_close_source_receipts():
    row={"session":"2026-10-13","scheduled_close_et":"16:00"}
    now=datetime(2026,10,13,22,0,tzinfo=timezone.utc)
    a={"provider":"MARKETSTACK","session":"2026-10-13",
       "retrieved_at":"2026-10-13T21:30:00Z","close_price":400,
       "source_sha256":"a"*64,"calendar_aligned":True}
    b={**a,"provider":"IBKR","source_sha256":"b"*64}
    assert completed_session_audit(row,[a],checked_at=now)["status"] == "EOD_EVIDENCE_PENDING"
    assert completed_session_audit(row,[a,b],checked_at=now)["verified_calendar_day"] is True


def test_spy_dividend_accrues_before_payable():
    bars=[
        {"session":"2026-03-19","open":100,"close":100},
        {"session":"2026-03-20","open":98,"close":98},
        {"session":"2026-03-23","open":99,"close":99},
    ]
    dist=[{"ex_date":"2026-03-20","payable_date":"2026-03-23",
           "cash_per_share":"2","issuer_receipt_sha256":"a"*64}]
    out=reconstruct_spy(bars,dist)
    assert out["daily"][1]["receivable_usd"] > 0
    assert out["daily"][2]["receivable_usd"] == 0
    assert out["daily"][2]["cash_dividend_paid_usd"] > 0
    assert out["status"] == "RECONSTRUCTED_NOT_SOURCE_CERTIFIED"
    with pytest.raises(SpyAuditHold):
        reconstruct_spy(bars,[{**dist[0],"issuer_receipt_sha256":"bad"}])


def test_sec_ytd_derivation_remains_uncertified():
    base={"start":"2026-01-01","unit":"USD","concept":"NetIncomeLoss","form":"10-Q"}
    prev={**base,"end":"2026-03-31","filed":"2026-05-01",
          "accession":"0000000001-26-000011","value":200}
    curr={**base,"end":"2026-06-30","filed":"2026-08-01",
          "accession":"0000000001-26-000022","value":550}
    out=quarter_from_ytd(current_ytd=curr,prior_ytd=prev,signal_day="2026-09-30")
    assert out["value_usd"] == "350"
    assert out["certified"] is False
    assert triage(["current_missing_operating_income"])[0]["action"].startswith("INSPECT_ISSUER")
    with pytest.raises(SECRemediationHold):
        quarter_from_ytd(current_ytd=curr,prior_ytd=prev,signal_day="2026-08-01")


def test_primary_sec_8k_candidates_not_auto_booked():
    data={"cik":1800,"filings":{"recent":{
        "form":["8-K","10-Q"],"accessionNumber":["0000001800-26-000020","0000001800-26-000021"],
        "filingDate":["2026-10-09","2026-10-10"],
        "primaryDocument":["abc.htm","abc.htm"],
        "items":["2.01,8.01",""],
    }}}
    out=discover_sec_event_candidates(data,cutoff="2026-10-13")
    assert out["count"] == 1
    assert out["event_candidates"][0]["economic_terms_verified"] is False
    assert out["portfolio_events_applied"] == 0


def test_marketstack_requires_opt_in_key_and_explicit_quota(monkeypatch):
    monkeypatch.delenv("GEM_MARKETSTACK_BACKFILL_ENABLED",raising=False)
    monkeypatch.delenv("MARKETSTACK_API_KEY",raising=False)
    with pytest.raises(MarketstackBackfillHold):
        collect_batch()


def test_marketstack_membership_source_sha_is_checked():
    data=("Symbol,CIK\n"+"".join(f"A{i:03d},{i+1}\n" for i in range(500))).encode()
    meta={"source_raw_zlib_base64":base64.b64encode(zlib.compress(data)).decode()}
    assert len(_unpack_membership(meta,sha256(data).hexdigest()))==500
    with pytest.raises(MarketstackBackfillHold):
        _unpack_membership(meta,"0"*64)
