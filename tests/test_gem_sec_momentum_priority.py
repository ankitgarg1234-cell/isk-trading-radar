"""Proof that GEM SEC review triage does not change the frozen trade gates."""
import base64
from datetime import date, timedelta
from hashlib import sha256
import json
import zlib

import pytest

from gem_data.gem_sec_momentum_priority import (
    build_sec_priority_queue, preliminary_momentum, PriorityEvidenceHold,
)

SIGNAL = "2026-09-30"


def days():
    d = date.fromisoformat(SIGNAL)
    selected = []
    while len(selected) < 64:
        if d.weekday() < 5:
            selected.append(d.isoformat())
        d -= timedelta(days=1)
    return list(reversed(selected))


def receipt(ticker, *, first=100, last=120, rejected=()):
    sessions = days()
    bars = []
    for i, session in enumerate(sessions):
        price = first + (last-first)*i/63
        bars.append({"ticker": ticker, "session": session, "vendor_adj_close": price,
                     "close": price, "volume": 1_000_000})
    raw = json.dumps(bars, sort_keys=True, separators=(",", ":")).encode()
    digest = sha256(raw).hexdigest()
    return {"provider": "MARKETSTACK", "source_sha256": digest,
            "metadata": {
                "ticker": ticker, "normalized_bars_sha256": digest,
                "normalized_bars_zlib_base64":
                    base64.b64encode(zlib.compress(raw)).decode(),
                "completed_sessions": 64, "first_session": sessions[0],
                "last_session": sessions[-1],
                "rejected_sessions": list(rejected),
                "source_qa_status": "PENDING",
                "adjustment_parity_reviewed": False,
                "trading_approved": False}}


def test_positive_vendor_r63_enters_financial_priority_but_never_gets_certified():
    item = preliminary_momentum(receipt("POS"), "POS", SIGNAL, calendar_sessions=days())
    assert item["priority"] == "SEC_REVIEW_FIRST"
    assert abs(item["r63_preliminary"] - .20) < 1e-12
    assert item["final_strategy_exclusion"] is False
    assert item["sec_gate_certified"] is False


@pytest.mark.parametrize("first,last", [(100,100),(100,99)])
def test_zero_and_negative_r63_defer_docs_not_final_eligibility(first,last):
    item = preliminary_momentum(receipt("NEG",first=first,last=last), "NEG", SIGNAL)
    assert item["priority"] == "DEFER_SEC_PENDING_PRICE_QA"
    assert item["r63_preliminary"] <= 0
    assert item["final_strategy_exclusion"] is False
    assert item["adjusted_price_parity_certified"] is False


def test_missing_or_incomplete_prices_go_to_qa_not_false_negative():
    assert preliminary_momentum(None,"MISS",SIGNAL)["priority"] == "PRICE_REPAIR_FIRST"
    actual = preliminary_momentum(receipt("MISS",rejected=[days()[31]]),"MISS",SIGNAL)
    assert actual["priority"] == "PRICE_REPAIR_FIRST"
    assert actual["r63_preliminary"] is None


def test_hash_tamper_and_bad_calendar_cannot_generate_priority():
    bad = receipt("CORRUPT")
    bad["source_sha256"] = "0"*64
    assert preliminary_momentum(bad,"CORRUPT",SIGNAL)["priority"] == "PRICE_REPAIR_FIRST"
    good = receipt("CAL")
    assert preliminary_momentum(good,"CAL",SIGNAL,
        calendar_sessions=days()[1:])["priority"] == "PRICE_REPAIR_FIRST"


def test_universe_queue_has_no_silent_exclusions_or_trade_authorization():
    members = ["POS","NEG"] + [f"X{i:03d}" for i in range(478)]
    result = build_sec_priority_queue(
        members, {"POS":receipt("POS"),"NEG":receipt("NEG",last=80)}, SIGNAL)
    assert result["member_count"] == 480
    assert result["priority_counts"] == {
        "SEC_REVIEW_FIRST": 1, "PRICE_REPAIR_FIRST": 478,
        "DEFER_SEC_PENDING_PRICE_QA": 1}
    assert result["rows"][0]["ticker"] == "POS"
    assert result["rows"][-1]["ticker"] == "NEG"
    assert all(not row["final_strategy_exclusion"] for row in result["rows"])
    assert result["final_strategy_exclusions_verified"] == 0
    assert result["source_qa_certified"] is False
    assert result["ranking_certified"] is False
    assert result["trading_authorized"] is False
    assert result["broker_orders_sent"] == 0
    assert len(result["report_sha256"]) == 64


def test_duplicate_universe_or_extra_price_symbols_are_rejected():
    members = [f"X{i:03d}" for i in range(480)]
    with pytest.raises(PriorityEvidenceHold):
        build_sec_priority_queue(members[:-1]+[members[0]], {}, SIGNAL)
    with pytest.raises(PriorityEvidenceHold):
        build_sec_priority_queue(members, {"FORGED":receipt("FORGED")}, SIGNAL)
