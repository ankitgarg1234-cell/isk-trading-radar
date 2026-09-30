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
    # Risk fit is advisory for sizing, never an entry veto. Under the uncapped
    # Top-20 policy every qualified entry must receive capital; higher-risk names
    # may receive a smaller suggested size but cannot be silently blocked.

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
    elif fit == "ABOVE TARGET":
        shares *= 0.35
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


RANK_VERSION = "rank-v1"
INVESTABLE_ENTRY_ACTIONS = {"STRONG BUY", "BUY", "STARTER BUY"}


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def entry_attention_signal(a: dict) -> str | None:
    """Portfolio-layer entry label using the agreed deterministic ladder.

    This intentionally does not blend AI/analyst scores into the decision.
    They remain separate confirmation signals.
    """
    if bool((a.get("thesis_assessment") or {}).get("invalidated")):
        return None
    if a.get("negative_news_override"):
        return None
    if str(a.get("decision_confidence") or "medium").lower() == "low":
        return None
    zone = str(a.get("entry_zone_status") or "").upper()
    if not zone:
        price = _float(a.get("price"))
        levels = a.get("levels") or {}
        b0, b1 = _float(levels.get("better_low")), _float(levels.get("better_high"))
        p0, p1 = _float(levels.get("buy_low")), _float(levels.get("buy_high"))
        if b0 and b0 <= price <= b1:
            zone = "BETTER_BUY"
        elif p0 and p0 <= price <= p1:
            zone = "PRIMARY_BUY"
    if zone not in {"PRIMARY_BUY", "BETTER_BUY"}:
        return None
    score = _float(a.get("deterministic_score"))
    if score >= 85:
        return "STRONG BUY"
    if score >= 75:
        return "BUY"
    if score >= 68 and zone == "BETTER_BUY":
        return "STARTER BUY"
    if score >= 68 and zone == "PRIMARY_BUY":
        return "CONSIDER BUY"
    return None


def candidate_rank_score(a: dict) -> dict:
    """Transparent deterministic portfolio-priority score (0-100).

    The stock's deterministic score remains untouched. This second score answers a
    different question: among already-analysed candidates, which deserves scarce
    portfolio capital first? AI/analyst opinions are reported as confirmations but
    are deliberately not blended into the arithmetic.
    """
    det = _clamp(_float(a.get("deterministic_score")))
    expected = _float(a.get("expected_yield_pct"))
    rr = max(0.0, _float(a.get("risk_reward")))
    confidence = str(a.get("decision_confidence") or "medium").lower()
    srisk = stock_risk_score(a)

    conviction_pts = det * 0.50
    upside_pts = _clamp(expected, 0, 35) / 35 * 20
    rr_pts = _clamp(rr, 0, 3.5) / 3.5 * 15
    confidence_pts = 10.0 if confidence == "high" else 6.0 if confidence == "medium" else 0.0
    risk_pts = max(0.0, 100.0 - srisk) / 100 * 5
    penalty = 0.0
    if a.get("negative_news_override"):
        penalty += 20
    if bool((a.get("thesis_assessment") or {}).get("invalidated")):
        penalty += 35
    if str(a.get("entry_zone_status") or "").upper() in {"DO_NOT_CHASE", "INVALIDATED"}:
        penalty += 12

    total = _clamp(conviction_pts + upside_pts + rr_pts + confidence_pts + risk_pts - penalty)
    ai = a.get("ai_score")
    analyst = a.get("analyst_score")
    strategic = a.get("strategic_capital") or {}
    ai_confirmation = "UNAVAILABLE"
    analyst_confirmation = "UNAVAILABLE"
    if ai is not None:
        delta = _float(ai) - det
        ai_confirmation = "CONFIRMS" if delta >= -5 and _float(ai) >= 70 else "DIVERGES" if delta <= -10 else "NEUTRAL"
    if analyst is not None:
        delta = _float(analyst) - det
        analyst_confirmation = "CONFIRMS" if delta >= -8 and _float(analyst) >= 65 else "DIVERGES" if delta <= -15 else "NEUTRAL"
    return {
        "score": round(total, 1),
        "version": RANK_VERSION,
        "entry_signal": entry_attention_signal(a),
        "components": {
            "Deterministic conviction": round(conviction_pts, 1),
            "Expected upside": round(upside_pts, 1),
            "Risk/reward": round(rr_pts, 1),
            "Evidence confidence": round(confidence_pts, 1),
            "Risk efficiency": round(risk_pts, 1),
            "Penalties": round(-penalty, 1),
        },
        "ai_confirmation": ai_confirmation,
        "analyst_confirmation": analyst_confirmation,
        "stock_risk": srisk,
        "strategic_capital_shadow": {
            "mode": strategic.get("mode") or "UNAVAILABLE",
            "label": strategic.get("label") or "NONE",
            "direction": strategic.get("direction") or "NONE",
            "evidence_strength": float(strategic.get("evidence_strength") or 0),
            "shadow_rank_adjustment": float(strategic.get("shadow_rank_adjustment") or 0),
            "government_equity_stake": strategic.get("government_equity_stake") or "UNKNOWN",
            "government_capital_or_demand": strategic.get("government_capital_or_demand") or "UNKNOWN",
            "sector_policy_support": strategic.get("sector_policy_support") or "UNKNOWN",
            "trump_administration_action": strategic.get("trump_administration_action") or "UNKNOWN",
            "trump_personal_disclosure": (strategic.get("trump_personal_disclosure") or {}).get("status") or "UNKNOWN",
        },
    }


