"""Offline safety tests for GEM SEC parity batch reader."""
import pytest

from scripts.gem_sec_frozen_parity_cli import read_pairs, read_only_run


class Cursor:
    def __init__(self):
        self.calls=[]
        self.rows=[]
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        assert sql.lstrip().startswith("SELECT ")
        if "GROUP BY" in sql:
            self.rows=[("CIK0001000000.json",)]
        else:
            self.rows=[
                ("SEC_ZIP_SUBMISSIONS", "https://example.invalid/sub",
                 "a"*64, {"zip_member_name":"CIK0001000000.json"},
                 "CIK0001000000.json"),
                ("SEC_ZIP_COMPANYFACTS", "https://example.invalid/fact",
                 "b"*64, {"zip_member_name":"CIK0001000000.json"},
                 "CIK0001000000.json"),
            ]
    def fetchall(self):
        return self.rows


class Conn:
    def __init__(self):
        self.cur=Cursor()
    def cursor(self):
        return self.cur


def test_bounded_reader_selects_original_paired_receipts_without_writes():
    conn=Conn()
    result=read_pairs(conn,limit=10,offset=0)
    assert len(result)==1
    cik, pair=result[0]
    assert cik=="0001000000"
    assert set(pair)=={"submissions","companyfacts"}
    assert all(sql.lstrip().startswith("SELECT") for sql,params in conn.cur.calls)
    assert len(conn.cur.calls)==2
    assert "DISTINCT ON" in conn.cur.calls[1][0]


@pytest.mark.parametrize("limit,offset", [(0,0),(26,0),(10,-1)])
def test_unbounded_requests_rejected_before_database_access(limit,offset):
    with pytest.raises(ValueError):
        read_pairs(Conn(),limit=limit,offset=offset)


def test_ingestion_or_other_database_role_refused():
    with pytest.raises(ValueError,match="read-only"):
        read_only_run(signal_day="2026-09-30",
                      dsn="postgresql://gem_source_ingest_limited:secret@localhost/gem_forward")
