from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import floor, isfinite
from typing import Iterable, Sequence


EMA_PERIOD = 200
EMA_ALPHA = 2 / 201
MOMENTUM_LOOKBACKS = (63, 126, 252)
LAG_SESSIONS = 21
ATR_PERIOD = 14
STOP_ATR_MULTIPLE = 3.0
MAX_HOLDINGS = 20
ENTRY_RANK_CUTOFF = 20
RETENTION_RANK_CUTOFF = 35
SLIPPAGE_BPS = 5.0
EXECUTION_ALLOWANCE_BPS = 2.0
COMMISSION_PER_SHARE = 0.005
MIN_COMMISSION = 1.0


class Regime(str, Enum):
    BULL = "BULL"
    BEAR = "BEAR"


class FundamentalStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    REVIEW = "REVIEW"


@dataclass(frozen=True)
class PriceBar:
    date: str
    open: float
    high: float
    low: float
    close: float
    total_return_close: float
    volume: float = 0.0


@dataclass(frozen=True)
class MomentumSignal:
    symbol: str
    score: float
    r63: float
    r126: float
    r252: float
    adv63: float
    atr14: float
    price: float
    atr_pct: float
    security_id: str | None = None


@dataclass(frozen=True)
class FundamentalCheck:
    status: FundamentalStatus
    revenue_growth_ttm: float | None
    gross_margin_ttm: float | None
    gross_margin_exempt: bool
    reason: str


@dataclass(frozen=True)
class StopState:
    peak: float
    stop: float
    breached: bool


def _finite_positive(value: float | None) -> bool:
    return value is not None and isfinite(float(value)) and float(value) > 0


def ema_seeded(values: Sequence[float], period: int = EMA_PERIOD) -> list[float | None]:
    """EMA seeded with the arithmetic mean of the first period observations."""
    if period <= 0:
        raise ValueError("period must be positive")
    if len(values) < period:
        return [None] * len(values)
    vals = [float(v) for v in values]
    if any(not isfinite(v) or v <= 0 for v in vals):
        raise ValueError("EMA input must be finite and positive")
    alpha = 2 / (period + 1)
    out: list[float | None] = [None] * len(vals)
    seed = sum(vals[:period]) / period
    out[period - 1] = seed
    previous = seed
    for i in range(period, len(vals)):
        previous = alpha * vals[i] + (1 - alpha) * previous
        out[i] = previous
    return out


def market_regime(total_return_series: Sequence[float]) -> tuple[Regime, float, float]:
    ema = ema_seeded(total_return_series, EMA_PERIOD)
    last_ema = ema[-1] if ema else None
    if last_ema is None:
        raise ValueError("SPY requires at least 200 sessions for the regime signal")
    last = float(total_return_series[-1])
    state = Regime.BULL if last > last_ema else Regime.BEAR
    return state, last, float(last_ema)


def momentum_components(total_return_series: Sequence[float], *, lagged: bool = False) -> tuple[float, float, float]:
    values = [float(v) for v in total_return_series]
    endpoint_lag = LAG_SESSIONS if lagged else 0
    endpoint = len(values) - 1 - endpoint_lag
    if endpoint < 0:
        raise ValueError("insufficient price history")
    returns: list[float] = []
    for tau in MOMENTUM_LOOKBACKS:
        start = endpoint - tau
        if start < 0:
            raise ValueError("insufficient price history")
        denominator = values[start]
        numerator = values[endpoint]
        if not _finite_positive(denominator) or not _finite_positive(numerator):
            raise ValueError("invalid total-return price history")
        returns.append(numerator / denominator - 1.0)
    return returns[0], returns[1], returns[2]


def momentum_score(total_return_series: Sequence[float], *, lagged: bool = False) -> tuple[float, tuple[float, float, float]]:
    parts = momentum_components(total_return_series, lagged=lagged)
    return sum(parts) / 3.0, parts


def average_dollar_volume_63(bars: Sequence[PriceBar]) -> float:
    if len(bars) < 63:
        raise ValueError("63 sessions required for average dollar volume")
    sample = bars[-63:]
    values = [float(b.close) * float(b.volume) for b in sample]
    if any(not isfinite(v) or v < 0 for v in values):
        raise ValueError("invalid dollar-volume history")
    return sum(values) / 63.0


def true_range(current: PriceBar, prior_close: float) -> float:
    return max(
        float(current.high) - float(current.low),
        abs(float(current.high) - float(prior_close)),
        abs(float(current.low) - float(prior_close)),
    )


def wilder_atr_series(bars: Sequence[PriceBar], period: int = ATR_PERIOD) -> list[float | None]:
    if len(bars) < period + 1:
        return [None] * len(bars)
    trs: list[float | None] = [None]
    for i in range(1, len(bars)):
        trs.append(true_range(bars[i], bars[i - 1].close))
    seed_trs = [float(v) for v in trs[1 : period + 1] if v is not None]
    if len(seed_trs) != period:
        return [None] * len(bars)
    out: list[float | None] = [None] * len(bars)
    atr = sum(seed_trs) / period
    out[period] = atr
    for i in range(period + 1, len(bars)):
        tr = trs[i]
        if tr is None:
            continue
        atr = ((period - 1) * atr + float(tr)) / period
        out[i] = atr
    return out


def latest_atr14(bars: Sequence[PriceBar], *, preceding_session: bool = False) -> float:
    series = wilder_atr_series(bars, ATR_PERIOD)
    idx = -2 if preceding_session else -1
    if len(series) < abs(idx):
        raise ValueError("insufficient ATR history")
    value = series[idx]
    if value is None or not _finite_positive(value):
        raise ValueError("valid positive ATR14 unavailable")
    return float(value)


