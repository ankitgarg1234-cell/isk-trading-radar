#!/usr/bin/env python3
"""Bounded read-only fast-path report: official NYSE schedule + optional SPY.

No database credentials, vendor paid keys, order execution or deployed code.
One SPY Yahoo Finance historical query is made ONLY with --fetch-spy and
GEM_SOURCE_FASTPATH_ALLOW_YFINANCE=yes. Default runs offline.

Artifact files are diagnostic/uncertified, with hashes and explicit exceptions.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
import sys

from gem_data.gem_nyse_2026_manifest import published_schedule_2026
from gem_data.gem_spy_total_return_diagnostic import provisional_spy_total_return


def produce(*, outdir, fetch_spy=False, signal_day="2026-10-13", ticker_factory=None,
            exchange_calendar=None):
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    if out.is_symlink():
        raise ValueError("Output artifact directory must not be a symlink")
    signal = date.fromisoformat(signal_day)
    if not date(2026,1,2) <= signal <= date(2026,12,31):
        raise ValueError("Signal session out of scheduled 2026")
    if exchange_calendar is None:
        try:
            import exchange_calendars as xc
        except ImportError as exc:
            raise ValueError("Independent XNYS calendar package required") from exc
        exchange_calendar = xc.get_calendar("XNYS")
    xny = [d.strftime("%Y-%m-%d") for d in exchange_calendar.sessions_in_range(
        "2026-01-01", "2026-12-31")]
    nyse = published_schedule_2026(independent_exchange_calendar=xny)
    complete_days = [d["session"] for d in nyse["sessions"]
                     if d["session"] <= signal_day]
    if signal_day not in complete_days:
        raise ValueError("Requested last session is not a scheduled trading day")
    observed = {"schema":"gem-public-quickwins-2026-v1",
                "signal_session":signal_day,
                "nyse_session_count":251,
                "nyse_schedule_crosscheck":"PASS",
                "nyse_published_source":nyse["published_source"],
                "nyse_actual_completed_sessions_verified":False,
                "spy_status":"NOT_FETCHED",
                "spy_source_approved":False,
                "trade_authorized":False}
    (out/"nyse-2026-schedule.json").write_text(
        json.dumps(nyse,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    if fetch_spy:
        if os.environ.get("GEM_SOURCE_FASTPATH_ALLOW_YFINANCE") != "yes":
            raise ValueError("SPY external-source opt-in required")
        from scripts.gem_spy_fastpath_cli import fetch_yfinance
        rows = fetch_yfinance("2026-01-01",(signal+timedelta(days=1)).isoformat(),
                              ticker_factory=ticker_factory)
        expected = [d for d in complete_days if d >= "2026-01-02"]
        data = provisional_spy_total_return(rows,expected_sessions=expected)
        source_sha = sha256(json.dumps(
            rows,sort_keys=True,separators=(",",":"),allow_nan=False
        ).encode()).hexdigest()
        observed.update({
            "spy_status":"VENDOR_OBSERVATION_NOT_SOURCE_CERTIFIED",
            "spy_sessions":len(rows),
            "spy_dividend_events":data["dividend_events"],
            "spy_total_return_provisional":data["total_return"],
            "spy_normalized_price_dividend_sha256":source_sha,
            "spy_source":"YFINANCE_HISTORICAL_CLOSE_AND_DIVIDENDS",
            "spy_original_http_response_sha256_verified":False,
        })
        (out/"spy-provisional-total-return.json").write_text(
            json.dumps(data,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    (out/"source-quickwins-status.json").write_text(
        json.dumps(observed,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    return observed


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--outdir",required=True)
    p.add_argument("--signal-day",default="2026-10-13")
    p.add_argument("--fetch-spy",action="store_true")
    args=p.parse_args(argv)
    print(json.dumps(produce(outdir=args.outdir,fetch_spy=args.fetch_spy,
                             signal_day=args.signal_day),sort_keys=True))
    return 0


if __name__=="__main__":
    try:
        sys.exit(main())
    except (ValueError,ImportError,OSError) as exc:
        print("GEM public quickwins HOLD: "+str(exc),file=sys.stderr)
        sys.exit(2)
