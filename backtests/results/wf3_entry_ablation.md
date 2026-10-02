# WF3 Entry-Timing Ablation

All variants keep the same PIT data, lane qualification, R/R >=2x, score gates, sizing, costs and thesis-gated exit rule.

| Variant | End value | Return | CAGR | Max DD | Buys | Sells | Entry opportunities | Alpha vs S&P |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Control — current zones | USD 10,375 | +3.8% | +1.4% | -1.1% | 3 | 0 | 6 | -63.7 pp |
| + Breakout | USD 10,375 | +3.8% | +1.4% | -1.1% | 3 | 0 | 6 | -63.7 pp |
| + Value corridor | USD 10,322 | +3.2% | +1.2% | -1.0% | 4 | 0 | 7 | -64.2 pp |
| + Breakout + value corridor | USD 10,322 | +3.2% | +1.2% | -1.0% | 4 | 0 | 7 | -64.2 pp |
| + Near-breakout confirmation | USD 10,183 | +1.8% | +0.7% | -6.0% | 11 | 0 | 17 | -65.6 pp |
| Zone-free diagnostic ceiling | USD 12,440 | +24.4% | +8.3% | -8.2% | 21 | 0 | 63 | -43.0 pp |
| S&P 500 Total Return | USD 16,743 | +67.4% | +20.6% | -18.8% | — | — | — | — |

## Interpretation guide
- Control is the current PRIMARY_BUY / BETTER_BUY entry policy.
- + Breakout adds only the existing production BREAKOUT rule: relative volume >=1.5x and deterministic score >=75.
- + Value corridor adds a starter entry only at score >=68 and only when the falling-risk test is false.
- + Near-breakout adds a starter only within 2% of breakout, score >=70, above EMA20, positive 20-day momentum, RSI 45-75.
- Zone-free diagnostic ceiling is not a proposed strategy. It shows the maximum participation effect of removing entry-zone timing while retaining qualification/RR/score safety gates.
- Historical analyst consensus, broad news and strategic-capital archives remain unavailable and are not backfilled.
