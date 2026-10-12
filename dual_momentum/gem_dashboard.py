"""GEM V1 read-only dashboard projection.

This module never imports the existing DM ledger, runs migrations, constructs a
simulated trade, or authorizes orders. A separate verified writer can publish
a bounded projection to GEM_STATUS_SNAPSHOT_PATH. Nothing is seeded here.
"""
from __future__ import annotations

import json
import os
import psycopg
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



def _neon_snapshot():
    """Query only the separate GEM database using its SELECT-only reader role.

    Neither this web process nor any render environment setting authorizes orders,
    creates tables, seeds accounts, migrates schemas or uses the DM DATABASE_URL.
    """
    url = os.getenv("GEM_READONLY_DATABASE_URL", "").strip()
    if not url:
        return None, "GEM isolated database read connection is not configured"
    try:
        with psycopg.connect(url, connect_timeout=4, options="-c statement_timeout=4000 -c default_transaction_read_only=on") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT experiment_id, frozen_commit, mode, planned_capital, "
                    "execution_enabled, receipt_count, signal_count FROM gem_status_v1 "
                    "WHERE experiment_id = %s",
                    ("gem-v1-forward-2026-10",),
                )
                record = cur.fetchone()
                if record is None or record[1] != FROZEN_REF or record[4] is not False:
                    return None, "GEM experiment missing, changed, or execution-enabled"
                cur.execute(
                    "SELECT DISTINCT ON (source_type) source_type, coverage_status, observed_at "
                    "FROM gem_source_receipt WHERE experiment_id=%s "
                    "ORDER BY source_type, collected_at DESC, receipt_id DESC",
                    ("gem-v1-forward-2026-10",),
                )
                receipts = cur.fetchall()
        return {
            "schema": "gem-dashboard-v1",
            "frozen_ref": FROZEN_REF,
            "environment": "shadow",
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "sources": {
                source_type: {"status": status, "as_of": asof.isoformat()}
                for source_type, status, asof in receipts
                if source_type in {entry[0] for entry in SOURCE_NAMES}
            },
            "counts": {"source_receipts": int(record[5]), "signals": int(record[6])},
            "ledger": None,
        }, None
    except (psycopg.Error, ValueError, TypeError, OSError):
        return None, "GEM isolated database read failed; no portfolio values shown"


def gem_status():
    snapshot, error = _neon_snapshot() if os.getenv("GEM_READONLY_DATABASE_URL") else _snapshot()
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
        "source_receipts": ((snapshot or {}).get("counts") or {}).get("source_receipts"),
        "shadow_signals": ((snapshot or {}).get("counts") or {}).get("signals"),
        "next_signal": (snapshot or {}).get("next_signal"),
        "notes": "Read-only. An external projection cannot grant trading authority.",
    }


@router.get("/gem-trial", response_class=HTMLResponse)
def gem_trial_page(request: Request):
    return templates.TemplateResponse(request, "gem_trial.html", {"gem": gem_status()})


@router.get("/api/gem-trial/status")
def gem_trial_status_api():
    return gem_status()
