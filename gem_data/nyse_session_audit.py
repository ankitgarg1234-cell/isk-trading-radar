"""2026 NYSE session plan and independently observed close audit.

Published dates from NYSE official hours/holiday schedule; refreshed source
receipt must match the published-year markers. This module does NOT presume
an exchange was open in an unscheduled emergency closure. Missing EOD data
keeps the completed-session gate on HOLD. No future-year rollover by guess.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
import re

NYSE_2026_CLOSED = frozenset({
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03",
    "2026-05-25", "2026-06-19", "2026-07-03", "2026-09-07",
    "2026-11-26", "2026-12-25",
})
NYSE_2026_EARLY = frozenset({"2026-11-27", "2026-12-24"})
OFFICIAL_URL = "https://www.nyse.com/trade/hours-calendars"
_ET = ZoneInfo("America/New_York")


class NyseAuditHold(ValueError):
    pass


def _calendar_day(value):
    if type(value) is not str:
        raise NyseAuditHold("Invalid ISO session date")
    try:
        d = date.fromisoformat(value)
    except ValueError:
        raise NyseAuditHold("Invalid ISO session date") from None
    if d.isoformat() != value or d.year != 2026:
        raise NyseAuditHold("Session calendar outside verified 2026 schedule")
    return d


def sessions_2026(first, last, *, official_receipt_sha256):
    if not isinstance(official_receipt_sha256, str) or not re.fullmatch(r"[a-f0-9]{64}", official_receipt_sha256):
        raise NyseAuditHold("Official NYSE source fingerprint required")
    start, stop = _calendar_day(first), _calendar_day(last)
    if start > stop:
        raise NyseAuditHold("Bad NYSE date window")
    sessions = []
    day = start
    while day <= stop:
        s = day.isoformat()
        if day.weekday() < 5 and s not in NYSE_2026_CLOSED:
            sessions.append({"session": s,
                             "scheduled_close_et":"13:00" if s in NYSE_2026_EARLY else "16:00",
                             "calendar_receipt":official_receipt_sha256,
                             "source":OFFICIAL_URL,
                             "source_certification":"PUBLISHED_2026_SCHEDULE_ONLY"})
        day += timedelta(days=1)
    return sessions


def completed_session_audit(row, source_confirmations, *, checked_at):
    """Require two distinct reconciled close observations after official close.

    Confirmation shape: {provider,session,retrieved_at,close_price,
    source_sha256,calendar_aligned}; same-provider duplicates don't count.
    This is evidence of data availability, not proof against an extraordinary
    NYSE closure or a source's altered dividend/split adjustments.
    """
    day = _calendar_day(row.get("session"))
    if type(checked_at) is not datetime or checked_at.tzinfo is None:
        raise NyseAuditHold("Timezone-aware audit timestamp required")
    scheduled_close = time(13,0) if row.get("scheduled_close_et")=="13:00" else time(16,0)
    close_at = datetime.combine(day, scheduled_close, tzinfo=_ET)
    post_close = close_at + timedelta(minutes=30)
    if checked_at.astimezone(_ET) < post_close:
        return {"session":day.isoformat(),"status":"NOT_YET_FINAL",
                "providers_confirmed":0,"verified_calendar_day":False}
    accepted = set()
    for obs in source_confirmations:
        if not isinstance(obs, dict) or obs.get("session") != day.isoformat():
            continue
        provider = obs.get("provider")
        digest = obs.get("source_sha256")
        value = obs.get("close_price")
        try:
            fetched_at = datetime.fromisoformat(obs.get("retrieved_at", "").replace("Z","+00:00"))
        except (TypeError, ValueError):
            continue
        if (not provider or not isinstance(provider, str)
                or not re.fullmatch(r"[a-f0-9]{64}", str(digest))
                or type(value) not in (int,float) or not 0 < float(value) < 1000000
                or fetched_at.tzinfo is None or fetched_at.astimezone(_ET) < post_close
                or obs.get("calendar_aligned") is not True):
            continue
        accepted.add(provider.upper())
    return {"session":day.isoformat(),
            "status":"CLOSE_OBSERVATIONS_RECONCILED" if len(accepted)>=2 else "EOD_EVIDENCE_PENDING",
            "providers_confirmed":len(accepted),
            "verified_calendar_day":len(accepted)>=2,
            "emergency_halt_independently_certified":False,
            "scheduled_close_et":row["scheduled_close_et"]}


def month_end_from_sessions(planned):
    if not isinstance(planned,list) or not planned:
        raise NyseAuditHold("Missing expected NYSE sessions")
    out = []
    for index in range(len(planned)-1):
        if planned[index]["session"][:7] != planned[index+1]["session"][:7]:
            out.append({"signal_session":planned[index]["session"],
                        "next_session":planned[index+1]["session"],
                        "status":"SCHEDULED_NOT_CONFIRMED",
                        "manual_only":True})
    return out
