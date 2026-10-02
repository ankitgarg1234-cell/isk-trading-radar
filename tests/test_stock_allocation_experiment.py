from datetime import date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from stock_allocation_experiment import allocation_policy, month_returns
from walkforward_backtest import State


def candidates():
    def row(symbol, rank, stop):
        return ({"symbol": symbol, "rank_score": rank, "entry_signal": "BUY", "analysis": {
            "symbol": symbol, "price": 100, "lane": "CORE_QUALITY", "risk_reward": 2.5,
            "levels": {"stop": stop, "target": 130}}}, "NEW")
    return [row("A", 90, 88), row("B", 80, 95)]


def test_uncapped_risk_allocation_cannot_silently_remove_risk_ceiling():
    st = State("test", 2, False)
    orders = allocation_policy("risk")(st, date(2024, 1, 2), candidates(), {}, {})
    by = {o["symbol"]: o for o in orders}
    assert by["A"]["shares"] == 6
    assert by["B"]["shares"] == 15
    assert sum(o["shares"] * 100.1 for o in orders) <= st.cash
    assert all(o["risk_budget"] == 75 for o in orders)


def test_full_deployment_uses_cash_including_fees_and_conviction_weights():
    st = State("test", 2, False)
    orders = allocation_policy("full")(st, date(2024, 1, 2), candidates(), {}, {})
    by = {o["symbol"]: o for o in orders}
    assert by["A"]["shares"] > by["B"]["shares"]
    spend = sum(o["shares"] * 100.1 for o in orders)
    assert 0 <= st.cash - spend < 100.1
    assert all(o["risk_budget"] is None for o in orders)


def test_full_deployment_with_one_candidate_is_explicitly_concentrated():
    st = State("test", 2, False)
    orders = allocation_policy("full")(st, date(2024, 1, 2), candidates()[:1], {}, {})
    assert orders[0]["shares"] == 99
    assert orders[0]["shares"] * 12 > 75


def test_partial_final_month_is_excluded_from_monthly_target_count():
    result = month_returns([{"date": "2024-01-02", "equity": 10000},
                            {"date": "2024-01-31", "equity": 13000},
                            {"date": "2024-02-29", "equity": 11700},
                            {"date": "2024-03-01", "equity": 12000}])
    assert abs(result["2024-01"]["return_pct"] - 30) < 1e-8
    assert abs(result["2024-02"]["return_pct"] + 10) < 1e-8
    assert result["2024-02"]["complete"] is True
    assert result["2024-03"]["complete"] is False
