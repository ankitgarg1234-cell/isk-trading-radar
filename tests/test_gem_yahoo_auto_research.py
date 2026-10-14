"""No-network tests for opt-in Yahoo personal research GEM bot."""
from datetime import datetime, timezone
import pytest

from gem_data import gem_yahoo_auto_research as auto
from gem_data.gem_yfinance_gap_research import collect_candidates


NOW=datetime(2026,10,14,14,tzinfo=timezone.utc)


def opt_in(monkeypatch):
    monkeypatch.setenv("GEM_YFINANCE_PERSONAL_RESEARCH_OPT_IN","yes")
    monkeypatch.setenv("GEM_YFINANCE_PERSONAL_USE_ACK","yes")
    monkeypatch.setenv("GEM_READONLY_DATABASE_URL",
                       "postgresql://gem_web_readonly:test@localhost/test")
    monkeypatch.setenv("GEM_INGEST_DATABASE_URL",
                       "postgresql://gem_source_ingest_limited:test@localhost/test")


def test_yahoo_not_accessed_without_explicit_opt_in(monkeypatch):
    monkeypatch.delenv("GEM_YFINANCE_PERSONAL_RESEARCH_OPT_IN",raising=False)
    monkeypatch.delenv("GEM_YFINANCE_PERSONAL_USE_ACK",raising=False)
    with pytest.raises(auto.YahooAutoHold):
        auto.research_batch(now=NOW)


def test_research_batch_records_provisional_candidates_only(monkeypatch):
    opt_in(monkeypatch)
    monkeypatch.setattr(auto,"pending_worklist",
                        lambda **kwargs: {"pending":{"AAPL":["2026-06-09","2026-06-10"]},
                                           "already_available":0,"retry_backoff_symbols":0})
    requests=[]
    stored=[]
    monkeypatch.setattr(auto,"_reserve_attempt",
                        lambda *args: requests.append(args[1:]) or True)
    monkeypatch.setattr(auto,"_store_candidate",
                        lambda writer, candidate, observed: stored.append(candidate) or 1)
    monkeypatch.setattr(auto,"_record_hold",
                        lambda *args: (_ for _ in ()).throw(AssertionError("unexpected hold")))
    monkeypatch.setattr(auto,"collect_candidates",
                        lambda tickers, **kwargs:{
                            "candidates":[{
                                "marketstack_ticker":"AAPL",
                                "bar":{"session":day},"normalized_row_sha256":"a"*64,
                                "status":"GAP_CANDIDATE_ONLY",
                                "trading_authorized":False} for day in kwargs["wanted_sessions"]["AAPL"]],
                            "holds":[]})
    result=auto.research_batch(now=NOW,max_tickers=2)
    assert result["requested"]==1
    assert result["candidate_bars"]==2
    assert result["certified"] is False
    assert result["trading_authorized"] is False
    assert len(stored)==2
    assert all(not c["trading_authorized"] for c in stored)
    assert requests[0]==("AAPL","20261014")


def test_already_attempted_cannot_spend_again(monkeypatch):
    opt_in(monkeypatch)
    monkeypatch.setattr(auto,"pending_worklist",
                        lambda **kwargs:{"pending":{"AAPL":["2026-06-09"]},
                                         "already_available":0,"retry_backoff_symbols":0})
    monkeypatch.setattr(auto,"_reserve_attempt",lambda *args:False)
    monkeypatch.setattr(auto,"collect_candidates",
                        lambda *args,**kwargs:(_ for _ in ()).throw(
                            AssertionError("network must not be called")))
    result=auto.research_batch(now=NOW)
    assert result["requested"]==0
    assert result["candidate_bars"]==0
    assert result["trading_authorized"] is False


def test_provider_fails_and_hold_written_only(monkeypatch):
    opt_in(monkeypatch)
    monkeypatch.setattr(auto,"pending_worklist",
                        lambda **kwargs:{"pending":{"BRK.B":["2026-06-09"]},
                                         "already_available":0,"retry_backoff_symbols":0})
    monkeypatch.setattr(auto,"_reserve_attempt",lambda *args:True)
    monkeypatch.setattr(auto,"collect_candidates",
                        lambda *args,**kwargs:{"candidates":[],
                            "holds":[{"ticker":"BRK.B","reason":"NON_USD_OR_CURRENCY_NOT_VERIFIED"}]})
    held=[]
    monkeypatch.setattr(auto,"_record_hold",lambda *args:held.append(args))
    result=auto.research_batch(now=NOW)
    assert result["candidate_bars"]==0 and result["held"]==1
    assert held[0][1]=="BRK.B"
    assert result["certified"] is False


def test_no_pending_gaps_do_not_call_provider(monkeypatch):
    opt_in(monkeypatch)
    monkeypatch.setattr(auto,"pending_worklist",
                        lambda **kwargs:{"pending":{},
                                         "already_available":1321,
                                         "retry_backoff_symbols":0})
    monkeypatch.setattr(auto,"collect_candidates",
                        lambda *args,**kwargs:(_ for _ in ()).throw(
                            AssertionError("network must not be called")))
    result=auto.research_batch(now=NOW)
    assert result["state"]=="NO_TARGETED_GAPS_PENDING"
    assert result["requested"]==0


@pytest.mark.parametrize("bad",[-1,0,6,1.5,True])
def test_bad_batch_budget_rejected_before_network(bad,monkeypatch):
    opt_in(monkeypatch)
    with pytest.raises(auto.YahooAutoHold):
        auto.research_batch(now=NOW,max_tickers=bad)


def test_hold_on_naive_clock(monkeypatch):
    opt_in(monkeypatch)
    with pytest.raises(auto.YahooAutoHold):
        auto.research_batch(now=datetime(2026,10,14,14))


def test_observation_metadata_is_never_certified(monkeypatch):
    opt_in(monkeypatch)
    candidate={"marketstack_ticker":"AAPL","yahoo_query_symbol":"AAPL",
               "symbol_alias_used":False,
               "bar":{"session":"2026-06-09","open":100.0,"close":100.0},
               "normalized_row_sha256":None}
    with pytest.raises(auto.YahooAutoHold,match="fingerprint"):
        auto._store_candidate("restricted-writer",candidate,NOW)
