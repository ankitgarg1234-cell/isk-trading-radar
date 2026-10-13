"""Retrieve historical SEC submissions fragments when 'recent' omits prior 10-Q.

The main SEC submissions JSON can truncate old accessions after ~1000 rows.
Only source-listed historical fragment filenames are fetched; original URLs,
SHA-256 and retrieval dates are recorded. Never guesses financial facts.
"""
from __future__ import annotations
from datetime import date, timedelta
from hashlib import sha256
import json
import re

ARCHIVE_NAME = re.compile(r"^CIK[0-9]{10}-submissions-[0-9]{3,5}\.json$")
REQUIRED = ("form","accessionNumber","filingDate","reportDate","primaryDocument")


class ArchiveHistoryHold(ValueError): pass


def historical_fragment_urls(submissions, cik, *, cutoff, lookback_days=850):
    if not re.fullmatch(r"[0-9]{10}",cik):
        raise ArchiveHistoryHold("Invalid SEC CIK")
    fragments=(submissions.get("filings") or {}).get("files") or []
    if not isinstance(fragments,list):
        raise ArchiveHistoryHold("Original historical index malformed")
    dates=(cutoff-timedelta(days=lookback_days),cutoff)
    selected=[]
    for part in fragments:
        if not isinstance(part,dict):
            continue
        name=part.get("name")
        if not isinstance(name,str) or not ARCHIVE_NAME.fullmatch(name):
            continue
        if not name.startswith("CIK"+cik+"-"):
            continue
        try:
            start=date.fromisoformat(part["filingFrom"])
            end=date.fromisoformat(part["filingTo"])
        except (ValueError,KeyError,TypeError):
            continue
        if start>dates[1] or end<dates[0] or end<start:
            continue
        selected.append(("https://data.sec.gov/submissions/"+name,start,end))
    selected.sort(key=lambda record:(record[2],record[1]),reverse=True)
    return [uri for uri,_,_ in selected[:3]]


def merge_archived_filings(original, fragments):
    recent=((original.get("filings") or {}).get("recent") or {})
    if any(not isinstance(recent.get(k),list) for k in REQUIRED):
        raise ArchiveHistoryHold("Original recent filing data incomplete")
    keys=tuple(k for k,v in recent.items() if isinstance(v,list))
    n=len(recent["form"])
    if any(len(recent[k])!=n for k in keys):
        raise ArchiveHistoryHold("Original recent filing column alignment failed")
    out={k:list(recent[k]) for k in keys}
    seen=set(recent["accessionNumber"])
    manifest=[]
    for uri,raw in fragments:
        if not isinstance(raw,bytes) or len(raw)>24_000_000:
            raise ArchiveHistoryHold("Historical source fragment out of bounds")
        try:
            payload=json.loads(raw)
        except (ValueError,UnicodeError):
            raise ArchiveHistoryHold("Invalid original historical SEC JSON") from None
        if not isinstance(payload,dict):
            raise ArchiveHistoryHold("Historical SEC filing structure invalid")
        if any(not isinstance(payload.get(k),list) for k in REQUIRED):
            raise ArchiveHistoryHold("Historical SEC fragment columns missing")
        length=len(payload["form"])
        if length>15000 or any(len(payload[k])!=length for k in REQUIRED):
            raise ArchiveHistoryHold("Historical SEC accession alignment failed")
        manifest.append({"url":uri,"sha256":sha256(raw).hexdigest(),
                         "original_bytes":len(raw),"filing_rows":length})
        for i,accn in enumerate(payload["accessionNumber"]):
            if not isinstance(accn,str) or accn in seen:
                continue
            seen.add(accn)
            for key in keys:
                out[key].append(payload[key][i] if key in payload else None)
    extended=dict(original)
    extended["filings"]=dict(original["filings"])
    extended["filings"]["recent"]=out
    return extended,manifest
