from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import time
import httpx

from .config import settings

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
        return float(value)
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
        # Use first available unit only as a last resort.
        for rows in units.values():
            return list(rows or [])
        return []

    @classmethod
    def _annual_values(cls, fact: dict | None, units: tuple[str, ...] = ("USD",)) -> list[dict]:
        rows = cls._entries(fact, units)
        keep: dict[str, dict] = {}
        for r in rows:
            if r.get("form") not in {"10-K", "10-K/A", "20-F", "20-F/A"}:
                continue
            days = _iso_days(r.get("start"), r.get("end"))
            if days is not None and not 300 <= days <= 430:
                continue
            end = r.get("end")
            if not end or r.get("val") is None:
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
            if r.get("form") not in {"10-Q", "10-Q/A"}:
                continue
            days = _iso_days(r.get("start"), r.get("end"))
            # Duration facts in 10-Q can also be six/nine-month YTD. Keep quarter-like periods only.
            if days is not None and not 65 <= days <= 120:
                continue
            end = r.get("end")
            if not end or r.get("val") is None:
                continue
            prior = keep.get(end)
            if not prior or str(r.get("filed") or "") >= str(prior.get("filed") or ""):
                keep[end] = r
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
    def _growth(rows: list[dict]) -> float | None:
        if len(rows) < 2:
            return None
        current = _safe_float(rows[-1].get("val"))
        previous = _safe_float(rows[-2].get("val"))
        if current is None or previous in (None, 0):
            return None
        return current / previous - 1

    def fundamentals(self, symbol: str) -> dict:
        ref = self.resolve(symbol)
        if not ref:
            return {"_status": "not covered by SEC ticker map", "_source": "SEC EDGAR/XBRL"}
        cik10 = ref["cik10"]
        submissions = self._json(f"https://data.sec.gov/submissions/CIK{cik10}.json")
        facts = self._json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json")

        revenue_fact = self._fact(facts, (
            "RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet",
        ))
        net_income_fact = self._fact(facts, ("NetIncomeLoss", "ProfitLoss"))
        gross_profit_fact = self._fact(facts, ("GrossProfit",))
        op_income_fact = self._fact(facts, ("OperatingIncomeLoss",))
        equity_fact = self._fact(facts, ("StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"))
        current_assets_fact = self._fact(facts, ("AssetsCurrent",))
        current_liab_fact = self._fact(facts, ("LiabilitiesCurrent",))
        ocf_fact = self._fact(facts, ("NetCashProvidedByUsedInOperatingActivities",))

        revenue = self._annual_values(revenue_fact)
        net_income = self._annual_values(net_income_fact)
        gross_profit = self._annual_values(gross_profit_fact)
        op_income = self._annual_values(op_income_fact)
        ocf = self._annual_values(ocf_fact)
        quarterly_revenue = self._quarter_values(revenue_fact)

        latest_rev = _safe_float(revenue[-1].get("val")) if revenue else None
        latest_ni = _safe_float(net_income[-1].get("val")) if net_income else None
        latest_gp = _safe_float(gross_profit[-1].get("val")) if gross_profit else None
        latest_oi = _safe_float(op_income[-1].get("val")) if op_income else None
        latest_ocf = _safe_float(ocf[-1].get("val")) if ocf else None
        equity = self._latest_instant(equity_fact)
        current_assets = self._latest_instant(current_assets_fact)
        current_liab = self._latest_instant(current_liab_fact)

        debt_tags = (
            "LongTermDebtAndFinanceLeaseObligationsCurrent",
            "LongTermDebtCurrent",
            "ShortTermBorrowings",
        )
        debt_noncurrent_tags = (
            "LongTermDebtAndFinanceLeaseObligationsNoncurrent",
            "LongTermDebtNoncurrent",
            "LongTermDebt",
        )
        debt_current = self._latest_instant(self._fact(facts, debt_tags)) or 0.0
        debt_noncurrent = self._latest_instant(self._fact(facts, debt_noncurrent_tags)) or 0.0
        debt_total = debt_current + debt_noncurrent

        sic = submissions.get("sic")
        sic_desc = submissions.get("sicDescription") or ""
        sector = sic_to_sector(sic, sic_desc)

        out = {
            "revenueGrowth": self._growth(revenue),
            "earningsGrowth": self._growth(net_income),
            "quarterlyRevenueGrowth": self._growth(quarterly_revenue),
            "grossMargins": (latest_gp / latest_rev) if latest_gp is not None and latest_rev else None,
            "operatingMargins": (latest_oi / latest_rev) if latest_oi is not None and latest_rev else None,
            "returnOnEquity": (latest_ni / equity) if latest_ni is not None and equity not in (None, 0) else None,
            "debtToEquity": (debt_total / equity * 100) if debt_total and equity not in (None, 0) else None,
            "currentRatio": (current_assets / current_liab) if current_assets is not None and current_liab not in (None, 0) else None,
            "operatingCashConversion": (latest_ocf / latest_ni) if latest_ocf is not None and latest_ni not in (None, 0) else None,
            "sector": sector,
            "industry": sic_desc or None,
            "sic": int(sic) if str(sic or "").isdigit() else sic,
            "companyName": submissions.get("name") or ref.get("title"),
            "cik": ref["cik"],
            "_status": "available",
            "_source": "SEC EDGAR/XBRL",
            "_fundamental_period": revenue[-1].get("end") if revenue else None,
            "_quarterly_period": quarterly_revenue[-1].get("end") if quarterly_revenue else None,
        }
        observed = sum(out.get(k) is not None for k in ("revenueGrowth", "earningsGrowth", "grossMargins", "operatingMargins", "returnOnEquity", "debtToEquity"))
        out["_coverage"] = observed
        return out


