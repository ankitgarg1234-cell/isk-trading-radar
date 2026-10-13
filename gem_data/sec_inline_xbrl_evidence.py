"""Bounded parser for *original* SEC Inline XBRL 10-Q numeric evidence.

Source facts are candidates, never silently mapped to GEM financials.
Original HTML SHA, accession, CIK identity, dates, unit, taxonomy tag and
context dimension are required to compare with standardized companyfacts.
This never grants independent context signoff or trading authorization.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from hashlib import sha256
from html.parser import HTMLParser
import re


class InlineEvidenceHold(ValueError):
    pass


MAX_HTML_BYTES = 6_000_000
MAX_CONTEXTS = 7000
MAX_FACTS = 150000
_NUMBER = re.compile(r"^[-+]?\\d{1,20}(?:\\.\\d{1,12})?$")
_DATE = re.compile(r"^\\d{4}-\\d{2}-\\d{2}$")
_US_GAAP_REVENUE = frozenset({
    "revenuefromcontractwithcustomerexcludingassessedtax",
    "revenuefromcontractwithcustomerincludingassessedtax",
    "revenues", "salesrevenuenet",
})
_GAAP_OPERATING = frozenset({"operatingincomeloss"})
_GAAP_NET = frozenset({"netincomeloss"})


def _tag_category(name):
    if not isinstance(name, str) or ":" not in name:
        return None
    taxonomy, concept = name.lower().split(":", 1)
    if taxonomy == "us-gaap":
        if concept in _US_GAAP_REVENUE:
            return "STANDARD_REVENUE"
        if concept in _GAAP_OPERATING:
            return "STANDARD_OPERATING_INCOME"
        if concept in _GAAP_NET:
            return "STANDARD_PARENT_NET_INCOME"
        return None
    # Custom taxonomy names are *review leads*, not equivalent metrics.
    if taxonomy not in ("us-gaap", "dei", "country", "iso4217"):
        if any(term in concept for term in ("revenue", "netsales", "operatingincome",
                                              "operatingprofit", "netincome")):
            return "ISSUER_EXTENSION_REVIEW_ONLY"
    return None


def _amount(text, attrs):
    v = "".join(text.split()).replace(",", "").replace("$", "")
    parens = v.startswith("(") and v.endswith(")")
    if parens:
        v = v[1:-1]
    if not _NUMBER.fullmatch(v):
        return None
    try:
        number = Decimal(v)
        scale = int(attrs.get("scale", "0"))
        if not -8 <= scale <= 12:
            return None
        number *= Decimal(10) ** scale
        if parens or attrs.get("sign") == "-":
            number *= -1
        if not number.is_finite():
            return None
        return str(number)
    except (InvalidOperation, TypeError, ValueError, OverflowError):
        return None


class _IXParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.contexts = {}
        self.units = {}
        self.facts = []
        self._context = None
        self._unit = None
        self._field = None
        self._field_parts = []
        self._fact = None
        self._fact_depth = 0
        self._dimension_depth = 0
        self._identifiers = set()

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag in ("xbrli:context", "context") and self._context is None:
            if len(self.contexts) >= MAX_CONTEXTS:
                raise InlineEvidenceHold("Too many Inline XBRL contexts")
            self._context = {"id": attrs.get("id"), "dimensioned": False}
        elif tag in ("xbrli:unit", "unit") and self._unit is None:
            self._unit = {"id": attrs.get("id"), "measures": []}
        if self._context is not None and tag in ("xbrli:segment", "xbrli:scenario",
                                                  "xbrldi:explicitmember", "xbrldi:typedmember"):
            self._context["dimensioned"] = True
        if tag in ("xbrli:startdate", "xbrli:enddate", "xbrli:instant",
                   "xbrli:identifier", "xbrli:measure"):
            self._field = tag
            self._field_parts = []
        if self._fact is not None:
            self._fact_depth += 1
        elif tag in ("ix:nonfraction", "ix:non-fraction"):
            if len(self.facts) >= MAX_FACTS:
                raise InlineEvidenceHold("Too many Inline XBRL numeric facts")
            self._fact = {"name": attrs.get("name"), "context_ref": attrs.get("contextref"),
                          "unit_ref": attrs.get("unitref"), "attributes": attrs,
                          "parts": []}
            self._fact_depth = 0

    def handle_startendtag(self, tag, attributes):
        self.handle_starttag(tag, attributes)
        self.handle_endtag(tag)

    def handle_data(self, data):
        if self._field:
            self._field_parts.append(data)
        if self._fact is not None:
            self._fact["parts"].append(data)

    def handle_endtag(self, tag):
        if self._field == tag:
            value = "".join(self._field_parts).strip()
            if self._context is not None:
                if tag == "xbrli:identifier":
                    self._identifiers.add(value)
                else:
                    self._context[tag.split(":")[-1]] = value
            if self._unit is not None and tag == "xbrli:measure":
                self._unit["measures"].append(value)
            self._field = None
            self._field_parts = []
        if self._fact is not None:
            if self._fact_depth > 0:
                self._fact_depth -= 1
            elif tag in ("ix:nonfraction", "ix:non-fraction"):
                self.facts.append(self._fact)
                self._fact = None
        if tag in ("xbrli:context", "context") and self._context is not None:
            cid = self._context["id"]
            if cid:
                self.contexts[cid] = self._context
            self._context = None
        if tag in ("xbrli:unit", "unit") and self._unit is not None:
            uid = self._unit["id"]
            if uid:
                self.units[uid] = self._unit["measures"]
            self._unit = None


def extract_inline_candidates(html, *, cik, accession, source_uri):
    if not isinstance(html, bytes) or not 0 < len(html) <= MAX_HTML_BYTES:
        raise InlineEvidenceHold("Original 10-Q HTML missing or outside byte limit")
    if not re.fullmatch(r"[0-9]{10}", str(cik)) or not re.fullmatch(
            r"[0-9]{10}-[0-9]{2}-[0-9]{6}", str(accession)):
        raise InlineEvidenceHold("Invalid original CIK or accession")
    expected = (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                + accession.replace("-", "") + "/")
    if not isinstance(source_uri, str) or not source_uri.startswith(expected):
        raise InlineEvidenceHold("Original SEC filing URL does not match accession")
    try:
        page = _IXParser()
        page.feed(html.decode("utf-8", errors="replace"))
        page.close()
    except (ValueError, OverflowError) as exc:
        raise InlineEvidenceHold("Invalid original Inline XBRL HTML") from exc
    ids = {v.zfill(10) for v in page._identifiers if v.isdigit()}
    if not ids or ids != {cik}:
        raise InlineEvidenceHold("Original Inline XBRL CIK identity missing/mismatched")
    out, seen = [], set()
    for item in page.facts:
        category = _tag_category(item["name"])
        if category is None:
            continue
        ctx = page.contexts.get(item["context_ref"])
        units = page.units.get(item["unit_ref"])
        if not ctx or ctx["dimensioned"] or units != ["iso4217:USD"]:
            continue
        start, end = ctx.get("startdate"), ctx.get("enddate")
        if not start or not end or not _DATE.fullmatch(start) or not _DATE.fullmatch(end):
            continue
        amount = _amount(item["parts"], item["attributes"])
        if amount is None:
            continue
        key = (item["name"],start,end,amount)
        if key in seen:
            continue
        seen.add(key)
        out.append({"concept": item["name"],"category": category,
                    "start": start, "end": end, "amount_usd": amount,
                    "accession": accession, "context_dimensioned": False,
                    "source_scope_reviewed": False})
        if len(out) >= 400:
            break
    return {
        "schema": "gem-sec-inline-xbrl-extraction-v1",
        "cik": cik,"accession":accession,"original_uri":source_uri,
        "original_raw_sha256":sha256(html).hexdigest(),
        "original_bytes":len(html),
        "total_numeric_elements":len(page.facts),
        "eligible_undimensioned_usd_candidates":len(out),
        "candidates":out,
        "status":"ORIGINAL_CONTEXT_CANDIDATES_NOT_CERTIFIED",
        "automatic_mapping_approved":False,
        "investment_approval":False,
    }
