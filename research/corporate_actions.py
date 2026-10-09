"""Research-only diagnostics and event-based, split-only OHLC preparation.

Never infer a split from adjusted_close/close: EODHD adjusted_close also includes
dividends. EODHD's base volume is already split-adjusted, so do not adjust it twice.
These functions do not connect to trading or order code.
"""
from __future__ import annotations

import math
from datetime import date


def _validate(rows):
    try:
        from research.eodhd_probe import validate_prices
    except ModuleNotFoundError:
        from eodhd_probe import validate_prices
    return validate_prices(rows)


def price_flags(rows, *, jump_threshold=0.25, factor_threshold=0.10,
                verified_returns=None, return_tolerance_pct=0.005,
                stable_factor_tolerance=0.001):
    rows = _validate(rows)
    flags = []
    for previous, current in zip(rows, rows[1:]):
        raw_return = current["close"] / previous["close"] - 1
        adjusted_return = current["adjusted_close"] / previous["adjusted_close"] - 1
        factor_ratio = ((current["adjusted_close"] / current["close"])
                        / (previous["adjusted_close"] / previous["close"]))
        reasons = []
        if abs(raw_return) > jump_threshold:
            reasons.append("unusual_raw_close_jump")
        if abs(adjusted_return) > jump_threshold:
            reasons.append("unusual_adjusted_close_jump")
        if abs(factor_ratio - 1) > factor_threshold:
            reasons.append("adjustment_factor_discontinuity")
        if reasons:
            classification = ("corporate_action_discontinuity" if "adjustment_factor_discontinuity" in reasons
                              else "unverified_extreme_market_return")
            evidence = (verified_returns or {}).get(current["date"])
            corroborated = (isinstance(evidence, dict) and bool(evidence.get("source"))
                            and isinstance(evidence.get("return_pct"), (int, float))
                            and not isinstance(evidence.get("return_pct"), bool)
                            and math.isfinite(evidence["return_pct"])
                            and abs(raw_return * 100 - evidence["return_pct"]) <= return_tolerance_pct
                            and abs(factor_ratio - 1) <= stable_factor_tolerance
                            and abs(adjusted_return * 100 - evidence["return_pct"]) <= return_tolerance_pct)
            if corroborated:
                classification = "verified_extreme_market_return"
            flag = {"date": current["date"], "previous_date": previous["date"],
                          "reasons": reasons, "raw_return_pct": raw_return * 100,
                          "adjusted_return_pct": adjusted_return * 100,
                          "adjustment_factor_ratio": factor_ratio,
                          "classification": classification, "requires_review": not corroborated}
            if evidence:
                flag["independent_return_evidence"] = evidence
                flag["independent_return_matches"] = bool(corroborated)
            flags.append(flag)
    return flags


def split_events(payload, *, source):
    """Parse new-shares/old-shares ratios without guessing tidy integers."""
    if not source or not isinstance(payload, list):
        raise ValueError("Split history and provenance are required")
    events = []
    seen = set()
    for event in payload:
        if not isinstance(event, dict):
            raise ValueError("Malformed split event")
        day = event.get("date", "")
        if date.fromisoformat(day).isoformat() != day or day in seen:
            raise ValueError("Invalid or duplicate event date")
        seen.add(day)
        try:
            numerator, denominator = str(event["split"]).split("/")
            numerator, denominator = float(numerator), float(denominator)
            if not all(math.isfinite(v) and v > 0 for v in (numerator, denominator)):
                raise ValueError()
            ratio = numerator / denominator
            if not math.isfinite(ratio) or ratio <= 0:
                raise ValueError()
        except (ValueError, KeyError, ZeroDivisionError):
            raise ValueError("Invalid new/old share ratio") from None
        events.append({"date": day, "new_shares_per_old_share": ratio, "source": source})
    return sorted(events, key=lambda e: e["date"])


