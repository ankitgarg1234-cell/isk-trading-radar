"""No-network regression tests for GEM raw Marketstack receipt diagnostics."""
from __future__ import annotations

import base64
from datetime import date
from hashlib import sha256
import json
import zlib

from gem_data.gem_price_receipt_audit import audit_receipt


def receipt(n=130, *, rejected=0):
    bars = []
    for index in range(n):
        session = date(2026, 1, 1).toordinal() + index
        bars.append({
            "ticker": "AAPL", "session": date.fromordinal(session).isoformat(),
            "open": 100.0, "high": 103.0, "low": 98.0, "close": 101.0,
            "volume": 1000000.0, "vendor_adj_close": 100.5,
            "split_factor": 1.0, "dividend": 0.0,
        })
    raw = json.dumps(bars, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    digest = sha256(raw).hexdigest()
    metadata = {
        "ticker":"AAPL", "completed_sessions":n,
        "first_session":bars[0]["session"], "last_session":bars[-1]["session"],
        "normalized_bars_sha256":digest,
        "normalized_bars_zlib_base64":base64.b64encode(zlib.compress(raw)).decode(),
        "vendor_page_hashes":["a" * 64],
        "rejected_session_count":rejected,
        "rejected_sessions":[str(i) for i in range(rejected)],
    }
    return "gem-marketstack-202610-AAPL-" + digest[:20],digest,metadata,bars


def test_valid_raw_receipt_is_not_trading_certification():
    rid,digest,metadata,_ = receipt()
    result = audit_receipt(rid,digest,metadata)
    assert result["state"] == "PARTIAL"
    assert result["raw_receipt_integrity_pass"] is True
    assert result["independent_price_parity_pass"] is False
    assert result["approved_for_trading"] is False
    assert result["bars_recomputed"] == 130


def test_short_history_is_held_and_not_fabricated():
    rid,digest,metadata,_ = receipt(90)
    result = audit_receipt(rid,digest,metadata)
    assert result["state"] == "BLOCKED"
    assert result["findings"] == ["INSUFFICIENT_127_SESSIONS"]


def test_vendor_row_rejections_are_preserved():
    rid,digest,metadata,_ = receipt(rejected=3)
    result = audit_receipt(rid,digest,metadata)
    assert result["state"] == "BLOCKED"
    assert "VENDOR_REJECTED_ROWS_PRESENT" in result["findings"]
    assert result["rejected_rows"] == 3


def test_tampered_raw_digest_fails_closed():
    rid,digest,metadata,_ = receipt()
    assert audit_receipt(rid, "b"*64, metadata)["findings"] == ["BARS_SHA256_MISMATCH"]


def test_bad_ohlc_rejected_even_with_valid_hash():
    rid,_,metadata,bars = receipt()
    bars[12]["high"] = 99
    raw = json.dumps(bars, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    digest = sha256(raw).hexdigest()
    metadata["normalized_bars_sha256"] = digest
    metadata["normalized_bars_zlib_base64"] = base64.b64encode(zlib.compress(raw)).decode()
    result = audit_receipt(rid,digest,metadata)
    assert result["state"] == "BLOCKED"
    assert result["findings"] == ["INVALID_NOMINAL_OHLC"]


def test_decompression_bomb_and_invalid_base64_fail_closed():
    rid,digest,metadata,_ = receipt()
    metadata["normalized_bars_zlib_base64"] = base64.b64encode(zlib.compress(b"z"*2_000_100)).decode()
    assert audit_receipt(rid,digest,metadata)["state"] == "BLOCKED"
    metadata["normalized_bars_zlib_base64"] = "not valid#"
    assert audit_receipt(rid,digest,metadata)["state"] == "BLOCKED"


def test_inconsistent_receipt_counts_are_held():
    rid,digest,metadata,_ = receipt()
    metadata["completed_sessions"] = 129
    assert audit_receipt(rid,digest,metadata)["findings"] == ["BAR_COUNT_MISMATCH"]
