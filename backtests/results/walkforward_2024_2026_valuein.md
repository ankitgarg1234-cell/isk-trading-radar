# 2024–2026 Point-in-Time Walk-Forward Backtest

Period: 2024-01-05 to 2026-10-01  
Starting capital: USD 10,000  
Deterministic run hash: 1c11dc6fc962ea806fc4b40f3d6b2a66ac92601ecd44aba66b9dd2c2ff2a9cd6

| Variant | End value | Total return | CAGR | Max DD | Trades | Win rate | Alpha vs S&P |
|---|---:|---:|---:|---:|---:|---:|---:|
| Current model (R/R >=2x) | USD 10,000 | +0.0% | +0.0% | 0.0% | 0 | — | -69.0 pp |
| No 2x R/R floor | USD 10,095 | +0.9% | +0.3% | -0.9% | 1 | — | -68.1 pp |
| Core-only (R/R >=2x) | USD 10,000 | +0.0% | +0.0% | 0.0% | 0 | — | -69.0 pp |
| S&P 500 Total Return | USD 16,902 | +69.0% | +21.1% | -18.8% | — | — | — |

## Annual returns

| Variant | 2024 | 2025 | 2026 |
|---|---:|---:|---:|
| Current model (R/R >=2x) | +0.0% | +0.0% | +0.0% |
| No 2x R/R floor | +0.0% | +0.1% | +0.9% |
| Core-only (R/R >=2x) | +0.0% | +0.0% | +0.0% |
| S&P 500 Total Return | +26.9% | +17.9% | +13.0% |

## Data / integrity notes
- Historical price coverage: 97.12% of the reconstructed 2024–2026 S&P universe.
- PIT fundamental coverage: 88.49% of scanner candidate symbols.
- Fundamental facts are admitted only when filing_date <= decision date; no current analyst consensus or current fundamentals are backfilled into historical dates.
- Historical general-news and strategic-capital archives are omitted; 10-K/10-Q filing dates serve only as a conservative earnings-catalyst proxy.
- The full historical S&P universe is cheap-screened weekly; up to 80 scanner-style candidates plus current holdings receive deep analysis.
- Signals are generated at weekly close and orders execute at the next available session open.
- Whole shares, current score-based sizing, 15% hard position cap, 10 bps transaction costs, Core/Explosive lane gates and R/R >=2x buy/add floor are applied.
- Existing holdings are not sold merely because R/R later falls below 2x.
- Sector ETF mapping uses the cached sector classification available in the historical-universe build; sector reclassifications are a minor residual limitation.
- Historical simulation is not a guarantee of future performance.
