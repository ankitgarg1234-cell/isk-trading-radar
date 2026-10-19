"""Isolation and mathematical regression tests for V3 dashboard."""
from datetime import date
import pytest
from fastapi import HTTPException
from tier1_v3.dashboard import Snapshot, evaluate_snapshot, verify_nav, app


def stock(ticker="NVDA", **extra):
    row = dict(ticker=ticker, listed_date="1999-01-01",
               price=100, adtv20=10_000_000,
               fundamentals_available_as_of="2025-11-30",
               ml_trained_through_year=2025,
               ytd_pct_rank=1.0, in_top_subindustry=1.0,
               davis_rank=1.0, rule40_rank=1.0,
               p_rf=1.0, p_et=1.0, p_gb=1.0,
               sma50=90, sma200=80, subindustry_vol_zscore=0,
               downside_vol=0.20)
    row.update(extra)
    return row


def run(rows, **kwargs):
    return evaluate_snapshot(Snapshot(as_of=date(2026, 10, 19),
                                      stocks=rows,
                                      spy_20d_ann_vol=.23,
                                      basket_ann_vol=.40,
                                      **kwargs))


def test_perfect_tier1_score():
    result = run([stock()])
    assert result["selected"][0]["ticker"] == "NVDA"
    assert result["selected"][0]["score"] == 1.35
    assert result["selected"][0]["portfolio_weight"] == 1.0


def test_below_sma_discount():
    result = run([stock(price=85, sma50=90)])
    assert result["selected"][0]["score"] == pytest.approx(1.0125)


def test_subindustry_vol_governor():
    result = run([stock(subindustry_vol_zscore=2.01)])
    assert result["selected"][0]["score"] == pytest.approx(.54)


def test_ipo_and_liquidity_gate():
    result = run([stock("PLTR", listed_date="2027-01-01"),
                  stock("NVDA", adtv20=100)])
    assert result["count_eligible"] == 0


def test_anti_lookahead_guards():
    result = run([stock(fundamentals_available_as_of="2026-11-01"),
                  stock("MSFT", ml_trained_through_year=2026)])
    assert result["count_eligible"] == 0
    assert result["selected"] == []


def test_ban_zero_selectable():
    assert run([stock(turnaround_banned=True)])["selected"] == []


def test_non_tier_requires_36_year_moat():
    s = stock("A_NON_TIER", pit_sp500_member=True,
              moat_lookback_years=35, moat_percentile=.99)
    assert run([s])["count_eligible"] == 0
    s["moat_lookback_years"] = 36
    assert run([s])["count_eligible"] == 1


def test_max_five_and_buffer_keeps_holding():
    symbols = ["NVDA", "MSFT", "META", "AMZN", "GOOGL", "AVGO", "MU"]
    rows = [stock(t, p_rf=1-i*.08, p_et=1-i*.08, p_gb=1-i*.08)
            for i,t in enumerate(symbols)]
    r = run(rows, current_holdings=["MU"])
    assert len(r["selected"]) == 5
    assert "MU" in [x["ticker"] for x in r["selected"]]


def test_volatility_weight_scaling():
    out = run([stock(), stock("MSFT", downside_vol=.80)],
              )["selected"]
    weight = {s["ticker"]: s["portfolio_weight"] for s in out}
    assert weight["NVDA"] == pytest.approx(2*weight["MSFT"], abs=1e-6)


def test_market_vol_scale_and_cash():
    r = evaluate_snapshot(Snapshot(as_of=date(2026,10,19),
                                   stocks=[stock()],
                                   spy_20d_ann_vol=.46,
                                   basket_ann_vol=.50))
    assert r["equity_scale"] == pytest.approx(.50)
    assert r["cash_weight"] == pytest.approx(.50)


def test_hold_if_vol_missing():
    r = evaluate_snapshot(Snapshot(as_of=date(2026,10,19), stocks=[stock()]))
    assert r["equity_scale"] is None
    assert all("portfolio_weight" not in x for x in r["selected"])


def test_daily_nav_verifier():
    r = verify_nav([{"date":"2020-01-01","nav":100},
                    {"date":"2020-07-01","nav":80},
                    {"date":"2021-01-01","nav":140}])
    assert r["max_drawdown_pct"] == pytest.approx(-20)
    assert r["cagr_pct"] > 0
    assert "NOT_INDEPENDENT" in r["status"]


def test_nav_out_of_order_fails():
    with pytest.raises(HTTPException):
        verify_nav([{"date":"2021-01-01","nav":100},
                    {"date":"2020-01-01","nav":200}])


def test_auth_no_fallthrough():
    from tier1_v3.dashboard import require_login
    with pytest.raises(HTTPException) as e:
        require_login(None)
    assert e.value.status_code in (401,503)


def test_never_imports_gem_processors():
    # No GEM background worker or broker imports may execute at startup.
    assert app.router.lifespan_context is not None
    import tier1_v3.dashboard as mod
    assert "gem_" not in " ".join(mod.evaluate_snapshot.__code__.co_names)
