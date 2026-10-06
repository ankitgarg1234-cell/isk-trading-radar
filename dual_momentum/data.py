from __future__ import annotations

import csv
import io
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from zoneinfo import ZoneInfo
from typing import Any, Sequence

import httpx

from app.market import SECFundamentalsProvider
from app.sec_evidence import accounting_facts
from .rules import (
    FundamentalCheck,
    FundamentalStatus,
    PriceBar,
    build_momentum_signal,
    evaluate_fundamentals,
    market_regime,
    rank_signals,
)

SP500_CSV_URL = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/master/data/constituents.csv"
SP500_HISTORY_URL = "https://en.wikipedia.org/wiki/Historical_components_of_the_S%26P_500"
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
UA = "Mozilla/5.0 Dual-Momentum-Radar/1.0"

REVENUE_TAGS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
)
GROSS_PROFIT_TAGS = ("GrossProfit",)
FINANCIAL_FORMS = {"10-Q", "10-Q/A", "10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}
ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}


def _safe_float(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except Exception:
        return None


def _days(start: str | None, end: str | None) -> int | None:
    if not start or not end:
        return None
    try:
        return (date.fromisoformat(end) - date.fromisoformat(start)).days
    except Exception:
        return None


def _normalise_yahoo_symbol(symbol: str) -> str:
    return symbol.strip().upper().replace(".", "-")


class _HTMLTables(HTMLParser):
    """Small dependency-free HTML table reader for the S&P change log."""

    def __init__(self):
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs):
        if tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str):
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None and self._table is not None:
            if self._row:
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            if self._table:
                self.tables.append(self._table)
            self._table = None


def _nyse_schedule(start_date: date, end_date: date):
    """Return the NYSE schedule when the optional live-service calendar is installed."""
    try:
        import pandas_market_calendars as mcal
    except Exception:
        return None
    calendar = mcal.get_calendar("NYSE")
    return calendar.schedule(start_date=start_date.isoformat(), end_date=end_date.isoformat())


def _session_dates(schedule) -> list[date]:
    if schedule is None:
        return []
    return [timestamp.date() for timestamp in schedule.index]


def _latest_completed_month_end_session(spy_bars: Sequence[PriceBar]) -> tuple[date, date | None]:
    """Resolve the latest month-end signal session and its next NYSE session."""
    now_ny = datetime.now(ZoneInfo("America/New_York"))
    today = now_ny.date()
    start = today - timedelta(days=100)
    end = today + timedelta(days=40)
    schedule = _nyse_schedule(start, end)
    sessions = _session_dates(schedule)

    if sessions:
        bar_dates = {date.fromisoformat(bar.date) for bar in spy_bars}
        month_ends: list[date] = []
        for idx, session in enumerate(sessions):
            next_session = sessions[idx + 1] if idx + 1 < len(sessions) else None
            if next_session is None or next_session.month != session.month:
                if session not in bar_dates:
                    continue
                if schedule is not None:
                    try:
                        close_ts = schedule.loc[str(session)]["market_close"]
                        close_dt = close_ts.to_pydatetime().astimezone(ZoneInfo("America/New_York"))
                        if close_dt > now_ny:
                            continue
                    except Exception:
                        if session >= today:
                            continue
                month_ends.append(session)
        if month_ends:
            decision = max(month_ends)
            future = [s for s in sessions if s > decision]
            return decision, future[0] if future else None

    # Conservative fallback when the optional calendar is unavailable: use the
    # final observed SPY session from the most recently completed calendar month.
    prior = [
        date.fromisoformat(bar.date)
        for bar in spy_bars
        if (date.fromisoformat(bar.date).year, date.fromisoformat(bar.date).month)
        < (today.year, today.month)
    ]
    if not prior:
        raise RuntimeError("No completed month-end SPY session is available")
    decision = prior[-1]
    later_bars = [date.fromisoformat(bar.date) for bar in spy_bars if date.fromisoformat(bar.date) > decision]
    return decision, later_bars[0] if later_bars else None


def _execution_window(next_session: date | None) -> str:
    if next_session is None:
        return "UNKNOWN"
    now_ny = datetime.now(ZoneInfo("America/New_York"))
    if next_session > now_ny.date():
        return "PENDING"
    if next_session < now_ny.date():
        return "MISSED"
    open_time = now_ny.replace(hour=9, minute=30, second=0, microsecond=0)
    return "PENDING" if now_ny < open_time else "MISSED"


