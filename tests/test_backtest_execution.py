"""Behavioral checks for dated fills, native share units and PIT publication."""
from copy import deepcopy
from datetime import date, datetime, timezone
import gzip
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import walkforward_backtest as wf
import wf3_offline_valuein as pit


@pytest.fixture(autouse=True)
def clean_db():
    # Replay tests use in-memory account objects and never access application
    # storage. Override the application's database-reset fixture here.
    yield


def analysis(price=100, target=130, stretch=145, stop=90):
    return {
        "symbol": "A", "price": price, "deterministic_score": 82,
        "news": {"label": "Neutral", "material_events": 0, "high_negative_events": 0, "items": []},
        "technicals": {"ema20": price - 2, "rsi": 56, "relative_volume": 1, "change20_pct": 4},
        "levels": {"buy_low": 95, "buy_high": 105, "better_low": 91, "better_high": 94,
                   "stop": stop, "target": target, "do_not_chase": 150, "breakout": 140},
        "risk_reward": (target - price) / (price - stop),
        "target_plan": {"stretch_target": stretch}, "holding_horizon": {"max_days": 90},
        "fundamental_confidence": "high", "decision_confidence": "high",
        "breakdown": {"Fundamentals": 18}, "lane": "CORE_QUALITY", "lane_qualified": True,
    }


def market_rows(rows, **events):
    return {"A": {"rows": [{"date": day, "open": op, "close": close, "high": close, "low": close, "volume": 100}
                            for day, op, close in rows], **events}}


def no_entries(monkeypatch):
    monkeypatch.setattr(wf, "build_optimizer_plan", lambda *args, **kwargs: {"selected_new": [], "visible": []})


def one_entry(monkeypatch, shares=2):
    def plan(candidates, owned, **kwargs):
        return {"selected_new": [] if "A" in owned else [{"symbol": "A", "analysis": candidates["A"],
                 "rank_score": 90, "entry_signal": "BUY"}], "visible": []}
    monkeypatch.setattr(wf, "build_optimizer_plan", plan)
    monkeypatch.setattr(wf, "suggested_position_size", lambda *args, **kwargs: {"shares": shares})


def test_future_open_is_not_used_for_signal_quantity_or_account(monkeypatch):
    market = market_rows([("2026-09-29", 100, 100), ("2026-09-30", 101, 101)])
    calls = []
    one_entry(monkeypatch)
    def size(a, **kwargs):
        calls.append((a["price"], kwargs["cash"]))
        return {"shares": 2}
    monkeypatch.setattr(wf, "suggested_position_size", size)
    st = wf.State("timing", 2, False)
    wf.run_state(st, date(2026, 9, 29), {"A": analysis()}, {"A"}, market)
    assert calls == [(100, 10000)]
    assert st.cash == 10000 and not st.pos and not st.trades
    assert st.curve[-1]["equity"] == 10000
    wf.run_state(st, date(2026, 9, 30), {"A": analysis(101)}, {"A"}, market)
    assert st.pos["A"].shares == 2
    assert st.trades[0]["signal_date"] == "2026-09-29"
    assert st.trades[0]["date"] == "2026-09-30"
    assert st.trades[0]["fill_risk_reward"] == pytest.approx(29/11)
    assert st.trades[0]["risk_amount"] == 22
    assert st.trades[0]["portfolio_equity_at_signal"] == 10000
    curve = pit.daily_curve(st, market, {"rows": [{"date": x} for x in ["2026-09-29", "2026-09-30"]]},
                            date(2026, 9, 29), date(2026, 9, 30))
    assert curve[0]["cash"] == 10000
    assert curve[1]["equity"] == pytest.approx(9999.798)


def test_next_open_rr_failure_cancels_order_instead_of_using_future_sizing(monkeypatch):
    market = market_rows([("2026-09-29", 100, 100), ("2026-09-30", 110, 110)])
    one_entry(monkeypatch)
    st = wf.State("gap", 2, False)
    wf.run_state(st, date(2026, 9, 29), {"A": analysis()}, {"A"}, market)
    wf.advance_state(st, market, date(2026, 9, 30))
    assert st.cash == 10000 and not st.pos and not st.trades
    assert st.rejections[0]["reason"] == "Opening R/R below entry floor"


