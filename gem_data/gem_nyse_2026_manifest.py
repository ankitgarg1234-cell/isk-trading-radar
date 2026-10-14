"""NYSE 2026 scheduled core-equities sessions, cross-checkable against NYSE.

Primary schedule: https://www.nyse.com/markets/hours-calendars
NYSE Group announcement 2025-12-23:
https://ir.theice.com/press/news-details/2025/NYSE-Group-Announces-2026-2027-and-2028-Holiday-and-Early-Closings-Calendar/

This is a deterministic *published schedule*, not proof of actual market
trading completion, intraday halts, or unscheduled emergency closure.
No network, broker, database writes or trading authorization.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
import json
from zoneinfo import ZoneInfo

YEAR = 2026
NY = ZoneInfo("America/New_York")

HOLIDAYS_2026 = frozenset((
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03",
    "2026-05-25", "2026-06-19", "2026-07-03", "2026-09-07",
    "2026-11-26", "2026-12-25",
))
EARLY_CLOSE_2026 = frozenset(("2026-11-27", "2026-12-24"))


def published_schedule_2026(*, independent_exchange_calendar=None):
    days = []
    day = date(YEAR, 1, 1)
    end = date(YEAR + 1, 1, 1)
    while day < end:
        stamp = day.isoformat()
        if day.weekday() < 5 and stamp not in HOLIDAYS_2026:
            early = stamp in EARLY_CLOSE_2026
            open_local = datetime.combine(day, time(9, 30), tzinfo=NY)
            close_local = datetime.combine(day, time(13 if early else 16, 0), tzinfo=NY)
            days.append({
                "session": stamp,
                "open_utc": open_local.astimezone(timezone.utc).isoformat(),
                "close_utc": close_local.astimezone(timezone.utc).isoformat(),
                "early_close": early,
                "scheduled_core_close_et": "13:00" if early else "16:00",
            })
        day += timedelta(days=1)
    if not days or len(days) != 251:
        raise ValueError("Official NYSE holiday schedule mismatch")
    if sum(bool(d["early_close"]) for d in days) != 2:
        raise ValueError("NYSE early-close schedule mismatch")
    session_days = [row["session"] for row in days]
    independently_matches = None
    if independent_exchange_calendar is not None:
        # Independent vendor calendar must be explicitly supplied, not assumed.
        if not isinstance(independent_exchange_calendar, list):
            raise ValueError("Independent session dates invalid")
        independently_matches = session_days == independent_exchange_calendar
        if not independently_matches:
            raise ValueError("Published NYSE and independent sessions disagree")
    month_ends = {}
    for row in days:
        month_ends[row["session"][:7]] = row["session"]
    report = {
        "schema": "gem-nyse-published-core-calendar-2026-v1",
        "published_source": "https://www.nyse.com/markets/hours-calendars",
        "official_schedule_year": YEAR,
        "session_count": len(days),
        "official_holidays": sorted(HOLIDAYS_2026),
        "official_early_closes": sorted(EARLY_CLOSE_2026),
        "month_end_sessions": month_ends,
        "sessions": days,
        "independent_schedule_reconciled": independently_matches is True,
        "actual_completed_sessions_verified": False,
        "emergency_closure_checked": False,
        "calendar_trading_certified": False,
        "trade_authorized": False,
    }
    report["report_sha256"] = sha256(json.dumps(
        report, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()).hexdigest()
    return report
