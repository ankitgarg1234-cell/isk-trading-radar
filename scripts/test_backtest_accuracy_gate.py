#!/usr/bin/env python3
"""Deterministic regression tests for PIT inputs and the reconstructed execution engine."""
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch, Mock
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import adaptive_entry_policy_backtest as b
import spy_sector_hierarchy_backtest as h
import reconcile_frozen_baseline as reconciliation


def annual(end, filed, val):
    return {"end":end, "filed":filed, "val":val,
            "start":end[:4]+"-01-01", "form":"10-K"}


def dummy_ind(mom):
    return {"mom":mom,"r63":mom,"r126":mom,"r252":mom,
            "adv63":1e7,"close":100,"atr":2.0,"pct_atr":0.02,"above_ema200":True}


class DataAccuracyTests(unittest.TestCase):
    def test_restatement_cannot_erase_original_historical_filing(self):
        records={"units":{"USD":[
            annual("2020-12-31","2021-02-15",100),
            annual("2021-12-31","2022-02-15",120),
            annual("2021-12-31","2024-02-15",999),
        ]}}
        history=b.annual_records(records)
        historical=b.asof_records(history,date(2022,3,31))
        self.assertEqual(len(historical),2)
        self.assertEqual(historical[-1]["val"],120)
        self.assertTrue(b.fundamental_pass({"rev":history,"gp":[]}, date(2022,3,31),"Financials"))
        later=b.asof_records(history,date(2024,3,31))
        self.assertEqual(later[-1]["val"],999)

    def test_filing_not_allowed_before_publication(self):
        history=b.annual_records({"units":{"USD":[
            annual("2021-12-31","2022-03-30",100),
            annual("2022-12-31","2023-03-30",120),
        ]}})
        self.assertEqual(len(b.asof_records(history,date(2023,3,1))),1)
        self.assertEqual(len(b.asof_records(history,date(2023,4,1))),2)

    def test_global_rank_remains_raw_before_fundamental_pass(self):
        markets={"A":object(),"B":object()}
        pits={"A":{"pass":False},"B":{"pass":True}}
        cmap={"A":"0001","B":"0002"}
        imap={markets["A"]:dummy_ind(1.2),markets["B"]:dummy_ind(0.8)}
        with patch.object(b,"indicators",side_effect=lambda m,d: imap[m]), \
             patch.object(b,"fundamental_pass",side_effect=lambda pit,d,sec: pit["pass"]), \
             patch.object(b,"shares_asof",return_value=100):
            snap,lead=h.signal_snapshot_pit(date(2022,5,31),set(markets),markets,pits,
                 {"A":"Energy","B":"Energy"},cmap)
            self.assertEqual(snap["A"]["rank"],1)
            self.assertEqual(snap["B"]["rank"],2)
            self.assertFalse(snap["A"]["fund"])
            self.assertTrue(snap["B"]["fund"])
            # Raw top-20 positions are NOT renumbered by fundamental eligibility.
            base,_=b.signal_snapshot(date(2022,5,31),set(markets),markets,pits,
                 {"A":"Energy","B":"Energy"},cmap)
            self.assertEqual(base["B"]["rank"],2)

    def test_continuous_ema200_uses_original_200_session_mean(self):
        from datetime import timedelta
        raw=[]
        for i in range(201):
            d=(date(2020,1,1)+timedelta(days=i)).isoformat()
            price=100.0 if i<200 else 200.0
            raw.append({"date":d,"open":price,"high":price,"low":price,
                        "close":price,"volume":1000})
        market=b.prepare_market({"rows":raw,"dividends":[]})
        alpha=2.0/201.0
        self.assertAlmostEqual(market["rows"][199]["ema200_tr"],1.0,places=10)
        self.assertAlmostEqual(market["rows"][200]["ema200_tr"],1.0+alpha,places=10)
        self.assertAlmostEqual(b.ema200_at_index(market["rows"],200),1.0+alpha,places=10)
        self.assertTrue(b.regime(market,date(2020,1,1)+timedelta(days=200)))

    def test_split_adjusted_historical_cap_restores_pre_split_issuer_size(self):
        # June 2024 NVDA 10-for-1 split: historic prices use post-split
        # units, while March 2023 SEC shares used pre-split units.
        shares={"val":2_500_000_000,"end":"2023-03-31"}
        market={"splits_verified":True,"splits":[
             {"date":"2024-06-10","ratio":10.0}]}
        self.assertAlmostEqual(
            b.split_adjusted_market_cap(shares,market,40.0),
            1_000_000_000_000.0)
        self.assertAlmostEqual(
            b.split_adjusted_market_cap(
              {"val":25_000_000_000,"end":"2024-06-30"},market,40.0),
            1_000_000_000_000.0)

    def test_historical_cap_never_assumes_no_splits_when_events_not_verified(self):
        with self.assertRaisesRegex(RuntimeError,"UNVERIFIED_SPLIT_EVENTS"):
            b.split_adjusted_market_cap(
                {"val":2_500_000_000,"end":"2023-03-31"},
                {"splits":None,"splits_verified":False},40.0)

    def test_yahoo_split_events_parsed_and_validated(self):
        action={"events":{"splits":{"e1":{"date":1717977600,
            "numerator":10,"denominator":1,"splitRatio":"10:1"}}}}
        actions=b.parse_chart_splits(action)
        self.assertEqual(len(actions),1)
        self.assertEqual(actions[0]["ratio"],10.0)

    def test_historical_sector_snapshot_changes_by_date(self):
        history=pd.DataFrame([
            {"rebalance_date":"2022-01-01","ticker":"TEST","sector":"Information Technology",
             "revision_timestamp":"2021-12-31T12:00:00Z","sector_source":"wikipedia_pit"},
            {"rebalance_date":"2022-05-01","ticker":"TEST","sector":"Communication Services",
             "revision_timestamp":"2022-04-30T12:00:00Z","sector_source":"wikipedia_pit"}
        ])
        january=h.pit_sector_snapshot(history,date(2022,2,1))
        june=h.pit_sector_snapshot(history,date(2022,6,1))
        self.assertEqual(january["sectors"]["TEST"],"Information Technology")
        self.assertEqual(june["sectors"]["TEST"],"Communication Services")

    def test_future_sector_revision_is_rejected(self):
        hist=pd.DataFrame([{"rebalance_date":"2022-02-01","ticker":"ABC",
            "sector":"Energy","sector_source":"wikipedia_pit",
            "revision_timestamp":"2022-06-01T00:00:00Z"}])
        with self.assertRaisesRegex(RuntimeError,"LOOKAHEAD"):
            h.pit_sector_snapshot(hist,date(2022,3,31))

    def test_fallback_sector_is_not_silently_current_sector(self):
        hist=pd.DataFrame([{"rebalance_date":"2022-02-01","ticker":"ABC",
            "sector":"Energy","sector_source":"fallback",
            "revision_timestamp":"2022-01-25T00:00:00Z"}])
        with self.assertRaisesRegex(RuntimeError,"Missing verified"):
            h.pit_sector_snapshot(hist,date(2022,3,31))

    def test_no_sec_facts_keeps_raw_stock_rank_but_not_entry_permission(self):
        markets={"NOS":object(),"YES":object()}
        imap={markets["NOS"]:dummy_ind(1.5),markets["YES"]:dummy_ind(0.5)}
        pits={"YES":{"pass":True}}
        with patch.object(b,"indicators",side_effect=lambda m,d: imap[m]), \
             patch.object(b,"fundamental_pass",side_effect=lambda pit,d,sec: pit["pass"]), \
             patch.object(b,"shares_asof",return_value=100):
            snap,_=h.signal_snapshot_pit(date(2022,6,30),set(markets),markets,pits,
               {"YES":"Energy","NOS":"Energy"},{"YES":"1","NOS":"2"})
            self.assertEqual(snap["NOS"]["rank"],1)
            self.assertIsNone(snap["NOS"]["fund"])
            self.assertEqual(snap["YES"]["rank"],2)

    def test_reconciliation_rejects_scalar_matching_without_reference_ledger(self):
        reference={
            "name":"PIT frozen-like control",
            "annual_returns_pct":dict(reconciliation.TARGET["annual_returns_pct"]),
            "cagr_5y_convention_pct":reconciliation.TARGET["cagr_5y_convention_pct"],
            "max_drawdown_pct":reconciliation.TARGET["max_drawdown_pct"],
            "trades":[],"daily":[]
        }
        result=reconciliation.assess({"results":[reference]})
        self.assertEqual(result["status"],"BLOCKED")
        self.assertEqual(result["metric_mismatches"],[])
        self.assertIn("ledger unavailable",result["reasons"][0].lower())

    def test_reconciliation_flags_exact_transaction_difference(self):
        actual={
            "name":"PIT frozen-like control",
            "annual_returns_pct":dict(reconciliation.TARGET["annual_returns_pct"]),
            "cagr_5y_convention_pct":reconciliation.TARGET["cagr_5y_convention_pct"],
            "max_drawdown_pct":reconciliation.TARGET["max_drawdown_pct"],
            "trades":[{"date":"2022-01-03","side":"BUY","symbol":"AAA",
                "sleeve":"rot","shares":5,"fill":100.0,"commission":1}],
            "daily":[{"date":"2022-01-03","nav":10000.0,"cash":9500.0,
                "equity_exposure":0.05,"positions":1}]
        }
        expected={"trades":[dict(actual["trades"][0],shares=4)],
                  "daily":[dict(actual["daily"][0])]}
        result=reconciliation.assess({"results":[actual]},expected)
        self.assertEqual(result["status"],"BLOCKED")
        self.assertTrue(result["trade_mismatches"])

    def test_membership_respects_effective_dates(self):
        history=[{"date":"2022-06-01","added":"NEW","removed":"OLD"}]
        current={"NEW","OTHER"}
        self.assertEqual(b.members_at(current,history,date(2022,5,31)),{"OLD","OTHER"})
        self.assertEqual(b.members_at(current,history,date(2022,6,1)),{"NEW","OTHER"})


