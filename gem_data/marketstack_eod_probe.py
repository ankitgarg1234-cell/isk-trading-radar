"""Bounded, read-only Marketstack v2 EOD diagnostic for GEMv1.

This module does NOT replace any trading signal adapter, persist a position,
certify data or run unattended jobs. Vendor adjusted values must not be
assumed to reproduce the frozen total-return series until independent parity
checks pass. The key belongs in MARKETSTACK_API_KEY, never in Git.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
import math
import os
import re

import httpx

_ENDPOINT = "https://api.marketstack.com/v2/eod"
_SYMBOL_RE = re.compile(r"^[A-Z0-9.-]{1,16}$")


class MarketstackProbeError(RuntimeError):
    """Data/protocol failure that must not authorize a GEMv1 trade."""


@dataclass(frozen=True)
class EODBar:
    symbol: str
    session: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    vendor_adj_close: float
    split_factor: float | None
    dividend: float | None


@dataclass(frozen=True)
class ProbeReceipt:
    symbol: str
    date_from: date
    date_to: date
    retrieved_pages: int
    consumed_symbol_credits: int
    response_sha256: tuple[str, ...]
    first_session: date
    last_session: date
    observed_sessions: int
    rejected_sessions: tuple[str, ...] = ()
    rejected_reasons: tuple[tuple[str, str], ...] = ()
    status: str = "UNVERIFIED_VENDOR_OBSERVATION"


class MarketstackEODProbe:
    """Use at most max_credits within THIS probe; account-wide caps come later.

    Marketstack bills by requested ticker and may bill paginated requests.
    Never schedule this without a separate persisted account-wide credit guard.
    """

    def __init__(
        self, *,
        key: str | None = None,
        max_credits: int = 20,
        page_limit: int = 1000,
        client: httpx.Client | None = None,
    ):
        self._key = (key if key is not None else os.environ.get("MARKETSTACK_API_KEY", "")).strip()
        if not self._key:
            raise MarketstackProbeError("MARKETSTACK_API_KEY is not set")
        if not 1 <= max_credits <= 1000 or not 1 <= page_limit <= 1000:
            raise ValueError("invalid per-probe credit or page limit")
        self.max_credits = max_credits
        self.page_limit = page_limit
        self.consumed_credits = 0
        self._client = client or httpx.Client(timeout=15.0)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    @staticmethod
    def _number(item: dict, name: str, *, nonnegative: bool = False) -> float:
        try:
            val = float(item[name])
        except (TypeError, ValueError, KeyError) as exc:
            raise MarketstackProbeError("missing or invalid vendor field: " + name) from exc
        import math
        if not math.isfinite(val) or (val < 0 if nonnegative else val <= 0):
            raise MarketstackProbeError("invalid vendor numeric field: " + name)
        return val

    def fetch(self, symbol: str, date_from: date, date_to: date) -> tuple[list[EODBar], ProbeReceipt]:
        symbol = symbol.strip().upper()
        if not _SYMBOL_RE.fullmatch(symbol):
            raise ValueError("invalid vendor ticker")
        if date_from > date_to or date_to > date.today():
            raise ValueError("invalid or future history window")

        offset = 0
        rows: list[EODBar] = []
        hashes: list[str] = []
        seen: set[date] = set()
        rejected = []
        pages = 0
        while True:
            if self.consumed_credits >= self.max_credits:
                raise MarketstackProbeError("probe request-credit budget exhausted")
            # Reserve before network call: failed responses are not retried automatically.
            self.consumed_credits += 1
            params = {
                "access_key": self._key,
                "symbols": symbol,
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
                "sort": "ASC",
                "limit": self.page_limit,
                "offset": offset,
            }
            try:
                resp = self._client.get(_ENDPOINT, params=params)
                status = resp.status_code
                if status != 200:
                    raise MarketstackProbeError("MARKETSTACK_HTTP_" + str(status))
                raw = resp.content
                payload = resp.json()
            except (httpx.HTTPError, ValueError) as exc:
                # Do not include the request URL: it contains the access key.
                raise MarketstackProbeError("Marketstack EOD request or JSON failed") from None
            if not isinstance(payload, dict):
                raise MarketstackProbeError("MARKETSTACK_INVALID_ENVELOPE")
            if payload.get("error"):
                detail = payload["error"]
                code = detail.get("code") if isinstance(detail,dict) else "UNKNOWN"
                if not isinstance(code,(str,int)) or not re.fullmatch(r"[A-Za-z0-9_]{1,45}",str(code)):
                    code = "UNKNOWN"
                raise MarketstackProbeError("MARKETSTACK_API_ERROR_" + str(code))
            data = payload.get("data")
            meta = payload.get("pagination")
            if not isinstance(data, list) or not isinstance(meta, dict):
                raise MarketstackProbeError("Marketstack pagination/data envelope missing")
            try:
                total = int(meta["total"])
                reported_offset = int(meta["offset"])
                reported_count = int(meta["count"])
            except (KeyError, TypeError, ValueError) as exc:
                raise MarketstackProbeError("invalid Marketstack pagination") from exc
            if total < 0 or reported_offset != offset or reported_count != len(data):
                raise MarketstackProbeError("inconsistent Marketstack pagination")
            if not data and offset < total:
                raise MarketstackProbeError("incomplete Marketstack page")
            hashes.append(hashlib.sha256(raw).hexdigest())
            pages += 1
            for item in data:
                if not isinstance(item, dict) or str(item.get("symbol", "")).upper() != symbol:
                    raise MarketstackProbeError("vendor symbol mismatch")
                try:
                    session = date.fromisoformat(str(item["date"])[:10])
                except (KeyError, ValueError) as exc:
                    raise MarketstackProbeError("missing or invalid vendor session") from exc
                if session < date_from or session > date_to or session in seen:
                    raise MarketstackProbeError("duplicate or out-of-window vendor session")
                seen.add(session)
                try:
                    op = self._number(item, "open")
                    hi = self._number(item, "high")
                    lo = self._number(item, "low")
                    cl = self._number(item, "close")
                    vol = self._number(item, "volume", nonnegative=True)
                    adj = self._number(item, "adj_close")
                    if hi < max(op, cl, lo) or lo > min(op, cl, hi):
                        raise MarketstackProbeError("invalid vendor nominal OHLC geometry")
                    split = item.get("split_factor")
                    dividend = item.get("dividend")
                    if split is not None:
                        split = float(split)
                        if not math.isfinite(split) or split <= 0:
                            raise ValueError()
                    if dividend is not None:
                        dividend = float(dividend)
                        if not math.isfinite(dividend) or dividend < 0:
                            raise ValueError()
                    rows.append(EODBar(
                        symbol=symbol, session=session, open=op, high=hi,
                        low=lo, close=cl, volume=vol, vendor_adj_close=adj,
                        split_factor=split, dividend=dividend,
                    ))
                except (MarketstackProbeError,ValueError,TypeError) as exc:
                    reason = str(exc)[:90] if isinstance(exc,MarketstackProbeError) else "invalid split/dividend metadata"
                    rejected.append((session.isoformat(), reason))
            offset += len(data)
            if offset >= total:
                break
        if not rows:
            # Keep the concrete evidence failure when EVERY returned row
            # was rejected. Generic "no historical prices" otherwise hides
            # the actionable root cause and breaks fail-closed diagnosis.
            if rejected:
                raise MarketstackProbeError(rejected[0][1])
            raise MarketstackProbeError("no valid vendor historical prices found")
        rows.sort(key=lambda b: b.session)
        receipt = ProbeReceipt(
            symbol=symbol, date_from=date_from, date_to=date_to,
            retrieved_pages=pages, consumed_symbol_credits=pages,
            response_sha256=tuple(hashes),
            first_session=rows[0].session, last_session=rows[-1].session,
            observed_sessions=len(rows),
            rejected_sessions=tuple(date for date,_ in rejected),
            rejected_reasons=tuple(rejected),
        )
        return rows, receipt


def receipt_json(receipt: ProbeReceipt) -> str:
    """Produce a non-secret review artifact; never call it a QA certificate."""
    from dataclasses import asdict
    return json.dumps(asdict(receipt), default=str, sort_keys=True, indent=2)
