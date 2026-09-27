# ISK Radar — Data Resilience Patch

## Why this patch exists
The V1 safety rule correctly stopped the engine from issuing REDUCE decisions when evidence was incomplete, but Yahoo `quoteSummary` failures caused fundamentals, analyst metadata, and sector metadata to disappear together. That produced widespread `HOLD — DATA REVIEW` states.

## Runtime changes
- Adds official SEC EDGAR/XBRL fallback for U.S. company fundamentals.
- Adds SEC ticker/CIK resolution and broad SIC-to-sector mapping.
- Rebuilds the sector ETF benchmark even when Yahoo sector metadata is absent.
- Makes analyst consensus and consensus price target **optional confirmation inputs**, not decision-confidence requirements.
- Adds optional Finnhub recommendation-trend enrichment through `FINNHUB_API_KEY`.
- Keeps Yahoo chart/history and Yahoo news for V1 pricing/news.
- Adds an Evidence Provenance table to each full symbol analysis.
- Exposes critical vs optional missing evidence separately.

## Environment variables
### Recommended
`SEC_USER_AGENT`

Set this in Render to a descriptive User-Agent containing a contact email, for example:

`ISK Trading Radar/1.0 your-email@example.com`

### Optional
`FINNHUB_API_KEY`

If configured, the app uses Finnhub recommendation trends for Strong Buy / Buy / Hold / Sell counts. If it is absent, the analyst score may remain unavailable, but this no longer lowers decision confidence by itself.

## Important limitation
The patch does not invent analyst price targets. Consensus target remains blank when the current analyst-data source does not return one. This is displayed as an optional unavailable input rather than a sell-signal/data-quality failure.

## Tests
`35 passed / 0 failed`

The new tests cover:
- SEC SIC sector mapping
- SEC Company Facts conversion into radar-compatible growth/margin/ROE/debt fields
- Yahoo fundamental failure recovered by SEC fallback
- optional analyst evidence not lowering otherwise high decision confidence
- Evidence Provenance rendering
