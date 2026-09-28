from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

RISK_PROFILES = {
    "LOW": {
        "label": "Low Risk",
        "target_score": 25,
        "risk_per_trade_pct": 0.35,
        "max_position_pct": 6.0,
        "max_explosive_pct": 1.5,
        "preferred_cash_pct": 25.0,
        "max_stock_risk": 58,
    },
    "MEDIUM": {
        "label": "Medium Risk",
        "target_score": 45,
        "risk_per_trade_pct": 0.75,
        "max_position_pct": 10.0,
        "max_explosive_pct": 4.0,
        "preferred_cash_pct": 15.0,
        "max_stock_risk": 72,
    },
    "HIGH": {
        "label": "High Risk",
        "target_score": 65,
        "risk_per_trade_pct": 1.25,
        "max_position_pct": 15.0,
        "max_explosive_pct": 8.0,
        "preferred_cash_pct": 8.0,
        "max_stock_risk": 86,
    },
    "AGGRESSIVE": {
        "label": "Aggressive",
        "target_score": 82,
        "risk_per_trade_pct": 2.0,
        "max_position_pct": 22.0,
        "max_explosive_pct": 12.0,
        "preferred_cash_pct": 5.0,
        "max_stock_risk": 100,
    },
}

ACTION_RANK = {
    "STRONG BUY": 0,
    "BUY": 1,
    "STARTER BUY": 2,
    "BREAKOUT BUY": 3,
    "TAKE PROFIT": 4,
    "SELL": 5,
    "STRONG SELL": 6,
    "HOLD": 7,
    "WAIT": 8,
    "WATCH": 9,
}


def normalise_profile(value: str | None) -> str:
    v = str(value or "MEDIUM").strip().upper().replace(" ", "_")
    aliases = {"LOW_RISK": "LOW", "MEDIUM_RISK": "MEDIUM", "HIGH_RISK": "HIGH", "RISK": "HIGH"}
    v = aliases.get(v, v)
    return v if v in RISK_PROFILES else "MEDIUM"


def risk_band(score: float) -> str:
    if score < 35:
        return "LOW"
    if score < 55:
        return "MEDIUM"
    if score < 75:
        return "HIGH"
    return "AGGRESSIVE"


def _float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def stock_risk_score(a: dict) -> float:
    """Deterministic 0-100 stock risk score used for sizing, not quality scoring."""
    price = max(_float(a.get("price")), 0.01)
    t = a.get("technicals") or {}
    n = a.get("news") or {}
    levels = a.get("levels") or {}
    score = 30.0

    category = str(a.get("category") or "Watch")
    if category == "Explosive Runner":
        score += 22
    elif category == "Watch":
        score += 7

    atr = _float(t.get("atr"))
    if atr:
        atr_pct = atr / price * 100
        score += min(22, atr_pct * 2.2)

    relvol = _float(t.get("relative_volume"))
    if relvol >= 2.5:
        score += 8
    elif relvol >= 1.5:
        score += 4

    change20 = abs(_float(t.get("change20_pct")))
    if change20 >= 25:
        score += 12
    elif change20 >= 15:
        score += 7
    elif change20 >= 8:
        score += 3

    if price < 5:
        score += 16
    elif price < 10:
        score += 9

    if n.get("high_negative_events", 0):
        score += 12
    elif n.get("material_events", 0) >= 2:
        score += 5

    stop = _float(levels.get("stop"))
    if stop and price > stop:
        stop_pct = (price - stop) / price * 100
        if stop_pct > 18:
            score += 10
        elif stop_pct > 12:
            score += 6

    confidence = str(a.get("decision_confidence") or "medium").lower()
    if confidence == "low":
        score += 8

    return round(max(0, min(100, score)), 1)


