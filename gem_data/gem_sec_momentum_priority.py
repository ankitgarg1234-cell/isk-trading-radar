"""Read-only prioritization of SEC financial review from preliminary GEMv1 r63.

Only original frozen score rule is used: vendor close[t]/close[t-63]-1 > 0.
Stored MARKETSTACK vendor_adj_close is NOT asserted equivalent to original frozen
vendor close. All outputs are REVIEW QUEUES, never proven strategy eligibility.
A nonpositive provisional return only defers SEC work; without independently
certified adjusted-price semantics and calendar it is never a final exclusion.
No external services, DB writes, or broker behavior in this module.
"""
from __future__ import annotations

import base64
import binascii
from datetime import date
from hashlib import sha256
import json
import math
import re
import zlib

MAX_COMPRESSED = 350_000
MAX_DECOMPRESSED = 2_000_000
HEX_SHA = re.compile(r"^[0-9a-f]{64}$")


class PriorityEvidenceHold(ValueError):
    pass


def _decoded_price_bars(receipt, ticker):
    if not isinstance(receipt, dict) or receipt.get("provider") != "MARKETSTACK":
        raise PriorityEvidenceHold("Missing approved-shape Marketstack receipt")
    metadata = receipt.get("metadata")
    if not isinstance(metadata, dict) or metadata.get("ticker") != ticker:
        raise PriorityEvidenceHold("Price receipt ticker mismatch")
    encoded = metadata.get("normalized_bars_zlib_base64")
    digest = receipt.get("source_sha256")
    if (not isinstance(encoded, str) or len(encoded) > MAX_COMPRESSED * 2
            or not isinstance(digest, str) or not HEX_SHA.fullmatch(digest)
            or metadata.get("normalized_bars_sha256") != digest):
        raise PriorityEvidenceHold("Price payload/hash metadata missing")
    try:
        compressed = base64.b64decode(encoded, validate=True)
        if len(compressed) > MAX_COMPRESSED:
            raise ValueError("compressed price payload too large")
        unpack = zlib.decompressobj()
        raw = unpack.decompress(compressed, MAX_DECOMPRESSED + 1)
        if (len(raw) > MAX_DECOMPRESSED or not unpack.eof
                or unpack.unconsumed_tail or unpack.unused_data):
            raise ValueError("unbounded or incomplete compressed price payload")
        raw += unpack.flush()
        if len(raw) > MAX_DECOMPRESSED or sha256(raw).hexdigest() != digest:
            raise ValueError("Stored price bars SHA256 mismatch")
        bars = json.loads(raw)
    except (ValueError, TypeError, binascii.Error, zlib.error, UnicodeError) as exc:
        raise PriorityEvidenceHold("Stored price receipt bytes cannot be verified") from exc
    if not isinstance(bars, list) or len(bars) > 400:
        raise PriorityEvidenceHold("Invalid price bar array")
    sessions = []
    for b in bars:
        if not isinstance(b, dict) or b.get("ticker") != ticker:
            raise PriorityEvidenceHold("Mixed price ticker identity")
        session = b.get("session")
        if not isinstance(session, str):
            raise PriorityEvidenceHold("Malformed price session")
        try:
            if date.fromisoformat(session).isoformat() != session:
                raise ValueError("noncanonical")
        except ValueError as exc:
            raise PriorityEvidenceHold("Malformed price date") from exc
        sessions.append(session)
    if not sessions or sessions != sorted(set(sessions)):
        raise PriorityEvidenceHold("Price sessions unsorted/duplicated")
    if metadata.get("completed_sessions") != len(bars):
        raise PriorityEvidenceHold("Price receipt row count mismatch")
    if (metadata.get("first_session") != sessions[0]
            or metadata.get("last_session") != sessions[-1]):
        raise PriorityEvidenceHold("Price history endpoint metadata mismatch")
    return bars


