"""Synthetic reference parity and international event/accounting regressions."""
import copy
import math
import unittest
from datetime import date, datetime, timedelta, timezone
from dataclasses import replace

from dual_momentum.rules import PriceBar
from research.historical_engine import FXObservation, FXTape, HistoricalEngine, InputUnavailable, SessionBar, ShareAction
from research.strategy_kernel import load_kernel

UTC = timezone.utc


def instant(day, hour):
    return datetime.combine(day, datetime.min.time(), UTC)+timedelta(hours=hour)


def small_engine(currency="USD", fx=None):
    day = date(2024,1,2)
    dates = [day+timedelta(days=i) for i in range(18)]
    calendar = [(d.isoformat(),instant(d,9),instant(d,16)) for d in dates]
    bars = [PriceBar(d.isoformat(),100.,102.,98.,100.,100.,1000.) for d in dates]
    records = [SessionBar("A","TEST",currency,b,instant(d,9),instant(d,16),instant(d,16),"synthetic") for d,b in zip(dates,bars)]
    engine = HistoricalEngine(records,{"TEST":calendar},[],lambda _:[],[],fx=fx)
    engine.history["A"] = bars[:-1]
    engine.last_record["A"] = records[-2]
    return engine,records[-1]


class ExecutionParity(unittest.TestCase):
    def test_us_fill_quantity_cash_fee_cost_and_initial_stop_match_reference(self):
        engine,r = small_engine()
        oracle = copy.deepcopy(engine.state)
        oracle["pending"] = [{"signal_date":engine.history["A"][-1].date,"fill_after":r.bar.date,
                              "orders":[dict(symbol="A",side="BUY",shares=20,reason="fixture")]}]
        engine._fill(dict(symbol="A",side="BUY",shares=20,reason="fixture"),r)
        load_kernel()["_execute_pending"](oracle,{"A":engine.history["A"]+[r.bar]},r.bar.date)
        self.assertEqual(engine.state["cash"],oracle["cash"])
        self.assertEqual(engine.state["holdings"],oracle["holdings"])
        for field in ("date","symbol","side","shares","price","fee","reason","kind"):
            self.assertEqual(engine.state["trades"][0][field],oracle["trades"][0][field])

    def test_insufficient_cash_and_sell_fee_match_reference(self):
        engine,r = small_engine()
        engine.state["cash"] = 200.
        oracle = copy.deepcopy(engine.state)
        order = dict(symbol="A",side="BUY",shares=20,reason="fixture")
        oracle["pending"] = [{"signal_date":engine.history["A"][-1].date,"fill_after":r.bar.date,"orders":[order]}]
        engine._fill(order,r)
        load_kernel()["_execute_pending"](oracle,{"A":engine.history["A"]+[r.bar]},r.bar.date)
        self.assertEqual(engine.state["holdings"],oracle["holdings"])
        self.assertEqual(engine.state["cash"],oracle["cash"])
        engine._fill(dict(symbol="A",side="SELL",shares=999,reason="exit"),r)
        oracle["pending"] = [{"signal_date":engine.history["A"][-1].date,"fill_after":r.bar.date,
                              "orders":[dict(symbol="A",side="SELL",shares=999,reason="exit")]}]
        load_kernel()["_execute_pending"](oracle,{"A":engine.history["A"]+[r.bar]},r.bar.date)
        self.assertEqual(engine.state["cash"],oracle["cash"])
        self.assertEqual(engine.state["holdings"],oracle["holdings"])

    def test_gap_stop_and_lockout_match_reference(self):
        engine,r = small_engine()
        engine.state["holdings"]["A"] = dict(shares=5,cost=100.,peak=101.,stop=95.,opened="2024-01-02")
        oracle = copy.deepcopy(engine.state)
        r = replace(r,bar=replace(r.bar,open=90.,high=94.,low=88.,close=91.))
        load_kernel()["_stop_check"](oracle,{"A":engine.history["A"]+[r.bar]},r.bar.date)
        engine._completed(r)
        self.assertEqual(engine.state["cash"],oracle["cash"])
        self.assertEqual(engine.state["holdings"],oracle["holdings"])
        self.assertEqual(engine.state["lockouts"],oracle["lockouts"])
        self.assertEqual(engine.state["trades"][0]["price"],89.937)

    def test_close_based_trailing_stop_is_not_peak_based(self):
        engine,r = small_engine()
        engine.state["holdings"]["A"] = dict(shares=1,cost=100.,peak=150.,stop=80.,opened="2024-01-02")
        oracle = copy.deepcopy(engine.state)
        load_kernel()["_stop_check"](oracle,{"A":engine.history["A"]+[r.bar]},r.bar.date)
        engine._completed(r)
        self.assertEqual(engine.state["holdings"],oracle["holdings"])
        self.assertEqual(engine.state["holdings"]["A"]["stop"],86.)

    def test_split_preserves_value_and_stop_distance(self):
        engine,r = small_engine()
        engine.state["holdings"]["A"] = dict(shares=10,cost=100.,peak=110.,stop=86.,opened="2024-01-02")
        action = ShareAction("A",r.open_at,r.open_at-timedelta(days=1),2.,"synthetic verified split")
        engine._action(action)
        h = engine.state["holdings"]["A"]
        self.assertEqual((h["shares"],h["cost"],h["stop"]),(20,50.,43.))
        self.assertEqual(h["shares"]*engine.history["A"][-1].close,1000.)
        r = replace(r,bar=replace(r.bar,open=50.,high=51.,low=49.,close=50.))
        engine._completed(r)
        self.assertIn("A",engine.state["holdings"])
        self.assertEqual(engine.state["trades"],[])
        self.assertEqual(engine.history["A"][-1].total_return_close,100.)

    def test_fractional_action_never_invents_cash_in_lieu(self):
        engine,r = small_engine()
        engine.state["holdings"]["A"] = dict(shares=1,cost=100.,peak=100.,stop=80.,opened="2024-01-02")
        with self.assertRaises(InputUnavailable):
            engine._action(ShareAction("A",r.open_at,r.open_at,0.5,"consolidation"))

    def test_fx_affordability_and_usd_fee(self):
        engine,r = small_engine("EUR",FXTape([FXObservation("EUR",instant(date(2024,1,19),8),instant(date(2024,1,19),8),2.,"synthetic")]))
        engine.state["cash"] = 250.
        engine._fill(dict(symbol="A",side="BUY",shares=2,reason="fixture"),r)
        self.assertEqual(engine.state["holdings"]["A"]["shares"],1)
        self.assertAlmostEqual(engine.state["cash"],250.-100.07*2.-1.)
        self.assertEqual(engine.state["holdings"]["A"]["stop"],86.07)

    def test_future_and_stale_fx_rejected(self):
        t = instant(date(2024,1,19),9)
        fx = FXTape([FXObservation("KRW",t-timedelta(hours=1),t+timedelta(hours=1),.001,"synthetic")])
        with self.assertRaises(InputUnavailable):fx.at("KRW",t)
        fx = FXTape([FXObservation("KRW",t-timedelta(days=6),t-timedelta(days=6),.001,"synthetic")])
        with self.assertRaises(InputUnavailable):fx.at("KRW",t)

    def test_extraordinary_closed_session_rejected(self):
        engine,r = small_engine()
        bad = {"TEST":[x for x in engine.calendars["TEST"] if x[0]!=r.bar.date]}
        with self.assertRaisesRegex(ValueError,"actual exchange session"):
            HistoricalEngine(engine.records,bad,[],lambda _:[],[])

    def test_jumps_not_automatically_repaired(self):
        engine,r = small_engine()
        r = replace(r,bar=replace(r.bar,open=130.,high=133.,low=127.,close=130.,total_return_close=130.))
        engine._completed(r)
        self.assertEqual(engine.history["A"][-1].close,130.)

    def test_preopen_orders_follow_venue_calendar_and_missing_open_expires(self):
        engine,r = small_engine()
        before = r.open_at-timedelta(hours=16)
        engine._queue({"A":1},before,(date(2024,1,18)).isoformat(),"fixture")
        self.assertEqual(engine.state["pending"][0]["orders"][0]["scheduled_at"],r.open_at.isoformat())
        # Explicit calendar has the open, but its price record is absent.
        engine.records = tuple(x for x in engine.records if x!=r)
        engine.history = {}
        engine.run(r.open_at,r.close_at+timedelta(days=1))
        self.assertEqual(engine.state["trades"],[])
        self.assertEqual(engine.state["pending"],[])


