import copy
import csv
import io
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from threading import Lock

import pytest
from fastapi.testclient import TestClient

from app import full_scan as module
from app.analysis_engine import SCORING_VERSION, technicals
from app.db import SessionLocal, FullScanRun, FullScanResult
from app.full_scan import FullUniverseScan, compact_result, preflight, summarize, accumulate
from tests.test_score_band_experiment import observation

NOW = datetime(2026, 10, 5, 22, tzinfo=timezone.utc)


def payload(symbol="TEST", **kwargs):
    a = observation(**kwargs)
    a.update(symbol=symbol, asof=NOW.isoformat(), scoring_version=SCORING_VERSION,
             breakdown={"Fundamentals":18,"Catalyst":5,"Valuation":7},
             fundamentals={"_analyst_status":"available","trailingPE":25},
             data_sources={"price":{"quote_asof":"2026-10-05T20:00:00+00:00"}})
    return a


class Provider:
    def __init__(self, symbols, quotes=None):
        self.symbols, self.quotes = symbols, quotes or {}
    def us_equity_universe(self):
        return [{"symbol":s} for s in self.symbols]
    def chart(self, symbol, *args):
        if symbol == "ERROR": raise TimeoutError("do not expose a credential-bearing URL")
        price, volume = self.quotes.get(symbol, (100,200000))
        return {"price":price,"rows":[{"date":"2026-10-05","close":price,"volume":volume} for _ in range(252)],
                "meta":{"regularMarketTime":int(datetime(2026,10,5,20,tzinfo=timezone.utc).timestamp())}}
    def _rows_from_chart(self, chart):
        return chart["rows"],chart["price"],99,"USD","NMS"


def service(monkeypatch, symbols, quotes=None):
    monkeypatch.setattr(module, "now", lambda:NOW)
    provider = Provider(symbols, quotes)
    analyzed, persisted = [], []
    def analyze(symbol, **kwargs):
        analyzed.append((symbol,kwargs))
        return payload(symbol)
    radar = SimpleNamespace(provider=provider,market_open=lambda:False,
        _scan_lock=Lock(),analyze_symbol=analyze,persist=lambda full:persisted.append(full["symbol"]))
    scan = FullUniverseScan(radar)
    monkeypatch.setattr(scan,"_launch",lambda run_id:scan._run(run_id))
    return scan, analyzed, persisted


@pytest.mark.parametrize("score,analyst,target,expected",[
    (69.999,90,110,False),(70,74.999,110,False),(70,None,110,False),
    (70,75,103.999,False),(70,75,104,True),(70,75,110,True)])
def test_full_scan_uses_exact_shared_gates(score,analyst,target,expected):
    a=payload(score=score,analyst=analyst,target=target,stop=90)
    a["risk_reward"]=10; a["action"]="BUY"
    before=copy.deepcopy(a)
    r=compact_result(a)
    assert r["qualified"] is expected and a == before
    assert r["risk_reward"] == pytest.approx((target-100)/10)


def test_preflight_matches_scoring_liquidity_and_only_rejects_hard_floors():
    p=Provider(["TEST"])
    p.quotes["TEST"]=(5,2000000)
    q=preflight(p,"TEST","2026-10-05")
    assert q["status"] == "awaiting_analysis" # exact $5 and $10M included
    assert q["avg_dollar_volume_20"] == technicals(p.chart("TEST")["rows"],5)["avg_dollar_volume_20"]
    p.quotes["TEST"]=(4.999,2000000)
    assert preflight(p,"TEST","2026-10-05")["blocker"] == "price_or_currency_invalid"
    p.quotes["TEST"]=(10,999999)
    assert preflight(p,"TEST","2026-10-05")["blocker"] == "liquidity_below_10m"
    with pytest.raises(ValueError):preflight(p,"TEST","2026-10-06")


@pytest.mark.parametrize("started", [
    datetime(2026, 10, 6, 7, tzinfo=timezone.utc),
    datetime(2026, 10, 10, 12, tzinfo=timezone.utc),
])
def test_new_after_hours_audit_uses_observed_market_session_not_calendar_today(monkeypatch, started):
    scan, analyzed, _ = service(monkeypatch, ["A"])
    monkeypatch.setattr(module, "now", lambda: started)
    result = scan.start()
    assert result["session_date"] == "2026-10-05"
    assert result["processed"] == 1 and result["status_counts"]["scored"] == 1
    assert result["status_counts"].get("error", 0) == 0 and analyzed[0][0] == "A"


