# Fresh database and deterministic-score assurance — 6 October 2026

## Additional score-input corrections (v17)

Two defects reproduced on the deployed v16 code. When verified SEC evidence
replaced the annual fundamental fields, a pre-existing Yahoo quarterly-growth
value could survive the merge. Its source metadata then described SEC evidence
while the scorer used the other provider's value. SEC integrity now controls
quarterly growth and its metadata together, including explicit unavailability.
A captured WDC SEC replay independently computes `3747/2605 - 1`; with a
contradictory 5% upstream quarter, the old merge withheld the existing two-point
quarterly bonus (17/20 instead of 19/20). This is a source replay, not a claim
that the current live Yahoo feed returned that conflicting value.

Analyst scoring also accepted nonfinite targets/means and invalid count mixes.
A malformed but truthy recommendation mean suppressed valid count evidence;
`recommendationMean='bad', strongBuy=10` incorrectly yielded unavailable, while
a NaN mean could produce 100. Finite positive targets, means in [1,5], and
nonnegative integer count buckets now control eligibility. Valid counts remain
usable when the mean is invalid. Invalid price cannot create target upside.
Valid observations retain their existing weights.

The new regression file has 24 cases; 16 of its initial 23 cases failed against
the exact deployed v16 commit and all now pass. The relevant combined suite
passed 375 checks before the final captured-source case was added; that final
case also passes. Version v17 invalidates saved v16 scoring decisions. The
70 deterministic / 75 analyst / 0.4x R/R gates and component weights are unchanged.

The user approved a fresh free-plan database after the old Neon project stopped
accepting reads. Old project metadata shows about 120 MB of logical storage,
20,577 compute seconds (5.72 CU-hours) and 5,582,512,313 bytes of public network
transfer. Network transfer exceeds the Free plan's 5 GB monthly allowance;
storage and compute are below their respective 1 GB and 100 CU-hour limits.
No old project or records are deleted. A fresh database starts a separate paper
history; it does not reconstruct inaccessible holdings or trades.

## What the score audit establishes

The final engine is `2026-10-06-completed-session-volume-v16`. Component caps are
Fundamentals 20, Catalyst 15, News 15, Momentum 15, Sector 10, Valuation 10,
Analyst confirmation 5 and Risk/Reward 10. Their total is 100. The shared
qualification gates remain deterministic 70, Analyst 75 and unrounded entry
R/R 0.4. A qualified stock still needs an entry trigger and a subsequent fresh
exchange observation before a paper fill.

- Captured SEC source replays verify fiscal-period and currency matching, annual
  and quarterly units, gross-margin reconstruction, average-equity ROE, genuine
  debt bounds and current aliases after older concepts were retired.
- Source-arithmetic controls include `23126/5895 - 1` for Broadcom earnings
  growth, `23126/((67678+81292)/2)` for its fiscal ROE and `59419/99690*100` for
  its matched balance-sheet debt/equity. These are source-derived calculations,
  not ticker-specific scoring exceptions.
- Captured fundamental scores: CRDO 20, NVDA 20, WDC 19, GOOGL 19, AVGO 20.
  The richer MSFT capture proves a liabilities/equity upper bound of 71.43%,
  giving 20/20; the earlier capture without that evidence gives 18/20. Missing
  exact debt is still disclosed and is never assumed to be zero.
- News and Catalyst checks cover factual company attribution, duplicate event
  groups, speculation, negation and negative-news overrides. Valuation checks
  cover positive finite forward P/E, trailing fallback, band boundaries and
  evidence provenance. Missing P/E earns the documented neutral baseline.
- R/R is recomputed from target, price and stop. A displayed or forged rounded
  R/R cannot bypass the gate. Its quality component uses the existing 3x scale:
  0.4x eligibility therefore contributes about 1.33/10, not full points.
- Full-scan exports disclose each component, filing periods, financial input
  ratios, missing-data status, model limitations and exact gate blockers.

