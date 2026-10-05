from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any
import time
import math
import re
import json
from collections import OrderedDict
from threading import Lock
from .market_evidence import EndpointCache, positive, matched_relative_volume
from difflib import SequenceMatcher
import httpx

from .config import settings
from .strategic_capital import StrategicCapitalProvider

UA = "Mozilla/5.0 ISK-Trading-Radar/1.0"

SECTOR_ETF = {
    "Technology": "XLK", "Communication Services": "XLC", "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP", "Financial Services": "XLF", "Healthcare": "XLV",
    "Industrials": "XLI", "Energy": "XLE", "Basic Materials": "XLB",
    "Real Estate": "XLRE", "Utilities": "XLU",
}


class MarketDataError(RuntimeError):
    pass


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        result = float(value)
        return result if math.isfinite(result) else None
    except Exception:
        return None


def _iso_days(start: str | None, end: str | None) -> int | None:
    if not start or not end:
        return None
    try:
        return (datetime.fromisoformat(end) - datetime.fromisoformat(start)).days
    except Exception:
        return None


def sic_to_sector(sic: int | str | None, description: str = "") -> str | None:
    """Map SEC SIC metadata to a broad SPDR-style sector.

    SIC is not a perfect GICS substitute; this mapping is intentionally broad and
    deterministic. It is used only to choose a benchmark ETF when Yahoo sector
    metadata is unavailable.
    """
    try:
        code = int(sic or 0)
    except Exception:
        code = 0
    d = (description or "").lower()

    # Strong keyword overrides for ambiguous manufacturing/service ranges.
    if any(x in d for x in ("pharmaceutical", "biological", "medical", "hospital", "health")):
        return "Healthcare"
    if any(x in d for x in ("software", "computer", "semiconductor", "electronic", "data processing")):
        return "Technology"
    if any(x in d for x in ("telecommunication", "broadcast", "radio", "television", "motion picture")):
        return "Communication Services"
    if any(x in d for x in ("real estate", "reit")):
        return "Real Estate"
    if any(x in d for x in ("bank", "insurance", "investment", "credit", "finance", "broker")):
        return "Financial Services"
    if any(x in d for x in ("electric service", "gas service", "water supply", "utility")):
        return "Utilities"
    if any(x in d for x in ("oil", "gas extraction", "petroleum", "coal")):
        return "Energy"

    if 6000 <= code <= 6799:
        return "Financial Services"
    if 6500 <= code <= 6599:
        return "Real Estate"
    if 4900 <= code <= 4999:
        return "Utilities"
    if 4800 <= code <= 4899 or 7800 <= code <= 7841:
        return "Communication Services"
    if 8000 <= code <= 8099 or 2830 <= code <= 2836 or 3840 <= code <= 3851:
        return "Healthcare"
    if 1300 <= code <= 1399 or code in {2911, 2990}:
        return "Energy"
    if 1000 <= code <= 1299 or 1400 <= code <= 1499 or 2600 <= code <= 2699 or 2800 <= code <= 2829 or 2840 <= code <= 2899 or 3300 <= code <= 3399:
        return "Basic Materials"
    if 3570 <= code <= 3579 or 3650 <= code <= 3699 or 7370 <= code <= 7379:
        return "Technology"
    if 2000 <= code <= 2199 or 5400 <= code <= 5499:
        return "Consumer Defensive"
    if 2300 <= code <= 2599 or 3100 <= code <= 3199 or 5200 <= code <= 5399 or 5500 <= code <= 5999 or 7000 <= code <= 7299:
        return "Consumer Cyclical"
    if 1500 <= code <= 1799 or 3400 <= code <= 3569 or 3600 <= code <= 3649 or 3700 <= code <= 3799 or 4000 <= code <= 4799:
        return "Industrials"
    return None