class FinnhubAnalystProvider:
    """Optional analyst-recommendation enrichment. Requires FINNHUB_API_KEY."""

    def __init__(self, token: str | None = None, timeout: float = 8.0):
        self.token = token or settings.finnhub_api_key
        self.client = httpx.Client(timeout=timeout, headers={"Accept": "application/json"})

    def recommendations(self, symbol: str) -> dict:
        if not self.token or symbol.endswith(".ST"):
            return {"_analyst_status": "optional Finnhub key not configured", "_analyst_source": "Finnhub (optional)"}
        r = self.client.get(
            "https://finnhub.io/api/v1/stock/recommendation",
            params={"symbol": symbol, "token": self.token},
        )
        r.raise_for_status()
        rows = r.json() or []
        if not rows:
            return {"_analyst_status": "no recommendation trend returned", "_analyst_source": "Finnhub"}
        row = rows[0]
        return {
            "strongBuy": row.get("strongBuy"), "buy": row.get("buy"), "hold": row.get("hold"),
            "sell": row.get("sell"), "strongSell": row.get("strongSell"),
            "_analyst_period": row.get("period"), "_analyst_status": "available",
            "_analyst_source": "Finnhub recommendation trends",
        }


class YahooMarketProvider:
    """No-key prototype price/news provider with SEC fundamentals fallback.

    Yahoo chart/search remain convenient for V1 pricing/news. Fundamental evidence is
    independently recovered from SEC EDGAR for U.S. issuers when Yahoo quoteSummary
    is unavailable, so one provider failure does not collapse the whole evidence pack.
    """

    def __init__(self, timeout: float = 10.0, sec_provider=None, analyst_provider=None):
        self.client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": UA, "Accept": "application/json"},
            follow_redirects=True,
        )
        self.sec = sec_provider or SECFundamentalsProvider(timeout=max(timeout, 12.0))
        self.analyst = analyst_provider or FinnhubAnalystProvider(timeout=timeout)

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

    def yahoo_fundamentals(self, symbol: str) -> dict:
        modules = "summaryDetail,defaultKeyStatistics,financialData,price,assetProfile,recommendationTrend,earningsTrend"
        try:
            data = self._json(
                f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{symbol}",
                {"modules": modules},
            )
            result = (((data.get("quoteSummary") or {}).get("result") or [{}])[0])
            out = self._flatten_summary(result)
            out["_status"] = "available"
            out["_source"] = "Yahoo quoteSummary"
            out["_analyst_source"] = "Yahoo quoteSummary"
            out["_analyst_status"] = "available" if any(out.get(k) not in (None, "") for k in ("targetMeanPrice", "recommendationMean", "strongBuy", "buy", "hold", "sell", "strongSell")) else "not returned by Yahoo quoteSummary"
            return out
        except Exception as exc:
            return {
                "_status": f"unavailable ({type(exc).__name__})",
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
        if yahoo_core < 3:
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
        merged["_fundamental_period"] = sec.get("_fundamental_period") or merged.get("_fundamental_period")
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
        return merged

    def _flatten_summary(self, result: dict) -> dict:
        fd = result.get("financialData") or {}
        sd = result.get("summaryDetail") or {}
        pr = result.get("price") or {}
        ap = result.get("assetProfile") or {}
        trends = result.get("recommendationTrend") or {}
        earnings = result.get("earningsTrend") or {}
        current_trend = ((trends.get("trend") or [{}])[0])
        earnings_current = ((earnings.get("trend") or [{}])[0])
        return {
            "sector": ap.get("sector"), "industry": ap.get("industry"),
            "marketCap": self._v(pr.get("marketCap")), "trailingPE": self._v(sd.get("trailingPE")),
            "forwardPE": self._v(sd.get("forwardPE")), "priceToSalesTrailing12Months": self._v(sd.get("priceToSalesTrailing12Months")),
            "revenueGrowth": self._v(fd.get("revenueGrowth")), "earningsGrowth": self._v(fd.get("earningsGrowth")),
            "grossMargins": self._v(fd.get("grossMargins")), "operatingMargins": self._v(fd.get("operatingMargins")),
            "returnOnEquity": self._v(fd.get("returnOnEquity")), "debtToEquity": self._v(fd.get("debtToEquity")),
            "targetMeanPrice": self._v(fd.get("targetMeanPrice")), "targetHighPrice": self._v(fd.get("targetHighPrice")),
            "targetLowPrice": self._v(fd.get("targetLowPrice")), "recommendationMean": self._v(fd.get("recommendationMean")),
            "recommendationKey": fd.get("recommendationKey"), "numberOfAnalystOpinions": self._v(fd.get("numberOfAnalystOpinions")),
            "strongBuy": current_trend.get("strongBuy"), "buy": current_trend.get("buy"), "hold": current_trend.get("hold"),
            "sell": current_trend.get("sell"), "strongSell": current_trend.get("strongSell"),
            "growth": self._v(earnings_current.get("growth")),
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
            close = adj[i] if i < len(adj) and adj[i] is not None else (closes[i] if i < len(closes) else None)
            if close is None:
                continue
            def at(name: str, default=None):
                arr = quote.get(name) or []
                return arr[i] if i < len(arr) else default
            rows.append({
                "ts": ts, "date": datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat(),
                "open": at("open"), "high": at("high"), "low": at("low"),
                "close": close, "volume": at("volume", 0) or 0,
            })
        current = meta.get("regularMarketPrice") or meta.get("currentMarketPrice") or (rows[-1]["close"] if rows else 0)
        previous = meta.get("chartPreviousClose") or meta.get("previousClose") or (rows[-2]["close"] if len(rows) > 1 else current)
        return rows, float(current or 0), float(previous or 0), meta.get("currency") or "USD", meta.get("exchangeName") or meta.get("fullExchangeName")

    def bundle(self, symbol: str) -> dict:
        symbol = symbol.upper().strip()
        daily = self.chart(symbol, "1y", "1d")
        rows, current, previous, currency, exchange = self._rows_from_chart(daily)
        fundamentals = self.fundamentals(symbol)
        news = self.news(symbol)
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

        data_sources = {
            "price": {"source": "Yahoo Finance chart", "status": "available" if rows and current else "unavailable", "asof": datetime.now(timezone.utc).isoformat()},
            "fundamentals": {
                "source": fundamentals.get("_fundamental_source") or fundamentals.get("_source") or "unavailable",
                "status": fundamentals.get("_status") or "unavailable",
                "asof": fundamentals.get("_fundamental_period"),
            },
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
        }
        return {
            "symbol": symbol, "price": current, "previous_close": previous,
            "currency": currency, "exchange": exchange, "history": rows,
            "fundamentals": fundamentals, "news": news,
            "sector_benchmark": sector_benchmark,
            "data_sources": data_sources,
            "provider": "Yahoo price/news + SEC EDGAR fundamentals + optional Finnhub analysts",
            "asof": datetime.now(timezone.utc).isoformat(),
        }

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
