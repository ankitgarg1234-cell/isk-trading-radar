from __future__ import annotations

import math
from typing import Any

from .rules import (
    EXECUTION_ALLOWANCE_BPS,
    MAX_HOLDINGS,
    SLIPPAGE_BPS,
    estimated_commission,
)


def _side_bps() -> float:
    return (SLIPPAGE_BPS + EXECUTION_ALLOWANCE_BPS) / 10_000.0


def _sell_proceeds(price: float, shares: int) -> float:
    if shares <= 0 or price <= 0:
        return 0.0
    gross = price * shares
    return gross * (1.0 - _side_bps()) - estimated_commission(shares)


def _buy_cash(price: float, shares: int) -> float:
    if shares <= 0 or price <= 0:
        return 0.0
    gross = price * shares
    return gross * (1.0 + _side_bps()) + estimated_commission(shares)


def _rank_value(rank: Any) -> int:
    return int(rank) if isinstance(rank, int) else 9999


def build_portfolio_plan(snapshot: dict, positions: list[dict], cash_usd: float, reserved_slots: int = 0) -> dict:
    """Create a deterministic month-end order proposal.

    Quantities use the signal-date close only. The next-session opening fill is
    intentionally unknown and must later be recorded separately.
    """
    regime = (snapshot.get("regime") or {}).get("state")
    candidate_rows = snapshot.get("candidates") or []
    candidates = {row["symbol"]: row for row in candidate_rows}
    holding_checks = snapshot.get("holding_checks") or {}
    positions_by_symbol = {str(p["symbol"]).upper(): dict(p) for p in positions}
    warnings: list[str] = []
    reserved_slots = max(0, int(reserved_slots or 0))

    if regime == "BEAR":
        exits = []
        for symbol, pos in sorted(positions_by_symbol.items()):
            shares = int(pos.get("shares") or 0)
            if shares <= 0:
                continue
            check = holding_checks.get(symbol) or {}
            price = float(check.get("price") or 0)
            exits.append(
                {
                    "symbol": symbol,
                    "side": "SELL",
                    "shares": shares,
                    "priority": 1,
                    "reason": "SPY total-return index is at or below EMA200; BEAR overrides equity purchases",
                    "signal_price": price or None,
                }
            )
        return {
            "regime": "BEAR",
            "selected": [],
            "retained": [],
            "new_entries": [],
            "exits": exits,
            "orders": exits,
            "target_equity_exposure": 0.0,
            "target_cash_weight": 1.0,
            "target_weights": {},
            "target_nav": None,
            "sizing_complete": True,
            "warnings": warnings,
        }

    retained: list[str] = []
    frozen_review: set[str] = set()
    exit_reasons: dict[str, str] = {}

    for symbol, pos in sorted(positions_by_symbol.items()):
        if int(pos.get("shares") or 0) <= 0:
            continue
        if bool(pos.get("pending_stop_exit")):
            exit_reasons[symbol] = "Previously triggered closing-price trailing stop; pending stop exit takes precedence"
            continue
        if pos.get("pending_rule_exit_reason"):
            exit_reasons[symbol] = str(pos.get("pending_rule_exit_reason"))
            continue

        check = holding_checks.get(symbol)
        if not check:
            retained.append(symbol)
            frozen_review.add(symbol)
            warnings.append(f"{symbol}: signal data unavailable; retained for review with no additions")
            continue

        if bool(check.get("membership_exit")):
            exit_reasons[symbol] = "S&P 500 membership has ended; exit at the next executable session"
            continue

        fund = str(check.get("fundamental_status") or "REVIEW")
        if fund == "FAIL":
            exit_reasons[symbol] = check.get("fundamental_reason") or "Valid fundamental check failed"
            continue

        momentum_positive = check.get("momentum_positive")
        if momentum_positive is False:
            exit_reasons[symbol] = "Momentum score is not positive"
            continue

        rank = check.get("rank")
        if isinstance(rank, int) and rank > 35:
            exit_reasons[symbol] = "Eligible incumbent ranks above the 1–35 retention buffer"
            continue

        # Missing market data alone is not deterioration. With no valid rank we
        # retain provisionally, but block additions until data are available.
        if momentum_positive is None or rank is None:
            retained.append(symbol)
            frozen_review.add(symbol)
            warnings.append(f"{symbol}: required market data unavailable; retained for review with no additions")
            continue

        if fund == "REVIEW":
            retained.append(symbol)
            frozen_review.add(symbol)
            warnings.append(f"{symbol}: fundamentals review; last verified status retained provisionally and additions blocked")
            continue

        if isinstance(rank, int) and rank <= 35:
            retained.append(symbol)
        else:
            exit_reasons[symbol] = "Eligible incumbent ranks above the 1–35 retention buffer"

    if len(retained) > MAX_HOLDINGS:
        warnings.append("More than 20 incumbent positions are marked retained; no new entries will be added")

    selected = list(retained[:MAX_HOLDINGS])
    new_entries: list[str] = []
    available_slots = max(0, MAX_HOLDINGS - reserved_slots)
    for row in candidate_rows:
        if len(selected) >= available_slots:
            break
        if int(row.get("rank") or 9999) > 20:
            continue
        symbol = str(row["symbol"]).upper()
        if symbol in selected or symbol in positions_by_symbol:
            continue
        if row.get("fundamental_status") != "PASS" or float(row.get("score") or 0) <= 0:
            continue
        selected.append(symbol)
        new_entries.append(symbol)

    n = len(selected)
    target_equity_exposure = n / MAX_HOLDINGS if n else 0.0
    target_cash_weight = 1.0 - target_equity_exposure

    def forced_exit_orders() -> list[dict]:
        out: list[dict] = []
        for symbol, reason in exit_reasons.items():
            pos = positions_by_symbol[symbol]
            shares = int(pos.get("shares") or 0)
            if shares <= 0:
                continue
            price = float((holding_checks.get(symbol) or {}).get("price") or 0)
            out.append(
                {
                    "symbol": symbol,
                    "side": "SELL",
                    "shares": shares,
                    "priority": 1,
                    "reason": reason,
                    "signal_price": price or None,
                    "kind": "EXIT",
                }
            )
        return out

    selected_data: dict[str, dict] = {}
    for symbol in selected:
        row = candidates.get(symbol)
        if row:
            selected_data[symbol] = row
        else:
            selected_data[symbol] = holding_checks.get(symbol) or {}

    # A missing valid ATR/price blocks the sizing proposal rather than fabricating it.
    for symbol, row in selected_data.items():
        price = row.get("price")
        atr_pct = row.get("atr_pct")
        if price is None or atr_pct is None or float(price) <= 0 or float(atr_pct) <= 0:
            warnings.append(f"{symbol}: valid price/ATR unavailable; monthly resize quantities withheld")
            return {
                "regime": "BULL",
                "selected": selected,
                "retained": retained,
                "new_entries": new_entries,
                "exits": forced_exit_orders(),
                "orders": forced_exit_orders(),
                "target_equity_exposure": target_equity_exposure,
                "target_cash_weight": target_cash_weight,
                "target_weights": {},
                "target_nav": None,
                "sizing_complete": False,
                "warnings": warnings,
            }

    inverse = {symbol: 1.0 / float(row["atr_pct"]) for symbol, row in selected_data.items()}
    inverse_total = sum(inverse.values())
    target_weights = {
        symbol: target_equity_exposure * value / inverse_total
        for symbol, value in inverse.items()
    }

    sector_weights: dict[str, float] = {}
    issuer_groups: dict[str, dict] = {}
    for symbol, weight in target_weights.items():
        row = selected_data[symbol]
        sector = str(row.get("sector") or "Unknown")
        sector_weights[sector] = sector_weights.get(sector, 0.0) + weight
        issuer_id = str(row.get("issuer_id") or row.get("security_id") or symbol)
        group = issuer_groups.setdefault(issuer_id, {"symbols": [], "weight": 0.0})
        group["symbols"].append(symbol)
        group["weight"] += weight
    sector_concentration = sorted(
        ({"sector": sector, "weight": weight} for sector, weight in sector_weights.items()),
        key=lambda x: (-x["weight"], x["sector"]),
    )
    combined_share_classes = sorted(
        (
            {"security_id": issuer_id, "symbols": sorted(group["symbols"]), "weight": group["weight"]}
            for issuer_id, group in issuer_groups.items()
            if len(group["symbols"]) > 1
        ),
        key=lambda x: (-x["weight"], x["security_id"]),
    )

    # NAV is marked at signal-date closes; future opening fills are not used.
    nav = max(0.0, float(cash_usd))
    for symbol, pos in positions_by_symbol.items():
        check = holding_checks.get(symbol) or candidates.get(symbol) or {}
        price = float(check.get("price") or 0)
        if price <= 0:
            warnings.append(f"{symbol}: NAV mark unavailable")
            return {
                "regime": "BULL",
                "selected": selected,
                "retained": retained,
                "new_entries": new_entries,
                "exits": forced_exit_orders(),
                "orders": forced_exit_orders(),
                "target_equity_exposure": target_equity_exposure,
                "target_cash_weight": target_cash_weight,
                "target_weights": target_weights,
                "target_nav": None,
                "sizing_complete": False,
                "warnings": warnings,
            }
        nav += int(pos.get("shares") or 0) * price

    desired_shares: dict[str, int] = {}
    for symbol in selected:
        price = float(selected_data[symbol]["price"])
        target_value = target_weights[symbol] * nav
        desired = max(0, math.floor(target_value / price))
        current = int((positions_by_symbol.get(symbol) or {}).get("shares") or 0)
        if symbol in frozen_review:
            desired = min(current, desired)
        desired_shares[symbol] = desired

    sell_orders: list[dict] = forced_exit_orders()

    buy_orders: list[dict] = []
    for symbol in selected:
        current = int((positions_by_symbol.get(symbol) or {}).get("shares") or 0)
        desired = desired_shares[symbol]
        delta = desired - current
        row = selected_data[symbol]
        rank = (candidates.get(symbol) or holding_checks.get(symbol) or {}).get("rank")
        if delta < 0:
            sell_orders.append(
                {
                    "symbol": symbol,
                    "side": "SELL",
                    "shares": abs(delta),
                    "priority": 2,
                    "reason": "Monthly inverse-ATR resize toward target weight; stop/peak history is preserved",
                    "signal_price": float(row["price"]),
                    "kind": "TRIM",
                    "rank": rank,
                }
            )
        elif delta > 0 and symbol not in frozen_review:
            buy_orders.append(
                {
                    "symbol": symbol,
                    "side": "BUY",
                    "shares": delta,
                    "priority": 3,
                    "reason": "Monthly inverse-ATR resize toward target weight" if current else "Highest-ranked verified Top-20 vacancy fill",
                    "signal_price": float(row["price"]),
                    "kind": "ADD" if current else "NEW",
                    "rank": rank,
                }
            )

    sell_orders.sort(key=lambda o: (o["priority"], _rank_value(o.get("rank")), o["symbol"]))
    available = max(0.0, float(cash_usd))
    for order in sell_orders:
        price = float(order.get("signal_price") or 0)
        available += _sell_proceeds(price, int(order["shares"]))

    # Fund better-ranked purchases first. Any gap-induced shortfall at actual fill
    # is handled again at execution; this proposal only reserves modeled costs.
    buy_orders.sort(key=lambda o: (_rank_value(o.get("rank")), o["symbol"]))
    total_required = sum(_buy_cash(float(o["signal_price"]), int(o["shares"])) for o in buy_orders)
    if total_required > available:
        for order in reversed(buy_orders):
            if total_required <= available:
                break
            shares = int(order["shares"])
            if shares <= 0:
                continue
            price = float(order["signal_price"])
            current_cost = _buy_cash(price, shares)
            shortfall = total_required - available
            approx_per_share = max(0.01, price * (1.0 + _side_bps()))
            cut = min(shares, max(1, math.ceil(shortfall / approx_per_share)))
            new_shares = shares - cut
            new_cost = _buy_cash(price, new_shares)
            order["shares"] = new_shares
            order["funding_adjusted"] = True
            total_required -= current_cost - new_cost

    buy_orders = [o for o in buy_orders if int(o["shares"]) > 0]
    estimated_cash_after = available - sum(
        _buy_cash(float(o["signal_price"]), int(o["shares"])) for o in buy_orders
    )

    orders = sell_orders + buy_orders
    return {
        "regime": "BULL",
        "selected": selected,
        "retained": retained,
        "review_frozen": sorted(frozen_review),
        "new_entries": new_entries,
        "exits": [o for o in sell_orders if o.get("kind") == "EXIT"],
        "orders": orders,
        "target_equity_exposure": target_equity_exposure,
        "target_cash_weight": target_cash_weight,
        "target_weights": target_weights,
        "sector_concentration": sector_concentration,
        "combined_share_classes": combined_share_classes,
        "target_nav": nav,
        "desired_shares": desired_shares,
        "estimated_cash_after": max(0.0, estimated_cash_after),
        "sizing_complete": True,
        "warnings": warnings,
        "reserved_slots": reserved_slots,
        "execution_note": "Quantities use signal-date closes; realized exposure must be recomputed from actual next-session fills. Mid-month system exits reserve their vacancies until a later month-end cycle.",
    }