@pytest.mark.parametrize("stamp", [None, float("nan"), 0, NOW.timestamp() + 3600])
def test_unavailable_stale_or_future_index_session_cannot_start_audit(monkeypatch, stamp):
    scan, analyzed, _ = service(monkeypatch, ["A"])
    monkeypatch.setattr(scan.radar.provider, "chart", lambda *args: {"meta": {"regularMarketTime": stamp}})
    assert scan.start()["status"] == "error" and not analyzed
    with SessionLocal() as db:
        assert db.query(FullScanRun).count() == 0
        assert db.query(FullScanResult).count() == 0


def test_complete_universe_has_no_top_n_deep_cutoff_and_errors_are_separate(monkeypatch):
    symbols=[f"S{i}" for i in range(70)]+["LOW","ILLIQUID","ERROR"]
    scan, analyzed, persisted=service(monkeypatch,symbols,{"LOW":(4,1e7),"ILLIQUID":(100,99999)})
    result=scan.start()
    assert result["status"] == "completed_with_data_gaps"
    assert result["universe_size"] == result["processed"] == 73
    assert len(analyzed) == len(persisted) == result["qualified_count"] == 70
    assert result["status_counts"] == {"scored":70,"excluded":2,"error":1}
    assert result["execution_enabled"] is False
    assert all(kwargs == {"persist":False,"contextual_ai":False} for _,kwargs in analyzed)
    rows=list(csv.DictReader(io.StringIO(scan.results_csv())))
    assert len(rows) == 73 and len({r["symbol"] for r in rows}) == 73
    assert next(r for r in rows if r["symbol"]=="ERROR")["error"] == "TimeoutError"
    assert "credential" not in scan.results_csv()


def test_resume_does_not_repeat_completed_symbols_and_survives_new_worker(monkeypatch):
    scan, _, _=service(monkeypatch,["A","B","C"])
    monkeypatch.setattr(scan,"_launch",lambda run_id:None)
    result=scan.start();run_id=result["run_id"]
    scan._claim(run_id)
    scan._record(run_id,[compact_result(payload("A"))],"prefilter")
    with SessionLocal() as db:
        run=db.get(FullScanRun,"latest");run.lease_until=NOW-timedelta(seconds=1);db.commit()
    resumed, analyzed, _=service(monkeypatch,["A","B","C"])
    result=resumed.start()
    assert result["run_id"] == run_id and result["processed"] == 3
    assert [s for s,_ in analyzed] == ["B","C"]
    assert result["summary"]["counts"]["scored"] == 3


def test_other_worker_cannot_take_unexpired_lease(monkeypatch):
    scan,_,_=service(monkeypatch,["A"])
    monkeypatch.setattr(scan,"_launch",lambda run_id:None)
    run_id=scan.start()["run_id"]
    assert scan._claim(run_id)
    second,_,_=service(monkeypatch,["A"])
    assert second._claim(run_id) is None


def test_scoring_version_change_stops_audit_instead_of_mixing_results(monkeypatch):
    scan,_,_=service(monkeypatch,["A"])
    monkeypatch.setattr(scan,"_launch",lambda run_id:None)
    run_id=scan.start()["run_id"]
    with SessionLocal() as db:
        r=db.get(FullScanRun,"latest");r.scoring_version="old";db.commit()
    assert scan._claim(run_id) is None
    assert scan.status()["status"] == "scoring_version_changed"


def test_resume_after_model_change_starts_clean_current_version_run(monkeypatch):
    scan, _, _ = service(monkeypatch, ["A", "B"])
    monkeypatch.setattr(scan, "_launch", lambda run_id:None)
    old_id = scan.start()["run_id"]
    with SessionLocal() as db:
        run = db.get(FullScanRun, "latest")
        run.scoring_version = "old"
        run.status = "analysis"
        db.commit()

    fresh, analyzed, _ = service(monkeypatch, ["A", "B"])
    result = fresh.resume()

    assert result["run_id"] != old_id
    assert result["scoring_version"] == SCORING_VERSION
    assert result["processed"] == 2
    assert [s for s, _ in analyzed] == ["A", "B"]


