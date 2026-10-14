"""Read-only GEM price-remediation progress from immutable Neon source evidence.

Deliberately does NOT fetch Yahoo, change prices, certify adjustments, generate
signals, or connect to a broker. Separate collected/observed/QA/release stages.
"""
from __future__ import annotations

from datetime import datetime, timezone
import os
import psycopg

from gem_data.gem_public_ingest import EXPERIMENT

TARGET_SESSIONS = ("2026-06-09", "2026-06-10", "2026-06-15")
MONTH = "202610"


class GapProgressUnavailable(RuntimeError):
    pass


def project_progress(*, target, observed, histories_127, affected, rejected_rows,
                     audited, raw_pass, raw_holds, last_audited, requests, request_cap,
                     session_counts, certified):
    """Simple pure projection; impossible-to-reconcile counts fail closed."""
    counts = (target, observed, histories_127, affected, rejected_rows, audited,
              raw_pass, raw_holds, requests, request_cap, certified)
    if any(type(n) is not int or n < 0 for n in counts):
        raise GapProgressUnavailable("Invalid or unknown progress counts")
    if (target < observed or observed < histories_127 or observed < affected
            or observed < audited or audited < raw_pass or audited < raw_holds
            or request_cap < 1 or certified > observed):
        raise GapProgressUnavailable("Inconsistent GEM progress counters")
    if not isinstance(session_counts, dict) or any(
            day not in TARGET_SESSIONS or type(count) is not int or count < 0 or count > observed
            for day, count in session_counts.items()):
        raise GapProgressUnavailable("Invalid targeted session inventory")
    if set(session_counts) != set(TARGET_SESSIONS):
        raise GapProgressUnavailable("Partial session-inventory query")
    return {
        "schema": "gem-price-gap-progress-v1",
        "data_access": "CONNECTED",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "investment_release": "DATA_HOLD",
        "trading_enabled": False,
        "collection": {
            "security_lines_target": target,
            "marketstack_histories_stored": observed,
            "remaining_without_history": target - observed,
            "histories_with_at_least_127_bars": histories_127,
            "histories_with_rejected_vendor_rows": affected,
            "rejected_vendor_rows": rejected_rows,
        },
        "stored_receipt_audit": {
            "audited": audited,
            "integrity_pass": raw_pass,
            "vendor_or_length_holds": raw_holds,
            "last_recorded_at": last_audited.astimezone(timezone.utc).isoformat()
                                if isinstance(last_audited, datetime) and last_audited.tzinfo
                                else None,
            "does_not_certify_prices": True,
        },
        "missing_close_sessions": [
            {"session": day, "affected_marketstack_histories": session_counts[day],
             "replacement_bars_approved": 0}
            for day in TARGET_SESSIONS
        ],
        "marketstack_local_budget": {
            "requests_reserved": requests,
            "cap": request_cap,
            "remaining_in_local_ledger": max(0, request_cap-requests),
            "vendor_account_balance_not_independently_verified": True,
        },
        "verification": {
            "independently_certified_price_histories": certified,
            "yahoo_research_cannot_certify_source": True,
            "production_price_patching_enabled": False,
            "next_required_step": "Independent licensed price/adjustment reconciliation; never replace missing close silently",
        },
        "yahoo_research": {
            "state": "EXTERNAL_PILOT_ONLY_NOT_IMPORTED",
            "sample_tickers": 3,
            "sample_observations": 9,
            "pilot_workflow_url": "https://github.com/ankitgarg1234-cell/isk-trading-radar/actions/runs/38568599964",
            "personal_research_not_production_feed": True,
        },
    }


