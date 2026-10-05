# Short-horizon forecast evaluation — 5 October 2026

## Deployment scope

Research-only forecasts added to the existing analysis pages and canonical observation archive. No changes to deterministic scoring v14, entry gates (70 / 75 / 0.4), targets, stops, sizing, account count, trial dates or paper execution. These diagnostics are not a trading-return backtest.

## Method

Five calendar-day horizons: 15, 25, 30, 45 and 60. Default Core horizon is 30 calendar days; default Explosive horizon is 15 calendar days, retaining the 20-trading-session holding limit. All horizons are displayed; the best-looking horizon is never selected for execution.

126 completed adjusted-close sessions form the training window. Fixed daily log-return weights are 25% full-window, 35% last 63 returns and 40% last 21 returns. When at least 64 aligned sector observations exist through the same final session, sector 21-return drift receives 10% weight. The daily drift is shrunk 50% toward zero and damped over a 20-session timescale. Centered historical multi-session block returns provide 10th/50th/90th percentile price factors and the mean price factor. The base price is the median, while expected return is the distribution mean; these are labeled separately. Both can be negative.

Current quote anchors forecast prices; completed-session history supplies returns. Running-day bars, future rows, invalid closes, conflicting dates, stale histories and long gaps do not become training data. Missing sector evidence falls back to the stock-only model. Invalid stop geometry produces unavailable research R/R. Calculation failure cannot interrupt scoring or exits.

Weekday counts approximate future sessions; exchange holidays and future discrete event gaps are not modeled. Calendar deadlines may be non-trading dates. Bounds are nominal 80% empirical intervals, not guaranteed confidence. Current adjusted histories can reflect subsequent corporate-action adjustments; this is not a point-in-time, full-strategy backtest.

## Validation and readiness

At successive five-session historical cutoffs, fit only to the preceding data and compare the median prediction with the last available close on or before each calendar deadline. Evaluate against no change and a simple 63-return trend. Report overlapping diagnostic folds and greedily selected non-overlapping windows separately. Use non-overlapping metrics for a minimum 20-window threshold, >5% lower absolute return error than both benchmarks, and 70–90% realized coverage of the nominal 80% interval. Passing historical checks alone does not enable execution; broader and prospective validation are still required.

Captured sample: three stocks (NVDA, MSFT, CRDO), each 251 price sessions and 127 sector sessions. Only 2–8 non-overlapping windows per horizon are available. Results do not consistently beat the no-change benchmark. Verdict: **not ready for trading use; evaluation only**. No inference about the entire 5,758-stock universe is supported.

| Stock | Horizon, calendar days | Base price | Mean return | Independent windows | Model error, pp | No-change error, pp | Trend error, pp | Range coverage |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| NVDA | 15 | 241.70 | +1.33% | 8 | 5.616 | 5.473 | 5.683 | 87.5% |
| NVDA | 25 | 244.54 | +1.88% | 6 | 7.135 | 6.905 | 7.500 | 66.7% |
| NVDA | 30 | 244.48 | +2.08% | 5 | 6.783 | 6.827 | 8.816 | 60.0% |
| NVDA | 45 | 245.97 | +2.49% | 3 | 11.231 | 10.140 | 12.141 | 66.7% |
| NVDA | 60 | 244.91 | +2.73% | 2 | 14.635 | 13.520 | 12.764 | 50.0% |
| MSFT | 15 | 524.90 | +1.67% | 8 | 9.148 | 9.072 | 9.261 | 62.5% |
| MSFT | 25 | 524.78 | +2.46% | 6 | 7.312 | 7.186 | 8.779 | 66.7% |
| MSFT | 30 | 525.78 | +2.73% | 5 | 10.577 | 9.676 | 12.584 | 60.0% |
| MSFT | 45 | 517.93 | +3.60% | 3 | 17.306 | 16.137 | 21.584 | 33.3% |
| MSFT | 60 | 541.44 | +3.94% | 2 | 22.130 | 18.996 | 27.008 | 0.0% |
| CRDO | 15 | 222.36 | +4.51% | 8 | 23.763 | 22.293 | 23.166 | 87.5% |
| CRDO | 25 | 231.15 | +6.61% | 6 | 26.396 | 24.359 | 26.657 | 83.3% |
| CRDO | 30 | 226.96 | +7.18% | 5 | 32.269 | 29.178 | 34.456 | 60.0% |
| CRDO | 45 | 209.84 | +8.56% | 3 | 46.953 | 44.216 | 45.631 | 66.7% |
| CRDO | 60 | 218.59 | +10.40% | 2 | 50.363 | 49.436 | 83.487 | 50.0% |

## Reproduction and controls

Captured public inputs are in `tests/fixtures/short_horizon_prices_2026_10_05.json`. Run:

```sh
python scripts/evaluate_short_horizon.py --inputs tests/fixtures/short_horizon_prices_2026_10_05.json --output results.json
```

378 focused regression checks passed across 14 relevant modules. Four known preexisting legacy failures were excluded, matching the prior deployed audit. New controls cover negative/flat projections, calendar units, future/partial-session exclusion, prefix-only sector features, benchmark failures, overlapping-window counts, explicit missing inputs, optional-model failure isolation, old-cache refresh, rendered explanations and unchanged paper fills/trial. Full-repository suite was not run. HTML rendering was checked through the actual template/route. Browser screenshots were unavailable because the local Chromium download failed; desktop/mobile visual layout has not been inspected.

Source references: https://otexts.com/fpp3/tscv.html (rolling-origin evaluation) and https://otexts.com/fpp3/prediction-intervals.html (distributional forecasts). Coefficients above are research assumptions, not parameters endorsed by those references.