def prepare_split_ohlc(rows, events, *, history_complete, basis_date,
                       volume_basis="eodhd_split_adjusted", consistency_tolerance=0.02,
                       verified_returns=None):
    """Return blocked rather than export unsafe bars.

    Events must be verified against a corporate-action source, with complete
    history through the chosen share basis. Prices before each ex-date are
    divided by new/old. Events effective on a bar's date never adjust that bar.
    No dividends enter the transformation. Price flags still require review;
    unexplained jumps and adjustment discontinuities block preparation.
    """
    rows = _validate(rows)
    date.fromisoformat(basis_date)
    reasons = []
    if not history_complete:
        reasons.append("complete_verified_event_history_required")
    if basis_date < rows[-1]["date"]:
        reasons.append("share_basis_precedes_price_history")
    if volume_basis != "eodhd_split_adjusted":
        reasons.append("unsupported_volume_basis")
    event_dates = set()
    for event in events:
        day = event.get("date", "")
        date.fromisoformat(day)
        ratio = event.get("new_shares_per_old_share")
        if (isinstance(ratio, bool) or not isinstance(ratio, (int, float))
                or not math.isfinite(ratio) or ratio <= 0 or not event.get("source")):
            raise ValueError("Invalid or unverified split event")
        if day in event_dates:
            raise ValueError("Duplicate event date")
        event_dates.add(day)
    relevant = [e for e in events if rows[0]["date"] < e["date"] <= basis_date]
    for flag in price_flags(rows, verified_returns=verified_returns):
        if flag["classification"] == "verified_extreme_market_return":
            # Corroborated economic returns retain their full move and TR/ATR.
            # They never create a split event or an adjustment multiplier.
            continue
        crossing = [e for e in relevant if flag["previous_date"] < e["date"] <= flag["date"]]
        ratio = math.prod(e["new_shares_per_old_share"] for e in crossing)
        if not crossing:
            reasons.append(f"unexplained_price_flag:{flag['date']}")
        elif abs(flag["adjustment_factor_ratio"] / ratio - 1) > consistency_tolerance:
            reasons.append(f"event_adjustment_ratio_mismatch:{flag['date']}")
        if "unusual_adjusted_close_jump" in flag["reasons"]:
            reasons.append(f"adjusted_price_jump_requires_review:{flag['date']}")
    # Check every observed event boundary, even if a small split did not flag.
    checks = []
    for previous, current in zip(rows, rows[1:]):
        crossing = [e for e in relevant if previous["date"] < e["date"] <= current["date"]]
        if not crossing:
            continue
        ratio = math.prod(e["new_shares_per_old_share"] for e in crossing)
        actual = ((current["adjusted_close"] / current["close"])
                  / (previous["adjusted_close"] / previous["close"]))
        passed = abs(actual / ratio - 1) <= consistency_tolerance
        checks.append({"date": current["date"], "new_shares_per_old_share": ratio,
                       "observed_adjustment_factor_ratio": actual, "passed": passed,
                       "split_normalized_close_return_pct":
                       (current["close"] / (previous["close"] / ratio) - 1) * 100,
                       "adjusted_close_return_pct":
                       (current["adjusted_close"] / previous["adjusted_close"] - 1) * 100})
        if not passed:
            reasons.append(f"event_adjustment_ratio_mismatch:{current['date']}")
    if reasons:
        return {"status": "blocked", "reasons": sorted(set(reasons)), "rows": [], "event_checks": checks}
    prepared = []
    for row in rows:
        multiplier = math.prod(1 / e["new_shares_per_old_share"]
                               for e in relevant if row["date"] < e["date"])
        bar = {"date": row["date"], **{k: row[k] * multiplier for k in ("open", "high", "low", "close")},
               "volume": row["volume"], "split_price_multiplier": multiplier}
        if any(not math.isfinite(bar[k]) or bar[k] <= 0 for k in ("open", "high", "low", "close")):
            raise ValueError("Split-adjusted price overflow or underflow")
        prepared.append(bar)
    return {"status": "ready_for_research", "reasons": [], "rows": prepared,
            "event_checks": checks, "share_basis_date": basis_date,
            "price_basis": "split_only_no_dividend_adjustment",
            "volume_basis": volume_basis,
            "lookahead_note": "End-date share basis; convert historical order units for point-in-time simulations."}


def true_ranges(prepared):
    """TR input for ATR, using one consistent split-only OHLC price basis."""
    if prepared.get("status") != "ready_for_research":
        raise ValueError("Cannot calculate true ranges from blocked prices")
    result = []
    previous_close = None
    for row in prepared["rows"]:
        tr = row["high"] - row["low"]
        if previous_close is not None:
            tr = max(tr, abs(row["high"] - previous_close), abs(row["low"] - previous_close))
        result.append({"date": row["date"], "true_range": tr})
        previous_close = row["close"]
    return result
