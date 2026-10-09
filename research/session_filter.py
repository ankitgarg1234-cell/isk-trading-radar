"""Exclude confirmed exchange closures without editing or redating observations."""
from datetime import date

from research.eodhd_probe import validate_prices


def filter_confirmed_closures(rows, calendar, exchange_closures):
    prices = validate_prices(rows)
    closures = exchange_closures.get(calendar, {})
    for day, evidence in closures.items():
        if date.fromisoformat(day).isoformat() != day or not evidence.get("source") or not evidence.get("reason"):
            raise ValueError("Closure requires an ISO date, reason and provenance")
    retained, excluded = [], []
    previous = None
    for row in prices:
        evidence = closures.get(row["date"])
        if evidence:
            flat = len({row[k] for k in ("open", "high", "low", "close")}) == 1
            carry_forward = (row["volume"] == 0 and flat and previous is not None
                             and row["close"] == previous["close"]
                             and row["adjusted_close"] == previous["adjusted_close"])
            excluded.append({"date": row["date"], "original_observation": dict(row),
                             "closure_evidence": evidence,
                             "classification": "consistent_with_carry_forward_placeholder" if carry_forward else "bar_on_confirmed_non_trading_session",
                             "valid_trading_session": False,
                             "flat_ohlc": flat, "zero_volume": row["volume"] == 0,
                             "matches_previous_trading_close": carry_forward,
                             "action": "exclude_from_derived_inputs_preserve_original",
                             "redating": "No evidence establishes another session; do not redate"})
        else:
            retained.append(dict(row))
            previous = row
    return {"rows": retained, "excluded_observations": excluded,
            "input_rows": len(prices), "output_rows": len(retained),
            "price_basis": "original_provider_prices_session_filtered_only",
            "readiness": "Session filtering only; split/FX/security/universe validation remains required"}
