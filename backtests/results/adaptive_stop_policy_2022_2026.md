# Adaptive stop-policy experiment - 2022-2026 research replay

This is an independent point-in-time research replay using the same reconstructed 75/25 architecture and data pipeline as the prior no-BEAR ablation. Absolute returns do not reproduce the earlier 19,808 artifact, so comparisons below are valid as within-replay ablations, not replacements for the frozen control.

Pre-registered controller thresholds:
- GREEN: SPY above EMA200 and healthy breadth >= 50%.
- NARROW_LEADERSHIP: SPY above EMA200, breadth < 50%, leadership health >= 40%.
- SYSTEMIC_BEAR: SPY below EMA200, healthy breadth < 35%, leadership health < 40%.
- CORRECTION: all other non-GREEN/non-NARROW states.
- Weekly RECOVERY: SPY back above EMA200 with breadth >= 40%, or positive 21-session SPY return with breadth >= 45%, leadership health >= 40%, and breadth at least 5 points above the defensive month-end.

| Variant | End value | 5Y return | CAGR | Max DD | 2022 | 2023 | 2024 | 2025 | 2026 | Avg exp. | Turnover | Costs | Recoveries |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| No-new-buys + 3x ATR | USD 10,875.20 | +8.75% | 1.69% | -15.01% | -4.75% | -4.26% | +5.88% | -0.81% | +13.56% | 40.75% | 7.44x | USD 1,217 | 0 |
| Adaptive systemic-only + 3x ATR | USD 10,978.88 | +9.79% | 1.89% | -15.05% | -4.75% | -4.31% | +5.88% | -0.03% | +13.80% | 40.23% | 7.33x | USD 1,204 | 0 |
| Adaptive systemic-only + 4x ATR | USD 11,355.60 | +13.56% | 2.58% | -15.19% | -5.98% | -1.72% | +13.28% | -1.17% | +9.78% | 47.60% | 6.44x | USD 1,090 | 0 |
| Adaptive systemic-only + 5x ATR | USD 12,190.34 | +21.90% | 4.04% | -15.42% | -6.59% | +2.42% | +16.05% | +1.18% | +8.52% | 52.30% | 5.66x | USD 985 | 0 |
| Adaptive systemic-only + monthly exits | USD 16,861.40 | +68.61% | 11.01% | -15.18% | -6.00% | +11.55% | +23.93% | +9.99% | +17.96% | 63.47% | 4.43x | USD 863 | 0 |
| Adaptive + leadership monthly exits | USD 11,257.62 | +12.58% | 2.40% | -14.87% | -5.07% | -2.87% | +9.53% | -0.56% | +12.10% | 44.12% | 6.66x | USD 1,111 | 0 |
| No-new-buys + monthly exits | USD 17,397.89 | +73.98% | 11.71% | -16.24% | -5.71% | +13.96% | +24.18% | +10.47% | +18.03% | 66.92% | 4.29x | USD 866 | 0 |

## 2023 monthly state classifications

### No-new-buys + 3x ATR

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

### Adaptive systemic-only + 3x ATR

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

### Adaptive systemic-only + 4x ATR

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

### Adaptive systemic-only + 5x ATR

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

### Adaptive systemic-only + monthly exits

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

### Adaptive + leadership monthly exits

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

### No-new-buys + monthly exits

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
