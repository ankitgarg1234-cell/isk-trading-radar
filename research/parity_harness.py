"""Deterministic SYNTHETIC replay parity against original trial orchestration."""
from __future__ import annotations

import ast
import copy
import json
import math
from datetime import date, datetime, timedelta, timezone

from dual_momentum.rules import PriceBar
from research.historical_engine import HistoricalEngine, SessionBar
from research.spgm_sources import DEFAULT_OUTPUT
from research.strategy_kernel import REPO, load_kernel


def original_reference():
    namespace = load_kernel()
    tree = ast.parse((REPO / "dual_momentum/trial.py").read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_stage_decision")
    exec(compile(ast.Module(body=[node],type_ignores=[]),"original_trial_stage_decision","exec"),namespace)
    return namespace


def synthetic_replay_parity():
    days = []
    d = date(2024,1,5)
    while len(days)<260:
        if d.weekday()<5: days.append(d)
        d -= timedelta(days=1)
    days.reverse()
    def at(d,h): return datetime(d.year,d.month,d.day,h,tzinfo=timezone.utc)
    k = original_reference()
    sectors = list(k["ETFS"])
    members = [dict(symbol=f"S{i:03d}",sector=sectors[i%len(sectors)]) for i in range(500)]
    all_symbols = [m["symbol"] for m in members] + list(k["ETFS"].values()) + ["SPY"]
    bars,records = {},[]
    for symbol in all_symbols:
        drift = .001 if symbol=="SPY" else (.002 if symbol in k["ETFS"].values() else .004-int(symbol[1:])*.000005)
        data = []
        for i,day in enumerate(days):
            px = 100*math.exp(drift*i+.003*math.sin(i*.8))
            if symbol=="S000" and i==len(days)-1: px *= .5
            b = PriceBar(day.isoformat(),px*.998,px*1.01,px*.99,px,px,100000.)
            data.append(b)
            records.append(SessionBar(symbol,"FIXTURE","USD",b,at(day,9),at(day,16),at(day,16),"SYNTHETIC_FIXTURE"))
        bars[symbol] = data
    calendar = [(d.isoformat(),at(d,9),at(d,16)) for d in days]
    # Include the next actual opening for terminal/missed-order tests.
    future = date(2024,1,8)
    calendar.append((future.isoformat(),at(future,9),at(future,16)))
    references = [(d.isoformat(),at(d,17)) for d in days]
    decisions = [at(days[-4],17),at(days[-2],17)]
    engine = HistoricalEngine(records,{"FIXTURE":calendar},references,lambda _:members,decisions)
    actual = engine.run(at(days[-4],17),at(days[-1],17))
    oracle = dict(cash=10000.,holdings={},pending=[],trades=[],notes=[],equity=[],lockouts={},last_signal=None)
    valuations, decision_rows = [],[]
    for index in range(len(days)-4,len(days)):
        day = days[index].isoformat()
        cut = {s:bs[:index+1] for s,bs in bars.items()}
        k["_execute_pending"](oracle,cut,day)
        k["_stop_check"](oracle,cut,day)
        marks = {s:bs[-1].close for s,bs in cut.items()}
        nav = k["_positions_value"](oracle,marks)
        valuations.append((nav,oracle["cash"],{s:h["shares"] for s,h in oracle["holdings"].items()}))
        if index==len(days)-1: continue
        if at(days[index],17) in decisions:
            k["_stage_decision"](oracle,members,cut,day,"MONTH_END")
            decision_rows.append(copy.deepcopy(oracle["last_signal"]))
        else:
            k["_daily_risk_check"](oracle,members,cut,day)
    comparisons = []
    def check(name, passed):
        comparisons.append({"check":name,"passed":bool(passed)})
    check("daily NAV/cash/share quantities",all(math.isclose(row['nav'],value[0],abs_tol=1e-8)
         and math.isclose(row['cash'],value[1],abs_tol=1e-8) and row['shares']==value[2]
         for row,value in zip(engine.valuations,valuations)) and len(engine.valuations)==len(valuations))
    check("final cash, holdings cost/peak/stops",math.isclose(actual['cash'],oracle['cash'],abs_tol=1e-8) and actual['holdings']==oracle['holdings'])
    check("selected stocks, weights, raw ranks, targets",all(a['selected']==b['selected'] and a['weights']==b['weights']
          and {s:a['raw_ranks'][s] for s in a['selected']}==b['raw_ranks'] and a['targets']==b['targets']
          for a,b in zip(engine.audit,decision_rows)) and len(engine.audit)==len(decision_rows))
    fields = ('date','symbol','side','shares','price','fee','reason','kind')
    check("entry/exit dates, fills, fees, stop events",[{k:t[k] for k in fields} for t in actual['trades']]==[{k:t[k] for k in fields} for t in oracle['trades']])
    check("post-stop lockouts",actual['lockouts']==oracle['lockouts'] and bool(actual['lockouts']))
    check("sector regimes and exposure caps",actual['last_regime']==oracle['last_regime'] and actual['active_cap']==oracle['active_cap'])
    if not all(r['passed'] for r in comparisons):
        raise AssertionError(json.dumps(comparisons))
    return engine,{"data_kind":"SYNTHETIC_FIXTURE","comparisons":comparisons,
                   "historical_performance_parity_established":False,
                   "stock_signals":500,"reference_etfs":12,"replay_sessions":4,
                   "decision_events":2,"stop_events":sum(t['kind']=='MODELED_STOP' for t in actual['trades'])}


def main():
    engine,result = synthetic_replay_parity()
    out = DEFAULT_OUTPUT / "historical_backtest" / "synthetic_parity"
    engine.save(out,data_kind="SYNTHETIC_FIXTURE")
    (out/"parity.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result))


if __name__ == "__main__":main()