def test_fill_clips_to_risk_cash_and_fee_ceilings(monkeypatch):
    market = market_rows([("2026-09-29", 100, 100), ("2026-09-30", 101, 101)])
    one_entry(monkeypatch)
    st = wf.State("ceilings", 2, False, cash=505, cost_bps=50)
    def allocate(*args):
        return [{"symbol": "A", "shares": 10, "analysis": analysis(), "reason": "TEST", "risk_budget": 30}]
    wf.run_state(st, date(2026, 9, 29), {"A": analysis()}, {"A"}, market, allocation_policy=allocate)
    wf.advance_state(st, market, date(2026, 9, 30))
    assert st.pos["A"].shares == 2  # floor(30 / 11), not the desired ten.
    assert st.cash == pytest.approx(505 - 202 * 1.005)
    assert st.trades[0]["fee"] == pytest.approx(1.01)


def test_entry_plan_is_frozen_and_base_profit_executes_once(monkeypatch):
    market = market_rows([("2026-09-28", 100, 100), ("2026-09-29", 100, 100),
                          ("2026-09-30", 121, 121), ("2026-10-01", 121, 121), ("2026-10-02", 121, 121)])
    one_entry(monkeypatch, shares=8)
    st = wf.State("harvest", 2, False)
    def allocate(st, day, orders, *args):
        return [{"symbol": "A", "shares": 8, "analysis": analysis(target=120, stretch=135), "reason": "TEST"}]
    wf.run_state(st, date(2026, 9, 28), {"A": analysis(target=120, stretch=135)}, {"A"}, market, allocation_policy=allocate)
    no_entries(monkeypatch)
    for day, price in [(date(2026, 9, 29), 100), (date(2026, 9, 30), 121), (date(2026, 10, 1), 121), (date(2026, 10, 2), 121)]:
        wf.run_state(st, day, {"A": analysis(price, target=150, stretch=180)}, {"A"}, market)
    position = st.pos["A"]
    assert position.entry_target == 120 and position.entry_stretch_target == 135
    assert position.shares == 6 and position.original_shares == 8
    assert position.profit_taken_shares == 2 and position.profit_taken_stages == {"BASE"}
    sells = [trade for trade in st.trades if trade["side"] == "SELL"]
    assert len(sells) == 1 and sells[0]["shares"] == 2
    assert sells[0]["pnl"] == pytest.approx(42 - .242 - .2)


def test_stretch_leap_harvests_half_and_retains_runner(monkeypatch):
    no_entries(monkeypatch)
    market = market_rows([("2026-09-29", 136, 136), ("2026-09-30", 136, 136), ("2026-10-01", 136, 136)])
    st = wf.State("stretch", 2, False)
    st.pos["A"] = wf.Pos(8, 100, date(2026, 9, 1), "CORE_QUALITY", 90,
                         entry_target=120, entry_stretch_target=135, entry_stop=90, entry_horizon_days=90)
    for day in [date(2026, 9, 29), date(2026, 9, 30), date(2026, 10, 1)]:
        wf.run_state(st, day, {"A": analysis(136, target=160)}, {"A"}, market)
    assert st.pos["A"].shares == 4
    assert st.pos["A"].profit_taken_stages == {"BASE", "STRETCH"}
    assert sum(t["side"] == "SELL" for t in st.trades) == 1


def test_profit_gap_does_not_mark_unfilled_stage(monkeypatch):
    no_entries(monkeypatch)
    market = market_rows([("2026-09-29", 121, 121), ("2026-09-30", 99, 99)])
    st = wf.State("profit gap", 2, False)
    st.pos["A"] = wf.Pos(8, 100, date(2026, 9, 1), "CORE_QUALITY", 90,
                         entry_target=120, entry_stretch_target=135, entry_stop=90)
    wf.run_state(st, date(2026, 9, 29), {"A": analysis(121)}, {"A"}, market)
    wf.advance_state(st, market, date(2026, 9, 30))
    assert st.pos["A"].shares == 8 and not st.pos["A"].profit_taken_stages
    assert "net loss" in st.rejections[0]["reason"]


def test_core_stop_crossing_is_thesis_review_and_profit_off_disables_harvest(monkeypatch):
    no_entries(monkeypatch)
    market = market_rows([("2026-09-29", 80, 80), ("2026-09-30", 121, 121), ("2026-10-01", 121, 121)])
    st = wf.State("core thesis", 2, False)
    st.pos["A"] = wf.Pos(8, 100, date(2026, 9, 1), "CORE_QUALITY", 90,
                         entry_target=120, entry_stretch_target=135, entry_stop=90)
    wf.run_state(st, date(2026, 9, 29), {"A": analysis(80, target=130, stop=90)}, {"A"}, market)
    assert not st.pending and not st.trades
    assert st.snap["A"]["action"] == "HOLD — THESIS REVIEW"
    wf.run_state(st, date(2026, 9, 30), {"A": analysis(121)}, {"A"}, market, profit_taking=False)
    assert st.pos["A"].shares == 8 and not st.pending