def test_start_after_model_change_creates_clean_current_version_run(monkeypatch):
    scan, _, _ = service(monkeypatch, ["A", "B"])
    monkeypatch.setattr(scan, "_launch", lambda run_id:None)
    old_id = scan.start()["run_id"]
    scan._claim(old_id)
    scan._record(old_id, [compact_result(payload("A"))], "analysis")
    with SessionLocal() as db:
        r = db.get(FullScanRun, "latest"); r.scoring_version = "old"; db.commit()
    fresh, analyzed, _ = service(monkeypatch, ["A", "B"])
    result = fresh.start()
    assert result["run_id"] != old_id and result["scoring_version"] == SCORING_VERSION
    assert [s for s, _ in analyzed] == ["A", "B"]
    assert result["summary"]["counts"]["scored"] == 2
    with SessionLocal() as db:
        assert db.query(FullScanResult).filter_by(run_id=old_id, status="scored").count() == 1


def test_independent_gate_counts_and_temporary_gaps_are_not_qualification():
    a=payload(score=69.9); b=payload(analyst=None)
    b["fundamentals"]["_analyst_status"]="unavailable (request budget)"
    rows=[compact_result(a),compact_result(b),compact_result(payload())]
    s=summarize(rows)
    assert s["independent_gate_pass_counts"]["deterministic_70"] == 2
    assert s["independent_gate_pass_counts"]["analyst_75"] == 2
    assert s["independent_gate_pass_counts"]["qualified"] == 1
    assert s["missing_data"]["analyst_score"] == 1
    assert s["missing_data"]["transient_data_gap"] == 1
    accumulate(s,rows[1],-1);accumulate(s,compact_result(payload()),1)
    assert s["counts"]["scored"] == 3 and s["missing_data"]["analyst_score"] == 0
    assert s["mean_score_components"]["Fundamentals"] == 18


def test_fundamental_and_analyst_pass_does_not_imply_deterministic_pass():
    row=compact_result(payload(score=61.8))
    counts=summarize([row])["independent_gate_pass_counts"]
    assert counts["fundamentals_14"] == counts["analyst_75"] == counts["fundamentals_and_analyst"] == 1
    assert counts["deterministic_70"] == 0
    assert counts["qualified"] == 0


@pytest.mark.parametrize("old_version", [
    "2026-10-06-score-evidence-integrity-v19",
    "2026-10-06-sec-filing-coverage-v20",
])
def test_prior_version_upgrade_reuses_quick_checks_but_never_old_scores(monkeypatch, old_version):
    scan,_,_=service(monkeypatch,["A","LOW","ERROR"],{"LOW":(4,1e7)})
    old=scan.start();old_id=old["run_id"]
    with SessionLocal() as db:
        run=db.get(FullScanRun,"latest");run.scoring_version=old_version;db.commit()
        row=db.query(FullScanResult).filter_by(run_id=old_id,symbol="A").one()
        saved=json.loads(row.payload_json);saved["avg_dollar_volume_20"]=20_000_000
        row.payload_json=json.dumps(saved);db.commit()
    fresh,analyzed,_=service(monkeypatch,["A","LOW","ERROR"])
    real_chart=fresh.radar.provider.chart
    checked=[]
    def chart(symbol,*args):
        checked.append(symbol)
        return real_chart(symbol,*args)
    fresh.radar.provider.chart=chart
    result=fresh.start()
    assert result["run_id"] != old_id and result["status_counts"] == {"scored":1,"excluded":1,"error":1}
    assert "LOW" not in checked and "A" not in checked
    assert [s for s,_ in analyzed] == ["A"]  # old score must be recalculated


def test_changed_session_does_not_reuse_previous_quick_checks(monkeypatch):
    scan,_,_=service(monkeypatch,["A"]);scan.start()
    with SessionLocal() as db:
        run=db.get(FullScanRun,"latest");run.scoring_version="2026-10-06-score-evidence-integrity-v19"
        run.session_date="2026-10-02";db.commit()
        assert scan._reusable_prechecks(db,run,"2026-10-05") == {}


def test_does_not_start_during_open_market_or_mutate_paper_ledger(monkeypatch):
    from app.db import ScoreBandExperiment, PaperAccount, PaperPosition, PaperTrade
    scan,analyzed,_=service(monkeypatch,["A"])
    scan.radar.market_open=lambda:True
    assert scan.start()["status"] == "market_open" and not analyzed
    scan.radar.market_open=lambda:False;scan.start()
    with SessionLocal() as db:
        assert all(db.query(model).count()==0 for model in [ScoreBandExperiment,PaperAccount,PaperPosition,PaperTrade])


def test_normal_after_hours_cycle_yields_but_open_market_keeps_running(monkeypatch):
    from app.scanner import RadarService
    radar=RadarService(provider=Provider(["A"]))
    radar.full_universe_scan=SimpleNamespace(active=lambda:True)
    monkeypatch.setattr(radar,"market_open",lambda:False)
    monkeypatch.setattr(radar,"stale_scoring_symbols",lambda **kw:pytest.fail("should yield provider budget"))
    assert radar._scan_once_impl()["status"] == "full_universe_audit_running"


