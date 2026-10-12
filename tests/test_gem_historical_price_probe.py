"""Tests for bounded public research price sample; no live provider requests."""
import pytest
from datetime import date, timedelta

from scripts.gem_historical_price_probe import (
    parse_vendor_csv, session_coverage, vendor_url,
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
