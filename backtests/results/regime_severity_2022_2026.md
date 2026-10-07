# Regime severity-aware controller - 2022-2026 research replay

This is an independent point-in-time research replay using the same reconstructed 75/25 architecture and data pipeline as the prior no-BEAR ablation. Absolute returns do not reproduce the earlier 19,808 artifact, so comparisons below are valid as within-replay ablations, not replacements for the frozen control.

This test splits broad deterioration into DEFENSIVE_BEAR versus DEEP_BEAR using contemporaneous severity. DEEP_BEAR is triggered by very weak breadth/leadership or extreme 21/63-session market loss; DEFENSIVE_BEAR keeps partial exposure. Weekly recovery is enabled and ATR trailing stops remain disabled.
- GREEN: SPY above EMA200 and healthy breadth >= 50%.
- NARROW_LEADERSHIP: SPY above EMA200, breadth < 50%, leadership health >= 40%.
- SYSTEMIC_BEAR: SPY below EMA200, healthy breadth < 35%, leadership health < 40%.
- CORRECTION: all other non-GREEN/non-NARROW states.
- Weekly RECOVERY: SPY back above EMA200 with breadth >= 40%, or positive 21-session SPY return with breadth >= 45%, leadership health >= 40%, and breadth at least 5 points above the defensive month-end.

| Variant | End value | 5Y return | CAGR | Max DD | 2022 | 2023 | 2024 | 2025 | 2026 | Avg exp. | Turnover | Costs | Recoveries |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Balanced + weekly recovery | USD 17,664.60 | +76.65% | 12.05% | -14.30% | -6.99% | +15.00% | +25.06% | +10.15% | +19.89% | 64.40% | 4.98x | USD 968 | 2 |
| Severity 65/25 + weekly recovery | USD 17,850.66 | +78.51% | 12.29% | -14.78% | -7.50% | +15.08% | +25.18% | +11.84% | +19.77% | 64.84% | 4.93x | USD 972 | 2 |
| Severity 75/20 + faster recovery | USD 17,814.52 | +78.15% | 12.24% | -14.75% | -7.47% | +15.08% | +25.18% | +12.33% | +18.97% | 65.11% | 4.97x | USD 972 | 2 |
| Severity 55/20 + weekly recovery | USD 17,854.74 | +78.55% | 12.29% | -14.32% | -7.02% | +15.01% | +25.06% | +11.47% | +19.76% | 64.59% | 4.93x | USD 970 | 2 |

## 2023 monthly state classifications

### Balanced + weekly recovery

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

### Severity 65/25 + weekly recovery

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

### Severity 75/20 + faster recovery

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

### Severity 55/20 + weekly recovery

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
