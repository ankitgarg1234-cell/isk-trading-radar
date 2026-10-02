from __future__ import annotations

import math
import re
import time
from datetime import datetime, timezone
from statistics import mean
from typing import Any

POSITIVE = {
    "beat", "beats", "upgrade", "upgraded", "approval", "approved", "record",
    "growth", "surge", "strong", "contract", "partnership", "launch", "raises",
    "raised", "outperform", "buy", "positive", "expansion", "wins", "win",
    "guidance raised", "fda approval", "backlog", "accelerates", "profit"
}
NEGATIVE = {
    "miss", "misses", "downgrade", "downgraded", "warning", "cuts", "cut",
    "lawsuit", "probe", "investigation", "weak", "decline", "delay", "rejected",
    "rejection", "offering", "dilution", "fraud", "recall", "guidance cut",
    "fda rejection", "bankruptcy", "restatement", "shortfall"
}
MATERIAL = {
    "earnings", "guidance", "fda", "approval", "contract", "acquisition", "merger",
    "offering", "dilution", "sec", "investigation", "lawsuit", "partnership", "trial",
    "phase 3", "phase iii", "bankruptcy", "buyback", "restatement"
}
CATALYST = {
    "earnings", "guidance", "fda", "approval", "contract", "partnership", "trial",
    "phase 3", "phase iii", "launch", "acquisition", "merger", "buyback", "analyst day"
}
CREDIBLE_HIGH = {
    "Reuters", "Bloomberg", "Associated Press", "AP Finance", "CNBC",
    "The Wall Street Journal", "Barrons.com", "MarketWatch"
}
CREDIBLE_PRIMARY = {"Business Wire", "GlobeNewswire", "PR Newswire"}

THESIS_BREAKING_TERMS = {
    "bankruptcy", "fraud", "restatement", "fda rejection", "rejected",
    "guidance cut", "cuts guidance", "withdraws guidance", "recall",
    "trial failure", "failed trial", "clinical hold", "default"
}
SEVERE_EXIT_TERMS = {"bankruptcy", "fraud", "fda rejection", "trial failure", "failed trial", "default"}

CORE_LANE = "CORE_QUALITY"
EXPLOSIVE_LANE = "EXPLOSIVE"
LANE_LABELS = {CORE_LANE: "Core Quality Lane", EXPLOSIVE_LANE: "Explosive Lane"}
MIN_SHARE_PRICE = 5.0
MIN_MARKET_CAP = 500_000_000.0
CORE_MIN_AVG_DOLLAR_VOLUME = 10_000_000.0
EXPLOSIVE_MIN_AVG_DOLLAR_VOLUME = 20_000_000.0
MIN_FUNDAMENTAL_SCORE = 14.0  # 70/100 normalized fundamental quality
EXPLOSIVE_MAX_TRADING_SESSIONS = 20
SCORING_VERSION = "2026-10-02-target-horizon-v3"

PROMOTION_SEVERE_TERMS = {
    "reverse split", "going concern", "minimum bid", "nasdaq compliance",
    "delisting notice", "bankruptcy", "fraud", "restatement",
}
PROMOTION_DILUTION_TERMS = {
    "at-the-market offering", "atm offering", "registered direct offering",
    "public offering", "warrant exercise", "warrants exercised", "dilution",
}


def clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def pct(v: Any) -> float | None:
    """Convert a normalized financial ratio to percentage points.

    Internal fundamentals use decimal ratios (0.30 == 30%, 2.05 == 205%).
    The previous magnitude heuristic treated ratios above 2.0 as if they were
    already percentages, which materially under-scored hyper-growth companies.
    Percentage-formatted strings are accepted as already-scaled display values.
    """
    if v is None:
        return None
    try:
        if isinstance(v, str):
            value = v.strip()
            if not value:
                return None
            if value.endswith("%"):
                return float(value[:-1].strip())
            v = value
        return float(v) * 100
    except Exception:
        return None


def ema(values: list[float], period: int) -> float | None:
    vals = [float(v) for v in values if v is not None]
    if not vals:
        return None
    k = 2 / (period + 1)
    out = vals[0]
    for v in vals[1:]:
        out = v * k + out * (1 - k)
    return out


def rsi(values: list[float], period: int = 14) -> float | None:
    vals = [float(v) for v in values if v is not None]
    if len(vals) <= period:
        return None
    changes = [vals[i] - vals[i - 1] for i in range(1, len(vals))]
    gains = [max(c, 0) for c in changes[-period:]]
    losses = [max(-c, 0) for c in changes[-period:]]
    ag, al = mean(gains), mean(losses)
    if al == 0:
        return 100.0
    rs = ag / al
    return 100 - (100 / (1 + rs))


def atr(rows: list[dict], period: int = 14) -> float | None:
    if len(rows) < 2:
        return None
    trs: list[float] = []
    for i in range(1, len(rows)):
        h, l, pc = rows[i].get("high"), rows[i].get("low"), rows[i - 1].get("close")
        if None in (h, l, pc):
            continue
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return mean(trs[-period:]) if trs else None


def _credibility(publisher: str) -> tuple[str, float]:
    if publisher in CREDIBLE_HIGH:
        return "high", 1.25
    if publisher in CREDIBLE_PRIMARY:
        return "primary-release", 1.1
    return "standard", 1.0


def _priced_in(published: Any) -> str:
    try:
        ts = float(published)
        age_hours = max(0.0, (time.time() - ts) / 3600)
        if age_hours <= 8:
            return "fresh / may not be fully priced"
        if age_hours <= 48:
            return "partially priced-in heuristic"
        return "older / more likely reflected in price"
    except Exception:
        return "unknown"


def news_analysis(news: list[dict]) -> dict:
    pos = neg = 0.0
    material = 0
    catalysts: list[str] = []
    items: list[dict] = []
    high_negative = 0
    for n in news[:15]:
        title_raw = n.get("title") or ""
        title = title_raw.lower()
        publisher = n.get("publisher") or ""
        p = sum(1 for w in POSITIVE if w in title)
        m = sum(1 for w in NEGATIVE if w in title)
        mat = sum(1 for w in MATERIAL if w in title)
        cat = [w for w in CATALYST if w in title]
        credibility, cred = _credibility(publisher)
        pos += p * cred
        neg += m * cred
        material += min(2, mat)
        catalysts.extend(cat)
        sentiment = "positive" if p > m else "negative" if m > p else "neutral"
        materiality = "high" if mat >= 1 else "normal"
        if sentiment == "negative" and materiality == "high":
            high_negative += 1
        items.append({
            **n,
            "sentiment": sentiment,
            "materiality": materiality,
            "credibility": credibility,
            "priced_in": _priced_in(n.get("published")),
            "thesis_impact": "supports" if sentiment == "positive" else "weakens" if sentiment == "negative" else "neutral",
        })
    raw = pos - neg
    score = clamp(7.5 + raw * 1.5, 0, 15)
    label = "Bullish" if raw >= 2 else "Bearish" if raw <= -2 else "Neutral"
    return {
        "score": round(score, 1), "label": label, "positive": round(pos, 1),
        "negative": round(neg, 1), "material_events": material,
        "high_negative_events": high_negative, "catalysts": sorted(set(catalysts)),
        "items": items,
    }


