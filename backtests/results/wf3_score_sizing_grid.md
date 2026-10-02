# WF3 Score Threshold × Sizing Grid

All fundamentals, R/R, entry-zone, liquidity, position-cap and exit rules are fixed. Only Core score floor and minimum target allocation vary.

| Score floor | Min alloc | Return | CAGR | Max DD | Avg cash | Buys | Core obs | R/R>=2 obs | Entry obs | Alpha vs S&P |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 68 | 8% | +19.94% | +6.85% | -10.07% | 76.2% | 7 | 179 | 122 | 23 | -47.49 pp |
| 68 | 10% | +24.18% | +8.20% | -11.44% | 72.9% | 7 | 179 | 122 | 23 | -43.25 pp |
| 68 | 12% | +29.60% | +9.90% | -13.85% | 66.9% | 7 | 179 | 122 | 23 | -37.83 pp |
| 66 | 8% | +19.94% | +6.85% | -10.07% | 76.2% | 7 | 179 | 122 | 23 | -47.49 pp |
| 66 | 10% | +24.18% | +8.20% | -11.44% | 72.9% | 7 | 179 | 122 | 23 | -43.25 pp |
| 66 | 12% | +29.60% | +9.90% | -13.85% | 66.9% | 7 | 179 | 122 | 23 | -37.83 pp |
| 64 | 8% | +19.94% | +6.85% | -10.07% | 76.2% | 7 | 179 | 122 | 23 | -47.49 pp |
| 64 | 10% | +24.18% | +8.20% | -11.44% | 72.9% | 7 | 179 | 122 | 23 | -43.25 pp |
| 64 | 12% | +29.60% | +9.90% | -13.85% | 66.9% | 7 | 179 | 122 | 23 | -37.83 pp |
| 62 | 8% | +19.94% | +6.85% | -10.07% | 76.2% | 7 | 179 | 122 | 23 | -47.49 pp |
| 62 | 10% | +24.18% | +8.20% | -11.44% | 72.9% | 7 | 179 | 122 | 23 | -43.25 pp |
| 62 | 12% | +29.60% | +9.90% | -13.85% | 66.9% | 7 | 179 | 122 | 23 | -37.83 pp |
| S&P 500 TR | — | +67.43% | +20.64% | -18.75% | — | — | — | — | — | — |

## Guardrails
- A higher backtest return alone is not sufficient to deploy a configuration.
- Configurations exceeding 15% max drawdown are flagged as outside the current risk target.
- This is still one historical window; any apparent winner must be validated out-of-sample before production changes.