def system_signal(a: dict, owned: bool = False) -> str:
    action = str(a.get("action") or "WATCH").upper()
    ai = _float(a.get("ai_score"))
    det = _float(a.get("deterministic_score"))

    if owned:
        if action == "EXIT":
            return "STRONG SELL"
        if action in {"REDUCE", "TAKE PARTIAL PROFIT"}:
            return "SELL" if action == "REDUCE" else "TAKE PROFIT"
        if action.startswith("HOLD") or action == "ADD":
            return "HOLD" if action != "ADD" else "BUY"

    if action in {"BUY NOW", "BREAKOUT BUY"}:
        return "STRONG BUY" if ai >= 88 and det >= 80 else "BUY"
    if action in {"CONSIDER BUYING NOW"}:
        return "BUY"
    if action in {"CONSIDER STARTER BUY"}:
        return "STARTER BUY"
    if action in {"EXIT"}:
        return "STRONG SELL"
    if action in {"REDUCE"}:
        return "SELL"
    if action in {"TAKE PARTIAL PROFIT"}:
        return "TAKE PROFIT"
    if action.startswith("HOLD"):
        return "HOLD"
    if action.startswith("WAIT"):
        return "WAIT"
    return "WATCH"


def _zone_distance(price: float, low: float, high: float) -> tuple[str, float]:
    if low <= price <= high:
        return "NOW", 0.0
    if price > high:
        pct = (price - high) / price * 100
        return f"{pct:.1f}% lower", pct
    pct = (low - price) / price * 100 if price else 0
    return f"{pct:.1f}% higher", abs(pct)


def active_level(a: dict, owned: bool = False) -> dict:
    price = _float(a.get("price"))
    lv = a.get("levels") or {}
    zone = str(a.get("entry_zone_status") or "WATCH")
    action = str(a.get("action") or "WATCH").upper()
    buy_low, buy_high = _float(lv.get("buy_low")), _float(lv.get("buy_high"))
    better_low, better_high = _float(lv.get("better_low")), _float(lv.get("better_high"))
    breakout = _float(lv.get("breakout"))

    if owned and action in {"REDUCE", "TAKE PARTIAL PROFIT", "EXIT"}:
        return {"label": "Position action", "value": "NOW", "distance": "NOW", "distance_pct": 0.0, "state": "ACTION"}

    if zone == "BETTER_BUY" or action == "WAIT FOR BETTER BUY":
        d, dp = _zone_distance(price, better_low, better_high)
        return {"label": "Better Buy", "value": f"{better_low:.2f}–{better_high:.2f}", "distance": d, "distance_pct": dp, "state": "BETTER_BUY"}
    if zone == "PRIMARY_BUY":
        d, dp = _zone_distance(price, buy_low, buy_high)
        return {"label": "Primary Buy", "value": f"{buy_low:.2f}–{buy_high:.2f}", "distance": d, "distance_pct": dp, "state": "PRIMARY_BUY"}
    if zone in {"VALUE_CORRIDOR", "DEEP_VALUE"}:
        d, dp = _zone_distance(price, better_low, better_high)
        return {"label": "Better Buy", "value": f"{better_low:.2f}–{better_high:.2f}", "distance": d, "distance_pct": dp, "state": zone}
    if action == "BREAKOUT BUY" or zone in {"APPROACHING_BREAKOUT", "BREAKOUT"}:
        dp = ((breakout - price) / price * 100) if price and breakout > price else 0.0
        return {"label": "Breakout", "value": f"> {breakout:.2f}", "distance": "NOW" if dp <= 0 else f"{dp:.1f}% higher", "distance_pct": abs(dp), "state": "BREAKOUT"}

    d, dp = _zone_distance(price, buy_low, buy_high)
    return {"label": "Primary Buy", "value": f"{buy_low:.2f}–{buy_high:.2f}", "distance": d, "distance_pct": dp, "state": zone}


def analyst_label(a: dict) -> str:
    key = str(a.get("analyst_recommendation_key") or "").replace("_", " ").strip().title()
    if key:
        return key
    score = a.get("analyst_score")
    if score is None:
        return "—"
    score = _float(score)
    if score >= 80:
        return "Strong Buy"
    if score >= 65:
        return "Buy"
    if score >= 45:
        return "Hold"
    if score >= 30:
        return "Sell"
    return "Strong Sell"


