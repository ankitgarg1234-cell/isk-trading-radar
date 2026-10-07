# Frozen-engine exception overlay - 2022-2026 research replay

This is an independent point-in-time research replay using the same reconstructed 75/25 architecture and data pipeline as the prior no-BEAR ablation. Absolute returns do not reproduce the earlier 19,808 artifact, so comparisons below are valid as within-replay ablations, not replacements for the frozen control.

This test keeps the frozen-like behavior intact in GREEN: normal 75/25 selection, normal inverse-ATR sizing, Top-20 entry/Top-35 retention, and 3x ATR trailing stops. The exception overlay intervenes only in NARROW_LEADERSHIP, CORRECTION, SYSTEMIC_BEAR, and optional weekly RECOVERY.
- GREEN: SPY above EMA200 and healthy breadth >= 50%.
- NARROW_LEADERSHIP: SPY above EMA200, breadth < 50%, leadership health >= 40%.
- SYSTEMIC_BEAR: SPY below EMA200, healthy breadth < 35%, leadership health < 40%.
- CORRECTION: all other non-GREEN/non-NARROW states.
- Weekly RECOVERY: SPY back above EMA200 with breadth >= 40%, or positive 21-session SPY return with breadth >= 45%, leadership health >= 40%, and breadth at least 5 points above the defensive month-end.

| Variant | End value | 5Y return | CAGR | Max DD | 2022 | 2023 | 2024 | 2025 | 2026 | Avg exp. | Turnover | Costs | Recoveries |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Frozen-like control: 3x ATR + full BEAR liquidation | USD 11,038.59 | +10.39% | 2.00% | -15.29% | -6.04% | -4.40% | +9.24% | -0.74% | +13.34% | 40.23% | 7.52x | USD 1,222 | 0 |
| Exception overlay: strict systemic | USD 12,120.63 | +21.21% | 3.92% | -14.56% | -3.20% | +2.09% | +7.74% | +1.26% | +12.42% | 45.04% | 6.92x | USD 1,143 | 0 |
| Exception overlay: strict + weekly recovery | USD 12,207.05 | +22.07% | 4.07% | -14.56% | -3.20% | +2.09% | +7.74% | +3.21% | +11.08% | 45.84% | 6.96x | USD 1,150 | 1 |
| Exception overlay: partial systemic | USD 12,146.14 | +21.46% | 3.97% | -14.50% | -3.69% | +2.19% | +7.73% | +1.90% | +12.43% | 45.04% | 6.90x | USD 1,149 | 0 |

## 2023 monthly state classifications

### Frozen-like control: 3x ATR + full BEAR liquidation

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

### Exception overlay: strict systemic

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

### Exception overlay: strict + weekly recovery

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

### Exception overlay: partial systemic

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
