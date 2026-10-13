"""Momentum-first targeted SEC reviewer: no unrelated original documents opened."""
import pytest

from scripts import gem_sec_momentum_parity_cli as runner


def test_reject_unbounded_or_untrusted_ciks_before_query():
    class Conn:
        def cursor(self):
            raise AssertionError("must validate CIKs before opening cursor")
    with pytest.raises(ValueError):
        runner.read_priority_receipts(Conn(),["NOT-A-CIK"])
    with pytest.raises(ValueError):
        runner.read_priority_receipts(Conn(),[str(i).zfill(10) for i in range(26)])


def test_prioritized_sec_selection_queries_only_requested_issuer():
    trace=[]
    class Cur:
        def __enter__(self): return self
        def __exit__(self,*args): return False
        def execute(self,sql,params=None):
            trace.append((sql,params))
            self.result = [
                ("SEC_ZIP_SUBMISSIONS","https://example.invalid",
                 "a"*64,{},"CIK0000000001.json"),
                ("SEC_ZIP_COMPANYFACTS","https://example.invalid",
                 "b"*64,{},"CIK0000000001.json"),
            ]
        def fetchall(self): return self.result
    class Conn:
        def cursor(self): return Cur()
    selected=runner.read_priority_receipts(Conn(),["0000000001","0000000002"])
    assert len(selected)==2
    assert set(selected[0][1])=={"submissions","companyfacts"}
    assert selected[1][1]=={}
    assert len(trace)==1
    assert trace[0][0].lstrip().startswith("SELECT")
    assert trace[0][1][-1]==["CIK0000000001.json","CIK0000000002.json"]


def test_end_to_end_only_positive_and_shared_cik_is_fetched_once(monkeypatch):
    from types import SimpleNamespace
    import psycopg
    seen=[]
    report={"rows":[
        {"ticker":"A", "cik":"0000000001","priority":"SEC_REVIEW_FIRST",
         "r63_preliminary":.2},
        {"ticker":"AA", "cik":"0000000001","priority":"SEC_REVIEW_FIRST",
         "r63_preliminary":.1},
        {"ticker":"B", "cik":"0000000002","priority":"DEFER_SEC_PENDING_PRICE_QA",
         "r63_preliminary":-.1},
        {"ticker":"C", "cik":"0000000003","priority":"PRICE_REPAIR_FIRST",
         "r63_preliminary":None}],
        "universe_count":500,"evaluated":500,"report_sha256":"a"*64,
        "counts":{"SEC_REVIEW_FIRST":2,"PRICE_REPAIR_FIRST":1,
                  "DEFER_SEC_PENDING_PRICE_QA":1}}
    monkeypatch.setattr(runner,"scan_prices",lambda **_:report)
    class Cur:
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def execute(self,sql,params=None):
            seen.append((sql,params))
            if "DISTINCT ON" in sql:
                self.result=[
                    ("SEC_ZIP_SUBMISSIONS","fake","a"*64,{},"CIK0000000001.json"),
                    ("SEC_ZIP_COMPANYFACTS","fake","b"*64,{},"CIK0000000001.json"),
                ]
            else: self.result=[]
        def fetchall(self):return self.result
    class Conn:
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def cursor(self):return Cur()
    monkeypatch.setattr(psycopg,"connect",lambda *args,**kw:Conn())
    audited=[]
    def diagnostic(sub,facts,cik,session):
        audited.append((cik,session))
        return {"status":"MATCHED_DIAGNOSTIC_NOT_CERTIFIED",
                "certified":False}
    monkeypatch.setattr(runner,"diagnose_receipts",diagnostic)
    out=runner.read_only_priority_parity(
        signal_day="2026-09-30",limit=25,
        dsn="postgresql://gem_web_readonly:test@localhost/gem_forward")
    assert out["sec_diagnostic_count"]==2
    assert len(audited)==2
    assert all(cik=="0000000001" for cik,_ in audited)
    assert out["price_repair_competitors_not_cleared"]==1
    assert out["deferred_negative_competitors_not_certified"]==1
    assert out["trading_authorized"] is False
    assert out["final_exclusions_certified"]==0
    sqlselect=[(sql,args) for sql,args in seen if "DISTINCT ON" in sql]
    assert len(sqlselect)==1
    assert sqlselect[0][1][-1]==["CIK0000000001.json"]
    assert all(sql.lstrip().startswith(("SET","SELECT")) for sql,args in seen)
