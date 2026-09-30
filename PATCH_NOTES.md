# Strategic-capital automatic enrichment + USAspending resilience fix

## Why this patch is needed

Two issues were visible in the NVDA detail panel:

1. Official government/disclosure evidence only advanced through the background queue while the regular U.S. market scanner was running. `scan_once()` returned immediately outside U.S. regular market hours, so a Swedish-morning visit could leave Top-20 names unchecked until a manual **Refresh analysis**.
2. A single non-2xx USAspending response raised `HTTPStatusError`, aborted the entire federal-spending pass, and that failure could be cached too long. The UI therefore showed `UNAVAILABLE (HTTPStatusError)` and product/reseller coverage stayed `NOT CHECKED`.

## Changes

### `app/scanner.py`
- Strategic-capital Top-20 enrichment now runs even while the U.S. equity market is closed.
- Successful official checks retain the normal 24-hour TTL.
- Partial/failed checks use the short retry TTL (`STRATEGIC_ERROR_RETRY_SECONDS`, default 600 seconds).
- The Top-20 queue still processes only a bounded number per cycle, avoiding large Neon reads/writes.

### `app/config.py`
- Default strategic enrichment cadence changed from 900 seconds to 120 seconds.
- Added `STRATEGIC_ERROR_RETRY_SECONDS` (default 600).
- Added `STRATEGIC_USASPENDING_MAX_ATTEMPTS` (default 2).

With the default 4 names per cycle, a stable Top 20 normally gets a first background pass in about 10 minutes rather than about 75 minutes.

### `app/strategic_capital.py`
- USAspending queries are split by award class (contracts, non-loan assistance, loans) so type-specific fields/sort keys are not mixed in one request.
- Product/vendor keyword searches are also split by award class.
- One failed component no longer erases successful components.
- Retryable HTTP/network failures get a bounded retry.
- Partial results are reported as `PARTIAL — AUTO RETRY`; complete outages as `TEMPORARILY UNAVAILABLE — AUTO RETRY` instead of leaking the raw Python exception name.
- Failed/partial USAspending results use the short retry cache instead of the 24-hour success cache.
- Component status and a sanitized last error are retained for diagnosis.
- Duplicate indirect awards are deduplicated before totals are calculated.
- `official_check_status` is now `COMPLETE`, `PARTIAL`, or `NOT CHECKED`, letting the scanner choose the right TTL.

## Scoring / trading behavior

No change to deterministic score, rank-v1, paper-trading thresholds, or live trading logic. Government/strategic-capital remains shadow-only.

## Deployment

Replace:
- `app/config.py`
- `app/scanner.py`
- `app/strategic_capital.py`

No database migration is required. The `.env.example` additions are optional; defaults are in code.
