#!/usr/bin/env python3
"""Accession-specific SEC XBRL fallback for *HOLD* positive-momentum issuers.

Default: offline read-only PLAN. No SEC web requests or edgartools import.
Optional --fetch explicitly requires GEM_SEC_XBRL_FALLBACK_ENABLED=yes,
EDGAR_IDENTITY from a secret manager, and --output-dir. Never modifies Neon,
GEM source QA, the ranking, production deployment or a brokerage account.

  python scripts/gem_sec_edgartools_fallback_cli.py --signal-day 2026-09-30 --limit 5
  # Operator-only after dry run and resource/rate-limit approval:
  # GEM_SEC_XBRL_FALLBACK_ENABLED=yes EDGAR_IDENTITY='Organization contact@domain' \
  # python scripts/gem_sec_edgartools_fallback_cli.py --signal-day 2026-09-30 \
  #   --limit 5 --fetch --max-filings 4 --output-dir /secure/review
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sys
import time

from gem_data.gem_edgartools_exception import (
    plan_filing_exceptions, fetch_filing_xbrl, SECXBRLHold)
from scripts.gem_sec_momentum_parity_cli import (
    read_only_priority_parity, read_priority_receipts)
from scripts.gem_sec_momentum_priority_cli import EXPERIMENT

CIK = re.compile(r"^[0-9]{10}$")


def plan_exception_batch(*,signal_day,limit=5,offset=0,dsn=None):
    """Review only unresolved SEC evidence of the already momentum-prioritized set."""
    if not isinstance(signal_day,str):
        raise ValueError("Signal day missing")
    date.fromisoformat(signal_day)
    if (type(limit) is not int or not 1 <= limit <= 10
            or type(offset) is not int or offset < 0):
        raise ValueError("Limit must be 1–10, offset nonnegative")
    dsn = dsn if dsn is not None else os.getenv("GEM_READONLY_DATABASE_URL","")
    if not dsn.startswith("postgresql://gem_web_readonly:"):
        raise ValueError("GEM read-only scoped database role required")
    result = read_only_priority_parity(signal_day=signal_day,limit=limit,
                                       offset=offset,dsn=dsn)
    if (result.get("scope") != "PROVISIONAL_MOMENTUM_FIRST_SEC_DIAGNOSTIC_NOT_CERTIFICATION"
            or result.get("trading_authorized") is not False
            or result.get("final_exclusions_certified") != 0):
        raise ValueError("Momentum SEC workload has unexpected authorizations")
    held = [r for r in result["issuer_reports"] if r["status"] == "HOLD"]
    # Some HOLDs are missing a paired SEC original; separate missing-source
    # from a valid original submissions receipt and do not manufacture accessions.
    plans=[]
    if held:
        import psycopg
        with psycopg.connect(dsn,connect_timeout=10) as conn:
            with conn.cursor() as cur:
                cur.execute("SET TRANSACTION READ ONLY")
                cur.execute("SET LOCAL statement_timeout=30000")
            for r in held:
                cik=r.get("cik")
                if not isinstance(cik,str) or not CIK.fullmatch(cik):
                    raise ValueError("HOLD issuer CIK invalid")
                if not isinstance(r.get("r63_preliminary"),(int,float)) or r["r63_preliminary"] <= 0:
                    raise ValueError("Unproven momentum-positive HOLD in priority report")
            unique = list(dict.fromkeys(r["cik"] for r in held))
            originals = dict(read_priority_receipts(conn,unique))
            cached={}
            for entry in held:
                cik=entry["cik"]
                if cik not in cached:
                    pair=originals[cik]
                    if "submissions" not in pair:
                        cached[cik]={"status":"HOLD_NO_ORIGINAL_SUBMISSIONS",
                                     "reason":"Original SEC submissions ZIP receipt missing",
                                     "filings":[]}
                    else:
                        try:
                            cached[cik]=plan_filing_exceptions(
                                pair["submissions"],cik,signal_day)
                        except SECXBRLHold as exc:
                            cached[cik]={"status":"HOLD_UNRESOLVED_FILING_SELECTION",
                                         "reason":str(exc)[:160],"filings":[]}
                plans.append({"ticker":entry["ticker"],"cik":cik,
                              "r63_preliminary":entry["r63_preliminary"],
                              **cached[cik]})
    status=dict(Counter(x["status"] for x in plans))
    return {"schema":"gem-sec-edgartools-exception-batch-v1",
            "signal_day":signal_day,"limit":limit,"offset":offset,
            "price_qa_status":"UNCERTIFIED_PROVISIONAL_PRIORITY_ONLY",
            "targeted_HOLD_tickers":len(held),
            "unique_targeted_CIKs":len(set(x["cik"] for x in plans)),
            "planned":plans,"statuses":status,
            "unresolved_price_competitors":result["price_repair_competitors_not_cleared"],
            "unverified_negative_competitors":result["deferred_negative_competitors_not_certified"],
            "trading_authorized":False,"source_certified":False,
            "reviewer_signed":False,"broker_orders_sent":0}


def _write_new_evidence(outdir, item):
    """Append-only local JSON evidence; never overwrite an existing accession."""
    path=Path(outdir)
    if not path.is_dir() or path.is_symlink():
        raise ValueError("Output must be an existing non-symlink review directory")
    digest=sha256(json.dumps(
        item,sort_keys=True,separators=(",",":"),allow_nan=False
    ).encode()).hexdigest()
    name="sec-xbrl-"+item["cik"]+"-"+item["accession"]+"-"+digest[:16]+".json"
    target=path/name
    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as handle:
            json.dump(item,handle,sort_keys=True,allow_nan=False)
            handle.write("\n")
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return {"file":name,"evidence_sha256":digest,"status":item["status"]}


def fetch_explicitly_approved(batch,*,max_filings=4,outdir=None,
                              filing_loader=None,sleep_fn=time.sleep):
    """Only operator path that can call SEC through EdgarTools."""
    if (os.getenv("GEM_SEC_XBRL_FALLBACK_ENABLED") != "yes"
            or not os.getenv("EDGAR_IDENTITY","").strip()):
        raise ValueError("Explicit SEC fallback opt-in and identity required")
    if type(max_filings) is not int or not 1 <= max_filings <= 8:
        raise ValueError("Exceeded bounded SEC filing request limit")
    if not outdir:
        raise ValueError("Safe existing output directory required")
    if (not isinstance(batch,dict)
            or batch.get("schema") != "gem-sec-edgartools-exception-batch-v1"
            or batch.get("trading_authorized") is not False):
        raise ValueError("Untrusted exception batch")
    from edgar import set_identity
    set_identity(os.environ["EDGAR_IDENTITY"])
    unique={}
    for plan in batch["planned"]:
        if plan["status"]!="PLANNED_UNCERTIFIED":
            continue
        for filing in plan["filings"]:
            accession=filing["accession"]
            if accession in unique and unique[accession]!=filing:
                raise ValueError("Conflicting metadata for same SEC accession")
            unique[accession]=filing
    # No silently truncated workloads; remaining filings are explicitly held.
    targets=list(unique.values())[:max_filings]
    outcomes=[]
    for n,item in enumerate(targets):
        if n:
            sleep_fn(1.0)  # EdgarTools may make multiple internal HTTP requests
        try:
            evidence=fetch_filing_xbrl(item,filing_loader=filing_loader)
            outcomes.append({"accession":item["accession"],
                             **_write_new_evidence(outdir,evidence)})
        except (SECXBRLHold,ValueError,OSError):
            outcomes.append({"accession":item["accession"],
                             "status":"HOLD_EXTRACTION_OR_STORAGE_FAILED"})
        except Exception:
            # SDK transport, parsing, timeout, or rate limit error: fail closed.
            outcomes.append({"accession":item["accession"],
                             "status":"HOLD_EDGARTOOLS_PROVIDER_ERROR"})
            break
    return {"schema":"gem-edgartools-fetch-result-v1",
            "attempted":len(outcomes),"remaining_unfetched":
                len(unique)-len(outcomes),
            "outcomes":outcomes,"independently_verified":False,
            "source_certified":False,"trading_authorized":False,
            "broker_orders_sent":0}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--signal-day",required=True)
    p.add_argument("--limit",type=int,default=5)
    p.add_argument("--offset",type=int,default=0)
    p.add_argument("--fetch",action="store_true")
    p.add_argument("--max-filings",type=int,default=4)
    p.add_argument("--output-dir")
    args=p.parse_args(argv)
    plan=plan_exception_batch(signal_day=args.signal_day,
                              limit=args.limit,offset=args.offset)
    if not args.fetch:
        print(json.dumps(plan,sort_keys=True,allow_nan=False))
        return 0
    data=fetch_explicitly_approved(plan,max_filings=args.max_filings,
                                   outdir=args.output_dir)
    print(json.dumps(data,sort_keys=True,allow_nan=False))
    return 0 if all(x["status"]=="EXTRACTED_FOR_INDEPENDENT_QA_ONLY"
                    for x in data["outcomes"]) else 3


if __name__=="__main__":
    try:
        sys.exit(main())
    except (ValueError,RuntimeError) as exc:
        print("GEM SEC XBRL exception HOLD: "+str(exc)[:180],file=sys.stderr)
        sys.exit(2)
