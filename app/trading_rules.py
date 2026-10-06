"""Agreed entry thresholds shared by the dashboard and paper account."""

import math

MIN_DETERMINISTIC_SCORE = 65
MIN_ANALYST_SCORE = 75
MIN_ENTRY_RISK_REWARD = 0.4


def number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def signal_geometry(a):
    """Anchor breakout/chase levels to completed sessions, never today's close."""
    levels = dict(a.get("levels") or {})
    quote_asof = ((a.get("data_sources") or {}).get("price") or {}).get("quote_asof") or a.get("asof")
    day = str(quote_asof or "")[:10]
    completed = [r for r in (a.get("history") or []) if str(r.get("date") or "") < day and number(r.get("close"))]
    atr = number((a.get("technicals") or {}).get("atr"))
    chase = number(levels.get("do_not_chase"))
    if len(completed) >= 20 and atr and atr > 0 and chase is not None:
        high20 = max(float(r["close"]) for r in completed[-20:])
        levels["breakout"] = round(high20 + .1 * atr, 4)
        levels["do_not_chase"] = round(min(chase, high20 + 1.1 * atr), 4)
        return levels, {"through_date": completed[-1]["date"], "high20_close": high20}
    return levels, a.get("breakout_anchor")


def qualification_check(a, price=None):
    """Shared pre-entry gates; R/R uses the trade-entry stop, not the deeper thesis stop."""
    price = number(a.get("price") if price is None else price)
    score, analyst = number(a.get("deterministic_score")), number(a.get("analyst_score"))
    lv = a.get("levels") or {}
    target = number((a.get("target_plan") or {}).get("base_target"))
    stop = number(lv.get("entry_stop", lv.get("stop")))
    if score is None or not MIN_DETERMINISTIC_SCORE <= score <= 100:
        return False, "deterministic_below_min_or_invalid", None
    if analyst is None:
        return False, "analyst_missing", None
    if not MIN_ANALYST_SCORE <= analyst <= 100:
        return False, "analyst_below_75_or_invalid", None
    if price is None or price < 5 or str(a.get("currency") or "USD") != "USD":
        return False, "price_or_currency_invalid", None
    if a.get("lane_qualified") is not True or a.get("lane") not in {"CORE_QUALITY", "EXPLOSIVE"}:
        return False, "quality_or_liquidity_gate", None
    if (a.get("promotion_risk") or {}).get("hard_reject"):
        return False, "promotion_risk", None
    if a.get("negative_news_override") or (a.get("thesis_assessment") or {}).get("invalidated"):
        return False, "material_negative_or_thesis_invalid", None
    if str(a.get("decision_confidence") or "low").lower() == "low":
        return False, "data_confidence_low", None
    if stop is None or target is None or not 0 < stop < price < target:
        return False, "target_stop_invalid", None
    rr = (target - price) / (price - stop)
    if rr + 1e-12 < MIN_ENTRY_RISK_REWARD:
        return False, "rr_below_0_4", rr
    return True, "qualified", rr


def entry_check(a, price=None):
    """Canonical trigger used by paper signals, alerts and dashboard decisions."""
    okay, reason, rr = qualification_check(a, price)
    if not okay:
        return okay, reason, rr
    price = number(a.get("price") if price is None else price)
    lv, _ = signal_geometry(a)
    t = a.get("technicals") or {}
    chase = number(lv.get("do_not_chase"))
    if chase is None or price > chase:
        return False, "do_not_chase", rr
    rsi, ema, change = (number(t.get(k)) for k in ("rsi", "ema20", "change20_pct"))
    if rsi is None or ema is None or change is None or rsi < 40 or (price < ema and change < -2):
        return False, "momentum_not_ready", rr
    for low, high, route in (("buy_low", "buy_high", "pullback"), ("better_low", "better_high", "better_buy")):
        lo, hi = number(lv.get(low)), number(lv.get(high))
        if lo is not None and hi is not None and lo <= price <= hi:
            return True, route, rr
    breakout, volume = number(lv.get("breakout")), number(t.get("relative_volume"))
    if breakout is not None and price >= breakout and volume is not None and volume >= 1.5:
        return True, "breakout", rr
    return False, "no_entry_trigger", rr


REASONS = {
    "qualified": "Score, analyst, R/R and quality gates passed; waiting for an entry trigger",
    "deterministic_below_min_or_invalid": f"Deterministic score must be at least {MIN_DETERMINISTIC_SCORE}/100",
    "analyst_missing": "Analyst score is unavailable; entry requires at least 75/100",
    "analyst_below_75_or_invalid": "Analyst score must be at least 75/100",
    "price_or_currency_invalid": "Entry requires a USD stock priced at $5 or more",
    "quality_or_liquidity_gate": "Core / Explosive quality and liquidity gates have not passed",
    "promotion_risk": "Promotion or reverse-split risk blocks entry",
    "material_negative_or_thesis_invalid": "Material negative evidence or thesis invalidation blocks entry",
    "data_confidence_low": "Critical evidence confidence is too low for entry",
    "target_stop_invalid": "A valid target above price and stop below price are required",
    "rr_below_0_4": "Target / stop risk-reward must be at least 0.4×",
    "do_not_chase": "Price exceeds the do-not-chase level or that level is unavailable",
    "momentum_not_ready": "Momentum confirmation is missing or insufficient",
    "no_entry_trigger": "Waiting for a buy-zone entry or a volume-confirmed breakout",
    "pullback": "Qualified primary buy-zone entry",
    "better_buy": "Qualified better-buy-zone entry",
    "breakout": "Qualified breakout with at least 1.5× relative volume",
}


def entry_status(a, price=None):
    qualified, blocker, rr = qualification_check(a, price)
    ready, trigger, _ = entry_check(a, price)
    reason = trigger if qualified else blocker
    if rr is None:
        current = number(a.get("price") if price is None else price)
        target = number((a.get("target_plan") or {}).get("base_target"))
        levels = a.get("levels") or {}
        stop = number(levels.get("entry_stop", levels.get("stop")))
        if current is not None and target is not None and stop is not None and 0 < stop < current < target:
            rr = (target-current)/(current-stop)
    return {"qualified": qualified, "ready": ready, "blocker": reason,
            "reason": REASONS[reason], "risk_reward": rr}
