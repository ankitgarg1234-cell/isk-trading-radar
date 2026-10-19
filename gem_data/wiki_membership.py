"""Current Wikipedia S&P 500 membership and SEC CIK reconciliation.

Wikipedia is a *secondary current-universe* source, not a historical
point-in-time or S&P Dow Jones membership certificate. Never auto-approve
signals or rewrite the original frozen backtest.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
import csv
from io import StringIO
import json
import re

import httpx

URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
SYMBOL = re.compile(r"^[A-Z][A-Z0-9.\-]{0,14}$")
CIK = re.compile(r"^[0-9]{1,10}$")


class MembershipHold(ValueError):
    pass


class _Table(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.inside = False
        self.depth = 0
        self.row = None
        self.cell = None
        self.rows = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "table" and attrs.get("id") == "constituents":
            self.inside, self.depth = True, 1
            return
        if not self.inside:
            return
        if tag == "table":
            self.depth += 1
        if self.depth == 1 and tag == "tr":
            self.row = []
        if self.depth == 1 and tag in ("td", "th") and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if not self.inside:
            return
        if tag in ("td", "th") and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        if tag == "tr" and self.row is not None:
            if self.row:
                self.rows.append(self.row)
            self.row = None
        if tag == "table":
            self.depth -= 1
            if self.depth == 0:
                self.inside = False


def parse_wikipedia_membership(html: bytes) -> dict:
    if not isinstance(html, bytes) or not 0 < len(html) <= 3_000_000:
        raise MembershipHold("Wikipedia page absent or oversized")
    try:
        parser = _Table()
        parser.feed(html.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise MembershipHold("Wikipedia HTML could not be parsed") from exc
    if not parser.rows or "CIK" not in parser.rows[0]:
        raise MembershipHold("Wikipedia constituents table or CIK header not found")
    header = parser.rows[0]
    wanted = ("Symbol", "Security", "Date added", "CIK")
    if any(k not in header for k in wanted):
        raise MembershipHold("Required constituents columns changed")
    columns = {name: header.index(name) for name in wanted}
    result, seen = [], set()
    for row in parser.rows[1:]:
        if len(row) <= max(columns.values()):
            raise MembershipHold("Wikipedia constituent row incomplete")
        ticker = row[columns["Symbol"]].strip().upper()
        raw_cik = row[columns["CIK"]].strip()
        if not SYMBOL.fullmatch(ticker) or not CIK.fullmatch(raw_cik):
            raise MembershipHold("Invalid ticker or CIK in Wikipedia snapshot")
        if ticker in seen:
            raise MembershipHold("Duplicate S&P ticker in Wikipedia snapshot")
        seen.add(ticker)
        result.append({"ticker": ticker, "security": row[columns["Security"]],
                       "cik": raw_cik.zfill(10), "date_added": row[columns["Date added"]]})
    if not 480 <= len(result) <= 600:
        raise MembershipHold("Incomplete or unexpectedly sized Wikipedia membership")
    result.sort(key=lambda x: x["ticker"])
    return {"schema": "gem-secondary-wikipedia-membership-v1",
            "source": URL,
            "source_sha256": sha256(html).hexdigest(),
            "securities": len(result),
            "unique_ciks": len({r["cik"] for r in result}),
            "members": result, "certified": False,
            "classification": "SECONDARY_CURRENT_SNAPSHOT_NOT_HISTORICAL"}


def compare_secondary_membership(wiki: dict, csv_source: bytes) -> dict:
    try:
        rows = list(csv.DictReader(StringIO(csv_source.decode("utf-8-sig"))))
        if not rows or not {"Symbol", "CIK"} <= set(rows[0]):
            raise ValueError()
        secondary = {r["Symbol"].strip().upper(): str(r["CIK"]).strip().zfill(10)
                     for r in rows}
    except (UnicodeError, ValueError, KeyError, csv.Error) as exc:
        raise MembershipHold("Secondary membership CSV unavailable for comparison") from exc
    wiki_by_ticker = {r["ticker"]: r["cik"] for r in wiki["members"]}
    added = sorted(wiki_by_ticker.keys() - secondary.keys())
    absent = sorted(secondary.keys() - wiki_by_ticker.keys())
    mismatch = sorted(t for t in wiki_by_ticker.keys() & secondary.keys()
                      if wiki_by_ticker[t] != secondary[t])
    return {"wikipedia_count": len(wiki_by_ticker), "secondary_count": len(secondary),
            "only_wikipedia": added, "only_secondary": absent,
            "cik_mismatches": mismatch,
            "identity_match": not (added or absent or mismatch),
            "membership_certified": False}


def fetch_wikipedia_snapshot(*, client=None) -> dict:
    own = client is None
    c = client or httpx.Client(timeout=20, follow_redirects=True,
                               headers={"User-Agent":"GEMv1 membership research bot"})
    try:
        response = c.get(URL)
        if response.status_code != 200 or len(response.content) > 3_000_000:
            raise MembershipHold("Wikipedia source HTTP/size hold")
        if response.url.host != "en.wikipedia.org" or response.url.scheme != "https":
            raise MembershipHold("Membership source redirected outside Wikipedia")
        return parse_wikipedia_membership(response.content)
    except httpx.HTTPError:
        raise MembershipHold("Wikipedia source network unavailable") from None
    finally:
        if own:
            c.close()
