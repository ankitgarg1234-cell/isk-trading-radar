# 2024–2026 Daily Point-in-Time Walk-Forward Backtest

Period: 2024-01-02 to 2026-10-01

| Variant | End value | Total return | CAGR | Max DD | Trades | Win rate | Alpha vs S&P |
|---|---:|---:|---:|---:|---:|---:|---:|
| Current model (R/R >=2x) | USD 10,375 | +3.8% | +1.4% | -1.1% | 3 | — | -63.7 pp |
| No 2x R/R floor | USD 10,473 | +4.7% | +1.7% | -2.3% | 5 | — | -62.7 pp |
| Core-only (R/R >=2x) | USD 10,375 | +3.8% | +1.4% | -1.1% | 3 | — | -63.7 pp |
| S&P 500 Total Return | USD 16,743 | +67.4% | +20.6% | -18.8% | — | — | — |

## Annual returns

| Variant | 2024 | 2025 | 2026 |
|---|---:|---:|---:|
| Current model (R/R >=2x) | +0.0% | +1.2% | +2.5% |
| No 2x R/R floor | +0.0% | +1.1% | +3.6% |
| Core-only (R/R >=2x) | +0.0% | +1.2% | +2.5% |
| S&P 500 Total Return | +25.7% | +17.9% | +13.0% |

## Run diagnostics
- Deep analyses: 55204
- Lane-qualified observations: 104
- Lane-qualified with R/R >=2x: 63
- Actionable lane-qualified R/R >=2x observations: 5

## Important limitations
- This is an S&P 500 historical-universe proxy, not the production scanner's full 5,000+ US-equity universe.
- Point-in-time fundamentals are filing-date gated. Historical analyst consensus, general news, and strategic-capital archives are omitted; SEC earnings filings are a conservative catalyst proxy.
- The live system scans intraday; daily-close decisions are materially closer than the earlier weekly replay but can still miss intraday setups.
- Whole shares, current score sizing, 15% position cap, 10 bps costs, Core/Explosive gates and R/R >=2x buy/add rule are enforced.
- Historical simulation is not a guarantee of future performance.
