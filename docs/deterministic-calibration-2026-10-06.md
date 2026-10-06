# Deterministic score calibration v21 — 6 October 2026

## Why this change exists

The evidence model became materially more conservative while the deterministic
entry threshold stayed at 70. Realistic forward targets replaced the old
52-week-high reward shortcut, factual catalyst/news validation removed inflated
headline credit, and R/R continued to use a 3x linear normalization. The result
was a compressed live score distribution: the v19 audit had 403 fully scored
stocks and none reached 70 even though 31 passed both Fundamentals >=14/20 and
Analyst >=75.

This release fixes the scale rather than lowering the gate. The canonical entry
thresholds remain deterministic >=70, Analyst >=75 and R/R >=0.4x.

## Calibrated 100-point blend

The underlying raw component calculations and their historical maxima are kept
for auditability. A separate calibrated contribution is used for the final
deterministic score:

| Component | Raw max | Deterministic weight |
|---|---:|---:|
| Fundamentals | 20 | 27 |
| Catalyst | 15 | 10 |
| News | 15 | 8 |
| Momentum | 15 | 15 |
| Sector | 10 | 10 |
| Valuation | 10 | 10 |
| Analyst confirmation | 5 | 10 |
| Risk/Reward | 10 | 10 |

Core quality therefore depends more on verified company quality and independent
analyst evidence, while Catalyst/News no longer consume 30% of the generic
deterministic scale. Explosive qualification still separately requires a
verified material catalyst, elevated relative volume, momentum/liquidity and its
existing lane rules, so reducing generic Catalyst/News weights does not make an
uncatalysed stock an Explosive candidate.

## R/R calibration

R/R remains a hard entry gate at 0.4x. The score contribution is now monotonic
and aligned with that gate:

- 0.4x = 4/10
- 1.0x = 6/10
- 2.0x = 8/10
- 3.0x or more = 10/10

Values below 0.4 can receive partial descriptive score credit but still fail the
entry gate. This removes the previous double penalty where an accepted 0.4x
setup earned only about 1.33/10 and then had to pass the hard R/R gate again.

## Regression anchors

The documented ANET v19 vector was 20 Fundamentals, 5 Catalyst, 7.5 News,
12 Momentum, 9 Sector, 3 Valuation, 4.2 Analyst confirmation and about 0.33x
R/R. It scored 61.8 on the old scale. The v21 calibration produces about 70.0
without changing any raw evidence or relaxing the 70 gate. Because its replayed
R/R is still below 0.4x, it would remain ineligible for entry until the separate
R/R gate passes.

A deliberately ordinary minimum-quality vector (14 Fundamentals, neutral
Catalyst/News, moderate momentum/sector/valuation, Analyst 75 and R/R 0.4x)
remains well below 70. The fix therefore restores reachable score separation
rather than making every fundamentally acceptable stock qualify.

## Auditability

Symbol analysis shows both raw evidence points and calibrated deterministic
contributions. Full-universe CSV export carries both sets. The scoring version is
bumped to `2026-10-06-deterministic-calibration-v21`, invalidating old cached
decisions so v20 scores cannot be mixed with the new scale.
