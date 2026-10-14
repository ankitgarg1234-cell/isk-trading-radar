from gem_data.market_calendar_benchmark import (validate_completed_sessions, reconstruct_spy_total_return)
from gem_data.wikipedia_constituents import parse_wikipedia_members, WikipediaMembersHold
import pytest


def test_completed_exchange_session_validation():
    result=validate_completed_sessions(["2026-10-12","2026-10-13"],
        [{"session":"2026-10-12","final":True,"close":100.},
         {"session":"2026-10-13","final":False,"close":101.}],
        receipt_sha256="a"*64,completed_through="2026-10-13")
    assert result["missing_or_unfinalized"]==["2026-10-13"]
    assert result["status"]=="HOLD"


def test_spy_total_return_includes_exdate_cash():
    report=reconstruct_spy_total_return(
      [{"session":"2026-10-12","close":100.},
       {"session":"2026-10-13","close":99.}],
      [{"ex_date":"2026-10-13","amount":1.}])
    assert abs(report["return_pct"])<1e-9
    assert report["status"]=="UNVERIFIED_SOURCE_INPUT_HOLD"
    assert report["trading_authorized"] is False


def test_missing_verified_input_does_not_fake_calendar_pass():
    assert validate_completed_sessions(["2026-10-12"],[],
         receipt_sha256="a"*64,completed_through="2026-10-12")["status"]=="HOLD"


def test_constituent_parser_rejects_too_small_coverage():
    html=b'<table id="constituents"><tr><th>Symbol</th><th>CIK</th></tr><tr><td>ABC</td><td>123456</td></tr></table>'
    with pytest.raises(WikipediaMembersHold):
        parse_wikipedia_members(html*15)
