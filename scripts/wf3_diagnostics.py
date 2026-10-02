#!/usr/bin/env python3
from __future__ import annotations
import json,sys,statistics
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"));sys.path.insert(0,str(ROOT))
import wf3_offline_valuein as bt
from app.analysis_engine import position_action

def main():
    prices=bt.load_gz(bt.PRICE_PATH);funds=bt.load_gz(bt.FUND_PATH)
    store=bt.PITFundamentals(funds)
    market=prices["market"];etfs=prices["sector_etfs"];sectors=prices["membership"]["sectors"]
    pref={bt.d(k):v for k,v in prices["prefilters"].items()}
    weeks=sorted(x for x in pref if x)
    blockers=Counter();fconf=Counter();zones=Counter();actions=Counter()
    rr=[];scores=[];fscores=[];top=[];weekly=[]
    analyzed=core=lane=rr2=score68=actionable=0
    for day in weeks:
        wc={"date":day.isoformat(),"requested":len(pref[day]),"analyzed":0,"core":0,"lane":0,"rr2":0,"actionable":0}
        for sym in pref[day]:
            a=bt.analyse(sym,day,market,store,sectors,etfs)
            if not a:continue
            analyzed+=1;wc["analyzed"]+=1
            sc=float(a.get("deterministic_score") or 0);rv=float(a.get("risk_reward") or 0);fs=float((a.get("breakdown") or {}).get("Fundamentals") or 0)
            scores.append(sc);rr.append(rv);fscores.append(fs);fconf[str(a.get("fundamental_confidence") or "low")]+=1;zones[str(a.get("entry_zone_status") or "")]+=1
            if sc>=68:score68+=1
            if a.get("core_quality_qualified") is True:core+=1;wc["core"]+=1
            if a.get("lane_qualified") is True:lane+=1;wc["lane"]+=1
            if a.get("lane_qualified") is True and rv>=2:rr2+=1;wc["rr2"]+=1
            for b in a.get("core_blockers") or []:blockers[b]+=1
            act,why=position_action(a,float(a.get("price") or 0),None);actions[act]+=1
            if a.get("lane_qualified") is True and rv>=2 and act in {"BUY NOW","CONSIDER BUYING NOW","CONSIDER STARTER BUY","REVIEW BUY","BREAKOUT BUY"}:
                actionable+=1;wc["actionable"]+=1
            top.append({"date":day.isoformat(),"symbol":sym,"score":sc,"fundamental":fs,"fconf":a.get("fundamental_confidence"),
                        "rr":rv,"lane":a.get("lane"),"lane_qualified":a.get("lane_qualified"),"zone":a.get("entry_zone_status"),
                        "action":act,"core_blockers":a.get("core_blockers") or [],"price":a.get("price")})
        weekly.append(wc)
    def q(v,p):
        if not v:return None
        x=sorted(v);i=min(len(x)-1,max(0,round((len(x)-1)*p)));return round(x[i],2)
    out={"weeks":len(weeks),"analyses":analyzed,"core_qualified":core,"lane_qualified":lane,"lane_rr2":rr2,"score68":score68,
         "actionable_rr2":actionable,"fundamental_confidence":dict(fconf),"top_core_blockers":blockers.most_common(20),
         "entry_zones":dict(zones),"new_position_actions":dict(actions),
         "score_quantiles":{"p10":q(scores,.1),"p50":q(scores,.5),"p90":q(scores,.9),"max":round(max(scores),2) if scores else None},
         "fundamental_quantiles":{"p10":q(fscores,.1),"p50":q(fscores,.5),"p90":q(fscores,.9),"max":round(max(fscores),2) if fscores else None},
         "rr_quantiles":{"p10":q(rr,.1),"p50":q(rr,.5),"p90":q(rr,.9),"max":round(max(rr),2) if rr else None},
         "top_candidates":sorted(top,key=lambda x:(x["lane_qualified"],x["rr"]>=2,x["score"]),reverse=True)[:50],
         "weekly":weekly}
    path=ROOT/"backtests/results/wf3_diagnostics.json";path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(out,indent=2))
    print(json.dumps({k:v for k,v in out.items() if k not in {"top_candidates","weekly"}},indent=2),flush=True)
    print("TOP",json.dumps(out["top_candidates"][:20],indent=2),flush=True)

if __name__=="__main__":main()
