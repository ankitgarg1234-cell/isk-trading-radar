"""Regression tests for fail-closed integrated manual monthly packets."""
import pytest

from gem_data import gem_monthly_packet as module


def payload():
    return {"schema":"gem-manual-month-packet-v1",
            "source_month":{"schema":"invalid", "signal_session":"2026-09-30"},
            "initial_cash":"10000", "manual_events":[],
            "reference_prices":{}}


def test_invalid_source_month_returns_hold_without_tickets():
    out=module.build_monthly_packet(payload())
    assert out["status"]=="DATA_HOLD"
    assert out["manual_trade_sheet"] is None
    assert out["orders_submitted"]==0
    assert any(x["scope"]=="SOURCE_MONTH" for x in out["blockers"])


def test_unreviewed_ranking_cannot_create_tickets(monkeypatch):
    def fake(month):
        return {"data_status":"HOLD","selected":[],
                "signal_session":"2026-09-30"}
    monkeypatch.setattr(module,"recompute_full_month",fake)
    out=module.build_monthly_packet(payload())
    assert out["status"]=="DATA_HOLD"
    assert any(x["scope"]=="RANKING_SOURCE_QA" for x in out["blockers"])


def test_complete_reviewed_signal_yields_only_user_review_sheet(monkeypatch):
    def fake(month):
        return {"data_status":"REVIEWED_COMPLETE","selected":list("ABCDE"),
                "signal_session":"2026-09-30"}
    monkeypatch.setattr(module,"recompute_full_month",fake)
    x=payload()
    x["reference_prices"]={k:100 for k in "ABCDE"}
    out=module.build_monthly_packet(x)
    assert out["status"]=="INDICATIVE_SHEET_READY_FOR_USER_REVIEW"
    assert len(out["manual_trade_sheet"]["tickets"])==5
    assert out["automatic_execution"] is False
    assert out["orders_submitted"]==0


def test_statement_mismatch_holds_even_if_signal_reviewed(monkeypatch):
    monkeypatch.setattr(module,"recompute_full_month",
                        lambda _: {"data_status":"REVIEWED_COMPLETE",
                                   "selected":list("ABCDE")})
    x=payload()
    x["reference_prices"]={k:100 for k in "ABCDE"}
    x["broker_statement"]={"source":"MANUAL_BROKER_STATEMENT_EXPORT",
                           "statement_sha256":"a"*64,
                           "shares":{},"cash":"9999","as_of":"2026-09-30"}
    out=module.build_monthly_packet(x)
    assert out["status"]=="DATA_HOLD"
    assert any(b["scope"]=="MANUAL_LEDGER" for b in out["blockers"])


def test_malformed_bundle_rejected():
    with pytest.raises(ValueError):
        module.build_monthly_packet({})
