# Adaptive entry-policy experiment - 2022-2026 research replay

This is an independent point-in-time research replay using the same reconstructed 75/25 architecture and data pipeline as the prior no-BEAR ablation. Absolute returns do not reproduce the earlier 19,808 artifact, so comparisons below are valid as within-replay ablations, not replacements for the frozen control.

Pre-registered controller thresholds:
- GREEN: SPY above EMA200 and healthy breadth >= 50%.
- NARROW_LEADERSHIP: SPY above EMA200, breadth < 50%, leadership health >= 40%.
- SYSTEMIC_BEAR: SPY below EMA200, healthy breadth < 35%, leadership health < 40%.
- CORRECTION: all other non-GREEN/non-NARROW states.
- Weekly RECOVERY: SPY back above EMA200 with breadth >= 40%, or positive 21-session SPY return with breadth >= 45%, leadership health >= 40%, and breadth at least 5 points above the defensive month-end.

| Variant | End value | 5Y return | CAGR | Max DD | 2022 | 2023 | 2024 | 2025 | 2026 | Avg exp. | Turnover | Costs | Recoveries |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| SPY gate + monthly exits | USD 17,397.89 | +73.98% | 11.71% | -16.24% | -5.71% | +13.96% | +24.18% | +10.47% | +18.03% | 66.92% | 4.29x | USD 866 | 0 |
| Adaptive: correction leadership-only | USD 17,069.82 | +70.70% | 11.29% | -15.30% | -5.77% | +11.82% | +23.94% | +11.20% | +17.55% | 66.74% | 4.30x | USD 864 | 0 |
| Adaptive: correction leadership + Top5 rot | USD 17,857.81 | +78.58% | 12.30% | -16.20% | -5.81% | +14.55% | +24.00% | +11.01% | +20.24% | 68.60% | 4.39x | USD 896 | 0 |
| Adaptive: correction leadership + Top10 rot | USD 17,860.46 | +78.60% | 12.30% | -16.16% | -6.01% | +13.46% | +25.82% | +11.60% | +19.28% | 71.00% | 4.49x | USD 919 | 0 |
| Adaptive: correction leadership + Top20 rot | USD 17,811.04 | +78.11% | 12.24% | -16.19% | -6.93% | +15.09% | +25.93% | +11.39% | +18.54% | 71.28% | 4.49x | USD 916 | 0 |

## 2023 monthly state classifications

### SPY gate + monthly exits

| Month-end | State | SPY>EMA200 | Breadth | Leader health |
|---|---|---:|---:|---:|
| 2023-01-31 | GREEN | Yes | 54.0% | 40.0% |
| 2023-02-28 | CORRECTION | Yes | 42.1% | 26.7% |
| 2023-03-31 | GREEN | Yes | 55.5% | 60.0% |
| 2023-04-28 | GREEN | Yes | 50.1% | 66.7% |
| 2023-05-31 | NARROW_LEADERSHIP | Yes | 30.4% | 46.7% |
| 2023-06-30 | GREEN | Yes | 58.6% | 73.3% |
| 2023-07-31 | GREEN | Yes | 54.9% | 86.7% |
| 2023-08-31 | NARROW_LEADERSHIP | Yes | 49.3% | 80.0% |
| 2023-09-29 | NARROW_LEADERSHIP | Yes | 37.1% | 73.3% |
| 2023-10-31 | CORRECTION | No | 25.3% | 40.0% |
| 2023-11-30 | GREEN | Yes | 55.9% | 80.0% |
| 2023-12-29 | GREEN | Yes | 65.5% | 53.3% |

### Adaptive: correction leadership-only

| Month-end | State | SPY>EMA200 | Breadth | Leader health |
|---|---|---:|---:|---:|
| 2023-01-31 | GREEN | Yes | 54.0% | 40.0% |
| 2023-02-28 | CORRECTION | Yes | 42.1% | 26.7% |
| 2023-03-31 | GREEN | Yes | 55.5% | 60.0% |
| 2023-04-28 | GREEN | Yes | 50.1% | 66.7% |
| 2023-05-31 | NARROW_LEADERSHIP | Yes | 30.4% | 46.7% |
| 2023-06-30 | GREEN | Yes | 58.6% | 73.3% |
| 2023-07-31 | GREEN | Yes | 54.9% | 86.7% |
| 2023-08-31 | NARROW_LEADERSHIP | Yes | 49.3% | 80.0% |
| 2023-09-29 | NARROW_LEADERSHIP | Yes | 37.1% | 73.3% |
| 2023-10-31 | CORRECTION | No | 25.3% | 40.0% |
| 2023-11-30 | GREEN | Yes | 55.9% | 80.0% |
| 2023-12-29 | GREEN | Yes | 65.5% | 53.3% |

