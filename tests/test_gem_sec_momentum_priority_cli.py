"""Read-only current-member momentum queue safety checks (synthetic only)."""
import base64
import csv
from hashlib import sha256
from io import StringIO
import zlib

import pytest

from scripts.gem_sec_momentum_priority_cli import _members, read_only_run

SIGNAL="2026-09-30"


def membership():
    stream = StringIO()
    writer = csv.DictWriter(stream,fieldnames=["Symbol","CIK"])
    writer.writeheader()
    for i in range(500):
        writer.writerow({"Symbol":f"X{i:03d}","CIK":str(i+1)})
    raw=stream.getvalue().encode()
    digest=sha256(raw).hexdigest()
    return digest, {"source_raw_zlib_base64":
            base64.b64encode(zlib.compress(raw)).decode()}


def test_membership_integrity_and_bounded_input():
    digest, metadata=membership()
    assert len(_members(digest,metadata))==500
    with pytest.raises(ValueError,match="hash"):
        _members("0"*64,metadata)


def test_reject_write_connection_or_unbounded_request_before_sql():
    with pytest.raises(ValueError,match="read role"):
        read_only_run(signal_day=SIGNAL,
            dsn="postgresql://gem_source_ingest_limited:secret@localhost/gem_forward")
    with pytest.raises(ValueError,match="bounded"):
        read_only_run(signal_day=SIGNAL,limit=100,
            dsn="postgresql://gem_web_readonly:secret@localhost/gem_forward")


def test_read_only_batch_returns_price_repair_holds_for_missing_prices(monkeypatch):
    from types import SimpleNamespace
    digest, meta=membership()
    calls=[]
    class Cur:
        def __enter__(self): return self
        def __exit__(self,*args): return False
        def execute(self, sql, params=None):
            calls.append((sql,params))
            if "SECONDARY_GITHUB_SP500" in sql:
                self.rows=[(digest,meta)]
            elif "DISTINCT ON" in sql:
                self.rows=[]
            else:
                self.rows=[]
        def fetchone(self): return self.rows[0] if self.rows else None
        def fetchall(self): return self.rows
    class Conn:
        def __enter__(self): return self
        def __exit__(self,*args): return False
        def cursor(self): return Cur()
    import psycopg
    monkeypatch.setattr(psycopg,"connect",lambda *args,**kw: Conn())
    report=read_only_run(signal_day=SIGNAL,limit=2,
        dsn="postgresql://gem_web_readonly:secret@localhost/gem_forward")
    assert report["universe_count"]==500
    assert report["evaluated"]==2
    assert report["counts"]=={
        "SEC_REVIEW_FIRST":0,
        "PRICE_REPAIR_FIRST":2,
        "DEFER_SEC_PENDING_PRICE_QA":0}
    assert report["excluded_as_proven_negative_momentum"]==0
    assert report["trade_authorized"] is False
    assert report["source_verified"] is False
    assert calls[0][0]=="SET TRANSACTION READ ONLY"
    assert all(sql.lstrip().startswith(("SELECT","SET")) for sql,_ in calls)
