"""Isolated, observation-driven paper experiment. Never submits broker orders.

Signals use one observation; simulated fills require a subsequent observation.
All prices are indicative Yahoo last prices, not executable bid/ask quotes.
"""
from __future__ import annotations

import copy
import math
from calendar import monthrange
from zoneinfo import ZoneInfo
from datetime import datetime, timezone

from .portfolio_engine import (
    RISK_PROFILES, candidate_rank_score, entry_attention_signal,
    suggested_position_size,
)
from .analysis_engine import position_action, position_action_plan
from .trading_rules import MIN_ENTRY_RISK_REWARD, entry_check

VERSION = "score-bands-paper-v1"
BANDS = ((90, 40), (85, 30), (80, 20), (75, 15), (70, 10))
VARIANTS = ("complete_strategy",)


def ensure_single_account(state):
    """Archive comparison ledgers without resetting or combining any balances."""
    books = state["variants"]
    if "complete_strategy" not in books:
        raise ValueError("Complete strategy ledger is missing; refusing to reset the account")
    inactive = [mode for mode in books if mode != "complete_strategy"]
    for mode in inactive:
        state.setdefault("archived_variants", {}).setdefault(mode, books.pop(mode))
    state["spec"]["active_accounts"] = 1
    return state


def number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def allocation_pct(score):
    score = number(score)
    if score is None or not 0 <= score <= 100:
        return 0
    return next((weight for minimum, weight in BANDS if score >= minimum), 0)


def timestamp(value):
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except (ValueError, TypeError):
        return None


def experiment_spec(profile="MEDIUM"):
    return {
        "version": VERSION, "starting_cash": 10000.0, "profile": profile, "active_accounts": 1,
        "risk_per_trade_pct": RISK_PROFILES[profile]["risk_per_trade_pct"],
        "bands": list(BANDS), "min_deterministic": 70, "min_analyst": 75, "min_rr": MIN_ENTRY_RISK_REWARD,
        "fee_bps": 10.0, "slippage_bps": 5.0, "fresh_seconds": 600,
        "initial_exit": "complete strategy: entry-time modeled stop; next fresh observation fill",
        "strong_momentum": "price >= EMA20 and RSI14 >= 50",
        "post_harvest_stop": "max(previous stop, peak observed price - (2 if strong else 1) * ATR14)",
        "profit_withdrawal": "once: ceil(unrealized price gain / net sale price), preserving >=1 share",
        "entry_levels": "frozen at signal time; breakout uses preceding completed daily closes",
        "fill_model": "next fresh scanner observation, adverse 5bps slippage, 10bps fee",
        "coverage": "all fresh deep analyses supplied by rotating scanner; no Top-20 limit; not a complete market census",
        "benchmark": "same-start observed S&P 500 total-return index; dividends on stock positions omitted",
    }


def new_state(profile="MEDIUM"):
    spec = experiment_spec(profile)
    return {"spec": spec, "started_at": None, "last_cycle": None, "last_market_open": None, "benchmark_start": None,
            "benchmark_last": None, "coverage": {}, "variants": {
                mode: {"cash": 10000.0, "positions": {}, "pending": {}, "trades": [],
                       "marks": {}, "seen": {}, "closed_dates": {}, "peak_equity": 10000.0,
                       "max_drawdown_pct": 0.0, "samples": 0, "cash_pct_sum": 0.0,
                       "curve": [], "blockers": {}, "fills": 0}
                for mode in VARIANTS}}


def equity(book):
    return book["cash"] + sum(p["shares"] * book["marks"].get(s, p["avg_cost"])
                               for s, p in book["positions"].items())


def arm_trial(state, armed_at):
    if timestamp(armed_at) is None:
        raise ValueError("Trial activation requires a valid timestamp")
    book = state["variants"]["complete_strategy"]
    if not state.get("trial") and not state.get("started_at") and not book["positions"] and not book["trades"] and not book["pending"]:
        # Restore the approved profile only for an entirely unstarted account.
        state["spec"] = experiment_spec("HIGH")
    # Retries and deployments never reset or restart an existing trial.
    state.setdefault("trial", {"armed_at": armed_at, "status": "waiting_for_inputs",
        "started_at": None, "ends_at": None, "baseline_equity": None,
        "benchmark_start": None, "benchmark_last": None, "baseline_trade_count": None,
        "peak_equity": None, "max_drawdown_pct": 0.0})
    return state["trial"]