class LiveDataSource:
    """Live/current data adapter.

    Price signals use Yahoo adjusted close as the dividend-reinvested signal series
    and raw tradable OHLC for execution/ATR. Current fundamentals come from SEC
    companyfacts and honor a conservative publication-date cutoff: a filing whose
    timestamp is unavailable is first usable on the following date.

    This adapter is for the live dashboard. Historical backtests must still use
    point-in-time index membership rather than today's constituent list.
    """

    def __init__(self, timeout: float = 15.0, price_workers: int = 8):
        self.timeout = timeout
        self.price_workers = max(1, min(16, int(price_workers)))
        self.client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": UA, "Accept": "application/json,text/csv,*/*"},
            follow_redirects=True,
        )
        self.sec = SECFundamentalsProvider(timeout=max(timeout, 12.0))

    def close(self) -> None:
        try:
            self.client.close()
        except Exception:
            pass

    def current_sp500(self) -> list[dict[str, str]]:
        response = self.client.get(SP500_CSV_URL)
        response.raise_for_status()
        rows = []
        for row in csv.DictReader(io.StringIO(response.text)):
            symbol = _normalise_yahoo_symbol(row.get("Symbol") or "")
            if not symbol:
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "name": (row.get("Security") or row.get("Name") or symbol).strip(),
                    "sector": (row.get("GICS Sector") or row.get("Sector") or "").strip(),
                    "issuer_id": str(row.get("CIK") or symbol).strip(),
                    "security_id": f"{str(row.get('CIK') or symbol).strip()}:{symbol}",
                }
            )
        if len(rows) < 400:
            raise RuntimeError("S&P 500 constituent source returned an incomplete universe")
        return rows

    def sp500_changes(self) -> list[dict]:
        response = self.client.get(SP500_HISTORY_URL)
        response.raise_for_status()
        parser = _HTMLTables()
        parser.feed(response.text)
        changes: list[dict] = []
        for table in parser.tables:
            for row in table:
                if len(row) < 5:
                    continue
                try:
                    effective = datetime.strptime(row[0].strip(), "%B %d, %Y").date()
                except Exception:
                    continue
                added = _normalise_yahoo_symbol(row[1]) if len(row) > 1 and row[1].strip() else ""
                added_name = row[2].strip() if len(row) > 2 else ""
                removed = _normalise_yahoo_symbol(row[3]) if len(row) > 3 and row[3].strip() else ""
                removed_name = row[4].strip() if len(row) > 4 else ""
                changes.append(
                    {
                        "effective_date": effective,
                        "added": added,
                        "added_name": added_name,
                        "removed": removed,
                        "removed_name": removed_name,
                    }
                )
        if not changes:
            raise RuntimeError("S&P 500 historical change source returned no effective-date rows")
        changes.sort(key=lambda row: row["effective_date"], reverse=True)
        return changes

    def sp500_at(self, decision_date: date) -> tuple[list[dict[str, str]], list[dict]]:
        """Reconstruct membership on decision_date from current members + effective changes."""
        current = self.current_sp500()
        members = {row["symbol"]: dict(row) for row in current}
        reversed_changes: list[dict] = []
        for change in self.sp500_changes():
            if change["effective_date"] <= decision_date:
                continue
            added = change.get("added") or ""
            removed = change.get("removed") or ""
            if added:
                members.pop(added, None)
            if removed:
                members[removed] = {
                    "symbol": removed,
                    "name": change.get("removed_name") or removed,
                    "sector": "",
                    "issuer_id": removed,
                    "security_id": removed,
                }
            reversed_changes.append(change)
        rows = sorted(members.values(), key=lambda row: row["symbol"])
        if len(rows) < 490:
            raise RuntimeError(f"Reconstructed S&P 500 universe is implausibly small ({len(rows)})")
        return rows, reversed_changes

    def _chart_json(self, symbol: str, range_: str = "2y") -> dict:
        response = self.client.get(
            YAHOO_CHART.format(symbol=symbol),
            params={
                "range": range_,
                "interval": "1d",
                "includePrePost": "false",
                "events": "div,splits",
            },
        )
        response.raise_for_status()
        result = ((response.json().get("chart") or {}).get("result") or [])
        if not result:
            raise RuntimeError(f"No daily chart for {symbol}")
        return result[0]

    @staticmethod
    def _bars_from_chart(chart: dict) -> list[PriceBar]:
        timestamps = chart.get("timestamp") or []
        indicators = chart.get("indicators") or {}
        quote = (indicators.get("quote") or [{}])[0]
        adjusted = ((indicators.get("adjclose") or [{}])[0]).get("adjclose") or []
        opens = quote.get("open") or []
        highs = quote.get("high") or []
        lows = quote.get("low") or []
        closes = quote.get("close") or []
        volumes = quote.get("volume") or []
        bars: list[PriceBar] = []
        for i, ts in enumerate(timestamps):
            raw_close = _safe_float(closes[i] if i < len(closes) else None)
            adj_close = _safe_float(adjusted[i] if i < len(adjusted) else None)
            op = _safe_float(opens[i] if i < len(opens) else None)
            hi = _safe_float(highs[i] if i < len(highs) else None)
            lo = _safe_float(lows[i] if i < len(lows) else None)
            if raw_close is None or adj_close is None or op is None or hi is None or lo is None:
                continue
            if min(raw_close, adj_close, op, hi, lo) <= 0:
                continue
            bars.append(
                PriceBar(
                    date=datetime.fromtimestamp(float(ts), tz=timezone.utc).date().isoformat(),
                    open=op,
                    high=hi,
                    low=lo,
                    close=raw_close,
                    total_return_close=adj_close,
                    volume=float(volumes[i] or 0) if i < len(volumes) else 0.0,
                )
            )
        return bars

    def price_bars(self, symbol: str, range_: str = "2y") -> list[PriceBar]:
        return self._bars_from_chart(self._chart_json(symbol, range_))

    def price_universe(self, members: list[dict[str, str]], *, lagged: bool = False, through_date: str | None = None) -> tuple[list, list[dict]]:
        signals = []
        errors: list[dict] = []

        def one(member: dict[str, str]):
            symbol = member["symbol"]
            bars = self.price_bars(symbol)
            if through_date:
                bars = [bar for bar in bars if bar.date <= through_date]
            signal = build_momentum_signal(symbol, bars, lagged=lagged, security_id=member.get("security_id") or symbol)
            return signal

        with ThreadPoolExecutor(max_workers=self.price_workers) as pool:
            futures = {pool.submit(one, member): member for member in members}
            for future in as_completed(futures):
                member = futures[future]
                try:
                    signal = future.result()
                    signals.append(signal)
                except Exception as exc:
                    errors.append(
                        {
                            "symbol": member["symbol"],
                            "kind": "price_history_or_atr",
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
        return rank_signals(signals), errors

    @staticmethod
    def _fact(facts: dict, tags: tuple[str, ...]) -> dict | None:
        us = (facts.get("facts") or {}).get("us-gaap") or {}
        for tag in tags:
            if tag in us:
                return us[tag]
        return None

    @staticmethod
    def _entries(fact: dict | None) -> list[dict]:
        if not fact:
            return []
        units = fact.get("units") or {}
        return list(units.get("USD") or [])

    @classmethod
    def _published_before(cls, row: dict, decision_date: date) -> bool:
        filed = row.get("filed")
        if not filed:
            return False
        try:
            # Companyfacts normally supplies a date, not a trustworthy timestamp.
            # Same-day filings are therefore deferred to the next date.
            return date.fromisoformat(str(filed)[:10]) < decision_date
        except Exception:
            return False

    @classmethod
    def _quarter_series(cls, fact: dict | None, decision_date: date) -> list[dict]:
        rows = [
            r
            for r in cls._entries(fact)
            if r.get("form") in FINANCIAL_FORMS
            and cls._published_before(r, decision_date)
            and _safe_float(r.get("val")) is not None
        ]
        keep: dict[str, dict] = {}

        # Standalone quarter-duration facts.
        for row in rows:
            duration = _days(row.get("start"), row.get("end"))
            end = str(row.get("end") or "")
            if not end or duration is None or not 65 <= duration <= 120:
                continue
            prior = keep.get(end)
            if prior is None or str(row.get("filed") or "") > str(prior.get("filed") or ""):
                keep[end] = row

        # Derive a missing fourth quarter from annual less nine-month YTD.
        annual_rows = [
            r for r in rows
            if r.get("form") in ANNUAL_FORMS and 300 <= (_days(r.get("start"), r.get("end")) or 0) <= 430
        ]
        for annual in annual_rows:
            end = str(annual.get("end") or "")
            if not end or end in keep:
                continue
            ytd = [
                r for r in rows
                if r.get("start") == annual.get("start")
                and 240 <= (_days(r.get("start"), r.get("end")) or 0) <= 310
                and 65 <= (_days(r.get("end"), end) or 0) <= 120
                and str(r.get("filed") or "") <= str(annual.get("filed") or "")
            ]
            if not ytd:
                continue
            nine = max(ytd, key=lambda r: (str(r.get("filed") or ""), str(r.get("end") or "")))
            annual_value = _safe_float(annual.get("val"))
            nine_value = _safe_float(nine.get("val"))
            if annual_value is None or nine_value is None:
                continue
            value = annual_value - nine_value
            if not math.isfinite(value):
                continue
            keep[end] = {
                **annual,
                "start": (date.fromisoformat(str(nine["end"])[:10])).isoformat(),
                "val": value,
                "_derived": "annual minus nine-month YTD",
            }

        return sorted(keep.values(), key=lambda r: str(r.get("end") or ""))

    @classmethod
    def _best_fact_with_history(cls, facts: dict, tags: tuple[str, ...], decision_date: date, minimum_quarters: int) -> tuple[dict | None, list[dict]]:
        choices: list[tuple[str, int, dict, list[dict]]] = []
        for tag in tags:
            fact = cls._fact(facts, (tag,))
            quarters = cls._quarter_series(fact, decision_date)
            if quarters:
                choices.append((str(quarters[-1].get("end") or ""), len(quarters), fact, quarters))
        if not choices:
            return None, []
        qualifying = [x for x in choices if x[1] >= minimum_quarters]
        chosen = max(qualifying or choices, key=lambda x: (x[0], x[1]))
        return chosen[2], chosen[3]

    def ttm_fundamentals(self, symbol: str, decision_date: date) -> dict:
        ref = self.sec.resolve(symbol)
        if not ref:
            return {
                "symbol": symbol,
                "check": FundamentalCheck(FundamentalStatus.REVIEW, None, None, False, "SEC issuer mapping unavailable"),
                "source": "SEC EDGAR/XBRL",
                "security_id": None,
                "issuer_id": None,
            }

        facts = self.sec._json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{ref['cik10']}.json")
        submissions = self.sec._json(f"https://data.sec.gov/submissions/CIK{ref['cik10']}.json")
        facts, _ = accounting_facts(facts, self.sec._annual_values)

        _, revenue_rows = self._best_fact_with_history(facts, REVENUE_TAGS, decision_date, 8)
        _, gross_rows = self._best_fact_with_history(facts, GROSS_PROFIT_TAGS, decision_date, 4)

        revenue_rows_8 = revenue_rows[-8:]
        revenue_values = [_safe_float(r.get("val")) for r in revenue_rows_8]
        revenue_values_clean = None if len(revenue_rows_8) < 8 or any(v is None for v in revenue_values) else [float(v) for v in revenue_values if v is not None]

        # Gross profit must match the exact latest four revenue quarter-ends.
        # A stale but otherwise valid gross-profit series is not silently mixed
        # with a newer revenue TTM window.
        gross_by_end = {str(r.get("end") or ""): r for r in gross_rows}
        latest_revenue_rows = revenue_rows_8[-4:]
        aligned_gross_rows = [gross_by_end.get(str(r.get("end") or "")) for r in latest_revenue_rows]
        gross_values = [
            _safe_float(r.get("val")) if r is not None else None
            for r in aligned_gross_rows
        ]
        gross_values_clean = None if len(latest_revenue_rows) < 4 or any(v is None for v in gross_values) else [float(v) for v in gross_values if v is not None]

        sic_raw = submissions.get("sic")
        try:
            sic = int(sic_raw)
        except Exception:
            sic = None
        gross_margin_exempt = bool(sic is not None and 6000 <= sic <= 6799)

        check = evaluate_fundamentals(
            revenue_values_clean,
            gross_values_clean,
            gross_margin_exempt=gross_margin_exempt,
        )
        used_rows = (revenue_rows_8 if revenue_rows_8 else []) + [r for r in aligned_gross_rows if r is not None]
        filed_dates = sorted({str(r.get("filed")) for r in used_rows if r.get("filed")})
        periods = sorted({str(r.get("end")) for r in used_rows if r.get("end")})

        return {
            "symbol": symbol,
            "check": check,
            "source": "SEC EDGAR/XBRL companyfacts",
            "sic": sic,
            "issuer_id": str(ref.get("cik") or symbol),
            "security_id": f"{str(ref.get('cik') or symbol)}:{symbol}",
            "sector": submissions.get("sicDescription") or None,
            "company": submissions.get("name") or ref.get("title") or symbol,
            "last_filed": filed_dates[-1] if filed_dates else None,
            "last_period": periods[-1] if periods else None,
        }

    def scan(
        self,
        *,
        holdings: set[str] | None = None,
        lagged: bool = False,
        decision_date: date | None = None,
        max_fundamental_checks: int = 160,
    ) -> dict:
        holdings = {_normalise_yahoo_symbol(s) for s in (holdings or set())}

        spy_bars_all = self.price_bars("SPY", "max")
        if decision_date is None:
            resolved_decision, next_session_date = _latest_completed_month_end_session(spy_bars_all)
            decision_date = resolved_decision
            decision_session = resolved_decision.isoformat()
        else:
            eligible_spy = [bar for bar in spy_bars_all if bar.date <= decision_date.isoformat()]
            if not eligible_spy:
                raise RuntimeError("No SPY session is available at or before the requested decision date")
            decision_session = eligible_spy[-1].date
            decision_date = date.fromisoformat(decision_session)
            schedule = _nyse_schedule(decision_date, decision_date + timedelta(days=10))
            future_sessions = [session for session in _session_dates(schedule) if session > decision_date]
            next_session_date = future_sessions[0] if future_sessions else None

        members, membership_changes_reversed = self.sp500_at(decision_date)
        member_by_symbol = {m["symbol"]: m for m in members}

        spy_bars = [bar for bar in spy_bars_all if bar.date <= decision_session]
        regime, spy_tr, spy_ema = market_regime([b.total_return_close for b in spy_bars])

        ranked_all, price_errors = self.price_universe(members, lagged=lagged, through_date=decision_session)
        signal_by_symbol = {s.symbol: s for s in ranked_all}
        ranked = [s for s in ranked_all if s.score > 0]

        raw_rank_by_symbol = {signal.symbol: rank for rank, signal in enumerate(ranked, start=1)}

        fundamental_rows: dict[str, dict] = {}
        checked = 0
        if regime.value == "BULL":
            # Momentum ranks are frozen BEFORE the fundamental screen. A failed
            # #7 does not promote raw momentum rank #21 into the Top 20.
            symbols_to_check: list[str] = [s.symbol for s in ranked[:35]]
            for symbol in sorted(holdings):
                rank = raw_rank_by_symbol.get(symbol)
                if rank is not None and rank <= 35 and symbol not in symbols_to_check:
                    symbols_to_check.append(symbol)

            with ThreadPoolExecutor(max_workers=4) as pool:
                for start_idx in range(0, len(symbols_to_check), 8):
                    batch_symbols = symbols_to_check[start_idx : start_idx + 8]
                    futures = {
                        pool.submit(self.ttm_fundamentals, symbol, decision_date): symbol
                        for symbol in batch_symbols
                    }
                    batch_rows: dict[str, dict] = {}
                    for future in as_completed(futures):
                        symbol = futures[future]
                        try:
                            batch_rows[symbol] = future.result()
                        except Exception as exc:
                            batch_rows[symbol] = {
                                "symbol": symbol,
                                "check": FundamentalCheck(
                                    FundamentalStatus.REVIEW,
                                    None,
                                    None,
                                    False,
                                    f"Fundamentals unavailable: {type(exc).__name__}",
                                ),
                                "source": "SEC EDGAR/XBRL",
                            }
                    checked += len(batch_symbols)
                    fundamental_rows.update(batch_rows)

        candidates = []
        for rank, signal in enumerate(ranked[:35], start=1):
            f = fundamental_rows.get(signal.symbol) or {
                "symbol": signal.symbol,
                "check": FundamentalCheck(
                    FundamentalStatus.REVIEW,
                    None,
                    None,
                    False,
                    "Fundamentals not checked because the market regime is BEAR",
                ),
                "source": "SEC EDGAR/XBRL",
            }
            member = member_by_symbol.get(signal.symbol, {})
            check = f["check"]
            candidates.append(
                {
                    "rank": rank,
                    "symbol": signal.symbol,
                    "name": member.get("name") or f.get("company") or signal.symbol,
                    "sector": member.get("sector") or f.get("sector"),
                    "security_id": member.get("security_id") or f.get("security_id") or signal.security_id or signal.symbol,
                    "issuer_id": member.get("issuer_id") or f.get("issuer_id") or signal.symbol,
                    "price": signal.price,
                    "score": signal.score,
                    "r63": signal.r63,
                    "r126": signal.r126,
                    "r252": signal.r252,
                    "adv63": signal.adv63,
                    "atr14": signal.atr14,
                    "atr_pct": signal.atr_pct,
                    "revenue_growth_ttm": check.revenue_growth_ttm,
                    "gross_margin_ttm": check.gross_margin_ttm,
                    "gross_margin_exempt": check.gross_margin_exempt,
                    "fundamental_status": check.status.value,
                    "fundamental_reason": check.reason,
                    "fundamental_last_filed": f.get("last_filed"),
                    "entry_zone": rank <= 20,
                    "retention_zone": rank <= 35,
                    "purchase_verified": rank <= 20 and check.status == FundamentalStatus.PASS,
                }
            )

        holding_checks = {}
        for symbol in sorted(holdings):
            member = member_by_symbol.get(symbol)
            if member is None:
                holding_checks[symbol] = {
                    "symbol": symbol,
                    "rank": None,
                    "in_index": False,
                    "membership_exit": True,
                    "momentum_positive": None,
                    "fundamental_status": "REVIEW",
                    "reason": "Security is absent from the current S&P 500 membership feed",
                    "sector": None,
                    "security_id": symbol,
                    "issuer_id": symbol,
                }
                continue

            sig = signal_by_symbol.get(symbol)
            f = fundamental_rows.get(symbol)
            raw_rank = raw_rank_by_symbol.get(symbol)
            if sig is None:
                holding_checks[symbol] = {
                    "symbol": symbol,
                    "rank": None,
                    "in_index": True,
                    "membership_exit": False,
                    "momentum_positive": None,
                    "fundamental_status": "REVIEW",
                    "reason": "Required price history or ATR unavailable",
                    "sector": member.get("sector"),
                    "security_id": member.get("security_id") or symbol,
                    "issuer_id": member.get("issuer_id") or symbol,
                }
                continue

            status = f["check"].status.value if f else "REVIEW"
            holding_checks[symbol] = {
                "symbol": symbol,
                "rank": raw_rank,
                "in_index": True,
                "membership_exit": False,
                "momentum_positive": sig.score > 0,
                "score": sig.score,
                "price": sig.price,
                "atr14": sig.atr14,
                "atr_pct": sig.atr_pct,
                "fundamental_status": status,
                "fundamental_reason": f["check"].reason if f else (
                    "Fundamentals not required because a valid momentum/rank exit already applies"
                    if sig.score <= 0 or (raw_rank is not None and raw_rank > 35)
                    else "Required fundamentals unavailable"
                ),
                "sector": member.get("sector") or (f or {}).get("sector"),
                "security_id": member.get("security_id") or (f or {}).get("security_id") or sig.security_id or symbol,
                "issuer_id": member.get("issuer_id") or (f or {}).get("issuer_id") or symbol,
            }

        return {
            "asof": datetime.now(timezone.utc).isoformat(),
            "decision_date": decision_date.isoformat(),
            "next_execution_session": next_session_date.isoformat() if next_session_date else next((bar.date for bar in spy_bars_all if bar.date > decision_session), None),
            "execution_window_status": _execution_window(next_session_date),
            "variant": "lagged-21" if lagged else "baseline",
            "membership_source": f"{SP500_CSV_URL} + {SP500_HISTORY_URL}",
            "membership_note": "Live month-end membership is reconstructed from current constituents plus effective-dated historical changes. Full backtests still require a verified point-in-time constituent/delisting dataset.",
            "membership_changes_reversed": len(membership_changes_reversed),
            "regime": {
                "state": regime.value,
                "spy_total_return_index": spy_tr,
                "spy_ema200": spy_ema,
                "distance_pct": (spy_tr / spy_ema - 1.0) if spy_ema else None,
            },
            "universe_size": len(members),
            "positive_momentum_count": len(ranked),
            "fundamental_checks": checked,
            "eligible_verified_count": sum(1 for row in candidates if row["fundamental_status"] == "PASS"),
            "candidates": candidates,
            "holding_checks": holding_checks,
            "price_errors": price_errors,
        }
