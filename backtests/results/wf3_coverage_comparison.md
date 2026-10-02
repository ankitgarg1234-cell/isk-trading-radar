# WF3 Scanner Coverage / Core-Gate Ablation

All strategy rules are fixed; only the number of stocks receiving daily deep analysis changes.

| Deep coverage | Avg analyzed/day | Fundamental pass | Score>=68 after fundamentals | Lane qualified | Lane + R/R>=2x | Investable entries | Return | CAGR | Max DD | Trades | Alpha vs S&P |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 80 | 79.9 | 8728 (15.83%) | 104 (1.19% of prior) | 104 | 63 | 6 | +3.75% | +1.35% | -1.06% | 3 | -63.68 pp |
| 160 | 159.8 | 13522 (12.26%) | 181 (1.34% of prior) | 179 | 122 | 23 | +36.07% | +11.87% | -9.34% | 7 | -31.36 pp |
| all | 493.5 | 27715 (8.14%) | 249 (0.90% of prior) | 247 | 178 | 42 | +33.46% | +11.08% | -11.79% | 15 | -33.97 pp |

S&P 500 Total Return: +67.43% total, +20.64% CAGR, -18.75% max drawdown.

## Top Core blockers by coverage

### Deep 80
- system conviction < 68: 55029
- fundamental score < 14/20: 46409
- market-cap evidence unavailable: 6932
- fundamental evidence confidence low: 3166
- promotion / reverse-split hard reject: 35
- market cap < $500M: 27

### Deep 160
- system conviction < 68: 110090
- fundamental score < 14/20: 96757
- market-cap evidence unavailable: 13653
- fundamental evidence confidence low: 7324
- promotion / reverse-split hard reject: 89
- market cap < $500M: 41

### Deep all
- system conviction < 68: 340248
- fundamental score < 14/20: 312795
- market-cap evidence unavailable: 43927
- fundamental evidence confidence low: 30651
- promotion / reverse-split hard reject: 592
- market cap < $500M: 167
- 20d dollar liquidity < $10M: 129

## Interpretation
- If opportunity counts and returns improve materially from 80 to 160/all, discovery coverage is a major bottleneck.
- If deep analyses rise sharply but lane/RR/entry counts barely move, the qualification/entry gates are the dominant bottleneck.
- No thresholds are changed in this experiment.