def test_api_progress_page_and_export(monkeypatch):
    from app.main import app
    import app.main as main
    scan,_,_=service(monkeypatch,["A"])
    monkeypatch.setattr(main,"full_scan",scan)
    client=TestClient(app)
    assert client.post('/api/full-scan').json()["qualified_count"] == 1
    assert client.get('/api/full-scan').json()["gates"] == {"deterministic":70,"analyst":75,"risk_reward":.4}
    assert "A,scored," in client.get('/api/full-scan/results.csv').text
    page=client.get('/scan-audit')
    assert page.status_code == 200 and "No top-candidate quota" in page.text


def test_cache_reuse_requires_post_close_current_version_and_nontransient_inputs(monkeypatch):
    from app.db import RadarCandidate
    scan,_,_=service(monkeypatch,["TEST"])
    def store(a):
        with SessionLocal() as db:
            row=db.query(RadarCandidate).filter_by(symbol="TEST").first() or RadarCandidate(symbol="TEST")
            row.current_json=json.dumps(a);db.add(row);db.commit()
    a=payload();store(a)
    assert scan._cached("TEST","2026-10-05")["source"] == "cached_post_close"
    a["asof"]="2026-10-05T19:59:00+00:00";store(a)
    assert scan._cached("TEST","2026-10-05") is None
    a=payload();a["scoring_version"]="old";store(a)
    assert scan._cached("TEST","2026-10-05") is None
    a=payload();a["fundamentals"]["trailingPE"]=None
    a["fundamentals"]["_valuation_status"]="unavailable (enrichment budget)";store(a)
    assert scan._cached("TEST","2026-10-05") is None
    a["fundamentals"]["trailingPE"]=25
    a["fundamentals"]["_valuation_status"]="available (cached validated evidence; refresh unavailable (enrichment budget))";store(a)
    assert scan._cached("TEST","2026-10-05") is not None


def test_completed_resume_does_not_duplicate_score_aggregates(monkeypatch):
    scan,_,_=service(monkeypatch,["A"])
    monkeypatch.setattr(scan,"_launch",lambda run_id:None)
    run_id=scan.start()["run_id"];scan._claim(run_id)
    scan._record(run_id,[compact_result(payload("A"))],"analysis")
    scan._record(run_id,[compact_result(payload("A",score=69))],"analysis")
    d=scan.status()
    assert d["qualified_count"] == 0 and d["summary"]["counts"]["scored"] == 1
    assert d["summary"]["independent_gate_pass_counts"]["qualified"] == 0


def test_export_exposes_components_and_unavailable_inputs_without_changing_gates(monkeypatch):
    scan, _, _ = service(monkeypatch, ["A"])
    a = payload("A")
    a["fundamentals"].update(sector="Financial Services", revenueGrowth=.064,
                             earningsGrowth=.07, returnOnEquity=.34, debtToEquity=172.3)
    a["fundamental_confidence"] = "medium"
    a["fundamental_reasons"] = ["Revenue growth 6.4% → 2/4"]
    scan.radar.analyze_symbol = lambda *args, **kwargs:a
    result = scan.start()
    row = next(csv.DictReader(io.StringIO(scan.results_csv())))
    assert float(row["deterministic_score"]) == a["deterministic_score"]
    assert float(row["fundamentals_points"]) == 18
    assert float(row["catalyst_points"]) == 5 and float(row["valuation_points"]) == 7
    assert row["fundamental_missing_inputs"] == "grossMargins; operatingMargins"
    assert row["fundamental_confidence"] == "medium"
    assert "no separate financial-services model" in row["fundamental_model_limitation"]
    assert float(row["revenue_growth_pct"]) == pytest.approx(6.4)
    assert float(row["roe_pct"]) == pytest.approx(34)
    assert float(row["debt_to_equity_pct"]) == pytest.approx(172.3)
    assert row["scoring_version"] == SCORING_VERSION
    assert result["summary"]["missing_data"]["incomplete_fundamental_inputs"] == 1
    assert result["summary"]["missing_data"]["financial_sector_model_limit"] == 1
    scan._claim(result["run_id"])
    scan._record(result["run_id"], [compact_result(payload("A"))], "analysis")
    assert scan.status()["summary"]["missing_data"]["financial_sector_model_limit"] == 0