def risk_fit(stock_risk: float, profile: str) -> str:
    p = RISK_PROFILES[normalise_profile(profile)]
    if stock_risk <= p["max_stock_risk"] - 15:
        return "GOOD FIT"
    if stock_risk <= p["max_stock_risk"]:
        return "STRETCH"
    return "ABOVE TARGET"


def suggested_position_size(
    a: dict,
    *,
    cash: float,
    reserve_cash: float,
    portfolio_value: float,
    profile: str,
    fx_rate_to_base: float = 1.0,
    existing_value: float = 0.0,
    whole_shares: bool = True,
) -> dict:
    profile = normalise_profile(profile)
    p = RISK_PROFILES[profile]
    price = _float(a.get("price"))
    stop = _float((a.get("levels") or {}).get("stop"))
    if price <= 0 or stop <= 0 or stop >= price or fx_rate_to_base <= 0:
        return {"shares": 0, "reason": "Sizing unavailable until price, stop and FX are valid", "fit": "UNKNOWN"}

    stock_risk = stock_risk_score(a)
    fit = risk_fit(stock_risk, profile)
    deployable_cash = max(0.0, cash - reserve_cash)
    if deployable_cash <= 0:
        return {"shares": 0, "reason": "No deployable cash after strategic reserve", "fit": fit, "stock_risk": stock_risk}
    if fit == "ABOVE TARGET" and profile in {"LOW", "MEDIUM"}:
        return {"shares": 0, "reason": f"Stock risk {stock_risk:.0f}/100 is above the {p['label']} limit", "fit": fit, "stock_risk": stock_risk}

    price_base = price * fx_rate_to_base
    stop_risk_base = (price - stop) * fx_rate_to_base
    total = max(portfolio_value, deployable_cash)
    risk_budget = total * (p["risk_per_trade_pct"] / 100)
    max_pct = p["max_explosive_pct"] if a.get("category") == "Explosive Runner" else p["max_position_pct"]
    max_value = total * (max_pct / 100)
    remaining_position_room = max(0.0, max_value - existing_value)

    by_risk = risk_budget / stop_risk_base if stop_risk_base > 0 else 0
    by_cap = remaining_position_room / price_base if price_base > 0 else 0
    by_cash = deployable_cash / price_base if price_base > 0 else 0
    shares = min(by_risk, by_cap, by_cash)
    if fit == "STRETCH":
        shares *= 0.6
    shares = math.floor(shares) if whole_shares else round(shares, 4)
    shares = max(0, shares)
    capital = shares * price_base
    risk_amount = shares * stop_risk_base
    return {
        "shares": shares,
        "capital": round(capital, 2),
        "risk_amount": round(risk_amount, 2),
        "risk_pct_portfolio": round((risk_amount / total * 100) if total else 0, 2),
        "weight_after_pct": round(((existing_value + capital) / (total + capital) * 100) if total + capital else 0, 1),
        "cash_after": round(max(0, cash - capital), 2),
        "fit": fit,
        "stock_risk": stock_risk,
        "profile": profile,
        "reason": f"Sized from {p['risk_per_trade_pct']}% risk/trade, {max_pct}% position cap and available cash",
    }


