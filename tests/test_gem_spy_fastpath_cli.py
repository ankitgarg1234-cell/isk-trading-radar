"""Offline tests for operator SPY raw close + dividend fast path."""
from datetime import datetime
import csv
import pytest

from scripts.gem_spy_fastpath_cli import read_csv, fetch_yfinance


def test_spy_offline_csv_accepts_raw_price_and_ex_date_dividend(tmp_path):
    path=tmp_path/"spy.csv"
    with path.open("w",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=["session","close","dividend"])
        writer.writeheader()
        writer.writerow({"session":"2026-09-17","close":"100","dividend":"0"})
        writer.writerow({"session":"2026-09-18","close":"99","dividend":"1"})
    rows=read_csv(str(path))
    assert rows==[
        {"session":"2026-09-17","close":100,"dividend":0,"stock_split":0},
        {"session":"2026-09-18","close":99,"dividend":1,"stock_split":0}]


def test_fetched_spy_requires_raw_close_and_dividend_per_session():
    class Frame:
        empty=False
        columns=["Close","Dividends","Stock Splits"]
        def iterrows(self):
            yield datetime(2026,9,17),{"Close":100,"Dividends":0,"Stock Splits":0}
            yield datetime(2026,9,18),{"Close":99,"Dividends":1,"Stock Splits":0}
    class Ticker:
        def history(self,**kw):
            assert kw["auto_adjust"] is False
            assert kw["actions"] is True
            assert kw["start"]=="2026-09-17"
            return Frame()
    def factory(ticker):
        assert ticker=="SPY"
        return Ticker()
    rows=fetch_yfinance("2026-09-17","2026-09-21",ticker_factory=factory)
    assert rows[1]["dividend"]==1
    assert rows[1]["close"]==99
    with pytest.raises(ValueError):
        fetch_yfinance("2026-09-21","2026-09-17",ticker_factory=factory)
