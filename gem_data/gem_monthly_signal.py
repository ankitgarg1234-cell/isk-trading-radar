"""GEMv1 month-end selection from a *complete*, source-identified feature panel.

This is an implementation of the archived growth_margin5 gate, not a
certification that upstream vendor/SEC data are correct. Missing competitor
evidence causes an explicit global HOLD, not silent exclusion.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from hashlib import sha256
import json
import math

FROZEN = "d59b93d3d9a87d582045b4ae71ff9a6f696a48be"


class MonthlySignalHold(ValueError):
    pass


def _date(x):
    try:
        if not isinstance(x, str):
            raise ValueError("missing date")
        return date.fromisoformat(x)
    except ValueError as exc:
        raise MonthlySignalHold("Invalid date") from exc


def _n(x, label):
    if isinstance(x, bool) or not isinstance(x, (float, int)) or not math.isfinite(x):
        raise MonthlySignalHold("Invalid " + label)
    return float(x)


def _stable_hash(x):
    return sha256(json.dumps(x, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def select_monthly(snapshot, *, fixture_min_members=None):
    """Return a QA-held ranked report until ALL inputs and reviews are sound.

    Candidate feature values MUST be independently source-derived upstream.
    Retrospective archived selection does NOT add an r63>0 filter.
    """
    if not isinstance(snapshot, dict) or snapshot.get("schema") != "gem-monthly-features-v1":
        raise MonthlySignalHold("Invalid GEM monthly feature bundle")
    if snapshot.get("frozen_commit") != FROZEN:
        raise MonthlySignalHold("Frozen strategy version mismatch")
    signal = _date(snapshot.get("signal_session"))
    nxt = _date(snapshot.get("next_session"))
    if nxt <= signal or nxt.strftime("%Y-%m") == signal.strftime("%Y-%m"):
        raise MonthlySignalHold("Official month-end/next-open calendar not established")
    if snapshot.get("calendar_verified") is not True:
        raise MonthlySignalHold("Month-end not independently verified")
    members = snapshot.get("universe")
    rows = snapshot.get("features")
    min_members = 480 if fixture_min_members is None else fixture_min_members
    if (not isinstance(members, list) or not isinstance(rows, list)
            or not min_members <= len(members) <= 600):
        raise MonthlySignalHold("Incomplete S&P 500 membership")
    identity = {}
    for member in members:
        if not isinstance(member, dict):
            raise MonthlySignalHold("Malformed membership")
        sec = member.get("security_id")
        ticker = member.get("ticker")
        if not isinstance(sec, str) or not sec or not isinstance(ticker, str) or not ticker:
            raise MonthlySignalHold("Missing stable security identity")
        if sec in identity or ticker in identity.values():
            raise MonthlySignalHold("Duplicate security or ticker")
        identity[sec] = ticker
    if len(rows) != len(members):
        raise MonthlySignalHold("One or more competitors missing")
    features = {}
    for row in rows:
        if not isinstance(row, dict) or row.get("security_id") not in identity:
            raise MonthlySignalHold("Unknown/duplicate security in features")
        key = row["security_id"]
        if key in features or row.get("ticker") != identity[key]:
            raise MonthlySignalHold("Duplicate or mismatched security")
        features[key] = row
    if set(features) != set(identity):
        raise MonthlySignalHold("Incomplete ranking universe")
    scored = []
    blockers = []
    for sec in sorted(identity, key=lambda v: identity[v]):
        row = features[sec]
        ticker = identity[sec]
        problem = []
        try:
            r63 = _n(row.get("r63"), ticker + ".r63")
            nominal = _n(row.get("nominal_close"), ticker + ".nominal_close")
            adv20 = _n(row.get("adv20"), ticker + ".adv20")
            rev = _n(row.get("revenue_yoy"), ticker + ".revenue_yoy")
            margin = _n(row.get("margin_delta_pp"), ticker + ".margin_delta_pp")
            income_now = _n(row.get("net_income_now"), ticker + ".net_income_now")
            income_before = _n(row.get("net_income_prior"), ticker + ".net_income_prior")
            if type(row.get("earnings_improvement")) is not bool:
                raise MonthlySignalHold("Missing independently derived earnings gate")
        except MonthlySignalHold:
            problem.append("MISSING_NUMERIC_FEATURE_OR_EARNINGS_GATE")
            r63 = nominal = adv20 = rev = margin = income_now = income_before = None
        if row.get("price_last_session") != signal.isoformat() or row.get("price_sessions", 0) < 127:
            problem.append("PRICE_STALE_OR_INCOMPLETE")
        if row.get("price_basis") != "FROZEN_VERIFIED":
            problem.append("PRICE_ADJUSTMENT_PARITY_UNVERIFIED")
        if row.get("financial_source") != "SEC_ORIGINAL_QA_REVIEWED":
            problem.append("SEC_PROVENANCE_UNVERIFIED")
        try:
            financial_cutoff = datetime.fromisoformat(row.get("latest_accepted_at", "").replace("Z", "+00:00"))
            if financial_cutoff.tzinfo is None or financial_cutoff.astimezone(timezone.utc).date() >= signal:
                problem.append("FINANCIAL_FILING_AFTER_CUTOFF")
        except (ValueError, AttributeError):
            problem.append("FINANCIAL_ACCEPTANCE_MISSING")
        if row.get("security_identity_reviewed") is not True:
            problem.append("IDENTITY_EVIDENCE_MISSING")
        if problem:
            blockers.append({"ticker": ticker, "reasons": problem})
        # Original archived engine: G = rev>0.2; E = earnings_improvement;
        # margin_delta_pp>3. Pre-price and ADV20 gates are panel construction.
        qualifying = (not problem and nominal >= 5 and adv20 >= 10_000_000
                      and rev > .2 and income_now > 0
                      and row["earnings_improvement"] is True and margin > 3)
        scored.append({
            "ticker": ticker, "security_id": sec, "r63": r63,
            "eligible": qualifying,
            "positive_r63": (r63 is not None and r63 > 0),
            "reason": "MISSING_COMPETITOR_EVIDENCE" if problem else
                      "PASS" if qualifying else "FAILED_FROZEN_GATE",
        })
    # A complete panel is not sufficient: primary identity/action provenance
    # and independent source QA must be separately supplied/reviewed.
    for field in ("membership_reviewed", "actions_reviewed", "benchmark_reviewed",
                  "source_manifest_reviewed"):
        if snapshot.get(field) is not True:
            blockers.append({"scope": field, "reasons": ["INDEPENDENT_QA_PENDING"]})
    eligible = sorted((r for r in scored if r["eligible"]),
                      key=lambda r: (-r["r63"], r["ticker"]))
    result = {
        "schema": "gem-monthly-ranked-v1",
        "signal_session": signal.isoformat(), "next_session": nxt.isoformat(),
        "strategy_commit": FROZEN,
        "member_count": len(members), "evaluated_count": len(scored),
        "qualified_count": len(eligible),
        "selected": [r["ticker"] for r in eligible[:5]] if not blockers else [],
        "provisional_top5": [r["ticker"] for r in eligible[:5]],
        "positive_momentum_disagreements": [r["ticker"] for r in eligible if not r["positive_r63"]],
        "candidate_audit": scored, "blockers": blockers,
        "data_status": "REVIEWED_COMPLETE" if not blockers else "HOLD",
        "automatic_execution": False,
        "broker_orders_sent": 0,
        "frozen_gate_note": "No explicit positive-r63 requirement in archived simulator",
        "qa_scope": "INPUT_REVIEW_FLAGS_NOT_EXTERNAL_CERTIFICATION",
    }
    result["report_sha256"] = _stable_hash(result)
    return result
