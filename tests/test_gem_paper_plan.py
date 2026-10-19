import pytest
from gem_data.gem_paper_plan import propose_rebalance, PaperHold


def ranking():
    return {"state":"INDEPENDENTLY_CERTIFIED_FOR_PAPER",
            "paper_execution_authorized":True,
            "signal_session":"2026-09-30",
            "selected":["A","B","C","D","E"]}


def test_initial_equal_weight_whole_share_plan():
    r=propose_rebalance(ranking(),{"cash":10000,"shares":{}},
                        {x:100 for x in "ABCDE"})
    assert len(r["indicative_orders"]) == 5
    assert set(r["ending_shares"]) == set("ABCDE")
    assert r["ending_cash"] >= 0
    assert r["execution"] == "DISABLED"
    assert r["broker_orders_sent"] == 0


def test_sells_old_holding_before_buying():
    r=propose_rebalance(ranking(),{"cash":0,"shares":{"Z":100}},
                        {x:100 for x in "ABCDEZ"})
    assert r["indicative_orders"][0]["side"] == "SELL"
    assert r["indicative_orders"][0]["ticker"] == "Z"
    assert "Z" not in r["ending_shares"]


def test_uncertified_ranking_holds():
    x=ranking()
    x["paper_execution_authorized"]=False
    with pytest.raises(PaperHold):
        propose_rebalance(x,{"cash":10000,"shares":{}},{k:100 for k in "ABCDE"})


def test_missing_price_holds():
    with pytest.raises(PaperHold):
        propose_rebalance(ranking(),{"cash":10000,"shares":{}},{"A":100})
