# Government / Strategic Capital Shadow Patch

## What changed
- Adds a separate **Government / Strategic Capital** evidence layer.
- Tracks company-specific federal awards/contracts/grants/loans through USAspending.gov.
- Detects government equity/stake language and administration-specific company actions in current news.
- Separates **Donald Trump personal disclosed interest** from **Trump administration action** and from **Trump-family interest**.
- Checks the configured certified President Trump OGE annual financial disclosure PDF and reports a company/ticker mention as **DISCLOSURE MENTION — REVIEW SOURCE** rather than assuming it is a stock purchase.
- Tracks sector-policy evidence and government demand/capital evidence.
- Adds provenance/status to stock detail and a compact GOV badge/detail to the Top-20 Radar.
- Stores a `shadow_rank_adjustment` for later validation, but **does not add it to rank-v1 or the deterministic 100-point score**.

## Why shadow-only
This factor is new. It must prove incremental value in walk-forward and forward paper trading before it can influence the 5–7 stock portfolio.

## Network / Neon safeguards
- Normal market scans use the news already fetched for the stock; no additional government API call per ticker.
- Official enrichment is limited to the optimizer Top 20.
- Default: four stale candidates per enrichment batch, at most once every 15 minutes.
- Each company official check is cached for 24 hours.
- Compact current-state payloads retain only the most relevant strategic events.

## New environment variables
- `STRATEGIC_CAPITAL_ENABLED=true`
- `STRATEGIC_OFFICIAL_REFRESH_HOURS=24`
- `STRATEGIC_ENRICH_PER_CYCLE=4`
- `STRATEGIC_ENRICH_INTERVAL_SECONDS=900`
- `STRATEGIC_USASPENDING_LOOKBACK_DAYS=730`
- `TRUMP_OGE_DISCLOSURE_URL=<current certified OGE PDF>`

The patch already contains the current 2026 certified President Trump disclosure URL as the default. Update the variable when OGE publishes a newer annual disclosure.

## Dependency
Adds `pypdf>=5.0,<7` for reading the certified OGE PDF. Failure to retrieve or parse the disclosure never blocks the scanner; status becomes UNKNOWN/UNAVAILABLE.

## Important interpretation rules
- Presidential praise/mention alone does not receive investment weight.
- Government action is not treated as Donald Trump personal investment.
- Donald Trump Jr./other family activity is not labelled as Donald Trump activity.
- `NOT FOUND IN CHECKED DISCLOSURE` means only that the configured disclosure did not match the company/ticker; it is not a universal proof of no economic interest.
