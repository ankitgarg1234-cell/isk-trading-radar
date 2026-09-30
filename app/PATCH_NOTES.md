# Strategic Capital Coverage Fix

## Why this patch exists
The first shadow monitor could show `NOT CHECKED` or `NONE FOUND IN CURRENT EVIDENCE` even when useful official evidence existed. The main gaps were:

1. It checked only the configured annual OGE disclosure, not the President's periodic transaction reports.
2. USAspending searched only for the company as the direct prime recipient, so federal purchases made through a reseller/integrator could be missed.
3. `Refresh analysis` refreshed normal market data but did not force the company-specific official strategic-capital sources.
4. Administration-highlighted company interest was not checked against the White House's official investment tracker.
5. The UI did not distinguish "not checked" from "checked and not found" clearly enough.

## What changed
- Adds configurable President Trump periodic transaction-report URLs and checks them alongside the annual OGE disclosure.
- Parses company/ticker matches row-locally and records transaction action/date/amount range when available.
- Keeps Donald Trump personal disclosure evidence separate from administration/government actions.
- Adds USAspending keyword/product-description search to detect indirect federal procurement through resellers/integrators.
- Indirect prime-award amounts are explicitly **not** counted as company revenue or direct government funding.
- Adds the official White House investment tracker as an **administration-interest/context** source. A tracker hit is not treated as U.S. government capital and not treated as Donald Trump personal ownership.
- Clicking `Refresh analysis` now forces an immediate official-source refresh for that symbol and bypasses the process-local 24h official-source cache for that manual request.
- Top-20 background enrichment remains rate-limited/cached exactly as before.
- Adds evidence coverage fields and clearer UI rows for direct federal awards, indirect product/reseller mentions, White House tracker status, and Trump disclosure coverage.
- Remains **SHADOW ONLY**: no deterministic-score or rank-v1 change.

## Deployment
Replace only the files included in this patch. No database migration is required.

Existing `TRUMP_OGE_DISCLOSURE_URL` remains supported. New optional settings:

- `TRUMP_PERIODIC_TRANSACTION_URLS=<comma-separated certified PDF URLs>`
- `WHITEHOUSE_INVESTMENTS_URL=https://www.whitehouse.gov/investments/`

The code contains defaults for the currently known 2026 President Trump periodic reports. Keep the periodic-report environment variable updated when a newer certified report is published.

## After deploy
1. Open `/analysis/NVDA`.
2. Click **Refresh analysis** once.
3. The Government / Strategic Capital panel should show an `official_checked_at` timestamp.
4. `Donald Trump personal disclosures` should show how many reports were checked and any verified matching transactions found.
5. `White House investment tracker` should show whether the company is highlighted there.
6. Direct federal awards and indirect federal product/reseller mentions are shown separately.

A direct U.S. government equity stake should still display `NONE FOUND IN CURRENT EVIDENCE` unless actual stake evidence is found. This patch does not turn general policy support, an administration-highlighted private investment, or a personal disclosure transaction into a government investment.

## Neon / network impact
- No new database table and no large historical payloads.
- Background official enrichment is still Top-20 only, limited by `STRATEGIC_ENRICH_PER_CYCLE`, `STRATEGIC_ENRICH_INTERVAL_SECONDS`, and the 24h per-source cache.
- Manual `Refresh analysis` intentionally makes fresh external official-source calls for that one ticker only.
