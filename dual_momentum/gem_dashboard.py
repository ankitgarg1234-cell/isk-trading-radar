"""GEM V1 read-only dashboard projection.

This module never imports the existing DM ledger, runs migrations, constructs a
simulated trade, or authorizes orders. A separate verified writer can publish
a bounded projection to GEM_STATUS_SNAPSHOT_PATH. Nothing is seeded here.
"""
from __future__ import annotations

import json
import os
import math
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="dual_momentum/templates")
FROZEN_REF = "d59b93d3d9a87d582045b4ae71ff9a6f696a48be"
MAX_SNAPSHOT_BYTES = 256_000
SOURCE_NAMES = (
    ("membership", "S&P 500 effective-dated membership", "Primary effective/announcement dates and stable security IDs"),
    ("prices", "Daily OHLCV and next-open observations", "Completed NYSE bars, full-universe coverage and independent action checks"),
    ("sec", "Original SEC 10-Q fundamentals", "Accession, value, context and publication-time receipts"),
    ("actions", "Corporate actions and distributions", "Splits, spinoffs, delisting consideration and dividend payable dates"),
    ("calendar", "NYSE session calendar", "Early closes, holidays and completed-session cutoffs"),
    ("benchmark", "SPY total-return benchmark", "Synchronized, source-audited returns"),
)


def _iso_datetime(value):
    if not isinstance(value, str):
        return None
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return d.astimezone(timezone.utc) if d.tzinfo else None
    except (ValueError, OverflowError):
        return None


def _snapshot():
    """Read a separately produced projection; never create or modify a DB/file."""
    filename = os.getenv("GEM_STATUS_SNAPSHOT_PATH", "").strip()
    if not filename:
        return None, "Not connected to a GEM-only read projection"
    try:
        p = Path(filename)
        if not p.is_file() or p.stat().st_size > MAX_SNAPSHOT_BYTES:
            return None, "GEM projection missing or exceeds the read limit"
        with p.open("rb") as fh:
            raw = fh.read(MAX_SNAPSHOT_BYTES + 1)
        if len(raw) > MAX_SNAPSHOT_BYTES:
            return None, "GEM projection exceeds the read limit"
        item = json.loads(raw)
        if not isinstance(item, dict) or item.get("schema") != "gem-dashboard-v1":
            return None, "GEM projection schema is invalid"
        if item.get("frozen_ref") != FROZEN_REF or item.get("environment") not in {"shadow", "paper"}:
            return None, "GEM projection does not match the frozen strategy"
        observed = _iso_datetime(item.get("observed_at"))
        if observed is None or observed > datetime.now(timezone.utc):
            return None, "GEM observation timestamp is invalid"
        if (datetime.now(timezone.utc) - observed).total_seconds() > 72 * 3600:
            return None, "GEM projection is stale (>72h); suppressing portfolio values"
        return item, None
    except (OSError, ValueError, TypeError):
        return None, "GEM projection could not be read or validated"



