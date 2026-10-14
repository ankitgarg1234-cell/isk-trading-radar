"""Budgeted, append-only Marketstack EOD collector for isolated GEM research.

Explicit GEM_MARKETSTACK_BACKFILL_ENABLED=yes and a positive
GEM_MARKETSTACK_MONTHLY_CREDIT_CAP are required before any paid requests.
Persist a monthly request reservation BEFORE each HTTP request so a restart
does not repeat an attempted provider charge. Raw EOD observations are
UNVERIFIED, never source QA PASS or eligible to release GEMv1 selections.
No broker access or automated trading.
"""
from __future__ import annotations

import base64
import csv
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from io import StringIO
import json
import os
import re
import zlib

import psycopg

from gem_data.gem_public_ingest import EXPERIMENT, write_observation
from gem_data.marketstack_eod_probe import MarketstackEODProbe, MarketstackProbeError

_SYMBOL = re.compile(r"^[A-Z0-9.\-]{1,16}$")
_RESERVE_PREFIX = "gem-marketstack-request-"


class MarketstackBackfillHold(RuntimeError):
    pass


def _db_urls():
    if (os.getenv("GEM_MARKETSTACK_BACKFILL_ENABLED") != "yes"
            or not os.getenv("MARKETSTACK_API_KEY")):
        raise MarketstackBackfillHold("Marketstack backfill disabled or key unavailable")
    reader = os.getenv("GEM_READONLY_DATABASE_URL", "")
    writer = os.getenv("GEM_INGEST_DATABASE_URL", "")
    if (not reader.startswith("postgresql://gem_web_readonly:")
            or not writer.startswith("postgresql://gem_source_ingest_limited:")):
        raise MarketstackBackfillHold("Restricted GEM reader/collector roles unavailable")
    try:
        monthly_cap = int(os.getenv("GEM_MARKETSTACK_MONTHLY_CREDIT_CAP", "0"))
    except ValueError:
        raise MarketstackBackfillHold("Invalid request budget") from None
    if not 1 <= monthly_cap <= 1000:
        raise MarketstackBackfillHold("Initial backfill explicitly capped at 1000 requests")
    # User authorized initial October backfill, not a fresh recurring
    # 1000-credit monthly allocation in perpetuity.
    if datetime.now(timezone.utc).strftime("%Y%m") != "202610":
        raise MarketstackBackfillHold("Initial October 2026 authorization expired")
    return reader, writer, monthly_cap


def _unpack_membership(metadata, digest):
    encoded = metadata.get("source_raw_zlib_base64")
    if not isinstance(encoded, str) or len(encoded) > 500_000:
        raise MarketstackBackfillHold("Membership source not retained")
    try:
        packed = base64.b64decode(encoded, validate=True)
        decomp = zlib.decompressobj()
        raw = decomp.decompress(packed, 500_001)
        if len(raw) > 500_000 or not decomp.eof or decomp.unconsumed_tail:
            raise ValueError()
        raw += decomp.flush()
        if sha256(raw).hexdigest() != digest:
            raise ValueError()
        rows = list(csv.DictReader(StringIO(raw.decode("utf-8-sig"))))
        tickers = sorted(set(row["Symbol"].upper() for row in rows))
        if not 480 <= len(tickers) <= 600 or any(not _SYMBOL.fullmatch(t) for t in tickers):
            raise ValueError()
        return tickers
    except (ValueError, KeyError, UnicodeError, zlib.error, TypeError, csv.Error):
        raise MarketstackBackfillHold("Stored membership fingerprint or symbols invalid") from None


