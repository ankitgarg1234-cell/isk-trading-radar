#!/usr/bin/env python3
from __future__ import annotations
import gzip, json, math
from datetime import date
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ACTIVE_PATH=ROOT/"backtests/results/wf3_capital_harvest_ablation.json"
PRICE_PATH=ROOT/"backtests/staged/wf3_prices.json.gz"
OUT=ROOT/"backtests/results/wf3_regime_sleeve.json"
MD=ROOT/"backtests/results/wf3_regime_sleeve.md"

TRAIN_START=date(2024,1,2);TRAIN_END=date(2025,12,31)
HOLD_START=date(2026,1,1);HOLD_END=date(2026,10,1)
COST_BPS=10.0

ACTIVE_NAMES={
    8:"8% minimum initial",
    10:"10% minimum initial",
}
WINDOWS=(100,150,200)
RISK_ON=(0.75,1.0)
RISK_OFF=(0.0,0.25,0.5)

def loadgz(p):
    with gzip.open(p,"rt",encoding="utf-8") as f:return json.load(f)

def metrics(curve,start,end):
    rs=[r for r in curve if start<=date.fromisoformat(r["date"])<=end]
    if not rs:return None
    first=float(rs[0]["equity"]);last=float(rs[-1]["equity"])
    days=max(1,(date.fromisoformat(rs[-1]["date"])-date.fromisoformat(rs[0]["date"])).days)
    yrs=days/365.25
    ret=last/first-1;cagr=(last/first)**(1/yrs)-1 if first>0 and last>0 else -1
    peak=0;dd=0
    for r in rs:
        e=float(r["equity"]);peak=max(peak,e)
        if peak:dd=min(dd,e/peak-1)
    return {"start_value":round(first,2),"end_value":round(last,2),"total_return_pct":round(ret*100,2),
            "cagr_pct":round(cagr*100,2),"max_drawdown_pct":round(dd*100,2)}

def benchmark_metrics(rows,start,end):
    rs=[r for r in rows if start<=date.fromisoformat(r["date"])<=end]
    first=float(rs[0]["close"]);last=float(rs[-1]["close"])
    fake=[{"date":r["date"],"equity":10000*float(r["close"])/first} for r in rs]
    return metrics(fake,start,end)

def regime_map(rows,window,on,off):
    closes=[];out={}
    for r in rows:
        px=float(r["close"]);closes.append(px)
        if len(closes)<window:
            exposure=off
        else:
            ma=sum(closes[-window:])/window
            exposure=on if px>=ma else off
        out[r["date"]]={"exposure":exposure,"close":px}
    return out

def apply_sleeve(active_curve,bench_rows,window,on,off):
    regime=regime_map(bench_rows,window,on,off)
    bench={r["date"]:float(r["close"]) for r in bench_rows}
    out=[];liquid=None;prev_cash=None;prev_close=None;prev_exposure=None;switch_cost=0.0
    for r in active_curve:
        ds=r["date"]
        if ds not in bench:continue
        acash=float(r.get("cash") or 0);aeq=float(r["equity"]);stock_value=aeq-acash
        close=bench[ds]
        if liquid is None:
            liquid=acash;exposure=regime[ds]["exposure"];prev_exposure=exposure
            out.append({"date":ds,"equity":stock_value+liquid,"cash":liquid,"sleeve_exposure":exposure})
            prev_cash=acash;prev_close=close
            continue
        # Previous close's regime determines exposure over the next close-to-close return.
        exposure=prev_exposure
        br=close/prev_close-1 if prev_close else 0
        liquid *= (1 + exposure*br)
        # Active stock cash flow enters/leaves the liquid sleeve.
        liquid += acash-prev_cash
        new_exposure=regime[ds]["exposure"]
        if new_exposure != exposure:
            cost=abs(new_exposure-exposure)*max(0,liquid)*(COST_BPS/10000.0)
            liquid-=cost;switch_cost+=cost
        out.append({"date":ds,"equity":stock_value+liquid,"cash":liquid,"sleeve_exposure":new_exposure})
        prev_cash=acash;prev_close=close;prev_exposure=new_exposure
    return out,round(switch_cost,2)

