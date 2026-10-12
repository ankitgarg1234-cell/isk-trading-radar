"""Offline independent GEM input-coverage and rank QA.

Data are caller-supplied, immutable as-of snapshots. The function refuses to
silently exclude missing competitors. It NEVER approves simulated purchases:
source authority, complete originals/identity and human QA signatures are
separate release gates. Code intentionally does not import any deployed DM
trading code, contact a broker, or write a database.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from typing import Any
import json
import math


class RankingHold(ValueError):
    pass


@dataclass(frozen=True)
class Candidate:
    ticker: str
    security_id: str
    r63: float
    revenue_growth: float
    net_income_current: float
    earnings_improvement: bool
    margin_delta_pp: float
    eligible: bool
    reason: str


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise RankingHold("Invalid/missing ISO trading date") from exc


def _finite(value: Any, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise RankingHold(f"Nonfinite/missing {what}")
    return float(value)


def _filing_quarter(row: dict, signal_day: date, *, label: str) -> tuple[float, date, date]:
    """Check six source-fact uses without assuming aggregation is primary proof."""
    if not isinstance(row, dict):
        raise RankingHold("No original SEC quarter evidence for " + label)
    if row.get("form") not in ("10-Q", "10-Q/A"):
        raise RankingHold("Non-10Q filing for " + label)
    if not isinstance(row.get("accession"), str) or not row["accession"]:
        raise RankingHold("Missing SEC accession for " + label)
    raw_hash = row.get("source_sha256")
    if not isinstance(raw_hash, str) or len(raw_hash) != 64 or any(c not in "0123456789abcdef" for c in raw_hash.lower()):
        raise RankingHold("Missing raw source fingerprint for " + label)
    if row.get("unit") != "USD" or not row.get("concept") or row.get("source_context_verified") is not True:
        raise RankingHold("Quarter unit/concept/context not independently mapped for " + label)
    start = _date(row.get("start"))
    end = _date(row.get("end"))
    duration = (end - start).days
    if not 60 <= duration <= 125:
        raise RankingHold("Non-quarter / YTD duration for " + label)
    filed = _date(row.get("filed"))
    if filed >= signal_day:
        raise RankingHold("Same/future-day filing for " + label)
    try:
        acceptance = datetime.fromisoformat(row["accepted_at"].replace("Z", "+00:00"))
    except (KeyError, ValueError, AttributeError) as exc:
        raise RankingHold("Missing SEC acceptance timestamp for " + label) from exc
    if acceptance.tzinfo is None or acceptance.astimezone(timezone.utc).date() >= signal_day:
        raise RankingHold("Late/ambiguous SEC acceptance timestamp for " + label)
    if row.get("first_public_observed_at"):
        try:
            first = datetime.fromisoformat(row["first_public_observed_at"].replace("Z", "+00:00"))
        except (TypeError, ValueError) as exc:
            raise RankingHold("Malformed first public observation") from exc
        if first.tzinfo is None or first.astimezone(timezone.utc).date() >= signal_day:
            raise RankingHold("Input not first-observed by prior-day cutoff")
    if row.get("publication_reviewed") is not True:
        raise RankingHold("SEC acceptance is not independently reviewed availability evidence")
    return _finite(row.get("value"), label), end, filed


def _expected_completed_sessions(snapshot: dict, signal_day: date) -> list[date]:
    """Require an explicit independently reviewed session calendar.

    A boolean calendar-verified flag alone cannot prove the 127 trading
    observations needed for momentum and dollar-volume calculations.
    """
    raw = snapshot.get("completed_sessions")
    if not isinstance(raw, list) or len(raw) < 127:
        raise RankingHold("Missing complete official session-date manifest")
    sessions = [_date(session) for session in raw]
    if sessions != sorted(set(sessions)) or sessions[-1] != signal_day:
        raise RankingHold("Duplicate, stale or out-of-order official session manifest")
    return sessions[-127:]


def _prices(row: dict, signal_day: date, expected_sessions: list[date]) -> tuple[float, float, float]:
    prices = row.get("bars")
    if not isinstance(prices, list) or len(prices) < 127:
        raise RankingHold("Missing 126 previous session prices")
    if row.get("frozen_vendor_parity_reviewed") is not True:
        raise RankingHold("Frozen adjusted-close/nominal-close semantics unreviewed")
    seen_dates = []
    close = []
    volume = []
    for item in prices:
        if not isinstance(item, dict):
            raise RankingHold("Malformed price bar")
        day = _date(item.get("session"))
        seen_dates.append(day)
        c = _finite(item.get("frozen_close"), "vendor close")
        o = _finite(item.get("nominal_open"), "nominal open")
        h = _finite(item.get("nominal_high"), "nominal high")
        lo = _finite(item.get("nominal_low"), "nominal low")
        v = _finite(item.get("volume"), "volume")
        if min(c, o, h, lo, v) <= 0 or lo > min(o, h) or h < max(o, lo):
            raise RankingHold("Invalid positive daily OHLCV values")
        close.append(c)
        volume.append(v)
    if (seen_dates != sorted(set(seen_dates)) or seen_dates[-1] != signal_day
            or any(d > signal_day for d in seen_dates)):
        raise RankingHold("Stale/forward/duplicate price observation")
    if seen_dates[-127:] != expected_sessions:
        raise RankingHold("Price bars do not cover the 127 certified completed exchange sessions")
    raw_close = _finite(row.get("nominal_close"), "nominal close")
    if raw_close <= 0:
        raise RankingHold("Invalid nominal closing unit")
    adv20 = sum(close[-20+i] * volume[-20+i] for i in range(20)) / 20
    r63 = close[-1] / close[-64] - 1
    return raw_close, adv20, r63


def audit_snapshot(snapshot: dict, *, fixture_min_members: int | None = None) -> dict:
    """Recompute GEM features for EVERY effective S&P member or HOLD.

    Production minimum is 480 security lines; tests may supply fixture_min_members.
    Source verification booleans here describe a *proposed* reviewed manifest.
    They are not cryptographic attestations or user approval.
    """
    if not isinstance(snapshot, dict):
        raise RankingHold("No input snapshot")
    if snapshot.get("schema") != "gem-source-qa-input-v1":
        raise RankingHold("Wrong source schema")
    if snapshot.get("strategy_commit") != "d59b93d3d9a87d582045b4ae71ff9a6f696a48be":
        raise RankingHold("Frozen GEM strategy drift")
    signal = _date(snapshot.get("signal_session"))
    if signal.month != (signal + timedelta(days=1)).month and snapshot.get("official_month_end") is not True:
        raise RankingHold("Signal month-end not officially established")
    if snapshot.get("official_month_end") is not True:
        raise RankingHold("Non-month-end or unverified exchange session")
    universe = snapshot.get("universe")
    if not isinstance(universe, list):
        raise RankingHold("Missing complete member list")
    min_members = 480 if fixture_min_members is None else fixture_min_members
    if len(universe) < min_members or len(universe) > 600:
        raise RankingHold("Missing or implausible full S&P constituent coverage")
    ids = [m.get("security_id") for m in universe if isinstance(m, dict)]
    symbols = [m.get("ticker") for m in universe if isinstance(m, dict)]
    if (len(ids) != len(universe) or len(set(ids)) != len(ids)
            or len(set(symbols)) != len(symbols)
            or any(not isinstance(s, str) or not s for s in ids + symbols)):
        raise RankingHold("Incomplete, ambiguous or duplicate S&P security identifiers")
    if snapshot.get("primary_universe_bytes_hash_verified") is not True:
        raise RankingHold("No primary effective-dated S&P identity/membership evidence")
    if snapshot.get("corporate_action_coverage_verified") is not True:
        raise RankingHold("Unresolved market split/spinoff/merger/dividend actions")
    if snapshot.get("spy_benchmark_coverage_verified") is not True:
        raise RankingHold("No independently reconciled SPY total-return benchmark")
    if snapshot.get("complete_exchange_calendar_verified") is not True:
        raise RankingHold("Exchange calendar/session status uncertified")
    rows = snapshot.get("candidates")
    if not isinstance(rows, list) or len(rows) != len(universe):
        raise RankingHold("Missing one or more competing S&P security rows")
    lookup = {r.get("security_id"): r for r in rows if isinstance(r, dict)}
    if len(lookup) != len(rows) or set(lookup) != set(ids):
        raise RankingHold("Missing or duplicated member candidates")
    expected_sessions = _expected_completed_sessions(snapshot, signal)
    result = []
    for member in sorted(universe, key=lambda m: m["ticker"]):
        row = lookup[member["security_id"]]
        if row.get("ticker") != member["ticker"]:
            raise RankingHold("Ticker/security identity mismatch")
        raw_close, adv, r63 = _prices(row, signal, expected_sessions)
        if len(row.get("quarterly_facts", {})) != 6:
            raise RankingHold("Missing some SEC quarter facts for " + member["ticker"])
        fs = row["quarterly_facts"]
        required = {"revenue_now", "revenue_prior", "income_now", "income_prior", "operating_now", "operating_prior"}
        if set(fs) != required:
            raise RankingHold("Unknown/missing revenue-income-margin evidence for " + member["ticker"])
        facts = {name: _filing_quarter(fs[name], signal, label=member["ticker"] + "." + name)
                 for name in sorted(required)}
        rev_now, end_now, filed_rev = facts["revenue_now"]
        rev_prev, end_prev, _ = facts["revenue_prior"]
        income_now, income_end, filed_income = facts["income_now"]
        income_prev, income_prev_end, _ = facts["income_prior"]
        operating_now, operating_end, _ = facts["operating_now"]
        operating_prev, operating_prev_end, _ = facts["operating_prior"]
        if (rev_now <= 0 or rev_prev <= 0 or (end_now - end_prev).days not in range(310, 421)
                or end_now != income_end or end_now != operating_end
                or end_prev != income_prev_end or end_prev != operating_prev_end):
            raise RankingHold("Quarter alignment/denominator failure for " + member["ticker"])
        cutoff = signal - timedelta(days=1)
        if (cutoff - filed_rev).days > 210 or (cutoff - filed_income).days > 210:
            raise RankingHold("SEC revenue/income freshness not established for " + member["ticker"])
        rev_growth = rev_now / rev_prev - 1
        earnings = income_now > 0 and (income_prev <= 0 or income_now / income_prev - 1 > .2)
        margin = 100 * (operating_now / rev_now - operating_prev / rev_prev)
        eligible = (
            raw_close >= 5 and adv >= 10_000_000 and r63 > 0
            and rev_growth > .2 and earnings and margin > 3
        )
        result.append(Candidate(
            ticker=member["ticker"], security_id=member["security_id"],
            r63=r63, revenue_growth=rev_growth,
            net_income_current=income_now,
            earnings_improvement=earnings, margin_delta_pp=margin,
            eligible=eligible, reason="PASS" if eligible else "FAILED_FROZEN_GATE",
        ))
    qualified = sorted((c for c in result if c.eligible), key=lambda c: (-c.r63, c.ticker))
    payload = {
        "schema": "gem-ranking-qa-proposal-v1",
        "signal_session": signal.isoformat(),
        "member_count": len(universe),
        "evaluated_count": len(result),
        "candidate_count": len(qualified),
        "selected": [c.ticker for c in qualified[:5]],
        "ranked_eligible": [asdict(c) for c in qualified],
        "state": "AWAITING_INDEPENDENT_SIGNED_SOURCE_QA",
        "paper_execution_authorized": False,
    }
    payload["decision_hash"] = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return payload