def _universe_and_spend(reader, month, today):
    with psycopg.connect(reader, connect_timeout=6) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SET LOCAL statement_timeout = 10000")
            cur.execute("""
                SELECT metadata,source_sha256
                FROM gem_source_receipt
                WHERE experiment_id=%s AND provider='SECONDARY_GITHUB_SP500'
                ORDER BY collected_at DESC LIMIT 1
            """, (EXPERIMENT,))
            source = cur.fetchone()
            if not source:
                raise MarketstackBackfillHold("No validated current membership source")
            tickers = _unpack_membership(source[0], str(source[1]).strip())
            cur.execute("""
                SELECT probe_id
                FROM gem_source_probe
                WHERE experiment_id=%s AND source_type='prices'
                  AND probe_id LIKE %s
            """, (EXPERIMENT, _RESERVE_PREFIX + month + "-%"))
            reservations = [x[0] for x in cur.fetchall()]
            count = len(reservations)
            # Keep the UTC reservation day and number of attempts per symbol.
            # Previous code treated ANY October request as a permanent attempt,
            # making all 503 names ineligible after the first sweep even though
            # 14 had no persisted observation. That was NOT quota exhaustion.
            attempted = {}
            prefix = _RESERVE_PREFIX + month + "-"
            for reservation in reservations:
                tail = reservation.removeprefix(prefix)
                day, separator, symbol = tail.partition("-")
                if separator and len(day) == 8 and day.isdigit() and _SYMBOL.fullmatch(symbol):
                    attempted.setdefault(symbol, {"days": [], "last_reason": None})["days"].append(day)
            cur.execute("""
                SELECT details->>'ticker', details->>'reason_code'
                FROM gem_source_probe
                WHERE experiment_id=%s AND source_type='prices'
                  AND probe_id LIKE %s AND details->>'ticker' IS NOT NULL
                ORDER BY observed_at ASC, probe_id ASC
            """, (EXPERIMENT, "gem-marketstack-failed-" + month + "%"))
            for symbol, reason in cur.fetchall():
                if symbol in attempted:
                    attempted[symbol]["last_reason"] = reason
            cur.execute("""
                SELECT DISTINCT metadata->>'ticker'
                FROM gem_source_receipt
                WHERE experiment_id=%s AND provider='MARKETSTACK'
                  AND source_type='prices'
                  AND metadata->>'retrieval_month'=%s
                  AND metadata->>'ticker' IS NOT NULL
            """, (EXPERIMENT, month))
            done = {x[0] for x in cur.fetchall()}
    return tickers, count, done, attempted


def _retry_candidates(symbols, complete, attempted, today):
    """Prefer never-tried symbols, then safe single retries on a later UTC day.

    A maximum of TWO reserved attempts per ticker is allowed for the initial
    backfill. Malformed/permanently unsupported vendor data needs independent
    resolution, not blind repeat spending. Supports old set-style test fixtures.
    """
    if not isinstance(attempted, dict):
        eligible = [sym for sym in symbols if sym not in complete and sym not in attempted]
        return eligible, []
    fresh, retry, held = [], [], []
    permanent = ("MARKETSTACK_HTTP_422",
                 "no valid vendor historical prices found",
                 "missing or invalid vendor field:",
                 "invalid vendor numeric field:",
                 "invalid vendor nominal OHLC")
    date_key = today.strftime("%Y%m%d")
    for symbol in symbols:
        if symbol in complete:
            continue
        info = attempted.get(symbol, {})
        days = info.get("days", [])
        reason = info.get("last_reason") or ""
        if any(reason.startswith(code) for code in permanent):
            held.append(symbol)
        elif not days:
            fresh.append(symbol)
        elif len(days) < 2 and max(days) < date_key:
            retry.append(symbol)
        else:
            held.append(symbol)
    return fresh + retry, held


