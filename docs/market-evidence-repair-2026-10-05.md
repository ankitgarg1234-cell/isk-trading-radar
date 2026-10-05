# Market evidence repair — 5 October 2026

Production audit before this repair showed every analyzed stock missing P/E and consensus targets, eight missing market cap, and partial daily volume compared with prior full sessions. These gaps explain weak score components; there is no hard score ceiling at 70.

## Changes

- Yahoo quoteSummary retries HTTP 401 using a session cookie and crumb. Empty results are unavailable. Failed authentication has a 15-minute cooldown.
- The existing Finnhub connection supplies optional TTM P/E, USD company market cap/shares (million-unit conversion), and validated consensus price targets. Identity, positive values, target ordering and target update dates are checked. Targets older than 90 days are unavailable. Restricted endpoints remain unavailable without subscription changes.
- Sources and dates are retained independently for valuation, targets, market cap and relative volume. A retrieval date is explicitly distinguished from a provider observation date.
- US RVOL compares cumulative completed regular-session five-minute intervals against matching intervals in up to 20 prior sessions, requiring at least 10 complete sessions. Extended hours and the active interval are excluded. Missing bars and stale quotes receive no volume credit. The daily ratio remains diagnostic only.
- Intraday response bytes are capped at 2 MiB, bars at 6,000, compact RVOL cache entries at 128. Finnhub caches retain only required fields, at most 256 entries, and impose a 45-request/minute budget and failure cooldowns.
- Negative/nonfinite P/E cannot earn cheap-valuation credit.
- Scoring version v10 invalidates old stored scores for refresh through the existing shared scorer.

## Invariants

Shared R/R floor 0.4x, deterministic gate 70, analyst gate 75, score weights, allocation bands, single paper account, starting cash and trial dates are unchanged. No ledger reset, new account or scoring fork.

## Validation

Full corrected suite: 418 passed, 27 failed; baseline: 401 passed, the identical 27 failures. Three additional focused tests subsequently passed for daylight-saving-time normalization, request budget and source preservation. Focused release checks cover paper ledger/trial behavior, score gates, fundamentals and all 20 new market-evidence tests. Live deployment and provider restrictions are verified separately after deployment.
