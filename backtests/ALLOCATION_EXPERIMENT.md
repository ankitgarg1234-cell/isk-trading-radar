# Stock allocation diagnostic

The current historical replay found no executable entries. All seven policies
kept their starting $10,000 in cash from 2024-01-02 through 2026-10-01. The
cached S&P 500 total-return benchmark gained 67.43%. **Allocation and profit
taking are not assessable in this run:** no stock reached both current lane
qualification and 2× entry R/R. These are idle-account outcomes, not returns
from a fully invested strategy. No live allocation default is changed.

## Fixed comparison

All cases retain current fundamental, lane, actionable-entry and priority gates,
and require R/R >= 2 at signal and execution. All use whole shares, dated
next-open fills and fees. The account has no external deposits, withdrawals,
leverage, ETF sleeve or cash interest.

| Allocation | Sizing | Profit taking | Cost per side |
| --- | --- | --- | --- |
| Capped | Existing conviction ladder, 15% cap and 0.75% modeled stop-risk budget per holding | On and off | 10 bps |
| Uncapped with risk | Conviction weights normalized over available cash; 0.75% risk budget retained | On and off | 10 bps |
| Full deployment | Normalized cash allocation; cap and per-holding risk ceiling removed | On and off | 10 bps |
| Full deployment sensitivity | Same as above | On | 50 bps |

Removing the 15% cap alone does not remove the independent risk-size ceiling.
One eligible stock can consume nearly all cash in the full-deployment case;
fees and whole-share rounding leave a residual. Cash remains unallocated if
there is no actionable NEW or ADD. Profit-taking proceeds await another
eligible allocation. A one-share holding cannot be partially harvested while
retaining a runner.

## Findings and limits

- 690 sessions, 340,509 stock-day analyses, 26 lane-qualified observations,
  zero lane-qualified observations with R/R >= 2, and zero executed trades.
- Reconstructing the 26 observations finds eight symbols, with R/R between
  0.30× and 1.50×. See `stock_allocation_blockers.json` for dated levels.
- Conviction and fundamental-score failures dominate the broader funnel.
  These are overlapping stock-day observations, not unique stock counts.
- Zero of 33 complete months reached 30%; October 2026 is partial.
  This is no evidence for 30% monthly returns and no measurement of the
  relative performance of allocation or harvesting policies.
- The sample covers a historical S&P membership proxy: 539 of 555 symbols
  have price histories, and 478 have usable cached fundamentals. It is not
  the production 5,000-plus-stock universe; CRDO is absent.
- Historical analyst consensus, broad news and strategic-capital archives
  are missing. Fundamental sample concepts are limited, and vendor share
  units are assumed to match recorded period-end units before split rollforward.
- Missing delisting/acquisition marks and terminal payouts are not rebuilt.
  Dividends are credited on cached ex-dates and fractional split entitlements
  use the split opening price for cash-in-lieu.
- USD results exclude actual Avanza commissions, SEK FX, tax and ISK charges.
  The modeled stop is a sizing reference, not an automatic Core stop-loss.
- This is retrospective research; 2026 was already inspected in earlier work.

The next experiment needs verified historical signal coverage, consistent
entry/target/stop horizons and missing archives before comparing sizing on
the same actual entries. Do not enlarge reward assumptions just to pass the
2× gate or select parameters to force the 30% objective.

## Execution and replay repairs

Final share sizing now respects risk and fees without being enlarged by display
target capital. Paper entries validate scoring version, recent analysis,
fresh timestamped quotes and executable-price R/R. Candidate eligibility is
applied before the ranked allocation limit. Scanner work reserves discovery
and broad-market slots rather than allowing stale refreshes to exhaust them.

Profit stages persist original quantity, completed stages and harvested shares.
Base and stretch targets have cumulative 25% and 50% tranches, execute once,
retain a runner and block immediate additions above a harvested frozen target.
Technical or lane weakness alone does not liquidate thesis-intact Core positions.

The replay uses dated pending orders, frozen signal quantities, fill-time
clipping/rejection, one-time corporate actions, native historical price/share
units and filing acceptance timestamps gated at the actual NYSE close. Each
case's cash and equity are rebuilt independently from dated ledger events.

## Validation and reproduction

The application suite passed **216 tests**. Behavioral tests cover buys, gap
cancellations, risk sizing, staged partial sales, splits, dividends and filing
cutoffs. Historical ledger checks reconcile all seven cases within $0.02,
but with zero trades these validate idle balances only. A five-session
uninterrupted run exactly matches a two-session checkpoint plus resumed run.

```sh
python -m pip install -r requirements-backtest.txt
python -m pytest tests -q
python scripts/stock_allocation_experiment.py
python scripts/inspect_allocation_blockers.py \
  backtests/results/stock_allocation_experiment.json \
  backtests/results/stock_allocation_blockers.json
```

For bounded execution, use `--max-sessions 25` and rerun with `--resume` until
completion. Checkpoints are trusted, locally generated pickle files; do not
load external checkpoints. Resume rejects changed source, data or protocol.

`stock_allocation_experiment.protocol.json` records the predeclared cases and
source/data SHA256 fingerprints. The result records curves, trades, rejections,
corporate cash events, ending holdings, pending orders and a deterministic
content hash. The frozen run used base commit
`62937bf14fa8f43bdc9f8c48de24d971a10cb61d` plus the recorded modified source.
A rerun from another commit changes the provenance hash even if outcomes match.

To render the shareable report, install matplotlib in the reporting environment
and run `scripts/render_allocation_report.py` with the result, output HTML,
`--test-log`, and optional `--gate-details`, `--patch` and `--review-url`.
