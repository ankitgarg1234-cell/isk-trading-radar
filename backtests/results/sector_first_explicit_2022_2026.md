# Explicit sector-first strategy (2022–Sep 2026), $100,000 initial capital

Independent new strategy; NOT the original frozen 75/25 engine or its replication. Using point-in-time historical constituent mappings and price-only stock criteria (no SEC fundamentals).

| Year | Return |
|---|---:|
| 2022 | -11.55% |
| 2023 | -6.89% |
| 2024 | +7.94% |
| 2025 | +28.43% |
| 2026 | +7.88% |

| Metric | Result |
|---|---:|
| CAGR | 4.49% |
| Max drawdown | -30.42% |
| Avg equity exposure | 80.28% |
| Ending NAV ($100,000) | $123,160.44 |
| Trades | 2444 |
| Costs | $14,748.63 |

## 2022 monthly sector decisions

| Date | SPY BULL | Sector allocation |
|---|---|---|
| 2022-01-31 | True | Energy: 70%, Financials: 30% |
| 2022-02-28 | False | Energy: 35%, Consumer Staples: 15% |
| 2022-03-31 | True | Energy: 70%, Utilities: 30% |
| 2022-04-29 | False | Energy: 35%, Consumer Staples: 15% |
| 2022-05-31 | False | Energy: 35%, Utilities: 15% |
| 2022-06-30 | False | Utilities: 40% |
| 2022-07-29 | False | Energy: 35%, Utilities: 15% |
| 2022-08-31 | False | Utilities: 40% |
| 2022-09-30 | False | Cash |
| 2022-10-31 | False | Energy: 50% |
| 2022-11-30 | True | Energy: 70%, Health Care: 30% |
| 2022-12-30 | False | Energy: 35%, Industrials: 15% |

## Execution and interpretation
- Monthly sector ranking is frozen between rebalances; daily SPY flips or active-sector permission failures can trigger next-open risk transitions.
- REENTRY events buy only vacant stock positions from available cash; they do not resize all existing holdings.
- Intraday trailing stops use the *previous day's* stop, with gap-open adjustment.
- In SPY BEAR with two qualifying sectors, allocation is capped at 50% and split 70/30 or 50/50 among Top-2.
- Sector breadth is strict >50%, resolving the 50% boundary overlap in favor of the original permission definition.
- Missing individual stock history contributes zero to the sector breadth numerator but remains in the historical constituent denominator; this is conservative and may understate bullish breadth.
- If either Top-2 sector momentum is non-positive, the 1.5x ratio is undefined; use a conservative 50/50 split.
- Financials are not special-cased; unlike prior reconstructed experiments, no SEC fundamental gate is applied.
- No guarantee of +16.4% in 2022: this is the mechanically executed strategy, not the manually authored monthly P&L path.
- Late-source PIT GICS classifications (>125 days old): 8 daily observations, latest dated snapshot carried forward without lookahead (lower confidence).
- Historical S&P membership and GICS source completeness, raw Yahoo corporate actions, and financing assumptions remain research-quality, not institutional-grade certified.
