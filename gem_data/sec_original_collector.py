"""SEC 10-Q original-accession retrieval for GEM research (read-only).

All external responses are untrusted. Collects and hashes the *raw* SEC
submissions/filing header; intentionally does NOT certify financial concepts,
publication acceptance timezone, or competitor eligibility. The whole S&P
universe and independent quarter parser remain required for GEM pre-trade QA.
No application DB/portfolio imports, no execution or broker calls.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import os
import re
import time

import httpx


SEC_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_ARCHIVE = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{filename}"
SEC_MIN_INTERVAL = 0.15
SEC_MAX_BYTES = 6_000_000
CIK_PATTERN = re.compile(r"^[0-9]{1,10}$")
ACCESSION_PATTERN = re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")
FILENAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


class SourceUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class RawReceipt:
    provider: str
    uri: str
    requested_at: str
    completed_at: str
    bytes: int
    sha256: str
    classification: str = "RAW_SEC_DISCOVERY_NOT_PIT_CERTIFIED"


def normalize_cik(cik: str) -> str:
    s = str(cik).strip()
    if not CIK_PATTERN.fullmatch(s):
        raise ValueError("Invalid SEC CIK")
    return s.zfill(10)


def validate_sec_user_agent(user_agent: str) -> str:
    if not isinstance(user_agent, str) or "@" not in user_agent or len(user_agent.strip()) < 12:
        raise ValueError("SEC_USER_AGENT must identify an organization and contact email")
    if "\r" in user_agent or "\n" in user_agent:
        raise ValueError("SEC_USER_AGENT contains control characters")
    return user_agent.strip()


class SecOriginalCollector:
    """Request-throttled read-only collector requiring a contact user agent."""

    def __init__(self, user_agent: str, *, transport=None, timeout: float = 18.0):
        self.ua = validate_sec_user_agent(user_agent)
        self.client = httpx.Client(
            timeout=timeout, transport=transport,
            headers={"User-Agent": self.ua, "Accept": "application/json,text/html,*/*"},
            follow_redirects=False,
        )
        self.last_call = None

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def get(self, uri: str) -> tuple[RawReceipt, bytes]:
        if not uri.startswith(("https://data.sec.gov/", "https://www.sec.gov/")):
            raise ValueError("SEC collector only accepts primary SEC hosts")
        if self.last_call is not None:
            time.sleep(max(0.0, SEC_MIN_INTERVAL - (time.monotonic() - self.last_call)))
        requested = datetime.now(timezone.utc).isoformat()
        self.last_call = time.monotonic()
        try:
            with self.client.stream("GET", uri) as response:
                response.raise_for_status()
                chunks = []
                total = 0
                for part in response.iter_bytes():
                    total += len(part)
                    if total > SEC_MAX_BYTES:
                        raise SourceUnavailable("SEC original response exceeds bounded size")
                    chunks.append(part)
                raw = b"".join(chunks)
        except httpx.HTTPError as exc:
            raise SourceUnavailable("SEC source unavailable: " + type(exc).__name__) from exc
        if not raw:
            raise SourceUnavailable("SEC returned an empty response")
        receipt = RawReceipt(
            provider="SEC_ORIGINAL", uri=uri, requested_at=requested,
            completed_at=datetime.now(timezone.utc).isoformat(),
            bytes=len(raw), sha256=sha256(raw).hexdigest(),
        )
        return receipt, raw

    def submissions(self, cik: str) -> tuple[dict, RawReceipt]:
        norm = normalize_cik(cik)
        receipt, raw = self.get(SEC_SUBMISSIONS.format(cik=norm))
        try:
            data = json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise SourceUnavailable("Invalid SEC submissions JSON") from exc
        if not isinstance(data, dict) or str(data.get("cik", "")).zfill(10) != norm:
            raise SourceUnavailable("SEC submissions CIK mismatch")
        return data, receipt

    def recent_10q_manifest(self, cik: str) -> dict:
        data, receipt = self.submissions(cik)
        recent = (data.get("filings") or {}).get("recent") or {}
        required = ("form", "accessionNumber", "filingDate", "acceptanceDateTime", "primaryDocument")
        if any(not isinstance(recent.get(key), list) for key in required):
            raise SourceUnavailable("Malformed recent filing column arrays")
        n = len(recent["form"])
        if any(len(recent[key]) != n for key in required):
            raise SourceUnavailable("Malformed SEC filing column alignment")
        quarter = []
        for i in range(n):
            if recent["form"][i] not in ("10-Q", "10-Q/A"):
                continue
            accession = recent["accessionNumber"][i]
            if not isinstance(accession, str) or not ACCESSION_PATTERN.fullmatch(accession):
                raise SourceUnavailable("Malformed SEC accession identity")
            quarter.append({
                "form": recent["form"][i],
                "accession": accession,
                "filed_date_raw": recent["filingDate"][i],
                "acceptance_datetime_raw": recent["acceptanceDateTime"][i],
                "primary_document": recent["primaryDocument"][i],
            })
        return {
            "schema": "gem-sec-quarter-discovery-v1",
            "cik": normalize_cik(cik),
            "discovered_recent_10q": quarter,
            "older_submission_files": (data.get("filings") or {}).get("files", []),
            "raw_submissions_receipt": asdict(receipt),
            "publication_time_certified": False,
            "complete_filing_history": False,
            "six_quarter_inputs_certified": False,
            "paper_execution_authorized": False,
        }

    def original_header(self, cik: str, accession: str) -> tuple[RawReceipt, bytes]:
        c = normalize_cik(cik)
        if not isinstance(accession, str) or not ACCESSION_PATTERN.fullmatch(accession):
            raise ValueError("Malformed original accession")
        compact = accession.replace("-", "")
        filename = accession + "-index-headers.html"
        assert FILENAME_PATTERN.fullmatch(filename)
        uri = SEC_ARCHIVE.format(cik=int(c), accession=compact, filename=filename)
        return self.get(uri)


def save_new_evidence(directory: str, manifest: dict, receipt: RawReceipt | None = None,
                      original_header: bytes | None = None):
    """Create-only files; do not overwrite source receipts or existing snapshots."""
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    cik = manifest["cik"]
    path = out / (f"CIK{cik}-quarter-discovery.json")
    if path.exists():
        raise FileExistsError("Refusing to overwrite original SEC evidence")
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if receipt is not None and original_header is not None:
        if sha256(original_header).hexdigest() != receipt.sha256:
            raise ValueError("Original header raw bytes do not match source receipt")
        header_path = out / f"CIK{cik}-original-header-{receipt.sha256}.html"
        if header_path.exists():
            raise FileExistsError("Duplicate original header raw bytes")
        header_path.write_bytes(original_header)
    return path


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--cik", required=True)
    parser.add_argument("--evidence-directory", required=True)
    args = parser.parse_args()
    ua = os.getenv("SEC_USER_AGENT", "")
    with SecOriginalCollector(ua) as service:
        manifest = service.recent_10q_manifest(args.cik)
    destination = save_new_evidence(args.evidence_directory, manifest)
    print(json.dumps({"artifact": str(destination),
                      "10q_count": len(manifest["discovered_recent_10q"]),
                      "certified": False, "paper_trades": 0}))
