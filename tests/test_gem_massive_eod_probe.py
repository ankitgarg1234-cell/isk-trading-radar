from datetime import date, datetime, timezone
import httpx
import pytest
from gem_data.massive_eod_probe import massive_raw_eod_observation, MassiveDataHold
from gem_data.market_data_patch import reconcile_prices


def test_massive_requests_raw_ohlcv_without_url_token():
    epoch=int(datetime(2025,1,2,tzinfo=timezone.utc).timestamp()*1000)
    def handle(req):
        assert req.headers["Authorization"]=="Bearer fake-key"
        assert req.url.params["adjusted"]=="false"
        assert "fake-key" not in str(req.url)
        return httpx.Response(200,json={
            "status":"OK","resultsCount":1,
            "results":[{"t":epoch,"o":100,"h":101,"l":99,"c":100,"v":1000000}]})
    with httpx.Client(transport=httpx.MockTransport(handle)) as c:
        x=massive_raw_eod_observation("AAPL",date(2025,1,2),date(2025,1,2),
                                     token="fake-key",client=c)
    assert x["bars"][0]["close"]==100
    assert x["frozen_adjustment_parity_verified"] is False
    assert x["trading_approved"] is False


def test_raw_ohlcv_sources_agree_when_one_omits_neutral_event_columns():
    day="2025-01-02"
    bar={"ticker":"AAPL","session":day,"open":100,"high":101,"low":99,
         "close":100,"volume":1000000}
    a={"provider":"TIINGO","basis":"NOMINAL_OHLCV",
       "receipt_sha256":"a"*64,"bars":[dict(bar,split_factor=1,dividend=0)]}
    b={"provider":"MASSIVE","basis":"NOMINAL_OHLCV",
       "receipt_sha256":"b"*64,"bars":[bar]}
    report=reconcile_prices("AAPL",[day],[a,b])
    assert report["corroborated_patch_candidates"]==1
    assert report["frozen_adjusted_price_parity"] is False
    assert report["manual_execution_authorized"] is False
    a["bars"][0]["split_factor"]=2
    held=reconcile_prices("AAPL",[day],[a,b])
    assert held["corroborated_patch_candidates"]==0
    assert held["conflicts"]


def test_massive_missing_token_fails_closed(monkeypatch):
    monkeypatch.delenv("MASSIVE_API_KEY",raising=False)
    with pytest.raises(MassiveDataHold):
        massive_raw_eod_observation("AAPL",date(2025,1,2),date(2025,1,2))
