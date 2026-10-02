#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"));sys.path.insert(0,str(ROOT))
import walkforward_backtest as wf
import wf3_offline_valuein as base

def precompute_quick(market):
    out=defaultdict(dict)
    for sym,data in market.items():
        rows=data.get("rows") or []
        closes=[];vols=[]
        for i,r in enumerate(rows):
            c=base.fv(r.get("close"));v=base.fv(r.get("volume")) or 0
            closes.append(c);vols.append(v)
            if i<20 or c is None or c<5:continue
            c5=closes[i-5]
            c20=closes[i-20]
            if c5 in (None,0) or c20 in (None,0):continue
            baseline=[x for x in vols[i-20:i] if x>0]
            av=sum(baseline)/len(baseline) if baseline else 0
            rv=v/av if av else 0;adv=c*av
            valid=[x for x in closes[i-19:i+1] if x is not None]
            near=c/max(valid) if valid else 0
            ch5=(c/c5-1)*100;ch20=(c/c20-1)*100
            scan=min(max(ch5,0),20)*2+min(max(ch20,0),40)*.7+min(rv,5)*8+(8 if near>=.98 else 0)+(5 if adv>=20_000_000 else 0)
            out[r["date"]][sym]={"symbol":sym,"price":c,"change_5_pct":ch5,"change_20_pct":ch20,
                                  "relative_volume":rv,"avg_dollar_volume_20":adv,"near_20d_high":near,"scan_score":scan}
    return out

