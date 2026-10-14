"""Offline no-order regression tests for authorized IBKR price crosschecks."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from gem_data.gem_ibkr_gap_crosscheck import (
    IBKRGatewayHold, _authorization, crosscheck_yahoo_ibkr,
    normalize_ibkr_history, _fetch,
)

DAYS=("2026-06-09","2026-06-10","2026-06-15")
NY=ZoneInfo("America/New_York")


def web_bar(day,*,close=100.0):
    t=int(datetime.fromisoformat(day+"T09:30:00").replace(tzinfo=NY).timestamp()*1000)
    return {"t":t,"o":100.0,"h":102.0,"l":98.0,"c":close,"v":900000}


def sample():
    return {"data":[web_bar(d) for d in DAYS],
            "outsideRth":False,"source":"trades","mktDataDelay":0}


def yahoo(day):
    return {"ticker":"AAPL","session":day,
            "open":100.0,"high":102.0,"low":98.0,
            "close":100.0,"volume":900000}


def test_exact_completed_sessions_and_normalized_prices():
    bars=normalize_ibkr_history(sample())
    assert set(bars)==set(DAYS)
    assert bars["2026-06-09"]["close"]==100.0
    assert bars["2026-06-15"]["volume"]==900000.0


def test_two_source_agreement_is_not_price_certification():
    bars=normalize_ibkr_history(sample())
    result=crosscheck_yahoo_ibkr(yahoo(DAYS[0]),bars[DAYS[0]],ticker="AAPL")
    assert result["state"]=="PROVISIONAL_TWO_SOURCE_PRICE_MATCH"
    assert result["source_certified"] is False
    assert result["frozen_adjusted_close_verified"] is False
    assert result["trading_authorized"] is False


def test_significant_price_conflict_is_not_averaged_away():
    src=sample()
    src["data"][0]["c"]=101.0
    diff=crosscheck_yahoo_ibkr(yahoo(DAYS[0]),
                              normalize_ibkr_history(src)[DAYS[0]],ticker="AAPL")
    assert diff["state"]=="PROVIDER_DISAGREEMENT_HOLD"
    assert "close" in diff["discrepancies"]


@pytest.mark.parametrize("alter",[
    lambda d:d.update(outsideRth=True),
    lambda d:d["data"].append(d["data"][0].copy()),
    lambda d:d["data"][0].update(h=99.0),
    lambda d:d["data"][0].update(c=float("nan")),
    lambda d:d["data"][0].update(t="not-a-time"),
    lambda d:d.update(data=[]),
    lambda d:d.update(source="midpoint"),
])
def test_malformed_or_incompatible_ibkr_source_holds(alter):
    data=sample()
    alter(data)
    with pytest.raises(IBKRGatewayHold):
        normalize_ibkr_history(data)


def test_wrong_symbol_or_date_is_held():
    with pytest.raises(IBKRGatewayHold):
        crosscheck_yahoo_ibkr(yahoo(DAYS[0]),normalize_ibkr_history(sample())[DAYS[1]],ticker="AAPL")
    with pytest.raises(IBKRGatewayHold):
        crosscheck_yahoo_ibkr(yahoo(DAYS[0]),normalize_ibkr_history(sample())[DAYS[0]],ticker="MSFT")


def test_broker_history_requires_explicit_optin_and_separate_sso(monkeypatch):
    monkeypatch.delenv("GEM_IBKR_HISTORICAL_READONLY_ENABLED",raising=False)
    monkeypatch.delenv("GEM_IBKR_READONLY_BEARER",raising=False)
    with pytest.raises(IBKRGatewayHold):
        _authorization()
    monkeypatch.setenv("GEM_IBKR_HISTORICAL_READONLY_ENABLED","yes")
    with pytest.raises(IBKRGatewayHold):
        _authorization()
    monkeypatch.setenv("GEM_IBKR_READONLY_BEARER","opaque-long-test-token-do-not-log")
    with pytest.raises(IBKRGatewayHold):
        _authorization()
    monkeypatch.setenv("GEM_IBKR_CONID_MAP_JSON",'{"AAPL":265598}')
    secret,mapping=_authorization()
    assert mapping=={"AAPL":265598}
    assert "opaque-" in secret


def test_history_fetch_never_routes_orders(monkeypatch):
    import gem_data.gem_ibkr_gap_crosscheck as mod
    requests=[]
    class Response:
        status_code=200
        content=b'{"data":[]}'
        def json(self):
            return {"data":[]}
    class Client:
        def __init__(self,**kwargs):
            assert kwargs["follow_redirects"] is False
        def __enter__(self):
            return self
        def __exit__(self,*args):
            pass
        def get(self,url,*,params,headers):
            requests.append((url,params,headers))
            return Response()
    monkeypatch.setattr(mod.httpx,"Client",Client)
    payload,digest=_fetch(265598,"opaque-long-test-token-do-not-log")
    assert payload=={"data":[]}
    assert len(digest)==64
    assert requests[0][0].endswith("/iserver/marketdata/history")
    assert requests[0][1]["source"]=="trades"
    assert requests[0][1]["outsideRth"]=="false"
    assert all("/orders" not in req[0] for req in requests)
