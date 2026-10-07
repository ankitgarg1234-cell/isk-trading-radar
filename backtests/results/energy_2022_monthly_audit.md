# 2022 Energy stock capture audit

Audit basis: the independent reconstructed frozen-like 75/25 engine (global momentum entry Top-20 / incumbent retention Top-35, 25% size-first leadership sleeve, SPY EMA200 BULL/BEAR gate, inverse-ATR sizing, 3x ATR stop). This is not the exact historical $19,808 artifact.

Global raw rank below is computed across all point-in-time S&P names with a usable momentum score. Engine eligible rank is the reconstruction's rank after fundamental PASS and positive momentum. Energy rank is raw momentum rank within point-in-time Energy constituents.

| Month-end | SPY state | Energy names | Positive mom | Raw global Top-20 | Engine Top-20 | Owned Energy wt | Target Energy wt | Target Energy names |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 2022-01-31 | BULL | 17 | 17 | 11 | 1 | 0.0% | 3.9% | BKR |
| 2022-02-28 | BEAR | 17 | 17 | 11 | 1 | 4.1% | 0.0% | - |
| 2022-03-31 | BULL | 17 | 17 | 12 | 1 | 0.0% | 2.9% | BKR |
| 2022-04-29 | BEAR | 17 | 17 | 11 | 1 | 0.0% | 0.0% | - |
| 2022-05-31 | BEAR | 17 | 17 | 14 | 1 | 0.0% | 0.0% | - |
| 2022-06-30 | BEAR | 17 | 15 | 10 | 1 | 0.0% | 0.0% | - |
| 2022-07-29 | BEAR | 17 | 17 | 9 | 0 | 0.0% | 0.0% | - |
| 2022-08-31 | BEAR | 17 | 16 | 9 | 0 | 0.0% | 0.0% | - |
| 2022-09-30 | BEAR | 17 | 12 | 7 | 0 | 0.0% | 0.0% | - |
| 2022-10-31 | BEAR | 19 | 18 | 11 | 0 | 0.0% | 0.0% | - |
| 2022-11-30 | BULL | 19 | 19 | 8 | 0 | 0.0% | 0.0% | - |
| 2022-12-30 | BEAR | 19 | 19 | 10 | 1 | 0.0% | 0.0% | - |

## Non-selection reason counts across all monthly Energy observations

| Reason | Count |
|---|---:|
| BEAR GATE: liquidate/block equity | 157 |
| FUNDAMENTAL UNRESOLVED | 36 |
| FUNDAMENTAL FAIL | 14 |
| GLOBAL RANK >20: NOT NEW-ENTRY ELIGIBLE | 1 |

## Highest-momentum Energy names by month

| Month-end | Energy #1 | Raw global rank | Engine rank | Momentum | Owned wt | Next target wt | Status |
|---|---|---:|---:|---:|---:|---:|---|
| 2022-01-31 | DVN | 1 | - | +118.4% | 0.0% | 0.0% | FUNDAMENTAL UNRESOLVED |
| 2022-02-28 | DVN | 1 | - | +109.4% | 0.0% | 0.0% | BEAR GATE: liquidate/block equity |
| 2022-03-31 | OXY | 1 | - | +98.8% | 0.0% | 0.0% | FUNDAMENTAL UNRESOLVED |
| 2022-04-29 | DVN | 1 | - | +76.5% | 0.0% | 0.0% | BEAR GATE: liquidate/block equity |
| 2022-05-31 | OXY | 1 | - | +108.0% | 0.0% | 0.0% | BEAR GATE: liquidate/block equity |
| 2022-06-30 | OXY | 1 | - | +64.7% | 0.0% | 0.0% | BEAR GATE: liquidate/block equity |
| 2022-07-29 | OXY | 2 | - | +79.8% | 0.0% | 0.0% | BEAR GATE: liquidate/block equity |
| 2022-08-31 | OXY | 1 | - | +75.4% | 0.0% | 0.0% | BEAR GATE: liquidate/block equity |
| 2022-09-30 | OXY | 2 | - | +39.9% | 0.0% | 0.0% | BEAR GATE: liquidate/block equity |
| 2022-10-31 | DVN | 1 | - | +58.9% | 0.0% | 0.0% | BEAR GATE: liquidate/block equity |
| 2022-11-30 | MPC | 1 | - | +48.6% | 0.0% | 0.0% | FUNDAMENTAL UNRESOLVED |
| 2022-12-30 | SLB | 2 | - | +60.9% | 0.0% | 0.0% | BEAR GATE: liquidate/block equity |

## Files

- Detailed row-level audit: backtests/results/energy_2022_monthly_audit.csv
- Month summary: backtests/results/energy_2022_monthly_summary.csv

## Caveats

- Historical S&P membership is reconstructed point-in-time, but ticker-to-sector labels use the current GICS mapping and do not reconstruct every historical GICS reclassification.
- The SEC fundamental PASS reconstruction is the largest known mismatch versus the original frozen artifact.
- Therefore use this audit to identify mechanisms and relative bottlenecks; exact frozen-artifact attribution still requires the original ledger/data package.
