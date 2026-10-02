#!/usr/bin/env python3
"""Render the saved allocation diagnostic as a standalone, shareable report."""
from __future__ import annotations

import argparse
import base64
from collections import Counter
from datetime import date, datetime, timezone
import html
from io import BytesIO
import json
from pathlib import Path
import re
import statistics

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter


NAMES = ["Capped / profit taking", "Uncapped / risk budget / profit taking", "Full deployment / profit taking"]
LABELS = {NAMES[0]: "Capped allocation", NAMES[1]: "Uncapped, risk budget kept", NAMES[2]: "Full deployment"}
COLORS = {NAMES[0]: "#758394", NAMES[1]: "#238575", NAMES[2]: "#2563a6", "S&P 500": "#192638"}


def esc(value):
    return html.escape(str(value))


def pct(value, signed=True):
    if value is None:
        return "—"
    return f"{value:+.2f}%" if signed else f"{value:.2f}%"


def money(value):
    return f"${value:,.0f}"


def img(fig):
    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=170, bbox_inches="tight", facecolor="#ffffff")
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def plots(report):
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.edgecolor": "#d3dce5", "axes.labelcolor": "#4b5f73",
                         "xtick.color": "#4b5f73", "ytick.color": "#4b5f73"})
    fig, ax = plt.subplots(figsize=(10.8, 4.4))
    for name in NAMES:
        rows = report["daily_curves"][name]
        ax.plot([date.fromisoformat(r["date"]) for r in rows], [r["equity"] for r in rows],
                label=LABELS[name], color=COLORS[name], linewidth=1.9)
    rows = report["benchmark_curve"]
    ax.plot([date.fromisoformat(r["date"]) for r in rows], [r["equity"] for r in rows],
            label="S&P 500 total return", color=COLORS["S&P 500"], linewidth=2.0, linestyle="--")
    ax.set_ylabel("Account value, USD")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f"${x / 1000:.0f}k"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.grid(axis="y", alpha=.2)
    ax.legend(loc="upper left", frameon=False, ncol=2, fontsize=9)
    ax.margins(x=.015)
    equity = img(fig)

    full = next(r for r in report["results"] if r["name"] == NAMES[2])
    full_label = "Full-deployment policy (no entries)" if full["buy_count"] == 0 else "Full deployment, with profit taking"
    b = report["benchmark"]["monthly_returns"]
    months = [m for m, v in full["monthly_returns"].items() if v["complete"]]
    fig, ax = plt.subplots(figsize=(10.8, 4.2))
    xs = list(range(len(months)))
    ax.bar([x - .18 for x in xs], [full["monthly_returns"][m]["return_pct"] for m in months],
           width=.36, color=COLORS[NAMES[2]], label=full_label)
    ax.bar([x + .18 for x in xs], [b[m]["return_pct"] for m in months],
           width=.36, color="#93a5b7", label="S&P 500 total return")
    ax.axhline(30, color="#ab6b2e", linestyle="--", linewidth=1.3, label="30% monthly target")
    ax.axhline(0, color="#4b5f73", linewidth=.6)
    ax.set_xticks(xs[::3], [datetime.strptime(months[x], "%Y-%m").strftime("%b %y") for x in xs[::3]])
    ax.set_ylabel("Monthly return, %")
    ax.grid(axis="y", alpha=.15)
    ax.legend(loc="upper left", frameon=False, fontsize=8.7, ncol=2)
    ax.margins(x=.012)
    monthly = img(fig)
    return equity, monthly


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--test-log", required=True)
    parser.add_argument("--review-url", default="")
    parser.add_argument("--patch", default="")
    parser.add_argument("--gate-details", default="")
    args = parser.parse_args()
    report = json.loads(Path(args.input).read_text())
    rows = {r["name"]: r for r in report["results"]}
    capped, risk, full = [rows[n] for n in NAMES]
    bench = report["benchmark"]
    protocol = report["protocol"]
    start, end = protocol["period"]["start"], protocol["period"]["end"]
    test_log = Path(args.test_log).read_text()
    tests = re.findall(r"(\d+ passed[^\n]*)", test_log)
    test_summary = tests[-1] if tests else "See verification log"
    equity_plot, monthly_plot = plots(report)
    target_met = full["months_at_least_30_pct"] == full["complete_months"]
    headline = "30% monthly is not supported by this test" if not target_met else "The historical target was met; forward validation remains open"
    advantage = full["total_return_pct"] - capped["total_return_pct"]
    benchmark_gap = full["total_return_pct"] - bench["total_return_pct"]
    comparison = (f"Full deployment returned {pct(full['total_return_pct'])}, versus {pct(capped['total_return_pct'])} with capped sizing "
                  f"and {pct(bench['total_return_pct'])} for S&P 500 total return. "
                  f"The best complete month was {pct(full['best_complete_month_pct'])}; {full['months_at_least_30_pct']} of "
                  f"{full['complete_months']} complete months reached 30%.")
    alpha_read = "outperformed" if benchmark_gap > 0 else "underperformed"
    action_read = ("Keep the allocation change as a research candidate. It still needs forward evidence of repeatable net alpha and acceptable drawdowns."
                   if benchmark_gap > 0 else "Keep this change out of live trading. The allocation hypothesis did not produce benchmark outperformance in this data.")
    no_entries = all(r["buy_count"] == 0 for r in rows.values())
    result_read = (f"Full deployment {alpha_read} the benchmark by {abs(benchmark_gap):.2f} percentage points over the full period. "
                   f"Versus repaired capped sizing, its total-return change was {advantage:+.2f} points.")
    kpis = (f"<div class='kpi'><label>Full deployment · net total</label><strong>{pct(full['total_return_pct'])}</strong><small>{money(full['end_value'])} ending account value</small></div>"
            f"<div class='kpi'><label>Best complete month</label><strong>{pct(full['best_complete_month_pct'])}</strong><small>Median month {pct(full['median_complete_month_pct'])}</small></div>"
            f"<div class='kpi'><label>Months reaching 30%</label><strong>{full['months_at_least_30_pct']} / {full['complete_months']}</strong><small>October 2026 is partial and excluded</small></div>")
    exercise_note = ""
    if no_entries:
        headline = "Cash stayed idle: the allocation comparison is inconclusive"
        comparison = (f"All seven policies made zero purchases and retained the entire {money(protocol['starting_cash_usd'])} account. "
                      f"The account returned 0%; cached S&P 500 total return was {pct(bench['total_return_pct'])}. "
                      "No eligible entry reached execution, so this run did not exercise uncapped sizing or profit taking.")
        action_read = ("Validate signal coverage and the consistency of entry, stop and target horizons before choosing an allocation policy. "
                       "All lane-qualified observations failed R/R; missing analyst and news archives also limit the evidence. "
                       "This run provides no support for 30% monthly returns.")
        result_read = (f"Idle cash lagged the benchmark by {abs(benchmark_gap):.2f} percentage points. "
                       "Identical zero returns do not show that the sizing policies are equivalent; none bought a stock.")
        kpis = ("<div class='kpi'><label>Executed purchases</label><strong>0</strong><small>Across all seven policies</small></div>"
                f"<div class='kpi'><label>Average account in cash</label><strong>100%</strong><small>{money(full['ending_cash'])} ending cash</small></div>"
                f"<div class='kpi'><label>Months reaching 30%</label><strong>0 / {full['complete_months']}</strong><small>Allocation and harvesting were not exercised</small></div>")
        exercise_note = "<div class='callout'><p><strong>Interpretation:</strong> These are idle-account outcomes under the named policies, not returns from a fully invested portfolio. The profit-taking and cost comparisons below are not assessable because there were no trades.</p></div>"
    if full["max_drawdown_pct"] < -15:
        action_read += " The full-deployment case also breached the prior 15% drawdown objective."
    main_table = []
    for r in [capped, risk, full]:
        main_table.append(f"<tr><th>{esc(LABELS[r['name']])}</th><td>{money(r['end_value'])}</td><td>{pct(r['total_return_pct'])}</td>"
                          f"<td>{pct(r['max_drawdown_pct'])}</td><td>{pct(r['average_cash_pct'],False)}</td>"
                          f"<td>{pct(r['median_complete_month_pct'])}</td><td>{pct(r['best_complete_month_pct'])}</td></tr>")
    bmonths = [v["return_pct"] for v in bench["monthly_returns"].values() if v["complete"]]
    main_table.append(f"<tr class='benchmark'><th>S&amp;P 500 total return</th><td>{money(bench['end_value'])}</td><td>{pct(bench['total_return_pct'])}</td>"
                      f"<td>{pct(bench['max_drawdown_pct'])}</td><td>0% assumed</td><td>{pct(statistics.median(bmonths))}</td><td>{pct(max(bmonths))}</td></tr>")
    paired = []
    for name in NAMES:
        yes = rows[name]
        no = rows[name.replace("profit taking", "no profit taking")]
        delta = yes["total_return_pct"] - no["total_return_pct"]
        paired.append(f"<tr><th>{esc(LABELS[name])}</th><td>{pct(yes['total_return_pct'])}</td><td>{pct(no['total_return_pct'])}</td>"
                      f"<td>{delta:+.2f} pp</td><td>{yes['profit_sell_count']}</td><td>{money(yes['fees_paid'])}</td></tr>")
    high_cost = rows["Full deployment / profit taking / 50 bps"]
    risk_rows = []
    for r in [capped, risk, full]:
        risk_rows.append(f"<tr><th>{esc(LABELS[r['name']])}</th><td>{pct(r['peak_position_weight_pct'],False)}</td>"
                         f"<td>{pct(r['peak_modeled_stop_risk_pct'],False)}</td><td>{r['buy_count']}</td><td>{r['sell_count']}</td>"
                         f"<td>{r['cancelled_orders']}</td><td>{money(r['ending_cash'])}</td></tr>")
    annual = []
    for r in [capped, risk, full, bench]:
        annual.append(f"<tr><th>{esc(LABELS.get(r['name'], 'S&P 500 total return'))}</th>" +
                      "".join(f"<td>{pct(r['annual_returns_pct'].get(y))}</td>" for y in ["2024", "2025", "2026"]) + "</tr>")
    monthly_rows = []
    for month in full["monthly_returns"]:
        label = datetime.strptime(month, "%Y-%m").strftime("%b %Y")
        complete = full["monthly_returns"][month]["complete"]
        if not complete:
            label += " · partial"
        values = [rows[n]["monthly_returns"][month]["return_pct"] for n in NAMES] + [bench["monthly_returns"][month]["return_pct"]]
        monthly_rows.append(f"<tr><th>{label}</th>" + "".join(f"<td class='{'positive' if v>0 else 'negative' if v<0 else ''}'>{pct(v)}</td>" for v in values) + "</tr>")
    pipeline = report["daily_pipeline"]
    days = len(pipeline)
    zero_days = sum(r["lane_rr"] == 0 for r in pipeline)
    eligible = [r["lane_rr"] for r in pipeline]
    blocker_rows = "".join(f"<tr><th>{esc(k)}</th><td>{v:,}</td></tr>" for k, v in Counter(report["pipeline_blockers"]).most_common(6))
    gate_details = ""
    if args.gate_details:
        details = json.loads(Path(args.gate_details).read_text())
        if details["result_hash"] != report["deterministic_hash"]:
            raise ValueError("Gate diagnostic belongs to a different result")
        obs = details["observations"]
        rr_values = [r["risk_reward"] for r in obs]
        gate_rows = "".join(f"<tr><th>{esc(r['symbol'])} · {r['date']}</th><td>${r['price']:,.2f}</td>"
                            f"<td>${r['stop']:,.2f}</td><td>${r['target']:,.2f}</td><td>{r['risk_reward']:.2f}×</td>"
                            f"<td>{r['fixed_plan_required_pullback_pct']:.2f}%</td></tr>" for r in obs[-8:])
        if obs:
            gate_details = (f"<h3>The binding R/R gate</h3><p>Reconstructing all {len(obs)} lane-qualified observations confirms R/R "
                            f"ranged from {min(rr_values):.2f}× to {max(rr_values):.2f}×. None met 2×. Below are the latest eight observations.</p>"
                            "<div class='table-scroll'><table><thead><tr><th>Stock · date</th><th>Price</th><th>Stop reference</th><th>Base target</th><th>R/R</th><th>Fixed-plan pullback for 2×</th></tr></thead>"
                            f"<tbody>{gate_rows}</tbody></table></div>"
                            "<p class='small'>The pullback calculation holds that historical stop and target fixed: maximum entry = (target + 2 × stop) / 3. "
                            "It is a diagnostic, not a recommended order price. A later entry requires fresh evidence, recalculated levels and another eligibility check.</p>")
    verification_note = ("With no trades, these historical ledger checks verify idle balances only. "
                         "The behavioral tests separately exercise buys, staged sales, gap cancellations and corporate actions. "
                         "A five-session uninterrupted run also matched a two-session checkpoint plus resumed run exactly.") if no_entries else ""
    rejects = Counter(r["reason"] for r in report["rejections"][NAMES[2]])
    rejected_read = "; ".join(f"{esc(k)}: {v}" for k,v in rejects.items()) or "No cancelled orders"
    buys = [t for t in report["trades"][NAMES[2]] if t["side"] == "BUY"]
    sells = [t for t in report["trades"][NAMES[2]] if t["side"] == "SELL"]
    realized = sum(t.get("pnl",0) for t in sells)
    min_rr = min((t.get("fill_risk_reward",0) for t in buys), default=None)
    rr_read = f"{min_rr:.2f}× minimum executed entry R/R" if min_rr is not None else "No executed buys"
    closing = report["closing_positions"][NAMES[2]]
    closing_rows = "".join(f"<tr><th>{esc(p['symbol'])}</th><td>{p['shares']:g}</td><td>{money(p['avg_cost'])}</td><td>{money(p['last_price'])}</td>"
                           f"<td>{esc(p['last_quote_date'])}</td><td>{esc(', '.join(p['profit_taken_stages']) or 'None')}</td></tr>" for p in closing)
    if not closing_rows:
        closing_rows = "<tr><td colspan='6'>No open positions at the end of the test.</td></tr>"
    coverage = report["coverage"]
    source = protocol["source"]
    source_hashes = "".join(f"<tr><th>{esc(k)}</th><td><code>{esc(v)}</code></td></tr>" for k,v in source["source_sha256"].items())
    review_link = f"<a class='button' href='{esc(args.review_url)}' target='_blank' rel='noreferrer'>Review code changes</a>" if args.review_url else ""
    if args.patch:
        patch_data = base64.b64encode(Path(args.patch).read_bytes()).decode()
        review_link += f"<a class='button secondary' href='data:text/plain;base64,{patch_data}' download='ISK_Allocation_Experiment.patch'>Download code patch</a>"
    support_json = base64.b64encode(Path(args.input).read_bytes()).decode()
    json_link = f"<a class='button secondary' href='data:application/json;base64,{support_json}' download='stock_allocation_experiment.json'>Download results and trade ledger</a>"
    created = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ISK · Allocation Experiment</title><style>
