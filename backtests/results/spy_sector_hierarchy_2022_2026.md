# SPY + sector hierarchy backtest (2022-Sep 2026)

Corrected research replay: December warm-start, raw momentum rank before fundamental filter, strict point-in-time filing cutoffs, missing-snapshot exits, verified historical sector snapshots. The experiment changes only market/sector permission; sizing and 3x ATR are otherwise unchanged.

Sector BULL = sector ETF has positive 63/126/252 average total-return momentum and is above its own EMA200. SPY BULL/BEAR is evaluated independently. In the Bear-exception variants, SPY BULL leaves the frozen engine unchanged; only SPY BEAR can admit stocks from BULL sectors.

| Variant | 2022 | 2023 | 2024 | 2025 | 2026 | CAGR | Max DD | Avg exposure | Turnover | Costs |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| PIT frozen-like control | -6.89% | -3.67% | +3.40% | +9.22% | +8.83% | 1.97% | -12.29% | 23.37% | 4.70x | $759 |
| Bear exception: all BULL sectors | -6.95% | -1.44% | +2.22% | +8.27% | +9.83% | 2.20% | -11.56% | 24.31% | 4.75x | $773 |
| Bear exception: Top-3 BULL sectors | -7.88% | -0.72% | +2.23% | +9.27% | +9.76% | 2.32% | -11.81% | 23.80% | 4.69x | $758 |
| Bear exception: Top-2 BULL sectors | -7.63% | +0.22% | +2.19% | +9.33% | +9.40% | 2.50% | -10.86% | 23.23% | 4.59x | $744 |
| Bear exception: Top-1 BULL sector | -6.89% | -2.32% | +1.03% | +8.33% | +10.45% | 1.91% | -11.25% | 22.53% | 4.46x | $717 |
| Full hierarchy: sector BULL required | -6.78% | -0.47% | +2.19% | +8.50% | +9.73% | 2.45% | -10.53% | 23.54% | 4.58x | $748 |
| Full hierarchy + Top-2 in SPY BEAR | -7.46% | +1.01% | +2.03% | +9.26% | +9.13% | 2.60% | -9.94% | 22.56% | 4.49x | $726 |

## Independent stock-eligibility diagnostics

This table isolates the pipeline before allocation and trading. A strong raw rank cannot become a position if fundamental PASS or leadership market cap fails. The raw-ranked universe still depends on price coverage.

| Year | Median priced stock count | Median Top-20 fundamental PASS | Median Top-20 unresolved | Median qualified leadership count |
|---|---:|---:|---:|---:|
| 2022 | 459 | 4.5 | 12.0 | 0.5 |
| 2023 | 474 | 8.0 | 9.5 | 4.0 |
| 2024 | 480 | 6.0 | 7.0 | 4.0 |
| 2025 | 488 | 8.5 | 7.0 | 5.0 |
| 2026 | 496 | 10.0 | 5.5 | 3.0 |

## Leadership diagnostic samples

| Date | Top-15 inferred-cap companies | Actual selected leadership names |
|---|---|---|
| 2022-05-31 | AAPL, MSFT, AMZN, TSLA, JNJ, NVDA, UNH, XOM, JPM, PG, WMT, CVX, HD, CTVA, BAC | JNJ |
| 2023-05-31 | AAPL, MSFT, AMZN, NVDA, META, TSLA, UNH, XOM, LLY, JNJ, JPM, WMT, AVGO, PG, ORCL | AAPL, MSFT, AMZN, NVDA, AVGO |
| 2023-06-30 | AAPL, MSFT, AMZN, NVDA, TSLA, META, UNH, LLY, XOM, JNJ, JPM, WMT, AVGO, PG, ORCL | AAPL, MSFT, AMZN, NVDA, AVGO |
| 2023-07-31 | AAPL, MSFT, AMZN, NVDA, TSLA, META, UNH, JPM, JNJ, XOM, LLY, WMT, AVGO, PG, HD | AAPL, MSFT, AMZN, NVDA, JPM |
| 2024-06-28 | MSFT, AAPL, NVDA, AMZN, META, LLY, AVGO, TSLA, JPM, WMT, UNH, XOM, PG, ORCL, COST | MSFT, NVDA, AMZN, AVGO, JPM |
| 2025-06-30 | NVDA, MSFT, AAPL, AMZN, GOOG, GOOGL, META, AVGO, TSLA, JPM, WMT, LLY, ORCL, NFLX, XOM | NVDA, AVGO, JPM, ORCL, NFLX |
| 2026-06-30 | NVDA, GOOGL, GOOG, AAPL, MSFT, AMZN, AVGO, TSLA, META, MU, LLY, AMD, WMT, JPM, INTC | MU, AMD, JNJ |

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