def trial_summary(state):
    trial = state.get("trial")
    if not trial:
        return None
    out = copy.deepcopy(trial)
    book = state["variants"]["complete_strategy"]
    value = trial.get("final_equity", equity(book))
    baseline = trial.get("baseline_equity")
    out["return_pct"] = round((value / baseline - 1) * 100, 4) if baseline else None
    first, last = trial.get("benchmark_start"), trial.get("benchmark_last")
    valuation, sampled = timestamp(trial.get("valuation_asof")), timestamp(trial.get("benchmark_asof"))
    aligned = valuation and sampled and 0 <= (valuation - sampled).total_seconds() <= state["spec"]["fresh_seconds"]
    out["benchmark_return_pct"] = round((last / first - 1) * 100, 4) if first and last and aligned else None
    out["excess_return_pct"] = round(out["return_pct"] - out["benchmark_return_pct"], 4) if out["return_pct"] is not None and out["benchmark_return_pct"] is not None else None
    out["trade_count"] = len(book["trades"]) - trial["baseline_trade_count"] if trial.get("baseline_trade_count") is not None else 0
    out["valuation_asof"] = trial.get("valuation_asof")
    return out


def proposed_quantity(a, book, spec, price, existing=None):
    total = equity(book)
    unit_cost = price * (1 + spec["fee_bps"] / 10000)
    existing = existing or {}
    current_shares = existing.get("shares", 0)
    target_room = max(0, total * allocation_pct(a.get("deterministic_score")) / 100 - current_shares * price)
    levels = a["levels"]
    per_share_risk = price - float(levels.get("entry_stop") or levels["stop"])
    # Include entry friction in the budget. Stops are scenario limits, not guaranteed fills.
    per_share_risk += price * (spec["fee_bps"] + spec["slippage_bps"]) / 10000
    risk_room = max(0, total * spec["risk_per_trade_pct"] / 100 - current_shares * per_share_risk)
    if per_share_risk <= 0:
        return 0
    return max(0, math.floor(min(target_room / unit_cost, risk_room / per_share_risk,
                                 book["cash"] / unit_cost) + 1e-12))


def profit_cash_quantity(shares, cost, sale_price, fee_bps=10):
    gain = max(0, shares * (sale_price - cost))
    if shares <= 1 or gain <= 0:
        return 0
    return min(shares - 1, math.ceil(gain / (sale_price * (1 - fee_bps / 10000))))


def trailing_stop(previous, peak, atr, price, ema20, rsi):
    if atr is None or atr <= 0 or ema20 is None or rsi is None:
        return previous
    strong = price >= ema20 and rsi >= 50
    return max(previous, peak - (2 if strong else 1) * atr)


def block(book, reason):
    book["blockers"][reason] = book["blockers"].get(reason, 0) + 1


def _sale(book, spec, symbol, qty, price, observed, reason):
    p = book["positions"][symbol]
    qty = min(p["shares"], int(qty))
    if qty <= 0:
        return
    gross, fee = qty * price, qty * price * spec["fee_bps"] / 10000
    book["cash"] += gross - fee
    entry_fee = p["entry_fee_per_share"] * qty
    book["trades"].append({"symbol": symbol, "side": "SELL", "shares": qty, "price": price,
        "fees": fee, "realized_profit": qty * (price - p["avg_cost"]) - fee - entry_fee,
        "cash_released": gross - fee, "observed_at": observed, "reason": reason})
    p["shares"] -= qty
    if p["shares"] == 0:
        del book["positions"][symbol]
        book["closed_dates"][symbol] = observed[:10]


