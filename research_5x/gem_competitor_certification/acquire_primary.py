"""Opt-in bounded original SEC accession-header acquisition; no case closure.

The backlog priority uses only archived signal-time information. This sample
targets NEM (priority 1), LLY (priority 7), and AWK (priority 9, revenue mismatch).
Headers can prove original acceptance metadata; they cannot prove all facts.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .certify import ARCHIVE, HERE, csv_rows

MAX_REQUESTS = 3
MAX_RESPONSE_BYTES = 2_000_000
# Reuse the public research identification already in frozen acquire_sources.py.
DEFAULT_USER_AGENT = "ISK Trading Radar academic research ankitgarg1234@gmail.com"
SAMPLE = (("NEM", "2025-03-31"), ("LLY", "2025-02-28"), ("AWK", "2025-03-31"))


def acquisition_plan(headers_dir: Path | None = None) -> list[dict]:
    uses = csv_rows(ARCHIVE / "signal_audit.csv.gz")
    result = []
    for ticker, signal_date in SAMPLE:
        matching = [r for r in uses if r["ticker"] == ticker and r["signal_date"] == signal_date]
        if not matching:
            raise ValueError("Frozen sample accession missing")
        use = matching[0]
        cik = str(int(use["cik"]))
        accession = use["accession"]
        base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/"
        url = base + f"{accession}-index-headers.html"
        if headers_dir is not None:
            headers = json.loads((headers_dir / "acquisition_summary.json").read_text())["records"]
            header = next(r for r in headers if r["accession"] == accession and r["status"] == "ACQUIRED_PENDING_REVIEW")
            raw = (headers_dir / header["raw_path"]).read_bytes()
            if hashlib.sha256(raw).hexdigest() != header["response_sha256"]:
                raise ValueError("Acquired header hash mismatch")
            filenames = set(re.findall(r"<FILENAME>([^\s<]+_htm\.xml)", html.unescape(raw.decode())))
            if len(filenames) != 1:
                raise ValueError("Original header must name one XBRL instance")
            url = base + filenames.pop()
        result.append({"ticker": ticker, "signal_date": signal_date, "cik": use["cik"],
                       "accession": accession, "url": url})
    return result


def acquire(output: Path, user_agent: str, max_requests: int = MAX_REQUESTS, transport: str = "urllib", headers_dir: Path | None = None) -> dict:
    if not 1 <= max_requests <= MAX_REQUESTS:
        raise ValueError("Bounded acquisition permits 1 through 3 requests")
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for item in acquisition_plan(headers_dir)[:max_requests]:
        key = hashlib.sha256(item["url"].encode()).hexdigest()
        record_path = output / f"{key}.json"
        if record_path.exists():
            saved = json.loads(record_path.read_text())
            if saved.get("url") != item["url"] or saved.get("accession") != item["accession"]:
                raise ValueError("Saved request identity drift")
            if saved.get("status") == "ACQUIRED_PENDING_REVIEW":
                source_name = saved.get("raw_path", "")
                if Path(source_name).name != source_name:
                    raise ValueError("Saved source path escapes the acquisition directory")
                raw = (output / source_name).read_bytes()
                if hashlib.sha256(raw).hexdigest() != saved.get("response_sha256"):
                    raise ValueError("Saved SEC response hash mismatch")
            records.append(saved)
            continue
        record = {**item, "requested_at_utc": datetime.now(timezone.utc).isoformat(), "transport": transport,
                  "automatic_case_certification": False, "network_retry_count": 0}
        request = urllib.request.Request(item["url"], headers={"User-Agent": user_agent, "Accept": "text/html"})
        try:
            if transport == "system-curl":
                # System TLS trust is useful where the standalone Python runtime
                # lacks a CA bundle. Certificate verification stays enabled.
                with tempfile.TemporaryDirectory() as tmp:
                    download = Path(tmp) / "response.html"
                    completed = subprocess.run(["curl", "--silent", "--show-error", "--max-time", "15",
                                                "--max-filesize", str(MAX_RESPONSE_BYTES), "--user-agent", user_agent,
                                                "--output", str(download), "--write-out", "%{http_code}", item["url"]],
                                               capture_output=True, text=True, timeout=18, check=False)
                    if completed.returncode:
                        raise RuntimeError(completed.stderr[:1000])
                    http_status = int(completed.stdout)
                    raw = download.read_bytes()
            elif transport == "urllib":
                with urllib.request.urlopen(request, timeout=15) as response:
                    raw = response.read(MAX_RESPONSE_BYTES + 1)
                    http_status = response.status
            else:
                raise ValueError("Unsupported transport")
            if len(raw) > MAX_RESPONSE_BYTES:
                raise ValueError("Bounded header size exceeded")
            digest = hashlib.sha256(raw).hexdigest()
            source_path = output / f"{digest}.html"
            if not source_path.exists():
                with source_path.open("xb") as stream:
                    stream.write(raw)
            record.update(status="ACQUIRED_PENDING_REVIEW" if http_status == 200 else
                          "SOURCE_BLOCKED" if http_status in {403, 429} else "HTTP_ERROR",
                          http_status=http_status, response_sha256=digest,
                          response_bytes=len(raw), raw_path=source_path.name,
                          retrieved_at_utc=datetime.now(timezone.utc).isoformat())
        except urllib.error.HTTPError as error:
            record.update(status="SOURCE_BLOCKED" if error.code in {403, 429} else "HTTP_ERROR",
                          http_status=error.code, error=str(error))
        except Exception as error:
            record.update(status="TRANSPORT_FAILED", error=f"{type(error).__name__}: {error}")
        record["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
        with record_path.open("x") as stream:
            stream.write(json.dumps(record, indent=2, sort_keys=True) + "\n")
        records.append(record)
        time.sleep(.5)
    summary = {"requested_accessions": len(records),
               "acquired_raw_responses": sum(r["status"] == "ACQUIRED_PENDING_REVIEW" for r in records),
               "acquired_raw_header_responses": sum(r["status"] == "ACQUIRED_PENDING_REVIEW" for r in records) if headers_dir is None else 0,
               "acquired_raw_xbrl_responses": sum(r["status"] == "ACQUIRED_PENDING_REVIEW" for r in records) if headers_dir is not None else 0,
               "new_full_case_certifications": 0, "records": records,
               "note": "Failed requests remain evidence; reruns reuse saved records without unbounded retries"}
    (output / "acquisition_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "primary_acquisition")
    parser.add_argument("--max-requests", type=int, default=MAX_REQUESTS)
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    parser.add_argument("--transport", choices=("urllib", "system-curl"), default="urllib")
    parser.add_argument("--headers-dir", type=Path, help="Acquire original XBRL instances named in retained accession headers")
    args = parser.parse_args()
    summary = acquire(args.output, args.user_agent, args.max_requests, args.transport, args.headers_dir)
    print(json.dumps({k: v for k, v in summary.items() if k != "records"}, indent=2))


if __name__ == "__main__":
    main()
