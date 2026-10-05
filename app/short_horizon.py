"""Reproducible price scenarios for research; never an execution input.

Only completed, dated observations enter features or rolling-origin tests.
Calendar-day horizons are approximated by weekdays (exchange holidays are not
modeled). Historical block returns supply empirical, initially uncalibrated
10th/50th/90th percentiles, rather than turning ATR into guaranteed upside.
"""
from __future__ import annotations

import bisect
import math
from datetime import date, datetime, timedelta, timezone
from statistics import mean
from zoneinfo import ZoneInfo

VERSION = "short-horizon-research-v1"
HORIZONS = (15, 25, 30, 45, 60)
TRAIN_SESSIONS = 126
VALIDATION_STRIDE = 5
MIN_INDEPENDENT_TESTS = 20
NY = ZoneInfo("America/New_York")


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (ValueError, TypeError, OverflowError):
        return None


def _date(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def _observed(bundle):
    value = ((bundle.get("data_sources") or {}).get("price") or {}).get("quote_asof") or bundle.get("asof")
    try:
        observed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if observed.tzinfo is None:
            return None
        return observed.astimezone(NY)
    except (ValueError, TypeError):
        return None


def _series(rows, cutoff):
    """Reject conflicting duplicate dates; do not interpolate missing closes."""
    by_date = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        day, close = _date(row.get("date")), _number(row.get("close"))
        if day is None or day > cutoff or close is None or close <= 0:
            continue
        if day in by_date and by_date[day] != close:
            return [], "Conflicting closes for the same date"
        by_date[day] = close
    series = sorted(by_date.items())
    if any((b[0] - a[0]).days > 10 for a, b in zip(series, series[1:])):
        return [], "Price history contains a gap longer than 10 calendar days"
    if any(abs(math.log(b[1]) - math.log(a[1])) > 5 for a, b in zip(series, series[1:])):
        return [], "Price history contains an extreme scale discontinuity"
    return series, None


def weekday_sessions(origin, days):
    return sum((origin + timedelta(days=i)).weekday() < 5 for i in range(1, days + 1))


def _quantile(values, q):
    ordered = sorted(values)
    index = (len(ordered) - 1) * q
    lo = int(index)
    return ordered[lo] + (ordered[min(lo + 1, len(ordered) - 1)] - ordered[lo]) * (index - lo)


def _returns(series):
    return [math.log(b[1]) - math.log(a[1]) for a, b in zip(series, series[1:])]


def _distribution(series, sector, sessions):
    sample = series[-TRAIN_SESSIONS:]
    changes = _returns(sample)
    daily_trend = .25 * mean(changes) + .35 * mean(changes[-63:]) + .40 * mean(changes[-21:])
    # Optional sector context is restricted to the same dates as stock inputs.
    stock_dates = {d for d, _ in sample}
    context = [(d, p) for d, p in sector if d in stock_dates]
    sector_used = len(context) >= 64 and context[-1][0] == sample[-1][0]
    if sector_used:
        daily_trend = .90 * daily_trend + .10 * mean(_returns(context)[-21:])
    # Fixed v1 coefficients, not selected against this stock's future outcomes.
    drift = .5 * daily_trend * 20 * (1 - math.exp(-sessions / 20))
    blocks = [sum(changes[i:i + sessions]) for i in range(len(changes) - sessions + 1)]
    center = mean(blocks)
    residuals = [x - center for x in blocks]
    prices = [math.exp(drift + x) for x in residuals]
    return {
        "down_factor": _quantile(prices, .1),
        "base_factor": _quantile(prices, .5),
        "up_factor": _quantile(prices, .9),
        "mean_factor": mean(prices),
        "simple_trend_factor": math.exp(mean(changes[-63:]) * sessions),
        "sector_used": sector_used,
    }


def rolling_validation(series, sector, horizon):
    """Prefix-only fit; outcome is the last observed close by the deadline.

    Every five sessions gives diagnostic folds. Overlapping folds are counted
    separately from greedily selected, non-overlapping outcome windows; only
    the latter are used for the minimum evidence threshold.
    """
    dates = [d for d, _ in series]
    folds = []
    for i in range(TRAIN_SESSIONS - 1, len(series), VALIDATION_STRIDE):
        origin, anchor = series[i]
        deadline = origin + timedelta(days=horizon)
        if deadline > dates[-1]:
            break
        j = bisect.bisect_right(dates, deadline) - 1
        if j <= i or (deadline - dates[j]).days > 4:
            continue
        distribution = _distribution(series[:i + 1], sector, weekday_sessions(origin, horizon))
        actual = series[j][1] / anchor
        folds.append({
            "origin": origin, "outcome": dates[j],
            "model_error": abs(distribution["base_factor"] - actual) * 100,
            "flat_error": abs(1 - actual) * 100,
            "trend_error": abs(distribution["simple_trend_factor"] - actual) * 100,
            "covered": distribution["down_factor"] <= actual <= distribution["up_factor"],
            "sector_used": distribution["sector_used"],
        })
    independent = []
    last_outcome = date.min
    for fold in folds:
        if fold["origin"] > last_outcome:
            independent.append(fold)
            last_outcome = fold["outcome"]

    def metrics(selected):
        if not selected:
            return {"model_mae_pct_points": None, "no_change_mae_pct_points": None,
                    "simple_trend_mae_pct_points": None, "interval_coverage_pct": None}
        return {"model_mae_pct_points": round(mean(f["model_error"] for f in selected), 3),
                "no_change_mae_pct_points": round(mean(f["flat_error"] for f in selected), 3),
                "simple_trend_mae_pct_points": round(mean(f["trend_error"] for f in selected), 3),
                "interval_coverage_pct": round(mean(f["covered"] for f in selected) * 100, 1)}

    independent_metrics = metrics(independent)
    enough = len(independent) >= MIN_INDEPENDENT_TESTS
    performance = enough and independent_metrics["model_mae_pct_points"] < .95 * min(
        independent_metrics["no_change_mae_pct_points"], independent_metrics["simple_trend_mae_pct_points"])
    calibrated = enough and 70 <= independent_metrics["interval_coverage_pct"] <= 90
    status = "historical_checks_passed" if performance and calibrated else "benchmark_checks_failed" if enough else "insufficient_independent_windows"
    return {"status": status, "folds": len(folds), "independent_windows": len(independent),
            "sector_context_folds": sum(f["sector_used"] for f in folds),
            "minimum_independent_windows": MIN_INDEPENDENT_TESTS,
            "first_origin": folds[0]["origin"].isoformat() if folds else None,
            "last_outcome": folds[-1]["outcome"].isoformat() if folds else None,
            "diagnostic_metrics": metrics(folds), "independent_metrics": independent_metrics,
            "reason": "Need at least 20 non-overlapping windows, >5% lower error than both benchmarks and 70–90% coverage of the nominal 80% interval. Historical checks alone do not authorize execution."}


def forecast_current(payload):
    return (payload.get("short_horizon_forecast") or {}).get("version") == VERSION


def _build_forecast(bundle, analysis):
    observed = _observed(bundle)
    price = _number(bundle.get("price"))
    lane = analysis.get("lane")
    out = {"version": VERSION, "mode": "research_only", "execution_enabled": False,
           "status": "unavailable", "horizon_unit": "calendar_days", "default_horizon_days": 15 if lane == "EXPLOSIVE" else 30,
           "rows": [], "price_asof": observed.isoformat() if observed else None,
           "price": price, "history_asof": None, "history_sessions": 0,
           "method": "Damped log-return trend with 50% shrinkage toward zero; optional 10% sector context; centered historical block-return percentiles",
           "limitations": ["Research estimates do not change scores, entry gates, targets, stops, sizing or paper orders",
                           "10th/90th percentile bounds form an estimated 80% interval; coverage is tested, not assumed",
                           "Calendar horizons use weekday session counts; exchange holidays can reduce actual sessions",
                           "Earnings, FDA decisions and other future event gaps are not modeled",
                           "Historical adjusted closes may include subsequent corporate-action adjustments; this is a price-model diagnostic, not a point-in-time strategy backtest"]}
    if not observed or not price or price <= 0:
        out["reason"] = "A positive quote with an explicit timezone-aware observation time is required"
        return out
    cutoff = observed.date() if observed.hour >= 16 else observed.date() - timedelta(days=1)
    series, error = _series(bundle.get("history"), cutoff)
    out["history_sessions"] = len(series)
    if error or len(series) < TRAIN_SESSIONS:
        out["reason"] = error or "At least 126 distinct completed trading sessions are required"
        return out
    out["history_asof"] = series[-1][0].isoformat()
    if (observed.date() - series[-1][0]).days > 7:
        out["reason"] = "Completed price history is more than seven calendar days behind the quote"
        return out
    sector_bundle = bundle.get("sector_benchmark") or {}
    sector, sector_error = _series(sector_bundle.get("history"), cutoff)
    if sector_error:
        sector = []
    out.update(status="available", reason="Forecasts available for evaluation; execution remains on the existing strategy",
               sector_symbol=sector_bundle.get("symbol"), sector_status="available" if sector else "unavailable; stock-only model",
               price_source=((bundle.get("data_sources") or {}).get("price") or {}).get("source") or bundle.get("provider") or "supplied history")
    stop = _number((analysis.get("levels") or {}).get("stop"))
    origin = observed.date()
    for horizon in HORIZONS:
        sessions = weekday_sessions(origin, horizon)
        distribution = _distribution(series, sector, sessions)
        base = price * distribution["base_factor"]
        rr = (base - price) / (price - stop) if stop and 0 < stop < price else None
        out["rows"].append({
            "days": horizon, "forecast_date": (origin + timedelta(days=horizon)).isoformat(),
            "estimated_sessions": sessions, "default": horizon == out["default_horizon_days"],
            "within_lane_window": lane != "EXPLOSIVE" or sessions <= 20,
            "down_price": round(price * distribution["down_factor"], 2), "base_price": round(base, 2),
            "up_price": round(price * distribution["up_factor"], 2), "mean_price": round(price * distribution["mean_factor"], 2),
            "base_return_pct": round((distribution["base_factor"] - 1) * 100, 2),
            "expected_return_pct": round((distribution["mean_factor"] - 1) * 100, 2),
            "risk_reward": round(rr, 3) if rr is not None else None, "stop": stop,
            "sector_used": distribution["sector_used"], "validation": rolling_validation(series, sector, horizon),
        })
    return out


def build_forecast(bundle, analysis):
    """An optional research failure must never interrupt scoring or exits."""
    try:
        return _build_forecast(bundle, analysis)
    except Exception as exc:
        return {"version": VERSION, "mode": "research_only", "execution_enabled": False,
                "status": "unavailable", "rows": [], "horizon_unit": "calendar_days",
                "reason": f"Forecast calculation unavailable ({type(exc).__name__}); current strategy continues"}