def preliminary_momentum(receipt, ticker, signal_day, *, calendar_sessions=None):
    """Rank SEC workload only, never return definitive eligibility/exclusion."""
    try:
        date.fromisoformat(signal_day)
        if not isinstance(ticker, str) or not ticker or not isinstance(signal_day, str):
            raise ValueError("ticker or signal day missing")
    except (ValueError, TypeError) as exc:
        raise PriorityEvidenceHold("Invalid requested signal date") from exc
    base = {"ticker": ticker, "signal_session": signal_day,
            "r63_preliminary": None,
            "adjusted_price_parity_certified": False,
            "sec_gate_certified": False,
            "final_strategy_exclusion": False}
    if receipt is None:
        return {**base, "priority": "PRICE_REPAIR_FIRST",
                "reason": "NO_PRICE_RECEIPT"}
    try:
        bars = _decoded_price_bars(receipt, ticker)
        index = {bar["session"]: n for n, bar in enumerate(bars)}
        if signal_day not in index:
            raise PriorityEvidenceHold("Signal-session observation missing")
        n = index[signal_day]
        if n < 63:
            raise PriorityEvidenceHold("Fewer than 64 observations by signal")
        tail = bars[n-63:n+1]
        if calendar_sessions is not None:
            if (not isinstance(calendar_sessions, list)
                    or len(calendar_sessions) < 64
                    or [b["session"] for b in tail] != calendar_sessions[-64:]
                    or calendar_sessions[-1] != signal_day):
                raise PriorityEvidenceHold("Price dates disagree with supplied calendar")
        metadata = receipt["metadata"]
        rejected = metadata.get("rejected_sessions")
        if not isinstance(rejected, list):
            raise PriorityEvidenceHold("Missing rejected-session audit list")
        if any(not isinstance(day, str) for day in rejected):
            raise PriorityEvidenceHold("Malformed rejected-session audit")
        if any(tail[0]["session"] <= day <= signal_day for day in rejected):
            raise PriorityEvidenceHold("Rejected vendor session within r63 window")
        closes = []
        for b in tail:
            x = b.get("vendor_adj_close")
            if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or x <= 0:
                raise PriorityEvidenceHold("Invalid vendor adjusted close in r63 window")
            closes.append(float(x))
        r63 = closes[-1] / closes[0] - 1.0
        # The Marketstack adjusted field is *not* proven frozen-vendor parity.
        if r63 > 0:
            return {**base, "r63_preliminary": r63,
                    "priority": "SEC_REVIEW_FIRST",
                    "reason": "POSITIVE_UNCERTIFIED_VENDOR_MOMENTUM"}
        return {**base, "r63_preliminary": r63,
                "priority": "DEFER_SEC_PENDING_PRICE_QA",
                "reason": "NONPOSITIVE_PROVISIONAL_NOT_PROVEN_EXCLUSION"}
    except PriorityEvidenceHold as exc:
        return {**base, "priority": "PRICE_REPAIR_FIRST",
                "reason": str(exc)[:160]}


def build_sec_priority_queue(members, receipt_by_ticker, signal_day, *, calendar_sessions=None):
    """Require complete unique universe; missing members remain explicit holds."""
    if (not isinstance(members, list) or not 480 <= len(members) <= 600
            or not isinstance(receipt_by_ticker, dict)
            or not isinstance(signal_day, str)):
        raise PriorityEvidenceHold("Complete input membership manifest required")
    if any(not isinstance(s, str) or not re.fullmatch(r"[A-Z0-9.-]{1,16}", s)
           for s in members) or len(set(members)) != len(members):
        raise PriorityEvidenceHold("Malformed or duplicate securities")
    if set(receipt_by_ticker) - set(members):
        raise PriorityEvidenceHold("Price evidence includes non-member symbol")
    rows = [preliminary_momentum(receipt_by_ticker.get(ticker), ticker, signal_day,
                                 calendar_sessions=calendar_sessions)
            for ticker in members]
    order = {"SEC_REVIEW_FIRST": 0, "PRICE_REPAIR_FIRST": 1,
             "DEFER_SEC_PENDING_PRICE_QA": 2}
    rows.sort(key=lambda x: (order[x["priority"]],
                             -x["r63_preliminary"] if x["r63_preliminary"] is not None else 0,
                             x["ticker"]))
    counts = {k: sum(row["priority"] == k for row in rows) for k in order}
    result = {"schema": "gem-sec-momentum-review-queue-v1",
              "signal_session": signal_day, "member_count": len(members),
              "priority_counts": counts, "rows": rows,
              "scope": "UNVERIFIED_PRELIMINARY_WORKLOAD_PRIORITIZATION_ONLY",
              "membership_effective_dated_certified": False,
              "price_adjustment_parity_certified": False,
              "final_strategy_exclusions_verified": 0,
              "source_qa_certified": False, "ranking_certified": False,
              "broker_orders_sent": 0, "trading_authorized": False}
    result["report_sha256"] = sha256(json.dumps(
        result, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()).hexdigest()
    return result
