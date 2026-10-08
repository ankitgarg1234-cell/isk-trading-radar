# SPY + sector hierarchy backtest (2022-Sep 2026)

Corrected research replay: December warm-start, raw momentum rank before fundamental filter, strict point-in-time filing cutoffs, missing-snapshot exits, verified historical sector snapshots. The experiment changes only market/sector permission; sizing and 3x ATR are otherwise unchanged.

Sector BULL = sector ETF has positive 63/126/252 average total-return momentum and is above its own EMA200. SPY BULL/BEAR is evaluated independently. In the Bear-exception variants, SPY BULL leaves the frozen engine unchanged; only SPY BEAR can admit stocks from BULL sectors.

| Variant | 2022 | 2023 | 2024 | 2025 | 2026 | CAGR | Max DD | Avg exposure | Turnover | Costs |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| PIT frozen-like control | -5.08% | -6.39% | +2.09% | +7.83% | +9.94% | 1.46% | -13.39% | 22.01% | 4.36x | $701 |
| Bear exception: all BULL sectors | -7.85% | -3.36% | -0.33% | +7.78% | +11.04% | 1.22% | -13.72% | 22.42% | 4.43x | $702 |
| Bear exception: Top-3 BULL sectors | -6.00% | -2.99% | -0.06% | +7.40% | +9.69% | 1.43% | -11.51% | 22.01% | 4.34x | $693 |
| Bear exception: Top-2 BULL sectors | -6.01% | -2.98% | -0.06% | +7.79% | +10.63% | 1.68% | -11.53% | 21.77% | 4.29x | $685 |
| Bear exception: Top-1 BULL sector | -5.08% | -5.34% | -0.91% | +7.65% | +11.13% | 1.27% | -12.86% | 21.11% | 4.15x | $659 |
| Full hierarchy: sector BULL required | -7.68% | -2.57% | -0.31% | +9.13% | +9.72% | 1.43% | -12.72% | 21.44% | 4.20x | $667 |
| Full hierarchy + Top-2 in SPY BEAR | -5.84% | -1.63% | -0.01% | +11.40% | +9.42% | 2.45% | -10.07% | 20.77% | 4.08x | $661 |

## Point-in-time sector coverage

| Period | Min coverage | Median coverage | Max coverage |
|---|---:|---:|---:|
| 2022-Sep 2026 | 98.0% | 99.2% | 100.0% |

## Monthly state sample: 2022-2023, Top-2 bear exception

| Month-end | SPY | Allowed sector set | Sector #1 | Sector #1 state |
|---|---|---|---|---|
| 2022-01-31 | BULL | Communication Services, Consumer Discretionary, Consumer Staples, Energy, Financials, Health Care, Industrials, Information Technology, Materials, Real Estate, Utilities | Energy | BULL |
| 2022-02-28 | BEAR | Consumer Staples, Energy | Energy | BULL |
| 2022-03-31 | BULL | Communication Services, Consumer Discretionary, Consumer Staples, Energy, Financials, Health Care, Industrials, Information Technology, Materials, Real Estate, Utilities | Energy | BULL |
| 2022-04-29 | BEAR | Consumer Staples, Energy | Energy | BULL |
| 2022-05-31 | BEAR | Energy, Utilities | Energy | BULL |
| 2022-06-30 | BEAR | Energy, Utilities | Energy | BULL |
| 2022-07-29 | BEAR | Energy, Utilities | Energy | BULL |
| 2022-08-31 | BEAR | Energy, Utilities | Energy | BULL |
| 2022-09-30 | BEAR | Energy | Energy | BULL |
| 2022-10-31 | BEAR | Energy, Health Care | Energy | BULL |
| 2022-11-30 | BULL | Communication Services, Consumer Discretionary, Consumer Staples, Energy, Financials, Health Care, Industrials, Information Technology, Materials, Real Estate, Utilities | Energy | BULL |
| 2022-12-30 | BEAR | Energy, Industrials | Energy | BULL |
| 2023-01-31 | BULL | Communication Services, Consumer Discretionary, Consumer Staples, Energy, Financials, Health Care, Industrials, Information Technology, Materials, Real Estate, Utilities | Energy | BULL |
| 2023-02-28 | BULL | Communication Services, Consumer Discretionary, Consumer Staples, Energy, Financials, Health Care, Industrials, Information Technology, Materials, Real Estate, Utilities | Energy | BULL |
| 2023-03-31 | BULL | Communication Services, Consumer Discretionary, Consumer Staples, Energy, Financials, Health Care, Industrials, Information Technology, Materials, Real Estate, Utilities | Information Technology | BULL |
| 2023-04-28 | BULL | Communication Services, Consumer Discretionary, Consumer Staples, Energy, Financials, Health Care, Industrials, Information Technology, Materials, Real Estate, Utilities | Information Technology | BULL |
| 2023-05-31 | BULL | Communication Services, Consumer Discretionary, Consumer Staples, Energy, Financials, Health Care, Industrials, Information Technology, Materials, Real Estate, Utilities | Information Technology | BULL |
| 2023-06-30 | BULL | Communication Services, Consumer Discretionary, Consumer Staples, Energy, Financials, Health Care, Industrials, Information Technology, Materials, Real Estate, Utilities | Information Technology | BULL |
| 2023-07-31 | BULL | Communication Services, Consumer Discretionary, Consumer Staples, Energy, Financials, Health Care, Industrials, Information Technology, Materials, Real Estate, Utilities | Information Technology | BULL |
| 2023-08-31 | BULL | Communication Services, Consumer Discretionary, Consumer Staples, Energy, Financials, Health Care, Industrials, Information Technology, Materials, Real Estate, Utilities | Information Technology | BULL |
| 2023-09-29 | BULL | Communication Services, Consumer Discretionary, Consumer Staples, Energy, Financials, Health Care, Industrials, Information Technology, Materials, Real Estate, Utilities | Energy | BULL |
| 2023-10-31 | BEAR | Communication Services, Information Technology | Communication Services | BULL |
| 2023-11-30 | BULL | Communication Services, Consumer Discretionary, Consumer Staples, Energy, Financials, Health Care, Industrials, Information Technology, Materials, Real Estate, Utilities | Information Technology | BULL |
| 2023-12-29 | BULL | Communication Services, Consumer Discretionary, Consumer Staples, Energy, Financials, Health Care, Industrials, Information Technology, Materials, Real Estate, Utilities | Information Technology | BULL |

## Interpretation guardrail

- This remains the independent public-data reconstruction, not the exact frozen $19,808.08 artifact. Compare variants within this replay; do not substitute these absolute returns for the frozen 14.66% benchmark.
- The SEC fundamental PASS approximation remains a known mismatch and can suppress otherwise strong stocks. Point-in-time sector classification is corrected using the nearest prior dated PIT sector snapshot, but the exact original fundamental dataset is still unavailable.
