"""2026 NYSE core-equities schedule proposal for GEMv1 independent review.

Derived from pinned pandas_market_calendars and checked against published NYSE
2026 closure/early-close dates. Publication link is NOT a signed raw receipt.
Emergency market changes can supersede the annual schedule; never auto-certify
a month-end, completed bars, or an order window from this helper.
"""
from __future__ import annotations

from datetime import date, datetime, timezone, timedelta
from hashlib import sha256
import json
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal

NYSE_2026_URL = "https://www.nyse.com/trade/hours-calendars"
NYSE_2026_CLOSED = frozenset({
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03",
    "2026-05-25", "2026-06-19", "2026-07-03", "2026-09-07",
    "2026-11-26", "2026-12-25",
})
NYSE_2026_EARLY = frozenset({"2026-11-27", "2026-12-24"})
NY = ZoneInfo("America/New_York")


def _utc_datetime(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("Observation must be timezone-aware")
    return value.astimezone(timezone.utc)


def proposed_nyse_calendar_2026(
    *, start: str, end: str, observed_at: datetime
) -> dict:
    """Build bounded month-end/next-open schedule, WITHOUT certification.

    Future scheduled sessions are forecasts. Only already closed sessions are
    marked completed at the observed instant. Manual extraordinary-market
    checks and primary-source retrieval are independent downstream gates.
    """
    try:
        first, last = date.fromisoformat(start), date.fromisoformat(end)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid schedule date range") from exc
    if first.year != 2026 or last.year != 2026 or not first <= last:
        raise ValueError("Only bounded official-published 2026 dates supported")
    if (last - first).days > 365:
        raise ValueError("Unbounded NYSE schedule request")
    observed = _utc_datetime(observed_at)
    # Span the published year so official closure and early-close checks
    # cannot be bypassed by requesting a narrow benign date range.
    calendar = mcal.get_calendar("NYSE")
    full = calendar.schedule(start_date="2026-01-01", end_date="2026-12-31")
    session_rows: list[dict] = []
    for index, row in full.iterrows():
        day = index.date().isoformat()
        opened = row["market_open"].to_pydatetime().astimezone(timezone.utc)
        closed = row["market_close"].to_pydatetime().astimezone(timezone.utc)
        if not (opened < closed and opened.astimezone(NY).hour == 9
                and opened.astimezone(NY).minute == 30):
            raise ValueError("NYSE calendar irregular open requires separate review")
        close_local = closed.astimezone(NY)
        if day in NYSE_2026_EARLY:
            if (close_local.hour, close_local.minute) != (13, 0):
                raise ValueError("Published NYSE early-close mismatch")
        elif (close_local.hour, close_local.minute) != (16, 0):
            raise ValueError("Unexpected NYSE close requires separate review")
        session_rows.append({
            "session": day,
            "open_utc": opened.isoformat(),
            "close_utc": closed.isoformat(),
            "early_close": day in NYSE_2026_EARLY,
            "completed_at_observation": closed <= observed,
        })

    dates = {r["session"] for r in session_rows}
    year_days = {
        (date(2026, 1, 1) + timedelta(days=i)).isoformat()
        for i in range(365)
        if (date(2026, 1, 1) + timedelta(days=i)).weekday() < 5
    }
    if year_days - dates != NYSE_2026_CLOSED:
        raise ValueError("NYSE proposed holiday dates disagree with 2026 publication")
    if {r["session"] for r in session_rows if r["early_close"]} != NYSE_2026_EARLY:
        raise ValueError("NYSE published 2026 early closes absent from schedule")
    selected = [r for r in session_rows if start <= r["session"] <= end]
    if not selected:
        raise ValueError("Selected window has no trading sessions")
    by_month: dict[str, dict] = {}
    for r in session_rows:
        month = r["session"][:7]
        if not (start[:7] <= month <= end[:7]):
            continue
        # Month-end is LAST completed or forecast scheduled session of month,
        # never inferred from the calendar date's weekday alone.
        by_month[month] = r
    for month, r in by_month.items():
        pos = session_rows.index(r)
        next_item = session_rows[pos + 1] if pos + 1 < len(session_rows) else None
        by_month[month] = {
            "month_end_session": r["session"],
            "last_close_utc": r["close_utc"],
            "next_session": next_item["session"] if next_item else None,
            "next_open_utc": next_item["open_utc"] if next_item else None,
            "month_end_completed": r["completed_at_observation"],
        }
    body = {
        "schema": "gem-nyse-2026-calendar-proposal-v1",
        "start": start, "end": end,
        "observed_at": observed.isoformat(),
        "source_publication": NYSE_2026_URL,
        "source_raw_receipt_sha256": None,
        "sessions": selected,
        "month_ends": by_month,
        "official_emergency_status_reviewed": False,
        "primary_source_independently_certified": False,
        "trading_authorized": False,
        "status": "PROPOSED_SCHEDULE_ONLY",
    }
    body["proposal_sha256"] = sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return body
