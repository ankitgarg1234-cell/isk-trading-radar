"""Bounded free 2022–2023 historical OHLCV probe for GEM research ONLY.

Do not import data into GEMv1 or use for a trade/rank. Vendor differences in
splits, dividends, nominal bars and deleted tickers require independent QA.
No credentials or paid vendors. Exactly one query per listed historical symbol.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, date, timezone
from pathlib import Path

MAX_BYTES = 2_000_000
START = date(2021, 1, 1)
END = date(2024, 1, 1)
SAMPLE = ("SPY", "AAPL", "MSFT", "NVDA", "FISV")
SIGNALS = ("2022-12-30", "2023-06-30", "2023-12-29")


def vendor_url(ticker: str) -> str:
    if ticker not in SAMPLE:
        raise ValueError("Explicit limited symbol sample only; no unbounded scraping")
    return ("https://stooq.com/q/d/l/?" +
            urllib.parse.urlencode({"s": ticker.lower() + ".us", "d1": "20210101",
                                    "d2": "20231231", "i": "d"}))


def parse_vendor_csv(raw: bytes) -> dict[str, dict]:
    try:
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    except UnicodeDecodeError as exc:
        raise ValueError("Vendor daily OHLCV not UTF-8") from exc
    if not rows or not {"Date","Open","High","Low","Close","Volume"}.issubset(rows[0]):
        raise ValueError("Vendor daily OHLCV missing required columns")
    out = {}
    for row in rows:
        try:
            d = date.fromisoformat(row["Date"])
            vals = {k: float(row[k]) for k in ("Open","High","Low","Close","Volume")}
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Malformed daily OHLCV row") from exc
        if (not all(math.isfinite(x) for x in vals.values())
                or min(vals.values()) <= 0
                or vals["Low"] > min(vals["Open"], vals["Close"])
                or vals["High"] < max(vals["Open"], vals["Close"])
                or d.isoformat() in out):
            raise ValueError("Invalid/duplicate daily OHLCV row")
        if START <= d < END:
            out[d.isoformat()] = vals
    return out


def session_coverage(rows: dict[str, dict], expected_sessions: dict[str, list[str]]) -> dict:
    """Only bar DATE coverage. Stooq split/dividend semantics are NOT certified."""
    return {signal: {
        "bars_required": len(sessions),
        "bars_found": sum(s in rows for s in sessions),
        "complete_127_dates": len(sessions) == 127 and all(s in rows for s in sessions),
        "missing": [s for s in sessions if s not in rows],
    } for signal, sessions in expected_sessions.items()}


def run(out_dir: Path, *, get=None, sleep=None) -> dict:
    if out_dir.exists():
        raise FileExistsError("Refusing to overwrite historical research probe")
    out_dir.mkdir(parents=True, exist_ok=False)
    import pandas_market_calendars as mcal
    days = [x.date().isoformat() for x in
            mcal.get_calendar("NYSE").valid_days("2021-01-01","2023-12-31")]
    expected = {}
    for signal in SIGNALS:
        if signal not in days:
            raise ValueError("Expected sample signal not completed NYSE session")
        i = days.index(signal)
        expected[signal] = days[i-126:i+1] if i >= 126 else []
    get = get or urllib.request.urlopen
    sleep = sleep or time.sleep
    report = {}
    for index, sym in enumerate(SAMPLE):
        if index:
            sleep(1.1)  # respect free public source rate limits
        url = vendor_url(sym)
        path = out_dir / f"{sym}-raw.csv"
        entry = {
            "symbol": sym, "uri": url,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "classification": "UNVERIFIED_FREE_PRICE_RESEARCH_NO_GEM_INPUT",
            "adjustment_parity_certified": False,
            "corporate_actions_reconciled": False,
            "original_SEC_facts_available": False,
        }
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0 (compatible; GEM academic price research)"})
            with get(request, timeout=20) as resp:
                raw = resp.read(MAX_BYTES + 1)
            if not raw or len(raw) > MAX_BYTES:
                raise ValueError("Empty/oversized public price response")
            rows = parse_vendor_csv(raw)
            if len(rows) < 127:
                raise ValueError("Insufficient provider bars in full sample window")
            path.write_bytes(raw)
            entry.update({"status": "RECEIVED_UNCERTIFIED", "sha256": hashlib.sha256(raw).hexdigest(),
                          "bytes": len(raw), "daily_bars": len(rows),
                          "asof_session_coverage": session_coverage(rows, expected)})
        except (OSError, ValueError, urllib.error.HTTPError) as exc:
            entry.update({"status": "FAILED_EXPLICIT", "error_type": type(exc).__name__})
        report[sym] = entry
    evidence = {
        "schema": "gem-public-price-sample-research-v1",
        "classification": "READ_ONLY_NO_COMMERCIAL_LICENSE_NOT_PIT_CERTIFICATION",
        "symbols": list(SAMPLE),
        "report": report,
        "paper_execution_authorized": False,
        "frozen_strategy_unchanged": True,
    }
    (out_dir / "price-sample-evidence.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return evidence


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--out-dir",required=True)
    args=parser.parse_args()
    report=run(Path(args.out_dir))
    print(json.dumps({x:{
        "status":v["status"],
        "bars":v.get("daily_bars"),
        "coverage": {k: y["complete_127_dates"] for k,y in
                     v.get("asof_session_coverage",{}).items()},
        "error_type":v.get("error_type")} for x,v in report["report"].items()}))