def account_risk(position_rows: list[dict], cash: float, *, target_profile: str = "MEDIUM") -> dict:
    values = [max(0.0, _float(p.get("value_base"))) for p in position_rows]
    invested = sum(values)
    total = invested + max(0.0, cash)
    if total <= 0:
        return {
            "score": 0.0, "band": "LOW", "target_profile": normalise_profile(target_profile),
            "target_score": RISK_PROFILES[normalise_profile(target_profile)]["target_score"],
            "gap": 0.0, "invested": 0.0, "total": max(0.0, cash), "cash_pct": 100.0,
            "reasons": ["No invested positions yet"], "breakdown": {},
        }

    position_weights = [(v / total) for v in values]
    invested_weights = [(v / invested) if invested else 0 for v in values]
    stock_risks = [_float(p.get("stock_risk"), 50) for p in position_rows]
    weighted_stock = sum(w * r for w, r in zip(invested_weights, stock_risks)) if invested else 0
    largest = max(position_weights, default=0) * 100
    concentration = min(100, max(0, (largest - 5) * 3.0))

    sectors: dict[str, float] = defaultdict(float)
    speculative = 0.0
    event_value = 0.0
    for p, v, r in zip(position_rows, values, stock_risks):
        sectors[str(p.get("sector") or "Unknown")] += v
        if r >= 70 or p.get("category") == "Explosive Runner":
            speculative += v
        if _float(p.get("material_events")) >= 1:
            event_value += v
    max_sector = (max(sectors.values(), default=0) / total * 100) if total else 0
    sector_risk = min(100, max(0, (max_sector - 15) * 2.2))
    speculative_risk = (speculative / total * 100) if total else 0
    event_risk = min(100, (event_value / total * 100) * 1.5) if total else 0
    cash_pct = max(0.0, cash) / total * 100
    cash_risk = 90 if cash_pct < 5 else 65 if cash_pct < 10 else 35 if cash_pct < 20 else 10

    score = (
        weighted_stock * 0.38 + concentration * 0.22 + sector_risk * 0.14 +
        speculative_risk * 0.14 + cash_risk * 0.08 + event_risk * 0.04
    )
    score = round(max(0, min(100, score)), 1)
    profile = normalise_profile(target_profile)
    target_score = RISK_PROFILES[profile]["target_score"]
    reasons = []
    if largest >= 20:
        reasons.append(f"Largest position is {largest:.1f}% of portfolio")
    if max_sector >= 35:
        reasons.append(f"Largest sector exposure is {max_sector:.1f}%")
    if speculative_risk >= 20:
        reasons.append(f"High-volatility/speculative exposure is {speculative_risk:.1f}%")
    if cash_pct < RISK_PROFILES[profile]["preferred_cash_pct"]:
        reasons.append(f"Cash buffer {cash_pct:.1f}% is below the {RISK_PROFILES[profile]['label']} preference")
    if not reasons:
        reasons.append("No single risk concentration dominates the account")
    return {
        "score": score,
        "band": risk_band(score),
        "target_profile": profile,
        "target_label": RISK_PROFILES[profile]["label"],
        "target_score": target_score,
        "gap": round(score - target_score, 1),
        "invested": round(invested, 2),
        "total": round(total, 2),
        "cash_pct": round(cash_pct, 1),
        "largest_position_pct": round(largest, 1),
        "largest_sector_pct": round(max_sector, 1),
        "speculative_pct": round(speculative_risk, 1),
        "reasons": reasons[:3],
        "breakdown": {
            "Stock volatility": round(weighted_stock, 1),
            "Concentration": round(concentration, 1),
            "Sector concentration": round(sector_risk, 1),
            "Speculative exposure": round(speculative_risk, 1),
            "Cash buffer": round(cash_risk, 1),
            "Event exposure": round(event_risk, 1),
        },
    }


def projected_risk(account_rows: list[dict], cash: float, candidate: dict, sizing: dict, fx_rate_to_base: float, target_profile: str) -> dict | None:
    shares = _float(sizing.get("shares"))
    if shares <= 0:
        return None
    price = _float(candidate.get("price"))
    capital = shares * price * fx_rate_to_base
    pseudo = {
        "symbol": candidate.get("symbol"),
        "value_base": capital,
        "stock_risk": stock_risk_score(candidate),
        "sector": (candidate.get("fundamentals") or {}).get("sector") or "Unknown",
        "category": candidate.get("category"),
        "material_events": (candidate.get("news") or {}).get("material_events", 0),
    }
    return account_risk(account_rows + [pseudo], max(0, cash - capital), target_profile=target_profile)
