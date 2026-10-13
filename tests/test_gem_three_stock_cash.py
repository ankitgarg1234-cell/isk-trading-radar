"""Apr 2025 archived GEM had three selections and 40% strategic cash."""
from decimal import Decimal
from gem_data.gem_manual_ops import manual_trade_sheet
from gem_data.gem_paper_plan import propose_rebalance


def test_three_names_preserve_cash_in_manual_ticket():
    signal={"selected": ["PLTR","UBER","DASH"],"data_status":"REVIEWED_COMPLETE",
            "signal_session":"2025-04-30"}
    plan=manual_trade_sheet(signal,{"cash":"10000","shares":{}},
                            {"PLTR":100,"UBER":100,"DASH":100})
    assert len(plan["tickets"])==3
    assert plan["status"]=="INDICATIVE_USER_REVIEW_REQUIRED"
    assert Decimal(plan["estimated_cash_after"]) >= Decimal("3900")
    assert plan["broker_orders_sent"]==0


def test_three_names_preserve_cash_in_isolated_paper_proposal():
    ranking={"selected":["PLTR","UBER","DASH"],
             "state":"INDEPENDENTLY_CERTIFIED_FOR_PAPER",
             "paper_execution_authorized":True,
             "signal_session":"2025-04-30"}
    proposal=propose_rebalance(ranking,{"cash":10000,"shares":{}},
                               {"PLTR":100,"UBER":100,"DASH":100})
    assert len(proposal["indicative_orders"])==3
    assert proposal["ending_cash"]>=3900
    assert proposal["broker_orders_sent"]==0