def main():
    active=json.load(open(ACTIVE_PATH));prices=loadgz(PRICE_PATH);bench=prices["benchmark"]["rows"]
    btrain=benchmark_metrics(bench,TRAIN_START,TRAIN_END);bhold=benchmark_metrics(bench,HOLD_START,HOLD_END);bfull=benchmark_metrics(bench,TRAIN_START,HOLD_END)
    configs=[]
    for alloc,name in ACTIVE_NAMES.items():
        curve=active["daily_curves"][name]
        for w in WINDOWS:
            for on in RISK_ON:
                for off in RISK_OFF:
                    if off>=on:continue
                    sleeve,cost=apply_sleeve(curve,bench,w,on,off)
                    tr=metrics(sleeve,TRAIN_START,TRAIN_END);ho=metrics(sleeve,HOLD_START,HOLD_END);fu=metrics(sleeve,TRAIN_START,HOLD_END)
                    for m,b in ((tr,btrain),(ho,bhold),(fu,bfull)):
                        m["alpha_pct"]=round(m["total_return_pct"]-b["total_return_pct"],2)
                    configs.append({"active_allocation_pct":alloc,"ma_window":w,"risk_on_pct":int(on*100),"risk_off_pct":int(off*100),
                                    "sleeve_switch_cost":cost,"train":tr,"holdout":ho,"full":fu})
    eligible=[x for x in configs if x["train"]["max_drawdown_pct"]>=-15]
    ranked=sorted(eligible,key=lambda x:(x["train"]["alpha_pct"],x["train"]["cagr_pct"]),reverse=True)
    out={"version":"wf3-regime-sleeve-v1",
         "selection_rule":"rank only on 2024-2025 train alpha with max drawdown <=15%; 2026 holdout not used in selection",
         "benchmark":{"train":btrain,"holdout":bhold,"full":bfull},
         "top_train_selected":ranked[:15],"all_configs":configs}
    OUT.write_text(json.dumps(out,indent=2))
    lines=["# WF3 Regime-Managed Idle-Cash Sleeve","",
           "**2024–2025 selects the configuration; 2026 is untouched holdout.**","",
           "| Rank | Active alloc | MA | Risk-on | Risk-off | Train return | Train alpha | Train DD | 2026 return | 2026 S&P | 2026 alpha | 2026 DD | Full return | Full alpha |",
           "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for i,x in enumerate(ranked[:15],1):
        lines.append(f"| {i} | {x['active_allocation_pct']}% | {x['ma_window']}d | {x['risk_on_pct']}% | {x['risk_off_pct']}% | "
                     f"{x['train']['total_return_pct']:+.2f}% | {x['train']['alpha_pct']:+.2f} pp | {x['train']['max_drawdown_pct']:.2f}% | "
                     f"{x['holdout']['total_return_pct']:+.2f}% | {bhold['total_return_pct']:+.2f}% | {x['holdout']['alpha_pct']:+.2f} pp | "
                     f"{x['holdout']['max_drawdown_pct']:.2f}% | {x['full']['total_return_pct']:+.2f}% | {x['full']['alpha_pct']:+.2f} pp |")
    lines+=["","## Notes",
            "- The active stock trades are unchanged from the corrected 160-name backtest.",
            "- Only otherwise-idle cash receives S&P exposure.",
            "- The trend signal uses the prior close; there is no same-day look-ahead.",
            "- A 10 bps switching cost is charged whenever sleeve exposure changes.",
            "- Benchmark-sleeve gains are not fed back into active-stock sizing, which makes the overlay conservative.",
            "- Historical simulation is not a guarantee of future performance."]
    MD.write_text("\n".join(lines)+"\n")
    print("\n".join(lines),flush=True)

if __name__=="__main__":
    main()
