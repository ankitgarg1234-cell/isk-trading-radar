#!/usr/bin/env python3
"""Diagnostics for explicit sector-first trade path; no strategy changes."""
import json,collections,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
r=json.loads((ROOT/"backtests/results/sector_first_explicit_2022_2026.json").read_text())
ts=r["trades"];ds=r["daily"]
from itertools import groupby
reason=collections.Counter(x["reason"] for x in ts)
years=collections.defaultdict(list)
for t in ts:years[t["date"][:4]].append(t)
months=collections.defaultdict(list)
for t in ts:months[t["date"][:7]].append(t)
navmonths={}
for row in ds:navmonths[row["date"][:7]]=row["nav"]
lines=["# Explicit sector-first trade-churn audit","",
       f"- Trades: {len(ts)}",
       f"- Final NAV: {r['metrics']['end_value']:,.2f}",
       f"- Costs: {r['metrics']['costs']:,.2f}",
       "","## Causes by trade reason","","| Reason | Trades |","|---|---:|"]
for reason,n in reason.most_common():lines.append(f"| {reason} | {n} |")
lines+=["","## Yearly counts","",
  "| Year | Trades | BUY | SELL |","|---|---:|---:|---:|"]
for y,records in years.items():
    lines.append(f"| {y} | {len(records)} | {sum(x['side']=='BUY' for x in records)} | {sum(x['side']=='SELL' for x in records)} |")
lines+=["","## 2022 monthly NAV and trades","",
        "| Month | Trades | End NAV | Month return |","|---|---:|---:|---:|"]
prev=10000
for mo,end in sorted(navmonths.items()):
 if not mo.startswith('2022'):continue
 lines.append(f"| {mo} | {len(months[mo])} | \${end:,.2f} | {(end/prev-1)*100:+.2f}% |")
 prev=end
lines+=["","## 2022 monthly signal with sectors and stocks","","| Date | Sector weights | Selected stocks |","|---|---|---|"]
for row in r["monthly_signals"]:
 if not row["date"].startswith("2022"):continue
 alloc=", ".join(f"{sec} {w*100:.0f}%" for sec,w in row["sector_alloc"].items())
 lines.append(f"| {row['date']} | {alloc} | {', '.join(row['stocks'])} |")
lines+=["","## Top active trading days","",
 "| Date | Trades |","|---|---:|"]
day=collections.Counter(t["date"] for t in ts)
for d,n in day.most_common(20):lines.append(f"| {d} | {n} |")
out=ROOT/"backtests/results/sector_first_explicit_churn_audit.md"
out.write_text("\n".join(lines)+"\n")
print(out.read_text())
