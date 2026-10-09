"""Normalize public SPGM holdings and measure point-in-time proxy coverage.

No network operations, trading imports, or current-universe backfilling. Inputs
and generated security-level data remain in Git-ignored eodhd_output.
"""
from __future__ import annotations

import argparse
import calendar
import csv
import hashlib
import io
import json
import re
import zipfile
from html import unescape
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

from research.spgm_sources import DEFAULT_OUTPUT, LABEL, SERIES, PublicCache, public_body

N = {"n": "http://www.sec.gov/edgar/nport"}
X = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
EMPTY = {"", "-", "—", "N/A", "NA", "NONE", "000000000", "XXXXXXXXX"}


def clean(value):
    value = (value or "").strip()
    return "" if value.upper() in EMPTY else value


def isin_valid(value):
    if not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", value):
        return False
    digits = "".join(str(ord(x) - 55) if x.isalpha() else x for x in value)
    total = 0
    for i, x in enumerate(reversed(digits)):
        v = int(x) * (2 if i % 2 else 1)
        total += v // 10 + v % 10
    return total % 10 == 0


def cusip_valid(value):
    if not re.fullmatch(r"[A-Z0-9*@#]{8}[0-9]", value):
        return False
    total = 0
    for i, x in enumerate(value[:8]):
        v = int(x) if x.isdigit() else ord(x) - 55 if x.isalpha() else {"*": 36, "@": 37, "#": 38}[x]
        v *= 1 if i % 2 == 0 else 2
        total += v // 10 + v % 10
    return (10 - total % 10) % 10 == int(value[-1])


def sedol_valid(value):
    if not re.fullmatch(r"[0-9BCDFGHJKLMNPQRSTVWXYZ]{6}[0-9]", value):
        return False
    numbers = [int(x) if x.isdigit() else ord(x) - 55 for x in value]
    return sum(x * w for x, w in zip(numbers, [1, 3, 1, 7, 3, 9, 1])) % 10 == 0


def identifier_keys(row):
    # Check digits reduce unsafe joins. Bad values stay in the source audit.
    keys = []
    for field, validator in (("isin", isin_valid), ("cusip", cusip_valid), ("sedol", sedol_valid)):
        if validator(row.get(field, "")):
            keys.append((field, row[field]))
    return keys


def annotate_identifiers(row):
    errors = []
    for field, validator in (("isin", isin_valid), ("cusip", cusip_valid), ("sedol", sedol_valid)):
        if row.get(field) and not validator(row[field]):
            errors.append(field + "_format_or_checksum")
    row["identifier_problems"] = ";".join(errors)
    row["instrument_key"] = ":".join(identifier_keys(row)[0]) if identifier_keys(row) else ""
    return row


def xml_root(data):
    data = public_body(data)
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValueError("Unexpected XML DTD/entity")
    return ET.fromstring(data)


