"""Original filing index timestamps, separate from current submissions API."""
import concurrent.futures
import json
import re
from pathlib import Path
from download_sources import ROOT, download

FILINGS = [
 ("DXCM_Q1_2024_10Q",1093557,"0001093557-24-000079"),
 ("DECK_Q1_FY2025_10Q",910521,"0000910521-24-000042"),
 ("DECK_Q2_FY2025_10Q_INELIGIBLE",910521,"0000910521-24-000059"),
 ("FSLR_Q1_2024_10Q",1274494,"0001274494-24-000022"),
 ("TTD_Q1_2025_10Q",1671933,"0001671933-25-000062"),
 ("APP_Q2_2025_10Q",1751008,"0001751008-25-000072"),
 ("DASH_Q2_2025_10Q",1792789,"0001792789-25-000012"),
 ("DASH_Q1_2025_10Q",1792789,"0001628280-25-023171"),
 ("DXCM_FY2023_10K",1093557,"0001093557-24-000021"),
 ("DECK_FY2024_10K",910521,"0000910521-24-000017"),
 ("FSLR_FY2023_10K",1274494,"0001274494-24-000004"),
 ("TTD_FY2024_10K",1671933,"0001671933-25-000029"),
 ("APP_FY2024_10K",1751008,"0001751008-25-000018"),
 ("DASH_FY2024_10K",1792789,"0001628280-25-005715"),
]

if __name__ == "__main__":
    items=[(sid+"_index",f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-','')}/{acc}-index.html") for sid,cik,acc in FILINGS]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        records=list(pool.map(download,items))
    manifest=ROOT / "download_manifest.json"
    old=json.loads(manifest.read_text());manifest.write_text(json.dumps(old+records,indent=2)+"\n")
    for r,(_,cik,acc) in zip(records,FILINGS):
        r["accession"]=acc
        if r["local_path"]:
            raw=(ROOT/r["local_path"]).read_text()
            from lxml import html
            txt=" ".join(" ".join(html.fromstring(raw).itertext()).split())
            m=re.search(r"Accepted\s+(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})",txt)
            r["accepted_eastern"] = m.group(1) if m else None
            m=re.search(r"Filing Date\s+(\d{4}-\d{2}-\d{2})",txt)
            r["filing_date"] = m.group(1) if m else None
    (ROOT / "filing_indices.json").write_text(json.dumps(records,indent=2)+"\n")
    print(json.dumps([dict(source_id=r['source_id'],accepted_eastern=r.get('accepted_eastern'),status=r['retrieval_status']) for r in records],indent=2))