def oct1_retrospective_reference():
    """Read an explicitly retrospective frozen evidence artifact; never place orders.

    This is not the GEM forward paper account or its source of trading authority.
    Historical vendor prices were retrieved after the Oct 1 model entry.
    """
    try:
        path = Path(__file__).with_name("gem_oct1_reference.json")
        if not path.is_file() or path.stat().st_size > 16000:
            return None
        ref = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(ref, dict)
                or ref.get("schema") != "gem-retrospective-reference-v1"
                or ref.get("classification") != "RETROSPECTIVE_NOT_FORWARD_NOT_CERTIFIED"
                or ref.get("strategy_commit") != FROZEN_REF
                or ref.get("signal_date") != "2026-09-30"
                or ref.get("simulated_open") != "2026-10-01"
                or ref.get("marked_through") != "2026-10-09"
                or ref.get("starting_cash_usd") != 10000
                or ref.get("cost_bps_per_side") != 20
                or ref.get("selected") != ["P", "MPC", "PLTR", "HPE", "VLO"]):
            return None
        orders = ref.get("orders")
        daily = ref.get("daily_nav")
        if not isinstance(orders, list) or len(orders) != 5 or not isinstance(daily, list) or len(daily) != 7:
            return None
        if any(not isinstance(order, dict) or order.get("actual_fill") is not False
               or order.get("side") != "HYPOTHETICAL_BUY" or order.get("quantity", 0) <= 0
               or order.get("ticker") != expected
               for order, expected in zip(orders, ref["selected"])):
            return None
        if (any(row.get("date") not in {"2026-10-01","2026-10-02","2026-10-05","2026-10-06","2026-10-07","2026-10-08","2026-10-09"}
                for row in daily) or
                [row["date"] for row in daily] != sorted(set(row["date"] for row in daily))):
            return None
        # Independently reconcile the entire seven-session archived NAV path
        # against the bundled source closes. Any changed/incomplete fixture
        # blocks the display instead of silently showing a plausible P&L.
        closes_by_date = ref.get("closing_prices_by_date")
        benchmark = ref.get("benchmark")
        if not isinstance(closes_by_date, dict) or not isinstance(benchmark, dict):
            return None
        if set(closes_by_date) != {row["date"] for row in daily}:
            return None
        expected_cash = 10000.0
        shares = {}
        for order in orders:
            qty = order["quantity"]
            opening_price = order.get("opening_price")
            gross = order.get("gross")
            modeled_fee = order.get("cost_20bps")
            if (type(qty) is not int or type(opening_price) not in (int, float)
                    or type(gross) not in (int, float)
                    or type(modeled_fee) not in (int, float)
                    or not all(math.isfinite(float(v)) and v >= 0
                               for v in (opening_price, gross, modeled_fee))
                    or abs(gross - qty * opening_price) > .01
                    or abs(modeled_fee - gross * 0.002) > .01):
                return None
            shares[order["ticker"]] = qty
            expected_cash -= gross + modeled_fee
        if abs(expected_cash - ref.get("ending_cash_usd", float("nan"))) > .01:
            return None
        spy_qty = benchmark.get("shares")
        spy_open = benchmark.get("opening_price")
        spy_cash = benchmark.get("cash_usd")
        if (type(spy_qty) is not int or spy_qty <= 0
                or type(spy_open) not in (int, float) or spy_open <= 0
                or type(spy_cash) not in (int, float)
                or abs(spy_cash + spy_qty * spy_open * 1.002 - 10000) > .01):
            return None
        for row in daily:
            marks = closes_by_date[row["date"]]
            if set(marks) != set(shares) | {"SPY"}:
                return None
            if any(type(x) not in (int, float) or not math.isfinite(x) or x <= 0
                   for x in marks.values()):
                return None
            nav = expected_cash + sum(qty * marks[sym] for sym, qty in shares.items())
            spy_nav = spy_cash + spy_qty * marks["SPY"]
            if (abs(nav - row.get("gem_nav", float("nan"))) > .01
                    or abs(spy_nav - row.get("spy_nav", float("nan"))) > .01
                    or abs((nav / 10000 - 1) * 100 - row.get("gem_return_pct", float("nan"))) > .0001
                    or abs((spy_nav / 10000 - 1) * 100 - row.get("spy_return_pct", float("nan"))) > .0001):
                return None
        # A historical reference must not be allowed to masquerade as a
        # contemporaneously recorded fill or a real prospective mark.
        latest = daily[-1]
        if latest.get("date") != "2026-10-09":
            return None
        return {
            "classification": "BACKFILLED_UNCERTIFIED",
            "as_of": latest["date"],
            "signal_date": ref["signal_date"],
            "modeled_buy_date": ref["simulated_open"],
            "nav_usd": latest["gem_nav"],
            "return_pct": latest["gem_return_pct"],
            "spy_nav_usd": latest["spy_nav"],
            "spy_return_pct": latest["spy_return_pct"],
            "cash_usd": ref["ending_cash_usd"],
            "orders": orders,
            "daily_nav": daily,
            "source_retrieved": "2026-10-11",
            "qa": "UNCERTIFIED — full eligible universe not reconciled",
            "issues": "20 historical competitor cases open for Sep 30, including PSX above observed cutoff and FDXF/HONA with unknown momentum",
            "fills_recorded": 0,
        }
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return None


def gem_status():
    snapshot, error = _snapshot()
    raw_sources = (snapshot or {}).get("sources") or {}
    # Source claims are shown as reports, NOT as authorization. Missing stays unknown.
    sources = []
    for key, label, requirement in SOURCE_NAMES:
        entry = raw_sources.get(key) if isinstance(raw_sources, dict) else None
        if not isinstance(entry, dict):
            entry = {}
        reported = entry.get("status")
        state = reported if reported in {"VERIFIED", "BLOCKED", "MISSING", "STALE"} else "UNKNOWN"
        sources.append({
            "key": key, "name": label, "requirement": requirement,
            "status": state,
            "as_of": str(entry.get("as_of") or "")[:32],
        })
    # No initial $10,000 account is fabricated. Expose values only from a
    # separately reconciled and anchored paper projection.
    ledger = (snapshot or {}).get("ledger") or {}
    certified = (
        snapshot is not None
        and isinstance(ledger, dict)
        and ledger.get("reconciled") is True
        and isinstance(ledger.get("trusted_head"), str)
        and len(ledger["trusted_head"]) == 64
        and snapshot.get("environment") == "paper"
    )
    portfolio = ledger.get("portfolio") if certified else None
    if not isinstance(portfolio, dict):
        portfolio = None
    return {
        "title": "GEM V1 Forward Paper Trial",
        "strategy_ref": FROZEN_REF[:7],
        "strategy_full_ref": FROZEN_REF,
        "mode": (snapshot or {}).get("environment", "not_started"),
        "execution": "DISABLED",
        "qa": "BLOCKED — independent certification and explicit release required",
        "as_of": (snapshot or {}).get("observed_at"),
        "projection_error": error,
        "starting_capital_planned": 10000,
        "portfolio": portfolio,
        "sources": sources,
        "historical_open_cases": 943,
        "historical_case_as_of": "2026-10-11",
        "read_model_connected": snapshot is not None,
        "oct1_backfill": oct1_retrospective_reference(),
        "next_signal": (snapshot or {}).get("next_signal"),
        "notes": "Read-only. An external projection cannot grant trading authority.",
    }


@router.get("/gem-trial", response_class=HTMLResponse)
def gem_trial_page(request: Request):
    return templates.TemplateResponse(request, "gem_trial.html", {"gem": gem_status()})


@router.get("/api/gem-trial/status")
def gem_trial_status_api():
    return gem_status()


@router.get("/api/gem-trial/backfill-reference")
def gem_oct1_backfill_reference_api():
    return oct1_retrospective_reference() or {"status": "UNAVAILABLE", "classification": "RETROSPECTIVE_ONLY"}