These checks establish correct implementation against captured evidence, not
forecast accuracy, profitability or optimal weights. Catalyst and News together
carry 30 points; a neutral headline set yields Catalyst 5 and News 7.5. The
weights therefore favour timely catalysts. At R/R 0.4, Fundamentals 14 and those
neutral news values, even perfect other components total only 67.83. Reweighting
needs separate calibration rather than points added merely to create candidates.
Financial-services margins and balance-sheet debt require a sector-specific
model; the industrial bands remain an explicitly reported model limitation.

## Database-transfer correction

The stale-score refresh check previously streamed **every complete candidate
payload** to the application each cycle until it found older versions. When
all rows were current it downloaded the whole scored universe repeatedly.
Version extraction and filtering now run in SQL; only a bounded ticker list
crosses the network. Validated JSON parsing preserves current, old, absent,
nested and malformed-version behaviour. PostgreSQL 18 was verified with a
read-only live query; the SQLite regression checks verify that analysis payloads
are not selected, including 80 current rows containing 100 KB each. The audit's
pending-work query likewise selects symbols only.

The full scan now freezes the date of the latest observed S&P 500 exchange quote
instead of calendar today. This prevents a morning/weekend/holiday audit from
rejecting valid previous-session stock closes. Unavailable, stale or future
index timestamps block starting the audit rather than create misleading errors
across the universe. No trading-calendar date is guessed.

## Production canary: completed-session volume omission

After the fresh database was live, source and component checks passed on NVDA,
MSFT and AVGO. They exposed another concrete input omission: the normalized
volume calculation returned `quote is not from the current trading date` for
all three previous-session closing quotes, simply because the calendar had
rolled over. MSFT's full-session daily ratio was about 1.25, while normalized
volume remained unknown; the scorer therefore withheld the existing three
volume points and the target plan could not recognize its stronger trend.

The provider now permits the latest completed session for closed-market
research. It still uses actual five-minute regular-session volume buckets and
requires complete current intervals, at least ten matched historical sessions,
an observed closing quote within seven days, matching latest chart metadata and
no later observed regular session. Incomplete, superseded and invalid observations
remain unavailable. The original exchange observation date is preserved.
Previous-session quotes remain rejected during the live regular-session clock;
paper entries retain their independent ten-minute exchange-quote freshness check.
The v16 version invalidates cached v15 decisions so older suppressed values are
refreshed instead of mixed into the new scan. No volume multiplier or bonus point
is invented to force a stock through 70.

A fresh independent Yahoo intraday capture confirms MSFT's valid close-session
volume is 19,628,576 versus 280,015,328/19 = 14,737,648.84 for the matched prior
sessions: **1.331866x**. The original rule discarded this observation; v16 retains
the exact source calculation. The captured timestamp/volume fixture and arithmetic
control are committed with the fix.

## Validation

- 270 focused scoring, filing, catalyst/valuation, shared gate, market-evidence,
  scanner, full-scan and transfer checks passed.
- 203 checks passed in the additional portfolio, trial, lane, market-source,
  article/news and paper-balance run. One legacy allocator test failed identically
  on the unchanged deployed commit `4877f928925632236c0cfb8f65f5146fe72edbbd`:
  `test_paper_allocator_preserves_score_weighting_when_cash_constrained`.
- After the session-date change, all 28 full-scan and transfer checks passed,
  including six new pre-open and invalid-index controls.
- Python compilation, dashboard JavaScript syntax and whitespace checks passed.
- After the production-volume discovery, 238 affected market-input, scoring,
  shared gate, scanner, full-scan, short-horizon, canonical strategy and trial
  checks passed. Nine new controls cover pre-open/weekend complete sessions,
  unchanged observation dates and rejection of stale/live/unfinished/missing/
  superseded inputs.
- The added real-source MSFT volume capture also passes its independent sum/mean
  control; all 30 market-evidence tests pass with this final fixture.

The legacy allocator failure is not represented as passing. Production uses the
armed canonical complete-strategy account. Score weights, financial thresholds
and target formulas are preserved; supplying correctly observed volume can change
the target and R/R through those existing formulas.
