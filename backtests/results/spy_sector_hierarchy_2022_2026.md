# SPY + sector hierarchy backtest (2022-Sep 2026)

Corrected research replay: December warm-start, raw momentum rank before fundamental filter, strict point-in-time filing cutoffs, missing-snapshot exits, verified historical sector snapshots. The experiment changes only market/sector permission; sizing and 3x ATR are otherwise unchanged.

Sector BULL = sector ETF has positive 63/126/252 average total-return momentum and is above its own EMA200. SPY BULL/BEAR is evaluated independently. In the Bear-exception variants, SPY BULL leaves the frozen engine unchanged; only SPY BEAR can admit stocks from BULL sectors.

| Variant | 2022 | 2023 | 2024 | 2025 | 2026 | CAGR | Max DD | Avg exposure | Turnover | Costs |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| PIT frozen-like control | -5.08% | -5.67% | +2.05% | +7.60% | +9.89% | 1.56% | -12.66% | 21.72% | 4.33x | $697 |
| Bear exception: all BULL sectors | -5.78% | -2.95% | -0.05% | +6.51% | +9.79% | 1.34% | -11.65% | 22.62% | 4.43x | $713 |
| Bear exception: Top-3 BULL sectors | -6.26% | -2.24% | -0.06% | +7.27% | +10.63% | 1.68% | -11.49% | 22.02% | 4.33x | $698 |
| Bear exception: Top-2 BULL sectors | -6.01% | -1.79% | -0.06% | +8.10% | +10.43% | 1.95% | -10.93% | 21.64% | 4.26x | $686 |
| Bear exception: Top-1 BULL sector | -5.08% | -4.69% | -0.63% | +7.78% | +9.83% | 1.25% | -12.14% | 20.85% | 4.12x | $656 |
| Full hierarchy: sector BULL required | -5.61% | -1.94% | -0.06% | +7.23% | +10.49% | 1.85% | -10.52% | 22.06% | 4.29x | $695 |
| Full hierarchy + Top-2 in SPY BEAR | -5.84% | -0.89% | -0.20% | +9.28% | +9.80% | 2.25% | -9.87% | 20.96% | 4.12x | $664 |

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
| 2023-02-28 | BEAR | Energy, Industrials | Energy | BULL |
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
