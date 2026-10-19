"""Offline synthetic Yahoo gap tests; no network requests or credentials."""
import os
from datetime import datetime, timezone
import pandas as pd
import pytest
from gem_data.gem_yfinance_gap_research import (
    TARGET_DATES, YahooResearchHold, collect_candidates, build_gap_worklist,
    save_candidate_file,
)


def frame(*, missing=(), null=(), invalid_high=False):
    rows=[]
    for session in TARGET_DATES:
        if session in missing:
            continue
        rows.append({"day":session, "Open":100., "High":90. if invalid_high else 106.,
                     "Low":99., "Close":None if session in null else 104.,
                     "Adj Close":102., "Volume":150000.,
                     "Dividends":0., "Stock Splits":0.})
    index=pd.DatetimeIndex([row.pop("day") for row in rows],tz="America/New_York")
    return pd.DataFrame(rows,index=index)


def test_exact_three_dates_are_unapproved_research_candidates():
    result=collect_candidates(["AAPL","MSFT"],fetch_fn=lambda *a:(frame(),"USD"),
                  now=datetime(2026,10,14,tzinfo=timezone.utc))
    assert result["possible_replacements"]==6
    assert result["allowed_for_live_trading"] is False
    assert result["merge_into_marketstack"] is False
    assert all(x["source_qa_status"]=="NOT_APPROVED" for x in result["candidates"])
    assert [x["bar"]["session"] for x in result["candidates"][:3]]==list(TARGET_DATES)
    assert result["candidates"][0]["bar"]["close"]==104.
    assert result["candidates"][0]["bar"]["yahoo_adj_close"]==102.


def test_missing_null_and_bad_ohlc_fail_closed():
    result=collect_candidates(["AAPL"],fetch_fn=lambda *a:(
        frame(missing=[TARGET_DATES[0]],null=[TARGET_DATES[1]]),"USD"))
    assert result["possible_replacements"]==1
    assert {x["session"] for x in result["holds"]}==set(TARGET_DATES[:2])
    invalid=collect_candidates(["AAPL"],fetch_fn=lambda *a:(frame(invalid_high=True),"USD"))
    assert invalid["possible_replacements"]==0
    assert {x["reason"] for x in invalid["holds"]}=={"INVALID_OHLC_GEOMETRY"}


def test_non_usd_and_unknown_currency_are_not_accepted():
    for currency in ("SEK",None):
        r=collect_candidates(["AAPL"],fetch_fn=lambda *a:(frame(),currency))
        assert r["possible_replacements"]==0
        assert r["holds"]==[{"ticker":"AAPL","reason":"NON_USD_OR_CURRENCY_NOT_VERIFIED"}]


def test_share_class_mapping_is_explicit_and_unverified():
    symbols=[]
    def fetch(symbol,*a):
        symbols.append(symbol)
        return frame(),"USD"
    r=collect_candidates(["BRK.B","BF.B"],fetch_fn=fetch)
    assert symbols==["BRK-B","BF-B"]
    assert all(x["symbol_alias_used"] and x["requires_independent_reference"]
               for x in r["candidates"])


def test_inventory_picks_only_rejected_dates_and_uses_cursor():
    rows=[
        ("AAPL",[["2026-06-09","null close"],["2026-07-01","other"]]),
        ("BRK.B",[["2026-06-10","null close"]]),
        ("MSFT",[["2026-06-13","not a trading session"]]),
        ("NVDA",[["2026-06-15","invalid close"]]),
    ]
    first=build_gap_worklist(rows,limit=2)
    assert first=={"AAPL":["2026-06-09"],"BRK.B":["2026-06-10"]}
    assert build_gap_worklist(rows,after_symbol="BRK.B")=={"NVDA":["2026-06-15"]}
    r=collect_candidates(list(first),wanted_sessions=first,fetch_fn=lambda *a:(frame(),"USD"))
    assert r["possible_replacements"]==2
    assert [x["bar"]["session"] for x in r["candidates"]]==["2026-06-09","2026-06-10"]


def test_invalid_parameters_do_not_make_provider_calls():
    with pytest.raises(YahooResearchHold):
        collect_candidates(["AAPL"]*2)
    with pytest.raises(YahooResearchHold):
        collect_candidates(["T%02d"%i for i in range(21)])
    with pytest.raises(YahooResearchHold):
        collect_candidates(["AAPL"],target_dates=["2026-06-13"])
    with pytest.raises(YahooResearchHold):
        collect_candidates(["AAPL"],target_dates=["2027-01-01"])
    with pytest.raises(YahooResearchHold,match="worklist mismatch"):
        collect_candidates(["AAPL"],wanted_sessions={"MSFT":["2026-06-09"]})
    with pytest.raises(YahooResearchHold,match="outside requested"):
        collect_candidates(["AAPL"],wanted_sessions={"AAPL":["2026-07-01"]})


def test_private_create_only_file(tmp_path):
    result=collect_candidates(["AAPL"],fetch_fn=lambda *a:(frame(),"USD"))
    file=tmp_path/"gap.json"
    save_candidate_file(file,result)
    assert file.exists()
    assert os.stat(file).st_mode & 0o777==0o600
    with pytest.raises(FileExistsError):
        save_candidate_file(file,result)


def test_fetch_exception_does_not_expose_secret_details():
    def fail(*args):
        raise RuntimeError("secret-do-not-print")
    result=collect_candidates(["AAPL"],fetch_fn=fail)
    assert "secret-do-not-print" not in str(result)
    assert result["holds"]==[{"ticker":"AAPL","reason":"YFINANCE_FETCH_RuntimeError"}]
