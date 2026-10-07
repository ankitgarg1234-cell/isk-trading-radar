# Regime-policy matrix - 2022-2026 research replay

This is an independent point-in-time research replay using the same reconstructed 75/25 architecture and data pipeline as the prior no-BEAR ablation. Absolute returns do not reproduce the earlier 19,808 artifact, so comparisons below are valid as within-replay ablations, not replacements for the frozen control.

Controller inputs: SPY trend, point-in-time constituent breadth, health of the 15 most liquid S&P names, and SPY-vs-RSP 63-session concentration gap. Policy multipliers alter deployment by detected state.
- GREEN: SPY above EMA200 and healthy breadth >= 50%.
- NARROW_LEADERSHIP: SPY above EMA200, breadth < 50%, leadership health >= 40%.
- SYSTEMIC_BEAR: SPY below EMA200, healthy breadth < 35%, leadership health < 40%.
- CORRECTION: all other non-GREEN/non-NARROW states.
- Weekly RECOVERY: SPY back above EMA200 with breadth >= 40%, or positive 21-session SPY return with breadth >= 45%, leadership health >= 40%, and breadth at least 5 points above the defensive month-end.

| Variant | End value | 5Y return | CAGR | Max DD | 2022 | 2023 | 2024 | 2025 | 2026 | Avg exp. | Turnover | Costs | Recoveries |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| SPY gate + monthly exits | USD 17,397.89 | +73.98% | 11.71% | -16.24% | -5.71% | +13.96% | +24.18% | +10.47% | +18.03% | 66.92% | 4.29x | USD 866 | 0 |
| Matrix Conservative | USD 17,058.66 | +70.59% | 11.27% | -14.24% | -6.26% | +14.38% | +25.05% | +8.56% | +17.21% | 60.74% | 4.60x | USD 906 | 0 |
| Matrix Balanced | USD 17,634.69 | +76.35% | 12.01% | -14.38% | -5.98% | +15.34% | +25.03% | +8.56% | +19.80% | 62.38% | 4.70x | USD 916 | 0 |
| Matrix Growth | USD 17,538.08 | +75.38% | 11.89% | -14.52% | -6.89% | +14.69% | +24.98% | +9.63% | +19.86% | 63.60% | 4.74x | USD 928 | 0 |

## 2023 monthly state classifications

### SPY gate + monthly exits

| Month-end | State | SPY>EMA200 | Breadth | Leader health |
|---|---|---:|---:|---:|
| 2023-01-31 | GREEN | Yes | 54.0% | 33.3% |
| 2023-02-28 | CORRECTION | Yes | 42.1% | 33.3% |
| 2023-03-31 | GREEN | Yes | 55.5% | 60.0% |
| 2023-04-28 | NARROW_LEADERSHIP | Yes | 50.1% | 66.7% |
| 2023-05-31 | NARROW_LEADERSHIP | Yes | 30.4% | 73.3% |
| 2023-06-30 | GREEN | Yes | 58.6% | 93.3% |
| 2023-07-31 | GREEN | Yes | 54.9% | 93.3% |
| 2023-08-31 | NARROW_LEADERSHIP | Yes | 49.3% | 86.7% |
| 2023-09-29 | NARROW_LEADERSHIP | Yes | 37.1% | 86.7% |
| 2023-10-31 | CORRECTION | No | 25.3% | 73.3% |
| 2023-11-30 | GREEN | Yes | 55.9% | 86.7% |
| 2023-12-29 | GREEN | Yes | 65.5% | 80.0% |

### Matrix Conservative

| Month-end | State | SPY>EMA200 | Breadth | Leader health |
|---|---|---:|---:|---:|
| 2023-01-31 | GREEN | Yes | 54.0% | 33.3% |
| 2023-02-28 | CORRECTION | Yes | 42.1% | 33.3% |
| 2023-03-31 | GREEN | Yes | 55.5% | 60.0% |
| 2023-04-28 | NARROW_LEADERSHIP | Yes | 50.1% | 66.7% |
| 2023-05-31 | NARROW_LEADERSHIP | Yes | 30.4% | 73.3% |
| 2023-06-30 | GREEN | Yes | 58.6% | 93.3% |
| 2023-07-31 | GREEN | Yes | 54.9% | 93.3% |
| 2023-08-31 | NARROW_LEADERSHIP | Yes | 49.3% | 86.7% |
| 2023-09-29 | NARROW_LEADERSHIP | Yes | 37.1% | 86.7% |
| 2023-10-31 | CORRECTION | No | 25.3% | 73.3% |
| 2023-11-30 | GREEN | Yes | 55.9% | 86.7% |
| 2023-12-29 | GREEN | Yes | 65.5% | 80.0% |

### Matrix Balanced

| Month-end | State | SPY>EMA200 | Breadth | Leader health |
|---|---|---:|---:|---:|
| 2023-01-31 | GREEN | Yes | 54.0% | 33.3% |
| 2023-02-28 | CORRECTION | Yes | 42.1% | 33.3% |
| 2023-03-31 | GREEN | Yes | 55.5% | 60.0% |
| 2023-04-28 | NARROW_LEADERSHIP | Yes | 50.1% | 66.7% |
| 2023-05-31 | NARROW_LEADERSHIP | Yes | 30.4% | 73.3% |
| 2023-06-30 | GREEN | Yes | 58.6% | 93.3% |
| 2023-07-31 | GREEN | Yes | 54.9% | 93.3% |
| 2023-08-31 | NARROW_LEADERSHIP | Yes | 49.3% | 86.7% |
| 2023-09-29 | NARROW_LEADERSHIP | Yes | 37.1% | 86.7% |
| 2023-10-31 | CORRECTION | No | 25.3% | 73.3% |
| 2023-11-30 | GREEN | Yes | 55.9% | 86.7% |
| 2023-12-29 | GREEN | Yes | 65.5% | 80.0% |

### Matrix Growth

| Month-end | State | SPY>EMA200 | Breadth | Leader health |
|---|---|---:|---:|---:|
| 2023-01-31 | GREEN | Yes | 54.0% | 33.3% |
| 2023-02-28 | CORRECTION | Yes | 42.1% | 33.3% |
| 2023-03-31 | GREEN | Yes | 55.5% | 60.0% |
| 2023-04-28 | NARROW_LEADERSHIP | Yes | 50.1% | 66.7% |
| 2023-05-31 | NARROW_LEADERSHIP | Yes | 30.4% | 73.3% |
| 2023-06-30 | GREEN | Yes | 58.6% | 93.3% |
| 2023-07-31 | GREEN | Yes | 54.9% | 93.3% |
| 2023-08-31 | NARROW_LEADERSHIP | Yes | 49.3% | 86.7% |
| 2023-09-29 | NARROW_LEADERSHIP | Yes | 37.1% | 86.7% |
| 2023-10-31 | CORRECTION | No | 25.3% | 73.3% |
| 2023-11-30 | GREEN | Yes | 55.9% | 86.7% |
| 2023-12-29 | GREEN | Yes | 65.5% | 80.0% |

## Interpretation discipline

- The earlier frozen 75/25 artifact reported USD 19,808.08 ending value, 14.66% CAGR, -33.85% max drawdown and +2.91% in 2023. This replay does not replicate it because its public-data fundamental/share reconstruction differs materially.
- Therefore choose among adaptive variants only on relative changes inside this replay, then confirm the winning controller against the original frozen artifact before production use.
