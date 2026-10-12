"""Research-only public membership: never imports or authorizes GEMv1 trades."""
from datetime import date

import pytest

from scripts.gem_public_membership_research import (
    ResearchSourceError, asof_members, parse_history, research_report,
)

HEADER = "symbol,cik,name,sector,date_added,date_removed,created_at\n"


def row(symbol, start, end="", created="2025-01-01", cik="0000001234"):
    return f"{symbol},{cik},Issuer,industrials,{start},{end},{created}\n"


def test_asof_effective_and_removal_boundaries_preserve_delisted():
    raw = (HEADER
           + row("OLD", "2019-01-01", "2023-07-01")
           + row("NEW", "2023-07-01")
           + row("HOLD", "2007-03-05*")).encode()
    rows = parse_history(raw)
    assert [x["ticker"] for x in asof_members(rows, date(2023, 6, 30))] == ["HOLD", "OLD"]
    assert [x["ticker"] for x in asof_members(rows, date(2023, 7, 1))] == ["HOLD", "NEW"]
    assert rows[-1]["date_approximate"] is True


def test_research_report_tracks_approximate_and_late_recorded_members():
    raw = (HEADER + row("AAA", "2010-01-01*", created="2026-10-01")).encode()
    report = research_report(raw, [date(2023, 6, 30)], retrieved_at="2026-10-12T12:00:00+00:00")
    snap = report["snapshots"][0]
    assert snap["approximate_date_count"] == 1
    assert snap["not_recorded_by_snapshot_count"] == 1
    assert "RETROSPECTIVELY_RECONSTRUCTED" in snap["quality_flags"]
    assert report["paper_execution_authorized"] is False
    assert report["primary_sp_dji_source"] is False
    assert report["classification"].startswith("UNVERIFIED")


def test_overlapping_duplicate_security_ticker_is_rejected():
    raw = (HEADER + row("AAA", "2020-01-01") + row("AAA", "2021-01-01")).encode()
    with pytest.raises(ResearchSourceError, match="Ambiguous"):
        asof_members(parse_history(raw), date(2023, 1, 31))


def test_before_public_source_tracking_cannot_be_certified():
    with pytest.raises(ResearchSourceError, match="March 2007"):
        asof_members([], date(2001, 1, 1))


def test_invalid_intervals_and_schema_rejected():
    with pytest.raises(ResearchSourceError, match="Impossible"):
        parse_history((HEADER + row("AAA", "2023-03-01", "2023-02-01")).encode())
    with pytest.raises(ResearchSourceError, match="schema"):
        parse_history(b"symbol,price\nAAA,100\n")


def test_secondary_comparisons_report_disagreements_without_replacement():
    raw = (HEADER + row("AAA", "2020-01-01") + row("BRK.B", "2020-01-01")).encode()
    current = ("Symbol,CIK\nAAA,0000001234\nBRK.B,0000000123\nCCC,0000000124\n").encode()
    april = "AAA\tIssuer\t0.5\nBRK/B\tIssuer\t0.5\nZZZ\tOther\t0.5\n".encode()
    report = research_report(raw, [date(2026, 4, 30)], current_raw=current,
                             monthly_raw={"2026-04-30": april}, retrieved_at="2026-10-12T12:00:00+00:00")
    assert report["cross_checks"]["other_public_current"]["only_in_reference"] == ["CCC"]
    assert report["cross_checks"]["monthly_2026-04-30"]["only_in_reference"] == ["ZZZ"]
    assert "BRK.B" not in report["cross_checks"]["monthly_2026-04-30"]["only_in_reference"]
    assert report["paper_execution_authorized"] is False


def test_future_membership_research_date_must_not_replay_unavailable_members():
    raw = (HEADER + row("AAA", "2010-01-01")).encode()
    with pytest.raises(ResearchSourceError, match="Future research snapshot"):
        research_report(raw, [date(2026, 12, 31)],
                        retrieved_at="2026-10-12T12:00:00Z")


def test_history_record_created_after_retrieval_is_rejected():
    raw = (HEADER + row("AAA", "2010-01-01", created="2026-10-13")).encode()
    with pytest.raises(ResearchSourceError, match="dated after retrieval"):
        research_report(raw, [date(2022, 12, 30)],
                        retrieved_at="2026-10-12T12:00:00Z")


def test_naive_retrieval_timestamp_is_rejected():
    raw = (HEADER + row("AAA", "2010-01-01")).encode()
    with pytest.raises(ResearchSourceError, match="Timezone-aware"):
        research_report(raw, [date(2022, 12, 30)],
                        retrieved_at="2026-10-12T12:00:00")