def test_explosive_expiry_counts_actual_sessions_not_calendar_days(monkeypatch):
    no_entries(monkeypatch)
    rows = []
    day = date(2026, 8, 3)
    from datetime import timedelta
    while len(rows) < 22:
        if day.weekday() < 5:
            rows.append((day.isoformat(), 100, 100))
        day += timedelta(days=1)
    market = market_rows(rows)
    st = wf.State("explosive clock", 2, False)
    st.pos["A"] = wf.Pos(8, 100, date(2026, 8, 3), "EXPLOSIVE", 90,
                         entry_target=130, entry_stretch_target=145, entry_stop=90)
    a = analysis()
    a["lane"] = "EXPLOSIVE"
    wf.run_state(st, date.fromisoformat(rows[19][0]), {"A": a}, {"A"}, market)
    assert not st.pending  # Nineteen sessions have elapsed since entry.
    wf.run_state(st, date.fromisoformat(rows[20][0]), {"A": a}, {"A"}, market)
    assert len(st.pending) == 1 and st.pending[0]["reason"] == "EXPLOSIVE TIME STOP"
    wf.advance_state(st, market, date.fromisoformat(rows[21][0]))
    assert "A" not in st.pos


def test_history_uses_one_split_adjustment_and_native_affordability():
    data = market_rows([("2024-06-07", 12, 12), ("2024-06-10", 12, 12)],
                       splits=[{"date": "2024-06-10", "numerator": 10, "denominator": 1}])["A"]
    assert wf.row_before(data, date(2024, 6, 7))["close"] == 120
    assert wf.hist_asof(data, date(2024, 6, 7))[-1]["close"] == 120
    assert [r["close"] for r in wf.hist_asof(data, date(2024, 6, 10))] == [12, 12]
    assert data["rows"][0]["close"] == 12  # Cache remains untouched.


@pytest.mark.parametrize("symbol,asof,rowdate", [("NVDA", "2024-06-11", "2024-06-07"),
                                                 ("ANET", "2024-12-05", "2024-12-03")])
def test_cached_real_split_boundaries_are_not_adjusted_twice(symbol, asof, rowdate):
    with gzip.open(pit.PRICE_PATH, "rt") as handle:
        data = json.load(handle)["market"][symbol]
    cached = next(row["close"] for row in data["rows"] if row["date"] == rowdate)
    history = wf.hist_asof(data, date.fromisoformat(asof))
    assert next(row["close"] for row in history if row["date"] == rowdate) == pytest.approx(cached)
    assert wf.row_before(data, date.fromisoformat(rowdate))["close"] > cached * 3


@pytest.mark.parametrize("symbol,before,after,ratio", [("NVDA", "2024-06-07", "2024-06-11", 10),
                                                      ("ANET", "2024-12-03", "2024-12-05", 4)])
def test_real_pit_share_count_rolls_forward_known_split_for_market_cap(symbol,before,after,ratio):
    store=pit.PITFundamentals(pit.load_gz(pit.FUND_PATH))
    data=pit.load_gz(pit.PRICE_PATH)["market"][symbol]
    before_day,after_day=date.fromisoformat(before),date.fromisoformat(after)
    pre=store.asof(symbol,before_day,wf.price_asof(data,before_day),splits=data["splits"])
    post=store.asof(symbol,after_day,wf.price_asof(data,after_day),splits=data["splits"])
    assert post["sharesOutstanding"] == pre["sharesOutstanding"]*ratio
    assert post["_shares_split_adjustments"] == pre["_shares_split_adjustments"]+1
    assert .9<post["marketCap"]/pre["marketCap"]<1.1


