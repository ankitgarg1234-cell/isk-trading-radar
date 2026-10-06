"""Bounded, descriptive score telemetry; never changes scores or trading gates."""
from __future__ import annotations

import math

from .trading_rules import MIN_DETERMINISTIC_SCORE


def _number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def scan_score_diagnostics(analyses):
    scores = []
    missing = {"valuation_pe": 0, "consensus_price_target": 0, "market_cap": 0}
    yahoo_unavailable = 0
    low_volume = 0
    normalized_available = 0
    normalized_missing = 0
    analyst_available = 0
    analyst_missing_statuses = {}
    bins = {"below_50": 0, "50_to_below_60": 0, "60_to_below_70": 0,
            "70_to_below_80": 0, "80_to_100": 0}
    for analysis in analyses:
        f = analysis.get("fundamentals") or {}
        t = analysis.get("technicals") or {}
        if _number(analysis.get("analyst_score")) is not None:
            analyst_available += 1
        else:
            status = str(f.get("_analyst_status") or "unavailable")
            analyst_missing_statuses[status] = analyst_missing_statuses.get(status, 0) + 1
        if not any((_number(f.get(k)) or 0) > 0 for k in ("forwardPE", "trailingPE")):
            missing["valuation_pe"] += 1
        if (_number(f.get("targetMeanPrice")) or 0) <= 0:
            missing["consensus_price_target"] += 1
        if (_number(f.get("marketCap")) or 0) <= 0:
            missing["market_cap"] += 1
        if str(f.get("_yahoo_status") or "").startswith("unavailable"):
            yahoo_unavailable += 1
        volume = _number(t.get("raw_daily_relative_volume", t.get("relative_volume")))
        normalized_available += int(bool(t.get("relative_volume_evidence")) and t.get("relative_volume") is not None)
        normalized_missing += int(bool(t.get("relative_volume_evidence")) and t.get("relative_volume") is None)
        low_volume += int(volume is not None and volume < 1.2)
        score = _number(analysis.get("deterministic_score"))
        if score is None or not 0 <= score <= 100:
            continue
        bucket = ("below_50" if score < 50 else "50_to_below_60" if score < 60
                  else "60_to_below_70" if score < 70 else "70_to_below_80" if score < 80
                  else "80_to_100")
        bins[bucket] += 1
        scores.append({"symbol": analysis.get("symbol"), "deterministic_score": score,
            "analyst_score": _number(analysis.get("analyst_score")),
            "risk_reward": _number(analysis.get("risk_reward")),
            "breakdown": analysis.get("breakdown") or {},
            "core_blockers": analysis.get("core_blockers") or [],
            "quote_asof": ((analysis.get("data_sources") or {}).get("price") or {}).get("quote_asof")})
    scores.sort(key=lambda row: (-row["deterministic_score"], str(row["symbol"])))
    return {"scope": "latest scanner cycle; repeated stocks across cycles are not unique coverage",
        "analyzed": len(analyses), "valid_scores": len(scores),
        "invalid_scores": len(analyses) - len(scores),
        "maximum_score": scores[0]["deterministic_score"] if scores else None,
        "score_at_least_65": sum(row["deterministic_score"] >= MIN_DETERMINISTIC_SCORE for row in scores),
        "score_at_least_70": sum(row["deterministic_score"] >= 70 for row in scores),
        "score_bins": bins, "missing_inputs": missing,
        "yahoo_fundamentals_unavailable": yahoo_unavailable,
        "raw_relative_volume_below_1_2": low_volume,
        "relative_volume_basis": "matching completed regular-session five-minute intervals; raw daily ratio retained only for diagnostics",
        "normalized_relative_volume_available": normalized_available,
        "normalized_relative_volume_missing": normalized_missing,
        "analyst_scores_available": analyst_available,
        "analyst_scores_missing": len(analyses) - analyst_available,
        "analyst_missing_statuses": analyst_missing_statuses,
        "top_candidates": scores[:5]}