class AccountingAndExecutionTests(unittest.TestCase):
    def test_execute_at_next_session_open_not_signal_close(self):
        dec=date(2021,12,31)
        first=date(2022,1,3)
        second=date(2022,1,4)
        snap={"AAA":{"mom":0.25,"rank":1,"fund":True,"sector":"Energy",
                     "pct_atr":0.02,"close":100.0,"atr":2.0}}
        prices={"AAA":{"dates":["2022-01-03","2022-01-04"],
                       "rows":[{"date":"2022-01-03","open":100.0,"close":110.0,
                                "atr":2.0,"dividend":0.0},
                               {"date":"2022-01-04","open":109.0,"close":110.0,
                                "atr":2.0,"dividend":0.0}]}}
        snapshots={dec:(snap,[],[],{"rebalance_date":"2021-11-15",
                                   "revision_timestamp":"2021-11-14"})}
        with patch.object(b,"regime",return_value=True):
            result=h.run_variant({"name":"test","mode":"control"},
                [first,second],[dec],snapshots,prices,None)
        buys=[t for t in result["trades"] if t["side"]=="BUY"]
        self.assertEqual(len(buys),1)
        self.assertEqual(buys[0]["date"],"2022-01-03")
        self.assertAlmostEqual(buys[0]["open"],100.0)
        self.assertEqual(buys[0]["shares"],5)
        self.assertGreater(result["daily"][0]["nav"],10000.0)

    def test_unavailable_open_rejects_execution(self):
        m={"dates":["2022-01-04"],
           "rows":[{"date":"2022-01-04","open":100.0}]}
        with self.assertRaisesRegex(RuntimeError,"UNEXECUTABLE_ORDER"):
            h.execution_open({"AAA":m},"AAA",date(2022,1,3))

    def test_missing_monthly_snapshot_creates_exit_in_both_engines(self):
        st=b.State("test",False)
        st.pos[b.key("rot","GHOST")]=b.VPos("rot","GHOST",10,10.0,date(2022,1,3),10,7)
        st.pos[b.key("lead","GHOST2")]=b.VPos("lead","GHOST2",10,10.0,date(2022,1,3),10,7)
        base,_,_=b.retained_or_targets(st,{},[],True)
        candidate,_,_=h.selection_plan(st,{},[],{"Energy"},True,"bear_exception")
        self.assertEqual(set(base),set(st.pos))
        self.assertEqual(set(candidate),set(st.pos))

    def test_missing_price_raises_instead_of_counting_as_zero(self):
        st=b.State("test",False)
        st.pos[b.key("rot","MISSING")]=b.VPos("rot","MISSING",3,100,date(2022,1,3),100,70)
        with self.assertRaisesRegex(RuntimeError,"MISSING_MARKET"):
            b.portfolio_nav(st,{},date(2022,1,4))

    def test_stale_delisted_price_raises_instead_of_marking_to_old_close(self):
        st=b.State("test",False)
        st.pos[b.key("rot","DELIST")]=b.VPos("rot","DELIST",3,100,date(2022,1,3),100,70)
        m={"dates":["2022-01-03"],
           "rows":[{"date":"2022-01-03","close":100.0}]}
        with self.assertRaisesRegex(RuntimeError,"STALE_HELD_PRICE"):
            b.portfolio_nav(st,{"DELIST":m},date(2022,1,17))

    def test_initial_december_signal_is_used_for_first_january_session(self):
        dec=date(2021,12,31)
        first=date(2022,1,3)
        second=date(2022,1,4)
        snapshots={dec:({},[],[],{"revision_timestamp":"2021-12-31","rebalance_date":"2021-11-15"})}
        with patch.object(h,"build_orders",return_value=([],[],[])) as orders, \
             patch.object(b,"regime",return_value=True):
            out=h.run_variant({"name":"test","mode":"control"},
                [first,second],[dec],snapshots,{},None)
            self.assertGreater(out["end_value"],0)
            self.assertEqual(orders.call_args.args[1],dec)
        with self.assertRaisesRegex(RuntimeError,"Missing pre-start"):
            h.run_variant({"name":"test","mode":"control"},
                [first,second],[],{}, {},None)

    def test_bull_exception_leaves_default_control_selection_unchanged(self):
        snap={"A":{"fund":True,"mom":0.5,"rank":1,"sector":"Energy"},
              "B":{"fund":True,"mom":0.4,"rank":2,"sector":"Materials"}}
        st=b.State("test",False)
        frozen=h.selection_plan(st,snap,[],set(h.SECTOR_ETFS),True,"control")
        exception=h.selection_plan(st,snap,[],set(h.SECTOR_ETFS),True,"bear_exception")
        self.assertEqual(frozen,exception)

    def test_occupancy_weight_formula_is_explicit(self):
        snap={"XOM":{"pct_atr":0.02},"CVX":{"pct_atr":0.03}}
        weights=b.target_weights(["XOM","CVX"],0.75,15,snap)
        self.assertAlmostEqual(sum(weights.values()),0.10)


if __name__=="__main__":
    unittest.main(verbosity=2)
