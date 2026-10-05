# Deterministic score input audit — 5 October 2026

Shared scoring version: `2026-10-05-score-input-integrity-v12`.

## Findings and corrections

1. **RSI was a rolling simple average rather than Wilder RSI.** The captured
   one-year Nvidia history gives approximately 83.87 with the old calculation
   and 65.67 with Wilder smoothing; Credo gives 75.98 versus 55.52. This withheld
   three existing momentum points and could prevent a constructive target plan.
   Seed the first 14 changes once, then smooth subsequent gains/losses. Flat
   histories return 50. The 45–72 constructive band remains unchanged.
2. **Valid gross-margin evidence was omitted.** Alphabet reports revenue and
   cost of revenue without a GrossProfit fact. Derive gross profit from matched
   complete cost/revenue tags only when fiscal dates and filing accession agree.
   Preserve reported GrossProfit when available; reject negative costs, older
   periods, partial cost tags, mismatched amendments and currencies. Alphabet's
   captured SEC fundamental score recovers three points (16 to 19).
3. **Incomplete exact debt does not always mean the score band is unknowable.**
   The stale-short-borrowing guard remains: no assumption of zero borrowings.
   Instead, reported total liabilities and equity from the same balance-sheet
   date/filing can prove a conservative upper bound on debt/equity. Below 75%
   proves the existing two-point band; below 150% proves at least one point.
   Higher bounds prove no credit. Exact reported debt takes precedence. Invalid
   exact debt, mismatched periods/filings and negative/nonpositive denominators
   cannot use this fallback. Exact debt remains null and the method is disclosed.
   Microsoft's matched liabilities/equity is 315989/442387 = 71.43%, restoring
   two points; its missing exact borrowings remain explicitly unavailable.
4. **A question erased an earlier factual headline assertion.** Assess separate
   sentences independently. Recognize asserted past-tense revenue growth,
   explicit subjectless contract/partnership continuations and passive stock
   upgrades. A dated May reference is not a modal verb. Speculation remains
   unscored; another company's named clauses cannot gain the target's credit.
   Source weights, duplicate treatment, negative overrides and opinion/body
   policy remain unchanged. Credo's observed factual revenue statement now counts.
5. **Optional requests wasted the protected enrichment budget.** Request only
   missing P/E/profile/target fields. SEC shares already support the existing
   market-cap calculation, so they do not require an extra Finnhub profile call.
   Recommendation prefetch, separate compact caches, 45 total/15 optional calls
   per minute and failure cooldowns remain intact.

## Captured-input replay

Same captured quote histories and news/consensus evidence for each before/after
comparison. These are offline diagnostic scores, not live executions or returns.

| Stock | Before | After | R/R after |
|---|---:|---:|---:|
| CRDO | 60.1 | 67.6 | 0.25 |
| NVDA | 64.4 | 67.7 | 0.43 |
| GOOGL | 63.8 | 66.8 | 0.64 |
| MSFT | 67.0 | 69.0 | 0.43 |
| WDC | 66.1 | 67.1 | 0.81 |

These repairs do not guarantee a qualifying stock. Some corrected observations
still fall below 70 or 0.4x. Yahoo quoteSummary still returned HTTP 401 on both
query hosts in a fresh authentication check; the connected Finnhub consensus
target endpoint remains restricted (HTTP 403). Missing targets remain unknown;
technical projections do not become invented analyst consensus. P/E missing
because of a request budget differs from P/E unavailable for an unprofitable
company. The rotating 200-name quick scan is not 5,758 full analyses per cycle.

Component caps remain 20/15/15/15/10/10/5/10. The entry gates remain deterministic
70, analyst 75, R/R 0.4x. R/R quality credit retains its existing 3x normalization;
that is separate from the 0.4x eligibility filter. No target/stop inflation,
allocation change, new ledger, trial reset or subscription change.

## Validation

Source fixtures retain SEC accession/period facts and captured Yahoo closes.
Independent controls cover Wilder recursion and flat histories, missing/stale/
amended costs, exact and bounded debt, band boundaries, financial units, neutral
and negative headlines, company attribution, request selectivity and shared
paper gates. Full suite: 467 passed, the identical 27 existing baseline failures.
Two additional invalid-debt controls follow that full run. Final focused run:
260 passed, with the known unrelated paper allocator failure deselected.

Calculation references: [Fidelity's Wilder RSI explanation](https://www.fidelity.com/bin-public/060_www_fidelity_com/documents/learning-center/trading-with-momentum-transcript.pdf)
and [FASB revenue taxonomy guide](https://xbrl.fasb.org/impdocs/Rev2_TIG/Revenue.htm).
