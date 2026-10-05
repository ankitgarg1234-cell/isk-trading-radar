# Analyst-feed regression and repair — 5 October 2026

## Confirmed production failure

At 15:47 UTC, CRDO returned analyst_score=null, _analyst_status="unavailable (request budget)". MSFT returned 84.5 from Finnhub recommendation counts. Thus the score pipeline was intermittently losing its inputs, rather than globally failing in the formula or display.

The 49b8745 market-evidence repair introduced a shared 45-request/minute budget and shared 256-entry cache across recommendation, metric, profile and target endpoints. New optional enrichment could exhaust recommendation capacity; metric/profile churn could evict valid cached recommendations. This was a regression introduced by that repair. Yahoo HTTP 401 and Finnhub price-target HTTP 403 were independently observed and predate this recommendation-starvation fix.

## Repair

- Prefetch recommendation counts for the full analysis batch before optional P/E/profile requests.
- Preserve the aggregate 45-request/minute limit, and cap optional enrichment at 15 requests/minute, reserving capacity for recommendations.
- Keep caches separate by endpoint: 256 recommendation entries, 128 metric entries, 128 profile entries, 32 target entries. Store compact required fields only. Recommendation TTL is six hours; provider period remains visible.
- Retry actual HTTP 429 responses after the 60-second cooldown instead of negative-caching the result for five minutes.
- Report analyst-score availability and missing-status counts in scanner diagnostics.
- Bump the shared scoring version to v11 to refresh persisted missing scores. The formula and weights do not change. This is used by both dashboard and canonical paper account.

## Validation

Full suite: 432 passed, the same 27 failures as the prior baseline. Six new regression tests passed in that run; a seventh verifies retry after actual HTTP 429 cooldown. Final focused run: 130 passed. Includes score gate, single-account paper trial and ledger checks. No score threshold, allocation band, ledger reset, trial-date or subscription change.
