"""Bounded public-primary retrieval; never substitutes failed/blocked sources.

Run explicitly with network permission. A snapshot retrieved in2026 preserves
the reviewed original dated page, not proof of a historical web archive.
"""
import concurrent.futures
import gzip
import hashlib
import json
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from build_audit import SOURCES

try:
    import certifi
    TLS_CONTEXT=ssl.create_default_context(cafile=certifi.where())
except ImportError:
    TLS_CONTEXT=ssl.create_default_context()

HERE=Path(__file__).resolve().parent
RAW=HERE/"raw"

def one(s):
    url=s["url"]
    base=dict(source_id=s["source_id"],source_url=url,retrieved_utc=datetime.now(timezone.utc).isoformat(),historical_archive_certification=False)
    path=RAW/(s["source_id"]+".html.gz")
    if path.exists():
        body=gzip.decompress(path.read_bytes())
        return dict(base,status="retained_existing_current_snapshot",path=str(path.relative_to(HERE)),uncompressed_bytes=len(body),uncompressed_sha256=hashlib.sha256(body).hexdigest(),gzip_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    req=urllib.request.Request(url,headers={"User-Agent":"Phase3QuantitativeResearch/1.0 PublicFinancialStatementsAudit","Accept":"text/html"})
    try:
        with urllib.request.urlopen(req,timeout=25,context=TLS_CONTEXT) as resp:
            body=resp.read()
            if not body or b"<html" not in body.lower():
                return dict(base,status="unexpected_response_not_retained",http_status=resp.status,uncompressed_bytes=len(body))
            path.write_bytes(gzip.compress(body,mtime=0))
            return dict(base,status="retained_current_snapshot_of_dated_original_document",http_status=resp.status,path=str(path.relative_to(HERE)),uncompressed_bytes=len(body),uncompressed_sha256=hashlib.sha256(body).hexdigest(),gzip_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    except Exception as exc:
        return dict(base,status="retrieval_failed_no_substitute",error=str(exc),exception=type(exc).__name__)
    finally:
        time.sleep(.35)

def main():
    RAW.mkdir(exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        rows=list(pool.map(one,SOURCES))
    result=dict(schema="primary_document_retention_v1",snapshots=rows,limitation="2026 retrieval of original dated release/accession pages; no historical web archive or all-fact source certification inferred. Failed binary downloads do not negate targeted web review, and remain disclosed.")
    (HERE/"download_manifest.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(dict(retained=sum(r["status"].startswith("retained") for r in rows),failed=sum(not r["status"].startswith("retained") for r in rows),total=len(rows))))

if __name__=="__main__":main()
