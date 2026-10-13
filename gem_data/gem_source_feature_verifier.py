"""Independent numeric recomputation of GEMv1 price and SEC feature inputs.

The verification layer recalculates r63/ADV20 and the six quarterly financial
comparisons. It never trusts prefilled rankings or a vendor's adjusted label.
'Reviewed' booleans in caller data are NOT cryptographic certification.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import math

from gem_data.gem_monthly_signal import select_monthly, MonthlySignalHold, FROZEN


class SourceFeatureHold(ValueError):
    pass


def _n(x, name):
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        raise SourceFeatureHold("Invalid/missing " + name)
    return float(x)


def verify_price_features(price, *, signal_day, sessions):
    """Compute returns from 64 closes and liquidity from 20 trading sessions."""
    if not isinstance(price, dict) or price.get("adjustment_basis") != "FROZEN_VERIFIED":
        raise SourceFeatureHold("Adjusted-price semantics unreviewed")
    bars = price.get("bars")
    if not isinstance(bars, list) or len(bars) < 127:
        raise SourceFeatureHold("127 completed daily bars required")
    tail = bars[-127:]
    if [b.get("session") for b in tail] != sessions[-127:] or tail[-1]["session"] != signal_day:
        raise SourceFeatureHold("Price history missing calendar sessions")
    frozen = []
    volumes = []
    for bar in tail:
        if not isinstance(bar, dict):
            raise SourceFeatureHold("Malformed OHLCV row")
        closing = _n(bar.get("frozen_close"), "frozen close")
        raw = _n(bar.get("nominal_close"), "nominal close")
        volume = _n(bar.get("volume"), "volume")
        if closing <= 0 or raw <= 0 or volume < 0:
            raise SourceFeatureHold("Impossible price/volume")
        frozen.append(closing)
        volumes.append(volume)
    return {
        "r63": frozen[-1] / frozen[-64] - 1,
        "adv20": sum(p * v for p,v in zip(frozen[-20:], volumes[-20:])) / 20,
        "nominal_close": _n(tail[-1]["nominal_close"], "nominal close"),
        "price_last_session": signal_day, "price_sessions": len(tail),
        "price_basis": "FROZEN_VERIFIED",
    }


def _fact(row, *, signal_day, name):
    if not isinstance(row, dict):
        raise SourceFeatureHold("Missing SEC quarterly record: " + name)
    if not str(row.get("form") or "").startswith("10-Q") or row.get("unit") != "USD":
        raise SourceFeatureHold("Original 10-Q quarterly evidence required: " + name)
    if row.get("source_context_reviewed") is not True:
        raise SourceFeatureHold("SEC original context QA missing: " + name)
    if not isinstance(row.get("accession"), str) or not row["accession"]:
        raise SourceFeatureHold("Missing SEC accession: " + name)
    try:
        end = date.fromisoformat(row["period_end"])
        start = date.fromisoformat(row["period_start"])
        filed = date.fromisoformat(row["filed"])
        accepted = datetime.fromisoformat(row["accepted_at"].replace("Z", "+00:00"))
        if accepted.tzinfo is None or (end-start).days < 60 or (end-start).days > 125:
            raise ValueError("non-quarter or naive acceptance")
    except (KeyError, TypeError, ValueError) as exc:
        raise SourceFeatureHold("Invalid quarter duration/acceptance: " + name) from exc
    if filed >= date.fromisoformat(signal_day) or accepted.astimezone(timezone.utc).date() >= date.fromisoformat(signal_day):
        raise SourceFeatureHold("Late public filing: " + name)
    return _n(row.get("value"), "SEC dollar amount"), end, filed


def verify_financial_features(facts, *, signal_day):
    required = {"revenue_now", "revenue_prior", "income_now", "income_prior",
                "operating_now", "operating_prior"}
    if not isinstance(facts, dict) or set(facts) != required:
        raise SourceFeatureHold("Six aligned original-quarter SEC facts required")
    values = {key: _fact(facts[key], signal_day=signal_day, name=key)
              for key in sorted(required)}
    rev_now, now, filed_rev = values["revenue_now"]
    rev_prior, prior, _ = values["revenue_prior"]
    income_now, inc_now, filed_inc = values["income_now"]
    income_prior, inc_prior, _ = values["income_prior"]
    op_now, op_end, _ = values["operating_now"]
    op_prior, op_prior_end, _ = values["operating_prior"]
    if (rev_now <= 0 or rev_prior <= 0 or not 310 <= (now-prior).days <= 420
            or not 310 <= (inc_now-inc_prior).days <= 420
            or now != op_end or prior != op_prior_end):
        raise SourceFeatureHold("Misaligned SEC financial periods")
    cutoff = date.fromisoformat(signal_day)
    if (cutoff-filed_rev).days > 211 or (cutoff-filed_inc).days > 211:
        raise SourceFeatureHold("Stale current revenue/income facts")
    earnings = income_now > 0 and (income_prior <= 0 or income_now / income_prior - 1 > .2)
    return {
        "revenue_yoy": rev_now/rev_prior-1,
        "net_income_now": income_now, "net_income_prior": income_prior,
        "earnings_improvement": earnings,
        "margin_delta_pp": 100*(op_now/rev_now - op_prior/rev_prior),
        "financial_source": "SEC_ORIGINAL_QA_REVIEWED",
        "latest_accepted_at": max(facts["revenue_now"]["accepted_at"],
                                  facts["income_now"]["accepted_at"]),
    }


def recompute_full_month(bundle, *, fixture_min_members=None):
    """Derive candidate panel and select; all missing competitors force HOLD."""
    if not isinstance(bundle, dict) or bundle.get("schema") != "gem-source-month-v1":
        raise SourceFeatureHold("Unrecognized GEM original-source bundle")
    members = bundle.get("universe")
    rows = bundle.get("candidates")
    sessions = bundle.get("completed_sessions")
    signal = bundle.get("signal_session")
    if (not isinstance(members, list) or not isinstance(rows, list)
            or not isinstance(sessions, list) or len(sessions) < 127
            or sessions != sorted(set(sessions))
            or signal != sessions[-1] or len(rows) != len(members)):
        raise SourceFeatureHold("Incomplete candidate or session universe")
    source_rows = {r.get("security_id"): r for r in rows if isinstance(r, dict)}
    if len(source_rows) != len(rows):
        raise SourceFeatureHold("Duplicated security source rows")
    mapped = []
    blockers = []
    for member in members:
        key = member.get("security_id")
        ticker = member.get("ticker")
        row = source_rows.get(key)
        if row is None or row.get("ticker") != ticker:
            raise SourceFeatureHold("Missing/incorrect security source identity")
        try:
            prices = verify_price_features(row.get("prices"), signal_day=signal, sessions=sessions)
            financial = verify_financial_features(row.get("facts"), signal_day=signal)
            mapped.append({"security_id": key, "ticker": ticker, **prices, **financial,
                           "security_identity_reviewed": row.get("identity_reviewed") is True})
        except (SourceFeatureHold, TypeError, ValueError) as exc:
            blockers.append({"ticker": ticker, "reason": str(exc)[:180]})
            # Fill with explicit missing flags, NEVER with invented data.
            mapped.append({"security_id": key, "ticker": ticker, "r63": None,
                           "nominal_close": None, "adv20": None, "revenue_yoy": None,
                           "margin_delta_pp": None, "net_income_now": None,
                           "net_income_prior": None, "earnings_improvement": None,
                           "price_last_session": None, "price_sessions": 0,
                           "price_basis": "HOLD", "financial_source": "HOLD",
                           "security_identity_reviewed": False})
    panel = {"schema": "gem-monthly-features-v1",
             "frozen_commit": FROZEN, "signal_session": signal,
             "next_session": bundle.get("next_session"),
             "calendar_verified": bundle.get("calendar_verified") is True,
             "universe": members, "features": mapped,
             "membership_reviewed": bundle.get("membership_reviewed") is True,
             "actions_reviewed": bundle.get("actions_reviewed") is True,
             "benchmark_reviewed": bundle.get("benchmark_reviewed") is True,
             "source_manifest_reviewed": bundle.get("source_manifest_reviewed") is True}
    report = select_monthly(panel, fixture_min_members=fixture_min_members)
    report["independent_recalculation_blockers"] = blockers
    report["raw_sources_used"] = True
    report["qa_scope"] = "NUMERICALLY_RECOMPUTED_SOURCE_FLAGS_NOT_CRYPTOGRAPHICALLY_CERTIFIED"
    return report
