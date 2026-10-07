# GREEN quality filter experiment - 2022-2026 research replay

This is an independent point-in-time research replay using the same reconstructed 75/25 architecture and data pipeline as the prior no-BEAR ablation. Absolute returns do not reproduce the earlier 19,808 artifact, so comparisons below are valid as within-replay ablations, not replacements for the frozen control.

This test asks whether apparent GREEN signals during bear-market rallies should require medium-term confirmation. The severity-aware 55/20 controller and weekly recovery are held fixed; only the GREEN qualification changes.
- GREEN: SPY above EMA200 and healthy breadth >= 50%.
- NARROW_LEADERSHIP: SPY above EMA200, breadth < 50%, leadership health >= 40%.
- SYSTEMIC_BEAR: SPY below EMA200, healthy breadth < 35%, leadership health < 40%.
- CORRECTION: all other non-GREEN/non-NARROW states.
- Weekly RECOVERY: SPY back above EMA200 with breadth >= 40%, or positive 21-session SPY return with breadth >= 45%, leadership health >= 40%, and breadth at least 5 points above the defensive month-end.

| Variant | End value | 5Y return | CAGR | Max DD | 2022 | 2023 | 2024 | 2025 | 2026 | Avg exp. | Turnover | Costs | Recoveries |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Severity 55/20 baseline | USD 17,854.74 | +78.55% | 12.29% | -14.32% | -7.02% | +15.01% | +25.06% | +11.47% | +19.76% | 64.59% | 4.93x | USD 970 | 2 |
| Severity + GREEN r63>0 | USD 18,258.71 | +82.59% | 12.80% | -13.20% | -5.93% | +15.31% | +25.02% | +12.48% | +19.69% | 63.74% | 4.76x | USD 942 | 2 |
| Severity + GREEN r63 + soft slope | USD 18,699.85 | +87.00% | 13.34% | -13.16% | -4.88% | +15.16% | +25.56% | +12.75% | +20.58% | 64.08% | 4.77x | USD 950 | 3 |
| Severity + GREEN r63 + positive slope | USD 18,014.47 | +80.14% | 12.49% | -13.00% | -4.88% | +12.84% | +25.01% | +12.32% | +19.53% | 62.29% | 4.65x | USD 925 | 3 |

## 2023 monthly state classifications

### Severity 55/20 baseline

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

### Severity + GREEN r63>0

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

### Severity + GREEN r63 + soft slope

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

### Severity + GREEN r63 + positive slope

| Month-end | State | SPY>EMA200 | Breadth | Leader health |
|---|---|---:|---:|---:|
| 2023-01-31 | CORRECTION | Yes | 54.0% | 33.3% |
| 2023-02-28 | CORRECTION | Yes | 42.1% | 33.3% |
| 2023-03-31 | CORRECTION | Yes | 55.5% | 60.0% |
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
