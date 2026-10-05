"""Offline price-forecast diagnostics, not a trading-performance backtest.

Usage: python scripts/evaluate_short_horizon.py --inputs captured.json --output results.json
Inputs may be dashboard bundles or a {"securities": [...]} captured-price pack.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.short_horizon import VERSION, build_forecast


def evaluate(paths):
    inputs, securities = [], []
    for path in paths:
        raw = Path(path).read_bytes()
        data = json.loads(raw)
        inputs.append({"file": Path(path).name, "sha256": hashlib.sha256(raw).hexdigest()})
        for bundle in data.get("securities", [data]):
            forecast = build_forecast(bundle, bundle.get("analysis") or bundle)
            securities.append({"symbol": bundle.get("symbol"), "forecast": forecast})
    return {"version": VERSION, "execution_enabled": False,
            "scope": "Captured-price rolling-origin diagnostics; not a full-universe or point-in-time strategy backtest",
            "inputs": inputs, "securities": securities}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", nargs="+", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = evaluate(args.inputs)
    Path(args.output).write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    for item in result["securities"]:
        forecast = item["forecast"]
        print(item["symbol"], forecast["status"], forecast.get("reason"))
        for row in forecast["rows"]:
            validation = row["validation"]
            print(row["days"], row["base_price"], row["expected_return_pct"],
                  validation["independent_windows"], validation["status"], validation["independent_metrics"])


if __name__ == "__main__":
    main()