def test_native_split_dividend_and_cash_in_lieu_tie_to_ledger(monkeypatch):
    no_entries(monkeypatch)
    market = market_rows([("2026-09-28", 60, 60), ("2026-09-29", 60, 60), ("2026-09-30", 60, 60)],
                        splits=[{"date": "2026-09-30", "numerator": 3, "denominator": 2}],
                        dividends=[{"date": "2026-09-29", "amount": 2/3}])
    st = wf.State("corporate", 2, False)
    # Cache uses final shares: native September 28 price is 90, not 60.
    wf.do_buy(st, "A", 3, 90, date(2026, 9, 28), "TEST", "CORE_QUALITY", 90,
              analysis=analysis(90, target=120, stretch=135, stop=80))
    for day, price in [(date(2026, 9, 28), 90), (date(2026, 9, 29), 90), (date(2026, 9, 30), 60)]:
        wf.run_state(st, day, {"A": analysis(price, target=150, stop=price-10)}, {"A"}, market)
    position = st.pos["A"]
    assert position.shares == 4 and position.avg == 60
    assert position.entry_target == 80 and position.original_shares == 4.5
    assert [event["cash"] for event in st.cash_events] == pytest.approx([3, 30])
    assert st.cash == pytest.approx(10000 - 270.27 + 3 + 30)
    curve = pit.daily_curve(st, market, {"rows": [{"date": day} for day in ["2026-09-28", "2026-09-29", "2026-09-30"]]},
                            date(2026, 9, 28), date(2026, 9, 30))
    assert curve[-1]["equity"] == pytest.approx(10002.73)
    wf.advance_state(st, market, date(2026, 9, 30))
    assert len(st.cash_events) == 2


def test_pending_buy_crossing_split_preserves_signal_notional(monkeypatch):
    one_entry(monkeypatch)
    market = market_rows([("2026-09-29", 10, 10), ("2026-09-30", 10, 10)],
                        splits=[{"date": "2026-09-30", "numerator": 10, "denominator": 1}])
    st = wf.State("pending split", 2, False)
    wf.run_state(st, date(2026, 9, 29), {"A": analysis()}, {"A"}, market)
    wf.advance_state(st, market, date(2026, 9, 30))
    assert st.pos["A"].shares == 20 and st.pos["A"].avg == 10
    assert st.pos["A"].entry_target == 13 and st.pos["A"].entry_stop == 9
    assert st.trades[0]["gross"] == 200


def test_last_day_signals_do_not_fill_outside_run_end(monkeypatch):
    one_entry(monkeypatch)
    market = market_rows([("2026-09-30", 100, 100), ("2026-10-01", 100, 100)])
    st = wf.State("end", 2, False)
    wf.run_state(st, date(2026, 9, 30), {"A": analysis()}, {"A"}, market)
    assert len(st.pending) == 1 and not st.trades and st.cash == 10000


def test_pit_gates_close_time_and_missing_timestamp_without_news_leak():
    def fact(value, accepted):
        return {"filing_date": "2026-09-29", "accepted_at": accepted, "accession_id": str(value),
                "standard_concept": "StockholdersEquity", "period_end": "2026-06-30", "numeric_value": value}
    store = pit.PITFundamentals({"facts": {"A": [fact(1, "2026-09-29T19:59:59+00:00"),
                                                   fact(2, "2026-09-29T20:00:01+00:00"), fact(3, None)]}})
    assert [r["numeric_value"] for r in store.eligible("A", "StockholdersEquity", date(2026, 9, 29))] == [1]
    assert len(store.eligible("A", "StockholdersEquity", date(2026, 9, 30))) == 3
    assert store.filing_news("A", date(2026, 9, 29))[0]["providerPublishTime"] == datetime(2026, 9, 29, 19, 59, 59, tzinfo=timezone.utc).timestamp()


def test_pit_winter_close_uses_new_york_dst_offset():
    row = {"filing_date": "2026-01-15", "accepted_at": "2026-01-15T20:30:00+00:00",
           "standard_concept": "StockholdersEquity", "period_end": "2025-12-31", "numeric_value": 1}
    store = pit.PITFundamentals({"facts": {"A": [row]}})
    assert len(store.eligible("A", "StockholdersEquity", date(2026, 1, 15))) == 1


def test_pit_early_close_excludes_after_close_filings_and_news():
    row = {"filing_date": "2024-07-03", "accepted_at": "2024-07-03T18:00:00+00:00",
           "standard_concept": "StockholdersEquity", "period_end": "2024-06-30", "numeric_value": 1}
    store = pit.PITFundamentals({"facts": {"A": [row]}})
    assert wf.market_close_at(date(2024, 7, 3)).hour == 13
    assert store.eligible("A", "StockholdersEquity", date(2024, 7, 3)) == []
    assert store.filing_news("A", date(2024, 7, 3)) == []
    assert len(store.eligible("A", "StockholdersEquity", date(2024, 7, 5))) == 1