def read_gap_progress():
    url = os.getenv("GEM_READONLY_DATABASE_URL", "")
    if not url.startswith("postgresql://gem_web_readonly:"):
        raise GapProgressUnavailable("Restricted GEM read-only role unavailable")
    try:
        with psycopg.connect(url, connect_timeout=5) as db:
            with db.cursor() as cur:
                cur.execute("SET TRANSACTION READ ONLY")
                cur.execute("SET LOCAL statement_timeout=15000")
                cur.execute("""
                    SELECT metadata->'metrics'->>'security_lines'
                    FROM gem_source_receipt
                    WHERE experiment_id=%s AND provider='SECONDARY_GITHUB_SP500'
                    ORDER BY collected_at DESC, receipt_id DESC LIMIT 1
                """, (EXPERIMENT,))
                r = cur.fetchone()
                if not r or r[0] is None or not str(r[0]).isdigit():
                    raise GapProgressUnavailable("Membership target not evidenced")
                target = int(r[0])
                cur.execute("""
                    WITH latest AS (
                        SELECT DISTINCT ON (metadata->>'ticker')
                            metadata
                        FROM gem_source_receipt
                        WHERE experiment_id=%s AND provider='MARKETSTACK'
                          AND source_type='prices' AND metadata->>'ticker' IS NOT NULL
                        ORDER BY metadata->>'ticker', observed_at DESC, receipt_id DESC
                    )
                    SELECT COUNT(*),
                           COUNT(*) FILTER (WHERE
                               (metadata->>'completed_sessions') ~ '^[0-9]{1,5}$'
                               AND (metadata->>'completed_sessions')::int >= 127),
                           COUNT(*) FILTER (WHERE
                               (metadata->>'rejected_session_count') ~ '^[0-9]{1,7}$'
                               AND (metadata->>'rejected_session_count')::int > 0),
                           COALESCE(SUM(CASE WHEN
                               (metadata->>'rejected_session_count') ~ '^[0-9]{1,7}$'
                               THEN (metadata->>'rejected_session_count')::int ELSE 0 END),0)
                    FROM latest
                """, (EXPERIMENT,))
                observed, histories_127, affected, rejected_rows = map(int, cur.fetchone())
                cur.execute("""
                    WITH latest AS (
                        SELECT DISTINCT ON (metadata->>'ticker')
                            metadata->>'ticker' ticker, metadata
                        FROM gem_source_receipt
                        WHERE experiment_id=%s AND provider='MARKETSTACK'
                          AND source_type='prices' AND metadata->>'ticker' IS NOT NULL
                        ORDER BY metadata->>'ticker', observed_at DESC, receipt_id DESC
                    )
                    SELECT reason.item->>0 AS session, COUNT(DISTINCT latest.ticker)
                    FROM latest
                    CROSS JOIN LATERAL jsonb_array_elements(
                        CASE WHEN jsonb_typeof(latest.metadata->'rejected_reasons')='array'
                        THEN latest.metadata->'rejected_reasons' ELSE '[]'::jsonb END
                    ) AS reason(item)
                    WHERE reason.item->>0 = ANY(%s)
                      AND reason.item->>1 = 'missing or invalid vendor field: close'
                    GROUP BY 1
                """, (EXPERIMENT, list(TARGET_SESSIONS)))
                daily = {day: 0 for day in TARGET_SESSIONS}
                for day, n in cur.fetchall():
                    daily[day] = int(n)
                cur.execute("""
                    SELECT COUNT(*),
                           COUNT(*) FILTER (WHERE details->>'raw_receipt_integrity_pass'='true'),
                           COUNT(*) FILTER (WHERE state='BLOCKED'),
                           MAX(observed_at)
                    FROM gem_source_probe
                    WHERE experiment_id=%s AND probe_id LIKE 'gem-price-raw-audit-v1-%%'
                """, (EXPERIMENT,))
                audited, passed, held, last_audited = cur.fetchone()
                cur.execute("""
                    SELECT COUNT(*) FROM gem_source_probe
                    WHERE experiment_id=%s AND source_type='prices'
                      AND probe_id LIKE %s
                """, (EXPERIMENT, 'gem-marketstack-request-'+MONTH+'-%'))
                requests = int(cur.fetchone()[0])
                cur.execute("""
                    SELECT COUNT(DISTINCT metadata->>'ticker') FROM gem_source_receipt
                    WHERE experiment_id=%s AND provider='MARKETSTACK'
                      AND source_type='prices'
                      AND metadata->>'source_qa_status'='PASS'
                      AND metadata->>'adjustment_parity_reviewed'='true'
                      AND metadata->>'last_completed_session'=metadata->>'signal_session'
                      AND LENGTH(COALESCE(metadata->>'source_raw_sha256',''))=64
                      AND CASE WHEN metadata->>'completed_sessions' ~ '^[0-9]{1,5}$'
                           THEN (metadata->>'completed_sessions')::int >= 127
                           ELSE FALSE END
                """, (EXPERIMENT,))
                certified = int(cur.fetchone()[0])
        cap_value = os.getenv("GEM_MARKETSTACK_MONTHLY_CREDIT_CAP", "")
        if not cap_value.isdigit():
            raise GapProgressUnavailable("Provider local budget cap not configured")
        return project_progress(
            target=target, observed=observed, histories_127=histories_127,
            affected=affected, rejected_rows=rejected_rows,
            audited=int(audited), raw_pass=int(passed), raw_holds=int(held),
            last_audited=last_audited, requests=requests,
            request_cap=int(cap_value), session_counts=daily, certified=certified,
        )
    except (psycopg.Error, ValueError, TypeError, OverflowError):
        raise GapProgressUnavailable("GEM price recovery progress unavailable") from None


def unavailable_gap_progress():
    """No fake zeros if the restricted database cannot be read."""
    return {
        "schema": "gem-price-gap-progress-v1",
        "data_access": "UNAVAILABLE",
        "investment_release": "DATA_HOLD",
        "trading_enabled": False,
        "collection": None,
        "stored_receipt_audit": None,
        "missing_close_sessions": None,
        "marketstack_local_budget": None,
        "verification": None,
        "yahoo_research": {"state":"EXTERNAL_PILOT_ONLY_NOT_IMPORTED",
                           "personal_research_not_production_feed":True},
    }