:root{{--ink:#18283a;--muted:#56697d;--line:#dce4eb;--blue:#2563a6;--paper:#f4f7fa}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:16px/1.65 -apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif}}
a{{color:var(--blue)}}header{{background:#13283e;color:white;padding:48px 0 36px}}.wrap{{max-width:1160px;margin:auto;padding:0 30px}}
.eyebrow{{font-size:12px;letter-spacing:1.5px;text-transform:uppercase;font-weight:700;color:#bdd2e6}}
h1{{font-size:38px;line-height:1.17;max-width:850px;margin:15px 0 16px;letter-spacing:-.8px}}header p{{color:#d6e3ee;max-width:820px}}
nav{{display:flex;gap:22px;flex-wrap:wrap;padding-top:14px}}nav a{{font-size:13px;color:#dce8f3;text-decoration:none}}
main{{padding:30px 0 64px}}section{{background:#fff;border:1px solid var(--line);border-radius:10px;padding:28px 30px;margin-bottom:22px}}
h2{{font-size:24px;line-height:1.25;margin:0 0 14px;letter-spacing:-.3px}}h3{{font-size:18px;margin:20px 0 10px}}p{{margin:10px 0 16px}}.lead{{font-size:18px;line-height:1.6}}
.status{{display:inline-block;padding:5px 10px;border-radius:4px;background:#e8eef5;color:#245078;font-size:12px;font-weight:700;letter-spacing:.35px}}
.callout{{border-left:4px solid #bc793a;background:#faf5ed;padding:14px 18px;margin:20px 0}}.callout p{{margin:0}}
.kpis{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:24px 0}}.kpi{{padding:20px;background:#edf4fb;border-radius:7px}}
.kpi label{{display:block;font-size:12px;color:var(--muted);font-weight:700;text-transform:uppercase;letter-spacing:.6px}}.kpi strong{{display:block;font-size:32px;line-height:1.35;margin:6px 0}}.kpi small{{display:block;color:var(--muted)}}
.table-scroll{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;font-size:13px;line-height:1.5}}thead th{{text-transform:none;color:var(--muted);font-size:12px;border-bottom:2px solid var(--line);padding:12px 10px;text-align:right;white-space:nowrap}}
thead th:first-child{{text-align:left}}tbody td,tbody th{{padding:12px 10px;border-bottom:1px solid #e7edf2;text-align:right;font-variant-numeric:tabular-nums}}tbody th{{text-align:left;font-weight:600;min-width:190px}}.benchmark{{background:#f1f5f8}}
.source-note,.small{{font-size:12px;color:var(--muted);line-height:1.55;margin-top:10px}}.chart{{display:block;width:100%;height:auto;margin:14px 0}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:25px}}ul{{padding-left:20px}}li{{padding-bottom:9px}}.positive{{color:#15765e}}.negative{{color:#a5473d}}
.button{{display:inline-block;padding:10px 16px;background:var(--blue);color:#fff;border-radius:5px;text-decoration:none;font-size:13px;font-weight:600;margin:8px 10px 4px 0}}.secondary{{background:#e8eef4;color:#234b70}}
details{{margin-top:22px}}summary{{cursor:pointer;font-weight:600;color:#244d74;padding:7px 0}}code{{font-size:10px;word-break:break-all}}footer{{padding:0 30px;color:var(--muted);font-size:12px}}
@media(max-width:740px){{.wrap{{padding:0 16px}}header{{padding:30px 0 25px}}h1{{font-size:29px}}section{{padding:22px 18px}}h2{{font-size:22px}}.kpis{{grid-template-columns:1fr}}.kpi strong{{font-size:29px}}.grid{{grid-template-columns:1fr}}tbody th{{min-width:160px}}nav{{gap:14px}}}}
@media print{{body{{background:#fff}}header{{background:#fff;color:var(--ink);padding:15px 0}}header p,.eyebrow{{color:var(--muted)}}section{{break-inside:avoid;border:0;border-top:1px solid var(--line);border-radius:0}}nav,.button{{display:none}}.wrap{{padding:0 15px}}details{{display:block}}}}
</style></head><body>
<header><div class="wrap"><div class="eyebrow">ISK Trading Radar · Allocation diagnostic · {start} to {end}</div>
<h1>Does fully investing $10,000 close the return gap?</h1><p>Repaired execution and historical replay. Seven fixed comparisons, current entry gates, whole shares, dated fills and trading costs.</p>
<nav><a href="#result">Result</a><a href="#comparison">Allocation</a><a href="#harvest">Profit taking</a><a href="#monthly">Monthly returns</a><a href="#repairs">Code repairs</a><a href="#method">Method &amp; evidence</a></nav></div></header>
<main class="wrap">
<section id="result"><span class="status">RESEARCH ONLY · NO LIVE ALLOCATION CHANGE</span><h2 style="margin-top:17px">{headline}</h2>
<p class="lead">{comparison}</p>
<div class="kpis">{kpis}</div>
<div class="callout"><p><strong>Decision:</strong> {action_read}</p></div>
<p>{result_read}</p>
<p class="source-note">Source: frozen experiment result and dated trade ledger, <code>{esc(Path(args.input).name)}</code>. Returns include both buy and sell fees and credited dividends. They are USD account returns, not monthly forecasts.</p></section>

<section id="cash"><h2>One shortlisted stock, one share: where does the rest go?</h2>
<p>Under the current policy, cash stays in the account until another stock qualifies or the existing holding qualifies for an addition. Profit-taking proceeds follow the same rule. The scanner continues to search, but an allocation setting cannot manufacture a qualified setup.</p>
<p>With one eligible stock, the full-deployment experiment can allocate nearly all cash to that stock. It must remove the per-holding risk-size ceiling as well as the 15% cap. Whole-share rounding and fees leave a small residual balance; later profit sales can create a larger cash balance again.</p>
<div class="table-scroll"><table><thead><tr><th>Illustrative policy</th><th>Quantity</th><th>Cash after purchase</th><th>Gain if stock rises 30%</th></tr></thead><tbody>
<tr><th>One-share purchase</th><td>1</td><td>$9,899.90</td><td>0.30% of starting account</td></tr>
<tr><th>Risk budget retained</th><td>6</td><td>$9,399.40</td><td>1.80% of starting account</td></tr>
<tr><th>Full deployment</th><td>99</td><td>$90.10</td><td>29.70% of starting account</td></tr>
</tbody></table></div>
<p class="small">Hypothetical sizing example only: $10,000 cash, $100 entry, $88 stop reference, $124 target (2× R/R), sufficient conviction and 10 bps buy fee. The $75 modeled risk budget permits floor($75/$12) = 6 shares. Gains show price appreciation divided by the initial $10,000, before transaction costs and without intervening sales. This is not an observed backtest return or the live stock's price.</p>
<p>One whole share cannot be partly sold while retaining a runner. A 20% stock decline with 99 shares also reduces the starting account by 19.8% before costs. Concentrating the money amplifies gains and losses; it does not improve the stock's expected return.</p></section>

<section id="comparison"><h2>The allocation comparison</h2>
{exercise_note}
<div class="table-scroll"><table><thead><tr><th>Same entries, different sizing</th><th>End value</th><th>Total return</th><th>Max drawdown</th><th>Average cash</th><th>Median month</th><th>Best month</th></tr></thead><tbody>{''.join(main_table)}</tbody></table></div>
<img class="chart" src="{equity_plot}" alt="Daily account values for capped, risk-constrained uncapped and full-deployment strategies, alongside S&P 500 total return.">
<div class="grid"><div><h3>Removing the cap alone</h3><p>The uncapped risk case normalizes conviction weights over available cash but keeps the 0.75% modeled stop-risk budget for each holding. Average cash was {pct(risk['average_cash_pct'],False)}. Removing a position cap cannot remove this independent sizing ceiling.</p></div>
<div><h3>The full-deployment hypothesis</h3><p>The full case removes both the 15% position cap and the 0.75% per-holding sizing ceiling. It spends available cash on currently eligible stocks, weighted by the existing score ladder. Average cash was {pct(full['average_cash_pct'],False)}; exposure to one holding peaked at {pct(full['peak_position_weight_pct'],False)}.</p></div></div>
<p class="small">Exposure can drift after entry. All cases require strong fundamentals, current lane qualification, a priority of at least68, an actionable entry, and R/R of at least2× at both signal and execution. There is no leverage, ETF sleeve, short selling, external deposit, or cash interest.</p></section>

<section id="harvest"><h2>Did profit taking improve returns?</h2>
<p>Targets are frozen when a position opens. The base target sells enough whole shares to reach25% of the original quantity; the stretch target takes cumulative sales to50%. Each stage executes once and retains at least one runner share. Sale proceeds remain in the account for the next qualifying entry.</p>
<div class="table-scroll"><table><thead><tr><th>Allocation</th><th>With profit taking</th><th>Without profit taking</th><th>Return difference</th><th>Profit sales</th><th>Fees with harvest</th></tr></thead><tbody>{''.join(paired)}</tbody></table></div>
<p>Full deployment realized {money(realized)} of net sale P&amp;L across {len(sells)} sales. This is distinct from total account return, which includes remaining holdings and dividends.</p>
<p><strong>Cost sensitivity:</strong> at50bps per side, full deployment with profit taking returned {pct(high_cost['total_return_pct'])}, with {pct(high_cost['max_drawdown_pct'])} maximum drawdown and {money(high_cost['fees_paid'])} in fees. The main comparison assumes10bps per side.</p>
<p class="small">The no-profit-taking comparison retains thesis-based reductions/exits and explosive-lane expiry; only profit harvests are disabled. Whole-share rounding makes small tranches approximate. Target completion markers survive additions, preventing repeated sell-and-rebuy cycles above a harvested target.</p></section>

<section id="risk"><h2>Exposure, trade counts and cash</h2>
<div class="table-scroll"><table><thead><tr><th>Allocation</th><th>Largest position</th><th>Peak modeled stop risk</th><th>Buys</th><th>Sells</th><th>Cancelled orders</th><th>Ending cash</th></tr></thead><tbody>{''.join(risk_rows)}</tbody></table></div>
<p><strong>A risk budget is not a loss guarantee.</strong> The existing Core rule holds through technical weakness while the thesis remains intact. A modeled stop used for entry sizing is not an automatically executed stop-loss. Gap losses and prolonged declines can therefore exceed the entry risk estimate. Concentrated holdings can amplify losses; see <a href="https://www.finra.org/investors/insights/concentration-risk">FINRA's concentration-risk explanation</a>.</p>
<p class="small">Peak modeled stop risk sums current price minus each frozen entry stop across open holdings, as a percentage of equity. It measures exposure to those reference levels, not a guaranteed maximum drawdown. Full-case cancellations: {rejected_read}.</p>
<h3>Annual returns from the continuous account</h3><div class="table-scroll"><table><thead><tr><th>Allocation</th><th>2024</th><th>2025</th><th>2026 through Oct1</th></tr></thead><tbody>{''.join(annual)}</tbody></table></div>
<p class="small">2026 includes positions carried from earlier years. It is not an untouched holdout: this historical period was already inspected during prior strategy work.</p></section>

<section id="monthly"><h2>The30% monthly test</h2><img class="chart" src="{monthly_plot}" alt="Complete monthly full-deployment returns compared with S&P 500 and the30% monthly target.">
<p>The full-deployment case's worst complete month was {pct(full['worst_complete_month_pct'])}. Its monthly target hit rate was {full['months_at_least_30_pct']}/{full['complete_months']}. Higher utilization does not create additional profitable setups.</p>
<details><summary>All monthly returns</summary><div class="table-scroll"><table><thead><tr><th>Month</th><th>Capped</th><th>Uncapped with risk</th><th>Full deployment</th><th>S&amp;P500 TR</th></tr></thead><tbody>{''.join(monthly_rows)}</tbody></table></div></details></section>

<section id="pipeline"><h2>Why cash still appears</h2>
<p>The replay evaluates every available historical index member daily. Across {days} sessions and {report['diagnostics']['analyses']:,} analyses, {zero_days} sessions had no stock meeting both the lane rules and2× R/R. The median daily count meeting those two gates was {statistics.median(eligible):g}; the maximum was {max(eligible)}. Entry timing and priority sizing can narrow that pool further.</p>
<div class="table-scroll"><table><thead><tr><th>Common gating failures</th><th>Symbol-day observations</th></tr></thead><tbody>{blocker_rows}</tbody></table></div>
<p class="small">Blockers overlap and are counts of observations, not unique stocks. The data lacks historical analyst estimates and a complete news archive. Those gaps limit the model's conviction and catalyst coverage; allocation changes cannot repair missing evidence.</p>
{gate_details}
<h3>Full-deployment holdings at the end</h3><div class="table-scroll"><table><thead><tr><th>Stock</th><th>Shares</th><th>Average entry</th><th>Last mark</th><th>Quote date</th><th>Completed stages</th></tr></thead><tbody>{closing_rows}</tbody></table></div></section>

<section id="repairs"><h2>Repairs completed before the experiment</h2>
<div class="table-scroll"><table><thead><tr><th>Defect</th><th>Repaired behavior</th></tr></thead><tbody>
<tr><th>Execution bypassed risk sizing</th><td>Final share quantity is the ceiling; display target capital cannot enlarge it. The100/88 price-stop regression now buys6 shares, rather than14.</td></tr>
<tr><th>Top20 fetched before eligibility</th><td>Paper candidate loading pages through lane, version, price and R/R eligibility before applying the ranked allocation limit.</td></tr>
<tr><th>Stale entry evidence</th><td>Paper entries require the current scoring version, recent analysis and a fresh executable quote; R/R is recomputed at that price.</td></tr>
<tr><th>Targets repeatedly trimmed holdings</th><td>Persistent stage markers and original-share tranches prevent repeated sales on unchanged targets, retain a runner and avoid buying back harvested shares above the frozen target.</td></tr>
<tr><th>Historical partial sales skipped</th><td>Replay consumes the shared suggested-shares contract and freezes entry plans, including a historical decision clock.</td></tr>
<tr><th>Future fills changed today's cash</th><td>Pending orders execute at their dated next open. Quantities use signal-close information; gaps can clip or cancel execution.</td></tr>
<tr><th>Splits adjusted twice</th><td>Native historical quotes and share entitlements are reconstructed once; entry anchors and reported shares are kept in matching units.</td></tr>
<tr><th>Filings visible too early</th><td>Acceptance timestamps are gated at the actual session close, including DST and published half days.</td></tr>
<tr><th>Discovery starved by refresh backlog</th><td>Scanner reserves discovery and broad-market slots, rotates quiet exploration and advances its cursor after completed cheap-scan work.</td></tr>
</tbody></table></div>
<p><strong>Verification:</strong> {esc(test_summary)}. Independent dated-ledger cash and equity reconcile to every decision-day account within$0.02 for all seven cases. {rr_read}. {verification_note}</p>
<p class="small">The pre-repair tests had149 passes and16 failures. Relevant fixtures now provide current scoring versions, full entry plans and quote timestamps; entry gates were retained. Exploration cursors are process-local and restart on service restart.</p>
{review_link}{json_link}
</section>

<section id="method"><h2>Method and limits on interpretation</h2><div class="grid"><div><h3>Common execution assumptions</h3><ul>
<li>Starting balance$10,000USD on {start}; daily close signals fill at the next available session open.</li>
<li>Whole-share quantities include fees and are never enlarged at the fill. Both signal and fill R/R must meet2×.</li>
<li>Current strong-fundamental, promotion, liquidity, lane and actionable-entry rules are retained. Top20 follows full eligibility.</li>
<li>No parameters were tuned to force a30% result. Seven cases were specified before the frozen run.</li>
<li>Dividends are credited on cached ex-dates; splits adjust shares and anchors once. Fractional split entitlements use the opening price as cash-in-lieu.</li>
</ul></div><div><h3>Evidence gaps that matter</h3><ul>
<li>Historical S&amp;P500 membership proxy: {coverage['prices']['price_ok']} of {coverage['prices']['universe']} symbols have cached price histories. It is not the production5,000-plus-stock universe; CRDO is absent.</li>
<li>{coverage['fundamentals']['usable_fundamental_symbols']} symbols are marked usable in the cached Valuein point-in-time sample. Analyst consensus, broad historical news and strategic-capital archives are unavailable.</li>
<li>Missing delisting/acquisition prices and terminal payouts are not reconstructed. No current data is substituted to fabricate historical outcomes.</li>
<li>Reported share counts are assumed to use their recorded period-end units and are adjusted through known splits. Vendor revisions were not independently reconciled to every filing.</li>
<li>USD returns exclude actual Avanza commissions, SEK FX conversion, tax and ISK-specific charges. The50bps case is an illustrative friction sensitivity.</li>
<li>This is retrospective model research. It does not establish future alpha or the reliability of30% monthly returns.</li>
</ul></div></div>
<p><strong>Next decision:</strong> Diagnose setup coverage and calibrate entry, target and stop horizons against point-in-time outcomes without inflating reward assumptions or weakening the 2× gate. Obtain the missing archives and evaluate the broader production universe. Once valid entries exist, compare allocation and harvesting on those same entries and require forward paper evidence of positive net excess returns with controlled drawdown.</p>
<h3>Sources and reproducibility</h3><p class="source-note">Prices: cached Yahoo daily OHLC, splits and dividends, <code>wf3_prices.json.gz</code>; benchmark<code>^SP500TR</code>. Fundamentals: cached Valuein filing/acceptance-dated sample,<code>wf3_valuein_fundamentals.json.gz</code>. Membership: staged historical start members and dated additions/removals. Closing-time schedule: <a href="https://ir.theice.com/press/news-details/2023/NYSE-Group-Announces-2024-2025-and-2026-Holiday-and-Early-Closings-Calendar/default.aspx">NYSE/ICE published2024–2026 calendar</a>.</p>
<details><summary>Exact source fingerprints and run protocol</summary><p class="small">Base repository commit<code>{esc(source['base_commit'])}</code>; scoring version<code>{esc(source['scoring_version'])}</code>. Modified source is identified by its hashes below. Result hash:<code>{esc(report['deterministic_hash'])}</code>.</p>
<div class="table-scroll"><table><tbody>{source_hashes}<tr><th>Price cache SHA256</th><td><code>{source['price_sha256']}</code></td></tr><tr><th>Fundamentals cache SHA256</th><td><code>{source['fundamentals_sha256']}</code></td></tr></tbody></table></div>
<pre style="white-space:pre-wrap;font-size:11px;line-height:1.6">{esc(json.dumps({k:v for k,v in protocol.items() if k!='source'},indent=2))}</pre>
</details></section>
<footer>ISK Trading Radar · Produced {created} · Historical allocation diagnostic · Account-equity returns, not a promised monthly yield.</footer>
</main></body></html>"""
    for before, after in {
        "at50bps": "at 50 bps", "assumes10bps": "assumes 10 bps", "reach25%": "reach 25%",
        "to50%": "to 50%", "least68": "least 68", "least2×": "least 2×", "The30%": "The 30%",
        "the30%": "the 30%", "a30%": "a 30%", "of30%": "of 30%", "the100/88": "the 100/88",
        "buys6": "buys 6", "than14": "than 14", "before149": "before 149", "had149": "had 149",
        "and16": "and 16", "before20": "before 20", "Top20": "Top 20", "to20": "to 20",
        "below2": "below 2", "both2": "both 2", "and2×": "and 2×", "S&amp;P500": "S&amp;P 500",
        "production5": "production 5", "The50bps": "The 50 bps", "through Oct1": "through Oct 1",
        "within$": "within $", "balance$": "balance $", "10,000USD": "10,000 USD",
        "calendar2024": "calendar 2024", "published2024": "published 2024", "close:16": "close: 16",
        "regular,13": "regular, 13", "version<code>": "version <code>", "commit<code>": "commit <code>",
        "benchmark<code>": "benchmark <code>", "sample,<code>": "sample, <code>",
    }.items():
        page = page.replace(before, after)
    Path(args.output).write_text(page, encoding="utf-8")
    print(json.dumps({"output": str(Path(args.output).resolve()), "bytes": len(page.encode()), "test_summary": test_summary}))


if __name__ == "__main__":
    main()
