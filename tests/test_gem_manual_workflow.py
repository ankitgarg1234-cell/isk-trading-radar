"""Deterministic end-to-end tests of manual GEM operations.

No market API, network, real broker or repository fixture required.
"""
from __future__ import annotations

import copy
import pytest

from gem_data.gem_manual_ops import (
    ManualLedgerHold, manual_trade_sheet, replay_manual_events,
)
from gem_data.market_data_patch import PricePatchHold, reconcile_prices
from gem_data.gem_monthly_signal import MonthlySignalHold, select_monthly, FROZEN


def test_manual_trades_never_route_to_broker():
    signal = {"selected": list("ABCDE"), "data_status": "REVIEWED_COMPLETE",
              "signal_session": "2026-09-30"}
    plan = manual_trade_sheet(signal, {"cash": "10000", "shares": {}},
                              {s: 100 for s in "ABCDE"})
    assert plan["status"] == "INDICATIVE_USER_REVIEW_REQUIRED"
    assert len(plan["tickets"]) == 5
    assert plan["broker_orders_sent"] == 0
    assert plan["actual_fills_required"] is True


def test_hold_uncertified_manual_trade_sheet():
    plan = manual_trade_sheet({"selected": list("ABCDE"), "data_status": "HOLD"},
                              {"cash": "10000", "shares": {}},
                              {s: 100 for s in "ABCDE"})
    assert plan["tickets"] == []
    assert plan["status"] == "DATA_HOLD"


def test_user_entered_fill_and_statement_reconciliation():
    buy = {"event_id": "fill-001", "type": "FILL", "trade_date": "2026-10-01",
           "ticker": "A", "side": "BUY", "shares": 10,
           "price": "100", "fees": "2", "source": "MANUAL_BROKER_ENTRY"}
    ledger = replay_manual_events("10000", [buy])
    assert ledger["cash"] == "8998"
    assert ledger["shares"] == {"A": 10}
    assert ledger["source_classification"] == "USER_ENTERED_NO_BROKER_API"
    assert ledger["statement_status"] == "NO_STATEMENT_ENTERED"
    statement = {"source": "MANUAL_BROKER_STATEMENT_EXPORT",
                 "statement_sha256": "a" * 64,
                 "as_of": "2026-10-02", "cash": "8998", "shares": {"A": 10}}
    assert replay_manual_events("10000", [buy], statement)["statement_status"] == "USER_STATEMENT_RECONCILED"
    statement["shares"] = {"A": 9}
    assert replay_manual_events("10000", [buy], statement)["statement_status"] == "STATEMENT_MISMATCH_HOLD"


def test_fills_validate_cash_and_duplicate_event_ids():
    buy = {"event_id": "a", "type": "FILL", "trade_date": "2026-10-01",
           "ticker": "A", "side": "BUY", "shares": 10,
           "price": "100", "fees": "2", "source": "MANUAL_BROKER_ENTRY"}
    with pytest.raises(ManualLedgerHold):
        replay_manual_events("100", [buy])
    with pytest.raises(ManualLedgerHold):
        replay_manual_events("10000", [buy, buy])


def test_split_and_spinoff_require_integer_shares():
    split = {"event_id": "s", "type": "SPLIT", "trade_date": "2026-10-02",
             "ticker": "A", "numerator": 3, "denominator": 2}
    buy = {"event_id": "b", "type": "FILL", "trade_date": "2026-10-01",
           "ticker": "A", "side": "BUY", "shares": 1, "price": "100",
           "fees": 0, "source": "MANUAL_BROKER_ENTRY"}
    with pytest.raises(ManualLedgerHold, match="fractional"):
        replay_manual_events("1000", [buy, split])
    buy["shares"] = 2
    result = replay_manual_events("1000", [buy, split])
    assert result["shares"]["A"] == 3


def bar(session):
    return {"ticker": "XYZ", "session": session,
            "open": 100, "high": 101, "low": 99, "close": 100,
            "volume": 1000000, "split_factor": 1, "dividend": 0}


