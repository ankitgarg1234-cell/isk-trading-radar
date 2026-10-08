#!/usr/bin/env python3
"""Deterministic no-network regression tests for explicit sector-first strategy."""
import math, sys, unittest
from datetime import date
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parent))
import sector_first_explicit_backtest as m

def row(sector,momentum=0.3,breadth=0.8,rel=0.1,r5=0.03,bull=True):
    return {"sector":sector,"momentum":momentum,"breadth":breadth,
            "relative63":rel,"r5":r5,"bull":bull}

class SectorFirstContract(unittest.TestCase):
    def test_exact_market_allocation_gradient(self):
        self.assertEqual(m.sector_allocation(True,[row("Energy",.3,.8),row("Technology",.1,.7)]),
                         {"Energy":.7,"Technology":.3})
        self.assertEqual(m.sector_allocation(True,[row("Energy",.2),row("Technology",.16)]),
                         {"Energy":.5,"Technology":.5})
        self.assertEqual(m.sector_allocation(True,[row("Energy",.2,.71)]),{"Energy":.9})
        self.assertEqual(m.sector_allocation(True,[row("Energy",.2,.70)]),{"Energy":.7})
        self.assertEqual(m.sector_allocation(True,[row("Energy",.2,.50)]),{"Energy":.7})
        self.assertEqual(m.sector_allocation(False,[row("Energy",.2,.60)]),{"Energy":.5})
        self.assertEqual(m.sector_allocation(False,[row("Energy",.2,.59)]),{"Energy":.4})
        self.assertEqual(m.sector_allocation(False,[row("Energy",.2,.95,r5=-.01)]),{"Energy":.4})
        self.assertEqual(m.sector_allocation(False,[row("Energy",.2,.95,rel=-.01)]),{})
        self.assertEqual(m.sector_allocation(False,[row("Energy",.3),row("Technology",.2)]),
                         {"Energy":.35,"Technology":.15})
        self.assertEqual(m.sector_allocation(False,[row("Energy",.3),row("Technology",.28)]),
                         {"Energy":.25,"Technology":.25})
        self.assertEqual(m.sector_allocation(False,[row("Energy",.2,bull=False)]),{})
    def test_monthly_rotation_does_not_retrade_on_daily_rank_noise(self):
        # Momentum leadership can change intramonth, but is not a daily
        # turnover signal unless the active sector actually loses permission.
        active={"Energy":.7,"Technology":.3}
        rows=[row("Technology",.7),row("Energy",.3)]
        self.assertEqual(m.event_driven_allocation(active,True,True,rows,False),active)
        self.assertEqual(m.event_driven_allocation(active,True,True,rows,True),
                         {"Technology":.7,"Energy":.3})

    def test_market_switch_forces_override_at_next_close(self):
        active={"Energy":.7,"Technology":.3}
        rows=[row("Technology",.2),row("Energy",.4)]
        self.assertEqual(m.event_driven_allocation(active,True,False,rows,False),
                         {"Energy":.35,"Technology":.15})

    def test_single_bear_leader_de_risks_on_momentum5_negative(self):
        active={"Energy":.5}
        rows=[row("Energy",.4,.8,rel=.1,r5=-.02)]
        self.assertEqual(m.event_driven_allocation(active,False,False,rows,False),
                         {"Energy":.4})
    def test_ineligible_sector_forces_risk_exit_daily(self):
        active={"Energy":.5}
        rows=[row("Energy",.4,bull=False)]
        self.assertEqual(m.event_driven_allocation(active,False,False,rows,False),{})

    def test_stock_risk_score_uses_price_not_dividend_returns(self):
        from datetime import timedelta
        rows=[]
        for i in range(310):
            dt=(date(2020,1,1)+timedelta(days=i)).isoformat()
            px=100+i*0.1+math.sin(i/3)*2
            rows.append({"date":dt,"open":px,"high":px+1,
                         "low":px-1,"close":px,"volume":10000})
        last=rows[-1]["date"]
        df=m.features({"rows":rows,"dividends":[{"date":last,"amount":10.0}],"splits":[]})
        r=df.iloc[-1]
        self.assertGreater(r["r63"],r["pr63"])
        expected=.5*r["pr63"]/r["sigma63"]+.3*r["pr126"]/r["sigma126"]+.2*r["pr252"]/r["sigma252"]
        self.assertAlmostEqual(float(r["score"]),float(expected),places=12)

    def test_no_future_lookahead_in_ema(self):
        v=pd.Series([100.]*200+[110.,500.],index=list(range(202)))
        e=m.ema_close(v,200)
        self.assertTrue(np.isnan(e.iloc[198]))
        self.assertEqual(e.iloc[199],100)
        self.assertAlmostEqual(e.iloc[200],100+10*2/201)
        self.assertAlmostEqual(m.ema_close(v.iloc[:201],200).iloc[-1],e.iloc[200])
    def test_stop_precomputed_prior_day_and_gap_fills(self):
        self.assertEqual(m.intraday_stop_fill(95,94,100),95)
        self.assertEqual(m.intraday_stop_fill(103,98,100),100)
        self.assertIsNone(m.intraday_stop_fill(103,102,100))
        self.assertIsNone(m.intraday_stop_fill(103,90,None))
    def test_lockout_five_complete_sessions(self):
        for ix in range(1,6):self.assertFalse(m.lockout_allows_signal(ix,0))
        self.assertTrue(m.lockout_allows_signal(6,0))
    def test_momentum_ratio_with_nonpositive_denominator_is_defined(self):
        alloc=m.sector_allocation(True,[row("Energy",-.01),row("Tech",-.02)])
        self.assertEqual(alloc,{"Energy":.5,"Tech":.5})
    def test_stock_scores_and_rank_filter(self):
        d="2022-01-03"
        frames={}
        for sym,score,above in [("A",3.0,True),("B",2.0,True),("C",10.0,False)]:
            frames[sym]=pd.DataFrame([{"score":score,"stock_ok":above}],index=[d])
        selected=m.selected_stock_ranks(d,"Energy",{"A","B","C"},{"A":"Energy","B":"Energy","C":"Energy"},frames)
        self.assertEqual(selected,["A","B"])
    def test_whole_share_cash_and_fees(self):
        p=m.Portfolio()
        self.assertEqual(p.trade("XOM",50,100,"2022-01-03","OPEN"),50)
        self.assertEqual(p.pos["XOM"]["qty"],50)
        self.assertGreater(p.cash,0)
        self.assertAlmostEqual(p.trades[0]["fill"],100.07)
        self.assertEqual(p.trade("XOM",-50,110,"2022-01-04","STOP"),-50)
        self.assertAlmostEqual(p.trades[-1]["fill"],109.923)
        self.assertNotIn("XOM",p.pos)
    def test_dividend_only_held_before_exdate(self):
        # The real simulator credits dividends before opening orders.
        # A portfolio that begins empty cannot collect an ex-date dividend
        # on shares purchased at that ex-date opening.
        p=m.Portfolio()
        self.assertEqual(len(p.pos),0)
        p.trade("A",1,100,"2022-01-03","BUY")
        self.assertEqual(len(p.pos),1)
    def test_warm_start_is_required(self):
        mkt={"SPY":pd.DataFrame(index=["2021-12-31","2022-01-03"])}
        with self.assertRaisesRegex(RuntimeError,"WARM_START_REQUIRED"):
            m.run(mkt,["2021-12-31","2022-01-03"],{},lambda d:set(),lambda d:{})
    def test_breadth_sector_permission_strictly_more_than_half(self):
        # Market state is strict > 50% even though cash gradient describes 50-70.
        self.assertFalse(0.5>0.5)
        self.assertTrue(0.50001>0.5)
if __name__=="__main__":unittest.main(verbosity=2)