def _fill(book, mode, spec, a, observed):
    symbol = a["symbol"]
    pending = book["pending"].get(symbol)
    if not pending or observed <= pending["observed_at"]:
        return
    del book["pending"][symbol]
    market = float(a["price"])
    if pending["side"] == "SELL":
        p = book["positions"].get(symbol)
        if not p:
            return
        price = market * (1 - spec["slippage_bps"] / 10000)
        if pending["reason"] == "PROFIT_CASH_WITHDRAWAL":
            if market < p["entry_target"]:
                block(book, "profit_withdrawal_cancelled_below_target")
                return
            qty = profit_cash_quantity(p["shares"], p["avg_cost"], price, spec["fee_bps"])
            p["harvested"] = True
            p["peak"] = max(p["peak"], market)
            _sale(book, spec, symbol, qty, price, observed, pending["reason"])
        else:
            _sale(book, spec, symbol, pending["shares"], price, observed, pending["reason"])
        book["fills"] += 1
        return
    if (timestamp(observed) - timestamp(pending["observed_at"])).total_seconds() > spec["fresh_seconds"]:
        block(book, "entry_intent_expired")
        return
    price = market * (1 + spec["slippage_bps"] / 10000)
    fresh = copy.deepcopy(a)
    fresh["price"] = price
    fresh["levels"], fresh["target_plan"] = pending["levels"], pending["target_plan"]
    existing = book["positions"].get(symbol)
    if existing:
        fresh["levels"]["entry_stop"] = existing["entry_stop"]
        fresh["target_plan"]["base_target"] = existing["entry_target"]
    if mode == "current_rules_control":
        fresh["price"] = price
        stop, target = number(fresh["levels"].get("entry_stop") or fresh["levels"].get("stop")), number(fresh["target_plan"].get("base_target"))
        if stop is None or target is None or not stop < price < target:
            block(book, "fill_target_stop_invalid")
            return
        fresh["risk_reward"] = (target - price) / (price - stop)
        okay = entry_attention_signal(fresh) is not None
        reason = "control_entry_failed_at_fill"
    else:
        okay, reason, _ = entry_check(fresh, price)
    if not okay:
        block(book, reason)
        return
    p = book["positions"].get(symbol)
    if p and (p.get("harvested") or mode != "complete_strategy"):
        block(book, "existing_position_no_add")
        return
    if mode == "complete_strategy":
        qty = proposed_quantity(fresh, book, spec, price, p)
    else:
        sizing = suggested_position_size(fresh, cash=book["cash"], reserve_cash=0,
            portfolio_value=equity(book), profile=spec["profile"],
            existing_value=(p["shares"] * price if p else 0), whole_shares=True)
        qty = int(sizing.get("shares") or 0)
    qty = min(qty, math.floor(book["cash"] / (price * (1 + spec["fee_bps"] / 10000))))
    if qty <= 0:
        block(book, "quantity_risk_cash_or_target_limit")
        return
    fee = qty * price * spec["fee_bps"] / 10000
    book["cash"] -= qty * price + fee
    if p:
        total = p["shares"] + qty
        p["avg_cost"] = (p["avg_cost"] * p["shares"] + price * qty) / total
        p["entry_fee_per_share"] = (p["entry_fee_per_share"] * p["shares"] + fee) / total
        p["shares"] = total
        # Adds retain the original exit plan.
    else:
        book["positions"][symbol] = {"shares": qty, "avg_cost": price,
            "entry_fee_per_share": fee / qty, "entry_stop": fresh["levels"].get("entry_stop") or fresh["levels"]["stop"],
            "entry_target": fresh["target_plan"]["base_target"],
            "entry_stretch_target": fresh["target_plan"].get("stretch_target"),
            "entry_horizon_days": (fresh.get("holding_horizon") or {}).get("max_days"),
            "stop": fresh["levels"].get("entry_stop") or fresh["levels"]["stop"], "harvested": False,
            "peak": market, "opened_at": observed, "profit_steps": []}
    book["trades"].append({"symbol": symbol, "side": "BUY", "shares": qty,
        "price": price, "fees": fee, "observed_at": observed,
        "signal_at": pending["observed_at"], "reason": pending["reason"],
        "deterministic_score": a.get("deterministic_score"), "analyst_score": a.get("analyst_score"),
        "entry_target": fresh["target_plan"]["base_target"], "entry_stop": fresh["levels"].get("entry_stop") or fresh["levels"]["stop"]})
    book["fills"] += 1


def _manage(book, mode, spec, a, observed):
    symbol, price = a["symbol"], float(a["price"])
    p = book["positions"].get(symbol)
    if not p or symbol in book["pending"]:
        return
    reason, qty = None, p["shares"]
    if (a.get("thesis_assessment") or {}).get("invalidated"):
        reason = "THESIS_EXIT"
    elif mode == "complete_strategy":
        if price <= p["stop"]:
            reason = "INITIAL_STOP" if not p["harvested"] else "MOMENTUM_TRAIL"
        elif not p["harvested"] and price >= p["entry_target"] and price > p["avg_cost"]:
            reason = "PROFIT_CASH_WITHDRAWAL"
        elif p["harvested"]:
            p["peak"] = max(p["peak"], price)
            t = a.get("technicals") or {}
            p["stop"] = trailing_stop(p["stop"], p["peak"], number(t.get("atr")), price,
                                      number(t.get("ema20")), number(t.get("rsi")))
            if price <= p["stop"]:
                reason = "MOMENTUM_TRAIL"
    else:
        pd = {**p, "account": "Experiment", "shares": p["shares"]}
        try:
            action, _ = position_action(copy.deepcopy(a), price, pd)
            if action == "EXIT":
                reason = "THESIS_EXIT"
            elif action in {"REDUCE", "TAKE PARTIAL PROFIT"}:
                result = copy.deepcopy(a)
                position_action(result, price, pd)
                plan = position_action_plan(action, result, price, {**pd, "account": "Avanza"})
                stage = str(result.get("profit_take_reason") or action)
                if plan and stage not in p["profit_steps"] and plan.get("suggested_shares", 0) > 0:
                    qty, reason = int(plan["suggested_shares"]), action
                    p["profit_steps"].append(stage)
        except (KeyError, TypeError, ValueError):
            block(book, "control_management_data_incomplete")
    if reason:
        book["pending"][symbol] = {"side": "SELL", "shares": qty, "reason": reason, "observed_at": observed}