def choose(rows,limit=80):
    rows=list(rows.values());half=max(1,limit//2)
    exp=[r for r in rows if r["avg_dollar_volume_20"]>=20_000_000 and (
        r["change_5_pct"]>=3 or r["change_20_pct"]>=7 or r["relative_volume"]>=1.5 or r["near_20d_high"]>=.985)]
    exp.sort(key=lambda r:r["scan_score"],reverse=True)
    core=[r for r in rows if r["avg_dollar_volume_20"]>=10_000_000]
    core.sort(key=lambda r:(r["avg_dollar_volume_20"],r["near_20d_high"]),reverse=True)
    out=[];seen=set()
    for r in exp[:half]:out.append(r["symbol"]);seen.add(r["symbol"])
    for r in core:
        if r["symbol"] in seen:continue
        out.append(r["symbol"]);seen.add(r["symbol"])
        if len(out)>=limit:break
    return out[:limit]

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--smoke-days",type=int,default=0)
    ap.add_argument("--output",default="backtests/results/walkforward_2024_2026_valuein_daily.json")
    ap.add_argument("--markdown",default="backtests/results/walkforward_2024_2026_valuein_daily.md")
    args=ap.parse_args()
    prices=base.load_gz(base.PRICE_PATH);funds=base.load_gz(base.FUND_PATH);market=prices["market"]
    store=base.PITFundamentals(funds);sectors=prices["membership"]["sectors"];etfs=prices["sector_etfs"]
    start=base.d(prices["period"]["start"]);end=base.d(prices["period"]["end"])
    trading=[base.d(r["date"]) for r in prices["benchmark"]["rows"] if start<=base.d(r["date"])<=end]
    if args.smoke_days:trading=trading[:args.smoke_days]
    quick=precompute_quick(market)
    members=set(prices["membership"]["start_members"])
    changes=defaultdict(list)
    for x in prices["membership"]["changes"]:changes[base.d(x["date"])].append(x)
    states=[wf.State("Current model (R/R >=2x)",2.0,False),
            wf.State("No 2x R/R floor",0.0,False),
            wf.State("Core-only (R/R >=2x)",2.0,True)]
    diagnostic={"analyses":0,"lane":0,"rr2":0,"actionable":0}
    from app.analysis_engine import position_action
    for i,day in enumerate(trading,1):
        for cd in sorted([x for x in changes if x<=day]):
            for x in changes.pop(cd):
                if x.get("removed"):members.discard(x["removed"])
                if x.get("added"):members.add(x["added"])
        dayrows={s:r for s,r in quick.get(day.isoformat(),{}).items() if s in members}
        shortlist=choose(dayrows,80)
        held=set().union(*(set(s.pos) for s in states));base_analyses={}
        for sym in set(shortlist)|held:
            a=base.analyse(sym,day,market,store,sectors,etfs)
            if not a:continue
            base_analyses[sym]=a;diagnostic["analyses"]+=1
            if a.get("lane_qualified") is True:
                diagnostic["lane"]+=1
                if float(a.get("risk_reward") or 0)>=2:
                    diagnostic["rr2"]+=1
                    act,_=position_action(a,float(a.get("price") or 0),None)
                    if act in {"BUY NOW","CONSIDER BUYING NOW","CONSIDER STARTER BUY","REVIEW BUY","BREAKOUT BUY"}:
                        diagnostic["actionable"]+=1
        for st in states:
            wf.run_state(st,day,base_analyses,set(shortlist),market)
            base.validate(st,base_analyses)
        if i%50==0 or i==len(trading):
            print("WF3_DAILY",day,i,"/",len(trading),[(s.name,round(wf.equity(s,market,day))) for s in states],diagnostic,flush=True)
    if args.smoke_days:
        print("WF3_DAILY_SMOKE_PASS",json.dumps(diagnostic),sum(len(s.trades) for s in states),flush=True);return
    benchmark=prices["benchmark"];results=[];curves={}
    for st in states:
        curve=base.daily_curve(st,market,benchmark,trading[0],trading[-1]);curves[st.name]=curve;results.append(base.stat(st.name,st,curve))
    br=wf.bench(benchmark,trading[0],trading[-1])
    for r in results:
        r["alpha_vs_benchmark_total_pct"]=round(r["total_return_pct"]-br["total_return_pct"],2)
        r["cagr_spread_vs_benchmark_pct"]=round(r["cagr_pct"]-br["cagr_pct"],2)
    rep={"version":"wf3-valuein-daily-v1","period":{"start":trading[0].isoformat(),"end":trading[-1].isoformat()},
         "methodology":{"decision_frequency":"daily close","execution":"next session open","starting_capital":wf.STARTING,
                        "transaction_cost_bps":wf.COST_BPS,"whole_shares":True,"max_position_pct":15,
                        "universe":"historical S&P 500 proxy","deep_candidates_per_day":80,
                        "fundamentals":"Valuein PIT sample; filing_date gated","price_data":"cached Yahoo daily history","min_entry_rr":2.0},
         "coverage":{"price":prices["coverage"],"fundamentals":{k:v for k,v in funds["meta"].items() if k!="coverage"}},
         "diagnostic":diagnostic,"results":results,"benchmark":br,"trades":{s.name:s.trades for s in states},"daily_curves":curves}
    core={"period":rep["period"],"diagnostic":diagnostic,"results":results,"benchmark":br,"trades":rep["trades"]}
    import hashlib
    rep["deterministic_hash"]=hashlib.sha256(json.dumps(core,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    p=Path(args.output);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(rep,indent=2))
    lines=["# 2024–2026 Daily Point-in-Time Walk-Forward Backtest","",
           f"Period: {rep['period']['start']} to {rep['period']['end']}","",
           "| Variant | End value | Total return | CAGR | Max DD | Trades | Win rate | Alpha vs S&P |",
           "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in results:
        wr="—" if r["win_rate_pct"] is None else f"{r['win_rate_pct']:.1f}%"
        lines.append(f"| {r['name']} | USD {r['end_value']:,.0f} | {r['total_return_pct']:+.1f}% | {r['cagr_pct']:+.1f}% | {r['max_drawdown_pct']:.1f}% | {r['trade_count']} | {wr} | {r['alpha_vs_benchmark_total_pct']:+.1f} pp |")
    lines.append(f"| {br['name']} | USD {br['end_value']:,.0f} | {br['total_return_pct']:+.1f}% | {br['cagr_pct']:+.1f}% | {br['max_drawdown_pct']:.1f}% | — | — | — |")
    years=sorted(br["annual_returns_pct"]);lines+=["","## Annual returns","","| Variant | "+" | ".join(years)+" |","|---|"+"|".join(["---:"]*len(years))+"|"]
    for r in results+[br]:lines.append("| "+r["name"]+" | "+" | ".join(f"{r.get('annual_returns_pct',{}).get(y,0):+.1f}%" for y in years)+" |")
    lines+=["","## Run diagnostics",f"- Deep analyses: {diagnostic['analyses']}",f"- Lane-qualified observations: {diagnostic['lane']}",
            f"- Lane-qualified with R/R >=2x: {diagnostic['rr2']}",f"- Actionable lane-qualified R/R >=2x observations: {diagnostic['actionable']}",
            "","## Important limitations",
            "- This is an S&P 500 historical-universe proxy, not the production scanner's full 5,000+ US-equity universe.",
            "- Point-in-time fundamentals are filing-date gated. Historical analyst consensus, general news, and strategic-capital archives are omitted; SEC earnings filings are a conservative catalyst proxy.",
            "- The live system scans intraday; daily-close decisions are materially closer than the earlier weekly replay but can still miss intraday setups.",
            "- Whole shares, current score sizing, 15% position cap, 10 bps costs, Core/Explosive gates and R/R >=2x buy/add rule are enforced.",
            "- Historical simulation is not a guarantee of future performance."]
    Path(args.markdown).write_text("\n".join(lines)+"\n")
    print("WF3_DAILY_RESULT="+json.dumps({"results":results,"benchmark":br,"diagnostic":diagnostic,"hash":rep["deterministic_hash"]},separators=(",",":")),flush=True)

if __name__=="__main__":main()
