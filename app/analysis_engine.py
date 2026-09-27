from __future__ import annotations

import math
import re
import time
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


def clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def pct(v: Any) -> float | None:
    if v is None:
        return None
    try:
        v = float(v)
        return v * 100 if abs(v) <= 2 else v
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
    if not available_weight:
        return None, ["Analyst data unavailable"], target_upside
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
    return {
        "ema20": e20, "ema50": e50, "ema200": e200, "rsi": rs, "atr": a,
        "relative_volume": rel, "high20": high20, "low20": low20,
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
    h52 = t.get("high52") or h20
    primary = e20 if price >= e20 * 0.94 else e50
    better = min(e50, low20 + a * 0.25)
    buy_low = max(0.01, primary - 0.45 * a)
    buy_high = primary + 0.20 * a
    better_low = max(0.01, better - 0.35 * a)
    better_high = better + 0.25 * a
    breakout = h20 + 0.10 * a
    stop = max(0.01, min(low20, e50) - 0.75 * a)
    target = max(h52, price + 3 * a)
    do_not_chase = max(breakout + 1.0 * a, price + 2.5 * a)
    return {
        k: round(v, 2)
        for k, v in {
            "buy_low": buy_low, "buy_high": buy_high, "better_low": better_low,
            "better_high": better_high, "breakout": breakout, "stop": stop,
            "target": target, "do_not_chase": do_not_chase,
        }.items()
    }


def score_bundle(bundle: dict) -> dict:
    price = float(bundle.get("price") or 0)
    rows = bundle.get("history") or []
    f = bundle.get("fundamentals") or {}
    news = news_analysis(bundle.get("news") or [])
    fs, freasons, fconf = fundamental_score(f)
    t = technicals(rows, price)
    levels = buy_levels(t, price)

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
    explosive = fs >= 14 and mom >= 11 and (catalyst >= 10 or news["score"] >= 10) and total >= 80 and not override
    category = "Explosive Runner" if explosive else "Core" if fs >= 14 and total >= 75 and not override else "Watch"
    deterministic_horizon = (10, 40) if category == "Explosive Runner" else (30, 180) if category == "Core" else (30, 365)
    breakdown = {
        "Fundamentals": round(fs, 1), "Catalyst": round(catalyst, 1), "News": round(news["score"], 1),
        "Momentum": round(mom, 1), "Sector": round(sector, 1), "Valuation": round(valuation, 1),
        "Analyst confirmation": round(a_score / 20 if a_score is not None else 2.5, 1),
        "Risk/Reward": round(rr_score, 1),
    }
    return {
        "deterministic_score": total,
        "analyst_score": a_score,
        "expected_yield_pct": deterministic_expected,
        "analyst_expected_yield_pct": round(analyst_yield, 1) if analyst_yield is not None else None,
        "deterministic_holding_period_min_days": deterministic_horizon[0],
        "deterministic_holding_period_max_days": deterministic_horizon[1],
        "analyst_holding_period_min_days": 180 if analyst_yield is not None else None,
        "analyst_holding_period_max_days": 365 if analyst_yield is not None else None,
        "category": category,
        "breakdown": breakdown,
        "fundamental_reasons": freasons,
        "fundamental_confidence": fconf,
        "analyst_reasons": a_reasons,
        "sector_reasons": sector_reasons,
        "technicals": t,
        "levels": levels,
        "news": news,
        "risk_reward": round(rr, 2),
        "momentum_reasons": mreasons,
        "negative_news_override": override,
    }


def position_action(result: dict, price: float, position: dict | None) -> tuple[str, str]:
    s = result["deterministic_score"]
    n = result["news"]
    t = result["technicals"]
    lv = result["levels"]
    momentum_weak = price < (t.get("ema20") or price) or (t.get("rsi") or 50) < 42
    bearish = n["label"] == "Bearish" and n["material_events"] > 0
    severe_bearish = n.get("high_negative_events", 0) >= 1 and bearish
    in_buy = lv["buy_low"] <= price <= lv["buy_high"]
    downside_to_better = ((price - lv["better_high"]) / price * 100) if price else 0
    thesis_invalid = price <= lv["stop"] or (s < 55 and bearish)

    if position:
        avg = float(position.get("avg_cost") or 0)
        pnl = (price / avg - 1) * 100 if avg else 0
        if thesis_invalid:
            return "EXIT", f"Thesis invalidation/stop condition triggered; unrealized P&L {pnl:.1f}%"
        if severe_bearish and pnl >= 5:
            return "TAKE PARTIAL PROFIT", f"Profitable position ({pnl:.1f}%) faces material negative news; protect capital while thesis is reassessed"
        if (bearish or momentum_weak) and pnl >= 8 and downside_to_better >= 3:
            return "TAKE PARTIAL PROFIT", f"Profitable position ({pnl:.1f}%) with weakening evidence and a lower re-entry zone"
        if s < 65 or (bearish and momentum_weak):
            return "REDUCE", f"Score/evidence deteriorated; P&L {pnl:.1f}%"
        if in_buy and s >= 85 and not bearish:
            return "ADD", f"Existing position is in buy zone with score {s:.0f} and thesis intact"
        if momentum_weak or bearish:
            return "HOLD — DON'T ADD", "Thesis not invalidated, but near-term evidence does not support adding"
        return "HOLD", f"Thesis intact; unrealized P&L {pnl:.1f}%"

    if thesis_invalid:
        return "AVOID", "Price/evidence invalidates the setup"
    if severe_bearish:
        return "AVOID", "Material negative news overrides the numerical setup"
    if price > lv["do_not_chase"]:
        return "DON'T CHASE", "Price is above the do-not-chase threshold"
    if in_buy:
        if downside_to_better >= 4 and (momentum_weak or bearish):
            return "WAIT MORE", f"Buy zone reached, but evidence supports waiting for {lv['better_low']:.2f}–{lv['better_high']:.2f}"
        if s >= 80 and not bearish:
            return "BUY NOW", "Buy zone reached with acceptable score and no material bearish override"
        return "WAIT MORE", "Buy zone reached but conviction is not high enough"
    if price >= lv["breakout"] and (t.get("relative_volume") or 0) >= 1.5 and s >= 82 and not bearish:
        return "BREAKOUT BUY", "Breakout confirmed by relative volume and score"
    if price < lv["buy_low"] and s >= 80 and not bearish:
        return "REVIEW BUY", "Price is below the modeled buy zone; rerun support/invalidation checks"
    return "WATCH", "Wait for buy zone, breakout confirmation, or stronger evidence"


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
    horizon = (10, 40) if result["category"] == "Explosive Runner" else (30, 180)
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
