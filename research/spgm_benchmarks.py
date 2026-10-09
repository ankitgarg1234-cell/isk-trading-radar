"""Dated MSCI factsheet counts for retrospective ETF sampling comparisons.

Counts are NOT index membership. PDF downloads and extracted data stay ignored.
The optional PDF reader is pypdf; parsing fails on ambiguous dates or counts.
"""
from __future__ import annotations

import argparse
import io
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlencode

from research.spgm_sources import DEFAULT_OUTPUT, PublicCache, public_body

FACTSHEET = "https://www.msci.com/documents/10199/255599/msci-acwi-imi.pdf"


def parse_factsheet(text):
    if "MSCI ACWI IMI Index" not in text:
        raise ValueError("Not an MSCI ACWI IMI factsheet")
    counts = {int(x.replace(",", "")) for x in re.findall(r"With\s+([0-9,]+)\s+constituents", text)}
    if len(counts) != 1:
        raise ValueError("Ambiguous or missing constituent count")
    dates = re.findall(r"(?:INDEX PERFORMANCE.*?|FUNDAMENTALS)\s*\(?([A-Z]{3}\s+[0-9]{1,2},\s+[0-9]{4})\)?", text)
    parsed = {datetime.strptime(x, "%b %d, %Y").date().isoformat() for x in dates}
    if len(parsed) != 1:
        raise ValueError("Ambiguous or missing factsheet observation date")
    return {"portfolio_date": parsed.pop(), "constituent_count": counts.pop()}


def build(fetch=False):
    from pypdf import PdfReader
    cache = PublicCache(DEFAULT_OUTPUT / "benchmark", fetch)
    query = "https://web.archive.org/cdx/search/cdx?" + urlencode({
        "url": FACTSHEET.removeprefix("https://"), "output": "json", "from": "20221001",
        "to": "20260930", "filter": "statuscode:200", "collapse": "timestamp:6", "limit": 1000})
    table = json.loads(cache.get(query, "json"))
    sources = [{"source_url": FACTSHEET, "available_at": cache.records.get(FACTSHEET, {}).get("retrieved_at"),
                "publication_basis": "original publication unknown; first verified retrieval bound"}]
    for values in table[1:]:
        rec = dict(zip(table[0], values))
        capture = datetime.strptime(rec["timestamp"], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc).isoformat()
        sources.append({"source_url": "https://web.archive.org/web/" + rec["timestamp"] + "id_/" + rec["original"],
                        "available_at": capture, "publication_basis": "archive capture availability bound"})
    counts, failures = [], []
    for source in sources:
        try:
            data = cache.get(source["source_url"], "pdf")
            pdf = public_body(data)
            if not pdf.startswith(b"%PDF-"):
                raise ValueError("Response is not a PDF after transport decoding")
            text = "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)
            parsed = parse_factsheet(text)
            if source["available_at"] is None:
                source["available_at"] = cache.records[source["source_url"]]["retrieved_at"]
            if parsed["portfolio_date"] > source["available_at"][:10]:
                raise ValueError("Factsheet date later than its availability")
            parsed.update(source)
            parsed["source_sha256"] = cache.records[source["source_url"]]["sha256"]
            parsed["pdf_terminal_eof_present"] = b"%%EOF" in pdf[-1024:]
            parsed["validation_scope"] = "readable index name/date/count; full PDF integrity not asserted"
            counts.append(parsed)
            print(parsed["portfolio_date"], parsed["constituent_count"], flush=True)
        except Exception as exc:
            failures.append({"source_url": source["source_url"], "error_type": type(exc).__name__})
    (DEFAULT_OUTPUT / "benchmark_counts.json").write_text(json.dumps(counts, indent=2) + "\n")
    (cache.output / "parse_failures.json").write_text(json.dumps(failures, indent=2) + "\n")
    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true")
    args = parser.parse_args()
    print("Verified dated counts:", len(build(args.fetch)))
