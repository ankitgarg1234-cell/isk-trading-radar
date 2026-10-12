"""GEM complete-universe QA and data-state tests.

Synthetic tiny universes exercise the exact failure paths. They are never
considered actual S&P constituent evidence or real portfolio signals.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from dual_momentum.gem_source_evidence import FROZEN_COMMIT, inspect_probes, merge_source_status
from gem_data.coverage_gate import RankingHold, audit_snapshot


def _facts(*, now_rev=160, previous_rev=100):
    values = {
        "revenue_now": now_rev, "revenue_prior": previous_rev,
        "income_now": 30, "income_prior": 10,
        "operating_now": 80, "operating_prior": 30,
    }
    rows = {}
    for key, value in values.items():
        old = key.endswith("prior")
        rows[key] = {
            "value": value, "form": "10-Q", "unit": "USD",
            "concept": "us-gaap:" + key, "accession": "0000000000-26-000012",
            "source_sha256": "a" * 64, "source_context_verified": True,
            "publication_reviewed": True,
            "filed": "2025-08-10" if old else "2026-08-10",
            "accepted_at": "2025-08-10T16:05:00Z" if old else "2026-08-10T16:05:00Z",
            "start": "2025-04-01" if old else "2026-04-01",
            "end": "2025-06-30" if old else "2026-06-30",
        }
    return rows


def _bars(rise):
    dates = []
    cursor = date(2026, 9, 30)
    while len(dates) < 127:
        if cursor.weekday() < 5:
            dates.append(cursor)
        cursor -= timedelta(days=1)
    dates.reverse()
    return [{
        "session": d.isoformat(),
        "frozen_close": 100.0 + rise * i,
        "nominal_open": 100.0,
        "nominal_high": 120.0,
        "nominal_low": 90.0,
        "volume": 2_000_000.0,
    } for i, d in enumerate(dates)]


def _snapshot():
    symbols = ["AAA", "BBB", "CCC"]
    return {
        "schema": "gem-source-qa-input-v1",
        "strategy_commit": FROZEN_COMMIT,
        "signal_session": "2026-09-30",
        "official_month_end": True,
        "primary_universe_bytes_hash_verified": True,
        "corporate_action_coverage_verified": True,
        "spy_benchmark_coverage_verified": True,
        "complete_exchange_calendar_verified": True,
        "universe": [{"ticker": s, "security_id": f"{i}:{s}"} for i, s in enumerate(symbols)],
        "candidates": [
            {"ticker": s, "security_id": f"{i}:{s}",
             "frozen_vendor_parity_reviewed": True,
             "bars": _bars(1.0 - 0.15 * i),
             "nominal_close": 118.0,
             "quarterly_facts": _facts(now_rev=160 if i < 2 else 110)}
            for i, s in enumerate(symbols)
        ]
    }


def test_complete_fixture_rank_proposal_never_authorizes_trades():
    result = audit_snapshot(_snapshot(), fixture_min_members=3)
    assert result["member_count"] == 3
    assert result["evaluated_count"] == 3
    assert result["selected"] == ["AAA", "BBB"]
    assert result["candidate_count"] == 2
    assert result["paper_execution_authorized"] is False
    assert result["state"] == "AWAITING_INDEPENDENT_SIGNED_SOURCE_QA"
    assert len(result["decision_hash"]) == 64


def test_production_full_sp500_gate_refuses_three_member_fixture():
    with pytest.raises(RankingHold, match="S&P constituent coverage"):
        audit_snapshot(_snapshot())


def test_missing_competitor_is_not_silently_removed():
    snap = _snapshot()
    snap["candidates"] = snap["candidates"][:-1]
    with pytest.raises(RankingHold, match="Missing one or more"):
        audit_snapshot(snap, fixture_min_members=3)


def test_future_filing_does_not_enter_rank():
    snap = _snapshot()
    snap["candidates"][0]["quarterly_facts"]["revenue_now"]["accepted_at"] = "2026-10-01T09:00:00Z"
    with pytest.raises(RankingHold, match="Late/ambiguous"):
        audit_snapshot(snap, fixture_min_members=3)


def test_unknown_quarter_semantics_blocks():
    snap = _snapshot()
    snap["candidates"][0]["quarterly_facts"]["operating_now"]["source_context_verified"] = False
    with pytest.raises(RankingHold, match="not independently mapped"):
        audit_snapshot(snap, fixture_min_members=3)


def test_future_price_bar_blocks():
    snap = _snapshot()
    snap["candidates"][0]["bars"][-1]["session"] = "2026-10-01"
    with pytest.raises(RankingHold, match="Stale/forward/duplicate"):
        audit_snapshot(snap, fixture_min_members=3)


def test_missing_adjustment_parity_blocks():
    snap = _snapshot()
    snap["candidates"][1]["frozen_vendor_parity_reviewed"] = False
    with pytest.raises(RankingHold, match="adjusted-close"):
        audit_snapshot(snap, fixture_min_members=3)


def _probe_bundle():
    return {
        "schema": "gem-source-probes-v1", "frozen_commit": FROZEN_COMMIT,
        "checked_on": "2026-10-12",
        "sources": [{"key": "prices", "status": "PARTIAL",
                     "evidence": "Sample only", "missing": ["Full 500"],
                     "checked_scope": "4 securities"}],
    }


def test_diagnostic_prices_do_not_become_verified():
    state = inspect_probes(_probe_bundle(), today=date(2026, 10, 12))
    assert state["prices"]["status"] == "PARTIAL"
    assert state["prices"]["trade_eligible"] is False
    assert state["sec"]["status"] == "UNKNOWN"


def test_claimed_green_source_downgraded_to_qa_pending():
    obj = _probe_bundle()
    obj["sources"][0]["status"] = "VERIFIED"
    row = inspect_probes(obj, today=date(2026, 10, 12))
    assert row["prices"]["status"] == "PENDING_QA"
    merged = merge_source_status(probe=row, observed={"prices": {"status": "VERIFIED"}})
    assert merged["prices"]["status"] == "UNKNOWN"  # Spoofed verified with no timestamp cannot pass
    assert merged["prices"]["trade_eligible"] is False


def test_old_price_probe_expires_in_two_days():
    result = inspect_probes(_probe_bundle(), today=date(2026, 10, 15))
    assert result["prices"]["status"] == "STALE"


def test_unknown_or_future_probe_fails():
    obj = _probe_bundle()
    obj["checked_on"] = "2099-01-01"
    with pytest.raises(ValueError, match="future"):
        inspect_probes(obj, today=date(2026, 10, 12))
