from datetime import date
import httpx
import pytest
from gem_data.tiingo_eod_probe import tiingo_eod_observation, TiingoDataHold


def test_tiingo_probe_reads_nominal_and_preserves_alt_adjustment():
    def serve(req):
        assert req.headers["Authorization"] == "Token fake-secret-for-fixture"
        assert "fake-secret" not in str(req.url)
        return httpx.Response(200,json=[{
            "date":"2025-01-02T00:00:00Z",
            "open":100., "high":101., "low":99., "close":100.,
            "volume":1000000, "adjClose":97.5, "divCash":0.,
            "splitFactor":1.,
        }])
    with httpx.Client(transport=httpx.MockTransport(serve)) as client:
        r=tiingo_eod_observation("AAPL",date(2025,1,2),date(2025,1,2),
                                token="fake-secret-for-fixture", client=client)
    assert r["provider"]=="TIINGO"
    assert r["basis"]=="NOMINAL_OHLCV"
    assert r["bars"][0]["close"]==100.
    assert r["vendor_specific_adjustments"][0]["tiingo_adj_close"]==97.5
    assert r["trading_approved"] is False
    assert r["frozen_adjustment_parity_verified"] is False


def test_missing_token_holds_without_request(monkeypatch):
    monkeypatch.delenv("TIINGO_API_TOKEN", raising=False)
    with pytest.raises(TiingoDataHold, match="not configured"):
        tiingo_eod_observation("AAPL",date(2025,1,2),date(2025,1,2))


def test_bad_ohlc_rejected():
    def bad(req):
        return httpx.Response(200,json=[{
            "date":"2025-01-02","open":100.,"high":90.,"low":80.,"close":100.,
            "volume":1000,"adjClose":100.,"divCash":0.,"splitFactor":1.
        }])
    with httpx.Client(transport=httpx.MockTransport(bad)) as client:
        with pytest.raises(TiingoDataHold, match="OHLC"):
            tiingo_eod_observation("AAPL",date(2025,1,2),date(2025,1,2),
                                    token="fixture", client=client)
