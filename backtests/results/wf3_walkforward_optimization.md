# WF3 Walk-Forward Optimization

**Selection uses only 2024-2025. 2026 is an untouched holdout.**

| Rank | Score floor | Entry | Min alloc | Idle cash in S&P | Train return | Train alpha | Train DD | 2026 return | 2026 S&P | 2026 alpha | 2026 DD | Trades |
|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 68 | current | 8% | 50% | +31.63% | -16.58 pp | -14.49% | +9.92% | +12.73% | -2.81 pp | -11.32% | 7 |
| 2 | 66 | current | 8% | 50% | +31.63% | -16.58 pp | -14.49% | +9.92% | +12.73% | -2.81 pp | -11.32% | 7 |
| 3 | 64 | current | 8% | 50% | +31.63% | -16.58 pp | -14.49% | +9.92% | +12.73% | -2.81 pp | -11.32% | 7 |
| 4 | 62 | current | 8% | 50% | +31.63% | -16.58 pp | -14.49% | +9.92% | +12.73% | -2.81 pp | -11.32% | 7 |
| 5 | 68 | current | 15% | 0% | +19.15% | -29.06 pp | -14.51% | +12.86% | +12.73% | +0.13 pp | -15.70% | 7 |
| 6 | 66 | current | 15% | 0% | +19.15% | -29.06 pp | -14.51% | +12.86% | +12.73% | +0.13 pp | -15.70% | 7 |
| 7 | 64 | current | 15% | 0% | +19.15% | -29.06 pp | -14.51% | +12.86% | +12.73% | +0.13 pp | -15.70% | 7 |
| 8 | 62 | current | 15% | 0% | +19.15% | -29.06 pp | -14.51% | +12.86% | +12.73% | +0.13 pp | -15.70% | 7 |
| 9 | 68 | current | 12% | 0% | +15.91% | -32.30 pp | -12.50% | +10.99% | +12.73% | -1.74 pp | -13.85% | 7 |
| 10 | 66 | current | 12% | 0% | +15.91% | -32.30 pp | -12.50% | +10.99% | +12.73% | -1.74 pp | -13.85% | 7 |
| 11 | 64 | current | 12% | 0% | +15.91% | -32.30 pp | -12.50% | +10.99% | +12.73% | -1.74 pp | -13.85% | 7 |
| 12 | 62 | current | 12% | 0% | +15.91% | -32.30 pp | -12.50% | +10.99% | +12.73% | -1.74 pp | -13.85% | 7 |

## Benchmark
- 2024-2025 S&P 500 Total Return: +48.21%
- 2026 holdout S&P 500 Total Return: +12.73%
- Full-period S&P 500 Total Return: +67.43%

## Guardrails
- R/R >=2x is fixed.
- Fundamental quality floor is fixed.
- Daily deep coverage is fixed at 160.
- Any training configuration with >15% drawdown is excluded before ranking.
- Profit-harvest overlay is off because the prior ablation reduced returns.
- Holdout performance is reported only after train ranking and does not influence selection.
- Qualified-any-zone is exploratory; it is not automatically a production recommendation even if it wins in-sample.
