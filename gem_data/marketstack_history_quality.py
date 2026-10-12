"""Offline, fail-closed Marketstack EOD coverage audit.

Takes already retrieved *vendor rows* and an independently supplied expected
completed-session manifest. No network, credentials, database, signal or order.
Passing local row geometry is NEVER source certification.
"""
from __future__ import annotations

from datetime import date
import math
import re

_TICKER = re.compile(r"^[A-Z0-9.-]{1,16}$")
_PRICE_FIELDS = ("open", "high", "low", "close", "adj_close")


def audit_eod_coverage(
    rows: list[dict], *, symbols: list[str], completed_sessions: list[str],
    max_reported_issues: int = 100,
) -> dict:
    """Report invalid/null rows AND missing expected sessions without filling gaps.

    An external reviewer must verify completed_sessions against the exchange.
    A green local shape check has no power to authorize GEM selections.
    """
    if (not isinstance(symbols, list) or not symbols
            or len(symbols) > 600
            or any(not isinstance(s, str) or not _TICKER.fullmatch(s) for s in symbols)
            or len(set(symbols)) != len(symbols)):
        raise ValueError("Invalid symbol manifest")
    if (not isinstance(completed_sessions, list) or not completed_sessions
            or len(completed_sessions) > 1500
            or any(not isinstance(s, str) or len(s) != 10 for s in completed_sessions)):
        raise ValueError("Invalid completed-session manifest")
    try:
        days = [date.fromisoformat(s) for s in completed_sessions]
    except ValueError as exc:
        raise ValueError("Invalid ISO completed-session date") from exc
    if days != sorted(set(days)):
        raise ValueError("Unsorted or duplicate completed-session manifest")
    if not isinstance(rows, list) or len(rows) > 900000:
        raise ValueError("Invalid or unbounded vendor rows")
    if not isinstance(max_reported_issues, int) or not 1 <= max_reported_issues <= 1000:
        raise ValueError("Invalid issue cap")

    expected_symbols = set(symbols)
    expected_days = set(completed_sessions)
    seen: set[tuple[str, str]] = set()
    issues: list[dict] = []
    issue_count = 0

    def flag(symbol: str, session: str, reason: str) -> None:
        nonlocal issue_count
        issue_count += 1
        if len(issues) < max_reported_issues:
            issues.append({"symbol": symbol, "session": session, "reason": reason})

    for item in rows:
        if not isinstance(item, dict):
            flag("UNKNOWN", "UNKNOWN", "MALFORMED_ROW")
            continue
        symbol = item.get("symbol")
        raw_date = item.get("date")
        if not isinstance(symbol, str) or not isinstance(raw_date, str):
            flag("UNKNOWN", "UNKNOWN", "MALFORMED_IDENTITY")
            continue
        session = raw_date[:10]
        try:
            if len(session) != 10:
                raise ValueError
            date.fromisoformat(session)
        except ValueError:
            flag(symbol, "INVALID_DATE", "MALFORMED_SESSION")
            continue
        if symbol not in expected_symbols or session not in expected_days:
            flag(symbol, session, "UNEXPECTED_VENDOR_ROW")
            continue
        key = (symbol, session)
        if key in seen:
            flag(symbol, session, "DUPLICATE_VENDOR_ROW")
            continue
        seen.add(key)
        numeric: dict[str, float] = {}
        for field in (*_PRICE_FIELDS, "volume"):
            value = item.get(field)
            try:
                if value is None or isinstance(value, bool):
                    raise ValueError
                parsed = float(value)
                if not math.isfinite(parsed) or (parsed < 0 if field == "volume" else parsed <= 0):
                    raise ValueError
                numeric[field] = parsed
            except (TypeError, ValueError, OverflowError):
                flag(symbol, session, "INVALID_" + field.upper())
        if all(f in numeric for f in ("open", "high", "low", "close")):
            if (numeric["high"] < max(numeric["open"], numeric["close"])
                    or numeric["low"] > min(numeric["open"], numeric["close"])
                    or numeric["low"] > numeric["high"]):
                flag(symbol, session, "INVALID_NOMINAL_OHLC")

    for symbol in symbols:
        for session in completed_sessions:
            if (symbol, session) not in seen:
                flag(symbol, session, "MISSING_VENDOR_ROW")

    return {
        "schema": "gem-marketstack-offline-coverage-v1",
        "status": "HOLD" if issue_count else "UNVERIFIED_LOCAL_SHAPE_ONLY",
        "certified": False,
        "expected_symbols": len(symbols),
        "expected_sessions_per_symbol": len(completed_sessions),
        "received_rows": len(rows),
        "issue_count": issue_count,
        "reported_issues": issues,
        "issues_truncated": issue_count > len(issues),
        "warning": "Completed-session manifest and vendor adjustments require independent QA.",
    }
