"""Marketstack initial-backfill authorization and source-integrity tests.

No network requests, no real API keys, no database writes, no broker.
"""
from datetime import datetime, timezone

import pytest

from gem_data.gem_marketstack_backfill import (
    MarketstackBackfillHold, _db_urls, _unpack_membership,
    _RESERVE_PREFIX,
)
from gem_data.gem_source_health import classify
import base64
import csv
import io
import zlib
import hashlib


def _env(monkeypatch, cap="1000"):
    # Freeze authorization-month clock; regression remains valid after Oct 2026.
    from gem_data import gem_marketstack_backfill as worker
    class October2026(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 13, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(worker, "datetime", October2026)
    monkeypatch.setenv("GEM_MARKETSTACK_BACKFILL_ENABLED", "yes")
    monkeypatch.setenv("MARKETSTACK_API_KEY", "unit-test-not-real")
    monkeypatch.setenv("GEM_READONLY_DATABASE_URL",
                       "postgresql://gem_web_readonly:private@localhost/db")
    monkeypatch.setenv("GEM_INGEST_DATABASE_URL",
                       "postgresql://gem_source_ingest_limited:private@localhost/db")
    monkeypatch.setenv("GEM_MARKETSTACK_MONTHLY_CREDIT_CAP", cap)


def test_approved_1000_credit_cap(monkeypatch):
    _env(monkeypatch)
    _, _, cap = _db_urls()
    assert cap == 1000


def test_cap_above_authorization_holds(monkeypatch):
    _env(monkeypatch, "1001")
    with pytest.raises(MarketstackBackfillHold, match="1000"):
        _db_urls()


def test_no_key_never_tries_provider(monkeypatch):
    _env(monkeypatch)
    monkeypatch.delenv("MARKETSTACK_API_KEY")
    with pytest.raises(MarketstackBackfillHold):
        _db_urls()


def test_current_membership_fingerprint_checked():
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=["Symbol", "CIK"])
    writer.writeheader()
    for i in range(500):
        writer.writerow({"Symbol":f"AAA{i}", "CIK":str(i+1)})
    raw = stream.getvalue().encode()
    metadata = {"source_raw_zlib_base64":
                base64.b64encode(zlib.compress(raw)).decode()}
    tickers = _unpack_membership(metadata, hashlib.sha256(raw).hexdigest())
    assert len(tickers) == 500
    with pytest.raises(MarketstackBackfillHold):
        _unpack_membership(metadata, "a"*64)


def test_observed_bars_are_not_verified_source_qa():
    report = classify(
       [{"source_type":"prices","provider":"MARKETSTACK",
         "receipt_count":4,"unique_members":0,"refreshed_at":
         datetime(2026,10,13,tzinfo=timezone.utc)}],
       [],{},membership_count=503,observed_marketstack=4,
       marketstack_requests=7,
       verified_price_tickers={})
    assert report["prices"]["marketstack_observed_not_certified"] == 4
    assert report["prices"]["marketstack_fully_verified"] == 0
    assert report["prices"]["marketstack_monthly_requests_reserved"] == 7
