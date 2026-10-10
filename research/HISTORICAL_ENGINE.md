# Isolated five-stock historical engine

Authority: `dual_momentum/trial.py`, not the20-position `rules.py` portfolio
rules or older historical experiments. Only `PriceBar` and Wilder ATR are used
from `rules.py`. The live/paper modules remain unchanged.

`strategy_kernel.py` compiles a whitelist of pure functions from the unchanged
trial AST. A committed manifest pins each function and relevant constant plus
the ATR source. Drift fails closed. Top-level imports, SQLAlchemy models,
database initialization, poll loops, providers and broker code never execute.

`historical_engine.py` supplies an isolated event timeline, actual exchange
openings, close/publication timestamps, prior-known FX, local stop/share units,
USD marks/fees/cash, monthly decisions and daily risk-budget reviews. Ranking,
incumbent protection, entry qualification and sector regime use the exact trial
functions. Execution and risk-budget accounting have independent adapters and
are tested against those functions in the U.S./identity-FX case.

The signal-history seed policy is **the entire supplied history**, as in the
pure trial `_momentum` function. Historical input bundles must fix the start
and vintages; this is not a claim that unknown historical live Yahoo2y windows
were reproduced. No parameters are optimized. The450-signal guard remains and
an additional95% full-universe data acceptance gate prevents a global data
collapse from passing it. Unknown sectors veto the run. All eleven ETFs must
be supplied as a readiness condition; ETF/SPY input histories are unchanged.

The scheduler corrects weekday-only holiday handling with explicit calendar
openings. Sells precede buys **at the same timestamp**; later U.S. sells cannot
fund earlier Asian buys. Missing expected opens expire at that opening and are
not later backfilled. Stops are evaluated when a completed daily bar becomes
available; no intraday timestamp is invented. Foreign stop fills use FX already
observable at that session's open, and cash is released conservatively at bar
publication. This is a disclosed daily-data FX/execution approximation. Other
fills use observable opening FX. FX older than five calendar days fails.

Share actions require source, effective time and a ratio already known by that
time. They transform preceding OHLC, live shares/cost/peak/stop and pending
quantities together. Fractional entitlements fail until real cash-in-lieu data
exist. TR inputs have a separate coherent fixed-index basis and are never
split-adjusted twice. Currency units are explicit; local raw prices cannot be
mixed with USD ATR. The original0.01 stop floor is retained in the local stop
coordinate, with that non-U.S. modeling limitation disclosed.

The terminal reference close freezes new orders, matching the trial; positions
are marked, not fictitiously liquidated. Dividends affect TR ranking inputs,
but the original stock-ledger convention has no explicit cash-dividend credit.
That accounting limitation is preserved for the first comparison, not concealed
as complete economic total returns. Delisting/tender/spin-off recoveries require
independently verified event adapters and remain readiness blockers where relevant.
No generic extreme return is repaired or treated as a split.

`backtest_metrics.py` computes returns, CAGR, drawdown, volatility, zero-risk-free
Sharpe/Sortino, monthly/annual returns, realized FIFO-lot win/holding statistics,
annualized one-way turnover, cash exposure, fees and reconciled stock/sector
cash-flow P&L. Share actions transform lot quantities/costs. Cash-drag and stop
counterfactual effects are deliberately null until paired simulations exist:
realized stopped-lot P&L is not the causal benefit of the stop rule.

Inputs are supplied by the caller; the engine has no acquisition or live state.
Performance entrypoints require the final readiness gate. Synthetic outputs are
labeled `SYNTHETIC_FIXTURE` and remain ignored. This engine's completed fixture
validation does not substitute for historical input coverage or a historical
five-stock performance-parity record.
