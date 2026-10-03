# Score allocation paper experiment v1

This is an isolated forward experiment, approved for testing on 2026-10-02.
No changes are made to production position sizing, trading cash, manual holdings,
or broker execution. Separate SQL tables hold virtual balances and observations.

## Frozen settings

- Start the single virtual paper account with $10,000. Freeze the dashboard risk profile at
  initialization; planned per-position risk uses its existing 0.35/0.75/1.25/2%
  budget. Score weights are targets constrained by this budget, not promises.
- Deterministic score >=70 AND analyst score >=75 AND entry R/R >=0.4.
  Missing or invalid analyst scores fail qualification.
- Preserve eligible Core/Explosive quality, liquidity, price >=$5, confidence,
  promotion-risk and material-negative gates. USD securities only in v1.
- Deterministic bands: [70,75) 10%, [75,80) 15%, [80,85) 20%, [85,90) 30%,
  [90,100] 40% of current equity. Allocate in descending score order; tie by
  symbol. Existing exposure reduces remaining capacity. No borrowing or
  normalization to force 100% invested. Fees and whole shares reduce quantities.
- Pullback: inside Primary/Better Buy zone; RSI14 >=40; reject price below EMA20
  AND 20-day change below -2%. Missing momentum inputs fail entry.
- Breakout: price >=preceding 20 completed daily closing highs +0.1 ATR14,
  relative volume >=1.5, same momentum filters, below the lesser of the supplied
  chase ceiling and preceding high +1.1 ATR14. The running daily close does not
  move the breakout line above itself. Targets are not raised to qualify a fill.
- Queue a signal; fill only at a later fresh exchange quote. Recheck scores,
  frozen target/stop, R/R, entry route and chase ceiling at the adverse fill
  price. Buy intents expire after 10 minutes. No weekend/closed-session fills.
- Preserve target and modeled stop at initial entry. Complete strategy queues
  a full exit when an observation reaches the initial stop or thesis invalidates.
- Once base target is reached, sell ceil(current shares * price gain / net sale
  price), capped to preserve >=1 share. This withdraws profit-sized cash; it does
  not realize all unrealized profit. A one-share position cannot withdraw cash,
  but its remaining share receives the trailing protection after target.
- After withdrawal, peak = highest observed price. Strong momentum means price
  >=EMA20 AND RSI14 >=50. Stop = max(previous stop, peak -(2 if strong else 1)
  * ATR14). Never lower the stop. Queue full exit if observed price <=stop.
  Missing ATR/momentum inputs retain the previous stop. No fixed base-target
  floor is claimed. Stop fills may be below the stop and are never guaranteed.
- A fully exited stock is not reopened in the same UTC trading date.
- Fees 10 bps and adverse slippage 5 bps on each side. Fills use indicative
  Yahoo last prices, not executable bid/ask quotes. Every trade records its
  signal/observation time and fees. Sale P&L includes allocated entry fees.

## Account and interpretation

On 2026-10-03 the user requested one experimental account, not three comparison
accounts. Only `complete_strategy` is active: new selection, agreed allocation
bands, profit withdrawal and momentum stops, starting with $10,000.

The earlier control ledgers are archived inside the existing state for recovery;
they are not displayed, scanned, filled or included in reported performance.
Migration preserves the complete strategy's cash, positions, pending orders,
trades, observations and frozen risk profile. Balances are not combined or reset.
The S&P 500 remains a numerical benchmark, not a separate trading account.

Stock dividends are omitted, as in live paper mark-to-market; the same-start
observed benchmark is the S&P 500 total-return index. If a benchmark is missing
at the first observation, excess return is unavailable rather than starting the
benchmark later. Average cash is sampled at observation cycles, not time-weighted.
Drawdown uses observed marks; unobserved intraday lows can be worse.

Every fresh deep analysis is eligible for the experiment, with no Top-20 limit.
The rotating scanner still has finite coverage. Its market coverage is not a
census of all stocks. Experiment holdings and pending signals receive priority
refresh, without entering the existing manual/paper ownership tables.

## Data integrity and reporting

Exchange `regularMarketTime` is archived independently of retrieval time.
Duplicate quote timestamps do not fill orders. Quotes older than 10 minutes,
future timestamps, and absent exchange timestamps are rejected. This also
blocks stale holiday/early-close quotes despite the scanner's basic session gate.
Actual analyst score, recommendation/target/count inputs and source metadata
are retained at collection time. No analyst consensus is manufactured.

Existing cached 2024–2026 replay data has SEC facts and prices, but no historical
analyst-consensus archive. Run `python scripts/score_band_experiment_audit.py` to
verify coverage. The complete historical return remains null; do not treat a
zero-trade cash portfolio as a strategy performance test.

The authenticated page `/experiments/score-bands` shows balances, returns,
drawdown, trades and realized profit. `/api/experiments/score-bands` includes full
trade and sampled equity histories. No S&P outperformance or 30% monthly return
is established by execution tests; live performance needs observation time.

Focused validation: threshold boundaries; pullbacks and confirmed breakouts;
fill-price gaps and frozen targets; risk, fees and whole shares; highest-score
allocation; duplicate/stale quotes; restart persistence; initial and trailing
exits; one-time withdrawal; separate original ledgers; archived analyst inputs;
report/API availability; unchanged existing paper balances and scanner behavior.

Validation on 2026-10-02: 46 focused checks passed. The broader scanner file has
four pre-existing alert-fixture failures, reproduced unchanged on a248b22; its
other 12 checks passed. Desktop and 390px mobile report views were rendered and
inspected. The authentication test found and fixed session-middleware ordering;
anonymous access is rejected and a valid login grants report access.

Single-account update on 2026-10-03: 49 focused checks passed, including
idempotent legacy migration, preservation of the active ledger, exclusion of
archived positions from scanning, and exactly one report/API account. Desktop
and mobile views were rendered and inspected again.
