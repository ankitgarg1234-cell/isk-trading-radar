# Dual Momentum Radar

This branch contains a standalone dashboard that implements the frozen S&P 500 rotational rules without changing the existing ISK Trading Radar.

## Service entry point

```bash
uvicorn dual_momentum.main:app --host 0.0.0.0 --port 8000
```

Render can use `render-dual-momentum.yaml`.

## Implemented baseline

- SPY dividend-reinvested adjusted-price EMA200 regime with arithmetic-mean seed over the first 200 sessions.
- Month-end decisions pinned to the final SPY session of the most recently completed calendar month.
- Equal-weight 63/126/252-session momentum and the isolated 21-session lag variant.
- Positive-momentum floor and deterministic tie-break order: momentum, 63-session average dollar volume, symbol.
- SEC EDGAR/XBRL TTM revenue-growth and gross-margin checks with a conservative publication-date cutoff.
- Missing fundamentals => review; verified failures => exit; review incumbents cannot be increased.
- Top-20 vacancy entry / Top-35 incumbent retention buffer.
- N/20 aggregate equity exposure and inverse percentage ATR weighting.
- Whole-share quantity proposals from signal-date closes only.
- Sell/trim funding before buys, no negative cash, 5 bps slippage + 2 bps execution allowance and max($1, $0.005/share) modeled commission.
- Actual fill ledger kept separate from modeled execution costs.
- Initial 3xATR stop from actual opening fill and preceding-session ATR.
- Ratcheted closing-price stop logic; additions preserve existing peak and stop.
- Pending stop exits supersede monthly buys.
- Separate dm_* persistence tables so the existing Radar data model is not modified.

## Important research boundary

The live dashboard currently uses a current S&P 500 constituent feed for universe discovery and explicitly labels that limitation. It does **not** claim that this is a valid historical membership source for backtesting.

A production backtest must separately supply:

- point-in-time S&P 500 additions/removals,
- failed and delisted securities,
- point-in-time/restated filing versions,
- corporate actions and dividends,
- matched execution calendars,
- USD and SEK benchmark series,
- whole-share funding and modeled/actual costs.

Performance remains unvalidated.

## Live operation

The UI provides:

1. regime status;
2. verified Top 35 with Top-20 entry zone;
3. current positions and monthly actions;
4. target exposure and inverse-ATR weights;
5. execution queue;
6. cash and fill recording;
7. daily stop refresh;
8. trade ledger.

The dashboard is proposal/recordkeeping software only; it does not place brokerage orders.

## Deployment isolation

Deploy this branch as a **separate Render web service** and preferably give it a separate Postgres database. The service can reuse the same authentication environment-variable pattern as the original dashboard.
