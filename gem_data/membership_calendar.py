"""Effective-date S&P member timeline + completed-session month-end scheduler.

Pure operations on externally supplied source receipts. Neither the current
membership snapshot nor a holiday heuristic is allowed to rewrite history.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from hashlib import sha256
import json


class CalendarMembershipHold(ValueError):
    pass


def _day(s):
    try:
        if not isinstance(s, str) or date.fromisoformat(s).isoformat() != s:
            raise ValueError()
    except ValueError as exc:
        raise CalendarMembershipHold("Invalid YYYY-MM-DD date") from exc
    return s


def month_end_plan(sessions, *, completed_through, official_receipt_sha256):
    """Returns all completed exchange month-end signals and their next open.

    The future next open can be scheduled only from an exchange calendar with
    a primary source receipt; a month is signaled only after that day's close.
    """
    if (not isinstance(official_receipt_sha256, str)
            or len(official_receipt_sha256) != 64
            or not isinstance(sessions, list)
            or len(sessions) != len(set(sessions))):
        raise CalendarMembershipHold("Missing calendar receipt/duplicate session")
    ordered = [_day(s) for s in sessions]
    if ordered != sorted(ordered):
        raise CalendarMembershipHold("Calendar out of order")
    cutoff = _day(completed_through)
    plans = []
    for idx in range(len(ordered)-1):
        day, nxt = ordered[idx], ordered[idx+1]
        if day <= cutoff and day[:7] != nxt[:7]:
            plans.append({"signal_session": day, "next_session": nxt,
                          "automatic_orders": False, "mode": "MANUAL_ONLY",
                          "calendar_receipt": official_receipt_sha256})
    return plans


def member_at(base_members, changes, signal_session):
    """Reconstruct effective-dated membership by security ID, with QA HOLD.

    Changes must include announced_at (date), effective_date, action,
    security_id, ticker and primary_evidence_sha256 to classify as reviewed.
    """
    target = _day(signal_session)
    members = {}
    for row in base_members:
        sec, ticker = row.get("security_id"), row.get("ticker")
        if not sec or not ticker or sec in members:
            raise CalendarMembershipHold("Invalid/duplicate starting security ID")
        members[sec] = ticker
    status = []
    changes = sorted(changes, key=lambda e: (e.get("effective_date", ""), e.get("security_id", "")))
    for event in changes:
        when = _day(event.get("effective_date"))
        if when > target:
            continue
        sec = event.get("security_id")
        ticker = event.get("ticker")
        action = event.get("action")
        if not sec or not ticker or action not in ("ADD", "REMOVE", "RENAME"):
            raise CalendarMembershipHold("Invalid membership action")
        announce = _day(event.get("announced_at"))
        if announce > when:
            raise CalendarMembershipHold("Membership event announced after effective date")
        receipt = event.get("primary_evidence_sha256")
        quality = ("PRIMARY_RECEIPT_REFERENCED" if isinstance(receipt, str)
                   and len(receipt) == 64 else "SECONDARY_EVIDENCE_HOLD")
        if action == "ADD":
            if sec in members:
                raise CalendarMembershipHold("Duplicate S&P admission")
            members[sec] = ticker
        elif action == "REMOVE":
            if members.get(sec) != ticker:
                raise CalendarMembershipHold("S&P removal identity conflict")
            del members[sec]
        else:
            if sec not in members:
                raise CalendarMembershipHold("Unknown S&P ticker rename")
            members[sec] = ticker
        status.append({"security_id": sec, "effective_date": when,
                       "action": action, "source_status": quality})
    if len(members) != len(set(members.values())):
        raise CalendarMembershipHold("Duplicate ticker/security assignment")
    return {"schema": "gem-sp500-effective-membership-v1",
            "as_of": target, "universe": [
                {"security_id": k, "ticker": v} for k,v in sorted(members.items(), key=lambda x: x[1])],
            "changes_applied": status,
            "independently_certified": False,
            "verification": "SOURCE_RECEIPTS_REQUIRE_INDEPENDENT_REVIEW",
            "count": len(members)}
