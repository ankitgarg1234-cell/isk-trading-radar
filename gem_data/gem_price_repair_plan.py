"""GEM V1 read-only price collection gap/repair report.

This module NEVER calls a market-data vendor or approves ranking inputs.
Its purpose is to keep observed but incomplete histories off the collector's
'finished' list, without silently retrying and spending user API credits.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
import re


def plan_price_repairs(members, receipts, *, min_sessions=127):
    if (not isinstance(members, list) or not 480 <= len(members) <= 600
            or not all(isinstance(s, str) and re.fullmatch(r"[A-Z0-9.-]{1,16}",s)
                       for s in members) or len(set(members)) != len(members)):
        raise ValueError("Expected membership universe missing or duplicate")
    if not isinstance(receipts, dict) or set(receipts) - set(members):
        raise ValueError("Unexpected vendor receipt outside membership")
    if type(min_sessions) is not int or not 64 <= min_sessions <= 400:
        raise ValueError("Unexpected source coverage threshold")
    rows = []
    for symbol in sorted(members):
        receipt = receipts.get(symbol)
        if receipt is None:
            action, reason = "ACQUIRE_MISSING_VENDOR_HISTORY", "NO_VENDOR_RECEIPT"
        else:
            metadata = receipt.get("metadata") if isinstance(receipt,dict) else None
            if (not isinstance(metadata,dict)
                    or receipt.get("provider") != "MARKETSTACK"
                    or metadata.get("ticker") != symbol):
                action, reason = "REPAIR_UNUSABLE_VENDOR_RECEIPT", "INVALID_RECEIPT_IDENTITY"
            else:
                sessions = metadata.get("completed_sessions")
                rejected = metadata.get("rejected_session_count")
                if type(sessions) is not int or sessions < min_sessions:
                    action, reason = "REPAIR_HISTORICAL_GAPS", "LESS_THAN_REQUIRED_SESSIONS"
                elif type(rejected) is not int or rejected < 0:
                    action, reason = "REPAIR_UNUSABLE_VENDOR_RECEIPT", "INVALID_REJECTION_AUDIT"
                elif rejected > 0 or metadata.get("fallback_needed") is True:
                    action, reason = "RECONCILE_REJECTED_VENDOR_BARS", "VENDOR_BAD_OR_MISSING_BARS"
                else:
                    action, reason = "VERIFY_SOURCE_ADJUSTMENT", "AWAIT_INDEPENDENT_PRICE_QA"
        rows.append({"ticker":symbol,"next_action":action,"reason":reason,
                     "complete_for_trading":False,"new_vendor_call_authorized":False})
    counts = dict(Counter(x["next_action"] for x in rows))
    result = {"schema":"gem-price-repair-backlog-v1",
              "members":len(members),"collected_members":len(receipts),
              "counts":counts,"queue":rows,"all_sources_certified":False,
              "vendor_budget_spend_authorized":False,
              "ranking_authorized":False}
    result["sha256"] = sha256(json.dumps(
        result,sort_keys=True,separators=(",",":"),allow_nan=False
    ).encode()).hexdigest()
    return result
