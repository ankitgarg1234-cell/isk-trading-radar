# 2022 sector-rotation return bridge

This is a test of the **opportunity capture in sector ETFs**, not a replication of the 75/25 stock portfolio.
Monthly 63/126/252 total-return momentum, sector own EMA200 (continuous, SMA-200-seeded), invest equally in Top-K sectors that are positive and above trend. Next-session open execution, whole shares, $1 minimum commission, 7 bps adverse price adjustment on each side. December 2021 signal is invested on January 3, 2022. No stock fundamental gates, SPY veto, ATR stops or sector concentration caps.

| ETF sector strategy | 2022 return | Dec 2022 NAV on $10k | Transaction costs |
|---|---:|---:|---:|
| Top-1 BULL sectors | +24.33% | $12,432.68 | $206.73 |
| Top-2 BULL sectors | +9.89% | $10,988.69 | $202.31 |
| Top-3 BULL sectors | +19.85% | $11,984.61 | $231.29 |

## Monthly decisions, Top-2 sector ETFs

| Signal after close | Next-session open | Allocated sector ETFs |
|---|---|---|
| 2021-12-31 | 2022-01-03 | XLRE (Real Estate), XLK (Information Technology) |
| 2022-01-31 | 2022-02-01 | XLE (Energy), XLF (Financials) |
| 2022-02-28 | 2022-03-01 | XLE (Energy), XLP (Consumer Staples) |
| 2022-03-31 | 2022-04-01 | XLE (Energy), XLU (Utilities) |
| 2022-04-29 | 2022-05-02 | XLE (Energy), XLP (Consumer Staples) |
| 2022-05-31 | 2022-06-01 | XLE (Energy), XLU (Utilities) |
| 2022-06-30 | 2022-07-01 | XLE (Energy), XLU (Utilities) |
| 2022-07-29 | 2022-08-01 | XLE (Energy), XLU (Utilities) |
| 2022-08-31 | 2022-09-01 | XLE (Energy), XLU (Utilities) |
| 2022-09-30 | 2022-10-03 | XLE (Energy) |
| 2022-10-31 | 2022-11-01 | XLE (Energy), XLV (Health Care) |
| 2022-11-30 | 2022-12-01 | XLE (Energy), XLV (Health Care) |

## Interpretation

The previously quoted ~15.75% sector-ETF test had an initialization defect and rolling-window EMA200; do not treat that value as certified. This run corrects both and reports an ETF-only diagnostic.
Any stock-portfolio return such as +16.4% requires an explicit allocation/eligibility/exit specification and trade-level attribution; this test cannot establish that number.
