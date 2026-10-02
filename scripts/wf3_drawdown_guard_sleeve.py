#!/usr/bin/env python3
from __future__ import annotations
import gzip, json
from datetime import date
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ACTIVE_PATH=ROOT/"backtests/results/wf3_capital_harvest_ablation.json"
PRICE_PATH=ROOT/"backtests/staged/wf3_prices.json.gz"
OUT=ROOT/"backtests/results/wf3_drawdown_guard_sleeve.json"
MD=ROOT/"backtests/results/wf3_drawdown_guard_sleeve.md"

TRAIN_START=date(2024,1,2);TRAIN_END=date(2025,12,31)
HOLD_START=date(2026,1,1);HOLD_END=date(2026,10,1)
COST_BPS=10.0
ACTIVE_NAMES={
    8:"8% minimum initial",
    10:"10% minimum initial",
    12:"12% minimum initial",
    15:"15% minimum initial",
}
TRIGGERS=(0.04,0.06,0.08,0.10)
REENTRIES=(0.01,0.02,0.03,0.04)
RISK_OFF=(0.0,0.25,0.5)

def loadgz(p):
    with gzip.open(p,"rt",encoding="utf-8") as f:return json.load(f)

def metrics(curve,start,end):
    rs=[r for r in curve if start<=date.fromisoformat(r["date"])<=end]
    first=float(rs[0]["equity"]);last=float(rs[-1]["equity"])
    days=max(1,(date.fromisoformat(rs[-1]["date"])-date.fromisoformat(rs[0]["date"])).days)
    yrs=days/365.25;ret=last/first-1;cagr=(last/first)**(1/yrs)-1 if first>0 and last>0 else -1
    peak=0;dd=0
    for r in rs:
        e=float(r["equity"]);peak=max(peak,e);dd=min(dd,e/peak-1 if peak else 0)
    return {"start_value":round(first,2),"end_value":round(last,2),"total_return_pct":round(ret*100,2),
            "cagr_pct":round(cagr*100,2),"max_drawdown_pct":round(dd*100,2)}

def bench_metrics(rows,start,end):
    rs=[r for r in rows if start<=date.fromisoformat(r["date"])<=end]
    first=float(rs[0]["close"])
    return metrics([{"date":r["date"],"equity":10000*float(r["close"])/first} for r in rs],start,end)

def exposure_map(rows,trigger,reentry,risk_off):
    high=0.0;risk_on=True;out={}
    for r in rows:
        px=float(r["close"]);high=max(high,px);dd=px/high-1 if high else 0
        if risk_on and dd<=-trigger:
            risk_on=False
        elif not risk_on and dd>=-reentry:
            risk_on=True
        out[r["date"]]={"exposure":1.0 if risk_on else risk_off,"benchmark_drawdown":dd}
    return out

def apply(active_curve,bench_rows,trigger,reentry,risk_off):
    em=exposure_map(bench_rows,trigger,reentry,risk_off)
    bench={r["date"]:float(r["close"]) for r in bench_rows}
    out=[];liquid=None;prev_cash=None;prev_close=None;prev_exp=None;cost_total=0.0
    for r in active_curve:
        ds=r["date"]
        if ds not in bench:continue
        acash=float(r.get("cash") or 0);aeq=float(r["equity"]);stock=aeq-acash;close=bench[ds]
        if liquid is None:
            liquid=acash;prev_cash=acash;prev_close=close;prev_exp=em[ds]["exposure"]
            out.append({"date":ds,"equity":stock+liquid,"cash":liquid,"sleeve_exposure":prev_exp});continue
        # Prior close state sets exposure for today's benchmark return: no look-ahead.
        br=close/prev_close-1 if prev_close else 0
        liquid *= (1 + prev_exp*br)
        liquid += acash-prev_cash
        new_exp=em[ds]["exposure"]
        if new_exp!=prev_exp:
            cost=abs(new_exp-prev_exp)*max(0,liquid)*(COST_BPS/10000.0)
            liquid-=cost;cost_total+=cost
        out.append({"date":ds,"equity":stock+liquid,"cash":liquid,"sleeve_exposure":new_exp})
        prev_cash=acash;prev_close=close;prev_exp=new_exp
    return out,round(cost_total,2)

