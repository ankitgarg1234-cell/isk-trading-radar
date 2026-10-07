# Sector-first stock backtest

Reconstructed 75/25 stock engine with the same stock momentum, inverse-ATR sizing, 3x ATR stops, whole-share/cost assumptions and point-in-time S&P membership as the research replay. Sector leadership is measured from the 11 SPDR sector ETFs using the same 63/126/252 total-return momentum. New entries require a top-K positive-momentum sector above EMA200; incumbents get one extra sector rank of retention.

| Variant | 2022 | 2023 | 2024 | 2025 | 2026 | CAGR | Max DD | Avg exposure | Turnover |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Sector Top-2 + SPY gate | -2.28% | -0.37% | -4.47% | -0.87% | +10.61% | 0.40% | -14.91% | 21.97% | 4.38x |
| Sector Top-2, no SPY gate | -3.43% | +5.67% | -3.92% | -2.98% | +12.23% | 1.32% | -12.16% | 25.63% | 5.07x |
| Sector Top-3, no SPY gate | -2.34% | +4.22% | -5.98% | -6.78% | +9.85% | -0.40% | -17.65% | 30.20% | 6.07x |
| Sector Top-1, no SPY gate | +1.00% | +1.88% | -1.80% | +1.77% | +1.31% | 0.82% | -10.82% | 18.22% | 3.57x |

## 2022-2023 sector choices: Top-2 no SPY gate

| Month-end | Entry sectors | Top sector | Top sector momentum |
|---|---|---|---:|
| 2022-01-31 | Energy, Financials | Energy | +42.81% |
| 2022-02-28 | Consumer Staples, Energy | Energy | +41.69% |
| 2022-03-31 | Energy, Utilities | Energy | +49.41% |
| 2022-04-29 | Consumer Staples, Energy | Energy | +35.81% |
| 2022-05-31 | Energy, Utilities | Energy | +50.35% |
| 2022-06-30 | Energy, Utilities | Energy | +21.03% |
| 2022-07-29 | Energy, Utilities | Energy | +29.20% |
| 2022-08-31 | Energy, Utilities | Energy | +26.14% |
| 2022-09-30 | Energy | Energy | +13.66% |
| 2022-10-31 | Energy, Health Care | Energy | +34.25% |
| 2022-11-30 | Energy, Health Care | Energy | +31.32% |
| 2022-12-30 | Energy, Industrials | Energy | +36.79% |
| 2023-01-31 | Energy, Materials | Energy | +21.38% |
| 2023-02-28 | Energy, Industrials | Energy | +7.26% |
| 2023-03-31 | Communication Services, Information Technology | Information Technology | +13.78% |
| 2023-04-28 | Communication Services, Information Technology | Information Technology | +12.88% |
| 2023-05-31 | Communication Services, Information Technology | Information Technology | +21.70% |
| 2023-06-30 | Consumer Discretionary, Information Technology | Information Technology | +32.36% |
| 2023-07-31 | Communication Services, Information Technology | Information Technology | +25.44% |
| 2023-08-31 | Communication Services, Information Technology | Information Technology | +21.51% |
| 2023-09-29 | Communication Services, Energy | Energy | +17.67% |
| 2023-10-31 | Communication Services, Information Technology | Communication Services | +13.35% |
| 2023-11-30 | Communication Services, Information Technology | Information Technology | +20.68% |
| 2023-12-29 | Communication Services, Information Technology | Information Technology | +29.58% |

## Limitation

- This is still the independent reconstruction, not the exact frozen $19,808 artifact. Use the result for causal A/B evidence only.
- Historical S&P membership is reconstructed point-in-time, but sector labels come from the current GICS mapping and therefore do not reconstruct every historical reclassification.
