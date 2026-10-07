# Sector ETF momentum diagnostic

Monthly sector score = equal-weight average of 63/126/252-session total returns. Invest next session in top-K positive-momentum sectors; trend-filter variants also require sector ETF above its EMA200. Whole shares, 7 bps adverse fill per side, commission max($1,$0.005/share).

| Variant | 2022 | 2023 | 2024 | 2025 | 2026 | CAGR | Max DD | End value |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Top-1 positive + EMA200 | +31.13% | +12.77% | +4.12% | +6.24% | +1.38% | 11.26% | -26.93% | USD 16,584.33 |
| Top-2 positive + EMA200 | +15.75% | +18.02% | +12.91% | +8.96% | +15.79% | 15.08% | -17.80% | USD 19,458.50 |
| Top-3 positive + EMA200 | +15.80% | +16.16% | +13.62% | +6.33% | +18.99% | 14.93% | -17.65% | USD 19,336.82 |
| Top-1 positive momentum only | +31.13% | +12.77% | +4.12% | +6.24% | +1.38% | 11.26% | -26.93% | USD 16,584.33 |
| Top-2 positive momentum only | +15.75% | +18.02% | +12.91% | +8.96% | +15.79% | 15.08% | -17.80% | USD 19,458.50 |
| Top-3 positive momentum only | +15.86% | +12.09% | +13.64% | +6.38% | +18.99% | 14.10% | -17.66% | USD 18,681.36 |

## Monthly investable sector selections in 2022-2023 (Top-3 positive + EMA200)

| Signal date | Selected sectors | Top-ranked sector | Top sector score |
|---|---|---|---:|
| 2022-01-31 | Energy, Financials, Consumer Staples | Energy | +42.81% |
| 2022-02-28 | Energy, Consumer Staples, Utilities | Energy | +41.69% |
| 2022-03-31 | Energy, Utilities, Real Estate | Energy | +49.41% |
| 2022-04-29 | Energy, Consumer Staples, Utilities | Energy | +35.81% |
| 2022-05-31 | Energy, Utilities, Consumer Staples | Energy | +50.35% |
| 2022-06-30 | Energy, Utilities | Energy | +21.03% |
| 2022-07-29 | Energy, Utilities, Health Care | Energy | +29.20% |
| 2022-08-31 | Energy, Utilities | Energy | +26.14% |
| 2022-09-30 | Energy | Energy | +13.66% |
| 2022-10-31 | Energy, Health Care | Energy | +34.25% |
| 2022-11-30 | Energy, Health Care, Consumer Staples | Energy | +31.32% |
| 2022-12-30 | Energy, Industrials, Health Care | Energy | +36.79% |
| 2023-01-31 | Energy, Materials, Industrials | Energy | +21.38% |
| 2023-02-28 | Energy, Industrials, Materials | Energy | +7.26% |
| 2023-03-31 | Information Technology, Communication Services, Energy | Information Technology | +13.78% |
| 2023-04-28 | Information Technology, Communication Services, Consumer Staples | Information Technology | +12.88% |
| 2023-05-31 | Information Technology, Communication Services, Consumer Discretionary | Information Technology | +21.70% |
| 2023-06-30 | Information Technology, Consumer Discretionary, Communication Services | Information Technology | +32.36% |
| 2023-07-31 | Information Technology, Communication Services, Consumer Discretionary | Information Technology | +25.44% |
| 2023-08-31 | Information Technology, Communication Services, Consumer Discretionary | Information Technology | +21.51% |
| 2023-09-29 | Energy, Communication Services, Information Technology | Energy | +17.67% |
| 2023-10-31 | Communication Services, Information Technology | Communication Services | +13.35% |
| 2023-11-30 | Information Technology, Communication Services, Consumer Discretionary | Information Technology | +20.68% |
| 2023-12-29 | Information Technology, Communication Services, Consumer Discretionary | Information Technology | +29.58% |

## Hindsight ceiling: best next-month sector (NOT investable)

| Signal date | Best next-month sector | Next-month return |
|---|---|---:|
| 2022-01-31 | Energy | +7.07% |
| 2022-02-28 | Utilities | +10.34% |
| 2022-03-31 | Consumer Staples | +2.31% |
| 2022-04-29 | Energy | +16.03% |
| 2022-05-31 | Consumer Staples | -2.37% |
| 2022-06-30 | Consumer Discretionary | +18.44% |
| 2022-07-29 | Energy | +2.65% |
| 2022-08-31 | Health Care | -2.54% |
| 2022-09-30 | Energy | +24.97% |
| 2022-10-31 | Materials | +11.70% |
| 2022-11-30 | Utilities | -0.49% |
| 2022-12-30 | Consumer Discretionary | +15.13% |
| 2023-01-31 | Information Technology | +0.41% |
| 2023-02-28 | Information Technology | +10.86% |
| 2023-03-31 | Consumer Staples | +3.65% |
| 2023-04-28 | Information Technology | +8.92% |
| 2023-05-31 | Consumer Discretionary | +12.23% |
| 2023-06-30 | Energy | +7.77% |
| 2023-07-31 | Energy | +1.65% |
| 2023-08-31 | Energy | +2.40% |
| 2023-09-29 | Utilities | +1.29% |
| 2023-10-31 | Information Technology | +12.90% |
| 2023-11-30 | Real Estate | +8.75% |
