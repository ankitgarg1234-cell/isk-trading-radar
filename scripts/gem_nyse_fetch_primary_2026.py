"""Fetch original public NYSE 2026 calendar bytes for human source review.

Read-only, network only when CLI is explicitly invoked. Never auto-approves
market status or GEM orders. GitHub Actions stores the raw response in a
short-lived review artifact with a SHA-256 receipt; publication-date metadata
is not authenticated by this download.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path

import httpx

NYSE_URL = "https://www.nyse.com/trade/hours-calendars"
MAX_BYTES = 2_000_000
REQUIRED_MARKERS = (
    "Holidays & Trading Hours",
    "Friday, June 19",
    "Friday, July 3",
    "Friday, November 27, 2026",
    "Thursday, December 24, 2026",
    "Core Trading Session",
)


class CalendarSourceUnavailable(RuntimeError):
    pass


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def read_primary_nyse_calendar(client: httpx.Client) -> tuple[dict, bytes]:
    try:
        with client.stream("GET", NYSE_URL, follow_redirects=False) as resp:
            if resp.status_code != 200:
                raise CalendarSourceUnavailable("Official NYSE calendar unavailable")
            if "text/html" not in resp.headers.get("content-type", "").lower():
                raise CalendarSourceUnavailable("Unexpected official source media type")
            chunks = []
            length = 0
            for chunk in resp.iter_bytes():
                length += len(chunk)
                if length > MAX_BYTES:
                    raise CalendarSourceUnavailable("Official source exceeds bounded bytes")
                chunks.append(chunk)
            raw = b"".join(chunks)
    except httpx.HTTPError:
        raise CalendarSourceUnavailable("Official NYSE calendar request failed") from None
    if not raw:
        raise CalendarSourceUnavailable("Empty official NYSE calendar response")
    parser = _Text()
    parser.feed(raw.decode("utf-8", errors="replace"))
    text = " ".join(" ".join(parser.parts).split())
    missing = [marker for marker in REQUIRED_MARKERS if marker not in text]
    if missing:
        raise CalendarSourceUnavailable("Official 2026 NYSE publication markers incomplete")
    receipt = {
        "schema": "gem-nyse-primary-2026-raw-receipt-v1",
        "url": NYSE_URL,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "response_bytes": len(raw),
        "raw_sha256": sha256(raw).hexdigest(),
        "published_markers_checked": list(REQUIRED_MARKERS),
        "source_raw_observed": True,
        "official_exception_notices_checked": False,
        "independent_reviewer_approved": False,
        "trading_authorized": False,
    }
    return receipt, raw


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output-dir", required=True)
    args = p.parse_args()
    out = Path(args.output_dir)
    if out.exists() and any(out.iterdir()):
        raise SystemExit("Evidence directory must be empty")
    with httpx.Client(timeout=15.0, headers={
        "User-Agent": "GEMv1 read-only research source audit"
    }) as client:
        receipt, raw = read_primary_nyse_calendar(client)
    out.mkdir(parents=True, exist_ok=True)
    (out / "nyse-2026-source.html").write_bytes(raw)
    (out / "nyse-2026-receipt.json").write_text(
        json.dumps(receipt, sort_keys=True, indent=2) + "\n",
        encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in receipt.items()
                      if k not in ("published_markers_checked",)}))


if __name__ == "__main__":
    main()