def advance(state, observations, now, market_open, benchmark=None, benchmark_asof=None):
    """Advance only through fresh observations; reproducible and duplicate-safe."""
    ensure_single_account(state)
    spec, fresh = state["spec"], []
    now_dt = timestamp(now)
    trial = state.get("trial")
    if trial and (trial["status"] == "completed" or (trial.get("ends_at") and now_dt and now_dt >= timestamp(trial["ends_at"]))):
        if trial["status"] != "completed":
            book = state["variants"]["complete_strategy"]
            trial.update(status="completed", completed_at=now, final_equity=equity(book))
            trial["cancelled_pending"] = copy.deepcopy(book["pending"])
            book["pending"] = {}
        return {"status": "trial_completed", "observations": 0, "fills": 0}
    state["last_market_open"] = bool(market_open)
    if not market_open:
        state["last_cycle"] = now
        return {"status": "market_closed", "observations": 0, "fills": 0}
    for a in observations:
        observed = a.get("asof")
        if a.get("symbol") and all(str(observed or "") <= book["seen"].get(a["symbol"], "")
                                    for book in state["variants"].values()):
            continue
        dt = timestamp(observed)
        price = number(a.get("price"))
        if dt is None or price is None or price <= 0 or now_dt is None or not 0 <= (now_dt - dt).total_seconds() <= spec["fresh_seconds"]:
            state["coverage"]["stale_or_invalid"] = state["coverage"].get("stale_or_invalid", 0) + 1
            continue
        fresh.append(a)
    # Highest-scoring candidates get cash first regardless of scan input order.
    fresh.sort(key=lambda a: (-(number(a.get("deterministic_score")) or 0), a["symbol"]))
    before = sum(b["fills"] for b in state["variants"].values())
    # Mark all currently observed stocks before allocating cash among candidates.
    for book in state["variants"].values():
        for a in fresh:
            if a["asof"] > book["seen"].get(a["symbol"], ""):
                book["marks"][a["symbol"]] = float(a["price"])
    if trial and trial["status"] == "waiting_for_inputs":
        if not (now_dt and now_dt >= timestamp(trial["armed_at"]) and fresh
                and any(number(a.get("analyst_score")) is not None for a in fresh)):
            state["last_cycle"] = now
            state["coverage"]["trial_waiting_for_inputs_cycles"] = state["coverage"].get("trial_waiting_for_inputs_cycles", 0) + 1
            return {"status": "trial_waiting_for_inputs", "observations": 0, "fills": 0}
        local = now_dt.astimezone(ZoneInfo("America/New_York"))
        month, year = (1, local.year + 1) if local.month == 12 else (local.month + 1, local.year)
        finish = local.replace(year=year, month=month, day=min(local.day, monthrange(year, month)[1]))
        book = state["variants"]["complete_strategy"]
        trial.update(status="running", started_at=now, ends_at=finish.astimezone(timezone.utc).isoformat(),
            baseline_equity=equity(book), benchmark_start=benchmark, benchmark_last=benchmark,
            baseline_trade_count=len(book["trades"]), peak_equity=equity(book))
    for a in fresh:
        observed, symbol = a["asof"], a["symbol"]
        seen_any = False
        for mode, book in state["variants"].items():
            if observed <= book["seen"].get(symbol, ""):
                continue
            seen_any = True
            book["seen"][symbol] = observed
            book["marks"][symbol] = float(a["price"])
            _fill(book, mode, spec, a, observed)
            _manage(book, mode, spec, a, observed)
            p = book["positions"].get(symbol)
            if symbol in book["pending"] or (p and (mode != "complete_strategy" or p["harvested"])):
                continue
            if book["closed_dates"].get(symbol) == observed[:10]:
                continue
            if mode == "current_rules_control":
                okay, reason = entry_attention_signal(a) is not None, "control_gate"
            else:
                okay, reason, _ = entry_check(a)
            if okay:
                book["pending"][symbol] = {"side": "BUY", "reason": reason, "observed_at": observed,
                    "levels": copy.deepcopy(a["levels"]), "target_plan": copy.deepcopy(a["target_plan"])}
            else:
                block(book, reason)
        if seen_any:
            state["coverage"]["total_fresh_observations"] = state["coverage"].get("total_fresh_observations", 0) + 1
            analyst_key = "analyst_missing_observations" if number(a.get("analyst_score")) is None else "analyst_available_observations"
            state["coverage"][analyst_key] = state["coverage"].get(analyst_key, 0) + 1
            okay, reason, _ = entry_check(a)
            key = "qualified_entry" if okay else reason
            state["coverage"][key] = state["coverage"].get(key, 0) + 1
    if fresh:
        if trial:
            book = state["variants"]["complete_strategy"]
            value = equity(book)
            trial["peak_equity"] = max(trial["peak_equity"], value)
            trial["max_drawdown_pct"] = min(trial["max_drawdown_pct"], (value / trial["peak_equity"] - 1) * 100)
            trial["valuation_asof"] = now
            if number(benchmark) and benchmark > 0:
                trial["benchmark_last"] = benchmark
                trial["benchmark_asof"] = benchmark_asof or now
        first_observation = state["started_at"] is None
        state["started_at"] = state["started_at"] or now
        if number(benchmark) and benchmark > 0:
            if first_observation:
                state["benchmark_start"] = benchmark
            state["benchmark_last"] = benchmark
        for book in state["variants"].values():
            value = equity(book)
            book["peak_equity"] = max(book["peak_equity"], value)
            book["max_drawdown_pct"] = min(book["max_drawdown_pct"], (value / book["peak_equity"] - 1) * 100)
            book["samples"] += 1
            book["cash_pct_sum"] += book["cash"] / value * 100 if value > 0 else 0
            row = {"asof": now, "equity": value, "cash": book["cash"], "positions": len(book["positions"])}
            # Retain one curve point per half-hour; trades retain their full timestamps.
            slot = now[:14] + ("00" if now_dt.minute < 30 else "30")
            if book["curve"] and book["curve"][-1].get("slot") == slot:
                book["curve"][-1] = {**row, "slot": slot}
            else:
                book["curve"].append({**row, "slot": slot})
    state["last_cycle"] = now
    return {"status": "observing" if state["started_at"] else "waiting_for_fresh_quotes", "observations": len(fresh),
            "fills": sum(b["fills"] for b in state["variants"].values()) - before}


