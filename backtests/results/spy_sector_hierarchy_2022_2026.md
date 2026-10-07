# SPY + sector hierarchy backtest (2022-Sep 2026)

Pre-registered architecture test. Stock ranking, 75/25 sleeves, inverse-ATR sizing, 3x ATR stops, costs and monthly cadence are unchanged. The experiment changes only market/sector permission and replaces current-sector labels with dated point-in-time Wikipedia-revision GICS sector snapshots.

Sector BULL = sector ETF has positive 63/126/252 average total-return momentum and is above its own EMA200. SPY BULL/BEAR is evaluated independently. In the Bear-exception variants, SPY BULL leaves the frozen engine unchanged; only SPY BEAR can admit stocks from BULL sectors.

| Variant | 2022 | 2023 | 2024 | 2025 | 2026 | CAGR | Max DD | Avg exposure | Turnover | Costs |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| PIT frozen-like control | -6.06% | -4.97% | +7.70% | +0.18% | +13.83% | 1.86% | -16.08% | 40.04% | 7.55x | $1,214 |
| Bear exception: all BULL sectors | -9.10% | +1.79% | +4.57% | -2.61% | +3.48% | -0.50% | -17.73% | 43.98% | 8.37x | $1,347 |
| Bear exception: Top-3 BULL sectors | -6.82% | +2.88% | +4.85% | -3.13% | +9.47% | 1.28% | -14.77% | 43.34% | 8.22x | $1,336 |
| Bear exception: Top-2 BULL sectors | -6.92% | +2.70% | +4.78% | -0.56% | +9.82% | 1.81% | -14.96% | 42.72% | 8.08x | $1,312 |
| Bear exception: Top-1 BULL sector | -5.15% | -3.60% | +5.50% | -0.77% | +9.75% | 0.99% | -14.09% | 40.60% | 7.79x | $1,249 |
| Full hierarchy: sector BULL required | -10.06% | +1.80% | +5.36% | -1.20% | +3.15% | -0.34% | -18.57% | 43.06% | 8.32x | $1,322 |
| Full hierarchy + Top-2 in SPY BEAR | -7.98% | +2.78% | +4.88% | +0.22% | +9.60% | 1.73% | -15.98% | 41.18% | 7.98x | $1,286 |

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
