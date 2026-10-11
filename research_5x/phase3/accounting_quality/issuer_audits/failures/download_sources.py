"""Preserve original public earnings-release bytes; never overwrite a snapshot."""
import concurrent.futures
import datetime as dt
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parent
SOURCES = [
    ("DXCM_Q1_2024", "https://investors.dexcom.com/news/news-details/2024/Dexcom-Reports-First-Quarter-2024-Financial-Results/default.aspx"),
    ("DECK_Q1_FY2025", "https://ir.deckers.com/news-events/press-releases/detail/237/deckers-brands-reports-first-quarter-fiscal-year-2025-financial-results"),
    ("DECK_Q2_FY2025", "https://ir.deckers.com/news-events/press-releases/detail/234/deckers-brands-reports-second-quarter-fiscal-year-2025-financial-results"),
    ("FSLR_Q1_2024", "https://www.sec.gov/Archives/edgar/data/1274494/000162828024019623/ex991pressreleaseq1-2024.htm"),
    ("TTD_Q1_2025", "https://investors.thetradedesk.com/news-and-events/news/news-details/2025/The-Trade-Desk-Reports-First-Quarter-2025-Financial-Results/default.aspx"),
    ("APP_Q2_2025", "https://investors.applovin.com/news/news-details/2025/AppLovin-Announces-Second-Quarter-2025-Financial-Results/default.aspx"),
    ("DASH_Q2_2025", "https://ir.doordash.com/news/news-details/2025/DoorDash-Releases-Second-Quarter-2025-Financial-Results/default.aspx"),
]

def download(item):
    sid, url = item
    p = ROOT / "raw" / (sid + ".html")
    out = dict(source_id=sid, url=url, retrieved_at_utc=dt.datetime.now(dt.timezone.utc).isoformat())
    try:
        if p.exists():
            data = p.read_bytes()
            out["retrieval_status"] = "existing_snapshot"
        else:
            req = urllib.request.Request(url, headers={"User-Agent":"Research audit research-contact@example.com", "Accept":"text/html"})
            with urllib.request.urlopen(req, timeout=60) as response:
                data = response.read()
                out["http_status"] = response.status
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
            out["retrieval_status"] = "success"
        out.update(local_path=str(p.relative_to(ROOT)), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    except Exception as exc:
        out.update(retrieval_status="failed", error=str(exc), local_path=None, sha256=None)
    return out

if __name__ == "__main__":
    extra = ROOT / "additional_sources.json"
    if extra.exists():
        SOURCES += [tuple(v) for v in json.loads(extra.read_text())]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        result = list(pool.map(download,SOURCES))
    p=ROOT / "download_manifest.json"
    if p.exists():
        old=json.loads(p.read_text()); result=old+result
    p.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))
