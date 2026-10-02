# WF3 Capital Deployment + Profit Harvesting Ablation

Stock selection and entry rules are identical across variants; only target allocation floor and harvesting differ.

| Variant | End value | Return | CAGR | Max DD | Avg cash | End cash | Buys | Sells | Alpha vs S&P |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Control — current sizing | USD 10,766 | +7.66% | +2.73% | -3.02% | 92.2% | 75.1% | 7 | 0 | -59.77 pp |
| 5% minimum initial | USD 11,305 | +13.05% | +4.57% | -6.74% | 83.7% | 58.0% | 7 | 0 | -54.38 pp |
| 8% minimum initial | USD 11,994 | +19.94% | +6.85% | -10.07% | 76.2% | 44.0% | 7 | 0 | -47.49 pp |
| 10% minimum initial | USD 12,418 | +24.18% | +8.20% | -11.44% | 72.9% | 37.8% | 7 | 0 | -43.25 pp |
| 5% minimum + harvest | USD 11,294 | +12.94% | +4.53% | -2.98% | 91.9% | 84.3% | 11 | 17 | -54.49 pp |
| 8% minimum + harvest | USD 11,750 | +17.50% | +6.05% | -6.06% | 87.1% | 78.8% | 10 | 16 | -49.93 pp |
| 10% minimum + harvest | USD 12,155 | +21.55% | +7.37% | -6.59% | 85.6% | 76.1% | 10 | 16 | -45.88 pp |
| S&P 500 Total Return | USD 16,743 | +67.43% | +20.64% | -18.75% | — | — | — | — | — |

## Notes
- Corrected split accounting is used throughout.
- Minimum-allocation floors can increase target size but never exceed the existing 15% position cap; stop-risk and cash ceilings remain active.
- Profit harvesting is tested as an overlay only; it is not deployed to production by this experiment.
- Historical analyst/news/strategic-capital archives remain omitted rather than backfilled with present-day data.