### Adaptive: correction leadership + Top5 rot

| Month-end | State | SPY>EMA200 | Breadth | Leader health |
|---|---|---:|---:|---:|
| 2023-01-31 | GREEN | Yes | 54.0% | 40.0% |
| 2023-02-28 | CORRECTION | Yes | 42.1% | 26.7% |
| 2023-03-31 | GREEN | Yes | 55.5% | 60.0% |
| 2023-04-28 | GREEN | Yes | 50.1% | 66.7% |
| 2023-05-31 | NARROW_LEADERSHIP | Yes | 30.4% | 46.7% |
| 2023-06-30 | GREEN | Yes | 58.6% | 73.3% |
| 2023-07-31 | GREEN | Yes | 54.9% | 86.7% |
| 2023-08-31 | NARROW_LEADERSHIP | Yes | 49.3% | 80.0% |
| 2023-09-29 | NARROW_LEADERSHIP | Yes | 37.1% | 73.3% |
| 2023-10-31 | CORRECTION | No | 25.3% | 40.0% |
| 2023-11-30 | GREEN | Yes | 55.9% | 80.0% |
| 2023-12-29 | GREEN | Yes | 65.5% | 53.3% |

### Adaptive: correction leadership + Top10 rot

| Month-end | State | SPY>EMA200 | Breadth | Leader health |
|---|---|---:|---:|---:|
| 2023-01-31 | GREEN | Yes | 54.0% | 40.0% |
| 2023-02-28 | CORRECTION | Yes | 42.1% | 26.7% |
| 2023-03-31 | GREEN | Yes | 55.5% | 60.0% |
| 2023-04-28 | GREEN | Yes | 50.1% | 66.7% |
| 2023-05-31 | NARROW_LEADERSHIP | Yes | 30.4% | 46.7% |
| 2023-06-30 | GREEN | Yes | 58.6% | 73.3% |
| 2023-07-31 | GREEN | Yes | 54.9% | 86.7% |
| 2023-08-31 | NARROW_LEADERSHIP | Yes | 49.3% | 80.0% |
| 2023-09-29 | NARROW_LEADERSHIP | Yes | 37.1% | 73.3% |
| 2023-10-31 | CORRECTION | No | 25.3% | 40.0% |
| 2023-11-30 | GREEN | Yes | 55.9% | 80.0% |
| 2023-12-29 | GREEN | Yes | 65.5% | 53.3% |

### Adaptive: correction leadership + Top20 rot

| Month-end | State | SPY>EMA200 | Breadth | Leader health |
|---|---|---:|---:|---:|
| 2023-01-31 | GREEN | Yes | 54.0% | 40.0% |
| 2023-02-28 | CORRECTION | Yes | 42.1% | 26.7% |
| 2023-03-31 | GREEN | Yes | 55.5% | 60.0% |
| 2023-04-28 | GREEN | Yes | 50.1% | 66.7% |
| 2023-05-31 | NARROW_LEADERSHIP | Yes | 30.4% | 46.7% |
| 2023-06-30 | GREEN | Yes | 58.6% | 73.3% |
| 2023-07-31 | GREEN | Yes | 54.9% | 86.7% |
| 2023-08-31 | NARROW_LEADERSHIP | Yes | 49.3% | 80.0% |
| 2023-09-29 | NARROW_LEADERSHIP | Yes | 37.1% | 73.3% |
| 2023-10-31 | CORRECTION | No | 25.3% | 40.0% |
| 2023-11-30 | GREEN | Yes | 55.9% | 80.0% |
| 2023-12-29 | GREEN | Yes | 65.5% | 53.3% |

## Interpretation discipline

- The earlier frozen 75/25 artifact reported USD 19,808.08 ending value, 14.66% CAGR, -33.85% max drawdown and +2.91% in 2023. This replay does not replicate it because its public-data fundamental/share reconstruction differs materially.
- Therefore choose among adaptive variants only on relative changes inside this replay, then confirm the winning controller against the original frozen artifact before production use.
