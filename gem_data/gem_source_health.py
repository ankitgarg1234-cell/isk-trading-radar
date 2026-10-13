"""Read-only GEMv1 source integrity scoreboard from isolated Neon receipts.

The scoreboard is a transparency view, NOT a source certification engine.
Never counts an API probe as complete coverage, or a machine candidate as
verified investment data. It never queries unrelated trading tables.
"""
from __future__ import annotations

from datetime import datetime, timezone
import os
import psycopg

EXPERIMENT = "gem-v1-forward-2026-10"
SOURCES = (
    ("membership", "S&P 500 membership", "Effective-dated issuer identity and additions/removals"),
    ("prices", "Daily prices and liquidity", "At least 127 bars per security, adjusted/nominal parity"),
    ("sec", "SEC financial statements", "Six quarter facts, original filing contexts and availability"),
    ("actions", "Corporate actions", "Splits, spinoffs, mergers and dividend entitlements"),
    ("calendar", "NYSE trading calendar", "Completed sessions, holidays and month-end cutoffs"),
    ("benchmark", "SPY benchmark", "Reconciled daily close, dividends and total returns"),
)


class IntegrityUnavailable(RuntimeError):
    pass


def _iso(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return None
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def classify(receipts, probes, sec_stats, *, membership_count=0,
             ibkr_sample_count=0, approved_signals=0, checked_at=None, verified_price_tickers=None,
             observed_marketstack=0, marketstack_requests=0, wiki_metrics=None,
             sec_exception_categories=None, marketstack_rejected_bars=0,
             marketstack_errors=None):
    """Pure testable projection. Explicitly fail closed on absent evidence."""
    receipt_by_type = {}
    providers = {}
    for row in receipts:
        source = row["source_type"]
        provider = row["provider"]
        receipt_by_type[source] = max(
            filter(None, (receipt_by_type.get(source), _iso(row.get("refreshed_at")))),
            default=None
        )
        providers[provider] = {
            "source_type": source,
            "unique_members": int(row.get("unique_members") or 0),
            "receipt_count": int(row.get("receipt_count") or 0),
            "last_refreshed": _iso(row.get("refreshed_at")),
        }
    probe_by_type = {r["source_type"]: r for r in probes}
    statements = int(providers.get("SEC_ZIP_SUBMISSIONS", {}).get("unique_members", 0))
    companyfacts = int(providers.get("SEC_ZIP_COMPANYFACTS", {}).get("unique_members", 0))
    pairs = min(statements, companyfacts)
    inspected = int(sec_stats.get("inspected", 0))
    machine_complete = int(sec_stats.get("machine_complete", 0))
    certified = int(sec_stats.get("certified", 0))
    reviewed_receipts = sec_stats.get("verified_receipts")
    if reviewed_receipts is not None:
        reviewed_receipts = int(reviewed_receipts)
    unknown = max(0, inspected - machine_complete)
    unaudited = max(0, pairs - inspected)
    verified_price_tickers = verified_price_tickers or {}
    marketstack = set(verified_price_tickers.get("MARKETSTACK", []))
    ibkr = set(verified_price_tickers.get("IBKR", [])) - marketstack
    others = set()
    for provider, tickers in verified_price_tickers.items():
        if provider not in ("MARKETSTACK", "IBKR"):
            others.update(tickers)
    others -= marketstack | ibkr
    wiki_metrics = wiki_metrics or {}
    sec_exception_categories = sec_exception_categories or {}
    marketstack_errors = marketstack_errors or {}
    sections = []
    for key, title, requirement in SOURCES:
        pr = probe_by_type.get(key, {})
        evidence = []
        if key == "membership":
            evidence = [f"{membership_count} current security lines in secondary snapshot" if membership_count else "No countable membership snapshot",
                        "Wikipedia/CIK cross-check: " + ("MATCH" if (wiki_metrics.get("secondary_comparison") or {}).get("identity_match") is True else "NOT RECONCILED"),
                        "Primary effective-date verification pending"]
        elif key == "prices":
            evidence = [f"{len(marketstack | ibkr | others)} complete independently reviewed 127-session security histories in stored receipts",
                        f"IBKR limited diagnostic: {ibkr_sample_count} sampled tickers" if ibkr_sample_count else "No IBKR full-universe ingestion established",
                        f"Marketstack EOD stored for {observed_marketstack} tickers; {marketstack_requests} requests reserved this month",
                        f"Marketstack invalid-date observations: {marketstack_rejected_bars}",
                        "Marketstack source failure reasons: " + ", ".join(
                            f"{code}: {count}" for code,count in marketstack_errors.items())
                            if marketstack_errors else "No retained source failure reasons",
                        "Observed prices still require independent adjustment and calendar QA"]
        elif key == "sec":
            evidence = [f"{pairs} company source pairs collected",
                        f"{inspected} machine-assessed; {machine_complete} candidate-complete, {unknown} incomplete/unknown, {unaudited} not assessed",
                        (f"{reviewed_receipts} receipt integrity checks passed" if reviewed_receipts is not None else "Independent receipt-audit count unavailable to read-only dashboard") + f"; {certified} independently certified",
                        "Primary SEC exceptions: " + ", ".join(
                            f"{key}={val}" for key,val in sorted(
                                sec_exception_categories.items(),key=lambda x:-x[1])[:4])]
        elif key == "actions":
            evidence = ["Limited corporate-action diagnostics; full issuer event ledger pending"]
        elif key == "calendar":
            evidence = ["Official exchange calendar received; completed-session audit pending"]
        else:
            evidence = ["Official distribution schedule received; total-return reconstruction pending"]
        inspected_stage = (key == "sec" and inspected > 0)
        sections.append({
            "key": key, "title": title, "requirement": requirement,
            "status": "PARTIAL" if (key in receipt_by_type or key in probe_by_type) else "NO_EVIDENCE",
            "last_refreshed": receipt_by_type.get(key),
            "last_checked": _iso(pr.get("last_checked")),
            "last_audited": _iso(sec_stats.get("last_audited")) if key == "sec" else None,
            "stages": [
                {"name": "Collected", "state": "PARTIAL" if (key in receipt_by_type or key in probe_by_type) else "PENDING"},
                {"name": "Coverage", "state": "PARTIAL" if key == "sec" and pairs else "PENDING"},
                {"name": "Fact / event QA", "state": "PARTIAL" if inspected_stage else "PENDING"},
                {"name": "Certified", "state": "PENDING"},
            ],
            "evidence": evidence,
        })
    return {
        "schema": "gem-source-integrity-overview-v1",
        "generated_at": _iso(checked_at or datetime.now(timezone.utc)),
        "investment_release": "DATA_HOLD",
        "manual_broker_only": True,
        "approved_monthly_signals": int(approved_signals),
        "membership_security_lines": int(membership_count),
        "wikipedia": {"securities":wiki_metrics.get("security_lines"),
                      "unique_ciks":wiki_metrics.get("unique_issuers"),
                      "secondary_comparison":wiki_metrics.get("secondary_comparison"),
                      "certified":False},
        "prices": {
            "security_lines_target": int(membership_count),
            "marketstack_fully_verified": len(marketstack),
            "ibkr_fully_verified": len(ibkr),
            "other_fully_verified": len(others),
            "overall_fully_verified": len(marketstack | ibkr | others),
            "ibkr_diagnostic_sample": int(ibkr_sample_count),
            "marketstack_observed_not_certified": int(observed_marketstack),
            "marketstack_monthly_requests_reserved": int(marketstack_requests),
            "marketstack_rejected_bars": int(marketstack_rejected_bars),
            "marketstack_errors": marketstack_errors,
            "coverage_note": "Counts require persisted per-ticker 127-session calendar coverage, reviewed price-adjustment parity, a source fingerprint, and source QA PASS. Unverified vendor responses and IBKR samples are not counted.",
        },
        "sec": {
            "unique_submissions": statements,
            "unique_companyfacts": companyfacts,
            "source_pairs": pairs,
            "machine_assessed": inspected,
            "machine_candidate_complete_not_certified": machine_complete,
            "machine_incomplete_or_unknown": unknown,
            "not_machine_assessed": unaudited,
            "independently_certified": certified,
            "receipt_integrity_pass": reviewed_receipts,
            "exception_categories": sec_exception_categories,
            "last_machine_audit": _iso(sec_stats.get("last_audited")),
            "selection_note": "Incomplete/unknown companies must be resolved or proven incapable of displacing the top five; they cannot be silently removed from the universe.",
        },
        "sources": sections,
    }


def read_source_integrity():
    url = os.environ.get("GEM_READONLY_DATABASE_URL", "")
    if not url.startswith("postgresql://gem_web_readonly:"):
        raise IntegrityUnavailable("GEM isolated read-only database is not configured")
    try:
        with psycopg.connect(url, connect_timeout=5) as db:
            with db.cursor() as cur:
                cur.execute("SET TRANSACTION READ ONLY")
                cur.execute("SET LOCAL statement_timeout = 10000")
                cur.execute("""
                    SELECT source_type,provider,
                           COUNT(*) AS receipt_count,
                           COUNT(DISTINCT metadata->>'zip_member_name') AS unique_members,
                           MAX(collected_at) AS refreshed_at
                    FROM gem_source_receipt WHERE experiment_id=%s
                    GROUP BY source_type,provider
                """, (EXPERIMENT,))
                receipts = [dict(zip(("source_type","provider","receipt_count",
                                      "unique_members","refreshed_at"), row))
                            for row in cur.fetchall()]
                cur.execute("""
                    SELECT source_type, MAX(observed_at) AS last_checked
                    FROM gem_source_probe WHERE experiment_id=%s
                    GROUP BY source_type
                """, (EXPERIMENT,))
                probes = [dict(zip(("source_type","last_checked"), row))
                          for row in cur.fetchall()]
                cur.execute("""
                    SELECT COALESCE(MAX((metadata->'metrics'->>'security_lines')::integer),0)
                    FROM gem_source_receipt
                    WHERE experiment_id=%s AND source_type='membership'
                      AND provider='SECONDARY_GITHUB_SP500'
                """, (EXPERIMENT,))
                membership_count = int(cur.fetchone()[0] or 0)
                cur.execute("""
                    SELECT details->'samples' FROM gem_source_probe
                    WHERE experiment_id=%s AND source_type='prices'
                    ORDER BY observed_at DESC LIMIT 1
                """, (EXPERIMENT,))
                price_probe = cur.fetchone()
                samples = price_probe[0] if price_probe and isinstance(price_probe[0], list) else []
                cur.execute("""
                    WITH latest AS (
                      SELECT DISTINCT ON ((substring(details->>'scope' FROM 'CIK ([0-9]{10})')))
                          substring(details->>'scope' FROM 'CIK ([0-9]{10})') AS cik,
                          details->>'fact_status' AS fact_status,
                          details->>'certified' AS certified,
                          observed_at
                      FROM gem_source_probe
                      WHERE experiment_id=%s AND source_type='sec'
                        AND details->>'scope' LIKE 'Independent automated recomputation for CIK %%'
                      ORDER BY (substring(details->>'scope' FROM 'CIK ([0-9]{10})')),
                               observed_at DESC, probe_id DESC
                    )
                    SELECT count(*),
                           count(*) FILTER (WHERE fact_status='CANDIDATE_COMPLETE_NOT_CERTIFIED'),
                           count(*) FILTER (WHERE certified='true'),
                           max(observed_at)
                    FROM latest WHERE cik IS NOT NULL
                """, (EXPERIMENT,))
                assessed, complete, certified, last_audit = cur.fetchone()
                # The read-only dashboard role intentionally cannot SELECT
                # gem_sec_independent_receipt_audit. Do not broaden database
                # privileges or turn an unavailable count into a fake zero.
                receipt_pass = None
                cur.execute("""
                    SELECT metadata->'metrics'
                    FROM gem_source_receipt
                    WHERE experiment_id=%s AND provider='WIKIPEDIA_SP500_CIK_CURRENT'
                    ORDER BY collected_at DESC LIMIT 1
                """, (EXPERIMENT,))
                wiki_row = cur.fetchone()
                wiki_metrics = wiki_row[0] if wiki_row and isinstance(wiki_row[0],dict) else {}
                cur.execute("""
                    SELECT COUNT(DISTINCT metadata->>'ticker')
                    FROM gem_source_receipt
                    WHERE experiment_id=%s AND provider='MARKETSTACK'
                      AND source_type='prices' AND metadata->>'ticker' IS NOT NULL
                """, (EXPERIMENT,))
                observed_marketstack = int(cur.fetchone()[0] or 0)
                cur.execute("""
                    SELECT COUNT(*) FROM gem_source_probe
                    WHERE experiment_id=%s AND source_type='prices'
                      AND probe_id LIKE %s
                """, (EXPERIMENT,
                       'gem-marketstack-request-'+datetime.now(timezone.utc).strftime('%Y%m')+'-%'))
                marketstack_requests = int(cur.fetchone()[0] or 0)
                cur.execute("""
                    WITH latest AS (
                      SELECT DISTINCT ON (details->>'scope')
                          details->'blockers' AS blockers
                      FROM gem_source_probe
                      WHERE experiment_id=%s AND source_type='sec'
                        AND details ? 'fact_status'
                      ORDER BY details->>'scope', observed_at DESC
                    )
                    SELECT reason, COUNT(*)
                    FROM latest,
                         LATERAL jsonb_array_elements_text(COALESCE(blockers,'[]'::jsonb))
                            AS item(reason)
                    GROUP BY reason ORDER BY COUNT(*) DESC LIMIT 20
                """, (EXPERIMENT,))
                sec_exception_categories={name:int(n) for name,n in cur.fetchall()}
                cur.execute("""
                    SELECT COALESCE(SUM(
                        CASE WHEN (metadata->>'rejected_session_count') ~ '^[0-9]{1,5}$'
                        THEN (metadata->>'rejected_session_count')::integer ELSE 0 END),0)
                    FROM gem_source_receipt
                    WHERE experiment_id=%s AND provider='MARKETSTACK'
                      AND source_type='prices' AND metadata->>'retrieval_month'=%s
                """,(EXPERIMENT,datetime.now(timezone.utc).strftime('%Y%m')))
                marketstack_rejected_bars = int(cur.fetchone()[0] or 0)
                cur.execute("""
                    SELECT details->>'reason_code', COUNT(*)
                    FROM gem_source_probe
                    WHERE experiment_id=%s AND source_type='prices'
                      AND probe_id LIKE %s
                      AND details->>'reason_code' IS NOT NULL
                    GROUP BY details->>'reason_code'
                """,(EXPERIMENT,
                     'gem-marketstack-failed-'+datetime.now(timezone.utc).strftime('%Y%m')+'%'))
                marketstack_errors = {k:int(v) for k,v in cur.fetchall()}
                # Price receipts are counted only after independently reviewed
                # source and adjustment evidence; raw vendor calls do not count.
                cur.execute("""
                    SELECT provider, metadata->>'ticker'
                    FROM gem_source_receipt
                    WHERE experiment_id=%s AND source_type='prices'
                      AND metadata->>'source_qa_status'='PASS'
                      AND metadata->>'adjustment_parity_reviewed'='true'
                      AND metadata->>'last_completed_session'=metadata->>'signal_session'
                      AND LENGTH(COALESCE(metadata->>'source_raw_sha256',''))=64
                      AND CASE WHEN (metadata->>'completed_sessions') ~ '^[0-9]{1,5}$'
                            THEN (metadata->>'completed_sessions')::integer >= 127
                            ELSE FALSE END
                """, (EXPERIMENT,))
                verified_price_tickers = {}
                for provider, ticker in cur.fetchall():
                    if provider and ticker:
                        verified_price_tickers.setdefault(provider.upper(), set()).add(ticker)
                cur.execute("""
                    SELECT COUNT(*) FROM gem_signal
                    WHERE experiment_id=%s AND state IN ('APPROVED','RELEASED')
                """, (EXPERIMENT,))
                approved_signals = int(cur.fetchone()[0] or 0)
        report = classify(
            receipts, probes,
            {"inspected": assessed, "machine_complete": complete,
             "certified": certified, "last_audited": last_audit,
             "verified_receipts": receipt_pass},
            membership_count=membership_count, ibkr_sample_count=len(samples),
            approved_signals=approved_signals, verified_price_tickers=verified_price_tickers,
            observed_marketstack=observed_marketstack, marketstack_requests=marketstack_requests,
            wiki_metrics=wiki_metrics,
            sec_exception_categories=sec_exception_categories,
            marketstack_rejected_bars=marketstack_rejected_bars,
            marketstack_errors=marketstack_errors,
        )
        report["data_access"] = "CONNECTED"
        return report
    except (psycopg.Error, ValueError, TypeError):
        raise IntegrityUnavailable("GEM isolated read-only source integrity unavailable") from None

def unavailable_integrity():
    """Render all six data-source cards on database/network failure.

    Never substitute zero for an unknown number or imply a successful audit.
    """
    report = classify([], [], {},
                      checked_at=datetime.now(timezone.utc))
    report["data_access"] = "UNAVAILABLE"
    report["approved_monthly_signals"] = None
    report["membership_security_lines"] = None
    report["wikipedia"] = {"securities":None,"unique_ciks":None,"secondary_comparison":None,"certified":False}
    for key in ("security_lines_target", "marketstack_fully_verified",
                "ibkr_fully_verified", "other_fully_verified",
                "overall_fully_verified", "ibkr_diagnostic_sample"):
        report["prices"][key] = None
    report["prices"]["marketstack_observed_not_certified"] = None
    report["prices"]["marketstack_monthly_requests_reserved"] = None
    report["prices"]["marketstack_rejected_bars"] = None
    report["prices"]["marketstack_errors"] = {}
    report["prices"]["coverage_note"] = (
        "Source database unavailable. Provider coverage is UNKNOWN, not zero.")
    for key in ("unique_submissions", "unique_companyfacts", "source_pairs",
                "machine_assessed", "machine_candidate_complete_not_certified",
                "machine_incomplete_or_unknown", "not_machine_assessed",
                "independently_certified", "receipt_integrity_pass"):
        report["sec"][key] = None
    report["sec"]["last_machine_audit"] = None
    report["sec"]["exception_categories"] = {}
    for source in report["sources"]:
        source["status"] = "UNAVAILABLE"
        source["last_refreshed"] = None
        source["last_checked"] = None
        source["last_audited"] = None
        source["stages"] = [
            {"name": stage["name"], "state": "PENDING"}
            for stage in source["stages"]
        ]
        source["evidence"] = [
            "Database source unavailable. Coverage and verification cannot be inferred.",
            "Try Refresh evidence; source collection state is not represented as zero.",
        ]
    return report