class SECFundamentalsProvider:
    """No-key U.S. fundamentals fallback using official SEC EDGAR JSON APIs."""

    _ticker_cache: dict[str, dict] = {}
    _ticker_cache_at: float = 0.0

    def __init__(self, timeout: float = 12.0, user_agent: str | None = None):
        self.client = httpx.Client(
            timeout=timeout,
            headers={
                "User-Agent": user_agent or settings.sec_user_agent,
                "Accept-Encoding": "gzip, deflate",
                "Accept": "application/json",
            },
            follow_redirects=True,
        )

    def _json(self, url: str) -> dict:
        r = self.client.get(url)
        r.raise_for_status()
        return r.json()

    def _ticker_map(self) -> dict[str, dict]:
        now = time.time()
        if self.__class__._ticker_cache and now - self.__class__._ticker_cache_at < 24 * 3600:
            return self.__class__._ticker_cache
        raw = self._json("https://www.sec.gov/files/company_tickers.json")
        mapped: dict[str, dict] = {}
        for item in raw.values() if isinstance(raw, dict) else []:
            ticker = str(item.get("ticker") or "").upper().strip()
            if ticker:
                mapped[ticker] = item
        self.__class__._ticker_cache = mapped
        self.__class__._ticker_cache_at = now
        return mapped

    def resolve(self, symbol: str) -> dict | None:
        symbol = symbol.upper().strip()
        # SEC association file is U.S.-company oriented. Do not force foreign .ST symbols.
        if symbol.endswith(".ST"):
            return None
        candidates = [symbol, symbol.replace(".", "-"), symbol.replace("-", ".")]
        m = self._ticker_map()
        for candidate in candidates:
            if candidate in m:
                row = m[candidate]
                cik = int(row.get("cik_str"))
                return {"cik": cik, "cik10": f"{cik:010d}", "title": row.get("title"), "ticker": candidate}
        return None

    @staticmethod
    def _fact(facts: dict, tags: tuple[str, ...]) -> dict | None:
        us = (facts.get("facts") or {}).get("us-gaap") or {}
        for tag in tags:
            if tag in us:
                return us[tag]
        return None

    @staticmethod
    def _entries(fact: dict | None, preferred_units: tuple[str, ...]) -> list[dict]:
        if not fact:
            return []
        units = fact.get("units") or {}
        for unit in preferred_units:
            if unit in units:
                return list(units.get(unit) or [])
        # Never silently divide USD facts by another currency or unit.
        return []

    @classmethod
    def _annual_values(cls, fact: dict | None, units: tuple[str, ...] = ("USD",)) -> list[dict]:
        rows = cls._entries(fact, units)
        keep: dict[str, dict] = {}
        for r in rows:
            if r.get("form") not in {"10-K", "10-K/A", "20-F", "20-F/A"}:
                continue
            days = _iso_days(r.get("start"), r.get("end"))
            if days is None or not 300 <= days <= 430:
                continue
            end = r.get("end")
            if not end or _safe_float(r.get("val")) is None:
                continue
            prior = keep.get(end)
            if not prior or str(r.get("filed") or "") >= str(prior.get("filed") or ""):
                keep[end] = r
        return sorted(keep.values(), key=lambda x: x.get("end") or "")

    @classmethod
    def _quarter_values(cls, fact: dict | None, units: tuple[str, ...] = ("USD",)) -> list[dict]:
        rows = cls._entries(fact, units)
        keep: dict[str, dict] = {}
        for r in rows:
            if r.get("form") not in {"10-Q", "10-Q/A", "10-K", "10-K/A", "20-F", "20-F/A"}:
                continue
            days = _iso_days(r.get("start"), r.get("end"))
            # Filing labels describe the filing, not the comparative fact. Require
            # actual quarter dates, including quarter-duration facts in annual reports.
            if days is None or not 65 <= days <= 120:
                continue
            end = r.get("end")
            if not end or _safe_float(r.get("val")) is None:
                continue
            prior = keep.get(end)
            if not prior or str(r.get("filed") or "") >= str(prior.get("filed") or ""):
                keep[end] = r

        # Q4 is often absent as a standalone fact. Derive it only from an annual
        # total and nine-month YTD with the identical fiscal-year start. Summing
        # arbitrary quarter rows risks overlap, missing quarters and restatements.
        for annual in cls._annual_values(fact, units):
            end = annual["end"]
            annual_revised = any(
                r.get("start") == annual.get("start") and r.get("end") == end
                and r.get("val") != annual.get("val")
                for r in rows if r.get("form") in {"10-K", "10-K/A", "20-F", "20-F/A"}
            )
            if end in keep:
                if not annual_revised or str(keep[end].get("filed") or "") >= str(annual.get("filed") or ""):
                    continue
                # An old standalone Q4 does not establish the revised quarter.
                del keep[end]
            ytd_rows = [r for r in rows
                        if r.get("form") in {"10-Q", "10-Q/A", "10-K", "10-K/A", "20-F", "20-F/A"}
                        and r.get("start") == annual.get("start")
                        and 240 <= (_iso_days(r.get("start"), r.get("end")) or 0) <= 310
                        and 65 <= (_iso_days(r.get("end"), end) or 0) <= 120
                        and _safe_float(r.get("val")) is not None]
            if not ytd_rows:
                continue
            ytd = max(ytd_rows, key=lambda r: (str(r.get("filed") or ""), str(r["end"])))
            # A changed annual comparative filed after the interim may have a
            # different accounting scope. Do not subtract an unrevised interim.
            changed_after_ytd = annual_revised and str(annual.get("filed") or "") > str(ytd.get("filed") or "")
            same_filing = bool(annual.get("accn") and annual.get("accn") == ytd.get("accn"))
            if changed_after_ytd and not same_filing:
                continue
            total = _safe_float(annual.get("val"))
            value = total - float(ytd["val"]) if total is not None else None
            if value is None or value < 0:
                continue
            keep[end] = {
                **annual,
                "start": (datetime.fromisoformat(ytd["end"]) + timedelta(days=1)).date().isoformat(),
                "val": value, "_derived": "annual minus nine-month YTD",
                "_ytd_accn": ytd.get("accn"), "_ytd_end": ytd["end"],
            }
        return sorted(keep.values(), key=lambda x: x.get("end") or "")

    @classmethod
    def _latest_instant(cls, fact: dict | None, units: tuple[str, ...] = ("USD",)) -> float | None:
        rows = cls._entries(fact, units)
        candidates = [r for r in rows if r.get("form") in {"10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "20-F/A"} and r.get("end") and r.get("val") is not None]
        if not candidates:
            return None
        candidates.sort(key=lambda r: (str(r.get("end") or ""), str(r.get("filed") or "")))
        return _safe_float(candidates[-1].get("val"))

    @staticmethod
    def _growth_pair(rows: list[dict]) -> tuple[dict, dict]:
        if len(rows) < 2:
            return {}, {}
        rows = sorted(rows, key=lambda r: str(r.get("end") or ""))
        current = rows[-1]
        candidates = [r for r in rows[:-1]
                      if 350 <= (_iso_days(r.get("end"), current.get("end")) or 0) <= 380
                      and 350 <= (_iso_days(r.get("start"), current.get("start")) or 0) <= 380]
        previous = min(candidates, key=lambda r: abs(_iso_days(r["end"], current["end"])-365)) if candidates else {}
        return current, previous

    @classmethod
    def _growth(cls, rows: list[dict]) -> float | None:
        current, previous = cls._growth_pair(rows)
        value, base = _safe_float(current.get("val")), _safe_float(previous.get("val"))
        # A percentage growth rate is not meaningful against a loss or zero base.
        return value / base - 1 if value is not None and base is not None and base > 0 else None

    @classmethod
    def _earnings_change(cls, rows: list[dict]) -> str:
        current, previous = cls._growth_pair(rows)
        value, base = _safe_float(current.get("val")), _safe_float(previous.get("val"))
        if value is None or base is None:
            return "no comparable fiscal year"
        if base > 0:
            return "profit to loss" if value < 0 else "percentage growth available"
        if base == 0:
            return "zero prior-year income; percentage growth unavailable"
        if value >= 0:
            return "returned to profitability" if value > 0 else "returned to breakeven"
        return "improving loss" if value > base else "worsening loss" if value < base else "unchanged loss"

    @classmethod
    def _instant_at(cls, fact: dict | None, end: str) -> float | None:
        candidates = [r for r in cls._entries(fact, ("USD",))
                      if r.get("end") == end and not r.get("start")
                      and r.get("form") in {"10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "20-F/A"}]
        latest = max(candidates, key=lambda r: str(r.get("filed") or ""), default={})
        return _safe_float(latest.get("val"))

    @classmethod
    def _debt_at(cls, facts: dict, end: str) -> tuple[float | None, str]:
        def value(tags):
            # Aliases are alternatives, not additive line items. Prefer fresh
            # facts at the requested balance-sheet date, never an obsolete tag.
            rows = [r for tag in tags for r in cls._entries(cls._fact(facts, (tag,)), ("USD",))
                    if r.get("end") == end and not r.get("start")
                    and r.get("form") in {"10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "20-F/A"}]
            latest = max(rows, key=lambda r: str(r.get("filed") or ""), default={})
            return _safe_float(latest.get("val"))
        short = value(("ShortTermBorrowings", "ShortTermBorrowingsCurrent"))
        if short is not None and short < 0:
            return None, "invalid negative short-term borrowings"
        current_total = value(("DebtCurrent", "ShortTermBorrowingsAndCurrentPortionOfLongTermDebt"))
        # A historical short-term-borrowing series cannot silently become zero.
        if current_total is None and short is None and any(cls._fact(facts, (tag,)) for tag in ("ShortTermBorrowings", "ShortTermBorrowingsCurrent")):
            return None, "short-term borrowings missing at balance-sheet date"
        total_long = value(("LongTermDebtAndFinanceLeaseObligationsIncludingCurrentMaturities", "LongTermDebt"))
        if total_long is not None:
            total = total_long + (short if short is not None else 0)
        else:
            # These total-current tags already include short-term borrowings.
            current_long = value(("LongTermDebtAndFinanceLeaseObligationsCurrent", "LongTermDebtCurrent"))
            noncurrent = value(("LongTermDebtAndFinanceLeaseObligationsNoncurrent", "LongTermDebtNoncurrent"))
            if noncurrent is None or (current_total is None and current_long is None):
                return None, "incomplete debt components at balance-sheet date"
            if any(v is not None and v < 0 for v in (noncurrent, current_total, current_long)):
                return None, "invalid negative debt component"
            total = noncurrent + (current_total if current_total is not None else current_long + (short if short is not None else 0))
        if total < 0:
            return None, "invalid negative debt"
        return total, "reported debt tags; aliases excluded from sums"

    @staticmethod
    def _quarter_yoy_growth(rows: list[dict]) -> float | None:
        """Match actual period dates, never the SEC filing's fy/fp labels."""
        if len(rows) < 2:
            return None
        rows = sorted(rows, key=lambda r: str(r.get("end") or ""))
        latest = rows[-1]
        current = _safe_float(latest.get("val"))
        if current is None:
            return None

        candidates: list[tuple[float, dict]] = []
        for prior in rows[:-1]:
            days = _iso_days(prior.get("end"), latest.get("end"))
            # Calendar and 52/53-week years, without accepting an adjacent quarter.
            if days is None or not 350 <= days <= 380:
                continue
            start_days = _iso_days(prior.get("start"), latest.get("start"))
            if start_days is not None and not 350 <= start_days <= 380:
                continue
            candidates.append((abs(days - 365), prior))

        if not candidates:
            return None
        _, prior = min(candidates, key=lambda x: (x[0], str(x[1].get("end") or "")))
        previous = _safe_float(prior.get("val"))
        if previous is None or previous <= 0:
            return None
        return current / previous - 1

    def fundamentals(self, symbol: str) -> dict:
        ref = self.resolve(symbol)
        if not ref:
            return {"_status": "not covered by SEC ticker map", "_source": "SEC EDGAR/XBRL"}
        cik10 = ref["cik10"]
        submissions = self._json(f"https://data.sec.gov/submissions/CIK{cik10}.json")
        facts = self._json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json")

        # Issuers can switch revenue tags. Do not let a populated but obsolete
        # preferred tag hide a newer series; never splice different tags together.
        revenue_facts = [self._fact(facts, (tag,)) for tag in (
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "RevenueFromContractWithCustomerIncludingAssessedTax", "Revenues", "SalesRevenueNet",
        )]
        revenue_fact = max((f for f in revenue_facts if f), default=None, key=lambda f: max(
            (str(r.get("end") or "") for r in self._annual_values(f) + self._quarter_values(f)),
            default="",
        ))
        net_income_fact = self._fact(facts, ("NetIncomeLoss", "ProfitLoss"))
        gross_profit_fact = self._fact(facts, ("GrossProfit",))
        op_income_fact = self._fact(facts, ("OperatingIncomeLoss",))
        equity_fact = self._fact(facts, ("StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"))
        current_assets_fact = self._fact(facts, ("AssetsCurrent",))
        current_liab_fact = self._fact(facts, ("LiabilitiesCurrent",))
        ocf_fact = self._fact(facts, ("NetCashProvidedByUsedInOperatingActivities",))
        dei = (facts.get("facts") or {}).get("dei") or {}
        shares_outstanding_fact = dei.get("EntityCommonStockSharesOutstanding")

        revenue = self._annual_values(revenue_fact)
        net_income = self._annual_values(net_income_fact)
        gross_profit = self._annual_values(gross_profit_fact)
        op_income = self._annual_values(op_income_fact)
        ocf = self._annual_values(ocf_fact)
        quarterly_revenue = self._quarter_values(revenue_fact)
        latest_quarter = quarterly_revenue[-1] if quarterly_revenue else {}
        recent = (submissions.get("filings") or {}).get("recent") or {}
        report_dates = recent.get("reportDate") or []
        latest_report = max((report_dates[i] for i, form in enumerate(recent.get("form") or [])
                             if form in {"10-Q", "10-Q/A", "10-K", "10-K/A", "20-F", "20-F/A"}
                             and i < len(report_dates) and _iso_days(report_dates[i], report_dates[i]) == 0), default="")
        latest_period = max(str(latest_quarter.get("end") or ""), str(revenue[-1].get("end") or "") if revenue else "", latest_report)
        quarter_current = latest_quarter.get("end") == latest_period
        quarterly_growth = self._quarter_yoy_growth(quarterly_revenue) if quarter_current else None

        annual = revenue[-1] if revenue else {}
        annual_end = annual.get("end")
        annual_reports = [report_dates[i] for i, form in enumerate(recent.get("form") or [])
                          if form in {"10-K", "10-K/A", "20-F", "20-F/A"}
                          and i < len(report_dates) and _iso_days(report_dates[i], report_dates[i]) == 0]
        latest_annual_report = max(annual_reports, default="")
        annual_current = bool(annual_end and (not latest_annual_report or annual_end == latest_annual_report))
        def matched(series):
            return [r for r in series if r.get("start") == annual.get("start") and r.get("end") == annual_end]
        # Missing current facts must not be substituted with older-year numerators.
        income_row = matched(net_income)
        latest_rev = _safe_float(annual.get("val")) if annual_current else None
        if latest_rev is not None and latest_rev <= 0:
            latest_rev = None
        latest_ni = _safe_float(income_row[-1].get("val")) if annual_current and income_row else None
        def amount(series):
            rows = matched(series)
            return _safe_float(rows[-1].get("val")) if annual_current and rows else None
        latest_gp, latest_oi, latest_ocf = amount(gross_profit), amount(op_income), amount(ocf)
        # ROE uses income and average equity for the same fiscal year.
        equity_end = self._instant_at(equity_fact, annual_end) if annual_end else None
        equity_start_date = (datetime.fromisoformat(annual["start"])-timedelta(days=1)).date().isoformat() if annual.get("start") else None
        equity_start = self._instant_at(equity_fact, equity_start_date) if equity_start_date else None
        average_equity = (equity_start+equity_end)/2 if equity_start is not None and equity_end is not None and equity_start > 0 and equity_end > 0 else None
        balance_equity = self._instant_at(equity_fact, latest_period)
        current_assets = self._instant_at(current_assets_fact, latest_period)
        current_liab = self._instant_at(current_liab_fact, latest_period)
        shares_outstanding = self._latest_instant(shares_outstanding_fact, ("shares",))
        debt_total, debt_status = self._debt_at(facts, latest_period)
        income_series = [r for r in net_income if str(r.get("end") or "") < str(annual_end or "")] + income_row
        earnings_change = self._earnings_change(income_series) if latest_ni is not None else "no matched annual net income"

        sic = submissions.get("sic")
        sic_desc = submissions.get("sicDescription") or ""
        sector = sic_to_sector(sic, sic_desc)

        out = {
            "revenueGrowth": self._growth(revenue) if annual_current else None,
            "earningsGrowth": self._growth(income_series) if latest_ni is not None else None,
            "quarterlyRevenueGrowth": quarterly_growth,
            "totalRevenue": latest_rev,
            "grossMargins": (latest_gp / latest_rev) if latest_gp is not None and latest_rev else None,
            "operatingMargins": (latest_oi / latest_rev) if latest_oi is not None and latest_rev else None,
            "returnOnEquity": (latest_ni / average_equity) if latest_ni is not None and average_equity is not None else None,
            "debtToEquity": (debt_total / balance_equity * 100) if debt_total is not None and balance_equity is not None and balance_equity > 0 else None,
            "currentRatio": (current_assets / current_liab) if current_assets is not None and current_liab is not None and current_liab > 0 else None,
            "operatingCashConversion": (latest_ocf / latest_ni) if latest_ocf is not None and latest_ni is not None and latest_ni > 0 else None,
            "sharesOutstanding": shares_outstanding,
            "sector": sector,
            "industry": sic_desc or None,
            "sic": int(sic) if str(sic or "").isdigit() else sic,
            "companyName": submissions.get("name") or ref.get("title"),
            "cik": ref["cik"],
            "_status": "available",
            "_source": "SEC EDGAR/XBRL",
            "_fundamental_period": annual_end if annual_current else None,
            "_fundamental_integrity": "matched-fiscal-periods-v1",
            "_annual_status": "available" if annual_current else "latest annual revenue unavailable",
            "_earnings_change": earnings_change,
            "_earnings_basis": "annual GAAP total net income; includes discontinued operations where reported",
            "_roe_method": "annual GAAP net income / average opening and closing fiscal-year equity",
            "_roe_status": "available" if average_equity is not None and latest_ni is not None else "missing matched income/equity or nonpositive equity",
            "_balance_period": latest_period or None,
            "_debt_status": debt_status if balance_equity is not None and balance_equity > 0 else "missing or nonpositive balance-sheet equity",
            "_debt_value": debt_total,
            "_roe_equity_start": equity_start,
            "_roe_equity_end": equity_end,
            "_quarterly_period": latest_period or None,
            "_quarterly_source": "SEC EDGAR/XBRL",
            "_quarterly_method": latest_quarter.get("_derived", "reported quarter") if quarter_current else None,
            "_quarterly_status": "available" if quarterly_growth is not None else "no comparable latest quarter",
        }
        observed = sum(out.get(k) is not None for k in ("revenueGrowth", "earningsGrowth", "grossMargins", "operatingMargins", "returnOnEquity", "debtToEquity"))
        out["_coverage"] = observed
        return out


class FinnhubAnalystProvider:
    """Optional analyst-recommendation enrichment. Requires FINNHUB_API_KEY."""

    def __init__(self, token: str | None = None, timeout: float = 8.0):
        self.token = token or settings.finnhub_api_key
        self.cache = EndpointCache()
        self.client = httpx.Client(timeout=timeout, headers={"Accept": "application/json"})

    def recommendations(self, symbol: str) -> dict:
        if not self.token or symbol.endswith(".ST"):
            return {"_analyst_status": "optional Finnhub key not configured", "_analyst_source": "Finnhub (optional)"}
        rows, status = self.cache.fetch(self.client, "recommendation", symbol, self.token, 21600)
        if not isinstance(rows, list):
            return {"_analyst_status": status, "_analyst_source": "Finnhub recommendation trends"}
        if not rows:
            return {"_analyst_status": "no recommendation trend returned", "_analyst_source": "Finnhub"}
        row = rows[0]
        return {
            "strongBuy": row.get("strongBuy"), "buy": row.get("buy"), "hold": row.get("hold"),
            "sell": row.get("sell"), "strongSell": row.get("strongSell"),
            "_analyst_period": row.get("period"), "_analyst_status": "available",
            "_analyst_source": "Finnhub recommendation trends",
        }

    def prefetch_recommendations(self, symbols: list[str]) -> None:
        # Sequential calls use the same account budget and bounded cache. A
        # provider failure remains isolated from price/fundamental analysis.
        if not self.token:
            return
        for symbol in symbols[:48]:
            try:
                self.recommendations(symbol)
            except Exception:
                continue

    def market_evidence(self, symbol: str) -> dict:
        out = {}
        if not self.token or symbol.endswith(".ST"):
            return out
        observed = datetime.now(timezone.utc).isoformat()
        metrics, status = self.cache.fetch(self.client, "metric", symbol, self.token, 21600, {"metric": "all"})
        metric = (metrics or {}).get("metric") or {} if isinstance(metrics, dict) else {}
        pe = positive(metric.get("peTTM")) if not (metrics or {}).get("symbol") or metrics.get("symbol") == symbol else None
        out.update(trailingPE=pe, _valuation_source="Finnhub basic financials (TTM P/E)",
                   _valuation_asof=(metrics or {}).get("_retrieved_at") or observed, _valuation_status="available; provider observation date not supplied" if pe else status if status != "available" else "unavailable (positive TTM P/E not returned)")
        profile, status = self.cache.fetch(self.client, "profile2", symbol, self.token, 21600)
        profile = profile if isinstance(profile, dict) else {}
        if profile.get("ticker") == symbol and profile.get("currency") == "USD":
            cap, shares = positive(profile.get("marketCapitalization")), positive(profile.get("shareOutstanding"))
            if cap:
                out.update(marketCap=cap * 1_000_000, _market_cap_source="Finnhub company profile (millions converted to USD)",
                           _market_cap_asof=profile.get("_retrieved_at") or observed, _market_cap_status="available; retrieved at shown time")
            if shares:
                out.update(sharesOutstanding=shares * 1_000_000)
        targets, status = self.cache.fetch(self.client, "price-target", symbol, self.token, 3600)
        targets = targets if isinstance(targets, dict) else {}
        out.update(_target_source="Finnhub price-target consensus", _target_status=status)
        try:
            updated = datetime.fromisoformat(str(targets.get("lastUpdated") or "").replace("Z", "+00:00"))
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - updated).total_seconds()
            mean, low, high = (positive(targets.get(key)) for key in ("targetMean", "targetLow", "targetHigh"))
            if targets.get("symbol") != symbol or not 0 <= age <= 90 * 86400 or not mean or not low or not high or not low <= mean <= high:
                raise ValueError()
            out.update(targetMeanPrice=mean, targetLowPrice=low, targetHighPrice=high,
                       _target_asof=updated.isoformat(), _target_status="available")
        except (ValueError, TypeError):
            if status == "available":
                out["_target_status"] = "unavailable (missing, stale or invalid target evidence)"
        return out


class YahooMarketProvider:
    _fx_cache: dict[str, tuple[float, float]] = {}

    """No-key prototype price/news provider with SEC fundamentals fallback.

    Yahoo chart/search remain convenient for V1 pricing/news. Fundamental evidence is
    independently recovered from SEC EDGAR for U.S. issuers when Yahoo quoteSummary
    is unavailable, so one provider failure does not collapse the whole evidence pack.
    """

    def __init__(self, timeout: float = 10.0, sec_provider=None, analyst_provider=None, strategic_provider=None):
        self.client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": UA, "Accept": "application/json"},
            follow_redirects=True,
        )
        self._auth_lock = Lock()
        self._crumb = None
        self._auth_retry_at = 0.0
        self._volume_cache = OrderedDict()
        self._volume_lock = Lock()
        self.sec = sec_provider or SECFundamentalsProvider(timeout=max(timeout, 12.0))
        self.analyst = analyst_provider or FinnhubAnalystProvider(timeout=timeout)
        self.strategic = strategic_provider or StrategicCapitalProvider(timeout=max(timeout, 12.0))

    def _json(self, url: str, params: dict[str, Any] | None = None) -> dict:
        r = self.client.get(url, params=params)
        r.raise_for_status()
        return r.json()

    def chart(self, symbol: str, range_: str = "1y", interval: str = "1d") -> dict:
        data = self._json(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
            {"range": range_, "interval": interval, "includePrePost": "true", "events": "div,splits"},
        )
        result = ((data.get("chart") or {}).get("result") or [])
        if not result:
            raise MarketDataError(f"No market data for {symbol}")
        return result[0]

    def _v(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            if "raw" in obj:
                return obj.get("raw")
            if "fmt" in obj and len(obj) <= 2:
                return obj.get("fmt")
        return obj

    def _yahoo_crumb(self):
        with self._auth_lock:
            if self._crumb:
                return self._crumb
            if time.monotonic() < self._auth_retry_at:
                return None
            self._auth_retry_at = time.monotonic() + 900
            try:
                # The cookie endpoint can return 404 while still setting the cookie.
                self.client.get("https://fc.yahoo.com")
                response = self.client.get("https://query1.finance.yahoo.com/v1/test/getcrumb")
                response.raise_for_status()
                crumb = response.text.strip()
                if not crumb or len(crumb) > 128 or any(x in crumb for x in ("<", "{", "\n")):
                    return None
                self._crumb = crumb
                return crumb
            except Exception:
                return None

    def relative_volume_evidence(self, symbol, quote_ts):
        try:
            key = (symbol, int(float(quote_ts or 0)) // 300)
        except (ValueError, TypeError, OverflowError):
            return {"relative_volume": None, "status": "unavailable (invalid quote timestamp)", "basis": "same-time regular-session volume"}
        with self._volume_lock:
            cached = self._volume_cache.get(key)
            if cached and cached[0] > time.monotonic():
                self._volume_cache.move_to_end(key)
                return dict(cached[1])
        try:
            # Bound decoded response memory; never retain intraday histories in analyses.
            with self.client.stream("GET", f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
                                    params={"range": "1mo", "interval": "5m", "includePrePost": "false"}) as response:
                response.raise_for_status()
                body = bytearray()
                for chunk in response.iter_bytes():
                    if len(body) + len(chunk) > 2 * 1024 * 1024:
                        raise MarketDataError("intraday response exceeds 2 MiB")
                    body.extend(chunk)
            payload = json.loads(body)
            chart = ((payload.get("chart") or {}).get("result") or [{}])[0]
            evidence = matched_relative_volume(chart, quote_ts)
        except Exception as exc:
            evidence = {"relative_volume": None, "status": f"unavailable ({type(exc).__name__})",
                        "source": "Yahoo Finance 5-minute chart", "basis": "same-time completed regular-session volume"}
        with self._volume_lock:
            self._volume_cache[key] = (time.monotonic() + 300, evidence)
            self._volume_cache.move_to_end(key)
            while len(self._volume_cache) > 128:
                self._volume_cache.popitem(last=False)
        return dict(evidence)

    def yahoo_fundamentals(self, symbol: str) -> dict:
        modules = "summaryDetail,defaultKeyStatistics,financialData,price,assetProfile,recommendationTrend,earningsTrend"
        try:
            url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{symbol}"
            params = {"modules": modules}
            if self._crumb:
                params["crumb"] = self._crumb
            try:
                data = self._json(url, params)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 401:
                    raise
                self._crumb = None
                crumb = self._yahoo_crumb()
                if not crumb:
                    raise
                data = self._json(url, {"modules": modules, "crumb": crumb})
            results = (data.get("quoteSummary") or {}).get("result") or []
            if not results or not results[0]:
                raise MarketDataError("empty quoteSummary")
            result = results[0]
            out = self._flatten_summary(result)
            out["_status"] = "available"
            out["_source"] = "Yahoo quoteSummary"
            out["_analyst_source"] = "Yahoo quoteSummary"
            out["_analyst_status"] = "available" if any(out.get(k) not in (None, "") for k in ("targetMeanPrice", "recommendationMean", "strongBuy", "buy", "hold", "sell", "strongSell")) else "not returned by Yahoo quoteSummary"
            return out
        except Exception as exc:
            return {
                "_status": f"unavailable (HTTP {exc.response.status_code})" if isinstance(exc, httpx.HTTPStatusError) else f"unavailable ({type(exc).__name__})",
                "_source": "Yahoo quoteSummary",
                "_analyst_status": "unavailable from Yahoo quoteSummary",
                "_analyst_source": "Yahoo quoteSummary",
            }

    def fundamentals(self, symbol: str) -> dict:
        yahoo = self.yahoo_fundamentals(symbol)
        sec: dict = {}
        # Use SEC whenever Yahoo lacks a meaningful fundamental set. This is also a
        # provenance-first fallback: each field keeps the source that supplied it.
        yahoo_core = sum(yahoo.get(k) is not None for k in ("revenueGrowth", "earningsGrowth", "grossMargins", "operatingMargins", "returnOnEquity", "debtToEquity"))
        # Market cap is a hard lane gate. If Yahoo omits it, pull SEC shares
        # outstanding even when the rest of Yahoo fundamentals are usable.
        if yahoo_core < 3 or yahoo.get("marketCap") in (None, "") or yahoo.get("quarterlyRevenueGrowth") is None:
            try:
                sec = self.sec.fundamentals(symbol)
            except Exception as exc:
                sec = {"_status": f"unavailable ({type(exc).__name__})", "_source": "SEC EDGAR/XBRL"}

        merged = dict(yahoo)
        for key, value in sec.items():
            if key.startswith("_"):
                continue
            if merged.get(key) in (None, "") and value not in (None, ""):
                merged[key] = value

        if sec.get("_fundamental_integrity"):
            for key in ("revenueGrowth", "earningsGrowth", "grossMargins", "operatingMargins",
                        "returnOnEquity", "debtToEquity", "totalRevenue", "currentRatio", "operatingCashConversion"):
                merged[key] = sec.get(key)
            for key, value in sec.items():
                if key.startswith("_") and key not in {"_status", "_source"}:
                    merged[key] = value

        # Prefer SEC sector/industry if Yahoo did not return them.
        if not merged.get("sector") and sec.get("sector"):
            merged["sector"] = sec["sector"]
        if not merged.get("industry") and sec.get("industry"):
            merged["industry"] = sec["industry"]

        core_after = sum(merged.get(k) is not None for k in ("revenueGrowth", "earningsGrowth", "grossMargins", "operatingMargins", "returnOnEquity", "debtToEquity"))
        if core_after:
            merged["_status"] = "available"
        merged["_fundamental_source"] = (
            "Yahoo quoteSummary + SEC EDGAR/XBRL" if yahoo_core and sec.get("_status") == "available"
            else "SEC EDGAR/XBRL" if sec.get("_status") == "available" and yahoo_core < 3
            else "Yahoo quoteSummary" if yahoo_core
            else sec.get("_source") or yahoo.get("_source") or "unavailable"
        )
        if sec.get("_fundamental_integrity"):
            merged["_fundamental_source"] = "SEC EDGAR/XBRL"
        merged["_fundamental_period"] = sec.get("_fundamental_period") if sec.get("_fundamental_integrity") else (sec.get("_fundamental_period") or merged.get("_fundamental_period"))
        if yahoo.get("quarterlyRevenueGrowth") is None:
            for key in ("_quarterly_period", "_quarterly_source", "_quarterly_method", "_quarterly_status"):
                merged[key] = sec.get(key)
        merged["_sec_status"] = sec.get("_status") if sec else "not needed / not attempted"
        merged["_yahoo_status"] = yahoo.get("_status")

        # Enrich recommendation counts independently. Never let analyst failure
        # change fundamental availability.
        try:
            analyst = self.analyst.recommendations(symbol)
        except Exception as exc:
            analyst = {"_analyst_status": f"unavailable ({type(exc).__name__})", "_analyst_source": "Finnhub"}
        for key in ("strongBuy", "buy", "hold", "sell", "strongSell"):
            if merged.get(key) in (None, "") and analyst.get(key) not in (None, ""):
                merged[key] = analyst[key]
        if analyst.get("_analyst_status") == "available":
            merged["_analyst_status"] = "available"
            merged["_analyst_source"] = analyst.get("_analyst_source")
            merged["_analyst_period"] = analyst.get("_analyst_period")
        elif merged.get("_analyst_status") != "available":
            merged["_analyst_status"] = analyst.get("_analyst_status") or merged.get("_analyst_status") or "unavailable"
            merged["_analyst_source"] = analyst.get("_analyst_source") or merged.get("_analyst_source") or "unavailable"
        if hasattr(self.analyst, "market_evidence") and any(not positive(merged.get(key)) for key in ("trailingPE", "marketCap", "targetMeanPrice")):
            try:
                evidence = self.analyst.market_evidence(symbol)
            except Exception as exc:
                evidence = {"_market_evidence_status": f"unavailable ({type(exc).__name__})"}
            for fields, prefix in ((('trailingPE',), 'valuation'), (('marketCap', 'sharesOutstanding'), 'market_cap'), (('targetMeanPrice', 'targetLowPrice', 'targetHighPrice'), 'target')):
                present = positive(merged.get(fields[0])) or (prefix == 'valuation' and positive(merged.get('forwardPE')))
                if present:
                    continue
                for key, value in evidence.items():
                    if value is not None and (key in fields or key.startswith(f"_{prefix}_")):
                        merged[key] = value
        return merged

    def _flatten_summary(self, result: dict) -> dict:
        fd = result.get("financialData") or {}
        sd = result.get("summaryDetail") or {}
        ks = result.get("defaultKeyStatistics") or {}
        pr = result.get("price") or {}
        ap = result.get("assetProfile") or {}
        trends = result.get("recommendationTrend") or {}
        earnings = result.get("earningsTrend") or {}
        current_trend = ((trends.get("trend") or [{}])[0])
        earnings_current = ((earnings.get("trend") or [{}])[0])
        return {
            "sector": ap.get("sector"), "industry": ap.get("industry"),
            "companyName": self._v(pr.get("longName")) or self._v(pr.get("shortName")),
            "marketCap": self._v(pr.get("marketCap")) or self._v(sd.get("marketCap")), "totalRevenue": self._v(fd.get("totalRevenue")),
            "sharesOutstanding": self._v(ks.get("sharesOutstanding")),
            "trailingPE": self._v(sd.get("trailingPE")) or self._v(ks.get("trailingPE")),
            "forwardPE": self._v(sd.get("forwardPE")) or self._v(ks.get("forwardPE")), "priceToSalesTrailing12Months": self._v(sd.get("priceToSalesTrailing12Months")),
            "revenueGrowth": self._v(fd.get("revenueGrowth")), "earningsGrowth": self._v(fd.get("earningsGrowth")),
            "grossMargins": self._v(fd.get("grossMargins")), "operatingMargins": self._v(fd.get("operatingMargins")),
            "returnOnEquity": self._v(fd.get("returnOnEquity")), "debtToEquity": self._v(fd.get("debtToEquity")),
            "targetMeanPrice": self._v(fd.get("targetMeanPrice")), "targetHighPrice": self._v(fd.get("targetHighPrice")),
            "targetLowPrice": self._v(fd.get("targetLowPrice")), "recommendationMean": self._v(fd.get("recommendationMean")),
            "recommendationKey": fd.get("recommendationKey"), "numberOfAnalystOpinions": self._v(fd.get("numberOfAnalystOpinions")),
            "strongBuy": current_trend.get("strongBuy"), "buy": current_trend.get("buy"), "hold": current_trend.get("hold"),
            "sell": current_trend.get("sell"), "strongSell": current_trend.get("strongSell"),
            "forecastEarningsGrowth": self._v(earnings_current.get("growth")),
            "_earnings_basis": "Yahoo reported earnings growth; provider period/basis",
        }

    def news(self, symbol: str, count: int = 15) -> list[dict]:
        try:
            data = self._json(
                "https://query1.finance.yahoo.com/v1/finance/search",
                {"q": symbol, "quotesCount": 1, "newsCount": count, "enableFuzzyQuery": "false"},
            )
            out = []
            for n in data.get("news") or []:
                out.append({
                    "title": n.get("title") or "", "publisher": n.get("publisher") or "",
                    "link": n.get("link") or n.get("clickThroughUrl", {}).get("url") or "",
                    "published": n.get("providerPublishTime"), "type": n.get("type") or "news",
                    "relatedTickers": n.get("relatedTickers") or [],
                })
            return out
        except Exception:
            return []

    def _rows_from_chart(self, chart: dict) -> tuple[list[dict], float, float, str, str | None]:
        meta = chart.get("meta") or {}
        timestamps = chart.get("timestamp") or []
        quote = (((chart.get("indicators") or {}).get("quote") or [{}])[0])
        adj = (((chart.get("indicators") or {}).get("adjclose") or [{}])[0]).get("adjclose") or []
        closes = quote.get("close") or []
        rows = []
        for i, ts in enumerate(timestamps):
            raw_close = closes[i] if i < len(closes) else None
            close = adj[i] if i < len(adj) and adj[i] is not None else raw_close
            if close is None:
                continue
            def at(name: str, default=None):
                arr = quote.get(name) or []
                return arr[i] if i < len(arr) else default
            rows.append({
                "ts": ts, "date": datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat(),
                "open": at("open"), "high": at("high"), "low": at("low"),
                "close": close, "raw_close": raw_close, "volume": at("volume", 0) or 0,
            })
        current = meta.get("regularMarketPrice") or meta.get("currentMarketPrice") or (rows[-1]["raw_close"] if rows else 0)

        # Do not use Yahoo's chartPreviousClose for Day %. Its meaning depends on
        # the requested chart range (for a 1y chart it can be roughly a year-old
        # reference), which produced absurd -20%/-30% daily moves on the dashboard.
        # Derive the immediately prior trading-session close from the daily bars.
        previous = current
        if rows:
            market_ts = meta.get("regularMarketTime")
            market_date = None
            if market_ts:
                try:
                    market_date = datetime.fromtimestamp(float(market_ts), tz=timezone.utc).date().isoformat()
                except Exception:
                    market_date = None
            if len(rows) > 1 and market_date and rows[-1].get("date") == market_date:
                prior_row = rows[-2]
            else:
                # If today's bar is not present yet (e.g. pre-market), the last
                # completed daily bar itself is the previous regular-session close.
                prior_row = rows[-1]
            previous = prior_row.get("raw_close")
            if previous in (None, 0):
                previous = prior_row.get("close") or current
        return rows, float(current or 0), float(previous or 0), meta.get("currency") or "USD", meta.get("exchangeName") or meta.get("fullExchangeName")

    def bundle(self, symbol: str) -> dict:
        symbol = symbol.upper().strip()
        daily = self.chart(symbol, "1y", "1d")
        rows, current, previous, currency, exchange = self._rows_from_chart(daily)
        split_events = list(((daily.get("events") or {}).get("splits") or {}).values())
        recent_reverse_splits = []
        cutoff_ts = time.time() - 366 * 86400
        for event in split_events:
            try:
                event_ts = float(event.get("date") or 0)
                numerator = float(event.get("numerator") or 0)
                denominator = float(event.get("denominator") or 0)
                if event_ts >= cutoff_ts and numerator > 0 and denominator > 0 and numerator < denominator:
                    recent_reverse_splits.append({
                        "date": event_ts,
                        "ratio": event.get("splitRatio") or f"{numerator:g}:{denominator:g}",
                    })
            except Exception:
                continue
        fundamentals = self.fundamentals(symbol)
        if fundamentals.get("marketCap") in (None, "", 0):
            shares_outstanding = _safe_float(fundamentals.get("sharesOutstanding"))
            if shares_outstanding and current:
                fundamentals["marketCap"] = shares_outstanding * current
                fundamentals["_market_cap_source"] = "SEC shares outstanding × Yahoo current price"
        news = self.news(symbol)
        strategic_capital = self.strategic.assess(
            symbol,
            company_name=fundamentals.get("companyName") or symbol,
            news=news,
            annual_revenue=_safe_float(fundamentals.get("totalRevenue")),
            fetch_official=False,
        ) if settings.strategic_capital_enabled else {"mode": "DISABLED", "events": [], "event_count": 0}
        sector_benchmark = None
        sector = fundamentals.get("sector")
        etf = SECTOR_ETF.get(sector)
        if etf:
            try:
                b = self.chart(etf, "6mo", "1d")
                b_rows, b_price, b_prev, b_currency, b_exchange = self._rows_from_chart(b)
                sector_benchmark = {
                    "symbol": etf, "price": b_price, "previous_close": b_prev,
                    "history": b_rows, "currency": b_currency, "exchange": b_exchange,
                }
            except Exception:
                sector_benchmark = None

        quote_asof = None
        try:
            quote_ts = (daily.get("meta") or {}).get("regularMarketTime")
            if quote_ts:
                quote_asof = datetime.fromtimestamp(float(quote_ts), tz=timezone.utc).isoformat()
        except (TypeError, ValueError, OverflowError):
            pass
        volume_evidence = self.relative_volume_evidence(symbol, (daily.get("meta") or {}).get("regularMarketTime")) if not symbol.endswith(".ST") else {"relative_volume": None, "status": "unavailable (US session normalization only)", "basis": "US regular session"}
        data_sources = {
            "price": {"source": "Yahoo Finance chart", "status": "available" if rows and current else "unavailable", "asof": datetime.now(timezone.utc).isoformat(), "quote_asof": quote_asof},
            "fundamentals": {
                "source": fundamentals.get("_fundamental_source") or fundamentals.get("_source") or "unavailable",
                "status": fundamentals.get("_status") or "unavailable",
                "asof": fundamentals.get("_fundamental_period"),
            },
            "relative_volume": volume_evidence,
            "news": {"source": "Yahoo Finance search", "status": "available" if news else "no recent items", "items": len(news)},
            "analyst": {
                "source": fundamentals.get("_analyst_source") or "unavailable",
                "status": fundamentals.get("_analyst_status") or "unavailable",
                "asof": fundamentals.get("_analyst_period"),
            },
            "sector": {
                "source": "Yahoo sector metadata" if fundamentals.get("_yahoo_status") == "available" and fundamentals.get("sector") else "SEC SIC mapping" if fundamentals.get("sic") else "unavailable",
                "status": "available" if sector_benchmark else (f"sector identified as {sector}, benchmark unavailable" if sector else "unavailable"),
                "benchmark": etf,
            },
            "strategic_capital": {
                "source": "USAspending.gov + OGE annual/periodic disclosures + White House investment tracker + classified news",
                "status": "shadow evidence",
                "asof": strategic_capital.get("official_checked_at") or datetime.now(timezone.utc).isoformat(),
            },
        }
        for key, prefix, field in (("valuation", "valuation", "trailingPE"), ("price_targets", "target", "targetMeanPrice"), ("market_cap", "market_cap", "marketCap")):
            available = positive(fundamentals.get(field)) or (key == "valuation" and positive(fundamentals.get("forwardPE")))
            data_sources[key] = {"source": fundamentals.get(f"_{prefix}_source") or ("Yahoo quoteSummary" if available else "unavailable"),
                                 "status": fundamentals.get(f"_{prefix}_status") or ("available" if available else "unavailable"),
                                 "asof": fundamentals.get(f"_{prefix}_asof")}
        return {
            "relative_volume_evidence": volume_evidence,
            "symbol": symbol, "price": current, "previous_close": previous,
            "currency": currency, "exchange": exchange, "history": rows,
            "fundamentals": fundamentals, "news": news,
            "recent_reverse_splits": recent_reverse_splits,
            "strategic_capital": strategic_capital,
            "sector_benchmark": sector_benchmark,
            "data_sources": data_sources,
            "provider": "Yahoo price/news + SEC EDGAR fundamentals + optional Finnhub analysts + strategic-capital shadow monitor",
            "asof": datetime.now(timezone.utc).isoformat(),
        }

    _universe_cache: list[dict] = []
    _universe_cache_at: float = 0.0

    @staticmethod
    def _normalise_company_name(value: str) -> str:
        value = re.sub(r"[^a-z0-9 ]+", " ", (value or "").lower())
        tokens = [
            t for t in value.split()
            if t not in {"inc", "incorporated", "corp", "corporation", "company", "co", "ltd", "limited", "plc", "common", "stock", "class", "ordinary", "shares"}
        ]
        return " ".join(tokens).strip()

    @staticmethod
    def _eligible_equity(symbol: str, name: str, *, test_issue: str = "N", etf: str = "N", financial_status: str = "N") -> bool:
        symbol = (symbol or "").strip().upper()
        name_l = (name or "").lower()
        if not symbol or test_issue == "Y" or etf == "Y":
            return False
        if financial_status and financial_status not in {"N", ""}:
            return False
        if any(x in symbol for x in ("$", "^", "/", "=")) or len(symbol) > 8:
            return False
        # Exclude non-common-equity structures from the trading universe. ADRs remain eligible.
        if any(x in name_l for x in (" warrant", " warrants", " right", " rights", " unit", " units", " preferred", " preference", " note due", " bond")):
            return False
        return True

    def us_equity_universe(self, force_refresh: bool = False) -> list[dict]:
        """Return a cached, exchange-wide U.S. equity universe.

        Nasdaq Trader publishes separate symbol-directory files for Nasdaq-listed and
        other U.S.-exchange-listed securities. We merge them, remove test issues,
        ETFs and obvious non-common-equity structures, and retain issuer names for
        company-name search.
        """
        now = time.time()
        cls = self.__class__
        if cls._universe_cache and not force_refresh and now - cls._universe_cache_at < 6 * 3600:
            return list(cls._universe_cache)

        rows: dict[str, dict] = {}
        sources = (
            ("https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt", "nasdaq"),
            ("https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt", "other"),
        )
        for url, kind in sources:
            try:
                r = self.client.get(url, headers={"Accept": "text/plain,*/*"})
                r.raise_for_status()
                lines = [line for line in r.text.splitlines() if line and not line.startswith("File Creation Time")]
                if not lines:
                    continue
                headers = [h.strip() for h in lines[0].split("|")]
                for line in lines[1:]:
                    parts = line.split("|")
                    if len(parts) < len(headers):
                        continue
                    rec = dict(zip(headers, parts))
                    if kind == "nasdaq":
                        symbol = (rec.get("Symbol") or "").strip().upper()
                        name = (rec.get("Security Name") or "").strip()
                        if not self._eligible_equity(
                            symbol, name,
                            test_issue=(rec.get("Test Issue") or "N").strip(),
                            etf=(rec.get("ETF") or "N").strip(),
                            financial_status=(rec.get("Financial Status") or "N").strip(),
                        ):
                            continue
                        exchange = "NASDAQ"
                    else:
                        symbol = (rec.get("ACT Symbol") or rec.get("CQS Symbol") or "").strip().upper()
                        name = (rec.get("Security Name") or "").strip()
                        if not self._eligible_equity(
                            symbol, name,
                            test_issue=(rec.get("Test Issue") or "N").strip(),
                            etf=(rec.get("ETF") or "N").strip(),
                            financial_status="N",
                        ):
                            continue
                        exchange = {
                            "N": "NYSE", "A": "NYSE American", "P": "NYSE Arca",
                            "Z": "Cboe", "V": "IEX",
                        }.get((rec.get("Exchange") or "").strip(), (rec.get("Exchange") or "OTHER").strip())
                    yahoo_symbol = symbol.replace(".", "-")
                    rows[yahoo_symbol] = {
                        "symbol": yahoo_symbol,
                        "name": name,
                        "exchange": exchange,
                        "name_key": self._normalise_company_name(name),
                    }
            except Exception:
                continue

        if not rows:
            try:
                for ticker, rec in self.sec._ticker_map().items():
                    symbol = ticker.replace(".", "-")
                    name = str(rec.get("title") or ticker)
                    if self._eligible_equity(symbol, name):
                        rows[symbol] = {"symbol": symbol, "name": name, "exchange": "US", "name_key": self._normalise_company_name(name)}
            except Exception:
                pass
        if rows:
            cls._universe_cache = sorted(rows.values(), key=lambda x: x["symbol"])
            cls._universe_cache_at = now
        return list(cls._universe_cache)

    def resolve_symbol(self, query: str) -> dict:
        """Resolve either a ticker or a company name to a tradable symbol."""
        raw = (query or "").strip()
        if not raw:
            raise MarketDataError("Enter a ticker or company name")
        universe = self.us_equity_universe()
        upper = raw.upper()
        by_symbol = {r["symbol"]: r for r in universe}
        if upper in by_symbol:
            return {**by_symbol[upper], "query": raw, "source": "Nasdaq Trader symbol directory"}

        key = self._normalise_company_name(raw)
        if key:
            exact = [r for r in universe if r.get("name_key") == key]
            if exact:
                return {**exact[0], "query": raw, "source": "Nasdaq Trader company-name match"}
            prefix = [r for r in universe if r.get("name_key", "").startswith(key) or key.startswith(r.get("name_key", ""))]
            if prefix:
                prefix.sort(key=lambda r: abs(len(r.get("name_key", "")) - len(key)))
                return {**prefix[0], "query": raw, "source": "Nasdaq Trader company-name match"}
            scored = []
            for r in universe:
                nk = r.get("name_key") or ""
                if not nk:
                    continue
                ratio = SequenceMatcher(None, key, nk).ratio()
                if key in nk or nk in key:
                    ratio += 0.2
                if ratio >= 0.68:
                    scored.append((ratio, r))
            if scored:
                scored.sort(key=lambda x: x[0], reverse=True)
                return {**scored[0][1], "query": raw, "source": "Nasdaq Trader fuzzy company-name match"}

        # If the user typed an all-caps ticker-like token, accept it directly after
        # exact/name resolution. The full market-data request remains the final validation.
        if raw == upper and " " not in raw and re.fullmatch(r"[A-Z0-9.\-]{1,15}", raw):
            return {"symbol": upper, "name": upper, "exchange": "", "query": raw, "source": "Direct ticker input"}

        # Last-resort search helps with brands/renamed issuers not represented cleanly in directory names.
        try:
            data = self._json(
                "https://query1.finance.yahoo.com/v1/finance/search",
                {"q": raw, "quotesCount": 10, "newsCount": 0, "enableFuzzyQuery": "true"},
            )
            quotes = [q for q in (data.get("quotes") or []) if q.get("quoteType") == "EQUITY"]
            if quotes:
                q = quotes[0]
                return {
                    "symbol": (q.get("symbol") or "").upper(),
                    "name": q.get("longname") or q.get("shortname") or q.get("symbol"),
                    "exchange": q.get("exchange") or q.get("exchDisp") or "",
                    "query": raw, "source": "Yahoo Finance search",
                }
        except Exception:
            pass
        raise MarketDataError(f"Could not resolve company or symbol: {raw}")

    def quick_scan(self, symbol: str) -> dict:
        """Low-cost first-pass market scan used across the whole U.S. universe."""
        chart = self.chart(symbol, "1mo", "1d")
        rows, current, previous, currency, exchange = self._rows_from_chart(chart)
        closes = [float(r["close"]) for r in rows if r.get("close") is not None]
        vols = [float(r.get("volume") or 0) for r in rows if r.get("close") is not None]
        if not current or len(closes) < 3:
            raise MarketDataError(f"Insufficient quick-scan history for {symbol}")
        change_5 = ((current / closes[-6]) - 1) * 100 if len(closes) >= 6 and closes[-6] else 0.0
        change_20 = ((current / closes[0]) - 1) * 100 if closes and closes[0] else 0.0
        baseline_vols = [v for v in vols[-21:-1] if v > 0]
        avg_vol = sum(baseline_vols) / len(baseline_vols) if baseline_vols else 0.0
        rel_vol = (vols[-1] / avg_vol) if vols and avg_vol else 0.0
        dollar_volume = current * (vols[-1] if vols else 0.0)
        avg_dollar_volume = current * avg_vol if avg_vol else 0.0
        high20 = max(closes[-20:]) if closes else current
        near_high = current / high20 if high20 else 0.0
        # Cheap discovery score only. Positive momentum can promote a candidate;
        # a large negative move is not treated as equally attractive for a long-only
        # opportunity funnel. Core-quality exploration is handled separately by the
        # scanner using liquidity, so quiet compounders still receive deep analysis.
        scan_score = (
            min(max(change_5, 0), 20) * 2.0
            + min(max(change_20, 0), 40) * 0.7
            + min(rel_vol, 5) * 8.0
            + (8.0 if near_high >= 0.98 else 0.0)
            + (5.0 if avg_dollar_volume >= 20_000_000 else 0.0)
        )
        qualifies = bool(
            current >= 5.0
            and avg_dollar_volume >= 20_000_000
            and (change_5 >= 3.0 or change_20 >= 7.0 or rel_vol >= 1.5 or near_high >= 0.985)
        )
        return {
            "symbol": symbol, "price": current, "previous_close": previous,
            "currency": currency, "exchange": exchange,
            "change_5_pct": change_5, "change_20_pct": change_20,
            "relative_volume": rel_vol, "dollar_volume": dollar_volume,
            "avg_dollar_volume_20": avg_dollar_volume,
            "near_20d_high": near_high, "scan_score": scan_score, "qualifies": qualifies,
        }


    def fx_rate(self, from_currency: str, to_currency: str) -> float | None:
        """Return a recent FX conversion rate using Yahoo chart data.

        The method is deliberately cached because portfolio sizing needs one
        account-level conversion, not a request per row.
        """
        src = str(from_currency or "").upper().strip()
        dst = str(to_currency or "").upper().strip()
        if not src or not dst or src == dst:
            return 1.0
        key = f"{src}{dst}"
        now = time.time()
        cached = self.__class__._fx_cache.get(key)
        if cached and now - cached[1] < 600:
            return cached[0]
        try:
            ch = self.chart(f"{src}{dst}=X", "5d", "1d")
            meta = ch.get("meta") or {}
            rate = _safe_float(meta.get("regularMarketPrice"))
            if rate is None:
                rows, price, *_ = self._rows_from_chart(ch)
                rate = price
            if rate and rate > 0:
                self.__class__._fx_cache[key] = (float(rate), now)
                return float(rate)
        except Exception:
            pass
        # Try the inverse pair before giving up.
        inv_key = f"{dst}{src}"
        try:
            ch = self.chart(f"{dst}{src}=X", "5d", "1d")
            meta = ch.get("meta") or {}
            inv = _safe_float(meta.get("regularMarketPrice"))
            if inv is None:
                rows, price, *_ = self._rows_from_chart(ch)
                inv = price
            if inv and inv > 0:
                rate = 1.0 / float(inv)
                self.__class__._fx_cache[key] = (rate, now)
                return rate
        except Exception:
            pass
        return None

    def discover(self, count: int = 50) -> list[dict]:
        """Broad cross-sector candidate discovery from multiple US market screeners."""
        symbols: dict[str, dict] = {}
        screeners = (
            "day_gainers", "most_actives", "aggressive_small_caps",
            "undervalued_growth_stocks", "growth_technology_stocks",
        )
        for screener in screeners:
            try:
                data = self._json(
                    "https://query2.finance.yahoo.com/v1/finance/screener/predefined/saved",
                    {
                        "formatted": "false", "lang": "en-US", "region": "US", "scrIds": screener,
                        "count": min(count, 250), "corsDomain": "finance.yahoo.com",
                    },
                )
                result = (((data.get("finance") or {}).get("result") or [{}])[0])
                for q in result.get("quotes") or []:
                    sym = (q.get("symbol") or "").upper()
                    if not sym or q.get("quoteType") not in (None, "EQUITY"):
                        continue
                    symbols[sym] = {
                        "symbol": sym, "price": q.get("regularMarketPrice") or q.get("intradayprice"),
                        "change_pct": q.get("regularMarketChangePercent") or q.get("percentchange"),
                        "volume": q.get("regularMarketVolume") or q.get("dayvolume"), "source": screener,
                    }
            except Exception:
                continue
        return list(symbols.values())
