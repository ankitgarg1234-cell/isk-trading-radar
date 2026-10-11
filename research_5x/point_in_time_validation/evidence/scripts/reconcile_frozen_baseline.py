#!/usr/bin/env python3
"""Fail-closed reconciliation against the original frozen 75/25 trading ledger.

A public-data approximation cannot be certified from scalar annual returns alone.
Usage:
 python scripts/reconcile_frozen_baseline.py \
    --candidate backtests/results/spy_sector_hierarchy_2022_2026.json \
    --reference /path/to/original_frozen_trade_ledger.json \
    --report backtests/results/frozen_reconciliation.json --strict
"""
import argparse
import json
import math
import sys
from pathlib import Path

TARGET={
 "annual_returns_pct":{
  "2022":-17.25,"2023":2.91,"2024":50.52,"2025":13.05,"2026":39.57
 },
 "cagr_5y_convention_pct":14.66,
 "max_drawdown_pct":-33.85
}
TRADE_COLUMNS=("date","side","symbol","sleeve","shares","fill","commission")
NAV_COLUMNS=("date","nav","cash","equity_exposure","positions")
PERCENT_TOLERANCE=0.02
AMOUNT_TOLERANCE=0.02
SHARES_TOLERANCE=0


def select_control(candidate):
    controls=[r for r in candidate.get("results",[]) if r.get("name")=="PIT frozen-like control"]
    if len(controls)!=1:
        raise ValueError(f"Expected exactly one PIT frozen-like control, found {len(controls)}")
    return controls[0]


def diff_metrics(actual, expected):
    mismatches=[]
    for key in ("cagr_5y_convention_pct","max_drawdown_pct"):
        a=actual.get(key); ref=expected.get(key)
        if not isinstance(a,(int,float)) or abs(a-ref)>PERCENT_TOLERANCE:
            mismatches.append({"field":key,"expected":ref,"actual":a})
    for year,ref in expected["annual_returns_pct"].items():
        a=actual.get("annual_returns_pct",{}).get(year)
        if not isinstance(a,(int,float)) or abs(a-ref)>PERCENT_TOLERANCE:
            mismatches.append({"field":f"annual_returns_pct.{year}","expected":ref,"actual":a})
    return mismatches


def reconcile_rows(actual,reference,columns,kind):
    mismatches=[]
    if not isinstance(actual,list) or not isinstance(reference,list):
        return [{"type":f"{kind}_missing_list"}]
    if len(actual)!=len(reference):
        mismatches.append({"type":f"{kind}_row_count","actual":len(actual),"reference":len(reference)})
    for n,(a,ref) in enumerate(zip(actual,reference),start=1):
        for c in columns:
            if c not in a or c not in ref:
                mismatches.append({"type":f"{kind}_missing_field","row":n,"field":c})
                continue
            av=a[c];rv=ref[c]
            if c in ("nav","cash","fill","commission"):
                try: equal=abs(float(av)-float(rv))<=AMOUNT_TOLERANCE
                except (ValueError,TypeError): equal=False
            elif c=="equity_exposure":
                try: equal=abs(float(av)-float(rv))<=0.0001
                except (ValueError,TypeError): equal=False
            else: equal=av==rv
            if not equal:
                mismatches.append({"type":f"{kind}_field_mismatch","row":n,
                                   "field":c,"actual":av,"reference":rv})
            if len(mismatches)>=100:
                return mismatches
    return mismatches


def assess(candidate,reference=None):
    control=select_control(candidate)
    metric_mismatches=diff_metrics(control,TARGET)
    reasons=[]
    trade_mismatches=[]
    nav_mismatches=[]
    if metric_mismatches:
        reasons.append("Control does not reproduce authoritative frozen annual/CAGR/drawdown metrics")
    if reference is None:
        reasons.append("Original frozen trade/daily-NAV ledger unavailable; transaction reconciliation BLOCKED")
    else:
        if not isinstance(reference.get("trades"),list) or not isinstance(reference.get("daily"),list):
            reasons.append("Original reference must contain trades[] and daily[] to certify")
        else:
            trade_mismatches=reconcile_rows(control.get("trades"),reference["trades"],TRADE_COLUMNS,"trade")
            nav_mismatches=reconcile_rows(control.get("daily"),reference["daily"],NAV_COLUMNS,"daily")
            if trade_mismatches: reasons.append("Transaction-level reconciliation mismatches")
            if nav_mismatches: reasons.append("Daily-NAV and cash reconciliation mismatches")
    return {
      "status":"PASS" if not reasons else "BLOCKED",
      "baseline_expected":TARGET,
      "control_name":control.get("name"),
      "control_actual":{k:control.get(k) for k in (
          "annual_returns_pct","cagr_5y_convention_pct","max_drawdown_pct",
          "end_value","avg_equity_exposure_pct","trade_count","costs")},
      "metric_mismatches":metric_mismatches,
      "trade_mismatches":trade_mismatches[:100],
      "daily_mismatches":nav_mismatches[:100],
      "reasons":reasons,
      "note":"Only a full original frozen trade/NAV ledger with matching assumptions can remove the BLOCKED status."
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--candidate",type=Path,required=True)
    p.add_argument("--reference",type=Path)
    p.add_argument("--report",type=Path)
    p.add_argument("--strict",action="store_true")
    args=p.parse_args(argv)
    if not args.candidate.is_file():
        print(f"BLOCKED: missing reconstructed control result {args.candidate}",file=sys.stderr)
        return 2 if args.strict else 0
    candidate=json.loads(args.candidate.read_text())
    reference=json.loads(args.reference.read_text()) if args.reference and args.reference.is_file() else None
    result=assess(candidate,reference)
    payload=json.dumps(result,indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(payload+"\n")
    print(payload)
    return 0 if result["status"]=="PASS" or not args.strict else 2

if __name__=="__main__":
    sys.exit(main())
