# Regime hysteresis and fast-recovery experiment - 2022-2026 research replay

This is an independent point-in-time research replay using the same reconstructed 75/25 architecture and data pipeline as the prior no-BEAR ablation. Absolute returns do not reproduce the earlier 19,808 artifact, so comparisons below are valid as within-replay ablations, not replacements for the frozen control.

This test keeps the Balanced regime-policy matrix fixed and changes only two controller mechanics: confirmation before entering a non-severe SYSTEMIC_BEAR, and weekly re-entry after a defensive state. ATR trailing stops remain disabled.
- GREEN: SPY above EMA200 and healthy breadth >= 50%.
- NARROW_LEADERSHIP: SPY above EMA200, breadth < 50%, leadership health >= 40%.
- SYSTEMIC_BEAR: SPY below EMA200, healthy breadth < 35%, leadership health < 40%.
- CORRECTION: all other non-GREEN/non-NARROW states.
- Weekly RECOVERY: SPY back above EMA200 with breadth >= 40%, or positive 21-session SPY return with breadth >= 45%, leadership health >= 40%, and breadth at least 5 points above the defensive month-end.

| Variant | End value | 5Y return | CAGR | Max DD | 2022 | 2023 | 2024 | 2025 | 2026 | Avg exp. | Turnover | Costs | Recoveries |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Matrix Balanced | USD 17,436.32 | +74.36% | 11.76% | -14.61% | -7.33% | +15.12% | +25.10% | +8.65% | +20.24% | 63.23% | 4.84x | USD 938 | 0 |
| Balanced + systemic confirmation | USD 17,485.72 | +74.86% | 11.82% | -16.06% | -8.90% | +14.97% | +24.88% | +11.47% | +19.93% | 66.14% | 4.88x | USD 960 | 0 |
| Balanced + weekly recovery | USD 17,664.60 | +76.65% | 12.05% | -14.30% | -6.99% | +15.00% | +25.06% | +10.15% | +19.89% | 64.40% | 4.98x | USD 968 | 2 |
| Balanced + confirmation + weekly recovery | USD 17,715.98 | +77.16% | 12.12% | -15.72% | -8.54% | +14.90% | +24.79% | +12.91% | +19.65% | 67.38% | 5.05x | USD 994 | 2 |

## 2023 monthly state classifications

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

### Balanced + systemic confirmation

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

### Balanced + confirmation + weekly recovery

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