def _reserve_request(reader, writer, symbol, stamp, cap):
    """Atomically serialize GEM Marketstack budget reservations across restarts.

    Writer retains INSERT-only GEM permissions; the separate SELECT-only role
    reads reservation counts *after* a writer-owned advisory lock is acquired.
    All app workers must use this function; unrelated consumers of the same
    Marketstack account are outside this isolated budget.
    """
    key = _RESERVE_PREFIX + stamp.strftime("%Y%m") + "-" + stamp.strftime("%Y%m%d") + "-" + symbol
    prefix = _RESERVE_PREFIX + stamp.strftime("%Y%m") + "-%"
    digest = sha256(key.encode()).hexdigest()
    with psycopg.connect(writer, connect_timeout=6) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ WRITE")
            cur.execute("SET LOCAL statement_timeout=10000")
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (20261013001,))
            with psycopg.connect(reader, connect_timeout=6) as ro:
                with ro.cursor() as probe:
                    probe.execute("SET TRANSACTION READ ONLY")
                    probe.execute("SET LOCAL statement_timeout=10000")
                    probe.execute("""
                        SELECT COUNT(*) FROM gem_source_probe
                        WHERE experiment_id=%s AND source_type='prices'
                          AND probe_id LIKE %s
                    """, (EXPERIMENT, prefix))
                    already = int(probe.fetchone()[0])
                    if already >= cap:
                        return False
                    probe.execute("""
                        SELECT 1 FROM gem_source_probe
                        WHERE experiment_id=%s AND probe_id=%s LIMIT 1
                    """, (EXPERIMENT, key))
                    if probe.fetchone() is not None:
                        return False
            cur.execute("""
                INSERT INTO gem_source_probe
                (probe_id,experiment_id,source_type,state,observed_at,
                 diagnostic_hash,sample_count,approved_for_trading,details)
                VALUES (%s,%s,'prices','PARTIAL',%s,%s,0,FALSE,%s::jsonb)
                ON CONFLICT (probe_id) DO NOTHING RETURNING probe_id
            """, (key, EXPERIMENT, stamp, digest,
                  json.dumps({"provider":"MARKETSTACK","ticker":symbol,
                              "state":"REQUEST_RESERVED_COUNTS_TOWARD_BUDGET",
                              "trading_authorized":False})))
            created = cur.fetchone() is not None
        conn.commit()
    return created


