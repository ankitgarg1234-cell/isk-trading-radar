"""Tier-1 Moat Momentum V3 read-only dashboard.

Replaces GEMv1 on its isolated Render service. No background collection,
no live trading, no Marketstack integration, and no mutation of existing
GEM or other radar databases. Historical claims require independent evidence.
"""
from __future__ import annotations

from datetime import date
from math import isfinite, sqrt
import os
import secrets

from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field


TIER1 = frozenset("""
NVDA AVGO MSFT META GOOGL AMZN PLTR MU AMD LRCX KLAC AMAT AAPL NFLX
DELL ANET SNPS CDNS PANW CRWD NOW FTNT WDC STX MRVL SNDK
""".split())
VERSION = "Tier1_Moat_Momentum_V3_Production"
START = "2010-01-01"
FEE_RATE = 0.002
TARGET_VOL = 0.23
BASKET_VOL_CAP = 0.45

app = FastAPI(
    title=VERSION,
    description="Read-only independent research dashboard; not a trading bot.",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
_basic = HTTPBasic(auto_error=False)


def _auth_config():
    # Existing GEM login remains valid to avoid inadvertently exposing the new UI.
    username = (os.getenv("TIER1_DASHBOARD_USERNAME")
                or os.getenv("GEM_DASHBOARD_USERNAME") or "").strip()
    password = (os.getenv("TIER1_DASHBOARD_PASSWORD")
                or os.getenv("GEM_DASHBOARD_PASSWORD") or "")
    return username, password


def require_login(credentials: HTTPBasicCredentials | None = Depends(_basic)):
    username, password = _auth_config()
    if len(username) < 3 or len(password) < 20:
        raise HTTPException(503, "Dashboard login is not configured.")
    if credentials is None or not (
        secrets.compare_digest(credentials.username.encode(), username.encode())
        and secrets.compare_digest(credentials.password.encode(), password.encode())
    ):
        raise HTTPException(401, "Authentication required",
                            headers={"WWW-Authenticate": 'Basic realm="Tier-1 V3 Research"'})


def value(row, key, low=None, high=None):
    x = row.get(key)
    if isinstance(x, bool) or x is None:
        raise ValueError(key + " missing")
    try:
        f = float(x)
    except (TypeError, ValueError):
        raise ValueError(key + " nonnumeric") from None
    if not isfinite(f) or (low is not None and f < low) or (high is not None and f > high):
        raise ValueError(key + " outside range")
    return f


class Snapshot(BaseModel):
    as_of: date
    stocks: list[dict] = Field(default_factory=list, max_length=15000)
    current_holdings: list[str] = Field(default_factory=list)
    spy_20d_ann_vol: float | None = None
    basket_ann_vol: float | None = None


class NavRequest(BaseModel):
    points: list[dict] = Field(default_factory=list, max_length=10000)


def evaluate_snapshot(snap: Snapshot):
    rows = []
    found = set()
    for rec in snap.stocks:
        ticker = str(rec.get("ticker") or "").strip().upper()
        if not ticker or ticker in found:
            continue
        found.add(ticker)
        entry = {"ticker": ticker, "eligible": False, "status": "DATA_HOLD",
                 "score": None, "reasons": []}
        why = entry["reasons"]
        rows.append(entry)
        try:
            listed = date.fromisoformat(str(rec["listed_date"]))
            if listed > snap.as_of:
                why.append("Not yet publicly listed")
                continue
            price = value(rec, "price", 0)
            adtv = value(rec, "adtv20", 0)
            if price < 5 or adtv < 5_000_000:
                entry["status"] = "FILTERED"
                why.append("Price/20-day liquidity gate")
                continue
            istier = ticker in TIER1
            if not istier:
                if not bool(rec.get("pit_sp500_member", False)):
                    entry["status"] = "FILTERED"
                    why.append("Not PIT S&P 500 member")
                    continue
                # Do not silently equate 36-year moat with 36-month momentum.
                years = value(rec, "moat_lookback_years", 0)
                moat = value(rec, "moat_percentile", 0, 1)
                if years < 36 or moat < .90:
                    entry["status"] = "FILTERED"
                    why.append("36-year non-Tier-1 capital moat gate")
                    continue
            if bool(rec.get("turnaround_banned", False)):
                entry["status"] = "BANNED"
                why.append("Permanent turnaround ban")
                continue
            # Require dated fundamentals and strictly prior-year ML training.
            f_available = date.fromisoformat(str(rec["fundamentals_available_as_of"]))
            if f_available > snap.as_of:
                why.append("Fundamental filing not available PIT")
                continue
            trained = int(rec["ml_trained_through_year"])
            if trained >= snap.as_of.year:
                why.append("ML model trained on future/current year")
                continue
            ytd = value(rec, "ytd_pct_rank", 0, 1)
            sub = value(rec, "in_top_subindustry", 0, 1)
            davis = value(rec, "davis_rank", 0, 1)
            rule40 = value(rec, "rule40_rank", 0, 1)
            rf = value(rec, "p_rf", 0, 1)
            et = value(rec, "p_et", 0, 1)
            gb = value(rec, "p_gb", 0, 1)
            sma50 = value(rec, "sma50", 0)
            sma200 = value(rec, "sma200", 0)
            vol_z = value(rec, "subindustry_vol_zscore")
            dvol = value(rec, "downside_vol", 0.00000001)
            ml = 0.35 * rf + 0.35 * et + 0.30 * gb
            structural = 0.35 * (ytd ** 3.5) + 0.25 * sub + 0.20 * davis + 0.20 * rule40
            uptrend = 1.0 if price > sma50 and price > sma200 else .75
            volatility = .40 if vol_z > 2 else 1.0
            tier = 1.35 if istier else 1.0
            score = (.40 * ml + .60 * structural) * uptrend * volatility * tier
            entry.update({"status": "RESEARCH_ONLY", "eligible": True,
                          "score": round(score, 6), "ml": round(ml, 5),
                          "structural": round(structural, 5),
                          "trend_mult": uptrend, "risk_mult": volatility,
                          "tier_mult": tier, "downside_vol": dvol,
                          "tier1": istier})
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            why.append("PIT evidence or required numeric field missing/invalid: " + str(exc)[:100])

    ranked = sorted((r for r in rows if r["eligible"]),
                    key=lambda r: (-r["score"], r["ticker"]))
    holdings = {str(h).strip().upper() for h in snap.current_holdings}
    # Retain current names ranked in top 10, then fill to five by rank.
    keep = [r for r in ranked[:10] if r["ticker"] in holdings][:5]
    chosen = keep + [r for r in ranked if r["ticker"] not in
                     {x["ticker"] for x in keep}][:max(0, 5-len(keep))]
    warnings = [
        "User-supplied prices, fundamentals and ML probabilities are not independently verified.",
        "Zero orders permitted; results are research-only, not actionable trade signals.",
        "No official 17-year backtest has been independently reproduced."
    ]
    if snap.spy_20d_ann_vol is None or snap.basket_ann_vol is None:
        warnings.append("Portfolio volatility governor HOLD: SPY/basket volatility missing.")
        equity_scale = None
    else:
        spy = snap.spy_20d_ann_vol
        basket = snap.basket_ann_vol
        if any(not isfinite(v) or v <= 0 for v in (spy, basket)):
            warnings.append("Portfolio volatility governor HOLD: invalid volatility.")
            equity_scale = None
        else:
            equity_scale = min(1.0, TARGET_VOL / spy, BASKET_VOL_CAP / basket)
    if equity_scale is not None and chosen:
        inv = [1.0 / sqrt(r["downside_vol"]) for r in chosen]
        denom = sum(inv)
        for r, v in zip(chosen, inv):
            r["portfolio_weight"] = round(equity_scale * v / denom, 7)
    return {
        "version": VERSION,
        "as_of": snap.as_of.isoformat(),
        "status": "RESEARCH_ONLY",
        "data_trust": "USER_PROVIDED_NOT_INDEPENDENTLY_VERIFIED",
        "count_input": len(snap.stocks),
        "count_eligible": len(ranked),
        "equity_scale": equity_scale,
        "cash_weight": None if equity_scale is None else round(1.0-equity_scale, 7),
        "selected": chosen,
        "ranked": ranked[:30],
        "excluded": [r for r in rows if not r["eligible"]][:100],
        "warnings": warnings,
        "execution_fee_per_dollar_turnover": FEE_RATE,
        "cash_sweep": "^IRX daily: not calculated without dated risk-free history"
    }


def verify_nav(points):
    dates, navs = [], []
    for p in points:
        try:
            d = date.fromisoformat(str(p["date"]))
            n = value(p, "nav", 0.0000001)
        except (KeyError, ValueError, TypeError):
            raise HTTPException(422, "NAV points require date YYYY-MM-DD and positive nav.")
        dates.append(d)
        navs.append(n)
    if len(dates) < 2 or any(b <= a for a,b in zip(dates,dates[1:])):
        raise HTTPException(422, "Need 2+ strictly increasing distinct trading dates.")
    days = (dates[-1] - dates[0]).days
    years = days / 365.25
    cagr = (navs[-1] / navs[0]) ** (1/years) - 1
    peak = navs[0]
    mdd = 0
    worst_date = dates[0]
    for d, n in zip(dates, navs):
        peak = max(peak, n)
        dd = n / peak - 1
        if dd < mdd:
            mdd, worst_date = dd, d
    return {"status":"NAV_ARITHMETIC_ONLY_NOT_INDEPENDENT_STRATEGY_VALIDATION",
            "start":dates[0].isoformat(), "end":dates[-1].isoformat(),
            "days":days, "observations":len(dates),
            "cagr_pct":round(100*cagr, 4),
            "max_drawdown_pct":round(100*mdd,4),
            "worst_drawdown_date":worst_date.isoformat(),
            "warning":"Uploaded NAV cannot prove PIT compliance, execution realism, or OOS selection."}


@app.get("/health")
def health():
    return {"healthy": True, "service": VERSION, "trading_enabled": False,
            "gem_workers_running": False, "read_only": True}


@app.get("/api/v3/status", dependencies=[Depends(require_login)])
def status():
    return {"strategy": VERSION,
            "validation": "PENDING_INDEPENDENT_REPRODUCTION",
            "claimed_cagr_pct": 34.99, "claimed_max_drawdown_pct": -37.44,
            "claimed_metrics_certified": False,
            "historical_nav_loaded": False, "signals_live": False,
            "automated_trading": False,
            "data_vendor": "NONE",
            "tier1_count": len(TIER1),
            "tier1_symbols": sorted(TIER1)}


@app.post("/api/v3/evaluate", dependencies=[Depends(require_login)])
def evaluate(snap: Snapshot):
    return evaluate_snapshot(snap)


@app.post("/api/v3/verify-nav", dependencies=[Depends(require_login)])
def nav(req: NavRequest):
    return verify_nav(req.points)


PAGE = """
<!doctype html><html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Tier-1 Moat Momentum V3 · Research Dashboard</title>
<style>
:root{font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#0c1525;color:#e6ecf7}
*{box-sizing:border-box} body{margin:0;background:radial-gradient(ellipse at top right,#233b57 0%,#0c1525 46%);min-height:100vh}
.wrap{width:min(1220px,94vw);margin:auto;padding:33px 0 70px}
header{display:flex;justify-content:space-between;align-items:center;gap:24px;border-bottom:1px solid #344459;padding-bottom:22px;flex-wrap:wrap}
h1{font-size:clamp(24px,3vw,34px);margin:8px 0}h2{font-size:21px;margin:0 0 15px}h3{margin:0 0 9px}
.sub{color:#a8bdd4}.small{font-size:12px}.eyebrow{font-size:11px;letter-spacing:.13em;font-weight:800;color:#8eafde}
.tag{border:1px solid #415471;color:#b7cdee;border-radius:30px;padding:8px 12px;font-size:12px;font-weight:700}
.tag.warn{color:#ffd59b;border-color:#786341}
.kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin:25px 0}
.card{border:1px solid #32445d;background:#122139dd;border-radius:15px;padding:20px;box-shadow:0 13px 33px #060d1826}
.kpi-label{font-size:12px;color:#9bb5d1}.kpi{font-size:28px;font-weight:800;margin:8px 0 5px}
.two{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(270px,1fr);gap:18px}
ul{padding-left:18px;line-height:1.8}.warning{color:#f7c488}
button{background:#8abaff;color:#101f32;border:0;padding:10px 18px;border-radius:9px;cursor:pointer;font-weight:750}
button:hover{filter:brightness(1.1)}label{display:block;margin-top:13px;color:#a9c1da;font-size:13px}
input[type=file]{display:block;margin:10px 0;color:#bacfe9;max-width:100%}
pre{background:#0a1423;border:1px solid #33455a;overflow:auto;border-radius:10px;padding:15px;min-height:70px;color:#d7e8f6;font-size:12px;max-height:370px}
table{border-collapse:collapse;width:100%;font-size:13px;margin-top:10px}td,th{text-align:left;padding:12px 8px;border-bottom:1px solid #33435a}th{color:#a9c7e9}
a{color:#a9cbff;text-decoration:none}.foot{margin-top:28px;color:#a4b7cc;font-size:12px}
@media(max-width:800px){.kpis{grid-template-columns:repeat(2,1fr)}.two{grid-template-columns:1fr}}
@media(max-width:490px){.kpis{grid-template-columns:1fr 1fr}.kpi{font-size:23px}}
</style></head><body><div class="wrap">
<header><div><div class="eyebrow">RESEARCH SYSTEM · V3 PRODUCTION BLUEPRINT</div>
<h1>Tier-1 Moat Momentum <span style="color:#8abaff">V3</span></h1>
<div class="sub">Monthly top-5 quality & momentum portfolio · point-in-time governance</div></div>
<div class="tag warn">NO LIVE TRADING · VALIDATION PENDING</div></header>
<div class="kpis">
 <div class="card"><div class="kpi-label">Claimed 2010–2026 CAGR</div><div class="kpi">34.99%</div><div class="small warning">Unverified target — not live performance</div></div>
 <div class="card"><div class="kpi-label">Claimed maximum drawdown</div><div class="kpi">−37.44%</div><div class="small warning">Unverified historical claim</div></div>
 <div class="card"><div class="kpi-label">Portfolio basket</div><div class="kpi">Top 5</div><div class="small sub">Keep buffer 10 · monthly rebalance</div></div>
 <div class="card"><div class="kpi-label">Verified live candidates</div><div class="kpi" id="eligible">—</div><div class="small sub">No independent PIT snapshot connected</div></div>
</div>
<div class="two">
 <section class="card">
 <h2>Research portfolio</h2>
 <div class="small sub">Import a point-in-time JSON snapshot to calculate research-only scores, eligibility, volatility scaling, and allocation. Nothing is saved or traded.</div>
 <label for="snapshot">Point-in-time stock snapshot (.json)</label><input id="snapshot" type="file" accept=".json,application/json">
 <button onclick="runSnapshot()">Evaluate snapshot</button>
 <div id="select" style="margin-top:18px;color:#afc6df">No verified holdings. The dashboard will not invent market prices, model probabilities, or past returns.</div>
 <h3 style="margin-top:25px">Evaluation output</h3><pre id="out">Select your PIT dataset to evaluate.</pre>
 </section>
 <section class="card"><h2>Risk & governance</h2>
 <ul><li>26 predefined Tier-1 compounders · 1.35× ranking multiplier</li>
 <li>Non-Tier-1: PIT S&P 500 + 36-year capital-moat top decile</li>
 <li>50D/200D SMA discount: 0.75× when either fails</li>
 <li>Sub-industry volatility Z &gt; 2: exposure-score multiplier 0.40×</li>
 <li>Annual walk-forward ML: RF 35% · ET 35% · GB 30%</li>
 <li>SPY 20D target volatility 23% · basket volatility cap 45%</li>
 <li>Portfolio weight ∝ 1/√downside volatility</li>
 <li>Model/trade data must be dated earlier than its use</li>
 <li>Rebalance fee: 0.20% of turnover · cash yield: ^IRX daily</li></ul>
 <p class="small warning">Research scores do not certify fundamentals, OOS targets, permanent-ban evidence, transaction slippage, or live feasibility.</p>
 </section>
</div>
<div class="two" style="margin-top:18px">
 <section class="card"><h2>Independent equity-curve audit</h2>
 <p class="small sub">Upload a JSON array of daily records with date (YYYY-MM-DD) and nav (positive number), or an object with a points array.</p>
 <input id="navfile" type="file" accept=".json,application/json">
 <button onclick="runNav()">Recalculate CAGR & drawdown</button>
 <pre id="navout">No daily NAV uploaded. Historical claims are not certified.</pre>
 </section>
 <section class="card"><h2>Data readiness</h2>
 <table><tr><th>Control</th><th>Current state</th></tr>
 <tr><td>SEC filing timestamps</td><td>Not connected</td></tr>
 <tr><td>Historical S&P membership</td><td>Not verified</td></tr>
 <tr><td>Survivorship-free delisted prices</td><td>Not verified</td></tr>
 <tr><td>ML model history / training targets</td><td>Not connected</td></tr>
 <tr><td>Transaction & risk-free series</td><td>Not connected</td></tr>
 <tr><td>Real-money order routing</td><td>Disabled</td></tr></table>
 </section>
</div>
<p class="foot">Tier1_Moat_Momentum_V3_Production · No GEM V1 workers · No Marketstack billing or APIs · No modification to other dashboards or shared databases.</p>
</div>
<script>
async function postJson(url,obj){
  const res=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(obj)});
  const body=await res.json(); if(!res.ok) throw Error(JSON.stringify(body)); return body;
}
function escapeText(x){return String(x).replace(/[&<>"\x27]/g,function(c){if(c==="&")return "&amp;";if(c==="<")return "&lt;";if(c===">")return "&gt;";if(c===String.fromCharCode(34))return "&quot;";return "&#39;";});}
async function runSnapshot(){
 const file=document.getElementById("snapshot").files[0]; if(!file){alert("Choose a JSON file.");return;}
 const area=document.getElementById("out");
 try{
  const payload=JSON.parse(await file.text());
  const result=await postJson("/api/v3/evaluate",payload);
  document.getElementById("eligible").textContent=String(result.count_eligible);
  const rows=result.selected.map(function(r){return "<tr><td>"+escapeText(r.ticker)+"</td><td>"+r.score.toFixed(4)+"</td><td>"+(r.portfolio_weight===undefined?"HOLD":(100*r.portfolio_weight).toFixed(2)+"%")+"</td></tr>"}).join("");
  document.getElementById("select").innerHTML=rows?'<table><tr><th>Stock</th><th>Score</th><th>Equity allocation</th></tr>'+rows+'</table><p class="small warning">User-supplied input only: NOT verified actionable signals.</p>':"No eligible holdings in the supplied PIT dataset.";
  area.textContent=JSON.stringify(result,null,2);
 }catch(e){area.textContent="Input rejected: "+e.message;}
}
async function runNav(){
 const file=document.getElementById("navfile").files[0]; if(!file){alert("Choose a JSON file.");return;}
 const area=document.getElementById("navout");
 try{
  const data=JSON.parse(await file.text());
  const result=await postJson("/api/v3/verify-nav",Array.isArray(data)?{points:data}:data);
  area.textContent=JSON.stringify(result,null,2);
 }catch(e){area.textContent="NAV input rejected: "+e.message;}
}
</script></body></html>
"""


@app.get("/", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def dashboard():
    return HTMLResponse(PAGE)