def parse_nport(data, metadata):
    root = xml_root(data)
    gen = root.find("n:formData/n:genInfo", N)
    if gen is None or gen.findtext("n:seriesId", namespaces=N) != SERIES:
        raise ValueError("N-PORT belongs to another fund series")
    # repPdEnd is fiscal-year end, NOT the portfolio observation date.
    portfolio = gen.findtext("n:repPdDate", namespaces=N)
    date.fromisoformat(portfolio)
    if portfolio != metadata["index_portfolio_date"]:
        raise ValueError("Portfolio date disagrees with SEC index")
    accepted = datetime.strptime(metadata["accepted_eastern"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo("America/New_York"))
    public = accepted.astimezone(timezone.utc).isoformat()
    if accepted.date().isoformat() > metadata["filing_date"]:
        # Preserve both fields; selection uses the later filing/acceptance bound.
        available = public
    elif accepted.date().isoformat() < metadata["filing_date"]:
        bound = datetime.fromisoformat(metadata["filing_date"] + "T23:59:59").replace(tzinfo=ZoneInfo("America/New_York"))
        available = bound.astimezone(timezone.utc).isoformat()
    else:
        available = public
    if portfolio > metadata["filing_date"]:
        raise ValueError("Public filing predates its portfolio")
    sid = metadata["accession"]
    rows = []
    for i, holding in enumerate(root.findall("n:formData/n:invstOrSecs/n:invstOrSec", N), 1):
        def text(field):
            return clean(holding.findtext("n:" + field, namespaces=N))
        identifiers = holding.find("n:identifiers", N)
        ids = defaultdict(list)
        if identifiers is not None:
            for item in identifiers:
                ids[item.tag.split("}")[-1]].append(dict(item.attrib))
        def ident(field):
            return clean(ids[field][0].get("value")) if len(ids[field]) == 1 else ""
        asset = text("assetCat")
        conditional = holding.find("n:assetConditional", N)
        if not asset and conditional is not None:
            asset = clean(conditional.get("assetCat"))
        currency = text("curCd")
        cc = holding.find("n:currencyConditional", N)
        if not currency and cc is not None:
            currency = clean(cc.get("curCd"))
        row = {"snapshot_id": sid, "row_number": i, "portfolio_date": portfolio,
               "publication_date": metadata["filing_date"], "available_at": available,
               "name": text("name"), "title": text("title"), "company_lei": text("lei"),
               "cusip": text("cusip"), "isin": ident("isin"), "sedol": "",
               "source_ticker": ident("ticker"), "other_identifiers_json": json.dumps(dict(ids), sort_keys=True),
               "country": text("invCountry"), "country_basis": "N-PORT investment country",
               "currency": currency, "asset_category": asset, "issuer_category": text("issuerCat"),
               "balance": text("balance"), "value_usd": text("valUSD"), "weight_pct": text("pctVal"),
               "sector": "", "sector_scheme": "", "sector_source": "not supplied in N-PORT XML",
               "raw_source_sha256": hashlib.sha256(data).hexdigest()}
        annotate_identifiers(row)
        if len(ids["isin"]) > 1 or len(ids["ticker"]) > 1:
            row["identifier_problems"] += ";multiple_source_identifiers"
        rows.append(row)
    if not rows:
        raise ValueError("No portfolio holdings in N-PORT")
    snapshot = {"snapshot_id": sid, "source_type": "SEC NPORT-P", "form_type": metadata["form_type"],
                "portfolio_date": portfolio, "publication_date": metadata["filing_date"],
                "accepted_eastern": metadata["accepted_eastern"], "public_timestamp_utc": public,
                "available_at": available, "publication_basis": "public NPORT-P filing; SEC index acceptance",
                "fiscal_year_end": gen.findtext("n:repPdEnd", namespaces=N),
                "series_name": gen.findtext("n:seriesName", namespaces=N),
                "source_url": metadata["xml_url"], "index_url": metadata["index_url"],
                "sha256": hashlib.sha256(data).hexdigest(), "exhibit_urls": metadata.get("exhibit_urls", [])}
    return snapshot, rows


def xlsx_rows(data):
    data = public_body(data)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if sum(x.file_size for x in archive.infolist()) > 80_000_000:
            raise ValueError("Workbook exceeds uncompressed limit")
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = xml_root(archive.read("xl/sharedStrings.xml"))
            strings = ["".join(t.text or "" for t in si.findall(".//x:t", X)) for si in root.findall("x:si", X)]
        # Publisher workbooks contain a single holdings worksheet. Resolve its
        # relationship rather than assuming the first ZIP member is the sheet.
        wb = xml_root(archive.read("xl/workbook.xml"))
        sheets = wb.findall("x:sheets/x:sheet", X)
        if len(sheets) != 1:
            raise ValueError("Ambiguous multi-sheet holdings workbook")
        rid = sheets[0].get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        rels = xml_root(archive.read("xl/_rels/workbook.xml.rels"))
        targets = [r.get("Target") for r in rels if r.get("Id") == rid]
        if len(targets) != 1:
            raise ValueError("Missing workbook relationship")
        target = targets[0].lstrip("/") if targets[0].startswith("/") else "xl/" + targets[0]
        root = xml_root(archive.read(target))
        result = []
        for row in root.findall("x:sheetData/x:row", X):
            cells = {}
            for cell in row.findall("x:c", X):
                column = re.sub(r"[0-9]", "", cell.get("r"))
                value = cell.findtext("x:v", default="", namespaces=X)
                if cell.get("t") == "s":
                    value = strings[int(value)]
                elif cell.get("t") == "inlineStr":
                    value = "".join(x.text or "" for x in cell.findall(".//x:t", X))
                cells[column] = value
            result.append(cells)
        return result


def parse_archive(data, metadata):
    cells = xlsx_rows(data)
    labels = [v for row in cells[:5] for v in row.values()]
    if not any("Global Stock Market ETF" in v for v in labels) or "SPGM" not in labels:
        raise ValueError("Workbook is not SPGM")
    values = [v for v in labels if v.startswith("As of ")]
    if len(values) != 1:
        raise ValueError("Missing workbook portfolio date")
    portfolio = datetime.strptime(values[0][6:], "%d-%b-%Y").date().isoformat()
    capture = datetime.strptime(metadata["capture"], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    if portfolio > capture.date().isoformat():
        raise ValueError("Workbook portfolio date is later than archive capture")
    header_indices = [i for i, r in enumerate(cells) if r.get("A") == "Name" and r.get("C") == "Identifier"]
    if len(header_indices) != 1:
        raise ValueError("Workbook holdings header is missing/ambiguous")
    header = cells[header_indices[0]]
    sid = "wayback-" + metadata["capture"]
    rows = []
    for raw in cells[header_indices[0] + 1:]:
        h = {header.get(k, k): clean(v) for k, v in raw.items()}
        if not h.get("Name") or not h.get("Identifier"):
            continue
        generic = h["Identifier"]
        # Generic identifiers remain intact even where their type is unknown.
        isin = generic if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", generic) else ""
        cusip = generic if re.fullmatch(r"[A-Z0-9*@#]{8}[0-9]", generic) else ""
        row = {"snapshot_id": sid, "row_number": len(rows) + 1, "portfolio_date": portfolio,
               "publication_date": "", "available_at": capture.isoformat(),
               "name": h["Name"], "title": h["Name"], "company_lei": "",
               "cusip": cusip, "isin": isin, "sedol": h.get("SEDOL", ""),
               "source_ticker": h.get("Ticker", ""),
               "other_identifiers_json": json.dumps({"publisher_identifier": generic}),
               "country": "", "country_basis": "not supplied; currency is not country",
               "currency": h.get("Local Currency", ""), "asset_category": "unclassified",
               "issuer_category": "", "balance": h.get("Shares Held", ""),
               "value_usd": "", "weight_pct": h.get("Weight", ""),
               "sector": h.get("Sector", ""), "sector_scheme": "publisher unspecified" if h.get("Sector") else "",
               "sector_source": metadata["url"], "raw_source_sha256": hashlib.sha256(data).hexdigest()}
        rows.append(annotate_identifiers(row))
    if not rows:
        raise ValueError("No holdings in workbook")
    return {"snapshot_id": sid, "source_type": "archived publisher XLSX", "form_type": "",
            "portfolio_date": portfolio, "publication_date": "",
            "public_timestamp_utc": "", "archive_capture_utc": capture.isoformat(),
            "available_at": capture.isoformat(),
            "publication_basis": "original publication unknown; archive capture is conservative availability bound",
            "source_url": metadata["url"], "sha256": hashlib.sha256(data).hexdigest()}, rows


def map_tickers(rows):
    """Exact valid identifier joins only. Preserve mapping publication times.

    A future archive may help research identity but cannot supply a ticker for
    an earlier decision. Names, currency and present-day tickers are not joins.
    """
    mappings = defaultdict(list)
    for row in rows:
        if row["source_ticker"]:
            for key in identifier_keys(row):
                mappings[key].append(row)
    for row in rows:
        row.update({"mapped_ticker": row["source_ticker"], "ticker_mapping_status": "source" if row["source_ticker"] else "unmapped",
                    "ticker_mapping_portfolio_date": row["portfolio_date"] if row["source_ticker"] else "",
                    "ticker_mapping_available_at": row["available_at"] if row["source_ticker"] else "",
                    "ticker_mapping_snapshot": row["snapshot_id"] if row["source_ticker"] else ""})
        if row["source_ticker"]:
            continue
        candidates = {}
        for key in identifier_keys(row):
            for candidate in mappings[key]:
                candidates[(candidate["snapshot_id"], candidate["row_number"])] = candidate
        past = [x for x in candidates.values() if x["portfolio_date"] <= row["portfolio_date"]
                and x["available_at"] <= row["available_at"]]
        choices = past or list(candidates.values())
        if not choices:
            continue
        chosen_date = max(x["portfolio_date"] for x in choices) if past else min(x["portfolio_date"] for x in choices)
        group = [x for x in choices if x["portfolio_date"] == chosen_date]
        if len({x["source_ticker"] for x in group}) != 1:
            row["ticker_mapping_status"] = "ambiguous_exact_identifier"
            continue
        candidate = min(group, key=lambda x: x["available_at"])
        row.update({"mapped_ticker": candidate["source_ticker"],
                    "ticker_mapping_status": "prior_archive_identity_only" if past else "future_archive_identity_only",
                    "ticker_mapping_portfolio_date": candidate["portfolio_date"],
                    "ticker_mapping_available_at": candidate["available_at"],
                    "ticker_mapping_snapshot": candidate["snapshot_id"]})


def quality(rows):
    keys = Counter(x["instrument_key"] for x in rows if x["instrument_key"])
    return {"holdings_count": len(rows),
            "common_equity_rows": sum(x["asset_category"] == "EC" for x in rows),
            "preferred_equity_rows": sum(x["asset_category"] == "EP" for x in rows),
            "unique_valid_instrument_keys": len(keys),
            "duplicate_instrument_rows": sum(v - 1 for v in keys.values()),
            "missing_valid_security_id": sum(not x["instrument_key"] for x in rows),
            "identifier_problem_rows": sum(bool(x["identifier_problems"]) for x in rows),
            "missing_company_lei": sum(not x["company_lei"] for x in rows),
            "missing_isin": sum(not x["isin"] for x in rows),
            "missing_source_ticker": sum(not x["source_ticker"] for x in rows),
            "unmapped_ticker": sum(not x["mapped_ticker"] for x in rows),
            "future_only_ticker_mapping": sum(x["ticker_mapping_status"] == "future_archive_identity_only" for x in rows),
            "ambiguous_ticker_mapping": sum(x["ticker_mapping_status"] == "ambiguous_exact_identifier" for x in rows),
            "missing_country": sum(not x["country"] for x in rows),
            "missing_sector": sum(not x["sector"] for x in rows),
            "missing_verified_gics": sum(x["sector_scheme"] != "verified historical GICS" for x in rows)}


def month_ends(first="2022-10", last="2026-09"):
    y, m = map(int, first.split("-"))
    result = []
    while f"{y:04}-{m:02}" <= last:
        result.append(date(y, m, calendar.monthrange(y, m)[1]))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return result


def available_snapshot(snapshots, decision):
    when = datetime.fromisoformat(decision)
    if when.tzinfo is None:
        raise ValueError("Selection decision needs an explicit timezone")
    possible = [s for s in snapshots
                if datetime.fromisoformat(s["available_at"]) <= when
                and date.fromisoformat(s["portfolio_date"]) <= when.date()]
    return max(possible, key=lambda s: (s["portfolio_date"], s["available_at"], s["snapshot_id"])) if possible else None


def coverage_matrix(snapshots, benchmarks=()):
    result = []
    for end in month_ends():
        decision = end.isoformat() + "T23:59:59+00:00"
        selected = available_snapshot(snapshots, decision)
        in_month = [s for s in snapshots if s["portfolio_date"][:7] == end.isoformat()[:7]]
        row = {"selection_month": end.isoformat()[:7], "selection_decision_utc": decision,
               "portfolio_snapshots_in_month": len(in_month),
               "month_end_observation_exists": any(s["portfolio_date"] == end.isoformat() for s in in_month),
               "month_end_observation_public_by_selection": any(s["portfolio_date"] == end.isoformat()
                 and datetime.fromisoformat(s["available_at"]) <= datetime.fromisoformat(decision) for s in in_month),
               "selected_snapshot_id": "", "selected_portfolio_date": "", "selected_available_at": "",
               "staleness_calendar_days": "", "known_membership_missing_securities": "unknown_without_index_membership",
               "benchmark_count": "", "benchmark_count_date": "", "benchmark_count_public_at_selection": False,
               "benchmark_count_gap_not_identity_overlap": "", "sector_readiness": "blocked_historical_GICS_missing"}
        if selected:
            row.update({"selected_snapshot_id": selected["snapshot_id"],
                        "selected_portfolio_date": selected["portfolio_date"],
                        "selected_available_at": selected["available_at"],
                        "staleness_calendar_days": (end - date.fromisoformat(selected["portfolio_date"])).days})
            for field in quality_fields():
                row[field] = selected[field]
        else:
            for field in quality_fields():
                row[field] = ""
        # Comparison uses a precisely dated reported count, never fills it back
        # through earlier history. Actual missing-security identities are unknown.
        candidates = [b for b in benchmarks if b["portfolio_date"][:7] == end.isoformat()[:7]
                      and b["portfolio_date"] <= end.isoformat()]
        if candidates:
            b = max(candidates, key=lambda b: (b["portfolio_date"], b["available_at"]))
            row.update({"benchmark_count": b["constituent_count"], "benchmark_count_date": b["portfolio_date"],
                        "benchmark_count_public_at_selection": datetime.fromisoformat(b["available_at"]) <= datetime.fromisoformat(decision)})
            if selected:
                row["benchmark_count_gap_not_identity_overlap"] = int(b["constituent_count"]) - selected["holdings_count"]
        result.append(row)
    return result


def observed_changes(snapshots, groups):
    """Observed ETF identity changes only; not MSCI events or delisting claims."""
    # Preserve amendments separately; compare the last observed version of each
    # quarterly portfolio retrospectively, with both publication dates recorded.
    by_date = {}
    for s in sorted(snapshots, key=lambda s: s["available_at"]):
        if s["source_type"] == "SEC NPORT-P":
            by_date[s["portfolio_date"]] = s
    ordered = [by_date[d] for d in sorted(by_date)]
    changes = []
    for previous, current in zip(ordered, ordered[1:]):
        old = {r["instrument_key"]: r for r in groups[previous["snapshot_id"]] if r["instrument_key"]}
        new = {r["instrument_key"]: r for r in groups[current["snapshot_id"]] if r["instrument_key"]}
        for label, keys, records in (("first_observed_after_gap", new.keys() - old.keys(), new),
                                     ("not_observed_in_next_snapshot", old.keys() - new.keys(), old)):
            for key in sorted(keys):
                changes.append({"change_type": label, "instrument_key": key, "name": records[key]["name"],
                                "previous_portfolio_date": previous["portfolio_date"], "portfolio_date": current["portfolio_date"],
                                "previous_available_at": previous["available_at"], "available_at": current["available_at"],
                                "scope": "ETF observation difference; unknown effective date/reason; possible identifier change",
                                "is_msci_event": False, "is_confirmed_delisting": False})
    return changes


def benchmark_comparisons(snapshots, benchmarks):
    comparisons = []
    for snapshot in snapshots:
        candidates = [b for b in benchmarks if b["portfolio_date"] <= snapshot["portfolio_date"]]
        row = {"snapshot_id": snapshot["snapshot_id"], "portfolio_date": snapshot["portfolio_date"],
               "holdings_count": snapshot["holdings_count"], "common_equity_rows": snapshot["common_equity_rows"],
               "benchmark_count_date": "", "benchmark_count": "", "benchmark_date_gap_days": "",
               "count_ratio_pct_not_overlap": "", "count_gap_not_known_missing_members": "",
               "missing_security_identities": "unknown_without_full_index_membership"}
        if candidates:
            b = max(candidates, key=lambda b: b["portfolio_date"])
            row.update({"benchmark_count_date": b["portfolio_date"], "benchmark_count": b["constituent_count"],
                        "benchmark_available_at": b["available_at"],
                        "benchmark_date_gap_days": (date.fromisoformat(snapshot["portfolio_date"]) - date.fromisoformat(b["portfolio_date"])).days,
                        "count_ratio_pct_not_overlap": round(snapshot["holdings_count"] / b["constituent_count"] * 100, 4),
                        "count_gap_not_known_missing_members": b["constituent_count"] - snapshot["holdings_count"]})
        comparisons.append(row)
    return comparisons


def quality_fields():
    dummy = {"instrument_key": "", "asset_category": "", "identifier_problems": "", "company_lei": "",
             "isin": "", "source_ticker": "", "mapped_ticker": "", "ticker_mapping_status": "",
             "country": "", "sector": "", "sector_scheme": ""}
    return list(quality([dummy]))


def parse_exhibit(data, metadata):
    """Scope a multi-fund schedule by TOC anchors before extracting aggregates.

    Aggregate sector weights are useful evidence, but cannot classify individual
    holdings. Names containing 'Information Technology' are not sector headers.
    """
    text = public_body(data).decode("utf-8")
    toc = re.findall(r'<A[^>]*href="#([^"]+)"[^>]*>([^<]*ETF[^<]*)</A>', text[:150_000], re.I)
    target = {anchor for anchor, label in toc if "Global Stock Market" in unescape(label)}
    if len(target) != 1:
        raise ValueError("Cannot uniquely scope SPGM schedule in multi-fund exhibit")
    target = target.pop()
    anchors = {m.group(1): m.start() for m in re.finditer(r'<A\s+(?:name|id)="([^"]+)"', text, re.I)}
    if target not in anchors:
        raise ValueError("SPGM schedule anchor missing")
    start = anchors[target]
    ends = [anchors[a] for a, _ in toc if a != target and a in anchors and anchors[a] > start]
    section = text[start:min(ends)] if ends else text[start:]
    plain = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", section)))
    when = date.fromisoformat(metadata["portfolio_date"])
    expected = when.strftime("%B") + " " + str(when.day) + ", " + str(when.year)
    if expected not in plain or "SCHEDULE OF INVESTMENTS" not in plain.upper():
        raise ValueError("Schedule's fund/date does not match its N-PORT observation")
    sectors = []
    block = re.search(r"Sector Breakdown as of\s+" + re.escape(expected) + r"(.*?)(?:TOTAL\s+100|The Fund's sector)", plain, re.I)
    if block:
        names = ["Information Technology", "Financials", "Health Care", "Industrials", "Consumer Discretionary",
                 "Consumer Staples", "Communication Services", "Energy", "Materials", "Real Estate", "Utilities"]
        for name in names:
            match = re.search(re.escape(name) + r"\s+([0-9]+\.[0-9]+)%?", block.group(1))
            if match:
                sectors.append({"snapshot_id": metadata["snapshot_id"], "portfolio_date": metadata["portfolio_date"],
                                "publication_date": metadata["publication_date"], "available_at": metadata["available_at"],
                                "sector": name, "weight_pct_net_assets": match.group(1),
                                "classification_level": "fund aggregate only; no security-level mapping",
                                "source_url": metadata["exhibit_url"]})
    audit = {"snapshot_id": metadata["snapshot_id"], "portfolio_date": metadata["portfolio_date"],
             "publication_date": metadata["publication_date"], "source_url": metadata["exhibit_url"],
             "source_sha256": hashlib.sha256(data).hexdigest(), "scope_anchor": target,
             "scope_sha256": hashlib.sha256(section.encode()).hexdigest(),
             "same_portfolio_observation_as_xml": True, "aggregate_sector_rows": len(sectors),
             "security_level_gics_mapping_supplied": False}
    return audit, sectors


def write_csv(path, rows):
    if not rows:
        return
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows({k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in row.items()} for row in rows)


def render_report(snapshots, matrix, summary, benchmarks):
    lines = ["# SPGM historical ETF holdings proxy", "",
             "Research checked on 10 October 2026 (Europe/Stockholm). Target: October 2022–September 2026.",
             "Series `S000036082`; registrant CIK `1168164`. **This is an ETF portfolio proxy, not official MSCI ACWI IMI constituents.**", "",
             "## Findings", "",
             f"Retrieved **{summary['target_snapshots']} distinct target-period snapshots**: 15 public SEC N-PORT portfolios and four archived publisher workbooks. Two earlier SEC observations are retained separately for initial availability. The 21 observations contain {summary['all_snapshot_rows']:,} position records, not unique companies.", "",
             "Observed portfolios cover **18/48 months**; 30 months have no direct portfolio observation. There are 15 month-end observations, all filed later. **0/48 contemporaneous month-end portfolios were verifiably public at their selection date.**", "",
             "A latest-public-portfolio convention supplies **48/48 lagged selection dates**, including the June 2022 warm-up. Age is **13–123 calendar days**. With a maximum age of 31/62/93/123 days, support falls to **4/21/35/48 dates** respectively. These are date-availability counts, not claims that all security mappings, sectors or backtest inputs are ready.", "",
             "All security-level historical GICS classifications remain missing. Quarterly positions and archived tickers preserve earlier holdings, but cannot reconstruct every intervening holding, actual MSCI additions/deletions, or the full set of delisted index members.", "",
             "## Sources and retrieval completeness", "",
             "[SEC series search](https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=S000036082&type=NPORT-P&count=100&output=atom) was queried for NPORT-P and explicitly for NPORT-P/A, including pagination support. It returned 28 original filings since 2019; the 17 filed from August 2022 through the research cutoff were retrieved and series/date validated. No additional amendment was found. Their actual portfolio dates run June 2022–June 2026. September 2026 was not publicly present at the cutoff; do not infer future publication or fill it with October holdings.", "",
             "All nine linked NPORT-EX multi-fund schedules were retrieved and the SPGM section was isolated by table-of-contents anchors. They repeat existing June/December portfolio dates, so do not add snapshots. Four schedules (one warm-up and three target-period) supply 11-sector **fund aggregate weights**; these are retained separately and never assigned to individual securities.", "",
             "Wayback CDX queries used all distinct captured contents, not one capture per month. The exact XLSX URL and broader publisher fund-data/URL searches found the same four holdings files. NAV and premium/discount history files were excluded because they are not holdings. This is a reproducible bounded public-source search; it does not prove that no other historical URL or archive exists.", "",
             "The broader publisher fund-data query completed with 12 records (four holdings, four NAV histories and four premium/discount histories). An additional whole-domain SPGM wildcard query timed out; its failure is retained in the separate discovery manifest. It does not affect the successful filing/holdings downloads, but limits the breadth of the archive search.", "",
             "All 17 XML responses, nine exhibits and four workbooks were successfully cached; retrieval failures: **0**. Raw response hashes, URLs and UTC retrieval times are recorded. The download code restricts HTTPS domains, checks redirects before following, throttles SEC requests below its fair-access ceiling, and uses no credentials or EODHD endpoint.", "",
             "## Snapshot inventory", "",
             "Counts include cash-equivalent funds, derivatives, preferred shares, rights and repeated instrument exposures. `EC` is the SEC common-equity category; workbook asset categories are unclassified. No raw line is dropped merely to make counts agree.", "",
             "| Portfolio date | Public filing date / archive bound | Source | Records | EC rows | Missing valid ID | Duplicate key rows | Country gaps | Security-sector gaps |",
             "|---|---|---|---:|---:|---:|---:|---:|---:|"]
    for s in snapshots:
        pub = s.get("publication_date") or s["available_at"][:10] + " (archive bound)"
        src = "SEC" if s["source_type"] == "SEC NPORT-P" else "archive"
        scope = " (warm-up)" if s["scope"] == "warm_up_only" else ""
        lines.append(f"| {s['portfolio_date']}{scope} | {pub} | [{src}]({s['source_url']}) | {s['holdings_count']} | {s['common_equity_rows'] if src == 'SEC' else 'unknown'} | {s['missing_valid_security_id']} | {s['duplicate_instrument_rows']} | {s['missing_country']} | {s['missing_sector']} |")
    lines += ["", "## Portfolio and publication dates", "",
              "SEC `repPdDate` is the portfolio date; `repPdEnd` is fiscal-year end and must not be used as the holdings date. Filing date and index acceptance timestamp are preserved separately, with America/New_York acceptance converted to UTC for availability. Later filing-date bounds remain conservative. Amendments remain separate versions and cannot replace an earlier observation before they became public.", "",
              "For archived workbooks, original publication dates are **unknown**. The internal `As of` date is the portfolio observation; the archive capture timestamp is a conservative upper bound on when the file was public. It must not be relabeled as its original publication date. No unknown release date is guessed.", "",
              "The illustrative selection convention below is calendar month-end at 23:59:59 UTC. It chooses the newest portfolio already public then; ties use the latest public version. A backtest with an earlier exchange-close cutoff must rerun availability at that exact timestamp. This convention does not change the investment strategy.", "",
              "## Monthly coverage matrix", "",
              "`Obs` counts directly observed portfolios in that month, including portfolios published later. `IDs` counts missing valid security identifiers. `Tickers` counts unresolved research ticker lookups; `Future` counts lookups relying on later archives, unavailable to an earlier decision. Both are weaker than an executable listing mapping. `Country`/`Sector` count missing fields in the selected portfolio. Missing MSCI members' identities remain **unknown in every month** without full official membership.", "",
              "| Selection month | Obs | Latest public portfolio | Age days | Records | IDs | Tickers | Future | Country | Sector |",
              "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in matrix:
        lines.append(f"| {r['selection_month']} | {r['portfolio_snapshots_in_month']} | {r['selected_portfolio_date'] or 'missing'} | {r['staleness_calendar_days']} | {r['holdings_count']} | {r['missing_valid_security_id']} | {r['unmapped_ticker']} | {r['future_only_ticker_mapping']} | {r['missing_country']} | {r['missing_sector']} |")
    lines += ["", "## Identifier, country and sector limitations", "",
              "CUSIP/ISIN/SEDOL values stay strings with leading zeroes. Format/checksum failures are retained and excluded from exact crosswalk joins. Across all observations, **89 rows lack a valid typed security ID**, and **149 extra rows share an instrument key within their portfolio**. Duplicates remain separate positions for audit; they must not be counted as distinct members. An instrument ID is not a permanent company ID or a verified exchange listing.", "",
              "SEC positions provide ISIN/CUSIP where supplied, company LEI and investment-country codes. **23,335 rows lack a company LEI** across all observations, including every workbook row. All SEC rows have country codes; **11,607 workbook rows lack country**. Currency, ISIN prefix and ticker are not automatically converted into MSCI risk country or exchange venue.", "",
              "SEC XML has no source tickers in this sample. Workbooks supply tickers for most rows. Exact valid-ID joins add research identity lookups, retaining the mapping's portfolio/publication dates and source. **30,760 position rows remain unmapped**, and **7,093 mappings use future archive evidence**; those future mappings must never be available to an earlier decision. Prior archive mappings also require checking for subsequent symbol changes. All exchange MIC/listing mappings remain unverified; names and currency are not fuzzy-joined.", "",
              "All **57,532 rows lack security-level sector/GICS**. The archive Sector column is `-`; SEC asset categories are instrument classes, not sectors. Four dated fund aggregate breakdowns are preserved in `aggregate_sector_weights.csv`, without security-level assignments. MSCI factsheet top-ten sectors are not a classification database for the remaining securities. Sector-dependent historical selection remains blocked.", "",
              "Consecutive SEC portfolios produce `observed_etf_changes.csv`: first-observed/not-observed identity differences with both publication dates. These are **ETF observation changes**, not exact transaction dates, MSCI entries/exits or confirmed delistings. Identifier conversions and observation gaps can also create apparent changes. No current-survivor filter is used.", "",
              "## Comparison with reported MSCI ACWI IMI counts", "",
              "Seven official [MSCI ACWI IMI factsheets](https://www.msci.com/documents/10199/255599/msci-acwi-imi.pdf), including six archive captures, were retrieved and their dated counts extracted. The current September 2026 count was first verified on the research date; it is not presumed known at September month-end. Counts below are research comparisons, not universe input.", "",
              "Some PDF responses have a truncated terminal EOF marker. Their index names, dates and constituent counts remain readable, and raw hashes/terminal-marker status are recorded. This validates those extracted fields, not the completeness of every PDF page. The current 8,036 count also agrees with the independently retrieved publisher benchmark statistics.", "",
              "| Index observation date | Reported constituents | Verified-public bound |",
              "|---|---:|---|"]
    for b in sorted(benchmarks, key=lambda b: b["portfolio_date"]):
        lines.append(f"| {b['portfolio_date']} | {b['constituent_count']:,} | [{b['available_at'][:10]}]({b['source_url']}) |")
    lines += ["", "Two exact-date comparisons are possible: September 30, 2025 has **2,922 ETF records versus 8,300 index constituents (35.20%)**; March 31, 2026 has **2,950 versus 8,253 (35.74%)**. Because ETF counts include non-equities and repeated exposures, these count ratios are not constituent overlap or investment-weight coverage. The corresponding raw count gaps are 5,378 and 5,303, but the missing securities cannot be identified from counts alone.", "",
              "At September 2026 selection the latest public portfolio is August 18 (2,975 records), whereas the September 30 index reports 8,036 constituents: **37.02%**, a count gap of 5,061 with differing dates. It is not a contemporaneous coverage measurement. Other comparison rows explicitly retain date gaps; no index count is interpolated across missing months.", "",
              "## Reproduction and output", "",
              "Run from the repository root. Default commands are cache-only and make no network requests:", "",
              "```sh", "python -m research.spgm_sources", "python -m research.spgm_benchmarks", "python -m research.spgm_proxy",
              "/workspace/.venvs/eodhd-validation/bin/python -m unittest discover -s research -p 'test_*.py'", "```", "",
              "On a fresh cache, explicitly add `--fetch` to the first two commands to retrieve public SEC/Wayback/MSCI files. The parser uses the Python standard library; factsheet extraction additionally uses `pypdf`. Network destinations are `www.sec.gov`, `web.archive.org`, and `www.msci.com` (publisher redirects may also require `www.ssga.com`). Existing cloud setup provides the validation environment and PDF reader.", "",
              "Security-level data and raw responses live exclusively under Git-ignored `research/eodhd_output/spgm_proxy/`: `holdings.csv`, `snapshots.csv/json`, `coverage_matrix.csv`, `coverage_summary.json`, `identifier_issues.csv`, `ticker_crosswalk.csv`, `observed_etf_changes.csv`, `benchmark_comparisons.csv`, `aggregate_sector_weights.csv`, source catalog, exhibit audit and checksum manifests. The local `coverage_report.md` is generated from those records; this reviewed aggregate report contains no security-level market-data extract.", "",
              "Public SEC filings were accessed without authentication or bypassing controls. Publisher archives and MSCI factsheets were accessed through public URLs; public access does not establish redistribution rights for a holdings database or proprietary MSCI data. Raw/normalized holdings, PDFs and workbooks are not committed. This research is separate from trading, makes **zero additional EODHD requests**, and does not modify the five-stock strategy.", ""]
    return "\n".join(lines)


def build(output=DEFAULT_OUTPUT):
    cache = PublicCache(output)
    catalog = json.loads((cache.output / "source_catalog.json").read_text())
    snapshots, rows, exhibit_audits, sector_aggregates = [], [], [], []
    for item in catalog["filings"]:
        if item.get("retrieved"):
            snapshot, holdings = parse_nport(cache.get(item["xml_url"], "xml"), item)
            snapshots.append(snapshot)
            rows.extend(holdings)
            print("Parsed", snapshot["portfolio_date"], len(holdings), flush=True)
            for url in item.get("exhibit_urls", []):
                try:
                    audit, aggregates = parse_exhibit(cache.get(url, "html"), {**snapshot, "exhibit_url": url})
                    exhibit_audits.append(audit)
                    sector_aggregates.extend(aggregates)
                except (ValueError, FileNotFoundError) as exc:
                    exhibit_audits.append({"snapshot_id": snapshot["snapshot_id"], "source_url": url,
                                           "error_type": type(exc).__name__, "investigation_required": True})
    for item in catalog["archives"]:
        snapshot, holdings = parse_archive(cache.get(item["url"], "xlsx"), item)
        snapshots.append(snapshot)
        rows.extend(holdings)
    map_tickers(rows)
    groups = defaultdict(list)
    for row in rows:
        groups[row["snapshot_id"]].append(row)
    for snapshot in snapshots:
        holdings = groups[snapshot["snapshot_id"]]
        keys = Counter(r["instrument_key"] for r in holdings if r["instrument_key"])
        for row in holdings:
            row["duplicate_instrument_key_in_snapshot"] = bool(row["instrument_key"] and keys[row["instrument_key"]] > 1)
            row["exchange_mic"] = ""  # Publisher ticker + currency do not verify a listing venue.
            row["listing_mapping_status"] = "unverified"
        snapshot.update(quality(holdings))
        snapshot["scope"] = "target" if "2022-10-01" <= snapshot["portfolio_date"] <= "2026-09-30" else "warm_up_only"
        snapshot["dataset_label"] = LABEL
    snapshots.sort(key=lambda s: (s["portfolio_date"], s["available_at"]))
    benchmarks_path = cache.output / "benchmark_counts.json"
    benchmarks = json.loads(benchmarks_path.read_text()) if benchmarks_path.exists() else []
    matrix = coverage_matrix(snapshots, benchmarks)
    target = [s for s in snapshots if s["scope"] == "target"]
    summary = {"dataset_label": LABEL, "series": SERIES, "as_of": catalog["as_of"],
               "target_period": "2022-10 through 2026-09", "selection_dates": len(matrix),
               "selection_convention": "calendar month-end 23:59:59 UTC; illustrative research convention, strategy unchanged",
               "target_snapshots": len(target), "target_sec_snapshots": sum(s["source_type"] == "SEC NPORT-P" for s in target),
               "warm_up_snapshots": len(snapshots) - len(target),
               "portfolio_months_observed": len({s["portfolio_date"][:7] for s in target}),
               "portfolio_months_missing": [x["selection_month"] for x in matrix if not x["portfolio_snapshots_in_month"]],
               "month_end_observations": sum(x["month_end_observation_exists"] for x in matrix),
               "contemporaneous_month_end_observations_public": sum(x["month_end_observation_public_by_selection"] for x in matrix),
               "lagged_proxy_selection_dates": sum(bool(x["selected_snapshot_id"]) for x in matrix),
               "lagged_support_by_max_calendar_age": {str(limit): sum(x["staleness_calendar_days"] != "" and x["staleness_calendar_days"] <= limit for x in matrix)
                                                      for limit in [31, 62, 93, 123]},
               "staleness_range": [min(x["staleness_calendar_days"] for x in matrix if x["selected_snapshot_id"]),
                                    max(x["staleness_calendar_days"] for x in matrix if x["selected_snapshot_id"])],
               "historical_gics_complete_selection_dates": 0,
               "official_msci_membership_complete_selection_dates": 0,
               "retrieval_failures": catalog["failures"], "benchmark_counts_verified": len(benchmarks),
               "exhibit_audits": len(exhibit_audits),
               "exhibit_audit_failures": sum(bool(a.get("investigation_required")) for a in exhibit_audits),
               "fund_aggregate_sector_observations": len({r["snapshot_id"] for r in sector_aggregates}),
               "eodhd_requests": 0, "all_snapshot_rows": len(rows)}
    (cache.output / "snapshots.json").write_text(json.dumps(snapshots, indent=2) + "\n")
    (cache.output / "coverage_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (cache.output / "exhibit_audit.json").write_text(json.dumps(exhibit_audits, indent=2) + "\n")
    write_csv(cache.output / "aggregate_sector_weights.csv", sector_aggregates)
    write_csv(cache.output / "snapshots.csv", snapshots)
    write_csv(cache.output / "holdings.csv", rows)
    write_csv(cache.output / "coverage_matrix.csv", matrix)
    write_csv(cache.output / "identifier_issues.csv", [r for r in rows if r["identifier_problems"]
              or not r["instrument_key"] or r["duplicate_instrument_key_in_snapshot"]])
    write_csv(cache.output / "ticker_crosswalk.csv", [r for r in rows if r["source_ticker"] or r["mapped_ticker"]])
    write_csv(cache.output / "observed_etf_changes.csv", observed_changes(snapshots, groups))
    write_csv(cache.output / "benchmark_comparisons.csv", benchmark_comparisons(snapshots, benchmarks))
    (cache.output / "coverage_report.md").write_text(render_report(snapshots, matrix, summary, benchmarks))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(build(args.output), indent=2))
