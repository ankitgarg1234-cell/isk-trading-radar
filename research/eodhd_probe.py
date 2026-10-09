#!/usr/bin/env python3
"""Conservative EODHD free-tier coverage probe; NOT an index backtest.

Python standard library only. By default this script is DRY-RUN and uses zero
API calls. Use --execute after configuring the EODHD_API_TOKEN secret.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
from datetime import date, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "research" / "eodhd_sample_symbols.csv"
DEFAULT_OUT = ROOT / "research" / "eodhd_output"
FIELDS = ("date", "open", "high", "low", "close", "adjusted_close", "volume")


def read_symbols(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    symbols = []
    for row in rows:
        symbol = (row.get("eodhd_ticker") or "").strip()
        if symbol:
            if "/" in symbol or "?" in symbol or " " in symbol:
                raise ValueError("Invalid ticker in sample manifest")
            if symbol not in symbols:
                symbols.append(symbol)
    if not symbols:
        raise ValueError("No symbols in manifest")
    return symbols


def validate_prices(payload: object) -> list[dict]:
    """Reject malformed, duplicate or unsorted prices instead of silently filling."""
    if not isinstance(payload, list) or not payload:
        raise ValueError("No price rows returned")
    records, seen = [], set()
    for row in payload:
        if not isinstance(row, dict):
            raise ValueError("Price payload must contain objects")
        day = str(row.get("date", ""))
        try:
            if date.fromisoformat(day).isoformat() != day:
                raise ValueError()
        except ValueError as exc:
            raise ValueError("Malformed session date") from exc
        if day in seen:
            raise ValueError("Duplicate daily session")
        seen.add(day)
        for field in FIELDS[1:]:
            value = row.get(field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"Missing/nonfinite {field} for {day}")
        if min(float(row[k]) for k in ("open", "high", "low", "close", "adjusted_close")) <= 0:
            raise ValueError("Nonpositive stock price")
        if float(row["volume"]) < 0:
            raise ValueError("Negative volume")
        if not float(row["volume"]).is_integer():
            raise ValueError("Fractional stock volume")
        if not (row["low"] <= min(row["open"], row["close"])
                <= max(row["open"], row["close"]) <= row["high"]):
            raise ValueError("Inconsistent OHLC range")
        records.append({field: row[field] for field in FIELDS})
    if [r["date"] for r in records] != sorted(seen):
        raise ValueError("Prices not in ascending session order")
    return records


def claim_call(ledger_path: Path, today: str, cap: int) -> None:
    """Reserve one request BEFORE sending it, including requests that fail."""
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {}
    if ledger.get("date") != today:
        ledger = {"date": today, "used": 0}
    if int(ledger.get("used", 0)) >= cap:
        raise RuntimeError("Local daily EODHD request safety cap reached")
    ledger["used"] += 1
    ledger_path.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")


def read_cached_prices(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    try:
        prices = [{"date": row["date"], **{field: float(row[field]) for field in FIELDS[1:]}}
                  for row in rows]
    except (KeyError, TypeError, ValueError):
        raise ValueError("Malformed cached price CSV") from None
    return validate_prices(prices)


def fetch_prices(ticker: str, token: str, start: str, end: str) -> list[dict]:
    query = urlencode({"api_token": token, "from": start, "to": end, "fmt": "json"})
    url = f"https://eodhd.com/api/eod/{quote(ticker, safe='.') }?{query}"
    request = Request(url, headers={"User-Agent": "ACWI-IMI-research-validation/1.0"})
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        # Never print exc.url or request details: the URL contains the token.
        raise RuntimeError(f"EODHD HTTP status {exc.code}") from None
    except URLError:
        raise RuntimeError("EODHD connection failed") from None
    except (UnicodeError, json.JSONDecodeError):
        raise RuntimeError("EODHD returned malformed JSON") from None
    return validate_prices(payload)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--execute", action="store_true", help="Make real API calls; otherwise dry-run")
    p.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    p.add_argument("--output", type=Path, default=DEFAULT_OUT)
    p.add_argument("--limit", type=int, default=8)
    p.add_argument("--daily-cap", type=int, default=15, help="Local script allowance (free account limit is 20)")
    p.add_argument("--from-date", default=(date.today()-timedelta(days=365)).isoformat())
    p.add_argument("--to-date", default=date.today().isoformat())
    args = p.parse_args()

    if not 1 <= args.limit <= 15 or not 1 <= args.daily_cap <= 19:
        p.error("Limit must be 1–15 and local daily cap must be 1–19")
    try:
        if date.fromisoformat(args.from_date) > date.fromisoformat(args.to_date):
            p.error("Start date must be <= end date")
    except ValueError:
        p.error("Dates must be YYYY-MM-DD")

    symbols = read_symbols(args.manifest)[:args.limit]
    print(json.dumps({"mode": "LIVE" if args.execute else "DRY_RUN",
                      "tickers": symbols, "from": args.from_date, "to": args.to_date,
                      "maximum_new_requests": len(symbols)}, indent=2))
    if not args.execute:
        print("No API calls made. Add EODHD_API_TOKEN to Codex securely and use --execute.")
        return 0

    token = os.environ.get("EODHD_API_TOKEN", "").strip()
    if not token:
        raise SystemExit("Missing EODHD_API_TOKEN (configure Codex environment secret, not source code)")
    args.output.mkdir(parents=True, exist_ok=True)
    ledger_path = args.output / "daily_request_ledger.json"
    # Flags are observations, not inferred splits or permission to trade.
    try:
        from research.corporate_actions import price_flags
    except ModuleNotFoundError:
        from corporate_actions import price_flags
    records = []
    for ticker in symbols:
        path = args.output / (ticker.replace(".", "_") + ".csv")
        if path.exists():
            try:
                prices = read_cached_prices(path)
                if any(not args.from_date <= row["date"] <= args.to_date for row in prices):
                    raise ValueError("Cache belongs to a different requested date range; use a separate output directory")
                records.append({"ticker": ticker, "status": "cached", "rows": len(prices),
                                "first": prices[0]["date"], "last": prices[-1]["date"],
                                "cache_range_verified": False,
                                "corporate_action_flags": price_flags(prices),
                                "cache_note": "CSV has no request-range provenance; endpoint completeness requires the coverage report/calendar checks."})
            except ValueError as exc:
                records.append({"ticker": ticker, "status": "failed", "reason": str(exc)})
            continue
        try:
            claim_call(ledger_path, date.today().isoformat(), args.daily_cap)
            prices = fetch_prices(ticker, token, args.from_date, args.to_date)
            with path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerows(prices)
            records.append({"ticker": ticker, "status": "ok", "rows": len(prices),
                            "first": prices[0]["date"], "last": prices[-1]["date"],
                            "corporate_action_flags": price_flags(prices)})
        except (ValueError, RuntimeError) as exc:
            records.append({"ticker": ticker, "status": "failed", "reason": str(exc)})
            if "safety cap" in str(exc):
                break
    report = {"asof": date.today().isoformat(), "start": args.from_date,
              "end": args.to_date, "results": records,
              "warning": "One-year free-tier coverage cannot support a three-year backtest. "
                         "This is a price-coverage test, not historical MSCI ACWI IMI membership."}
    (args.output / "coverage_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 1 if any(row["status"] == "failed" for row in records) else 0


if __name__ == "__main__":
    raise SystemExit(main())