def summary(state):
    ensure_single_account(state)
    benchmark = None
    if state.get("benchmark_start") and state.get("benchmark_last"):
        benchmark = (state["benchmark_last"] / state["benchmark_start"] - 1) * 100
    variants = {}
    for mode, book in state["variants"].items():
        value = equity(book)
        sells = [t for t in book["trades"] if t["side"] == "SELL"]
        ret = (value / state["spec"]["starting_cash"] - 1) * 100
        monthly_closes = {}
        for point in book["curve"]:
            monthly_closes[point["asof"][:7]] = point["equity"]
        monthly_returns = {}
        previous = state["spec"]["starting_cash"]
        for month, close in sorted(monthly_closes.items()):
            monthly_returns[month] = round((close / previous - 1) * 100, 4)
            previous = close
        variants[mode] = {"cash": round(book["cash"], 2), "equity": round(value, 2),
            "return_pct": round(ret, 4), "max_drawdown_pct": round(book["max_drawdown_pct"], 4),
            "average_cash_pct": round(book["cash_pct_sum"] / book["samples"], 2) if book["samples"] else None,
            "realized_profit": round(sum(t["realized_profit"] for t in sells), 2),
            "sell_fill_win_rate_pct": round(100 * sum(t["realized_profit"] > 0 for t in sells) / len(sells), 2) if sells else None,
            "trade_count": len(book["trades"]), "positions": book["positions"],
            "monthly_returns_pct": monthly_returns,
            "partial_month": (state.get("last_cycle") or "")[:7] or None,
            "blockers": book["blockers"], "pending_count": len(book["pending"]),
            "excess_return_pct": round(ret - benchmark, 4) if benchmark is not None else None}
    return {"version": VERSION, "started_at": state["started_at"], "last_cycle": state["last_cycle"],
            "spec": state["spec"], "coverage": state["coverage"],
            "benchmark_return_pct": benchmark, "variants": variants,
            "trial": trial_summary(state),
            "status": ("trial_" + state["trial"]["status"]) if state.get("trial") else "observing" if state["started_at"] else ("waiting_for_fresh_quotes" if state.get("last_market_open") else "waiting_for_market_open")}