class RankingParity(unittest.TestCase):
    def test_known_return_window_and_ema_seed(self):
        k = load_kernel()
        bars = [PriceBar(str(i),100+i,102+i,98+i,100+i,100+i,1.) for i in range(254)]
        s = k["_momentum"](bars)
        self.assertAlmostEqual(s["r63"],353/290-1)
        self.assertAlmostEqual(s["score"],sum(353/(353-n)-1 for n in (63,126,252))/3)
        self.assertTrue(s["above_ema50"] and s["above_ema"])
        self.assertEqual(k["_momentum"](bars[:252]),None)

    def test_retention_lockout_sector_cap_and_quantities(self):
        k = load_kernel()
        stats = {f"S{i}":dict(score=1-i*.01,risk=10-i,r63=.5,above_ema50=True,
                             above_ema=True,close=100.,last="2024-01-10") for i in range(20)}
        members = [dict(symbol=s,sector="Information Technology") for s in stats]
        state = dict(cash=10000.,holdings={"S14":dict(shares=1)},lockouts={"S0":"2024-01-09"})
        sessions = ["2024-01-09","2024-01-10"]
        quantities,weights,selected,ranks = k["_calculate_targets"](state,members,stats,1.,{s:100. for s in stats},sessions,.1)
        self.assertEqual(set(selected),{"S14","S1","S2","S3","S4"})
        self.assertEqual(ranks["S14"],15)
        self.assertAlmostEqual(sum(weights.values()),.5)
        self.assertEqual(sum(quantities.values()),49)  # Integer floors leave additional cash.

    def test_drift_risk_formula_matches_original(self):
        engine,_ = small_engine()
        members = [dict(symbol="A",sector="Information Technology")]
        engine.members_at = lambda _:members
        engine.state["holdings"]["A"] = dict(shares=60,cost=100.,peak=100.,stop=80.,opened="2024-01-02")
        engine.state["cash"] = 4000.
        engine.state["last_signal"] = dict(selected=["A"],equity_cap=1.)
        engine.state["active_cap"] = 1.
        engine._signals = lambda at,m:(dict(A={}),dict(A=100.),.5,{"spy":"BEAR"},.1)
        captured = []
        engine._queue = lambda desired,at,day,reason:captured.append((desired,reason))
        engine._reference_close("2024-01-18",instant(date(2024,1,18),17))
        self.assertEqual(captured,[({"A":14},"EOD_SECTOR_OR_REGIME_RISK")])
        self.assertEqual(engine.state["active_cap"],.5)


if __name__ == "__main__":
    unittest.main()