def main():
    active=json.load(open(ACTIVE_PATH));prices=loadgz(PRICE_PATH);bench=prices["benchmark"]["rows"]
    btrain=bench_metrics(bench,TRAIN_START,TRAIN_END);bhold=bench_metrics(bench,HOLD_START,HOLD_END);bfull=bench_metrics(bench,TRAIN_START,HOLD_END)
    configs=[]
    for alloc,name in ACTIVE_NAMES.items():
        curve=active["daily_curves"][name]
        for trigger in TRIGGERS:
            for reentry in REENTRIES:
                if reentry>=trigger:continue
                for off in RISK_OFF:
                    c,cost=apply(curve,bench,trigger,reentry,off)
                    tr=metrics(c,TRAIN_START,TRAIN_END);ho=metrics(c,HOLD_START,HOLD_END);fu=metrics(c,TRAIN_START,HOLD_END)
                    for m,b in ((tr,btrain),(ho,bhold),(fu,bfull)):m["alpha_pct"]=round(m["total_return_pct"]-b["total_return_pct"],2)
                    configs.append({"active_allocation_pct":alloc,"trigger_drawdown_pct":int(trigger*100),
                                    "reentry_drawdown_pct":int(reentry*100),"risk_off_exposure_pct":int(off*100),
                                    "switch_cost":cost,"train":tr,"holdout":ho,"full":fu})
    eligible=[x for x in configs if x["train"]["max_drawdown_pct"]>=-15]
    ranked=sorted(eligible,key=lambda x:(x["train"]["alpha_pct"],x["train"]["cagr_pct"]),reverse=True)
    out={"version":"wf3-drawdown-guard-v1",
         "selection_rule":"2024-2025 train alpha only, with train max drawdown <=15%; 2026 holdout untouched",
         "benchmark":{"train":btrain,"holdout":bhold,"full":bfull},"top_train_selected":ranked[:20],"all_configs":configs}
    OUT.write_text(json.dumps(out,indent=2))
    lines=["# WF3 Drawdown-Guarded Idle-Cash Sleeve","",
           "**2024–2025 selects; 2026 is untouched holdout.**","",
           "| Rank | Active alloc | Trigger | Re-enter | Risk-off sleeve | Train return | Train alpha | Train DD | 2026 return | 2026 S&P | 2026 alpha | 2026 DD | Full return | Full alpha |",
           "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for i,x in enumerate(ranked[:20],1):
        lines.append(f"| {i} | {x['active_allocation_pct']}% | -{x['trigger_drawdown_pct']}% | -{x['reentry_drawdown_pct']}% | {x['risk_off_exposure_pct']}% | "
                     f"{x['train']['total_return_pct']:+.2f}% | {x['train']['alpha_pct']:+.2f} pp | {x['train']['max_drawdown_pct']:.2f}% | "
                     f"{x['holdout']['total_return_pct']:+.2f}% | {bhold['total_return_pct']:+.2f}% | {x['holdout']['alpha_pct']:+.2f} pp | "
                     f"{x['holdout']['max_drawdown_pct']:.2f}% | {x['full']['total_return_pct']:+.2f}% | {x['full']['alpha_pct']:+.2f} pp |")
    lines+=["","## Notes",
            "- Stock selections and stock trades are unchanged.",
            "- The sleeve is 100% S&P while risk-on; only the otherwise-idle cash is affected.",
            "- The previous close's benchmark drawdown controls today's sleeve exposure.",
            "- Risk-off exposure is 0/25/50% depending on the tested configuration.",
            "- Re-entry uses hysteresis to reduce whipsaw.",
            "- 10 bps cost is charged on sleeve exposure changes.",
            "- Historical simulation is not a guarantee of future performance."]
    MD.write_text("\n".join(lines)+"\n");print("\n".join(lines),flush=True)

if __name__=="__main__":main()