def build_optimizer_plan(
    analyses: dict[str, dict],
    owned_symbols: set[str] | list[str] | tuple[str, ...] = (),
    *,
    profile: str = "MEDIUM",
    visible_limit: int = 20,
    shortlist_limit: int = 10,
    target_positions: int = 6,
    max_positions: int = 7,
    min_rank_score: float = 62.0,
    rotation_gap: float = 12.0,
    rotation_yield_gap: float = 8.0,
) -> dict:
    """Rank candidates and select every qualified entry inside the visible Top 20.

    Full-market scanning remains unchanged. The legacy target/max/min-rank/rotation
    arguments are retained for call compatibility but no longer gate paper entries.
    Ranking still determines which names are in the visible Top-20 universe.
    """
    owned = {str(s).upper() for s in owned_symbols}
    profile = normalise_profile(profile)
    rows = []
    for sym, a in analyses.items():
        if not isinstance(a, dict):
            continue
        sym = str(sym or a.get("symbol") or "").upper()
        if not sym:
            continue
        rank = candidate_rank_score(a)
        srisk = rank["stock_risk"]
        fit = risk_fit(srisk, profile)
        sector = str((a.get("fundamentals") or {}).get("sector") or "Unknown")
        adjusted = rank["score"] - (6 if fit == "STRETCH" else 20 if fit == "ABOVE TARGET" else 0)
        rows.append({
            "symbol": sym,
            "analysis": a,
            "rank_score": round(_clamp(adjusted), 1),
            "raw_rank_score": rank["score"],
            "rank_components": rank["components"],
            "entry_signal": rank["entry_signal"],
            "ai_confirmation": rank["ai_confirmation"],
            "analyst_confirmation": rank["analyst_confirmation"],
            "risk_fit": fit,
            "stock_risk": srisk,
            "sector": sector,
            "owned": sym in owned,
            "expected_yield_pct": _float(a.get("expected_yield_pct")),
            "strategic_capital_shadow": rank.get("strategic_capital_shadow") or {},
        })
    rows.sort(key=lambda r: (r["rank_score"], r["expected_yield_pct"]), reverse=True)
    for i, r in enumerate(rows, 1):
        r["market_rank"] = i
        r["bucket"] = "RESERVE"
        r["optimizer_action"] = "PASS"
        r["decision_reason"] = f"PASS — outside the current Top-{max(1, visible_limit)} allocation universe"

    visible = rows[:max(1, visible_limit)]
    shortlist = visible[:max(1, min(shortlist_limit, len(visible)))]
    shortlist_symbols = {r["symbol"] for r in shortlist}

    selected_new = []
    # Uncapped allocation policy:
    # every currently actionable candidate inside the ranked Top 20 is eligible
    # for paper capital. Rank, sector, tier, risk-fit and holding count do NOT gate
    # selection. The shortlist remains a review label only.
    for r in visible:
        if r["owned"]:
            r["bucket"] = "PORTFOLIO"
            r["optimizer_action"] = "HOLD / MANAGE"
            r["decision_reason"] = "HOLD / MANAGE — already held in the portfolio"
            continue
        if r["entry_signal"] in INVESTABLE_ENTRY_ACTIONS:
            r["bucket"] = "INVEST NOW"
            r["optimizer_action"] = r["entry_signal"]
            r["decision_reason"] = (
                f"{r['entry_signal']} — qualified inside Top-{max(1, visible_limit)}; "
                "no holding-count, sector, tier, rank-threshold or risk-fit gate"
            )
            selected_new.append(r)
            continue
        r["bucket"] = "SHORTLIST" if r["symbol"] in shortlist_symbols else "RESERVE"
        r["optimizer_action"] = "PASS"
        r["decision_reason"] = f"PASS — current entry signal {r['entry_signal'] or 'NONE'} is not investable"

    # With no holding-count cap there is no need to sell an intact holding merely
    # to make room for another qualified candidate. Thesis-gated exits/reductions
    # remain handled by the position-management layer.
    rotations = []

    return {
        "version": RANK_VERSION,
        "visible": visible,
        "shortlist": shortlist,
        "selected_new": selected_new,
        "rotations": rotations,
        "position_cap_enabled": False,
        "target_positions": None,
        "max_positions": None,
        "owned_count": len(owned),
        "visible_limit": visible_limit,
        "shortlist_limit": shortlist_limit,
        "allocation_policy": "TOP20_ALL_QUALIFIED",
    }
