#!/usr/bin/env python3
"""Reconstruct lane-qualified observations from a frozen allocation result.

This diagnostic leaves the experiment and its entry rules unchanged. The
implied entry price holds the recorded stop and target fixed; it is not a new
trade recommendation or a prediction of a later recalculated plan.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path

from stock_allocation_experiment import ROOT, digest
import wf3_offline_valuein as data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("output")
    args = parser.parse_args()
    result = json.loads(Path(args.input).read_text())
    source = result["protocol"]["source"]
    for name, expected in source["source_sha256"].items():
        if digest(ROOT / name) != expected:
            raise ValueError(f"Frozen source differs: {name}")
    for path, key in [(data.PRICE_PATH, "price_sha256"), (data.FUND_PATH, "fundamentals_sha256")]:
        if digest(path) != source[key]:
            raise ValueError(f"Frozen data differs: {path.name}")
    prices = data.load_gz(data.PRICE_PATH)
    store = data.PITFundamentals(data.load_gz(data.FUND_PATH))
    observations = []
    for daily in result["daily_pipeline"]:
        if not daily["lane"]:
            continue
        day = date.fromisoformat(daily["date"])
        members = set(prices["membership"]["start_members"])
        for change in sorted(prices["membership"]["changes"], key=lambda r: r["date"]):
            if change["date"] > daily["date"]:
                break
            if change.get("removed"):
                members.discard(change["removed"])
            if change.get("added"):
                members.add(change["added"])
        found = 0
        for symbol in sorted(members):
            a = data.analyse(symbol, day, prices["market"], store,
                             prices["membership"]["sectors"], prices["sector_etfs"])
            if not a or not a.get("lane_qualified"):
                continue
            found += 1
            price = float(a["price"])
            stop, target = (float(a["levels"][k]) for k in ["stop", "target"])
            threshold = (target + 2 * stop) / 3
            observations.append({"date": daily["date"], "symbol": symbol, "lane": a["lane"],
                                 "price": price, "stop": stop, "target": target,
                                 "risk_reward": a["risk_reward"],
                                 "risk_reward_unrounded": (target - price) / (price - stop),
                                 "fixed_plan_max_entry_for_2x": round(threshold, 4),
                                 "fixed_plan_required_pullback_pct": round((1 - threshold / price) * 100, 4),
                                 "target_plan": a["target_plan"], "breakdown": a["breakdown"],
                                 "analyst_opinion_count": a.get("analyst_opinion_count"),
                                 "fundamental_confidence": a.get("fundamental_confidence")})
        if found != daily["lane"]:
            raise AssertionError(f"Lane reconstruction differs on {day}: {found} vs {daily['lane']}")
    if len(observations) != result["diagnostics"]["lane_observations"]:
        raise AssertionError("Lane observation total differs")
    output = {"result_hash": result["deterministic_hash"], "observations": observations,
              "interpretation": "Recorded fixed-plan entry thresholds are diagnostics only; a later price requires a fresh plan and eligibility check."}
    Path(args.output).write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps({"observations": len(observations), "unique_symbols": sorted({r["symbol"] for r in observations}),
                      "max_rr": max((r["risk_reward"] for r in observations), default=None),
                      "min_rr": min((r["risk_reward"] for r in observations), default=None),
                      "examples": observations[-3:]}, indent=2))


if __name__ == "__main__":
    main()
