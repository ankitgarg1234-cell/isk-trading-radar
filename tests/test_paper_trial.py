"""Network-free regression tests for the isolated one-month paper trial."""
import unittest
from datetime import date, timedelta

from dual_momentum.trial import (
    CAPITAL, SECTOR_CAP, _initial, _next_weekday, _stage,
    _calculate_targets, _execute_pending, _stop_check,
)
from dual_momentum.rules import PriceBar


def bars(symbol="MSFT", days=270, end=date(2026, 10, 9)):
    dates=[]
    d=end
    while len(dates)<days:
        if d.weekday()<5:
            dates.append(d)
        d-=timedelta(days=1)
    dates=dates[::-1]
    return [
        PriceBar(date=d.isoformat(),open=100+i/10,high=101+i/10,
                 low=99+i/10,close=100+i/10,total_return_close=100+i/10,volume=1000000)
        for i,d in enumerate(dates)
    ]


class TestPaperTrial(unittest.TestCase):
    def test_initial_account_is_exactly_ten_thousand(self):
        s=_initial()
        self.assertEqual(s["cash"],CAPITAL)
        self.assertEqual(s["holdings"],{})
        self.assertEqual(s["trades"],[])
        self.assertEqual(s["start"],"2026-10-09")

    def test_friday_signal_targets_next_monday(self):
        self.assertEqual(_next_weekday(date(2026,10,9)),date(2026,10,12))

    def test_order_never_executes_on_signal_date(self):
        s=_initial()
        _stage(s,"2026-10-08",{"MSFT":5},"INITIAL")
        self.assertEqual(s["pending"][0]["fill_after"],"2026-10-09")
        bs=bars(end=date(2026,10,9))
        _execute_pending(s,{"MSFT":bs},"2026-10-08")
        self.assertEqual(s["cash"],CAPITAL)
        self.assertEqual(len(s["trades"]),0)
        _execute_pending(s,{"MSFT":bs},"2026-10-09")
        self.assertEqual(len(s["trades"]),1)
        self.assertEqual(s["trades"][0]["kind"],"MODELED_NEXT_OPEN")
        self.assertGreaterEqual(s["cash"],0)

    def test_sector_cap_leaves_cash_instead_of_backfill(self):
        s=_initial()
        members=[{"symbol":x,"sector":"Information Technology"} for x in ["NVDA","MSFT","AAPL","AVGO","AMD"]]
        stats={x:{"score":5-i,"above_ema":True,"close":100.0,"last":"2026-10-08"} for i,x in enumerate(["NVDA","MSFT","AAPL","AVGO","AMD"])}
        qty,w,selected,_=_calculate_targets(s,members,stats,1.0,{x:100 for x in stats})
        self.assertEqual(len(selected),5)
        self.assertLessEqual(sum(w.values()),SECTOR_CAP+1e-9)
        self.assertEqual(qty["AAPL"],0)
        self.assertEqual(sum(qty.values()),50)

    def test_existing_stops_are_not_filled_before_entry(self):
        s=_initial()
        s["holdings"]={"MSFT":{"shares":5,"cost":120.0,"peak":120.0,"stop":110.0,"opened":"2026-10-09"}}
        bs=bars(end=date(2026,10,9))
        # The low is above active stop, so no stop exit.
        _stop_check(s,{"MSFT":bs},"2026-10-09")
        self.assertIn("MSFT",s["holdings"])


if __name__ == "__main__":
    unittest.main()
