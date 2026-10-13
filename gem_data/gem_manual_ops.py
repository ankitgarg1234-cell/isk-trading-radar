"""GEMv1 manual-broker workflow: indicative tickets and user-entered ledger.

No broker import, broker API, order submission, credential storage or automated
execution. Only explicit user-supplied fills change the paper/reconciliation
ledger. All arithmetic uses Decimal and every event is hash-chained.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
from hashlib import sha256
import json


class ManualLedgerHold(ValueError):
    pass


def _decimal(value, label, *, allow_zero=True):
    if isinstance(value, bool) or isinstance(value, (dict, list)) or value is None:
        raise ManualLedgerHold("Invalid " + label)
    try:
        val = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ManualLedgerHold("Invalid " + label) from exc
    if not val.is_finite() or val < 0 or (val == 0 and not allow_zero):
        raise ManualLedgerHold("Negative/zero " + label)
    return val


def _int(value, label):
    if isinstance(value, bool) or type(value) is not int or value <= 0:
        raise ManualLedgerHold("Invalid integer " + label)
    return value


def _id(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 120:
        raise ManualLedgerHold("Missing event id")
    return value


def _session(value):
    try:
        if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
            raise ValueError("not canonical")
    except (ValueError, TypeError) as exc:
        raise ManualLedgerHold("Invalid event trade date") from exc
    return value


def _hash(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             default=str, allow_nan=False).encode()).hexdigest()


def replay_manual_events(initial_cash, events, statement=None):
    """Replay append-only manually reported events; reconcile external statement.

    Supported: FILL, DIVIDEND, CASH_DEPOSIT, CASH_WITHDRAWAL, SPLIT, SPINOFF,
    MERGER_CASH. Fractional shares are a HOLD until manually resolved.
    The statement is a manually provided export, not independently attested.
    """
    cash = _decimal(initial_cash, "initial_cash")
    if not isinstance(events, list):
        raise ManualLedgerHold("Event list required")
    positions = {}
    event_ids = set()
    head = "0" * 64
    audit = []
    last_date = ""
    for event in events:
        if not isinstance(event, dict):
            raise ManualLedgerHold("Malformed event")
        eid = _id(event.get("event_id"))
        if eid in event_ids:
            raise ManualLedgerHold("Duplicate event id")
        event_ids.add(eid)
        day = _session(event.get("trade_date"))
        if day < last_date:
            raise ManualLedgerHold("Events out of chronological order")
        last_date = day
        kind = event.get("type")
        ticker = event.get("ticker")
        if kind in ("FILL", "SPLIT", "SPINOFF", "MERGER_CASH", "DIVIDEND"):
            if not isinstance(ticker, str) or not ticker:
                raise ManualLedgerHold("Missing event ticker")
        if kind == "FILL":
            if event.get("source") != "MANUAL_BROKER_ENTRY":
                raise ManualLedgerHold("Manual confirmation source required")
            qty = _int(event.get("shares"), "fill shares")
            price = _decimal(event.get("price"), "fill price", allow_zero=False)
            fees = _decimal(event.get("fees"), "fill fees")
            gross = qty * price
            if event.get("side") == "BUY":
                if gross + fees > cash:
                    raise ManualLedgerHold("Insufficient cash for entered BUY")
                cash -= gross + fees
                positions[ticker] = positions.get(ticker, 0) + qty
            elif event.get("side") == "SELL":
                if positions.get(ticker, 0) < qty:
                    raise ManualLedgerHold("Entered sale exceeds shares")
                positions[ticker] -= qty
                cash += gross - fees
                if cash < 0:
                    raise ManualLedgerHold("Negative cash after sale")
            else:
                raise ManualLedgerHold("Unknown fill side")
        elif kind == "DIVIDEND":
            if positions.get(ticker, 0) == 0:
                raise ManualLedgerHold("Dividend without held security")
            cash += _decimal(event.get("amount"), "dividend amount", allow_zero=False)
        elif kind == "CASH_DEPOSIT":
            cash += _decimal(event.get("amount"), "deposit", allow_zero=False)
        elif kind == "CASH_WITHDRAWAL":
            amount = _decimal(event.get("amount"), "withdrawal", allow_zero=False)
            if amount > cash:
                raise ManualLedgerHold("Withdrawal exceeds cash")
            cash -= amount
        elif kind == "SPLIT":
            num = _int(event.get("numerator"), "split numerator")
            den = _int(event.get("denominator"), "split denominator")
            shares = positions.get(ticker, 0)
            if not shares or shares * num % den:
                raise ManualLedgerHold("Missing holding or unresolved fractional split")
            positions[ticker] = shares * num // den
        elif kind == "SPINOFF":
            num = _int(event.get("numerator"), "spinoff numerator")
            den = _int(event.get("denominator"), "spinoff denominator")
            child = event.get("child_ticker")
            if not isinstance(child, str) or not child or child == ticker:
                raise ManualLedgerHold("Invalid spinoff child")
            shares = positions.get(ticker, 0)
            if not shares or shares * num % den:
                raise ManualLedgerHold("Unresolved fractional spinoff")
            positions[child] = positions.get(child, 0) + shares * num // den
        elif kind == "MERGER_CASH":
            held = positions.get(ticker, 0)
            if not held:
                raise ManualLedgerHold("Merger on unheld shares")
            consideration = _decimal(event.get("cash_per_share"), "merger consideration")
            cash += held * consideration
            positions[ticker] = 0
        else:
            raise ManualLedgerHold("Unsupported manual event type")
        payload = {"prev": head, "event": event}
        head = _hash(payload)
        audit.append({"event_id": eid, "trade_date": day, "kind": kind,
                      "prev_hash": payload["prev"], "event_hash": head})
    positions = {t: q for t, q in sorted(positions.items()) if q}
    status = "NO_STATEMENT_ENTERED"
    diffs = []
    if statement is not None:
        if (not isinstance(statement, dict)
                or statement.get("source") != "MANUAL_BROKER_STATEMENT_EXPORT"
                or not isinstance(statement.get("statement_sha256"), str)
                or len(statement["statement_sha256"]) != 64
                or not isinstance(statement.get("shares"), dict)
                or not isinstance(statement.get("as_of"), str)):
            raise ManualLedgerHold("Statement origin/hash and complete share balances required")
        _session(statement["as_of"])
        if audit and statement["as_of"] < audit[-1]["trade_date"]:
            raise ManualLedgerHold("Statement predates latest recorded event")
        observed_cash = _decimal(statement.get("cash"), "statement cash")
        if abs(observed_cash - cash) > Decimal(".01"):
            diffs.append({"kind": "CASH", "expected": str(cash),
                          "statement": str(observed_cash)})
        observed = statement["shares"]
        if any(type(q) is not int or q < 0 for q in observed.values()):
            raise ManualLedgerHold("Invalid statement share balance")
        observed = {t: q for t, q in observed.items() if q}
        for t in sorted(set(positions) | set(observed)):
            if positions.get(t, 0) != observed.get(t, 0):
                diffs.append({"kind": "SHARES", "ticker": t,
                              "expected": positions.get(t, 0),
                              "statement": observed.get(t, 0)})
        status = "USER_STATEMENT_RECONCILED" if not diffs else "STATEMENT_MISMATCH_HOLD"
    return {
        "schema": "gem-manual-ledger-v1", "cash": str(cash), "shares": positions,
        "head": head, "events_count": len(audit), "audit": audit,
        "statement_status": status, "statement_differences": diffs,
        "source_classification": "USER_ENTERED_NO_BROKER_API",
        "broker_orders_sent": 0, "automatic_execution": False,
    }


def manual_trade_sheet(signal, ledger, reference_prices, *, bps=20):
    """Generate *indicative* five-stock tickets; never authorize submission.

    User executes independently. Entry prices are reference estimates only:
    real fills entered later in replay_manual_events always determine holdings.
    """
    if not isinstance(signal, dict) or not isinstance(ledger, dict):
        raise ManualLedgerHold("Missing signal or portfolio")
    selected = signal.get("selected")
    if (not isinstance(selected, list) or len(selected) > 5
            or len(set(selected)) != len(selected) or any(not isinstance(s, str) or not s for s in selected)):
        raise ManualLedgerHold("At most five distinct selected tickers required")
    quality = signal.get("data_status")
    if quality != "REVIEWED_COMPLETE":
        return {"schema": "gem-manual-trade-sheet-v1", "selected": selected,
                "status": "DATA_HOLD", "tickets": [],
                "reason": "Complete reviewed all-member market/SEC inputs not demonstrated",
                "broker_orders_sent": 0}
    shares = ledger.get("shares")
    if not isinstance(shares, dict) or any(type(q) is not int or q < 0 for q in shares.values()):
        raise ManualLedgerHold("Invalid current holdings")
    cash = _decimal(ledger.get("cash"), "cash")
    symbols = set(shares) | set(selected)
    if not isinstance(reference_prices, dict) or set(reference_prices) != symbols:
        raise ManualLedgerHold("Reference price missing or extraneous")
    prices = {s: _decimal(reference_prices[s], "price", allow_zero=False) for s in symbols}
    fee_factor = _decimal(bps, "bps") / Decimal(10000)
    if fee_factor > Decimal(".1"):
        raise ManualLedgerHold("Excessive transaction fee")
    nav = cash + sum(prices[s] * shares.get(s, 0) for s in symbols)
    target = nav / Decimal(5)
    positions = dict(shares)
    tickets = []
    for s in sorted(symbols):
        wanted = int((target / prices[s]).to_integral_value(rounding=ROUND_FLOOR)) if s in selected else 0
        amount = max(0, positions.get(s, 0) - wanted)
        if amount:
            cash += prices[s] * amount * (1-fee_factor)
            positions[s] -= amount
            tickets.append({"ticker": s, "side": "SELL", "estimated_shares": amount,
                            "reference_price": str(prices[s])})
    for s in selected:
        wanted = int((target / (prices[s] * (1 + fee_factor))).to_integral_value(rounding=ROUND_FLOOR))
        amount = max(0, wanted - positions.get(s, 0))
        affordable = int((cash / (prices[s] * (1 + fee_factor))).to_integral_value(rounding=ROUND_FLOOR))
        amount = min(amount, affordable)
        if amount:
            cash -= prices[s] * amount * (1+fee_factor)
            positions[s] = positions.get(s, 0) + amount
            tickets.append({"ticker": s, "side": "BUY", "estimated_shares": amount,
                            "reference_price": str(prices[s])})
    return {
        "schema": "gem-manual-trade-sheet-v1", "selected": selected,
        "status": "INDICATIVE_USER_REVIEW_REQUIRED", "signal_session": signal.get("signal_session"),
        "tickets": tickets, "reference_nav": str(nav),
        "estimated_cash_after": str(cash),
        "transaction_cost_bps": str(bps), "not_order_instructions": True,
        "broker_orders_sent": 0, "actual_fills_required": True,
        "sheet_sha256": _hash(tickets),
    }
