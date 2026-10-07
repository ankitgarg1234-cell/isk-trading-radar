# 75/25 leadership architecture — BEAR liquidation ablation

Research branch run. The only intended behavioral change between the two variants is the market-regime action:
- Control: BEAR liquidates all equity positions and blocks buys.
- No-new-buys: BEAR blocks new/additional buys but retains incumbents unless their own rank, momentum, leadership qualification, or ATR stop exits them.

| Metric | Frozen-rule control | No-new-buys in BEAR |
|---|---:|---:|
| Ending value | $10,550.92 | $10,612.54 |
| 5Y return | +5.51% | +6.13% |
| CAGR (same 5Y convention) | 1.08% | 1.20% |
| Actual elapsed CAGR | 1.14% | 1.26% |
| Max drawdown | -17.40% | -15.88% |
| 2022 | -6.04% | -4.75% |
| 2023 | -5.76% | -5.04% |
| 2024 | +5.12% | +5.33% |
| 2025 | +0.49% | -0.85% |
| 2026 Jan-Sep | +12.81% | +12.35% |
| Avg equity exposure | 39.01% | 40.23% |
| Annualized turnover | 7.51x | 7.39x |
| Costs | $1,207.69 | $1,203.07 |
| Trades | 960 | 956 |

## Validation against the previously reported control

Previously reported earlier-25%-leadership control: ending value $19,808.08, 5Y return +98.08%, CAGR 14.66%, max drawdown -33.85%, 2023 +2.91%.
This independent replay uses the public S&P constituent-change table, Yahoo historical prices/dividends, and SEC filing-timestamped annual revenue/gross-profit/share data. Any difference from the prior artifact is reported rather than calibrated away.

## 2023 leadership validation

Expected conceptual check from prior research: June/July 2023 should favor mega-cap trend-qualified names such as MSFT, AMZN, NVDA, TSLA and AVGO.

Control leadership log: {"2023-06-30": ["AAPL", "MSFT", "AMZN", "JPM", "ORCL"], "2023-07-31": ["AAPL", "MSFT", "AMZN", "JPM", "JNJ"]}

## Data/method notes

- Point-in-time S&P 500 membership is reconstructed from the public current-constituent and historical-changes tables.
- Momentum and the SPY regime use a dividend-reinvested total-return series reconstructed from split-adjusted Yahoo closes plus cash dividends.
- Fills use next-session opens with 7 bps adverse price drag per side plus max($1, $0.005/share) commission.
- Sizing is inverse percentage Wilder ATR14, with occupied-slot exposure preserved separately for the 15-slot rotational and 5-slot leadership sleeves.
- Fundamental PASS is approximated from filing-timestamped SEC annual revenue growth >=0 and positive gross profit, with Financials gross-profit-exempt. This is the largest potential source of mismatch versus the earlier experiment artifact.
- Whole shares only; no leverage; stopped-out cash waits until a later monthly cycle.
