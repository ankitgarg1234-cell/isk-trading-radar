import copy
import json
import math
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.short_horizon import VERSION, HORIZONS, build_forecast, rolling_validation, _series, _distribution
from app.analysis_engine import score_bundle
from app.scanner import _compact_payload
from app.score_band_capture import compact_observation
from app.score_band_experiment import new_state, advance, entry_check
from tests.helpers import bundle as scoring_bundle
from tests.test_score_band_experiment import observation


def bundle(drift=.001, count=400):
    day, price, rows = date(2025, 1, 2), 100., []
    while len(rows) < count:
        if day.weekday() < 5:
            price *= math.exp(drift + .012 * math.sin(len(rows) * 1.7))
            rows.append({"date": day.isoformat(), "close": price})
        day += timedelta(days=1)
    return {"symbol": "TEST", "price": price, "asof": rows[-1]["date"] + "T21:00:00+00:00",
            "history": rows, "sector_benchmark": {"symbol": "XLK", "history": copy.deepcopy(rows)},
            "data_sources": {"price": {"source": "test history"}}}


def forecast(b=None, lane="CORE_QUALITY"):
    b = b or bundle()
    return build_forecast(b, {"lane": lane, "levels": {"stop": b["price"] * .9}})


def test_five_calendar_horizons_ordered_scenarios_and_fixed_core_default():
    f = forecast()
    assert f["status"] == "available" and f["execution_enabled"] is False
    assert f["horizon_unit"] == "calendar_days"
    assert tuple(r["days"] for r in f["rows"]) == HORIZONS
    assert [r["days"] for r in f["rows"] if r["default"]] == [30]
    for row in f["rows"]:
        assert row["down_price"] <= row["base_price"] <= row["up_price"]
        assert (date.fromisoformat(row["forecast_date"]) - date.fromisoformat(f["price_asof"][:10])).days == row["days"]
        assert row["risk_reward"] == pytest.approx((row["base_price"]-f["price"])/(f["price"]-row["stop"]),abs=.002)
    json.dumps(f, allow_nan=False)


def test_negative_and_flat_prices_do_not_receive_automatic_positive_targets():
    falling = forecast(bundle(drift=-.004))
    assert all(r["base_return_pct"] < 0 and r["expected_return_pct"] < 0 for r in falling["rows"])
    b = bundle()
    for row in b["history"]:
        row["close"] = 100
    b.update(price=100, sector_benchmark={})
    flat = forecast(b)
    assert all(r["base_price"] == 100 and r["expected_return_pct"] == 0 for r in flat["rows"])


def test_no_future_stock_or_sector_rows_affect_current_forecasts():
    b = bundle()
    expected = forecast(b)
    future = {"date": (date.fromisoformat(b["asof"][:10])+timedelta(days=1)).isoformat(), "close": 10**9}
    b["history"].append(future)
    b["sector_benchmark"]["history"].append(future)
    assert forecast(b) == expected


def test_partial_current_session_is_excluded_and_exchange_timestamp_wins():
    b = bundle()
    last = b["history"][-1]["date"]
    b["data_sources"]["price"]["quote_asof"] = last + "T15:00:00-04:00"
    b["asof"] = last + "T23:00:00+00:00"
    before = forecast(b)
    b["history"][-1]["close"] = 9999
    assert forecast(b) == before
    assert before["history_asof"] < last


def test_historical_features_are_prefix_only_even_with_full_sector_history():
    b = bundle()
    series, _ = _series(b["history"],date.max)
    prefix = series[:180]
    assert _distribution(prefix, series, 20) == _distribution(prefix, prefix, 20)
    changed = [(d, p*1000) if d > prefix[-1][0] else (d,p) for d,p in series]
    assert _distribution(prefix, changed, 20) == _distribution(prefix, prefix, 20)


def test_validation_reports_overlap_and_fails_a_worse_model_against_trend():
    b = bundle(drift=.002,count=700)
    series, _ = _series(b["history"],date.max)
    v = rolling_validation(series, [], 15)
    assert v["folds"] > v["independent_windows"] >= 20
    assert v["independent_metrics"]["model_mae_pct_points"] > v["independent_metrics"]["simple_trend_mae_pct_points"]
    assert v["status"] == "benchmark_checks_failed"
    assert v["last_outcome"] <= series[-1][0].isoformat()


def test_one_year_is_not_claimed_to_be_20_independent_60_day_tests():
    f = forecast(bundle(count=251))
    last = f["rows"][-1]["validation"]
    assert last["folds"] > last["independent_windows"]
    assert last["independent_windows"] < 20
    assert last["status"] == "insufficient_independent_windows"


@pytest.mark.parametrize("fault", ["short", "conflict", "no_time", "bad_price", "stale", "gap"])
def test_missing_invalid_or_sparse_inputs_are_explicitly_unavailable(fault):
    b = bundle()
    if fault == "short": b["history"] = b["history"][-50:]
    if fault == "conflict": b["history"].append({"date":b["history"][10]["date"],"close":1})
    if fault == "no_time": b["asof"] = b["asof"][:19]
    if fault == "bad_price": b["price"] = float("nan")
    if fault == "stale": b["history"] = b["history"][:-10]
    if fault == "gap": del b["history"][180:200]
    f = forecast(b)
    assert f["status"] == "unavailable" and f["rows"] == [] and f["reason"]
    json.dumps(f,allow_nan=False)


