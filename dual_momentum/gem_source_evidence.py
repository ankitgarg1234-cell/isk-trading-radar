"""GEM source-readiness evidence: availability != certification.

The bundled probes are dated observations from read-only source checks, not
full-universe quality certificates. Neither this module nor a dashboard source
status can authorize a trading signal or paper order. No production DB imports.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

FROZEN_COMMIT = "d59b93d3d9a87d582045b4ae71ff9a6f696a48be"
SOURCE_IDS = ("membership", "prices", "sec", "actions", "calendar", "benchmark")
DISPLAY_STATES = frozenset({"UNKNOWN", "MISSING", "PARTIAL", "BLOCKED", "STALE", "PENDING_QA", "VERIFIED"})
MAX_AGE_DAYS = {"membership": 7, "prices": 2, "sec": 7, "actions": 3, "calendar": 21, "benchmark": 2}
REQUIREMENTS = {
    "membership": "Effective-dated primary S&P files; complete current share classes, CIK/security identity and removals.",
    "prices": "All members, >=126 prior completed daily OHLCV bars; nominal units, dollar volume, r63 and verified next open.",
    "sec": "Every possible top-five competitor accounted for with original 10-Q facts, exact quarters and prior-day publication proof.",
    "actions": "Split/spinoff, delisting proceeds and dividend ex/pay dates; full member action coverage and reconciled units.",
    "calendar": "Official NYSE session status, holiday/early-close schedule, last completed close and correct next open.",
    "benchmark": "Complete-date SPY bars plus dividends/actions, synchronized total-return accounting and independent reconciliation.",
}


def _safe_date(raw):
    if not isinstance(raw, str):
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _limited_text(value, length=220):
    if not isinstance(value, str):
        return ""
    return value[:length]


def inspect_probes(bundle: dict, *, today: date | None = None) -> dict:
    """Accept dated source observations; NEVER infer VERIFY from probe reachability.

    A fully certified source requires a separate, cryptographically checked QA
    certificate, not included in this probe schema. Even a spoofed 'VERIFIED'
    field in a JSON fixture is downgraded to PENDING_QA or BLOCKED.
    """
    now = today or datetime.now(timezone.utc).date()
    if not isinstance(bundle, dict) or bundle.get("schema") != "gem-source-probes-v1":
        raise ValueError("Unrecognized GEM source evidence schema")
    if bundle.get("frozen_commit") != FROZEN_COMMIT:
        raise ValueError("GEM source evidence strategy mismatch")
    checked = _safe_date(bundle.get("checked_on"))
    if checked is None or checked > now:
        raise ValueError("Missing or future source observation date")
    observations = bundle.get("sources")
    if not isinstance(observations, list):
        raise ValueError("Source observations must be a list")
    by_key = {}
    for entry in observations:
        if not isinstance(entry, dict) or entry.get("key") not in SOURCE_IDS:
            raise ValueError("Unrecognized source observation")
        key = entry["key"]
        if key in by_key:
            raise ValueError("Duplicate source observation: " + key)
        by_key[key] = entry
    output = {}
    for key in SOURCE_IDS:
        row = by_key.get(key, {})
        raw_state = row.get("status")
        if raw_state not in {"PARTIAL", "MISSING", "BLOCKED", "PENDING_QA", "VERIFIED"}:
            raw_state = "UNKNOWN"
        state = raw_state
        # A probe doesn't authenticate an independent reviewer or prove full
        # universe completeness. A claimed VERIFIED can NEVER become green.
        if state == "VERIFIED":
            state = "PENDING_QA"
        if (now - checked).days > MAX_AGE_DAYS[key] and state not in {"MISSING", "BLOCKED"}:
            state = "STALE"
        missing = row.get("missing")
        if not isinstance(missing, list) or any(not isinstance(x, str) for x in missing):
            missing = ["Independent source verification not provided"]
        output[key] = {
            "key": key, "status": state,
            "as_of": checked.isoformat(), "evidence": _limited_text(row.get("evidence")),
            "missing": [_limited_text(item) for item in missing[:6]],
            "checked_scope": _limited_text(row.get("checked_scope")),
            "required": REQUIREMENTS[key],
            "trade_eligible": False,
            "evidence_level": "DIAGNOSTIC_PROBE_NOT_CERTIFICATION",
        }
    return output


def probe_status(*, today: date | None = None) -> dict:
    """Read a small, committed evidence index; no vendor calls on web requests."""
    filename = Path(__file__).with_name("gem_source_probe_2026_10_12.json")
    if not filename.is_file() or filename.stat().st_size > 20_000:
        return _missing_all()
    try:
        bundle = json.loads(filename.read_text(encoding="utf-8"))
        return inspect_probes(bundle, today=today)
    except (OSError, ValueError, TypeError):
        return _missing_all()


def _missing_all():
    return {key: {
        "key": key, "status": "UNKNOWN", "as_of": "",
        "evidence": "", "missing": ["No trusted source evidence read"],
        "checked_scope": "", "required": REQUIREMENTS[key],
        "trade_eligible": False, "evidence_level": "NONE"
    } for key in SOURCE_IDS}


def merge_source_status(*, probe: dict, observed: dict | None) -> dict:
    """Overlay GEM-only DB status, without accepting raw unverified PASS claims.

    Only a separate future signature-verified authorization service can mark
    individual sources VERIFIED. The dashboard intentionally cannot do that.
    """
    result = dict(probe)
    for key in SOURCE_IDS:
        row = observed.get(key) if isinstance(observed, dict) else None
        if not isinstance(row, dict):
            continue
        state = row.get("status")
        # DB writer-provided strings are not an authenticated QA certificate.
        if state == "VERIFIED":
            state = "PENDING_QA"
        if state not in DISPLAY_STATES:
            state = "UNKNOWN"
        observed_at = _limited_text(row.get("as_of"))
        observed_day = _safe_date(observed_at[:10])
        if observed_day is None or observed_day > datetime.now(timezone.utc).date():
            state = "UNKNOWN"
        elif (datetime.now(timezone.utc).date() - observed_day).days > MAX_AGE_DAYS[key]:
            state = "STALE"
        existing = result[key]
        updated = dict(existing)
        updated["status"] = state
        updated["as_of"] = observed_at or existing["as_of"]
        updated["evidence"] = _limited_text(row.get("evidence")) or "GEM-only DB diagnostic; independent QA still required"
        updated["checked_scope"] = _limited_text(row.get("checked_scope")) or existing["checked_scope"]
        missing = row.get("missing")
        updated["missing"] = ([_limited_text(item) for item in missing[:6] if isinstance(item, str)]
                              if isinstance(missing, list)
                              else ["Independent source QA certificate absent"])
        updated["trade_eligible"] = False
        result[key] = updated
    return result
