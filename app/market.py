from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import httpx

UA = "Mozilla/5.0 ISK-Trading-Radar/1.0"

SECTOR_ETF = {
    "Technology": "XLK", "Communication Services": "XLC", "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP", "Financial Services": "XLF", "Healthcare": "XLV",
    "Industrials": "XLI", "Energy": "XLE", "Basic Materials": "XLB",
    "Real Estate": "XLRE", "Utilities": "XLU",
}


class MarketDataError(RuntimeError):
    pass


class YahooMarketProvider:
    """No-key prototype provider. Useful for V1; not an exchange-grade guaranteed real-time feed."""

    def __init__(self, timeout: float = 10.0):
        self.client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": UA, "Accept": "application/json"},
            follow_redirects=True,
        )

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

    def fundamentals(self, symbol: str) -> dict:
        modules = "summaryDetail,defaultKeyStatistics,financialData,price,assetProfile,recommendationTrend,earningsTrend"
        try:
            data = self._json(
                f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{symbol}",
                {"modules": modules},
            )
            result = (((data.get("quoteSummary") or {}).get("result") or [{}])[0])
            out = self._flatten_summary(result)
            out["_status"] = "available"
            out["_analyst_status"] = "available" if any(out.get(k) not in (None, "") for k in ("targetMeanPrice", "recommendationMean", "strongBuy", "buy", "hold", "sell", "strongSell")) else "not returned by Yahoo quoteSummary"
            return out
        except Exception as exc:
            # Yahoo's quoteSummary endpoint is not guaranteed for server-side/no-key access.
            # Keep the failure explicit so the decision engine does not interpret missing data as deterioration.
            return {"_status": f"unavailable ({type(exc).__name__})", "_analyst_status": "unavailable from current no-key feed"}

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
            rows.append({
                "ts": ts, "date": datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat(),
                "open": (quote.get("open") or [None] * len(timestamps))[i],
                "high": (quote.get("high") or [None] * len(timestamps))[i],
                "low": (quote.get("low") or [None] * len(timestamps))[i],
                "close": close,
                "volume": (quote.get("volume") or [0] * len(timestamps))[i] or 0,
            })
        current = meta.get("regularMarketPrice") or meta.get("currentMarketPrice") or (rows[-1]["close"] if rows else 0)
        previous = meta.get("chartPreviousClose") or meta.get("previousClose") or (rows[-2]["close"] if len(rows) > 1 else current)
        return rows, float(current or 0), float(previous or 0), meta.get("currency") or "USD", meta.get("exchangeName") or meta.get("fullExchangeName")

    def bundle(self, symbol: str) -> dict:
        symbol = symbol.upper().strip()
        daily = self.chart(symbol, "1y", "1d")
        rows, current, previous, currency, exchange = self._rows_from_chart(daily)
        fundamentals = self.fundamentals(symbol)
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
        return {
            "symbol": symbol, "price": current, "previous_close": previous,
            "currency": currency, "exchange": exchange, "history": rows,
            "fundamentals": fundamentals, "news": self.news(symbol),
            "sector_benchmark": sector_benchmark,
            "provider": "Yahoo Finance no-key V1 feed", "asof": datetime.now(timezone.utc).isoformat(),
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
