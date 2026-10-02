#!/usr/bin/env python3
from __future__ import annotations
import argparse, gzip, json
from datetime import date, timedelta
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import walkforward_backtest as wf

def load_gz(path):
    with gzip.open(path,"rt",encoding="utf-8") as f:return json.load(f)

def dump_gz(path,obj):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    with gzip.open(p,"wt",encoding="utf-8") as f:json.dump(obj,f,separators=(",",":"))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--dataset",required=True);ap.add_argument("--year",type=int,required=True);ap.add_argument("--output",required=True)
    ap.add_argument("--start");ap.add_argument("--end");ap.add_argument("--shortlist-limit",type=int)
    args=ap.parse_args();ds=load_gz(args.dataset);year=args.year
    start=date.fromisoformat(args.start) if args.start else date(year,1,1)
    end=date.fromisoformat(args.end) if args.end else date(year,12,31)
    end=min(end,date.fromisoformat(ds["period"]["end"]))
    market=ds["market"];facts=ds["sec_facts"];sectors=ds["membership"]["sectors"];etfs=ds["sector_etfs"]
    fdates={s:wf.filing_dates(f,start-timedelta(days=400),end) for s,f in facts.items()}
    pref={date.fromisoformat(k):v for k,v in ds["prefilters"].items()}
    dates=sorted(d for d in pref if start<=d<=end)
    seen=set()
    for d in sorted(x for x in pref if x<start):seen.update(pref[d])
    snapshots={};generated=0;errors=0
    for i,d in enumerate(dates,1):
        shortlist=list(pref[d])
        if args.shortlist_limit:shortlist=shortlist[:args.shortlist_limit]
        seen.update(shortlist)
        base={}
        for sym in sorted(seen):
            if sym not in facts or sym not in market:continue
            try:
                a=wf.analyse(sym,d,market,facts,fdates,sectors,etfs)
                if a:base[sym]=a;generated+=1
            except Exception:errors+=1
        snapshots[d.isoformat()]={"investable":shortlist,"analyses":base}
        if i%10==0 or i==len(dates):print(f"SNAPSHOT {year} {i}/{len(dates)} seen={len(seen)} analyses={len(base)}",flush=True)
    if not snapshots:raise RuntimeError(f"No snapshots generated for {year}")
    out={"version":"wf3-snapshots-v1","year":year,"start":start.isoformat(),"end":end.isoformat(),"snapshots":snapshots,
         "stats":{"dates":len(snapshots),"analyses_generated":generated,"errors":errors}}
    dump_gz(args.output,out);print(json.dumps(out["stats"],indent=2),flush=True)

if __name__=="__main__":main()
