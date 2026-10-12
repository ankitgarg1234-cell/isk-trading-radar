# GEMv1 two-universe monthly ranking audit — October 12, 2026

**RESEARCH ONLY. Not independently point-in-time certified. No paper/live trading permission. No GEMv1 strategy or Paper Model changes.**

## Completed comparison

GitHub Actions: https://github.com/ankitgarg1234-cell/isk-trading-radar/actions/runs/38253872109

- 57 NYSE month-end dates, January 2022–September 2026.
- 52 secondary source-B monthly constituent lists actually retrieved and archived through April 2026, with source hashes. No invented May–Sep 2026 file.
- 33 months of frozen archived GEMv1 features available (2024–2026); no archival feature tape for 2022–2023.
- **21 of 21 archived original monthly top-five signals in 2025–2026 reproduced exactly** by applying the unchanged frozen screening logic to stored feature rows.
- **Zero observed-only top-five differences across 28 comparable months (Jan 2024–Apr 2026)**. This is NOT full-universe rank proof: all months retain potential unobserved competitor data gaps.
- No independently verified selection outcome for any of the 57 months, and GEMv1 forward data certification remains 0/6.

## Representative monthly membership comparison

These are counts AFTER documented ticker-era exclusions, not authoritative official index constituent counts.

| Month end | Source A | Source B | Observed-only rank |
|---|---:|---:|---|
| Jan 2022 | 505 | 492 | No frozen feature tape |
| Dec 2022 | 503 | 494 | No frozen feature tape |
| Jun 2023 | 503 | 494 | No frozen feature tape |
| Dec 2023 | 503 | 496 | No frozen feature tape |
| Dec 2024 | 503 | 500 | Same observed top five |
| Sep 2025 | 503 | 501 | Same observed top five |
| Jan 2026 | 502 | 502 | Same observed top five |
| Apr 2026 | 503 | 502 | Same observed top five |
| Sep 2026 | 502 | Not published | Cannot compare |

Source B is frequently UNDERCOMPLETE after filtering future tickers, because its retroactively named securities have not been mapped back to independently verified predecessor security IDs. Never treat the post-quarantine count as a certified complete membership list.

## Existing frozen price archive coverage

The historical price cache used by the frozen research engine starts in late 2022. Every count below requires exactly the previous 127 NYSE completed sessions, but it does not certify adjustment economics, original publication, or independent vendor parity.

- All 2022 and January–April 2023 month-ends: **0** fully covered symbol series in this existing cache.
- May–December 2023: **467–478** source A member series per month.
- January and December 2024: **478** and **486** source A members.
- January and December 2025: **486** and **493** source A members.
- January–April 2026: **494–497** source A members.

A missing archived feature row may represent a failed original screen, a missing vendor price history, or absent SEC facts. Never infer which without the original evidence.

## Frozen GEMv1 rank boundaries

Exact unchanged research screen: prior-session price/liquidity/warmup prefilter, positive 63-session momentum, revenue year-over-year growth above 20%, earnings improvement and operating-margin improvement above 3 percentage points; top five ranked by 63-session momentum. Read from the frozen archived research commit d59b93d3d9a87d582045b4ae71ff9a6f696a48be. The archived source includes unresolved original SEC/accession and historical membership issues: **943 unresolved security/date competitor cases** in the prior gap triage.

A conditional observed-only shortlist is not the same as a complete GEMv1 historical portfolio. Never invent unobserved competitors' pass/fail state or fill/return outcomes.

## Required repairs before true 2022–2026 top-five comparison

1. Obtain 127-bar 2022–early 2023 historical daily OHLCV histories from free sources with source-byte receipts, especially missing/delisted/renamed securities, and reconcile nominal/adjusted close semantics.
2. Fill member-specific missing archived price windows for late 2023–2026; preserve quarantined ticker changes and separate genuine dual-share classes.
3. Validate every possible competing security's six original SEC financial facts with accession, period, units, first availability and acceptance cutoffs; classify unknowns explicitly.
4. Recompute the frozen global top-five independently from both complete monthly member sets and note any discrepancies. Do not treat unranked securities as failing.
5. Preserve the original frozen signals; do not modify the Paper Model, trades, dashboard certified-source indicators or strategy rules.

## Source artifacts and tracking

- Historical members and effective-dated identity PR: https://github.com/ankitgarg1234-cell/isk-trading-radar/pull/84
- Two-universe monthly research PR: https://github.com/ankitgarg1234-cell/isk-trading-radar/pull/86
- Full rankings evidence workstream: https://github.com/ankitgarg1234-cell/isk-trading-radar/issues/85
- Master GEMv1 tracking: https://github.com/ankitgarg1234-cell/isk-trading-radar/issues/80

The GitHub Actions artifact gem-two-universe-2022-2026-not-certified contains the original public source snapshots, source hashes, all month-by-month ticker differences, archived-feature gap lists, 127-session price-coverage names, conditional top-five values and missing-SEC/evidence status. All outputs remain research-only.