def fundamental_score(f: dict) -> tuple[float, list[str], str]:
    score = 0.0
    reasons: list[str] = []
    observed = 0
    rg = pct(f.get("revenueGrowth"))
    qrg = pct(f.get("quarterlyRevenueGrowth"))
    eg = pct(f.get("earningsGrowth") or f.get("growth"))
    gm = pct(f.get("grossMargins"))
    om = pct(f.get("operatingMargins"))
    roe = pct(f.get("returnOnEquity"))
    de = f.get("debtToEquity")
    checks = [
        (rg, 4, [(25, 4), (15, 3), (5, 2), (-math.inf, 0)], "Revenue growth", "%"),
        (eg, 4, [(25, 4), (10, 3), (0, 1), (-math.inf, 0)], "Earnings growth", "%"),
        (gm, 4, [(60, 4), (40, 3), (25, 2), (-math.inf, 1)], "Gross margin", "%"),
        (om, 3, [(20, 3), (10, 2), (0, 1), (-math.inf, 0)], "Operating margin", "%"),
        (roe, 3, [(20, 3), (10, 2), (0, 1), (-math.inf, 0)], "ROE", "%"),
    ]
    for value, maxpts, bands, label, suffix in checks:
        if value is None:
            continue
        observed += 1
        pts = next(points for cutoff, points in bands if value >= cutoff)
        score += pts
        reasons.append(f"{label} {value:.1f}{suffix} → {pts}/{maxpts}")
    if de is not None:
        observed += 1
        try:
            de = float(de)
            pts = 2 if de < 75 else 1 if de < 150 else 0
            score += pts
            reasons.append(f"Debt/equity {de:.0f} → {pts}/2")
        except Exception:
            pass
    if qrg is not None:
        observed += 1
        qpts = 2 if qrg >= 25 else 1 if qrg >= 10 else 0
        score += qpts
        accel = " (accelerating)" if rg is not None and qrg >= rg + 5 else ""
        reasons.append(f"Quarterly revenue growth {qrg:.1f}%{accel} → +{qpts}")
    if observed == 0:
        return 10.0, ["Fundamental feed unavailable: neutral 10/20 until verified"], "low"
    confidence = "high" if observed >= 5 else "medium" if observed >= 3 else "low"
    return round(clamp(score, 0, 20), 1), reasons, confidence


def analyst_score(f: dict, price: float) -> tuple[float | None, list[str], float | None]:
    target = f.get("targetMeanPrice")
    rec = f.get("recommendationMean")
    raw_points = 0.0
    available_weight = 0.0
    parts: list[str] = []
    target_upside: float | None = None
    if target and price:
        try:
            target_upside = (float(target) / price - 1) * 100
            raw_points += clamp(25 + target_upside, 0, 50)
            available_weight += 50
            parts.append(f"Mean analyst target implies {target_upside:.1f}% upside")
        except Exception:
            pass
    if rec:
        try:
            r = float(rec)
            raw_points += clamp((5 - r) / 4 * 50, 0, 50)
            available_weight += 50
            parts.append(f"Recommendation mean {r:.2f} (1=strong buy, 5=sell)")
        except Exception:
            pass
    # Some feeds return recommendation counts even when recommendationMean is absent.
    counts = {k: f.get(k) for k in ("strongBuy", "buy", "hold", "sell", "strongSell")}
    try:
        total = sum(float(v or 0) for v in counts.values())
    except Exception:
        total = 0
    if total > 0 and not rec:
        weighted = (
            float(counts.get("strongBuy") or 0) * 100
            + float(counts.get("buy") or 0) * 80
            + float(counts.get("hold") or 0) * 50
            + float(counts.get("sell") or 0) * 20
            + float(counts.get("strongSell") or 0) * 0
        ) / total
        raw_points += weighted * 0.5
        available_weight += 50
        parts.append(
            "Recommendation mix: "
            f"{int(float(counts.get('strongBuy') or 0))} strong buy / "
            f"{int(float(counts.get('buy') or 0))} buy / "
            f"{int(float(counts.get('hold') or 0))} hold / "
            f"{int(float(counts.get('sell') or 0))} sell / "
            f"{int(float(counts.get('strongSell') or 0))} strong sell"
        )
    if not available_weight:
        status = f.get("_analyst_status") or f.get("_status") or "unavailable"
        return None, [f"Analyst data unavailable from current provider ({status})"], target_upside
    return round(raw_points / available_weight * 100, 1), parts, target_upside


def technicals(rows: list[dict], price: float) -> dict:
    closes = [r["close"] for r in rows if r.get("close") is not None]
    vols = [r.get("volume") or 0 for r in rows]
    e20 = ema(closes[-80:], 20)
    e50 = ema(closes[-160:], 50)
    e200 = ema(closes, 200)
    rs = rsi(closes, 14)
    a = atr(rows, 14) or (price * 0.03 if price else 1)
    prev_vols = [v for v in vols[-21:-1] if v]
    avgvol = mean(prev_vols) if prev_vols else None
    rel = (vols[-1] / avgvol) if avgvol and vols else 1.0
    high20 = max(closes[-20:]) if closes else price
    low20 = min(closes[-20:]) if closes else price
    high52 = max(closes[-252:]) if closes else price
    change20 = (price / closes[-21] - 1) * 100 if len(closes) > 21 and closes[-21] else 0
    avg_dollar_volume = (avgvol * price) if avgvol and price else 0.0
    near_20d_high = (price / high20) if high20 else 0.0
    return {
        "ema20": e20, "ema50": e50, "ema200": e200, "rsi": rs, "atr": a,
        "relative_volume": rel, "avg_volume_20": avgvol, "avg_dollar_volume_20": avg_dollar_volume,
        "high20": high20, "low20": low20, "near_20d_high": near_20d_high,
        "high52": high52, "change20_pct": change20,
    }


def sector_score(bundle: dict) -> tuple[float, list[str]]:
    bench = bundle.get("sector_benchmark") or {}
    rows = bench.get("history") or []
    price = float(bench.get("price") or 0)
    if not rows or not price:
        return 5.0, ["Sector benchmark unavailable: neutral 5/10"]
    t = technicals(rows, price)
    points = 0.0
    reasons: list[str] = []
    if price > (t.get("ema20") or price + 1):
        points += 3
        reasons.append("Sector benchmark above EMA20 +3")
    if price > (t.get("ema50") or price + 1):
        points += 3
        reasons.append("Sector benchmark above EMA50 +3")
    ch = t.get("change20_pct") or 0
    if ch >= 8:
        points += 4
        reasons.append(f"Sector 20-day momentum {ch:.1f}% +4")
    elif ch >= 3:
        points += 3
        reasons.append(f"Sector 20-day momentum {ch:.1f}% +3")
    elif ch >= 0:
        points += 2
        reasons.append(f"Sector 20-day momentum {ch:.1f}% +2")
    return round(clamp(points, 0, 10), 1), reasons


def buy_levels(t: dict, price: float) -> dict:
    a = max(t.get("atr") or price * 0.03, price * 0.005) if price else 1
    e20 = t.get("ema20") or price
    e50 = t.get("ema50") or e20
    low20 = t.get("low20") or e50
    h20 = t.get("high20") or price
    primary = e20 if price >= e20 * 0.94 else e50
    better = min(e50, low20 + a * 0.25)
    buy_low = max(0.01, primary - 0.45 * a)
    buy_high = primary + 0.20 * a
    better_low = max(0.01, better - 0.35 * a)
    better_high = better + 0.25 * a
    breakout = h20 + 0.10 * a
    stop = max(0.01, min(low20, e50) - 0.75 * a)
    # Target is filled by forward_target_plan(). Keeping target construction out
    # of entry-level geometry prevents a distant historical 52-week high from
    # automatically becoming the reward assumption.
    do_not_chase = max(breakout + 1.0 * a, price + 2.5 * a)
    return {
        k: round(v, 2)
        for k, v in {
            "buy_low": buy_low, "buy_high": buy_high, "better_low": better_low,
            "better_high": better_high, "breakout": breakout, "stop": stop,
            "do_not_chase": do_not_chase,
        }.items()
    }


