"""Retrieve public SPGM N-PORT and publisher archives; never contact EODHD.

Default is a cache-only rebuild. Raw responses and manifests belong exclusively
under the Git-ignored research/eodhd_output directory.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener
from xml.etree import ElementTree as ET

SERIES = "S000036082"
REGISTRANT = "1168164"
ROOT = Path(__file__).resolve().parent / "eodhd_output"
DEFAULT_OUTPUT = ROOT / "spgm_proxy"
DOMAINS = {"www.sec.gov", "web.archive.org", "www.ssga.com", "www.msci.com"}
LABEL = "SPGM historical ETF holdings proxy"
UA = "isk-trading-radar SPGMResearch (https://github.com/ankitgarg1234-cell/isk-trading-radar)"


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)


def allowed_url(url):
    p = urlsplit(url)
    if p.scheme != "https" or p.hostname not in DOMAINS or p.username or p.password:
        raise ValueError("Only approved unauthenticated public research HTTPS sources are allowed")


def public_body(data):
    """Archive responses can retain HTTP gzip encoding; preserve raw on disk."""
    if data.startswith(b"\x1f\x8b"):
        data = gzip.decompress(data)
        if len(data) > 85_000_000:
            raise ValueError("Decoded response exceeds size limit")
    return data


class RestrictedRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        allowed_url(newurl)  # Validate BEFORE following, including any EODHD URL.
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class PublicCache:
    def __init__(self, output=DEFAULT_OUTPUT, fetch=False):
        self.output = Path(output).resolve()
        if ROOT.resolve() not in self.output.parents:
            raise ValueError("Output must be inside Git-ignored research/eodhd_output")
        self.output.mkdir(parents=True, exist_ok=True)
        self.fetch = fetch
        self.path = self.output / "retrieval_manifest.json"
        self.records = json.loads(self.path.read_text()) if self.path.exists() else {}
        self.last_request = 0.0

    def save(self):
        self.path.write_text(json.dumps(self.records, indent=2) + "\n")

    def get(self, url, extension="bin"):
        allowed_url(url)
        key = hashlib.sha256(url.encode()).hexdigest()
        path = self.output / "raw" / (key + "." + extension)
        rec = self.records.get(url)
        if rec and rec.get("status") == "ok" and path.exists():
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != rec["sha256"]:
                raise ValueError("Cached public response checksum mismatch")
            return data
        if not self.fetch:
            raise FileNotFoundError("Public response not cached: " + url)
        # Stay well below SEC's 10 requests/second fair-access ceiling.
        time.sleep(max(0, 0.35 - (time.monotonic() - self.last_request)))
        self.last_request = time.monotonic()
        now = datetime.now(timezone.utc).isoformat()
        try:
            with build_opener(RestrictedRedirect()).open(Request(url, headers={"User-Agent": UA}), timeout=60) as response:
                allowed_url(response.url)
                data = response.read(85_000_001)
                if len(data) > 85_000_000:
                    raise ValueError("Public response exceeds size limit")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                self.records[url] = {"status": "ok", "retrieved_at": now,
                                     "path": str(path.relative_to(self.output)),
                                     "sha256": hashlib.sha256(data).hexdigest(),
                                     "bytes": len(data), "final_url": response.url}
        except Exception as exc:
            self.records[url] = {"status": "failed", "retrieved_at": now,
                                 "error_type": type(exc).__name__}
            self.save()
            raise
        self.save()
        return data


def parse_feed(data):
    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(data)
    records = []
    for entry in root.findall("a:entry", ns):
        def field(name):
            return entry.findtext("a:content/a:" + name, namespaces=ns)
        records.append({"accession": field("accession-number"),
                        "filing_date": field("filing-date"),
                        "form_type": field("filing-type"),
                        "index_url": field("filing-href"),
                        "feed_updated": entry.findtext("a:updated", namespaces=ns)})
    return records


def parse_index(data, index_url):
    text = data.decode("utf-8")
    accepted = re.search(r'Accepted</div>\s*<div[^>]*>([^<]+)', text)
    report = re.search(r'Period of Report</div>\s*<div[^>]*>([^<]+)', text)
    p = Links()
    p.feed(text)
    xml = [urljoin(index_url, x) for x in p.links
           if x.endswith(".xml") and "xslForm" not in x]
    if len(set(xml)) != 1 or not accepted or not report:
        raise ValueError("Ambiguous or incomplete N-PORT filing index")
    # Scope attachments by the document table's explicit NPORT-EX type.
    exhibits = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.S | re.I):
        if re.search(r">NPORT-EX<", row):
            q = Links()
            q.feed(row)
            exhibits.extend(urljoin(index_url, x) for x in q.links)
    return {"xml_url": xml[0], "accepted_eastern": accepted.group(1).strip(),
            "index_portfolio_date": report.group(1).strip(),
            "exhibit_urls": sorted(set(exhibits))}


def retrieve(output=DEFAULT_OUTPUT, fetch=False, as_of="2026-10-10"):
    cache = PublicCache(output, fetch)
    filings, failures = {}, []
    # Explicit amendment search supplements the form-prefix search.
    for form in ("NPORT-P", "NPORT-P/A"):
        start = 0
        while True:
            query = urlencode({"action": "getcompany", "CIK": SERIES,
                               "type": form, "count": 100, "start": start, "output": "atom"})
            url = "https://www.sec.gov/cgi-bin/browse-edgar?" + query
            try:
                entries = parse_feed(cache.get(url, "xml"))
            except Exception as exc:
                failures.append({"url": url, "error_type": type(exc).__name__})
                break
            for item in entries:
                # June/September 2022 are explicitly separate warm-up snapshots.
                if "2022-08-01" <= item["filing_date"] <= as_of:
                    filings[item["accession"]] = item
            if len(entries) < 100:
                break
            start += 100
    for item in sorted(filings.values(), key=lambda x: x["filing_date"]):
        try:
            item.update(parse_index(cache.get(item["index_url"], "html"), item["index_url"]))
            cache.get(item["xml_url"], "xml")
            item["retrieved"] = True
            for url in item["exhibit_urls"]:
                try:
                    cache.get(url, "html")
                except Exception as exc:
                    failures.append({"url": url, "error_type": type(exc).__name__})
            print(item["filing_date"], item["index_portfolio_date"], item["accession"], flush=True)
        except Exception as exc:
            item["retrieved"] = False
            failures.append({"url": item["index_url"], "error_type": type(exc).__name__})
    archive_url = "https://web.archive.org/cdx/search/cdx?" + urlencode({
        "url": "www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spgm.xlsx",
        "output": "json", "from": "20221001", "to": "20260930",
        "filter": "statuscode:200", "collapse": "digest", "limit": "10000"})
    archives = []
    try:
        table = json.loads(cache.get(archive_url, "json"))
        for row in table[1:]:
            rec = dict(zip(table[0], row))
            url = "https://web.archive.org/web/" + rec["timestamp"] + "id_/https://" + rec["original"].removeprefix("https://").removeprefix("http://")
            try:
                cache.get(url, "xlsx")
                archives.append({"capture": rec["timestamp"], "url": url})
            except Exception as exc:
                failures.append({"url": url, "error_type": type(exc).__name__})
    except Exception as exc:
        failures.append({"url": archive_url, "error_type": type(exc).__name__})
    catalog = {"dataset_label": LABEL, "series": SERIES, "registrant_cik": REGISTRANT,
               "as_of": as_of, "filings": list(filings.values()), "archives": archives,
               "failures": failures, "eodhd_requests": 0}
    (cache.output / "source_catalog.json").write_text(json.dumps(catalog, indent=2) + "\n")
    return catalog


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true", help="Retrieve missing public SEC/Wayback responses")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--as-of", default="2026-10-10")
    args = parser.parse_args()
    result = retrieve(args.output, args.fetch, args.as_of)
    print(json.dumps({"filings": len(result["filings"]), "archives": len(result["archives"]),
                      "failures": len(result["failures"]), "eodhd_requests": 0}))
