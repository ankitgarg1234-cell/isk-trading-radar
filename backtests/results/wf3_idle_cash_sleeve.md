# WF3 Idle-Cash S&P Sleeve Walk-Forward

The stock model is fixed at score>=68, 12% minimum initial allocation and 160-name deep coverage.

| Idle cash swept to S&P | Train return | Train DD | 2026 return | 2026 DD | Full return |
|---:|---:|---:|---:|---:|---:|
| 0% | +15.63% | -12.50% | +22.25% | -15.33% | +42.04% |
| 50% | +35.35% | -17.91% | +24.31% | -16.21% | +69.17% |
| 75% | +46.73% | -20.79% | +24.54% | -16.72% | +83.80% |
| 100% | +57.13% | -23.27% | +26.09% | -17.62% | +99.10% |

Train S&P: +48.21% / DD -18.75%
2026 S&P: +12.73% / DD -8.89%

Selected on train under 15% DD: **score>=68/min12/sleeve0**
2026 validation: +22.25% vs S&P +12.73%.

This sleeve is a diagnostic. It is not deployed to production and assumes frictionless daily rebalancing of the idle-cash sleeve.
