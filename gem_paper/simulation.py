"""Deterministic offline order preview; no submission/fill mutation exists."""
from decimal import Decimal, ROUND_FLOOR
from .common import ControlError, digest, money, positive_integer, utc

COST_RATE = Decimal("0.002")  # exact archived 20 basis points per side
SLOT_WEIGHT = Decimal("0.2")


def _shares(budget, price):
    return int((budget / price / (1 + COST_RATE)).to_integral_value(rounding=ROUND_FLOOR))


def preview_orders(*, cash, holdings, targets, open_prices, signal_at,
                   execution_at, observed_at, next_session_open_at):
    """Replay ordinary GEM V1 rebalance from a later observed session open.

    Open prices are deliberately unavailable to signal generation. The preview
    occurs after that open, for dry-run evidence only; no future quote is placed
    in a signal. Fractions/spinoffs need certified accounting and are blocked.
    next_session_open_at must come from an independently verified calendar.
    """
    signal, execution, observed, scheduled = map(utc, (
        signal_at, execution_at, observed_at, next_session_open_at))
    if not signal < execution <= observed or execution != scheduled:
        raise ControlError("Must preview the first session open after the signal")
    if len(targets) > 5 or len(targets) != len(set(targets)):
        raise ControlError("Expected up to five unique frozen targets")
    if any(not isinstance(symbol, str) or not symbol for symbol in [*holdings, *targets]):
        raise ControlError("Invalid security identifier")
    balance = money(cash)
    validated_positions = {symbol: positive_integer(quantity, allow_zero=True)
                           for symbol, quantity in holdings.items()}
    positions = {symbol: quantity for symbol, quantity in validated_positions.items() if quantity != 0}
    initial_positions = dict(positions)
    initial_cash = balance
    required = set(positions) | set(targets)
    if set(open_prices) != required:
        raise ControlError("Missing or extraneous open-price observation")
    prices = {symbol: money(value) for symbol, value in open_prices.items()}
    if any(value == 0 for value in prices.values()):
        raise ControlError("Zero open price")
    equity = balance + sum((quantity * prices[symbol] for symbol, quantity in positions.items()), Decimal(0))
    desired = {symbol: _shares(equity * SLOT_WEIGHT, prices[symbol]) for symbol in targets}
    orders = []

    def record(symbol, quantity, side):
        nonlocal balance
        gross = quantity * prices[symbol]
        cost = gross * COST_RATE
        if side == "SELL":
            balance += gross - cost
            positions[symbol] -= quantity
            if positions[symbol] == 0:
                positions.pop(symbol)
        else:
            quantity = min(quantity, _shares(balance, prices[symbol]))
            if not quantity:
                return
            gross, cost = quantity * prices[symbol], quantity * prices[symbol] * COST_RATE
            balance -= gross + cost
            positions[symbol] = positions.get(symbol, 0) + quantity
        orders.append({"ticker": symbol, "side": side, "shares": quantity,
                       "nominal_open": str(prices[symbol]), "gross": str(gross),
                       "cost": str(cost), "cash_after": str(balance)})

    # Holdings insertion order mirrors the archived account ledger. Targets
    # retain stable rank order, preserving cash-affordability tie behavior.
    for symbol in list(positions):
        excess = positions[symbol] - desired.get(symbol, 0)
        if excess > 0:
            record(symbol, excess, "SELL")
    for symbol in targets:
        deficit = desired[symbol] - positions.get(symbol, 0)
        if deficit > 0:
            record(symbol, deficit, "BUY")
    if balance < 0:
        raise ControlError("Negative preview cash")
    result = {"mode": "OFFLINE_DRY_RUN", "execution_capability": False,
              "signal_at": signal_at, "execution_at": execution_at,
              "observed_at": observed_at, "next_session_open_at": next_session_open_at,
              "initial_cash": str(initial_cash), "initial_holdings": initial_positions,
              "targets": list(targets), "open_prices": {symbol: str(price) for symbol, price in prices.items()},
              "open_equity": str(equity),
              "cost_bps_per_side": 20, "orders": orders,
              "cash": str(balance), "holdings": positions,
              "total_cost": str(sum((Decimal(order["cost"]) for order in orders), Decimal(0)))}
    result["preview_hash"] = digest(result)
    return result


def reconcile(*, expected_cash, expected_holdings, observed_cash, observed_holdings):
    """Strict equality for whole shares/cash in this offline accounting model."""
    def quantities(values):
        validated = {key: positive_integer(value, allow_zero=True) for key, value in values.items()}
        return {key: value for key, value in validated.items() if value != 0}
    cash_delta = money(observed_cash) - money(expected_cash)
    expected, observed = quantities(expected_holdings), quantities(observed_holdings)
    mismatches = {symbol: observed.get(symbol, 0) - expected.get(symbol, 0)
                  for symbol in sorted(set(expected) | set(observed))
                  if observed.get(symbol, 0) != expected.get(symbol, 0)}
    return {"passed": cash_delta == 0 and not mismatches,
            "cash_delta": str(cash_delta), "share_deltas": mismatches}
