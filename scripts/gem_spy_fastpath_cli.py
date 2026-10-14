#!/usr/bin/env python3
"""Operator-only SPY prices+dividend probe; never a GEM benchmark certificate.

Default offline from CSV: session,close,dividend,stock_split.
With --fetch: use yfinance in an operator environment, NOT Render production.
No DB mutation, trade suggestion, or automatic source approval.
"""
import argparse
import csv
from datetime import date
from hashlib import sha256
import json
import sys

from gem_data.gem_spy_total_return_diagnostic import provisional_spy_total_return


def read_csv(path):
    with open(path,encoding="utf-8",newline="") as stream:
        reader=csv.DictReader(stream)
        if not reader.fieldnames or not {"session","close"}.issubset(reader.fieldnames):
            raise ValueError("SPY CSV must have session and unadjusted close")
        rows=[]
        for row in reader:
            rows.append({"session":row["session"],"close":float(row["close"]),
                         "dividend":float(row.get("dividend") or 0),
                         "stock_split":float(row.get("stock_split") or 0)})
            if len(rows)>3000:
                raise ValueError("SPY data exceeds bounded window")
    return rows


def fetch_yfinance(start,end,*,ticker_factory=None):
    if date.fromisoformat(start)>=date.fromisoformat(end):
        raise ValueError("Invalid date interval")
    if ticker_factory is None:
        import yfinance as yf
        ticker_factory=yf.Ticker
    df=ticker_factory("SPY").history(start=start,end=end,
                                     auto_adjust=False,actions=True)
    if df is None or df.empty or not {"Close","Dividends"}.issubset(df.columns):
        raise ValueError("SPY raw close or ex-date dividend data missing")
    rows=[]
    for session,row in df.iterrows():
        rows.append({"session":session.date().isoformat(),
                     "close":float(row["Close"]),
                     "dividend":float(row["Dividends"]),
                     "stock_split":float(row.get("Stock Splits",0)),
                     "vendor_adj_close":float(row.get("Adj Close",row["Close"]))})
    return rows


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    a=p.add_mutually_exclusive_group(required=True)
    a.add_argument("--csv")
    a.add_argument("--fetch",action="store_true")
    p.add_argument("--start")
    p.add_argument("--end")
    args=p.parse_args(argv)
    if args.fetch:
        if not args.start or not args.end:
            raise ValueError("Supply explicit start/end dates for vendor call")
        rows=fetch_yfinance(args.start,args.end)
    else:
        rows=read_csv(args.csv)
    report=provisional_spy_total_return(rows)
    receipt=sha256(json.dumps(rows,sort_keys=True,allow_nan=False).encode()).hexdigest()
    print(json.dumps({"source":"YFINANCE_SECONDARY" if args.fetch else "LOCAL_CSV",
                      "normalized_sha256":receipt,
                      "source_raw_response_verified":False,
                      "result":report},sort_keys=True,allow_nan=False))
    return 0


if __name__=="__main__":
    try:
        sys.exit(main())
    except (ValueError,OSError,ImportError) as exc:
        print("SPY diagnostic HOLD: "+str(exc),file=sys.stderr)
        sys.exit(2)
