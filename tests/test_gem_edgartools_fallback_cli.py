"""No-network SEC XBRL fallback operator gating and targeted review tests."""
from types import SimpleNamespace
import sys

import pytest

CIK = "0001000000"
from scripts import gem_sec_edgartools_fallback_cli as runner


def test_only_momentum_positive_SEC_HOLD_tickers_get_filing_plans(monkeypatch):
    watched=[]
    def queue(**kw):
        assert kw["signal_day"]=="2026-09-30"
        return {
            "scope":"PROVISIONAL_MOMENTUM_FIRST_SEC_DIAGNOSTIC_NOT_CERTIFICATION",
            "trading_authorized":False,
            "final_exclusions_certified":0,
            "price_repair_competitors_not_cleared":231,
            "deferred_negative_competitors_not_certified":100,
            "issuer_reports":[
                {"ticker":"AAA","cik":CIK,"r63_preliminary":.2,"status":"HOLD"},
                {"ticker":"BBB","cik":"0002000000","r63_preliminary":.1,
                 "status":"MATCHED_DIAGNOSTIC_NOT_CERTIFIED"},
            ],
        }
    monkeypatch.setattr(runner,"read_only_priority_parity",queue)

    class Cur:
        def __enter__(self): return self
        def __exit__(self,*_):return False
        def execute(self,sql,params=None):
            watched.append(sql)
            assert sql.startswith("SET ")
    class Conn:
        def __enter__(self):return self
        def __exit__(self,*_):return False
        def cursor(self):return Cur()
    import psycopg
    monkeypatch.setattr(psycopg,"connect",lambda *a,**kw:Conn())
    def original_lookup(conn,ciks):
        assert ciks==[CIK]
        return [(CIK,{"submissions":{"provider":"SEC_ZIP_SUBMISSIONS"}})]
    monkeypatch.setattr(runner,"read_priority_receipts",original_lookup)
    monkeypatch.setattr(runner,"plan_filing_exceptions",
        lambda receipt,cik,session:{
            "status":"PLANNED_UNCERTIFIED",
            "filings":[{"cik":cik,"accession":f"{cik}-26-000001",
                        "form":"10-Q","filed":"2026-08-01",
                        "report_period":"2026-06-30"}]})
    report=runner.plan_exception_batch(
        signal_day="2026-09-30",limit=5,
        dsn="postgresql://gem_web_readonly:x@localhost/gem_forward")
    assert len(report["planned"])==1
    assert report["planned"][0]["ticker"]=="AAA"
    assert report["planned"][0]["status"]=="PLANNED_UNCERTIFIED"
    assert report["unresolved_price_competitors"]==231
    assert report["unverified_negative_competitors"]==100
    assert report["trading_authorized"] is False
    assert all(sql.startswith("SET ") for sql in watched)


def test_fetch_is_disabled_without_explicit_opt_in(monkeypatch,tmp_path):
    monkeypatch.delenv("GEM_SEC_XBRL_FALLBACK_ENABLED",raising=False)
    monkeypatch.delenv("EDGAR_IDENTITY",raising=False)
    with pytest.raises(ValueError,match="opt-in"):
        runner.fetch_explicitly_approved(
            {"schema":"gem-sec-edgartools-exception-batch-v1",
             "trading_authorized":False,"planned":[]},outdir=str(tmp_path))


def test_explicit_fetch_writes_one_local_uncertified_artifact(monkeypatch,tmp_path):
    monkeypatch.setenv("GEM_SEC_XBRL_FALLBACK_ENABLED","yes")
    monkeypatch.setenv("EDGAR_IDENTITY","Organization contact@example.invalid")
    identities=[]
    monkeypatch.setitem(sys.modules,"edgar",SimpleNamespace(
        set_identity=identities.append))
    entry={"cik":CIK,"accession":f"{CIK}-26-000001",
           "form":"10-Q","filed":"2026-08-01",
           "report_period":"2026-06-30",
           "accepted_at":"2026-08-01T13:00:00"}
    batch={"schema":"gem-sec-edgartools-exception-batch-v1",
           "trading_authorized":False,
           "planned":[{"status":"PLANNED_UNCERTIFIED","filings":[entry]}]}
    def fake_extract(filing,*,filing_loader=None):
        assert filing==entry
        return {"cik":CIK,"accession":filing["accession"],
                "status":"EXTRACTED_FOR_INDEPENDENT_QA_ONLY",
                "certified":False}
    monkeypatch.setattr(runner,"fetch_filing_xbrl",fake_extract)
    report=runner.fetch_explicitly_approved(
        batch,max_filings=1,outdir=str(tmp_path),sleep_fn=lambda _:None)
    assert identities==["Organization contact@example.invalid"]
    assert report["attempted"]==1
    assert report["remaining_unfetched"]==0
    assert report["outcomes"][0]["status"]=="EXTRACTED_FOR_INDEPENDENT_QA_ONLY"
    assert len(list(tmp_path.iterdir()))==1
    assert report["source_certified"] is False
    assert report["trading_authorized"] is False
    # Same evidence cannot be overwritten by a repeated run.
    again=runner.fetch_explicitly_approved(
        batch,max_filings=1,outdir=str(tmp_path),sleep_fn=lambda _:None)
    assert again["outcomes"][0]["status"]=="HOLD_EXTRACTION_OR_STORAGE_FAILED"
    assert len(list(tmp_path.iterdir()))==1


def test_cannot_use_unbounded_batches_or_non_readonly_neon_role():
    with pytest.raises(ValueError):
        runner.plan_exception_batch(signal_day="2026-09-30",limit=100,
                                    dsn="postgresql://gem_web_readonly:x@localhost/db")
    with pytest.raises(ValueError,match="read-only"):
        runner.plan_exception_batch(signal_day="2026-09-30",limit=1,
                     dsn="postgresql://gem_source_ingest_limited:x@localhost/db")
