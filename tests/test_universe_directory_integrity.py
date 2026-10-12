"""Regression tests for exchange-directory universe completeness.

These tests do not alter GEMv1 ranking or trade selection.
"""
from app.market import YahooMarketProvider


class _Response:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


def test_partial_directory_outage_does_not_publish_smaller_universe(monkeypatch):
    provider = YahooMarketProvider()
    monkeypatch.setattr(YahooMarketProvider, "_universe_cache", [])
    monkeypatch.setattr(YahooMarketProvider, "_universe_cache_at", 0.0)

    def get(url, **kwargs):
        if "otherlisted.txt" in url:
            raise ConnectionError("directory unavailable")
        return _Response(
            "Symbol|Security Name|Test Issue|ETF|Financial Status\n"
            "AAPL|Apple Inc|N|N|N\n"
        )

    monkeypatch.setattr(provider.client, "get", get)
    assert provider.us_equity_universe(force_refresh=True) == []
    assert YahooMarketProvider._universe_cache == []


def test_partial_directory_outage_preserves_last_complete_cache(monkeypatch):
    provider = YahooMarketProvider()
    previous = [{"symbol": "AAPL", "name": "Apple Inc", "exchange": "NASDAQ", "name_key": "apple"}]
    monkeypatch.setattr(YahooMarketProvider, "_universe_cache", previous)
    monkeypatch.setattr(YahooMarketProvider, "_universe_cache_at", 0.0)

    def get(url, **kwargs):
        if "otherlisted.txt" in url:
            raise ConnectionError("directory unavailable")
        return _Response(
            "Symbol|Security Name|Test Issue|ETF|Financial Status\n"
            "MSFT|Microsoft Corp|N|N|N\n"
        )

    monkeypatch.setattr(provider.client, "get", get)
    assert provider.us_equity_universe(force_refresh=True) == previous
    assert YahooMarketProvider._universe_cache == previous
