"""Evidence-backed ticker-era checks; research-only, not S&P or trade authority."""
from datetime import date
from scripts.gem_membership_identity_audit import (
    identity_screen, identity_issues, screen_reference_symbols,
)
from scripts.gem_public_membership_research import parse_history, research_report


def member(symbol, cik):
    return {"ticker": symbol, "cik": cik}


def test_pre_ticker_fi_and_bny_are_not_double_counted_in_2022():
    data = [
        member("FISV", "0000798354"), member("FI", "0000798354"),
        member("BK", "0001390777"), member("BNY", "0001390777"),
        member("GOOG", "0001652044"), member("GOOGL", "0001652044"),
    ]
    result = identity_screen(data, date(2022, 12, 30))
    assert result["post_symbol_era_count"] == 4
    assert set(q["ticker"] for q in result["quarantined"]) == {"FI", "BNY"}
    assert result["confirmed_separate_share_classes"] == [
        {"cik": "0001652044", "tickers": ["GOOG", "GOOGL"]}
    ]
    assert result["unresolved_same_cik_collisions"] == []
    assert result["rank_authorized"] is False


def test_on_effective_date_ticker_switches_without_substituting_price_history():
    before = identity_screen([member("FISV", "0000798354"), member("FI", "0000798354")],
                             date(2023, 6, 6))
    after = identity_screen([member("FISV", "0000798354"), member("FI", "0000798354")],
                            date(2023, 6, 7))
    assert before["retained"] == ["FISV"]
    assert after["retained"] == ["FI"]


def test_unrelated_company_cik_does_not_trigger_fiserv_alias():
    assert identity_issues("FI", "0000001234", date(2022, 12, 30)) == []


def test_future_successor_stocks_are_not_backfilled_into_2022():
    history = identity_screen([
        member("PSKY", "0002041610"), member("SKYD", "0002041610"),
        member("PARA", "0000813828")], date(2022, 12, 30))
    assert history["retained"] == ["PARA"]
    assert {x["ticker"] for x in history["quarantined"]} == {"PSKY", "SKYD"}
    assert all(item["flags"][0]["do_not_backfill_predecessor"] for item in history["quarantined"])


def test_currently_valid_genuine_issuer_shareclasses_not_collapsed():
    rows = [
        member("GOOG", "0001652044"), member("GOOGL", "0001652044"),
        member("FOX", "0001754301"), member("FOXA", "0001754301"),
        member("NWS", "0001564708"), member("NWSA", "0001564708"),
    ]
    result = identity_screen(rows, date(2023, 1, 31))
    assert result["post_symbol_era_count"] == 6
    assert len(result["confirmed_separate_share_classes"]) == 3


def test_unresearched_same_cik_shareclass_pair_never_silently_collapsed():
    result = identity_screen([member("AAA", "0000000123"), member("AAB", "0000000123")],
                             date(2023, 1, 31))
    assert result["unresolved_same_cik_collisions"] == [
        {"cik": "0000000123", "tickers": ["AAA", "AAB"]}
    ]


def test_apparent_smurfit_westrock_in_december_2022_reference_is_quarantined():
    result = screen_reference_symbols({"SW", "AAPL"}, date(2022, 12, 30))
    assert result["retained"] == ["AAPL"]
    assert result["quarantined"][0]["ticker"] == "SW"
    assert result["quarantined"][0]["flags"][0]["effective_on"] == "2024-07-08"


def test_main_report_includes_rank_hold_and_quarantines():
    raw = (
        "symbol,cik,name,sector,date_added,date_removed,created_at\n"
        "FI,0000798354,Fiserv,financials,2001-04-02,,2023-06-08\n"
        "FISV,0000798354,Fiserv,financials,2001-04-02,2023-06-07,2007-03-05\n"
        "GOOG,0001652044,Alphabet,technology,2014-04-03,,2014-04-03\n"
        "GOOGL,0001652044,Alphabet,technology,2014-04-03,,2014-04-03\n"
    ).encode()
    report = research_report(raw, [date(2022, 12, 30)], retrieved_at="2026-10-12T12:00:00Z")
    snap = report["snapshots"][0]
    assert snap["asof_ticker_identity"]["post_symbol_era_count"] == 3
    assert snap["frozen_gem_top5_impact"].startswith("UNDETERMINED")
    assert snap["ranking_comparison_ready"] is False
    assert next(x for x in snap["members"] if x["ticker"] == "FI")["asof_ticker_identity_status"].startswith("QUARANTINED")


def test_2022_five_issuer_announced_ticker_changes_avoid_retrospective_overcount():
    rows = [
        member("ANTM", "0001156039"), member("ELV", "0001156039"),
        member("BLL", "0000009389"), member("BALL", "0000009389"),
        member("FB", "0001326801"), member("META", "0001326801"),
        member("NLOK", "0000849399"), member("GEN", "0000849399"),
        member("VIAC", "0000813828"), member("PARA", "0000813828"),
    ]
    jan = identity_screen(rows, date(2022, 1, 31))
    assert jan["post_symbol_era_count"] == 5
    assert set(jan["retained"]) == {"ANTM", "BLL", "FB", "NLOK", "VIAC"}
    assert {x["ticker"] for x in jan["quarantined"]} == {"ELV", "BALL", "META", "GEN", "PARA"}
    assert jan["unresolved_same_cik_collisions"] == []
    december = identity_screen(rows, date(2022, 12, 30))
    assert set(december["retained"]) == {"ELV", "BALL", "META", "GEN", "PARA"}
    assert december["post_symbol_era_count"] == 5


def test_off_by_one_public_interval_does_not_override_documented_ticker_session():
    # Source interval reversals around June 8/9 are approximate. At the
    # documented first META session, FB must not be considered a distinct line.
    june8 = identity_screen([member("FB", "0001326801"), member("META", "0001326801")],
                             date(2022, 6, 8))
    june9 = identity_screen([member("FB", "0001326801"), member("META", "0001326801")],
                             date(2022, 6, 9))
    assert june8["retained"] == ["FB"]
    assert june9["retained"] == ["META"]
