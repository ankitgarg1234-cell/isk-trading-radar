"""Audit whether the cached replay can honestly test the mandatory analyst gate."""
import argparse
import gzip
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.score_band_experiment import experiment_spec


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=str(ROOT / "backtests/results/score_bands_data_audit.json"))
    args = p.parse_args()
    with gzip.open(ROOT / "backtests/staged/wf3_prices.json.gz", "rt") as f:
        prices = json.load(f)
    with gzip.open(ROOT / "backtests/staged/wf3_valuein_fundamentals.json.gz", "rt") as f:
        fundamentals = json.load(f)
    # These caches contain price bars and SEC reported facts. There is no dated
    # consensus archive. Today's analyst targets must never be backfilled.
    archive = fundamentals.get("analyst_history") or prices.get("analyst_history")
    report = {"strategy": experiment_spec(), "period": prices.get("period"),
        "price_symbols": len(prices.get("market") or {}),
        "sec_symbols": len(fundamentals.get("facts") or {}),
        "dated_analyst_archive_present": bool(archive),
        "historical_complete_strategy_return": None,
        "status": "requires_dated_analyst_validation" if archive else "blocked_missing_analyst_archive",
        "next_step": "Capture actual analyst inputs, exchange quote times and decisions in the isolated live paper account.",
        "non_negotiable": "Missing analyst data fails qualification; no present-day backfill or relaxed gate."}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k:v for k,v in report.items() if k!="strategy"}, indent=2))


if __name__ == "__main__":
    main()
