"""GEMv1 forward monthly *paper plan*; never executes or certifies trades.

Consumes a verified external ranking snapshot and explicit next-open prices.
No broker, network, database, or scheduler. Missing data fails closed.
"""
from __future__ import annotations
from datetime import date
from hashlib import sha256
import json
import math


class PaperHold(ValueError):
    pass


def _money(x, label):
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or x < 0:
        raise PaperHold("Invalid " + label)
    return float(x)


def propose_rebalance(ranking: dict, portfolio: dict, next_open: dict, *, cost_bps=20.0) -> dict:
    """Target 20% per selected name, sell first, then whole-share buys.

    This is an indicative immutable plan, not the archived simulator's
    full event/settlement/dividend ledger. All proposed orders are disabled.
    """
    if ranking.get("state") != "INDEPENDENTLY_CERTIFIED_FOR_PAPER" or ranking.get("paper_execution_authorized") is not True:
        raise PaperHold("Ranking not independently certified for paper")
    picks = ranking.get("selected")
    if not isinstance(picks, list) or len(picks) > 5 or len(set(picks)) != 5:
        raise PaperHold("At most five distinct qualified selections required")
    if not isinstance(next_open, dict) or not isinstance(portfolio, dict):
        raise PaperHold("Missing portfolio or next-open prices")
    positions = portfolio.get("shares")
    if not isinstance(positions, dict) or any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in positions.values()):
        raise PaperHold("Invalid whole-share holdings")
    cash = _money(portfolio.get("cash"), "cash")
    names = set(positions) | set(picks)
    if set(next_open) != names:
        raise PaperHold("Missing or extraneous next-open prices")
    prices = {name: _money(next_open[name], "next-open price") for name in names}
    if any(p <= 0 for p in prices.values()):
        raise PaperHold("Nonpositive next-open price")
    bps = _money(cost_bps, "transaction cost bps")
    if bps > 1000:
        raise PaperHold("Unreasonable cost assumption")
    nav = cash + sum(positions.get(name, 0) * prices[name] for name in names)
    target = nav / 5
    orders = []
    holdings = dict(positions)
    for name in sorted(names):
        wanted = math.floor(target / prices[name]) if name in picks else 0
        sell = max(0, holdings.get(name, 0) - wanted)
        if sell:
            gross = sell * prices[name]
            fee = gross * bps / 10000
            cash += gross - fee
            holdings[name] -= sell
            orders.append(dict(ticker=name, side="SELL", shares=sell, assumed_open=prices[name], estimated_cost=fee))
    for name in picks:
        wanted = math.floor(target / (prices[name] * (1 + bps / 10000)))
        buy = max(0, wanted - holdings.get(name, 0))
        buy = min(buy, math.floor((cash + 1e-9) / (prices[name] * (1 + bps / 10000))))
        if buy:
            gross = buy * prices[name]
            fee = gross * bps / 10000
            cash -= gross + fee
            holdings[name] = holdings.get(name, 0) + buy
            orders.append(dict(ticker=name, side="BUY", shares=buy, assumed_open=prices[name], estimated_cost=fee))
    if cash < -1e-6:
        raise PaperHold("Negative simulated cash")
    result = dict(schema="gem-paper-rebalance-proposal-v1",
                  signal_session=ranking.get("signal_session"),
                  selected=picks, starting_nav=nav, ending_cash=cash,
                  ending_shares={k:v for k,v in sorted(holdings.items()) if v},
                  indicative_orders=orders,
                  execution="DISABLED", broker_orders_sent=0,
                  certification="PROPOSAL_ONLY_NOT_EXECUTION_RECONCILIATION")
    result["proposal_hash"] = sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
    return result
