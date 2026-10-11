"""Append-only original-source download, no trading or production imports.

Run with bundled Python. SEC Archives can reject HTTP clients; failures are retained.
Web-reviewed numbers remain distinct from byte-level downloads.
"""
import datetime, gzip, hashlib, json, pathlib, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
SOURCES = [
 ('NVDA_Q4_release','NVDA','2024-02-21','https://investor.nvidia.com/news/press-release-details/2024/NVIDIA-Announces-Financial-Results-for-Fourth-Quarter-and-Fiscal-2024/default.aspx'),
 ('NVDA_Q4_SEC_release','NVDA','2024-02-21','https://www.sec.gov/Archives/edgar/data/1045810/000104581024000028/q4fy24pr.htm'),
 ('NVDA_FY24_10K','NVDA','2024-02-21','https://www.sec.gov/Archives/edgar/data/1045810/000104581024000029/nvda-20240128.htm'),
 ('ZBRA_Q3_release','ZBRA','2024-10-29','https://investors.zebra.com/news-and-events/news/news-details/2024/Zebra-Technologies-Announces-Third-Quarter-2024-Results/default.aspx'),
 ('ZBRA_Q3_SEC_release','ZBRA','2024-10-29','https://www.sec.gov/Archives/edgar/data/877212/000087721224000162/zbraex99120240928.htm'),
 ('ZBRA_Q2_release','ZBRA','2024-07-30','https://www.sec.gov/Archives/edgar/data/877212/000087721224000149/zbraex99120240629.htm'),
 ('ZBRA_Q3_10Q','ZBRA','2024-10-29','https://www.sec.gov/Archives/edgar/data/877212/000087721224000164/zbra-20240928.htm'),
 ('PLTR_Q1_release','PLTR','2025-05-05','https://www.sec.gov/Archives/edgar/data/1321655/000132165525000063/a2025q1ex991pressrelease.htm'),
 ('PLTR_Q1_10Q','PLTR','2025-05-06','https://www.sec.gov/Archives/edgar/data/1321655/000132165525000066/pltr-20250331.htm'),
 ('PLTR_Q2_release','PLTR','2025-08-04','https://www.sec.gov/Archives/edgar/data/1321655/000132165525000105/a2025q2ex991pressrelease.htm'),
 ('PLTR_Q2_10Q','PLTR','2025-08-05','https://www.sec.gov/Archives/edgar/data/1321655/000132165525000106/pltr-20250630.htm'),
 ('NOW_Q4_release','NOW','2024-01-24','https://www.servicenow.com/content/dam/servicenow-assets/public/en-us/doc-type/other-document/earnings/Q4-2023-Earnings-Release.pdf'),
 ('NOW_Q4_SEC_release','NOW','2024-01-24','https://www.sec.gov/Archives/edgar/data/1373715/000137371524000009/erq4fy23.htm'),
 ('NOW_FY23_10K','NOW','2024-01-25','https://www.sec.gov/Archives/edgar/data/1373715/000137371524000030/now-20231231.htm'),
 ('SNPS_Q1_release','SNPS','2024-02-21','https://investor.synopsys.com/news/news-details/2024/Synopsys-Posts-Financial-Results-for-First-Quarter-Fiscal-Year-2024/default.aspx'),
 ('SNPS_Q1_SEC_release','SNPS','2024-02-21','https://www.sec.gov/Archives/edgar/data/883241/000119312524041524/d759623dex991.htm'),
 ('SNPS_Q1_10Q','SNPS','2024-02-23','https://www.sec.gov/Archives/edgar/data/883241/000088324124000013/snps-20240131.htm'),
 ('CCL_Q4_release','CCL','2023-12-21','https://www.sec.gov/Archives/edgar/data/815097/000081509723000071/a20234qearningsrelease8-k.htm'),
 ('CCL_FY23_10K','CCL','2024-01-26','https://www.sec.gov/Archives/edgar/data/815097/000081509724000011/ccl-20231130.htm'),
 ('RCL_Q3_release','RCL','2023-10-26','https://www.sec.gov/Archives/edgar/data/884887/000088488723000054/a2023q3earningsrelease8-k.htm'),
 ('RCL_Q3_10Q','RCL','2023-10-26','https://www.sec.gov/Archives/edgar/data/884887/000088488723000056/rcl-20230930.htm'),
]

# Index clocks own timestamp certification; API acceptanceDateTime can disagree.
for sid,ticker,date,url in list(SOURCES):
    if 'www.sec.gov/Archives/edgar/data/' not in url:continue
    directory=url.rsplit('/',1)[0];compact=directory.rsplit('/',1)[-1]
    accession=compact[:10]+'-'+compact[10:12]+'-'+compact[12:]
    if any(s[3]==directory+'/'+accession+'-index.html' for s in SOURCES):continue
    SOURCES.append((sid+'_index',ticker,date,directory+'/'+accession+'-index.html'))

def main():
    manifest = ROOT / 'download_manifest.json'
    old = json.loads(manifest.read_text()) if manifest.exists() else []
    existing = {r['source_id'] for r in old if r['status'] == 'downloaded'}
    for sid, ticker, date, url in SOURCES:
        if sid in existing:
            continue
        rec = dict(source_id=sid,ticker=ticker,publication_date=date,url=url,
                   retrieved_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'Academic historical financial research contact research@example.com','Accept-Encoding':'identity'})
            with urllib.request.urlopen(req, timeout=35) as response:
                raw=response.read(); rec['http_status']=response.status
                rec['content_type']=response.headers.get('Content-Type','')
            path=ROOT/'raw'/(sid+'.bin.gz');path.parent.mkdir(exist_ok=True)
            path.write_bytes(gzip.compress(raw,mtime=0))
            rec.update(status='downloaded',byte_count=len(raw),raw_sha256=hashlib.sha256(raw).hexdigest(),local_path=str(path.relative_to(ROOT)))
        except Exception as exc:
            rec.update(status='failed',error=str(exc))
        old.append(rec);manifest.write_text(json.dumps(old,indent=2)+'\n')
        print(sid,rec['status'],rec.get('byte_count',rec.get('error')))

if __name__=='__main__':
    main()