def source(provider, sessions):
    return {"provider": provider, "receipt_sha256": "a" * 64,
            "basis": "NOMINAL_OHLCV", "bars": [bar(s) for s in sessions]}


def test_vendor_missing_day_can_be_crosschecked_not_silently_certified():
    days = ["2026-10-08", "2026-10-09"]
    report = reconcile_prices("XYZ", days, [
        source("FROZEN_VENDOR", days[:1]), source("INDEPENDENT_A", days),
        source("INDEPENDENT_B", days),
    ])
    assert report["missing_original"] == 1
    assert report["corroborated_patch_candidates"] == 1
    assert report["frozen_adjusted_price_parity"] is False
    assert report["manual_execution_authorized"] is False


def test_single_fallback_held_and_conflict_visible():
    days = ["2026-10-09"]
    report = reconcile_prices("XYZ", days, [source("INDEPENDENT_A", days)])
    assert report["unresolved_sessions"] == days
    bad = source("INDEPENDENT_B", days)
    bad["bars"][0]["close"] = 105
    bad["bars"][0]["high"] = 106
    report = reconcile_prices("XYZ", days, [source("INDEPENDENT_A", days), bad])
    assert report["corroborated_patch_candidates"] == 0
    assert report["conflicts"][0]["type"] == "FALLBACK_DISAGREEMENT"


def test_adjusted_vs_nominal_basis_cannot_be_interchanged():
    bad = source("INDEPENDENT_A", ["2026-10-09"])
    bad["basis"] = "TOTAL_RETURN_ADJUSTED"
    with pytest.raises(PricePatchHold):
        reconcile_prices("XYZ", ["2026-10-09"], [bad])


def signal_snapshot():
    rows = []
    for i, ticker in enumerate(("A", "B")):
        rows.append({
            "security_id": str(i), "ticker": ticker, "r63": -.1 if i == 0 else .2,
            "nominal_close": 100, "adv20": 100_000_000,
            "revenue_yoy": .5, "margin_delta_pp": 5,
            "net_income_now": 20, "net_income_prior": 10,
            "earnings_improvement": True,
            "price_last_session": "2026-09-30", "price_sessions": 127,
            "price_basis": "FROZEN_VERIFIED", "financial_source": "SEC_ORIGINAL_QA_REVIEWED",
            "latest_accepted_at": "2026-09-20T10:00:00Z",
            "security_identity_reviewed": True,
        })
    return {
        "schema": "gem-monthly-features-v1",
        "frozen_commit": FROZEN, "signal_session": "2026-09-30",
        "next_session": "2026-10-01", "calendar_verified": True,
        "universe": [{"security_id": str(i), "ticker": ticker}
                     for i, ticker in enumerate(("A", "B"))],
        "features": rows,
        "membership_reviewed": True, "actions_reviewed": True,
        "benchmark_reviewed": True, "source_manifest_reviewed": True,
    }


def test_selection_excludes_negative_r63_under_frozen_engine():
    report = select_monthly(signal_snapshot(), fixture_min_members=2)
    assert report["data_status"] == "REVIEWED_COMPLETE"  # fewer than five is allowed
    assert report["qualified_count"] == 1
    assert report["selected"] == ["B"]
    assert report["provisional_top5"] == ["B"]
    assert report["positive_momentum_disagreements"] == []
    assert report["automatic_execution"] is False


def test_missing_competitor_and_missing_provenance_hold():
    snap = signal_snapshot()
    snap["features"].pop()
    with pytest.raises(MonthlySignalHold):
        select_monthly(snap, fixture_min_members=2)
    snap = signal_snapshot()
    # A is conclusively negative-r63 and does not need SEC docs.
    # B is positive-r63; its unverified financials MUST hold the full signal.
    snap["features"][1]["financial_source"] = "UNKNOWN"
    report = select_monthly(snap, fixture_min_members=2)
    assert report["selected"] == []
    assert report["blockers"][0]["ticker"] == "B"
