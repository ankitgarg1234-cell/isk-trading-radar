"""Vendor-independent GEMv1 OHLCV gap inventory and source reconciliation.

Never interpolate prices, manufacture adjustments or promote a replacement
provider to frozen-vendor parity. Designed for CSV/API adapters to normalize
daily observations before ingestion; NO outbound calls or trading activity.
"""
from __future__ import annotations

from datetime import date
from hashlib import sha256
import json
import math


class PricePatchHold(ValueError):
    pass


def _float(value, label, *, zero=False):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise PricePatchHold("Missing/nonfinite " + label)
    if value < 0 if zero else value <= 0:
        raise PricePatchHold("Nonpositive " + label)
    return float(value)


def _check_sessions(sessions):
    if not isinstance(sessions, list) or not sessions or len(sessions) != len(set(sessions)):
        raise PricePatchHold("Trading calendar is absent or has duplicates")
    try:
        parsed = [date.fromisoformat(s) for s in sessions]
    except (ValueError, TypeError) as exc:
        raise PricePatchHold("Invalid exchange trading session") from exc
    if parsed != sorted(parsed):
        raise PricePatchHold("Trading sessions out of order")
    return parsed


def _bar(item, ticker, session):
    if not isinstance(item, dict) or item.get("ticker") != ticker or item.get("session") != session:
        raise PricePatchHold("Symbol/session mismatch")
    vals = {f: _float(item.get(f), f, zero=(f == "volume"))
            for f in ("open", "high", "low", "close", "volume")}
    if vals["high"] < max(vals["open"], vals["close"]) or vals["low"] > min(vals["open"], vals["close"]):
        raise PricePatchHold("Bad nominal OHLC geometry")
    # A different provider's adjusted close is NOT a frozen-replay close.
    factor = item.get("split_factor")
    dividend = item.get("dividend")
    if factor is not None:
        vals["split_factor"] = _float(factor, "split factor")
    if dividend is not None:
        vals["dividend"] = _float(dividend, "dividend", zero=True)
    vals["ticker"] = ticker
    vals["session"] = session
    return vals


def _agree(a, b):
    # Explicit cross-source tolerance, NEVER silently averages disagreements.
    for key in ("open", "high", "low", "close"):
        if abs(a[key] - b[key]) > max(.02, .001 * max(a[key], b[key])):
            return False
    if abs(a["volume"] - b["volume"]) > max(100, .01 * max(a["volume"], b["volume"])):
        return False
    for key in ("split_factor", "dividend"):
        if a.get(key) != b.get(key):
            return False
    return True


def reconcile_prices(ticker: str, sessions: list[str], sources: list[dict]) -> dict:
    """Inventory missing sessions and proposed corroborated replacements.

    sources: list of {provider, receipt_sha256, basis, bars}.
    basis MUST be NOMINAL_OHLCV; frozen adjusted-close must be sourced and
    verified separately. Two nonvendor, independently identified providers
    must agree before a fallback earns CROSSCHECKED status.
    """
    _check_sessions(sessions)
    if not isinstance(ticker, str) or not ticker or not isinstance(sources, list):
        raise PricePatchHold("Missing symbol or sources")
    seen_providers = set()
    mapped = {}
    for source in sources:
        provider = source.get("provider")
        receipt = source.get("receipt_sha256")
        if (not isinstance(provider, str) or not provider
                or provider in seen_providers or not isinstance(receipt, str)
                or len(receipt) != 64 or any(x not in "0123456789abcdef" for x in receipt.lower())
                or source.get("basis") != "NOMINAL_OHLCV"):
            raise PricePatchHold("Duplicate/unaudited provider or incompatible price basis")
        seen_providers.add(provider)
        series = {}
        for item in source.get("bars", []):
            day = item.get("session") if isinstance(item, dict) else None
            if day not in sessions or day in series:
                raise PricePatchHold("Duplicate or out-of-calendar source bar")
            series[day] = _bar(item, ticker, day)
        mapped[provider] = (receipt, series)
    base = mapped.get("FROZEN_VENDOR", (None, {}))[1]
    missing = []
    conflicts = []
    candidates = []
    matched = []
    for day in sessions:
        originals = base.get(day)
        alternatives = [(p, rec, bars[day]) for p, (rec, bars) in mapped.items()
                        if p != "FROZEN_VENDOR" and day in bars]
        if originals is not None:
            disagreement = [p for p, _, b in alternatives if not _agree(originals, b)]
            if disagreement:
                conflicts.append({"session": day, "type": "PRIMARY_ALTERNATE_CONFLICT",
                                  "providers": disagreement})
            matched.append({"session": day, "provider": "FROZEN_VENDOR",
                            "status": "ORIGINAL_PRESENT"})
            continue
        missing.append(day)
        groups = []
        for provider, receipt, bar in alternatives:
            bucket = next((g for g in groups if _agree(g[0][2], bar)), None)
            if bucket is None:
                bucket = []
                groups.append(bucket)
            bucket.append((provider, receipt, bar))
        if len(groups) > 1:
            conflicts.append({"session": day, "type": "FALLBACK_DISAGREEMENT",
                              "providers": [x[0] for g in groups for x in g]})
        winners = [g for g in groups if len(g) >= 2]
        if len(winners) == 1 and len(groups) == 1:
            winners[0].sort(key=lambda x: x[0])
            candidates.append({"session": day, "bar": winners[0][0][2],
                               "sources": [{"provider": p, "sha256": r} for p, r, _ in winners[0]],
                               "status": "CROSSCHECKED_NOT_ADJUSTMENT_CERTIFIED"})
        else:
            matched.append({"session": day, "status": "MISSING_OR_SINGLE_UNVERIFIED_SOURCE"})
    report = {
        "schema": "gem-nominal-price-gap-review-v1", "ticker": ticker,
        "sessions_requested": len(sessions), "original_present": len(sessions)-len(missing),
        "missing_original": len(missing), "corroborated_patch_candidates": len(candidates),
        "unresolved_sessions": [r["session"] for r in matched
                                if r["status"] == "MISSING_OR_SINGLE_UNVERIFIED_SOURCE"],
        "conflicts": conflicts, "patch_candidates": candidates,
        "frozen_adjusted_price_parity": False,
        "source_certification": "REVIEW_REQUIRED",
        "manual_execution_authorized": False,
    }
    report["report_sha256"] = sha256(json.dumps(report, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return report