def forward_target_plan(t: dict, f: dict, price: float, catalyst_score: float = 5.0, material_events: int = 0) -> dict:
    """Build an auditable forward target instead of recycling the 52-week high.

    The base target is primarily a volatility/trend projection. Nearby resistance
    and analyst consensus may confirm it, but a distant historical high is only a
    stretch reference and never becomes the base reward assumption by itself.
    """
    if price <= 0:
        return {
            "base_target": 0.0, "stretch_target": 0.0, "technical_projection": 0.0,
            "target_source": "unavailable", "target_confidence": "low",
            "analyst_target_used": None, "nearest_resistance": None,
        }
    a = max(float(t.get("atr") or price * 0.03), price * 0.005)
    e20 = float(t.get("ema20") or price)
    e50 = float(t.get("ema50") or e20)
    rsi_v = float(t.get("rsi") if t.get("rsi") is not None else 50)
    ch20 = float(t.get("change20_pct") or 0)
    rel = float(t.get("relative_volume") or 0)

    strong = price >= e20 >= e50 and ch20 >= 3 and 45 <= rsi_v <= 72 and rel >= 0.8
    weak = price < e20 or rsi_v < 42 or ch20 < 0
    atr_mult = 2.5 if strong else 1.5 if weak else 2.0
    if catalyst_score >= 10 and material_events > 0 and not weak:
        atr_mult += 0.25
    technical_projection = price + atr_mult * a

    resistance_candidates = []
    for raw in (t.get("high20"), t.get("high52")):
        try:
            level = float(raw)
        except Exception:
            continue
        # Only treat resistance within a plausible 3-ATR forward window as a
        # base-target input. Distant historical highs remain stretch references.
        if price + 0.35 * a <= level <= price + 3.0 * a:
            resistance_candidates.append(level)
    nearest_resistance = min(resistance_candidates) if resistance_candidates else None

    analyst_target = None
    analyst_raw = None
    try:
        raw = f.get("targetMeanPrice")
        if raw not in (None, "") and float(raw) > price:
            analyst_raw = float(raw)
            # Consensus is useful confirmation but is capped to avoid one stale or
            # extreme target dominating the deterministic horizon.
            analyst_target = min(analyst_raw, price + 4.0 * a, price * 1.40)
    except Exception:
        analyst_target = None
        analyst_raw = None

    candidates = [technical_projection]
    source_parts = ["ATR/trend"]
    if nearest_resistance is not None:
        candidates.append(nearest_resistance)
        source_parts.append("near resistance")
    if analyst_target is not None:
        candidates.append(analyst_target)
        source_parts.append("analyst consensus")

    # A distant prior high can contribute to the base case only when it is
    # independently corroborated by analyst consensus AND the stock has a
    # material catalyst with elevated volume. Historical price alone never
    # upgrades the reward assumption.
    try:
        h52 = float(t.get("high52") or 0)
    except Exception:
        h52 = 0.0
    catalyst_breakout = catalyst_score >= 8 and material_events > 0 and rel >= 1.5
    corroborated_far_target = (
        catalyst_breakout
        and h52 > price
        and h52 <= price * 1.60
        and analyst_raw is not None
        and analyst_raw > price
        and abs(h52 - analyst_raw) / price <= 0.20
    )
    if corroborated_far_target:
        candidates.append(h52)
        candidates.append(min(analyst_raw, price * 1.60))
        source_parts.append("corroborated 52w/analyst stretch")
    ordered = sorted(candidates)
    base_target = ordered[len(ordered) // 2] if len(ordered) % 2 else sum(ordered[len(ordered)//2-1:len(ordered)//2+1]) / 2
    if corroborated_far_target:
        # For a catalyst/volume setup, a prior high becomes a legitimate base
        # objective only when analyst consensus independently confirms roughly
        # the same region. Use the lower corroborated anchor, never the higher.
        base_target = min(h52, analyst_raw, price * 1.60)

    stretch_candidates = [base_target + a]
    for raw in (t.get("high52"), f.get("targetHighPrice"), f.get("targetMeanPrice")):
        try:
            level = float(raw)
        except Exception:
            continue
        if base_target < level <= min(price + 6.0 * a, price * 1.60):
            stretch_candidates.append(level)
    stretch_target = max(stretch_candidates)

    confidence = "high" if len(candidates) >= 3 else "medium" if len(candidates) >= 2 else "medium"
    return {
        "base_target": round(base_target, 2),
        "stretch_target": round(stretch_target, 2),
        "technical_projection": round(technical_projection, 2),
        "target_source": " + ".join(source_parts),
        "target_confidence": confidence,
        "analyst_target_used": round(analyst_target, 2) if analyst_target is not None else None,
        "nearest_resistance": round(nearest_resistance, 2) if nearest_resistance is not None else None,
        "historical_52w_high": round(float(t.get("high52") or 0), 2) if t.get("high52") is not None else None,
    }


def holding_horizon_plan(price: float, target: float, t: dict, lane: str | None, catalyst_verified: bool = False) -> dict:
    """Translate target distance and setup quality into a realistic review horizon."""
    if lane == EXPLOSIVE_LANE:
        return {
            "min_days": 3, "max_days": 20, "review_days": 7,
            "rationale": "Explosive lane: catalyst/momentum trade with a maximum 20-trading-session holding window",
        }
    upside = ((target / price) - 1) * 100 if price and target else 0.0
    if upside <= 8:
        lo, hi = 15, 45
    elif upside <= 15:
        lo, hi = 25, 75
    elif upside <= 25:
        lo, hi = 40, 120
    else:
        lo, hi = 60, 180

    e20 = float(t.get("ema20") or price or 0)
    rsi_v = float(t.get("rsi") if t.get("rsi") is not None else 50)
    ch20 = float(t.get("change20_pct") or 0)
    weak = (price and e20 and price < e20) or rsi_v < 42 or ch20 < 0
    if weak:
        lo += 10
        hi += 30
    if catalyst_verified:
        lo = max(10, int(round(lo * 0.8)))
        hi = max(lo + 15, int(round(hi * 0.85)))
    hi = min(240, hi)
    review = min(45, max(15, int(round(lo * 0.75))))
    return {
        "min_days": int(lo), "max_days": int(hi), "review_days": int(review),
        "rationale": (
            f"Core target is {upside:.1f}% away; "
            + ("weak/repairing momentum extends the expected path" if weak else "current trend supports a normal realization window")
            + ("; verified catalyst may accelerate realization" if catalyst_verified else "")
        ),
    }



def _promotion_risk(bundle: dict, news: dict, t: dict) -> dict:
    price = float(bundle.get("price") or 0)
    f = bundle.get("fundamentals") or {}
    market_cap = float(f.get("marketCap") or 0)
    avg_dollar = float(t.get("avg_dollar_volume_20") or 0)
    relvol = float(t.get("relative_volume") or 0)
    titles = " | ".join(str(i.get("title") or "").lower() for i in (news.get("items") or []))
    severe_hits = sorted(term for term in PROMOTION_SEVERE_TERMS if term in titles)
    dilution_hits = sorted(term for term in PROMOTION_DILUTION_TERMS if term in titles)

    hard_reasons = []
    if bundle.get("recent_reverse_splits"):
        ratios = ", ".join(str(x.get("ratio") or "reverse split") for x in bundle.get("recent_reverse_splits")[:3])
        hard_reasons.append(f"recent reverse split detected ({ratios})")
    if price < MIN_SHARE_PRICE:
        hard_reasons.append(f"share price below ${MIN_SHARE_PRICE:.0f}")
    if market_cap and market_cap < MIN_MARKET_CAP:
        hard_reasons.append(f"market cap below ${MIN_MARKET_CAP/1_000_000:.0f}M")
    if avg_dollar and avg_dollar < CORE_MIN_AVG_DOLLAR_VOLUME:
        hard_reasons.append(f"20d average dollar volume below ${CORE_MIN_AVG_DOLLAR_VOLUME/1_000_000:.0f}M")
    hard_reasons.extend(severe_hits)

    catalyst_explained = bool(news.get("catalysts")) and int(news.get("material_events") or 0) >= 1
    unexplained_extreme_volume = relvol >= 4.0 and not catalyst_explained
    dilution_risk = len(dilution_hits) >= 2 or (bool(dilution_hits) and relvol >= 4.0)
    promotional_risk = bool(hard_reasons or unexplained_extreme_volume or dilution_risk)
    return {
        "hard_reject": bool(hard_reasons),
        "promotional_risk": promotional_risk,
        "unexplained_extreme_volume": unexplained_extreme_volume,
        "dilution_risk": dilution_risk,
        "severe_hits": severe_hits,
        "dilution_hits": dilution_hits,
        "reasons": hard_reasons
            + (["extreme relative volume has no identifiable material catalyst"] if unexplained_extreme_volume else [])
            + (["dilution/financing promotion risk"] if dilution_risk else []),
    }


def _strategic_catalyst(bundle: dict) -> tuple[bool, list[str]]:
    strategic = bundle.get("strategic_capital") or {}
    accepted_types = {
        "GOVERNMENT_EQUITY_STAKE", "GOVERNMENT_CAPITAL_OR_DEMAND",
        "FEDERAL_AWARD", "FEDERAL_LOAN_OR_GUARANTEE",
        "ADMINISTRATION_HIGHLIGHTED_INVESTMENT",
    }
    evidence = []
    for event in strategic.get("events") or []:
        if event.get("type") not in accepted_types:
            continue
        if event.get("source_quality") != "OFFICIAL" and event.get("verification") != "VERIFIED SOURCE":
            continue
        if event.get("direction") == "NEGATIVE":
            continue
        if event.get("materiality") not in {"HIGH", "VERY HIGH", "MEDIUM"}:
            continue
        evidence.append(str(event.get("title") or event.get("type")))
    return bool(evidence), evidence[:4]

def _verified_news_catalyst(news: dict, relvol: float) -> tuple[bool, list[str]]:
    """Require a material catalyst from a credible or primary-release source.

    Explosive qualification must not be created by social/secondary chatter.
    At extreme volume (>=8x), require a concrete event term even for a primary
    company release so generic promotional partnerships cannot explain the move.
    """
    strong_terms = {
        "earnings", "guidance", "fda", "approval", "contract", "acquisition",
        "merger", "trial", "phase 3", "phase iii", "buyback",
    }
    evidence: list[str] = []
    for item in news.get("items") or []:
        title = str(item.get("title") or "")
        title_l = title.lower()
        if item.get("materiality") != "high":
            continue
        credibility = str(item.get("credibility") or "standard")
        if credibility not in {"high", "primary-release"}:
            continue
        matched = [term for term in CATALYST if term in title_l]
        if not matched:
            continue
        if relvol >= 8.0 and not any(term in title_l for term in strong_terms):
            continue
        evidence.append(title)
    return bool(evidence), evidence[:4]


def classify_lane(
    bundle: dict, *, fs: float, fconf: str, news: dict, t: dict,
    catalyst_score: float, total_score: float, expected_upside_pct: float,
    negative_override: str | None, explosive_upside_pct: float | None = None,
) -> dict:
    promotion = _promotion_risk(bundle, news, t)
    f = bundle.get("fundamentals") or {}
    market_cap = float(f.get("marketCap") or 0)
    avg_dollar = float(t.get("avg_dollar_volume_20") or 0)
    relvol = float(t.get("relative_volume") or 0)
    change20 = float(t.get("change20_pct") or 0)
    near_high = float(t.get("near_20d_high") or 0)

    core_reasons = []
    core_blockers: list[str] = []
    core_quality = (
        not promotion["hard_reject"]
        and fs >= MIN_FUNDAMENTAL_SCORE
        and fconf in {"medium", "high"}
        and total_score >= 68
        and not negative_override
        and avg_dollar >= CORE_MIN_AVG_DOLLAR_VOLUME
        and market_cap >= MIN_MARKET_CAP
    )
    if fs < MIN_FUNDAMENTAL_SCORE:
        msg=f"fundamentals {fs:.1f}/20 below {MIN_FUNDAMENTAL_SCORE:.0f}/20 floor"
        core_reasons.append(msg); core_blockers.append("fundamental score < 14/20")
    if fconf == "low":
        core_reasons.append("fundamental evidence confidence is low"); core_blockers.append("fundamental evidence confidence low")
    if total_score < 68:
        core_reasons.append(f"system conviction {total_score:.1f}/100 below 68"); core_blockers.append("system conviction < 68")
    if negative_override:
        core_reasons.append(str(negative_override)); core_blockers.append("material negative-news override")
    if market_cap <= 0:
        core_reasons.append("market-cap evidence unavailable"); core_blockers.append("market-cap evidence unavailable")
    elif market_cap < MIN_MARKET_CAP:
        core_reasons.append(f"market cap ${market_cap/1_000_000:.0f}M below ${MIN_MARKET_CAP/1_000_000:.0f}M floor"); core_blockers.append("market cap < $500M")
    if avg_dollar <= 0:
        core_reasons.append("20d average dollar-volume evidence unavailable"); core_blockers.append("20d dollar-volume unavailable")
    elif avg_dollar < CORE_MIN_AVG_DOLLAR_VOLUME:
        core_reasons.append(f"20d average dollar volume ${avg_dollar/1_000_000:.1f}M below ${CORE_MIN_AVG_DOLLAR_VOLUME/1_000_000:.0f}M floor"); core_blockers.append("20d dollar liquidity < $10M")
    if promotion["hard_reject"]:
        core_blockers.append("promotion / reverse-split hard reject")
    core_reasons.extend(promotion["reasons"])

    strategic_catalyst, strategic_evidence = _strategic_catalyst(bundle)
    catalyst_verified, catalyst_evidence = _verified_news_catalyst(news, relvol)
    # Government / political / connected-capital evidence is intentionally
    # shadow-only in v2. It is recorded for validation but cannot independently
    # qualify an Explosive setup or change Portfolio Priority.
    volume_explained = not promotion["unexplained_extreme_volume"]
    explosive_blockers: list[str] = []
    if not core_quality:
        explosive_blockers.append("Core quality gate")
    if avg_dollar < EXPLOSIVE_MIN_AVG_DOLLAR_VOLUME:
        explosive_blockers.append("20d dollar liquidity < $20M")
    if relvol < 1.5:
        explosive_blockers.append("relative volume < 1.5x")
    if not (change20 >= 3.0 or near_high >= 0.985):
        explosive_blockers.append("momentum / near-high confirmation")
    if not catalyst_verified:
        explosive_blockers.append("verified material catalyst")
    if catalyst_score < 8:
        explosive_blockers.append("catalyst score < 8/15")
    if total_score < 75:
        explosive_blockers.append("system conviction < 75")
    explosive_potential = expected_upside_pct if explosive_upside_pct is None else explosive_upside_pct
    if explosive_potential < 30.0:
        explosive_blockers.append("modeled remaining upside < 30%")
    if not volume_explained:
        explosive_blockers.append("unexplained extreme volume")
    if promotion["dilution_risk"]:
        explosive_blockers.append("dilution / financing risk")

    explosive = not explosive_blockers

    if explosive:
        lane = EXPLOSIVE_LANE
        label = LANE_LABELS[lane]
        reasons = [
            f"fundamentals {fs:.1f}/20",
            f"20d dollar liquidity ${avg_dollar/1_000_000:.1f}M",
            f"relative volume {relvol:.2f}x",
            f"20d move {change20:+.1f}%",
            f"modeled stretch upside {explosive_potential:.1f}%",
            "material catalyst verified from credible/primary evidence",
        ]
        reasons.extend(catalyst_evidence[:2])
        reasons.extend(strategic_evidence[:2])
    elif core_quality:
        lane = CORE_LANE
        label = LANE_LABELS[lane]
        reasons = [
            f"fundamentals {fs:.1f}/20",
            f"20d dollar liquidity ${avg_dollar/1_000_000:.1f}M" if avg_dollar else "liquidity feed unavailable",
            "fundamental quality gate passed",
        ]
    else:
        lane = None
        label = "Ineligible / Watch"
        reasons = core_reasons or ["did not pass investable lane qualification"]

    return {
        "lane": lane,
        "lane_label": label,
        "lane_qualified": lane in {CORE_LANE, EXPLOSIVE_LANE},
        "core_quality_qualified": core_quality,
        "explosive_qualified": explosive,
        "explosive_holding_max_trading_sessions": EXPLOSIVE_MAX_TRADING_SESSIONS if explosive else None,
        "promotion_risk": promotion,
        "lane_reasons": reasons,
        "core_blockers": core_blockers,
        "explosive_blockers": explosive_blockers,
        "catalyst_verified": catalyst_verified,
        "catalyst_evidence": catalyst_evidence,
        "strategic_catalyst_evidence": strategic_evidence,
    }


def score_bundle(bundle: dict) -> dict:
    price = float(bundle.get("price") or 0)
    rows = bundle.get("history") or []
    f = bundle.get("fundamentals") or {}
    news = news_analysis(bundle.get("news") or [])
    fs, freasons, fconf = fundamental_score(f)
    t = technicals(rows, price)

    mom = 0.0
    mreasons: list[str] = []
    momentum_checks = [
        ("Above EMA20", price > (t.get("ema20") or price + 1), 3),
        ("Above EMA50", price > (t.get("ema50") or price + 1), 3),
        ("Above EMA200", price > (t.get("ema200") or price + 1), 3),
        ("RSI constructive", t.get("rsi") is not None and 45 <= t["rsi"] <= 72, 3),
        ("Relative volume >1.2x", (t.get("relative_volume") or 0) >= 1.2, 3),
    ]
    for label, condition, points in momentum_checks:
        if condition:
            mom += points
            mreasons.append(f"{label} +{points}")

    catalyst = clamp(5 + len(news["catalysts"]) * 2 + min(news["material_events"], 3), 0, 15)
    target_plan = forward_target_plan(t, f, price, catalyst, int(news.get("material_events") or 0))
    levels = buy_levels(t, price)
    levels["target"] = target_plan["base_target"]
    levels["stretch_target"] = target_plan["stretch_target"]
    sector, sector_reasons = sector_score(bundle)
    pe = f.get("forwardPE") or f.get("trailingPE")
    rg = pct(f.get("revenueGrowth"))
    valuation = 5.0
    if pe:
        try:
            pe = float(pe)
            valuation = 8 if pe < 20 else 7 if pe < 30 else 5 if pe < 45 else 3
            if rg and rg > 25 and pe < 45:
                valuation = min(10, valuation + 2)
        except Exception:
            pass

    a_score, a_reasons, analyst_yield = analyst_score(f, price)
    # Evidence confidence is based on decision-critical evidence only. Analyst
    # consensus is deliberately optional: lack of Wall Street coverage must not
    # downgrade a well-evidenced company into DATA REVIEW.
    missing_inputs: list[str] = []
    optional_missing_inputs: list[str] = []
    quality_points = 0
    if fconf == "high":
        quality_points += 4
    elif fconf == "medium":
        quality_points += 3
    elif fconf == "low" and any(f.get(k) is not None for k in ("revenueGrowth", "earningsGrowth", "grossMargins", "operatingMargins", "returnOnEquity", "debtToEquity")):
        quality_points += 1
        missing_inputs.append("complete fundamentals")
    else:
        missing_inputs.append("complete fundamentals")
    if news.get("items"):
        quality_points += 1
    else:
        missing_inputs.append("recent news")
    if len(rows) >= 100:
        quality_points += 2
    elif len(rows) >= 50:
        quality_points += 1
    else:
        missing_inputs.append("price history")
    if bundle.get("sector_benchmark"):
        quality_points += 1
    else:
        missing_inputs.append("sector benchmark")
    if a_score is None:
        optional_missing_inputs.append("analyst consensus")
    if f.get("targetMeanPrice") in (None, ""):
        optional_missing_inputs.append("consensus price target")
    data_quality_pct = round(quality_points / 8 * 100, 1)
    decision_confidence = "high" if data_quality_pct >= 75 else "medium" if data_quality_pct >= 50 else "low"
    rr_up = (levels["target"] - price) / price if price else 0
    rr_down = (price - levels["stop"]) / price if price else 1
    rr = (rr_up / rr_down) if rr_down > 0 else 0
    rr_score = clamp(rr / 3 * 10, 0, 10)
    total = fs + catalyst + news["score"] + mom + sector + valuation + (a_score / 100 * 5 if a_score is not None else 2.5) + rr_score

    # Material negative news can override an otherwise strong numerical setup.
    override: str | None = None
    if news["high_negative_events"] >= 2:
        total = min(total, 68)
        override = "Multiple material negative news events cap the score until resolved"
    elif news["high_negative_events"] >= 1 and news["label"] == "Bearish":
        total = min(total, 74)
        override = "Material negative news prevents a high-conviction qualification"

    total = round(clamp(total), 1)
    deterministic_expected = round(max(-50, min(150, rr_up * 100)), 1)
    lane_info = classify_lane(
        bundle, fs=fs, fconf=fconf, news=news, t=t,
        catalyst_score=catalyst, total_score=total, expected_upside_pct=deterministic_expected,
        negative_override=override, explosive_upside_pct=deterministic_expected,
    )
    category = "Explosive Runner" if lane_info["lane"] == EXPLOSIVE_LANE else "Core" if lane_info["lane"] == CORE_LANE else "Watch"
    horizon_plan = holding_horizon_plan(
        price, levels["target"], t, lane_info["lane"],
        catalyst_verified=bool(lane_info.get("catalyst_verified")),
    )
    deterministic_horizon = (horizon_plan["min_days"], horizon_plan["max_days"])
    breakdown = {
        "Fundamentals": round(fs, 1), "Catalyst": round(catalyst, 1), "News": round(news["score"], 1),
        "Momentum": round(mom, 1), "Sector": round(sector, 1), "Valuation": round(valuation, 1),
        "Analyst confirmation": round(a_score / 20 if a_score is not None else 2.5, 1),
        "Risk/Reward": round(rr_score, 1),
    }
    return {
        "scoring_version": SCORING_VERSION,
        "deterministic_score": total,
        "analyst_score": a_score,
        "expected_yield_pct": deterministic_expected,
        "analyst_expected_yield_pct": round(analyst_yield, 1) if analyst_yield is not None else None,
        "deterministic_holding_period_min_days": deterministic_horizon[0],
        "deterministic_holding_period_max_days": deterministic_horizon[1],
        "holding_horizon": horizon_plan,
        "target_plan": target_plan,
        "analyst_holding_period_min_days": 180 if analyst_yield is not None else None,
        "analyst_holding_period_max_days": 365 if analyst_yield is not None else None,
        "category": category,
        "lane": lane_info["lane"],
        "lane_label": lane_info["lane_label"],
        "lane_qualified": lane_info["lane_qualified"],
        "core_quality_qualified": lane_info["core_quality_qualified"],
        "explosive_qualified": lane_info["explosive_qualified"],
        "explosive_holding_max_trading_sessions": lane_info["explosive_holding_max_trading_sessions"],
        "promotion_risk": lane_info["promotion_risk"],
        "lane_reasons": lane_info["lane_reasons"],
        "core_blockers": lane_info.get("core_blockers") or [],
        "explosive_blockers": lane_info.get("explosive_blockers") or [],
        "catalyst_verified": lane_info["catalyst_verified"],
        "catalyst_evidence": lane_info.get("catalyst_evidence") or [],
        "strategic_catalyst_evidence": lane_info["strategic_catalyst_evidence"],
        "breakdown": breakdown,
        "fundamental_reasons": freasons,
        "fundamental_confidence": fconf,
        "analyst_reasons": a_reasons,
        "analyst_target_mean_price": float(f.get("targetMeanPrice")) if f.get("targetMeanPrice") not in (None, "") else None,
        "analyst_target_high_price": float(f.get("targetHighPrice")) if f.get("targetHighPrice") not in (None, "") else None,
        "analyst_target_low_price": float(f.get("targetLowPrice")) if f.get("targetLowPrice") not in (None, "") else None,
        "analyst_opinion_count": int(float(f.get("numberOfAnalystOpinions"))) if f.get("numberOfAnalystOpinions") not in (None, "") else None,
        "analyst_recommendation_key": f.get("recommendationKey"),
        "analyst_data_status": f.get("_analyst_status") or f.get("_status") or ("available" if a_score is not None else "unavailable"),
        "data_quality_pct": data_quality_pct,
        "decision_confidence": decision_confidence,
        "missing_inputs": missing_inputs,
        "optional_missing_inputs": optional_missing_inputs,
        "evidence_sources": bundle.get("data_sources") or {},
        "sector_reasons": sector_reasons,
        "technicals": t,
        "levels": levels,
        "entry_zone_status": entry_zone_state(levels, price),
        "news": news,
        "risk_reward": round(rr, 2),
        "momentum_reasons": mreasons,
        "negative_news_override": override,
    }


def entry_zone_state(levels: dict, price: float) -> str:
    """Classify price relative to the modeled entry ladder.

    The primary buy zone is not a one-shot band: once price trades below it,
    a cheaper price should not automatically revert to generic WATCH. The
    corridor down to the better-buy zone remains entry-relevant until the stop
    / invalidation level is threatened.
    """
    if price <= levels["stop"]:
        return "INVALIDATED"
    if price > levels["do_not_chase"]:
        return "DO_NOT_CHASE"
    if price >= levels["breakout"]:
        return "BREAKOUT"
    if levels["buy_low"] <= price <= levels["buy_high"]:
        return "PRIMARY_BUY"
    if levels["better_low"] <= price <= levels["better_high"]:
        return "BETTER_BUY"
    if levels["better_high"] < price < levels["buy_low"]:
        return "VALUE_CORRIDOR"
    if levels["stop"] < price < levels["better_low"]:
        return "DEEP_VALUE"
    if levels["buy_high"] < price < levels["breakout"]:
        return "APPROACHING_BREAKOUT"
    return "WATCH"



def thesis_assessment(result: dict) -> dict:
    """Evidence-gated thesis state for existing-position sell decisions.

    Short-term price/momentum weakness is deliberately excluded. REDUCE/EXIT can
    only come from explicit thesis-breaking news or verified fundamental
    deterioration relative to a prior saved snapshot.
    """
    news=result.get("news") or {}
    breakdown=result.get("breakdown") or {}
    fscore=float(breakdown.get("Fundamentals") or 0)
    fconf=result.get("fundamental_confidence") or "low"
    prior=result.get("previous_snapshot") or {}
    prior_fscore=None
    try:
        prior_fscore=float((prior.get("breakdown") or {}).get("Fundamentals"))
    except Exception:
        prior_fscore=None
    titles=[str(i.get("title") or "").lower() for i in (news.get("items") or []) if i.get("sentiment") == "negative"]
    breaking_terms=sorted({term for title in titles for term in THESIS_BREAKING_TERMS if term in title})
    severe_terms=sorted({term for title in titles for term in SEVERE_EXIT_TERMS if term in title})
    fundamental_deterioration=(
        fconf in {"medium","high"}
        and fscore <= 8
        and prior_fscore is not None
        and (prior_fscore >= 12 or prior_fscore - fscore >= 4)
    )
    material_negative=bool(news.get("high_negative_events",0))
    invalidated=bool(breaking_terms) or fundamental_deterioration
    severe=bool(severe_terms) and (fundamental_deterioration or material_negative)
    reasons=[]
    if breaking_terms: reasons.append("Thesis-breaking event: " + ", ".join(breaking_terms))
    if fundamental_deterioration: reasons.append(f"Verified fundamentals deteriorated from {prior_fscore:.1f}/20 to {fscore:.1f}/20")
    return {
        "invalidated": invalidated, "severe": severe, "reasons": reasons,
        "fundamental_deterioration": fundamental_deterioration,
        "breaking_terms": breaking_terms, "prior_fundamental_score": prior_fscore,
        "current_fundamental_score": fscore,
    }

def position_action(result: dict, price: float, position: dict | None) -> tuple[str, str]:
    s = result["deterministic_score"]
    n = result["news"]
    t = result["technicals"]
    lv = result["levels"]
    ema20 = t.get("ema20") or price
    rsi = t.get("rsi") if t.get("rsi") is not None else 50
    change20 = t.get("change20_pct") or 0
    relvol = t.get("relative_volume") or 0
    momentum_weak = price < ema20 or rsi < 42
    falling_risk = (price < ema20 and change20 < -2) or rsi < 40
    ema_gap_pct = ((price / ema20) - 1) * 100 if ema20 else 0
    better_buy_weak_flags = [rsi < 40, change20 < -6, ema_gap_pct < -2.5, relvol >= 1.5 and change20 < -4]
    better_buy_weakness_count = sum(bool(x) for x in better_buy_weak_flags)
    better_buy_falling_risk = rsi < 34 or better_buy_weakness_count >= 2
    mild_better_buy_weakness = better_buy_weakness_count == 1
    bearish = n["label"] == "Bearish" and n["material_events"] > 0
    severe_bearish = n.get("high_negative_events", 0) >= 1 and bearish
    zone = entry_zone_state(lv, price)
    downside_to_better = ((price - lv["better_high"]) / price * 100) if price else 0
    confidence = result.get("decision_confidence") or "medium"
    thesis = thesis_assessment(result)
    # Expose the assessment to downstream alert/detail rendering.
    result["thesis_assessment"] = thesis

    if position:
        avg = float(position.get("avg_cost") or 0)
        pnl = (price / avg - 1) * 100 if avg else 0
        shares = float(position.get("shares") or 0)
        whole_share_account = "avanza" in str(position.get("account") or "").lower()
        entry_target = float(position.get("entry_target") or lv.get("target") or 0)
        entry_stretch = float(position.get("entry_stretch_target") or (result.get("target_plan") or {}).get("stretch_target") or entry_target)
        entry_stop = float(position.get("entry_stop") or lv.get("stop") or 0)
        horizon_days = int(position.get("entry_horizon_days") or (result.get("holding_horizon") or {}).get("max_days") or 0)
        holding_days = None
        opened_at = position.get("opened_at")
        try:
            opened_dt = opened_at if isinstance(opened_at, datetime) else datetime.fromisoformat(str(opened_at))
            if opened_dt.tzinfo is None:
                opened_dt = opened_dt.replace(tzinfo=timezone.utc)
            holding_days = max(0, (datetime.now(timezone.utc) - opened_dt).days)
        except Exception:
            holding_days = None
        entry_rr = None
        if avg and entry_stop < avg < entry_target:
            entry_rr = (entry_target - avg) / (avg - entry_stop)
        result["position_plan"] = {
            "avg_cost": round(avg, 2) if avg else None,
            "entry_target": round(entry_target, 2) if entry_target else None,
            "entry_stretch_target": round(entry_stretch, 2) if entry_stretch else None,
            "entry_stop": round(entry_stop, 2) if entry_stop else None,
            "entry_rr": round(entry_rr, 2) if entry_rr is not None else None,
            "forward_rr": result.get("risk_reward"),
            "holding_days": holding_days,
            "review_horizon_days": horizon_days or None,
            "plan_version": position.get("entry_plan_version"),
        }

        # Hard rule: no panic sell. REDUCE/EXIT require explicit thesis/fundamental invalidation.
        if thesis["severe"]:
            why = "; ".join(thesis["reasons"]) or "Severe thesis invalidation confirmed"
            return "EXIT", f"{why}; unrealized P&L {pnl:.1f}%"
        if thesis["invalidated"]:
            why = "; ".join(thesis["reasons"]) or "Investment thesis/fundamentals materially invalidated"
            return "REDUCE", f"{why}; unrealized P&L {pnl:.1f}%"

        if entry_stretch and price >= entry_stretch and pnl > 0:
            result["profit_take_pct"] = 50
            result["profit_take_reason"] = f"Stretch target {entry_stretch:.2f} reached"
            return "TAKE PARTIAL PROFIT", f"Stretch target {entry_stretch:.2f} reached with unrealized P&L {pnl:.1f}%; lock part of the gain and keep a runner while the thesis remains intact"
        if entry_target and price >= entry_target and pnl > 0:
            trim = 50 if (momentum_weak or bearish) else 25
            result["profit_take_pct"] = trim
            result["profit_take_reason"] = f"Base target {entry_target:.2f} reached"
            return "TAKE PARTIAL PROFIT", f"Base target {entry_target:.2f} reached with unrealized P&L {pnl:.1f}%; take {trim}% profit rather than letting the target move indefinitely"

        if horizon_days and holding_days is not None and holding_days >= horizon_days:
            if pnl >= 8 and momentum_weak:
                result["profit_take_pct"] = 25
                result["profit_take_reason"] = f"Modeled {horizon_days}-day horizon elapsed with weakening momentum"
                return "TAKE PARTIAL PROFIT", f"Modeled {horizon_days}-day horizon has elapsed; position is still up {pnl:.1f}% but momentum weakened, so harvest 25% and reassess"
            result["position_plan"]["horizon_review_due"] = True

        if confidence == "low" and not severe_bearish:
            return "HOLD — DATA REVIEW", "Evidence coverage is incomplete; missing data is not treated as a sell signal"
        if severe_bearish and pnl >= 5:
            if whole_share_account and shares <= 1:
                return "HOLD — THESIS REVIEW", "Material negative news detected, but the thesis has not been invalidated and a one-share position cannot be partially trimmed"
            return "TAKE PARTIAL PROFIT", f"Profitable position ({pnl:.1f}%) faces material negative news; trim gains only, not because the thesis is broken"
        if bearish and momentum_weak and pnl >= 5:
            if whole_share_account and shares <= 1:
                return "HOLD — DON'T ADD", "Bearish evidence and weak momentum are present, but the thesis remains intact and partial trimming is impractical"
            return "TAKE PARTIAL PROFIT", f"Profitable position ({pnl:.1f}%) has bearish near-term evidence; thesis remains intact, so only optional profit protection is warranted"
        if zone == "INVALIDATED":
            return "HOLD — THESIS REVIEW", "Price crossed the modeled technical invalidation level, but technical weakness alone is not a sell signal; re-check the investment thesis/fundamentals"
        if momentum_weak or bearish:
            return "HOLD — DON'T ADD", "Near-term evidence has weakened, but the thesis/fundamentals are not invalidated; do not panic sell"
        if s < 65:
            return "HOLD — DON'T ADD", f"Score is only {s:.0f}, but a low score by itself is not a sell signal; wait for explicit thesis deterioration"
        if zone in {"PRIMARY_BUY", "BETTER_BUY", "VALUE_CORRIDOR"} and s >= 75 and not bearish and confidence != "low":
            return "ADD", f"Position is in an active entry zone ({zone.replace('_', ' ').title()}) with score {s:.0f}, adequate evidence coverage, and thesis intact"
        if result.get("position_plan", {}).get("horizon_review_due"):
            return "HOLD — REBALANCE REVIEW", f"Modeled holding horizon has elapsed after {holding_days} days; thesis remains intact, so compare this position with stronger qualified opportunities rather than panic-selling"
        return "HOLD", f"Thesis intact; unrealized P&L {pnl:.1f}%"

    # New-position logic remains entry/risk oriented.
    if zone == "INVALIDATED":
        return "AVOID", "Price is below the modeled invalidation level; wait for the setup to rebuild"
    if severe_bearish:
        return "AVOID", "Material negative news overrides the numerical setup"
    if confidence == "low":
        return "WATCH — DATA REVIEW", "Evidence coverage is incomplete; wait for sufficient data before opening a new position"
    if zone == "DO_NOT_CHASE":
        return "DON'T CHASE", "Price is above the do-not-chase threshold"
    if zone == "PRIMARY_BUY":
        if (falling_risk or (bearish and momentum_weak)) and downside_to_better >= 3:
            return "WAIT MORE", f"Buy level reached, but price is below EMA20 / recent momentum is weakening; better-buy zone is {lv['better_low']:.2f}–{lv['better_high']:.2f}"
        if s >= 80 and not bearish:
            return "BUY NOW", "Primary buy zone reached with high deterministic conviction and no material bearish override"
        if s >= 65 and not bearish:
            return "CONSIDER BUYING NOW", f"Primary buy zone reached; score {s:.0f}, evidence coverage is adequate, and no material bearish override is present"
        return "WAIT MORE", f"Primary buy zone reached, but deterministic conviction is only {s:.0f}/100"
    if zone == "BETTER_BUY":
        technical_context = f"RSI {rsi:.1f}, 20d {change20:.1f}%, price vs EMA20 {ema_gap_pct:.1f}%"
        if better_buy_falling_risk or (bearish and momentum_weak):
            return "WAIT MORE", f"Better-buy zone reached, but multiple downside signals still point to falling-knife risk ({technical_context}); wait for stabilization"
        if s >= 75 and not bearish and not mild_better_buy_weakness:
            return "BUY NOW", f"Better-buy zone reached with strong score {s:.0f}, adequate evidence, and stable momentum ({technical_context})"
        if s >= 65 and not bearish:
            if mild_better_buy_weakness:
                return "CONSIDER STARTER BUY", f"Better-buy zone reached and score is {s:.0f}; only one moderate weakness flag remains ({technical_context}), so consider a staged starter position rather than waiting for a lower price"
            return "CONSIDER BUYING NOW", f"Better-buy zone reached with score {s:.0f}, adequate evidence, and thesis intact ({technical_context})"
        return "WATCH", f"Better-buy zone reached, but score {s:.0f}/100 is not yet sufficient despite the attractive price"
    if zone == "VALUE_CORRIDOR":
        if falling_risk or (bearish and momentum_weak):
            return "WAIT FOR BETTER BUY", f"Price has crossed below the primary buy zone, but momentum remains weak; next modeled better-buy zone is {lv['better_low']:.2f}–{lv['better_high']:.2f}"
        if s >= 65 and not bearish:
            return "CONSIDER STARTER BUY", f"Price is below the primary buy zone but above the better-buy zone; score {s:.0f} and thesis remain acceptable"
        return "WATCH", f"Price is cheaper than the primary buy zone, but score {s:.0f}/100 does not justify an entry yet"
    if zone == "DEEP_VALUE":
        if s >= 70 and not bearish and not falling_risk:
            return "REVIEW BUY", "Price is below the better-buy zone but still above invalidation; rerun support/thesis checks before entry"
        return "WAIT MORE", "Price is below the better-buy zone and close enough to invalidation to require stabilization first"
    if zone == "BREAKOUT" and relvol >= 1.5 and s >= 75 and not bearish:
        return "BREAKOUT BUY", "Breakout confirmed by relative volume and adequate deterministic conviction"
    if zone == "BREAKOUT":
        return "WATCH BREAKOUT", "Price is above the breakout level, but volume/conviction confirmation is insufficient"
    if zone == "APPROACHING_BREAKOUT":
        return "WATCH", "Price is above the primary buy zone but has not confirmed a breakout; avoid chasing the middle"
    return "WATCH", "No active entry trigger is present"

def position_action_plan(action: str, result: dict, price: float, position: dict | None) -> dict | None:
    if not position:
        return None
    shares = float(position.get("shares") or 0)
    if shares <= 0:
        return None
    account = str(position.get("account") or "")
    whole_share_account = "avanza" in account.lower()
    if action == "EXIT":
        pct_to_reduce = 100
        rationale = "Full exit because the modeled thesis/stop is invalidated"
    elif action == "TAKE PARTIAL PROFIT":
        severe = (result.get("news") or {}).get("high_negative_events", 0) >= 1
        pct_to_reduce = float(result.get("profit_take_pct") or (50 if severe else 25))
        rationale = result.get("profit_take_reason") or "Take part of the position off while retaining exposure if the thesis remains intact"
    elif action == "REDUCE":
        pct_to_reduce = 50 if result.get("deterministic_score", 100) < 60 else 25
        rationale = "Reduce risk while keeping a smaller position for reassessment"
    else:
        return None
    raw_qty = shares * pct_to_reduce / 100
    if whole_share_account:
        if pct_to_reduce < 100 and shares <= 1:
            qty = 0
            rationale = "Partial reduction is not practical for a one-share whole-share position; review HOLD versus EXIT"
        else:
            qty = min(shares, float(math.ceil(raw_qty)))
    else:
        qty = min(shares, round(raw_qty, 4))
    actual_pct = round((qty / shares * 100), 1) if shares and qty else 0.0
    return {
        "requested_percent": pct_to_reduce,
        "suggested_shares": qty,
        "actual_percent": actual_pct,
        "remaining_shares": round(max(0.0, shares - qty), 4),
        "rationale": rationale,
    }


def heuristic_ai(result: dict) -> dict:
    score = result["deterministic_score"]
    adjustments: list[dict] = []
    n = result["news"]
    t = result["technicals"]
    if n["label"] == "Bullish" and n["material_events"]:
        score += 4
        adjustments.append({"points": 4, "reason": "Material positive news reinforces the setup"})
    if n["label"] == "Bearish" and n["material_events"]:
        score -= 8
        adjustments.append({"points": -8, "reason": "Material negative news creates an override risk"})
    if (t.get("relative_volume") or 0) >= 1.8:
        score += 3
        adjustments.append({"points": 3, "reason": "Unusually strong relative volume"})
    if (t.get("rsi") or 50) > 76:
        score -= 4
        adjustments.append({"points": -4, "reason": "Short-term momentum is stretched/overbought"})
    if result["risk_reward"] >= 3:
        score += 3
        adjustments.append({"points": 3, "reason": "Modeled risk/reward is at least 3:1"})
    if result.get("negative_news_override"):
        score = min(score, 72)
        adjustments.append({"points": 0, "reason": result["negative_news_override"]})
    score = round(clamp(score), 1)
    exp = round(result["expected_yield_pct"] * (0.85 if n["label"] == "Bearish" else 1.05), 1)
    horizon = (
        int(result.get("deterministic_holding_period_min_days") or 3),
        int(result.get("deterministic_holding_period_max_days") or 28),
    )
    lv = result.get("levels") or {}
    sensitivity = [
        {"condition": f"Price breaks modeled stop/support near {lv.get('stop', 0):.2f}", "new_score": round(clamp(score - 18), 1)},
        {"condition": "Material negative guidance or regulatory news appears", "new_score": round(clamp(score - 22), 1)},
        {"condition": f"Breakout above {lv.get('breakout', 0):.2f} with strong volume", "new_score": round(clamp(score + 5), 1)},
        {"condition": "Sector momentum materially weakens", "new_score": round(clamp(score - 8), 1)},
    ]
    return {
        "ai_score": score,
        "ai_expected_yield_pct": exp,
        "holding_period_min_days": horizon[0],
        "holding_period_max_days": horizon[1],
        "mode": "explainable heuristic fallback",
        "reasons": [a["reason"] for a in adjustments] or ["No contextual override to the deterministic score"],
        "risks": [
            "Free market/news feeds can be delayed or incomplete",
            "AI expected yield is a scenario estimate, not a guaranteed return",
        ],
        "adjustments": adjustments,
        "sensitivity": sensitivity,
    }


def parse_positions_from_text(text: str) -> list[dict]:
    """Parse OCR/copy-pasted broker rows. User must confirm/edit before saving.

    Supports both simple ``TICKER SHARES AVG_COST`` rows and Avanza-style OCR where
    the account number appears before quantity and the purchase price appears after
    the current/last price. The parser intentionally prefers returning nothing over
    confidently saving a malformed position.
    """
    rows: list[dict] = []

    # Broker display names that can be resolved without guessing. Unknown names are
    # left for manual confirmation rather than inventing a ticker.
    name_aliases = [
        (re.compile(r"alphabet\s+inc(?:\s+class\s+a)?", re.I), "GOOGL"),
        (re.compile(r"credo\s+technology", re.I), "CRDO"),
        (re.compile(r"investor\s+b", re.I), "INVE-B.ST"),
        (re.compile(r"jaguar\s+health", re.I), "JAGX"),
        # OCR can drop the initial M in Mirum.
        (re.compile(r"(?:m|\\)?irum\s+pharmaceuticals", re.I), "MIRM"),
    ]

    def num(x: str) -> float:
        x = x.replace(" ", "")
        # Thousands separators in broker screenshots are usually commas; decimals
        # are dots in the screenshots we currently support.
        if "," in x and "." not in x:
            parts=x.split(",")
            if len(parts[-1]) == 3:
                x="".join(parts)
            else:
                x=x.replace(",", ".")
        else:
            x=x.replace(",", "")
        return float(x)

    for line in text.splitlines():
        clean = " ".join(line.strip().split())
        if not clean:
            continue

        # ---- Avanza / broker table OCR path ---------------------------------
        account_match = re.search(r"\b\d{7,10}\b", clean)
        if account_match and re.search(r"\b(?:Buy|Sell)\b", clean, re.I):
            before = clean[:account_match.start()]
            after = clean[account_match.end():].strip()

            ticker = None
            for pattern, symbol in name_aliases:
                if pattern.search(before):
                    ticker = symbol
                    break

            # If the broker actually displays a ticker, accept a sensible explicit
            # symbol, but never one-character OCR/UI tokens such as O.
            if ticker is None:
                explicit = re.findall(r"\b[A-Z]{2,5}(?:[.-][A-Z]{1,3})?\b", before)
                explicit = [x for x in explicit if x not in {"BUY", "SELL", "SEK", "USD", "ISK"}]
                ticker = explicit[-1] if explicit else None

            share_match = re.match(r"(\d+(?:[.,]\d+)?)\b", after)
            if not ticker or not share_match:
                continue
            try:
                shares = num(share_match.group(1))
            except Exception:
                continue
            # Account numbers/OCR garbage must never become position quantities.
            if not (0 < shares < 1_000_000):
                continue

            tail = after[share_match.end():]
            avg = None
            # For US Avanza rows the purchase price is explicitly prefixed with $;
            # the current price immediately before it is not.
            usd = re.search(r"\$\s*([0-9][0-9,.]*)", tail)
            if usd:
                try:
                    avg = num(usd.group(1))
                except Exception:
                    avg = None
            else:
                # For SEK rows, use the first plain amount followed by SEK. Skip
                # signed P/L values (+/-) and percentages.
                for m in re.finditer(r"(?<![+\-])\b([0-9][0-9,.]*)\s*SEK\b", tail, re.I):
                    try:
                        candidate=num(m.group(1))
                    except Exception:
                        continue
                    if candidate > 0:
                        avg=candidate
                        break

            if avg and avg > 0:
                rows.append({"symbol": ticker, "shares": shares, "avg_cost": avg, "account": "Avanza Screenshot"})
            continue

        # ---- Generic copy/paste path ----------------------------------------
        ticker_matches = re.findall(r"\b[A-Z]{2,5}(?:[.-][A-Z]{1,3})?\b", clean)
        if not ticker_matches:
            continue
        ticker = next((x for x in ticker_matches if x not in {"USD", "SEK", "ISK", "BUY", "SELL"}), None)
        if not ticker:
            continue
        after = clean[clean.find(ticker) + len(ticker):]
        nums = re.findall(r"-?\d+(?:[.,]\d+)?", after)
        if len(nums) < 2:
            continue
        try:
            shares, avg = num(nums[0]), num(nums[1])
            if 0 < shares < 1_000_000 and avg > 0:
                rows.append({"symbol": ticker, "shares": shares, "avg_cost": avg, "account": "Screenshot"})
        except Exception:
            pass

    # Last occurrence wins, which is useful when a pasted statement contains an
    # updated duplicate row for the same symbol.
    out: dict[str, dict] = {}
    for r in rows:
        out[r["symbol"]] = r
    return list(out.values())


def portfolio_proposals(
    positions: list[dict], analyses: dict[str, dict], deployable_cash: float, reserve_cash: float = 0
) -> list[dict]:
    props: list[dict] = []
    candidates: list[tuple[str, dict]] = []
    for sym, a in analyses.items():
        if a.get("action") in {"BUY NOW", "BREAKOUT BUY", "REVIEW BUY", "ADD"} and a.get("ai_score", 0) >= 82:
            candidates.append((sym, a))
    candidates.sort(key=lambda x: (x[1].get("ai_score", 0), x[1].get("ai_expected_yield_pct", 0)), reverse=True)
    available = max(0, deployable_cash - reserve_cash)
    if candidates and available > 0:
        sym, a = candidates[0]
        alloc = min(available, max(500, available * 0.35))
        props.append({
            "type": "DEPLOY CASH", "title": f"Consider deploying cash into {sym}",
            "detail": f"Allocate about {alloc:.0f} cash units; AI score {a.get('ai_score', 0):.0f}, expected yield {a.get('ai_expected_yield_pct', 0):.1f}%",
            "symbol_to": sym, "amount": round(alloc, 2),
        })
    weak: list[tuple[dict, dict]] = []
    for p in positions:
        a = analyses.get(p["symbol"])
        if a and a.get("action") in {"REDUCE", "TAKE PARTIAL PROFIT", "EXIT", "HOLD — DON'T ADD"}:
            weak.append((p, a))
    if candidates and weak:
        best_sym, best = candidates[0]
        for p, a in weak:
            gap = best.get("ai_score", 0) - a.get("ai_score", 0)
            yield_gap = best.get("ai_expected_yield_pct", 0) - a.get("ai_expected_yield_pct", 0)
            if gap >= 10 and yield_gap >= 8 and p["symbol"] != best_sym:
                qty = max(1, int(p["shares"] * 0.35))
                props.append({
                    "type": "ROTATE", "title": f"Consider rotating {qty} {p['symbol']} shares into {best_sym}",
                    "detail": f"Score gap {gap:.0f} pts; expected-return gap {yield_gap:.1f} pts. Review spread, fees, diversification and catalyst timing before acting.",
                    "symbol_from": p["symbol"], "symbol_to": best_sym, "shares": qty,
                })
                break
    return props
