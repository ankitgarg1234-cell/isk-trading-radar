#!/usr/bin/env python3
from __future__ import annotations
import gzip,json,math
from pathlib import Path
import pandas as pd
from valuein_sdk import ValueinClient

ROOT=Path(__file__).resolve().parents[1]
PRICE_PATH=ROOT/"backtests"/"staged"/"wf3_prices.json.gz"
OUT=ROOT/"backtests"/"staged"/"wf3_valuein_fundamentals.json.gz"
CONCEPTS=[
 "TotalRevenue","NetIncome","GrossProfit","OperatingIncome",
 "StockholdersEquity","TotalDebt","CommonSharesOutstanding"
]

def clean(v):
    if pd.isna(v): return None
    if hasattr(v,"isoformat"): return v.isoformat()
    if hasattr(v,"item"):
        try:return v.item()
        except:pass
    return v

def main():
    with gzip.open(PRICE_PATH,"rt",encoding="utf-8") as f:prices=json.load(f)
    symbols=sorted(set(prices["candidate_union"]))
    rows=[]
    with ValueinClient(tables=["references","filing","fact"]) as c:
        print("VALUEIN_PLAN",c.me(),flush=True)
        for n in range(0,len(symbols),60):
            chunk=symbols[n:n+60]
            quoted=",".join("'"+s.replace("'","''")+"'" for s in chunk)
            concepts=",".join("'"+x+"'" for x in CONCEPTS)
            q=f"""
            SELECT
                REPLACE(UPPER(r.symbol),'.','-') AS symbol,
                r.cik,
                f.accession_id,
                f.filing_date,
                f.accepted_at,
                f.form_type,
                f.report_date,
                fa.standard_concept,
                fa.numeric_value,
                fa.derived_quarterly_value,
                fa.period_start,
                fa.period_end,
                fa.period_span_days,
                fa.fiscal_year,
                fa.fiscal_period,
                fa.unit,
                fa.confidence_score
            FROM "references" r
            JOIN filing f ON f.entity_id=r.cik
            JOIN fact fa ON fa.accession_id=f.accession_id
            WHERE REPLACE(UPPER(r.symbol),'.','-') IN ({quoted})
              AND r.is_primary_ticker=TRUE
              AND f.filing_date >= DATE '2021-10-01'
              AND f.filing_date <= DATE '2026-10-01'
              AND f.form_type IN ('10-K','10-Q','10-K/A','10-Q/A')
              AND fa.standard_concept IN ({concepts})
              AND fa.numeric_value IS NOT NULL
            """
            df=c.run_query(q)
            if not df.empty:
                # remove exact duplicates from historical security aliases / comparative facts
                df=df.drop_duplicates(subset=[
                    "symbol","accession_id","standard_concept","period_start","period_end",
                    "numeric_value","fiscal_year","fiscal_period"
                ])
                rows.extend([{k:clean(v) for k,v in rec.items()} for rec in df.to_dict(orient="records")])
            print("VALUEIN",min(n+60,len(symbols)),"/",len(symbols),"rows",len(rows),flush=True)

    by={}
    for r in rows:by.setdefault(r["symbol"],[]).append(r)
    coverage=[]
    for sym in symbols:
        concepts={x["standard_concept"] for x in by.get(sym,[])}
        coverage.append({
            "symbol":sym,"rows":len(by.get(sym,[])),
            "has_revenue":"TotalRevenue" in concepts,
            "has_equity":"StockholdersEquity" in concepts,
            "has_shares":"CommonSharesOutstanding" in concepts,
        })
    usable=[x for x in coverage if x["has_revenue"] and x["has_equity"]]
    meta={
        "version":"wf3-valuein-v1",
        "source":"Valuein Sample point-in-time fundamentals",
        "candidate_symbols":len(symbols),
        "symbols_with_rows":sum(1 for x in coverage if x["rows"]>0),
        "usable_fundamental_symbols":len(usable),
        "usable_pct":round(len(usable)/max(1,len(symbols))*100,2),
        "row_count":len(rows),
        "concepts":CONCEPTS,
        "coverage":coverage,
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    with gzip.open(OUT,"wt",encoding="utf-8") as f:json.dump({"meta":meta,"facts":by},f,separators=(",",":"))
    print("VALUEIN_META",json.dumps({k:v for k,v in meta.items() if k!="coverage"},separators=(",",":")),flush=True)
    if meta["usable_pct"] < 80:
        raise SystemExit(f"Valuein fundamental coverage {meta['usable_pct']}% below 80%")

if __name__=="__main__":main()
