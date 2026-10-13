"""Optional Tiingo EOD *read-only* alternative to a stalled Marketstack feed.

Uses customer-provided TIINGO_API_TOKEN, never a shared or guessed credential.
Tiingo raw/adjusted semantics are explicitly preserved, not rebranded as the
frozen vendor's total-return series. No automatic orders or background sync.
"""
from __future__ import annotations

from datetime import date
from hashlib import sha256
import json
import math
import os
import re

import httpx

_API = "https://api.tiingo.com/tiingo/daily"
_TICKER = re.compile(r"^[A-Z0-9.-]{1,15}$")


class TiingoDataHold(ValueError):
    pass


def _positive(row, key, *, zero=False):
    val = row.get(key)
    if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val):
        raise TiingoDataHold("Missing/invalid Tiingo field " + key)
    if val < 0 if zero else val <= 0:
        raise TiingoDataHold("Nonpositive Tiingo field " + key)
    return float(val)


def tiingo_eod_observation(ticker, start, end, *, token=None, client=None):
    """One bounded symbol request with an immutable raw-body receipt.

    Caller explicitly chooses to run the probe and bears subscription/API
    quota obligations. Inject httpx.Client for deterministic tests.
    """
    if not isinstance(ticker, str) or not _TICKER.fullmatch(ticker):
        raise TiingoDataHold("Invalid ticker")
    if type(start) is not date or type(end) is not date or start > end or end > date.today():
        raise TiingoDataHold("Invalid or future request dates")
    if (end - start).days > 1100:
        raise TiingoDataHold("History window too large for one bounded query")
    secret = (token if token is not None else os.environ.get("TIINGO_API_TOKEN", "")).strip()
    if not secret:
        raise TiingoDataHold("TIINGO_API_TOKEN not configured")
    owns_client = client is None
    connection = client or httpx.Client(timeout=18.0, follow_redirects=False)
    try:
        try:
            response = connection.get(
                f"{_API}/{ticker}/prices",
                headers={"Authorization": "Token " + secret, "Accept": "application/json"},
                params={"startDate": start.isoformat(), "endDate": end.isoformat()},
            )
            if response.status_code != 200 or len(response.content) > 5_000_000:
                raise TiingoDataHold("Tiingo HTTP failure or oversized response")
            body = response.content
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise TiingoDataHold("Tiingo network or JSON parsing failed") from None
    finally:
        if owns_client:
            connection.close()
    if not isinstance(payload, list) or len(payload) > 850:
        raise TiingoDataHold("Tiingo EOD format/count changed")
    seen = set()
    raw_bars = []
    adjustments = []
    for row in payload:
        if not isinstance(row, dict):
            raise TiingoDataHold("Malformed Tiingo EOD row")
        try:
            day = date.fromisoformat(row["date"][:10])
        except (KeyError, TypeError, ValueError) as exc:
            raise TiingoDataHold("Invalid Tiingo EOD date") from exc
        if day in seen or day < start or day > end:
            raise TiingoDataHold("Duplicate/out-of-range Tiingo observation")
        seen.add(day)
        raw = {key: _positive(row, key, zero=(key == "volume"))
               for key in ("open", "high", "low", "close", "volume")}
        if raw["high"] < max(raw["open"], raw["close"]) or raw["low"] > min(raw["open"], raw["close"]):
            raise TiingoDataHold("Invalid Tiingo OHLC values")
        adj = _positive(row, "adjClose")
        div = _positive(row, "divCash", zero=True)
        split = _positive(row, "splitFactor")
        raw_bars.append({"ticker": ticker, "session": day.isoformat(), **raw,
                         "split_factor": split, "dividend": div})
        adjustments.append({"session": day.isoformat(), "tiingo_adj_close": adj,
                            "split_factor": split, "ex_date_dividend": div,
                            "status": "ALTERNATE_NOT_FROZEN_PARITY"})
    if not raw_bars:
        raise TiingoDataHold("Empty Tiingo history")
    raw_bars.sort(key=lambda x: x["session"])
    adjustments.sort(key=lambda x: x["session"])
    return {
        "provider": "TIINGO", "basis": "NOMINAL_OHLCV",
        "receipt_sha256": sha256(body).hexdigest(),
        "window": {"from": start.isoformat(), "to": end.isoformat()},
        "bars": raw_bars, "vendor_specific_adjustments": adjustments,
        "retrieval": "CUSTOMER_TOKEN_ONE_SHOT", "trading_approved": False,
        "frozen_adjustment_parity_verified": False,
        "attribution": "Tiingo End-of-Day Stock Price API",
    }
