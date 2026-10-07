# Adaptive market-state controller - 2022-2026 research replay

This is an independent point-in-time research replay using the same reconstructed 75/25 architecture and data pipeline as the prior no-BEAR ablation. Absolute returns do not reproduce the earlier 19,808 artifact, so comparisons below are valid as within-replay ablations, not replacements for the frozen control.

Pre-registered controller thresholds:
- GREEN: SPY above EMA200 and healthy breadth >= 50%.
- NARROW_LEADERSHIP: SPY above EMA200, breadth < 50%, leadership health >= 40%.
- SYSTEMIC_BEAR: SPY below EMA200, healthy breadth < 35%, leadership health < 40%.
- CORRECTION: all other non-GREEN/non-NARROW states.
- Weekly RECOVERY: SPY back above EMA200 with breadth >= 40%, or positive 21-session SPY return with breadth >= 45%, leadership health >= 40%, and breadth at least 5 points above the defensive month-end.

| Variant | End value | 5Y return | CAGR | Max DD | 2022 | 2023 | 2024 | 2025 | 2026 | Avg exp. | Turnover | Costs | Recoveries |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Control: full BEAR liquidation | USD 10,612.40 | +6.12% | 1.20% | -16.62% | -6.04% | -4.97% | +6.09% | -0.28% | +12.35% | 39.60% | 7.56x | USD 1,212 | 0 |
| No-new-buys in BEAR | USD 10,875.20 | +8.75% | 1.69% | -15.01% | -4.75% | -4.26% | +5.88% | -0.81% | +13.56% | 40.75% | 7.44x | USD 1,217 | 0 |
| Adaptive: systemic-only liquidation | USD 10,978.88 | +9.79% | 1.89% | -15.05% | -4.75% | -4.31% | +5.88% | -0.03% | +13.80% | 40.23% | 7.33x | USD 1,204 | 0 |
| Adaptive: systemic survivor 50% | USD 10,892.22 | +8.92% | 1.72% | -15.05% | -4.75% | -4.31% | +5.88% | -0.59% | +13.53% | 40.16% | 7.33x | USD 1,202 | 0 |
| Adaptive + weekly recovery | USD 11,495.83 | +14.96% | 2.83% | -15.05% | -1.87% | -5.92% | +5.66% | +0.34% | +17.45% | 42.92% | 7.59x | USD 1,267 | 7 |
| Full adaptive + narrow leadership tilt | USD 11,200.65 | +12.01% | 2.29% | -15.95% | -2.81% | -5.31% | +4.02% | +2.99% | +13.61% | 42.32% | 7.70x | USD 1,302 | 7 |

## 2023 monthly state classifications

### Control: full BEAR liquidation

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

### No-new-buys in BEAR

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

### Adaptive: systemic-only liquidation

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

### Adaptive: systemic survivor 50%

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

### Adaptive + weekly recovery

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

### Full adaptive + narrow leadership tilt

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
