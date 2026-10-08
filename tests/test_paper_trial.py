"""Network-free regression tests for the isolated one-month paper trial."""
import unittest
from unittest.mock import patch
from datetime import date, timedelta

from dual_momentum.trial import (
    CAPITAL, SECTOR_CAP, _initial, _next_weekday, _stage,
    _calculate_targets, _ranking_audit, _execute_pending, _stop_check,
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
    def test_ephemeral_sqlite_fails_closed_without_market_download(self):
        from dual_momentum.trial import poll
        with patch("dual_momentum.trial.read_trial",return_value={"state":_initial()}), \
             patch("dual_momentum.trial._write") as save, \
             patch("dual_momentum.trial._poll_impl") as engine_run, \
             patch("dual_momentum.trial.engine") as db_engine:
            db_engine.url.get_backend_name.return_value = "sqlite"
            result=poll()
            self.assertEqual(result["status"],"STORAGE_BLOCKED")
            self.assertFalse(engine_run.called)
            self.assertEqual(save.call_args.args[1],"STORAGE_BLOCKED")

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
        stats={x:{"score":5-i,"risk":5-i,"r63":.40,"above_ema50":True,"above_ema":True,"close":100.0,"last":"2026-10-08"} for i,x in enumerate(["NVDA","MSFT","AAPL","AVGO","AMD"])}
        qty,w,selected,_=_calculate_targets(s,members,stats,1.0,{x:100 for x in stats},spy_r63=.10)
        self.assertEqual(len(selected),5)
        self.assertLessEqual(sum(w.values()),SECTOR_CAP+1e-9)
        self.assertGreater(qty["AAPL"],0)
        self.assertTrue(all(w[s]>0 for s in selected))
        self.assertLessEqual(sum(qty.values()),50)

    def test_read_only_sector_lookup_never_invokes_trading(self):
        from dual_momentum.main import trial_sectors
        fake_members=[{"symbol":"MPC","sector":"Energy"},
                      {"symbol":"HPE","sector":"Information Technology"},
                      {"symbol":"ILMN","sector":"Health Care"}]
        fake_members += [{"symbol":"MOCK"+str(i),"sector":"Industrials"}
                         for i in range(480)]
        with patch("dual_momentum.main.LiveDataSource") as factory, \
             patch("dual_momentum.trial.poll") as paper_engine:
            factory.return_value.current_sp500.return_value=fake_members
            response=trial_sectors()
            self.assertEqual(response["sectors"]["MPC"],"Energy")
            self.assertEqual(response["sectors"]["HPE"],"Information Technology")
            self.assertEqual(response["sectors"]["ILMN"],"Health Care")
            paper_engine.assert_not_called()
            factory.return_value.close.assert_called_once()

    def test_dashboard_shows_sectors_and_missing_audit_not_a_fabricated_rank(self):
        from pathlib import Path
        html=(Path(__file__).resolve().parents[1] /
              "dual_momentum" / "templates" / "trial.html").read_text()
        self.assertIn("Target exposure by sector",html)
        self.assertIn("Audit calculating",html)
        self.assertIn("auditAutoRequested",html)
        self.assertIn("Rebuild ranking explanation",html)
        self.assertIn("sectorFor(k)",html)
        self.assertIn("Eligible buy rank",html)

    def test_ranking_inspection_is_a_separate_endpoint_from_paper_execution(self):
        from dual_momentum.main import app
        routes={(r.path,method) for r in app.routes
                for method in (getattr(r,"methods",None) or set())}
        self.assertIn(("/api/trial/ranking-audit/refresh","POST"),routes)
        self.assertIn(("/api/trial/refresh","POST"),routes)

    def test_ranking_audit_explains_raw_number_one_exclusion_without_trades(self):
        """Raw #1 can be ineligible despite having the highest simple momentum."""
        state=_initial()
        members=[{"symbol":x,"sector":"Information Technology"} for x in ("FAST","LOWVOL","STRONG","THIRD")]
        stats={
            "FAST":{"score":1.0,"risk":0.8,"r63":.35,"above_ema50":False,"above_ema":True,"close":100.,"last":"2026-10-08"},
            "LOWVOL":{"score":0.7,"risk":3.5,"r63":.28,"above_ema50":True,"above_ema":True,"close":100.,"last":"2026-10-08"},
            "STRONG":{"score":0.5,"risk":3.0,"r63":.40,"above_ema50":True,"above_ema":True,"close":100.,"last":"2026-10-08"},
            "THIRD":{"score":0.3,"risk":1.0,"r63":.30,"above_ema50":True,"above_ema":True,"close":100.,"last":"2026-10-08"},
        }
        selected=["LOWVOL","STRONG","THIRD"]
        ranks={"FAST":1,"LOWVOL":2,"STRONG":3,"THIRD":4}
        original_cash=state["cash"]
        report=_ranking_audit(state,members,stats,selected,ranks,.10,
                              decision_date="2026-10-08")
        assert report["raw_top5"][0]=="FAST"
        assert report["eligible_top5"][0]=="LOWVOL"
        indexed={r["symbol"]:r for r in report["rows"]}
        self.assertEqual(indexed["FAST"]["status"],"NOT ELIGIBLE")
        self.assertIn("Below 50-day EMA",indexed["FAST"]["reason"])
        self.assertEqual(indexed["LOWVOL"]["eligible_rank"],1)
        self.assertEqual(indexed["LOWVOL"]["status"],"NEW ENTRY")
        self.assertEqual(state["cash"],original_cash)
        self.assertEqual(state["pending"],[])
        self.assertEqual(state["trades"],[])

    def test_ranking_audit_marks_protected_incumbent_not_eligible_new_entry(self):
        state=_initial()
        state["holdings"]={"EXIST":{"shares":2,"cost":100.,"peak":100.,"stop":80.,"opened":"2026-10-01"}}
        members=[{"symbol":"EXIST","sector":"Industrials"},{"symbol":"NEXT","sector":"Technology"}]
        stats={
            "EXIST":{"score":.40,"risk":.50,"r63":.01,"above_ema50":False,"above_ema":True,"close":100.,"last":"2026-10-08"},
            "NEXT":{"score":.55,"risk":.60,"r63":.30,"above_ema50":True,"above_ema":True,"close":100.,"last":"2026-10-08"},
        }
        report=_ranking_audit(state,members,stats,["NEXT","EXIST"],{"NEXT":1,"EXIST":2},.10,
                              decision_date="2026-10-08")
        by={r["symbol"]:r for r in report["rows"]}
        self.assertEqual(by["EXIST"]["status"],"RETAINED")
        self.assertIsNone(by["EXIST"]["eligible_rank"])
        self.assertEqual(by["NEXT"]["status"],"NEW ENTRY")

    def test_ranking_audit_does_not_modify_existing_target_allocations(self):
        s=_initial()
        members=[{"symbol":x,"sector":"Energy"} for x in ["MPC","VLO","PSX"]]
        stats={x:{"score":5-i,"risk":8-i,"r63":.40,"above_ema50":True,"above_ema":True,
                  "close":100.,"last":"2026-10-08"} for i,x in enumerate(["MPC","VLO","PSX"])}
        marks={sym:100. for sym in stats}
        before=_calculate_targets(s,members,stats,1.0,marks,spy_r63=.10)
        _,_,selected,ranks=before
        _ranking_audit(s,members,stats,selected,ranks,.10,decision_date="2026-10-08")
        after=_calculate_targets(s,members,stats,1.0,marks,spy_r63=.10)
        self.assertEqual(before,after)

    def test_existing_stops_are_not_filled_before_entry(self):
        s=_initial()
        s["holdings"]={"MSFT":{"shares":5,"cost":120.0,"peak":120.0,"stop":110.0,"opened":"2026-10-09"}}
        bs=bars(end=date(2026,10,9))
        # The low is above active stop, so no stop exit.
        _stop_check(s,{"MSFT":bs},"2026-10-09")
        self.assertIn("MSFT",s["holdings"])


if __name__ == "__main__":
    unittest.main()
