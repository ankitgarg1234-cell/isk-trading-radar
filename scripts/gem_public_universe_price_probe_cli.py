#!/usr/bin/env python3
"""One-shot public Yahoo alternative 503-stock diagnostic (NOT broker eligible).

Only --run with explicit GEM_PUBLIC_UNIVERSE_ALLOW_YFINANCE=yes initiates
source GETs; the CI job is a separately contained review environment.
No database credentials or broker secrets. Research-only historical screen.
"""
import argparse
import json
import os
from pathlib import Path
import sys

from gem_data.gem_public_universe_price_probe import probe_universe


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run",action="store_true")
    p.add_argument("--limit",type=int,default=40)
    p.add_argument("--batch-size",type=int,default=40)
    p.add_argument("--outdir",required=True)
    args=p.parse_args(argv)
    if not args.run or os.environ.get("GEM_PUBLIC_UNIVERSE_ALLOW_YFINANCE")!="yes":
        raise ValueError("Explicit operator diagnostic opt-in required")
    result=probe_universe(max_symbols=args.limit,batch_size=args.batch_size)
    out=Path(args.outdir)
    if out.is_symlink():
        raise ValueError("Output must not be symlink")
    out.mkdir(parents=True,exist_ok=True)
    (out/"universe-public-price-momentum-provisional.json").write_text(
        json.dumps(result,sort_keys=True,indent=2,allow_nan=False)+"\n",
        encoding="utf-8")
    summary={key:result[key] for key in (
        "current_membership_count","current_issuer_count",
        "membership_matches_stored_oct13","symbols_attempted",
        "status_counts","full_history_observed",
        "positive_momentum_observed_not_certified",
        "price_liquidity_plus_momentum_observed_not_certified",
        "verified_eligible_competitor_set",
        "source_certified","trading_authorized","report_sha256")}
    print(json.dumps(summary,sort_keys=True))
    return 0


if __name__=="__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, ImportError) as exc:
        print("GEM alternate price triage HOLD: "+str(exc),file=sys.stderr)
        sys.exit(2)
