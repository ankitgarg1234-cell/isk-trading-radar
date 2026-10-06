"""Consolidated, unit-checked SEC evidence; never blend accounting taxonomies."""
from html.parser import HTMLParser
import math
import re

ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}
FINANCIAL_FORMS = ANNUAL_FORMS | {"10-Q", "10-Q/A", "6-K", "6-K/A"}

# Only equivalent whole-company measures are mapped. IFRS CostOfSales can omit
# separately presented production depreciation; do not infer a gross margin.
IFRS_MAP = {
    "Revenues": "Revenue", "NetIncomeLoss": "ProfitLoss", "GrossProfit": "GrossProfit",
    "OperatingIncomeLoss": "ProfitLossFromOperatingActivities",
    "StockholdersEquity": "Equity", "AssetsCurrent": "CurrentAssets",
    "LiabilitiesCurrent": "CurrentLiabilities", "Liabilities": "Liabilities",
    "NetCashProvidedByUsedInOperatingActivities": "CashFlowsFromUsedInOperatingActivities",
}
US_TAGS = set(IFRS_MAP) | {
    "RevenueFromContractWithCustomerExcludingAssessedTax", "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet", "ProfitLoss", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    "CostOfRevenue", "CostOfGoodsAndServicesSold", "LongTermDebt", "DebtCurrent",
    "ShortTermBorrowingsAndCurrentPortionOfLongTermDebt", "ShortTermBorrowings", "ShortTermBorrowingsCurrent",
    "LongTermDebtCurrent", "LongTermDebtNoncurrent", "LongTermDebtAndFinanceLeaseObligationsCurrent",
    "LongTermDebtAndFinanceLeaseObligationsNoncurrent", "LongTermDebtAndFinanceLeaseObligationsIncludingCurrentMaturities",
}


class _Inline(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.record = None
        self.contexts, self.units, self.values = {}, {}, []

    def handle_starttag(self, tag, attrs):
        local = tag.split(":")[-1]
        if self.record is None:
            if local not in {"context", "unit", "nonfraction"}:
                return
            self.record = {"kind": local, "attrs": dict(attrs), "stack": [local], "fields": {}, "text": [], "dimension": False}
        else:
            self.record["stack"].append(local)
            if local in {"explicitmember", "typedmember", "segment", "scenario"}:
                self.record["dimension"] = True

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data):
        if self.record:
            self.record["text"].append(data)
            self.record["fields"].setdefault(self.record["stack"][-1], []).append(data)

    def handle_endtag(self, tag):
        if not self.record:
            return
        local = tag.split(":")[-1]
        if local not in self.record["stack"]:
            return
        while self.record["stack"]:
            popped = self.record["stack"].pop()
            if popped == local:
                break
        if self.record["stack"]:
            return
        r, self.record = self.record, None
        fields = {k: "".join(v).strip() for k, v in r["fields"].items()}
        if r["kind"] == "context":
            self.contexts[r["attrs"].get("id")] = (fields, r["dimension"])
        elif r["kind"] == "unit":
            # Reject compound units (EPS, currency/share), not just their first measure.
            if "divide" not in fields and len(r["fields"].get("measure", [])) == 1:
                self.units[r["attrs"].get("id")] = fields.get("measure", "").split(":")[-1]
        else:
            self.values.append((r["attrs"], "".join(r["text"]).strip()))


def inline_facts(html, *, cik, form, filed, accn, report_date):
    """Read only unsegmented USD/share facts belonging to the expected filer.

    Context dates, scale and sign come from the filing. Conflicting duplicate
    facts are discarded; an empty/dash value is not assumed to be zero.
    """
    parser = _Inline()
    parser.feed(html)
    keep, conflicts = {}, set()
    for attrs, text in parser.values:
        name = attrs.get("name", "")
        if ":" not in name:
            continue
        ns, tag = name.split(":", 1)
        allowed = (ns == "us-gaap" and tag in US_TAGS or ns == "ifrs-full" and tag in IFRS_MAP.values()
                   or ns == "dei" and tag == "EntityCommonStockSharesOutstanding")
        context, dimension = parser.contexts.get(attrs.get("contextref"), ({}, True))
        unit = parser.units.get(attrs.get("unitref"))
        if not allowed or dimension or unit != ("shares" if ns == "dei" else "USD"):
            continue
        if any(k.split(":")[-1] == "nil" and v.lower() in {"true", "1"} for k, v in attrs.items()):
            continue
        if str(context.get("identifier", "")).lstrip("0") != str(cik).lstrip("0"):
            continue
        start, end = context.get("startdate"), context.get("enddate") or context.get("instant")
        if not end or end > report_date:
            continue
        if attrs.get("format") and attrs["format"].split(":")[-1] not in {"num-dot-decimal", "numdotdecimal"}:
            continue
        try:
            scale = int(attrs.get("scale", 0))
            if not -12 <= scale <= 12 or not re.fullmatch(r"[+-]?[\d,]+(?:\.\d+)?", text):
                continue
            value = float(text.replace(",", "")) * 10 ** scale
            if attrs.get("sign") == "-":
                if value < 0:
                    continue
                value = -value
            if not math.isfinite(value):
                continue
        except (TypeError, ValueError, OverflowError):
            continue
        key = (ns, tag, unit, start, end)
        row = {"end": end, "val": value, "form": form, "filed": filed, "accn": accn}
        if start:
            row["start"] = start
        if key in keep and keep[key]["val"] != value:
            conflicts.add(key)
        keep[key] = row
    return [(key, row) for key, row in keep.items() if key not in conflicts]


def merge_inline(facts, rows):
    out = {**facts, "facts": {**facts.get("facts", {})}}
    for (ns, tag, unit, _, _), row in rows:
        namespace = out["facts"].setdefault(ns, {}).copy()
        concept = namespace.get(tag, {}).copy()
        units = concept.get("units", {}).copy()
        existing = units.get(unit, [])
        matching = [r for r in existing if r.get("accn") == row["accn"]
                    and r.get("start") == row.get("start") and r.get("end") == row["end"]]
        if any(r.get("val") != row["val"] for r in matching):
            units[unit] = [r for r in existing if r not in matching]
        else:
            units[unit] = [*existing, row]
        concept["units"] = units
        namespace[tag] = concept
        out["facts"][ns] = namespace
    return out


def accounting_facts(facts, annual_values):
    """Choose the newer annual revenue taxonomy, preserving one accounting basis."""
    namespaces = facts.get("facts", {})
    def latest(ns, tags):
        return max((r.get("end", "") for tag in tags
                    for r in annual_values(namespaces.get(ns, {}).get(tag))), default="")
    us = latest("us-gaap", ("RevenueFromContractWithCustomerExcludingAssessedTax",
                           "RevenueFromContractWithCustomerIncludingAssessedTax", "Revenues", "SalesRevenueNet"))
    ifrs = latest("ifrs-full", ("Revenue",))
    if ifrs and ifrs > us:
        mapped = {key: namespaces["ifrs-full"][tag] for key, tag in IFRS_MAP.items() if tag in namespaces["ifrs-full"]}
        return {**facts, "facts": {**namespaces, "us-gaap": mapped}}, "IFRS"
    return facts, "US GAAP"
