# R/R filter correction and deterministic-score audit — 5 October 2026

## Release behavior

The agreed minimum entry R/R is 0.4×. `app/trading_rules.py` is the shared source for dashboard ranking, entry alerts, paper add checks and the canonical paper strategy. The dashboard text and API fallback use that value. The paper strategy still recalculates R/R from price, frozen target and stop at signal/fill time. Its 70-point deterministic gate, 75-point analyst gate, allocation bands, ledger and trial dates are unchanged.

The scanner now records bounded `score_diagnostics` in each completed open-market cycle: score bins, maximum, count at/above 70, missing-input counts and the five highest-scoring analyses. This is a description of the latest cycle, not a census of distinct stocks. It never changes scoring or qualification.

## Production findings before this correction

At 14:48 UTC the canonical account had 1,036 fresh observations, all blocked at `deterministic_below_70_or_invalid`, including repeated observations of stocks. The rotating scanner prefilters 200 names per cycle from a 5,758-name universe, then deeply analyzes at most 48 candidates. The last observed cycle analyzed 32 without errors. The account had $10,000 cash, no trades and no positions; the trial started at 13:31:37 UTC and ends at 14:31:37 UTC on 5 November.

A read of 12 production analyses around 14:53–14:55 UTC found:

- Yahoo fundamentals reported `unavailable (HTTPStatusError)` for all 12.
- Forward P/E, trailing P/E and analyst mean price targets were missing in all 12. The current scorer assigns a neutral 5/10 valuation score without P/E; targets use ATR/trend and nearby resistance without analyst target confirmation. Restoring these inputs can move scores in either direction and must not be represented as guaranteed bonus points.
- Recommendation scores were available through Finnhub. Analyst recommendations and analyst price targets are distinct inputs; an analyst score above 75 does not establish an available price target.
- RVOL is latest daily volume divided by the previous 20 full-day volumes. It is not matched to time of day. Early in the session, it can withhold 3 momentum points and prevent the elevated-volume target/catalyst tests from passing. Accurate correction requires intraday volume histories; multiplying by elapsed-session time would only be an approximation, not time-matched RVOL.
- Corrected news assessment often yields News 7.5/15 and Catalyst 5/15. This materially reduces inflated headline scores. Opinion credit does not manufacture factual catalysts.
- Several stocks have additional valid technical blockers, such as RSI above 72 or price below an EMA. These must not be automatically awarded points.
- PLTR and GOOGL lacked market-cap evidence in the sample, an additional quality blocker.
- Some saved detail responses, including MSFT and WDC, still had Friday quote timestamps. Those are saved analyses, not evidence of a fresh Monday quote. The paper account's exchange-time freshness check rejects stale observations.

Sample scores (saved responses have different timestamps and are not a synchronized market ranking):

| Stock | Deterministic | Analyst | Fundamentals | News | Catalyst | Momentum | Valuation | R/R |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| CRDO | 62.0 | 85.0 | 20 | 9.0 | 5 | 9 | 5 | 0.23 |
| NVDA | 60.9 | 84.8 | 20 | 7.5 | 5 | 9 | 5 | 0.35 |
| PLTR | 64.7 | 75.6 | 20 | 9.0 | 8 | 9 | 5 | 0.27 |
| CSCO | 63.4 | 74.6 | 19 | 7.5 | 5 | 12 | 5 | 0.65 |
| NOW | 58.7 | 82.0 | 17 | 7.5 | 5 | 9 | 5 | 0.63 |

CRDO's total is approximately 20 + 5 + 9 + 9 + 9 (Sector) + 5 + 4.25 (Analyst confirmation) + 0.8 (R/R) = 62.0. Displayed component rounding can differ slightly from the rounded total.

There is no hard ceiling at 70. The unchanged scorer produces 85.7 on the existing supported-input fixture, and that fixture qualifies in Core Quality. This validates reachability, not real-market profitability or the correctness of missing production data.

## Validation

- Focused portfolio, paper execution, trial, balance, fundamentals, news, article, source and diagnostics checks: 260 passed. The narrower portfolio/paper/trial/balance run passed all 66 checks.
- Ten additional checks cover the shared 0.4 boundary, entries between 0.4 and 2.0, unchanged sub-70 paper rejection, rendered threshold, bounded diagnostics and an actual scorer output above 70.
- Full baseline: 391 passed, 27 failed.
- Full correction: 401 passed, the same 27 failed. Failure ID comparison found no new or resolved failures. This run includes duplicate `app/tests` tests and the unrelated `backend-patch/tests` mobile suite.

The correction does not repair the Yahoo data source, normalize intraday RVOL, reweight news or automatically refresh all saved detail responses. These remain identified follow-up work. Lowering the R/R filter cannot by itself raise a deterministic score.
