"""Personal-research-only yfinance gap candidates for exact rejected GEM sessions.

No Marketstack overwrites, no production scheduling, no database writes, no
source certification, no trading. Optional external dependency: yfinance.
Usage:
  pip install yfinance
  python -m gem_data.gem_yfinance_gap_research --from-neon --output ./gaps.json
  python -m gem_data.gem_yfinance_gap_research --symbols AAPL,MSFT,SPY --output ./test.json

Only use Yahoo data within Yahoo's personal-use terms; use a licensed second
feed and separately approved adjustment parity before research is released.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re

TARGET_DATES = ("2026-06-09", "2026-06-10", "2026-06-15")
SYMBOL = re.compile(r"^[A-Z0-9.\-]{1,16}$")
MAX_SYMBOLS = 20
# Explicitly known Yahoo share-class aliases; all still require identity QA.
YAHOO_ALIASES = {"BRK.B": "BRK-B", "BF.B": "BF-B"}


class YahooResearchHold(ValueError):
    pass


def _float(value, field, *, zero=False):
    if isinstance(value, bool):
        raise YahooResearchHold("INVALID_" + field.upper())
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise YahooResearchHold("INVALID_" + field.upper()) from None
    if not math.isfinite(number) or (number < 0 if zero else number <= 0):
        raise YahooResearchHold("INVALID_" + field.upper())
    return number


def _validate_symbols(symbols):
    if not isinstance(symbols, (tuple, list)) or not 1 <= len(symbols) <= MAX_SYMBOLS:
        raise YahooResearchHold("Bounded 1..20 ticker research batch required")
    checked = []
    for symbol in symbols:
        if not isinstance(symbol, str) or not SYMBOL.fullmatch(symbol):
            raise YahooResearchHold("Invalid ticker symbol")
        if symbol in checked:
            raise YahooResearchHold("Duplicate ticker")
        checked.append(symbol)
    return checked


def _validate_dates(target_dates):
    if not isinstance(target_dates, (tuple, list)) or not 1 <= len(target_dates) <= 20:
        raise YahooResearchHold("Bounded target sessions required")
    parsed = []
    for value in target_dates:
        if not isinstance(value, str):
            raise YahooResearchHold("Session must be ISO date")
        try:
            day = date.fromisoformat(value)
        except ValueError:
            raise YahooResearchHold("Session must be ISO date") from None
        if day.isoformat() != value or day.weekday() >= 5 or day > date.today():
            raise YahooResearchHold("Invalid/noncompleted trading weekday")
        if day in parsed:
            raise YahooResearchHold("Duplicate session")
        parsed.append(day)
    return tuple(parsed)


def build_gap_worklist(rows, *, target_dates=TARGET_DATES, after_symbol="", limit=MAX_SYMBOLS):
    """Extract exact rejected ticker/date pairs from latest Marketstack receipts."""
    target = {x.isoformat() for x in _validate_dates(target_dates)}
    if not isinstance(after_symbol, str) or (after_symbol and not SYMBOL.fullmatch(after_symbol)):
        raise YahooResearchHold("Invalid cursor")
    if type(limit) is not int or not 1 <= limit <= MAX_SYMBOLS:
        raise YahooResearchHold("Invalid worklist limit")
    pending = {}
    for ticker, rejected in rows:
        if not isinstance(ticker, str) or not SYMBOL.fullmatch(ticker) or ticker <= after_symbol:
            continue
        if not isinstance(rejected, list):
            continue
        bad = sorted({item[0] for item in rejected
                      if isinstance(item, (list, tuple)) and len(item) >= 2
                      and isinstance(item[0], str) and item[0] in target})
        if bad:
            pending[ticker] = bad
            if len(pending) == limit:
                break
    return pending


def load_marketstack_gap_worklist(*, after_symbol="", limit=MAX_SYMBOLS):
    """Neon restricted-reader inventory. Never touch any paper-trading tables."""
    import psycopg
    from gem_data.gem_public_ingest import EXPERIMENT
    reader = os.getenv("GEM_READONLY_DATABASE_URL", "")
    if not reader.startswith("postgresql://gem_web_readonly:"):
        raise YahooResearchHold("Restricted GEM read-only URL required")
    with psycopg.connect(reader, connect_timeout=6) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SET LOCAL statement_timeout=10000")
            cur.execute("""
                SELECT DISTINCT ON (metadata->>'ticker')
                    metadata->>'ticker', metadata->'rejected_reasons'
                FROM gem_source_receipt
                WHERE experiment_id=%s AND provider='MARKETSTACK'
                  AND source_type='prices' AND metadata->>'ticker' > %s
                ORDER BY metadata->>'ticker', observed_at DESC, receipt_id DESC
            """, (EXPERIMENT, after_symbol))
            rows = cur.fetchall()
    return build_gap_worklist(rows, after_symbol=after_symbol, limit=limit)


def _fetch_yfinance(ticker, start, end):
    """Only import yfinance on an explicitly invoked research CLI."""
    import yfinance as yf
    client = yf.Ticker(ticker)
    frame = client.history(start=start, end=end, interval="1d",
                           actions=True, auto_adjust=False, repair=False, keepna=True)
    metadata = client.history_metadata or {}
    return frame, metadata.get("currency")


def _row_from_frame(frame, session, *, ticker):
    if frame is None or not hasattr(frame, "iterrows"):
        raise YahooResearchHold("INVALID_HISTORY_FRAME")
    matches = []
    for timestamp, row in frame.iterrows():
        try:
            day = timestamp.date().isoformat()
        except (AttributeError, TypeError, ValueError):
            raise YahooResearchHold("INVALID_SOURCE_DATE") from None
        if day == session:
            matches.append(row)
    if len(matches) != 1:
        raise YahooResearchHold("MISSING_OR_DUPLICATE_SESSION")
    row = matches[0]
    values = {}
    for name, field in (("Open", "open"), ("High", "high"), ("Low", "low"),
                        ("Close", "close"), ("Adj Close", "yahoo_adj_close"),
                        ("Volume", "volume")):
        values[field] = _float(row.get(name), field, zero=field == "volume")
    if (values["high"] < max(values["open"], values["close"], values["low"])
            or values["low"] > min(values["open"], values["close"], values["high"])):
        raise YahooResearchHold("INVALID_OHLC_GEOMETRY")
    for name, field in (("Dividends", "dividend"), ("Stock Splits", "split_factor_event")):
        if name not in row:
            raise YahooResearchHold("MISSING_CORPORATE_ACTION_FIELD")
        values[field] = _float(row[name], field, zero=True)
    return {"ticker": ticker, "session": session, **values}


def collect_candidates(symbols, *, target_dates=TARGET_DATES,
                       wanted_sessions=None, fetch_fn=None, now=None):
    """Return separate provisional observations; never source PASS or broker orders."""
    tickers = _validate_symbols(symbols)
    sessions = _validate_dates(target_dates)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise YahooResearchHold("Timezone-aware audit clock required")
    first = date.fromordinal(min(sessions).toordinal()-2).isoformat()
    last = date.fromordinal(max(sessions).toordinal()+2).isoformat()
    fetch_fn = fetch_fn or _fetch_yfinance
    if wanted_sessions is not None:
        if not isinstance(wanted_sessions, dict) or set(wanted_sessions) != set(tickers):
            raise YahooResearchHold("Candidate worklist mismatch")
        allowed = {x.isoformat() for x in sessions}
        for ticker, days in wanted_sessions.items():
            if not isinstance(days, list) or not days or any(day not in allowed for day in days):
                raise YahooResearchHold("Candidate sessions outside requested range")
    candidates, holds = [], []
    for ticker in tickers:
        yahoo = YAHOO_ALIASES.get(ticker, ticker)
        try:
            frame, currency = fetch_fn(yahoo, first, last)
        except Exception as exc:
            holds.append({"ticker": ticker, "reason": "YFINANCE_FETCH_" + type(exc).__name__})
            continue
        if currency != "USD":
            holds.append({"ticker": ticker, "reason": "NON_USD_OR_CURRENCY_NOT_VERIFIED"})
            continue
        for day in sessions:
            if wanted_sessions is not None and day.isoformat() not in wanted_sessions[ticker]:
                continue
            try:
                bar = _row_from_frame(frame, day.isoformat(), ticker=ticker)
            except YahooResearchHold as exc:
                holds.append({"ticker": ticker, "session": day.isoformat(), "reason": str(exc)})
                continue
            digest = sha256(json.dumps(bar, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            candidates.append({
                "marketstack_ticker": ticker,
                "yahoo_query_symbol": yahoo,
                "symbol_alias_used": yahoo != ticker,
                "bar": bar,
                "normalized_row_sha256": digest,
                "dataframe_only_no_raw_http_receipt": True,
                "source": "YAHOO_FINANCE_YFINANCE_PERSONAL_RESEARCH",
                "status": "GAP_CANDIDATE_ONLY",
                "source_qa_status": "NOT_APPROVED",
                "trading_authorized": False,
                "requires_independent_reference": True,
                "adjustment_parity_verified": False,
                "close_basis": "YAHOO_CLOSE_UNRECONCILED_SPLIT_AND_DIVIDEND_SEMANTICS",
            })
    return {
        "schema": "gem-yfinance-gap-research-v1",
        "retrieved_at": now.astimezone(timezone.utc).isoformat(),
        "target_sessions": [x.isoformat() for x in sessions],
        "tickers_requested": len(tickers),
        "possible_replacements": len(candidates),
        "holds": holds,
        "candidates": candidates,
        "allowed_for_live_trading": False,
        "authorization": "PERSONAL_RESEARCH_ONLY_NO_PRODUCTION_FEED",
        "merge_into_marketstack": False,
    }


def save_candidate_file(path, report):
    """Create-only private local research file; do not archive Yahoo data in Git."""
    path = Path(path)
    raw = (json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as output:
        output.write(raw)
    return str(path)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Personal price-gap research only, no trading")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--symbols", help="Comma-separated canonical tickers, 1..20")
    source.add_argument("--from-neon", action="store_true", help="Read actual rejected dates from GEM isolated restricted reader")
    parser.add_argument("--after-symbol", default="", help="Cursor for paged Neon worklist")
    parser.add_argument("--output", required=True, help="New private local JSON output; refuses overwrite")
    args = parser.parse_args(argv)
    wanted = load_marketstack_gap_worklist(after_symbol=args.after_symbol) if args.from_neon else None
    symbols = list(wanted) if wanted is not None else [x.strip().upper() for x in args.symbols.split(",")]
    if not symbols:
        print(json.dumps({"tickers": 0, "candidate_bars": 0, "message": "No more vendor-rejected target dates"}))
        return 0
    report = collect_candidates(symbols, wanted_sessions=wanted)
    report["next_cursor"] = symbols[-1] if args.from_neon else None
    save_candidate_file(args.output, report)
    print(json.dumps({"schema": report["schema"], "tickers": report["tickers_requested"],
                      "candidate_bars": report["possible_replacements"],
                      "held_checks": len(report["holds"]), "next_cursor": report["next_cursor"],
                      "trading_authorized": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