def test_missing_sector_does_not_invent_context():
    b = bundle(); b.pop("sector_benchmark")
    f = forecast(b)
    assert f["status"] == "available" and "unavailable" in f["sector_status"]
    assert not any(r["sector_used"] for r in f["rows"])


def test_explosive_default_and_existing_holding_limit_are_preserved():
    f = forecast(lane="EXPLOSIVE")
    assert [r["days"] for r in f["rows"] if r["default"]] == [15]
    assert f["rows"][0]["within_lane_window"] is True
    assert f["rows"][-1]["within_lane_window"] is False


def test_research_cannot_change_deterministic_score_levels_or_entry_gate(monkeypatch):
    b = scoring_bundle()
    before = score_bundle(b)
    monkeypatch.setattr("app.analysis_engine.build_forecast",lambda *args: {"version":VERSION,"base_price":10**9,"execution_enabled":True})
    after = score_bundle(b)
    for key in ("deterministic_score","breakdown","levels","target_plan","holding_horizon","risk_reward","lane","lane_qualified"):
        assert after[key] == before[key]
    assert entry_check(after) == entry_check(before)


def test_predictions_are_archived_but_do_not_change_paper_fills_or_trial():
    a = observation(stop=99)
    b = copy.deepcopy(a)
    b["short_horizon_forecast"] = forecast()
    assert _compact_payload(b)["short_horizon_forecast"] == b["short_horizon_forecast"]
    assert compact_observation(b)["short_horizon_forecast"] == b["short_horizon_forecast"]
    state_a, state_b = new_state(),new_state()
    for minute in (1,2):
        obs_a = observation(minute=minute,stop=99)
        obs_b = {**copy.deepcopy(obs_a),"short_horizon_forecast":b["short_horizon_forecast"]}
        advance(state_a,[obs_a],obs_a["asof"],True)
        advance(state_b,[obs_b],obs_b["asof"],True)
    assert state_a["variants"] == state_b["variants"]
    assert state_a.get("trial") == state_b.get("trial")


def test_forecast_panel_and_independent_validation_render(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app, radar
    b = scoring_bundle()
    data = {**b,**score_bundle(b),"short_horizon_forecast":forecast(),"position":None,
            "action":"WATCH","action_reason":"Waiting","ai_score":75,"adjustments":[],"reasons":[],"risks":[],"sensitivity":[]}
    monkeypatch.setattr(radar,"analyze_symbol",lambda *args,**kwargs:copy.deepcopy(data))
    response = TestClient(app).get("/analysis/TEST")
    assert response.status_code == 200
    assert "15, 25, 30, 45 and 60 calendar days" in response.text
    assert "non-overlapping" in response.text and "No-change error" in response.text
    assert "Evaluation only" in response.text and "Current strategy target" in response.text
    api = TestClient(app).get("/api/analysis/TEST").json()
    assert api["short_horizon_forecast"]["version"] == VERSION


def test_real_capture_replay_is_reproducible_and_does_not_claim_validation():
    data = json.loads((Path(__file__).parent/"fixtures/short_horizon_prices_2026_10_05.json").read_text())
    for b in data["securities"]:
        first = build_forecast(b,b["analysis"])
        assert first == build_forecast(copy.deepcopy(b),copy.deepcopy(b["analysis"]))
        assert first["status"] == "available"
        assert all(r["validation"]["status"] == "insufficient_independent_windows" for r in first["rows"])


def test_optional_model_failure_cannot_break_scoring(monkeypatch):
    b = scoring_bundle()
    valid = bundle()
    b.update(history=valid["history"],asof=valid["asof"],price=valid["price"],sector_benchmark=valid["sector_benchmark"])
    before = score_bundle(b)
    def fail(*args,**kwargs):
        raise ArithmeticError()
    monkeypatch.setattr("app.short_horizon._distribution",fail)
    after = score_bundle(b)
    assert after["short_horizon_forecast"]["status"] == "unavailable"
    assert after["deterministic_score"] == before["deterministic_score"]
    assert after["levels"] == before["levels"]


def test_preexisting_scoring_cache_is_refreshed_for_new_forecasts(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app, radar
    from app.db import SessionLocal, RadarCandidate
    old = {**scoring_bundle(),**score_bundle(scoring_bundle())}
    old.pop("short_horizon_forecast")
    with SessionLocal() as db:
        db.add(RadarCandidate(symbol="TEST",score=old["deterministic_score"],current_json=json.dumps(old)))
        db.commit()
    calls=[]
    def refresh(*args,**kwargs):
        calls.append(args)
        return {**old,"short_horizon_forecast":forecast()}
    monkeypatch.setattr(radar,"analyze_symbol",refresh)
    result=TestClient(app).get("/api/analysis/TEST").json()
    assert calls and result["short_horizon_forecast"]["version"] == VERSION