def build_momentum_signal(symbol: str, bars: Sequence[PriceBar], *, lagged: bool = False, security_id: str | None = None) -> MomentumSignal:
    tr = [b.total_return_close for b in bars]
    score, parts = momentum_score(tr, lagged=lagged)
    atr = latest_atr14(bars)
    price = float(bars[-1].close)
    if not _finite_positive(price):
        raise ValueError("invalid closing price")
    atr_pct = atr / price
    if not _finite_positive(atr_pct):
        raise ValueError("invalid percentage ATR")
    return MomentumSignal(
        symbol=symbol,
        score=score,
        r63=parts[0],
        r126=parts[1],
        r252=parts[2],
        adv63=average_dollar_volume_63(bars),
        atr14=atr,
        price=price,
        atr_pct=atr_pct,
        security_id=security_id,
    )


def evaluate_fundamentals(
    revenue_quarters: Sequence[float] | None,
    gross_profit_quarters: Sequence[float] | None,
    *,
    gross_margin_exempt: bool = False,
) -> FundamentalCheck:
    if revenue_quarters is None or len(revenue_quarters) < 8:
        return FundamentalCheck(FundamentalStatus.REVIEW, None, None, gross_margin_exempt, "Eight published revenue quarters unavailable")
    revenue = [float(v) for v in revenue_quarters[-8:]]
    if any(not isfinite(v) for v in revenue):
        return FundamentalCheck(FundamentalStatus.REVIEW, None, None, gross_margin_exempt, "Required revenue facts unavailable")
    latest_revenue = sum(revenue[-4:])
    prior_revenue = sum(revenue[-8:-4])
    if latest_revenue <= 0 or prior_revenue <= 0:
        return FundamentalCheck(FundamentalStatus.FAIL, None, None, gross_margin_exempt, "Revenue denominator must be valid and positive")
    growth = latest_revenue / prior_revenue - 1.0
    if growth < 0:
        return FundamentalCheck(FundamentalStatus.FAIL, growth, None, gross_margin_exempt, "TTM revenue growth is negative")
    if gross_margin_exempt:
        return FundamentalCheck(FundamentalStatus.PASS, growth, None, True, "Revenue growth passes; gross margin structurally exempt")
    if gross_profit_quarters is None or len(gross_profit_quarters) < 4:
        return FundamentalCheck(FundamentalStatus.REVIEW, growth, None, False, "Required gross-profit facts unavailable")
    gross = [float(v) for v in gross_profit_quarters[-4:]]
    if any(not isfinite(v) for v in gross):
        return FundamentalCheck(FundamentalStatus.REVIEW, growth, None, False, "Required gross-profit facts unavailable")
    gross_margin = sum(gross) / latest_revenue
    if not isfinite(gross_margin):
        return FundamentalCheck(FundamentalStatus.REVIEW, growth, None, False, "Gross margin unavailable")
    if gross_margin <= 0:
        return FundamentalCheck(FundamentalStatus.FAIL, growth, gross_margin, False, "TTM gross margin is not positive")
    return FundamentalCheck(FundamentalStatus.PASS, growth, gross_margin, False, "Required fundamental checks pass")


def rank_signals(signals: Iterable[MomentumSignal]) -> list[MomentumSignal]:
    """Rank by momentum, then higher ADV63, then stable security identifier."""
    return sorted(signals, key=lambda s: (-s.score, -s.adv63, s.security_id or s.symbol))


def target_weights(signals: Sequence[MomentumSignal]) -> tuple[dict[str, float], float]:
    n = len(signals)
    if n > MAX_HOLDINGS:
        raise ValueError("selected holdings exceed 20")
    if n == 0:
        return {}, 1.0
    equity_exposure = n / MAX_HOLDINGS
    inverses: dict[str, float] = {}
    for s in signals:
        if not _finite_positive(s.atr_pct):
            raise ValueError(f"{s.symbol}: invalid ATR percentage")
        inverses[s.symbol] = 1.0 / s.atr_pct
    denom = sum(inverses.values())
    weights = {symbol: equity_exposure * inv / denom for symbol, inv in inverses.items()}
    return weights, 1.0 - equity_exposure


def initial_stop(fill_price: float, preceding_atr14: float) -> StopState:
    if not _finite_positive(fill_price) or not _finite_positive(preceding_atr14):
        raise ValueError("valid fill and preceding-session ATR are required")
    fill = float(fill_price)
    return StopState(peak=fill, stop=fill - STOP_ATR_MULTIPLE * float(preceding_atr14), breached=False)


def advance_stop(previous: StopState, close: float, atr14: float) -> StopState:
    close = float(close)
    atr14 = float(atr14)
    if not _finite_positive(close) or not _finite_positive(atr14):
        raise ValueError("valid close and ATR14 are required")
    if close <= previous.stop:
        return StopState(peak=previous.peak, stop=previous.stop, breached=True)
    peak = max(previous.peak, close)
    stop = max(previous.stop, peak - STOP_ATR_MULTIPLE * atr14)
    return StopState(peak=peak, stop=stop, breached=False)


def estimated_commission(shares: int) -> float:
    if shares <= 0:
        return 0.0
    return max(MIN_COMMISSION, COMMISSION_PER_SHARE * int(shares))


def estimated_side_cost(price: float, shares: int) -> float:
    notional = max(0.0, float(price)) * max(0, int(shares))
    market_cost = notional * ((SLIPPAGE_BPS + EXECUTION_ALLOWANCE_BPS) / 10_000.0)
    return market_cost + estimated_commission(shares)


def whole_share_target(target_value: float, signal_close: float) -> int:
    """Quantity uses only information available at submission; never next-session open."""
    if target_value <= 0 or signal_close <= 0:
        return 0
    return max(0, floor(float(target_value) / float(signal_close)))
