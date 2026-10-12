"""Tests for bounded public research price sample; no live provider requests."""
import pytest
import json
from datetime import date, timedelta

from scripts.gem_historical_price_probe import (
    parse_vendor_csv, parse_yahoo_chart, session_coverage, vendor_url, yahoo_url,
)


def test_only_explicit_price_probe_symbols_are_allowed():
    assert vendor_url("AAPL").startswith("https://stooq.com/q/d/l/")
    with pytest.raises(ValueError, match="Explicit limited"):
        vendor_url("INVALID")


def test_raw_bar_schema_and_nominal_ohlc_are_checked():
    raw = (
        b"Date,Open,High,Low,Close,Volume\n"
        b"2022-12-29,100,110,90,105,2000000\n"
        b"2022-12-30,105,115,100,112,3000000\n"
    )
    bars = parse_vendor_csv(raw)
    assert bars["2022-12-30"]["Close"] == 112
    assert len(bars) == 2


def test_bad_ohlcv_and_duplicate_dates_block():
    with pytest.raises(ValueError, match="Invalid/duplicate"):
        parse_vendor_csv(
            b"Date,Open,High,Low,Close,Volume\n"
            b"2022-12-30,105,107,100,112,3000000\n"
        )
    with pytest.raises(ValueError, match="Invalid/duplicate"):
        parse_vendor_csv(
            b"Date,Open,High,Low,Close,Volume\n"
            b"2022-12-30,105,115,100,112,3000000\n"
            b"2022-12-30,105,115,100,112,3000000\n"
        )


def test_missing_sessional_dates_cannot_satisfy_price_coverage():
    sess = [(date(2022, 1, 1) + timedelta(days=i)).isoformat() for i in range(127)]  # synthetic dates, no trade authority
    available = {d: {"Close": 100} for d in sess[:-1]}
    report = session_coverage(available, {"2022-12-30": sess})
    assert report["2022-12-30"]["complete_127_dates"] is False


def test_short_series_is_not_a_complete_127_bar_history():
    result = session_coverage({"2022-12-30": {"Close": 100}},
                              {"2022-12-30": ["2022-12-30"]})
    assert result["2022-12-30"]["complete_127_dates"] is False


def test_yahoo_url_is_read_only_and_bounded():
    assert "period1=" in yahoo_url("AAPL")
    assert "/v8/finance/chart/AAPL" in yahoo_url("AAPL")
    with pytest.raises(ValueError, match="Explicit sample"):
        yahoo_url("NOT_A_REAL_GEM_SAMPLE")


def test_yahoo_chart_original_arrays_are_parsed_without_certification():
    from datetime import datetime, timezone
    stamp = int(datetime(2022, 12, 30, 14, 30, tzinfo=timezone.utc).timestamp())
    raw = json.dumps({"chart":{"result":[{"timestamp":[stamp],
        "indicators":{"quote":[{"open":[100], "high":[110], "low":[90],
                                 "close":[105], "volume":[2000000]}]}}],
        "error":None}}).encode()
    bars = parse_yahoo_chart(raw)
    assert bars["2022-12-30"]["Close"] == 105
    assert bars["2022-12-30"]["Volume"] == 2000000


def test_yahoo_chart_array_mismatch_blocks():
    raw = json.dumps({"chart":{"result":[{"timestamp":[100,101],
        "indicators":{"quote":[{"open":[100], "high":[100], "low":[100],
                                 "close":[100], "volume":[1]}]}}]}}).encode()
    with pytest.raises(ValueError,match="not aligned"):
        parse_yahoo_chart(raw)