def _persist_observation(writer, symbol, observed, bars, receipt):
    normalized = [
        {"ticker": bar.symbol, "session": bar.session.isoformat(),
         "open":bar.open,"high":bar.high,"low":bar.low,"close":bar.close,
         "volume":bar.volume,"vendor_adj_close":bar.vendor_adj_close,
         "split_factor":bar.split_factor,"dividend":bar.dividend}
        for bar in bars
    ]
    raw = json.dumps(normalized, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    digest = sha256(raw).hexdigest()
    month = observed.strftime("%Y%m")
    data = {
        "receipt_id": "gem-marketstack-" + month + "-" + symbol + "-" + digest[:20],
        "provider": "MARKETSTACK", "observed_at": observed,
        "source_uri": "https://api.marketstack.com/v2/eod",
        "source_sha256": digest,
        "coverage_status": "UNKNOWN",
        "metadata": {
            "ticker": symbol,"retrieval_month":month,
            "first_session":bars[0].session.isoformat(),
            "last_session":bars[-1].session.isoformat(),
            "completed_sessions":len(bars),
            "vendor_page_hashes":receipt.response_sha256,
            "rejected_session_count":len(receipt.rejected_sessions),
            "rejected_sessions":list(receipt.rejected_sessions),
            "rejected_reasons":list(receipt.rejected_reasons),
            "fallback_needed":bool(receipt.rejected_sessions),
            "normalized_bars_sha256":digest,
            "normalized_bars_zlib_base64":base64.b64encode(zlib.compress(raw,6)).decode(),
            "source_qa_status":"PENDING",
            "adjustment_parity_reviewed":False,
            "trading_approved":False,
        },
    }
    probe = {
        "probe_id": "gem-marketstack-observed-" + month + "-" + symbol + "-" + digest[:20],
        "source_type":"prices","state":"PARTIAL","observed_at":observed,
        "diagnostic_hash":digest,"sample_count":len(bars),
        "details":{"provider":"MARKETSTACK","ticker":symbol,
                   "observed_sessions":len(bars),
                   "rejected_session_count":len(receipt.rejected_sessions),
                   "fallback_needed":bool(receipt.rejected_sessions),
                   "first_session":bars[0].session.isoformat(),
                   "last_session":bars[-1].session.isoformat(),
                   "validation":"NORMALIZED_EOD_OBSERVED_NOT_ADJUSTMENT_CERTIFIED",
                   "trading_authorized":False},
    }
    with psycopg.connect(writer, connect_timeout=6) as conn:
        write_observation(conn, data, probe)
    return len(bars)


def _record_failed_observation(writer, symbol, observed, reason):
    """A provider attempt remains visible even when no usable EOD bars returned."""
    key = "gem-marketstack-failed-" + observed.strftime("%Y%m%d") + "-" + symbol
    digest = sha256((key + reason).encode()).hexdigest()
    probe = {
        "probe_id":key, "source_type":"prices","state":"BLOCKED",
        "observed_at":observed,"diagnostic_hash":digest,"sample_count":0,
        "details":{"provider":"MARKETSTACK","ticker":symbol,
                   "reason_code":reason,"validation":"NO_USABLE_EOD_OBSERVATION",
                   "trading_authorized":False},
    }
    with psycopg.connect(writer,connect_timeout=6) as conn:
        write_observation(conn,None,probe)


def collect_batch(*, max_tickers=20, observed=None, fetch_fn=None):
    """One explicit batch; no HTTP request is triggered by dashboard views.

    Bounded at twenty symbols per call; one provider page per symbol (period 220
    calendar days). A whole month is budget-capped by persisted reservations.
    API failures consume their reserved request and remain visible as gaps.
    """
    if type(max_tickers) is not int or not 1 <= max_tickers <= 20:
        raise MarketstackBackfillHold("One batch limited to 1..20 tickers")
    reader, writer, cap = _db_urls()
    observed = observed or datetime.now(timezone.utc)
    if observed.tzinfo is None:
        raise MarketstackBackfillHold("Timezone-aware observation required")
    observed = observed.astimezone(timezone.utc)
    month = observed.strftime("%Y%m")
    if month != "202610":
        raise MarketstackBackfillHold("Initial October 2026 authorization expired")
    symbols, used, complete, attempted = _universe_and_spend(reader, month, observed.date())
    remaining = min(max_tickers, max(0, cap-used))
    eligible, held = _retry_candidates(symbols, complete, attempted, observed.date())
    chosen = eligible[:remaining]
    pending = sum(sym not in complete for sym in symbols)
    report = {"universe_symbols":len(symbols),"monthly_cap":cap,
              "reserved_before":used,"monthly_remaining_local":max(0,cap-used),
              "new_reserved":0,"retry_eligible":len(eligible),
              "held_for_source_review":len(held),
              "observed_symbols":0,"observed_bars":0,
              "failed":[], "pending_symbols_before":pending,
              "certified":False,"automatic_trading":False}
    if not chosen:
        if used >= cap:
            report["status"] = "LOCAL_MONTHLY_REQUEST_CAP_REACHED"
        elif pending == 0:
            report["status"] = "ALL_SYMBOLS_OBSERVED_QA_PENDING"
        else:
            report["status"] = "RETRY_BACKOFF_OR_SOURCE_REVIEW_REQUIRED"
        return report
    probe = fetch_fn
    consecutive_failures = 0
    for symbol in chosen:
        if not _reserve_request(reader, writer, symbol, observed, cap):
            continue
        report["new_reserved"] += 1
        try:
            if probe is None:
                with MarketstackEODProbe(max_credits=1, page_limit=1000) as vendor:
                    rows, receipt = vendor.fetch(symbol, observed.date()-timedelta(days=220), observed.date())
            else:
                rows, receipt = probe(symbol, observed.date()-timedelta(days=220), observed.date())
            count = _persist_observation(writer, symbol, observed, rows, receipt)
            report["observed_symbols"] += 1
            report["observed_bars"] += count
            consecutive_failures = 0
        except (MarketstackProbeError, ValueError, psycopg.Error) as exc:
            reason = str(exc)[:90] if isinstance(exc,MarketstackProbeError) else type(exc).__name__
            report["failed"].append({"ticker":symbol,"reason_code":reason})
            try:
                _record_failed_observation(writer,symbol,observed,reason)
            except psycopg.Error:
                report["failure_receipt_write_error"]=True
            consecutive_failures += 1
            # A systemic provider/auth/quota issue should never burn hundreds
            # of prepaid attempts just because the backfill batch is large.
            if (reason in ("MARKETSTACK_HTTP_401", "MARKETSTACK_HTTP_402",
                           "MARKETSTACK_HTTP_403", "MARKETSTACK_HTTP_429")
                    or reason.startswith("MARKETSTACK_API_ERROR_")
                    or consecutive_failures >= 3):
                report["status"] = "PROVIDER_OR_SYSTEMIC_FAILURE_PAUSED"
                report["pause_reason"] = reason
                return report
    report["status"]="OBSERVATIONS_ONLY_NOT_APPROVED"
    return report


if __name__ == "__main__":
    print(json.dumps(collect_batch(), sort_keys=True))
