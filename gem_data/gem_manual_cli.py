"""Offline GEMv1 monthly manual-investing operator CLI.

Usage:
 python -m gem_data.gem_manual_cli signal --input month.json --out ranked.json
 python -m gem_data.gem_manual_cli gaps --input provider_bars.json --out gap_report.json
 python -m gem_data.gem_manual_cli tickets --input sheet_inputs.json --out sheet.json
 python -m gem_data.gem_manual_cli ledger --input fills_and_statement.json --out account.json
 python -m gem_data.gem_manual_cli history --input claims_and_evidence.json --out audit.json

No broker, API calls, database mutations or unattended market orders. All
outputs are atomic local artifacts. A trading ticket remains user-reviewed.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

from gem_data.gem_manual_ops import manual_trade_sheet, replay_manual_events, ManualLedgerHold
from gem_data.gem_monthly_signal import select_monthly, MonthlySignalHold
from gem_data.gem_source_feature_verifier import recompute_full_month, SourceFeatureHold
from gem_data.market_data_patch import reconcile_prices, PricePatchHold
from gem_data.historical_evidence_audit import audit_historical_claims


def load(path):
    source = Path(path)
    if source.stat().st_size > 25_000_000:
        raise ValueError("Input exceeds offline safety limit")
    item = json.loads(source.read_text(encoding="utf8"))
    if not isinstance(item, dict):
        raise ValueError("Expected a JSON object")
    return item


def atomic_save(path, result):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Never clobber a prior monthly decision or manually reconciled statement.
    if target.exists():
        raise FileExistsError("Audit artifact already exists: " + str(target))
    raw = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".gem-manual-",
                                     suffix=".tmp", mode="w", encoding="utf8",
                                     delete=False) as tmp:
        tmp.write(raw)
        scratch = tmp.name
    try:
        os.link(scratch, target)  # atomic create-if-absent, never overwrite existing audit
    finally:
        if os.path.exists(scratch):
            os.unlink(scratch)


def calculate(command, item):
    if command == "signal":
        return select_monthly(item)
    if command == "verify":
        return recompute_full_month(item)
    if command == "gaps":
        return reconcile_prices(item["ticker"], item["sessions"], item["sources"])
    if command == "tickets":
        return manual_trade_sheet(item["signal"], item["ledger"], item["reference_prices"])
    if command == "ledger":
        return replay_manual_events(item["initial_cash"], item["events"], item.get("statement"))
    if command == "history":
        return audit_historical_claims(item["claims"], item["evidence"])
    raise ValueError("Unknown offline operation")


def main(argv=None):
    parser = argparse.ArgumentParser(description="GEMv1 manual-only offline workbench")
    parser.add_argument("operation", choices=("signal", "verify", "gaps", "tickets", "ledger", "history"))
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = calculate(args.operation, load(args.input))
        atomic_save(args.out, result)
    except (OSError, ValueError, KeyError, TypeError, ManualLedgerHold,
            MonthlySignalHold, SourceFeatureHold, PricePatchHold) as exc:
        print(json.dumps({"operation": args.operation, "status": "HOLD",
                          "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps({"operation": args.operation, "output": str(args.out),
                      "status": result.get("data_status", result.get("status", "REPORT_GENERATED")),
                      "execution": "MANUAL_ONLY_NO_BROKER"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
