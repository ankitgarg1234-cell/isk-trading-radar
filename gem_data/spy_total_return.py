"""Independent, offline SPY benchmark candidate (not a certified index).

Reconstructs SPY buy-and-hold from nominal closes and confirmed cash
distributions. Maintains ex-date receivables and pays on payable date.
Also reports an ex-date dividend-reinvestment total-return approximation.
No network/broker/orders and no assumption that future SPY payments are known.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from hashlib import sha256
from datetime import date
import json
import re


class SpyAuditHold(ValueError):
    pass


def _amt(x, label, *, allow_zero=False):
    try:
        value = Decimal(str(x))
    except (InvalidOperation, ValueError):
        raise SpyAuditHold("Bad " + label) from None
    if not value.is_finite() or (value < 0 if allow_zero else value <= 0):
        raise SpyAuditHold("Nonpositive or missing " + label)
    return value


def _day(s):
    try:
        d = date.fromisoformat(s)
        if d.isoformat() != s:
            raise ValueError()
        return d
    except (ValueError, TypeError, AttributeError):
        raise SpyAuditHold("Invalid ISO date") from None


def reconstruct_spy(bars, distributions, *, initial_cash="10000", cost_bps="20"):
    if not isinstance(bars,list) or len(bars)<2 or not isinstance(distributions,list):
        raise SpyAuditHold("At least two SPY closing prices and dividend inventory required")
    sessions = [_day(b["session"]) for b in bars]
    if sessions != sorted(set(sessions)):
        raise SpyAuditHold("SPY sessions missing ordering or duplicate")
    closes = [_amt(b["close"], "SPY nominal close") for b in bars]
    opening = _amt(bars[0]["open"],"SPY initial open")
    principal = _amt(initial_cash,"SPY initial capital")
    bps = _amt(cost_bps,"transaction bps",allow_zero=True)
    if bps > 1000:
        raise SpyAuditHold("Unreasonable transaction cost")
    qty = int(principal/(opening*(1+bps/10000)))
    if qty<=0:
        raise SpyAuditHold("Insufficient capital for SPY")
    cash = principal-Decimal(qty)*opening*(1+bps/10000)
    events = {}
    for dist in distributions:
        ex = _day(dist["ex_date"])
        payable = _day(dist["payable_date"])
        amount = _amt(dist["cash_per_share"],"SPY dividend per share")
        proof = dist.get("issuer_receipt_sha256")
        if ex>payable or not isinstance(proof,str) or not re.fullmatch(r"[a-f0-9]{64}",proof):
            raise SpyAuditHold("Distribution missing issuer evidence or invalid dates")
        if ex not in sessions:
            raise SpyAuditHold("Dividend ex-date does not align to SPY price sessions")
        if ex in events:
            raise SpyAuditHold("Duplicate SPY distribution ex-date")
        events[ex] = {"payable":payable,"amount":amount}
    receivables={}
    index_value=Decimal(1)
    detail=[]
    for i,day in enumerate(sessions):
        if i:
            index_value *= (closes[i]+events.get(day,{}).get("amount",Decimal(0)))/closes[i-1]
        elif day in events:
            raise SpyAuditHold("Initial SPY day has dividend without prior close")
        if day in events:
            payable=events[day]["payable"]
            receivables[payable]=receivables.get(payable,Decimal(0))+events[day]["amount"]*qty
        paid=receivables.pop(day,Decimal(0))
        cash += paid
        pending=sum(receivables.values(),Decimal(0))
        nav = cash + Decimal(qty)*closes[i] + pending
        detail.append({"session":day.isoformat(),
                       "cash_usd":round(float(cash),6),
                       "receivable_usd":round(float(pending),6),
                       "nav_usd":round(float(nav),6),
                       "cash_dividend_paid_usd":round(float(paid),6),
                       "dividend_reinvested_index":round(float(index_value),10)})
    result = {
        "schema":"gem-spy-benchmark-candidate-v1",
        "status":"RECONSTRUCTED_NOT_SOURCE_CERTIFIED",
        "shares":qty,
        "starting_capital":str(principal),
        "initial_open":str(opening),
        "initial_fee":str(Decimal(qty)*opening*bps/10000),
        "cash_dividend_policy":"ACCRUE_EX_DATE_PAY_PAYABLE_DATE_NO_REINVESTMENT",
        "index_policy":"EX_DATE_DIVIDEND_REINVESTMENT_APPROXIMATION",
        "daily":detail,
        "source_verification":"PRIMARY_ISSUER_DISTRIBUTIONS_AND_EOD_PARITY_REQUIRED",
        "broker_orders_sent":0,
    }
    result["reconstruction_sha256"]=sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()
    return result
