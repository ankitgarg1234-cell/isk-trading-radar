# GEMv1 source freshness architecture — deployment approval required

Read-only code branch: `draft/gem-public-source-refresh-20261012`, based on repository's default **main**. The GitHub Actions `schedule` trigger is evaluated only on the **default branch**, so this draft will NOT refresh anything unattended until reviewed and explicitly merged into main. No live Render, Paper Model, or frozen GEM strategy code changes. This workflow does **not** write Neon yet; GitHub Actions artifact retention is only 30 days. Never market data for trading.

## Two public downloads in phase 1

Each calendar day at 23:40 UTC (subject to GitHub Actions' best-effort scheduling), fetch original NYSE published calendar from `https://www.nyse.com/trade/hours-calendars` and secondary current S&P constituent CSV (public `datasets/s-and-p-500-companies`). Archive exact raw bytes, retrieval UTC, response lengths, SHA-256 fingerprints and calendar/member presence checks as a 30-day GitHub artifact. The sources remain **PARTIAL** despite successful retrieval because:
- Official NYSE extraordinary/halt notices, current completed-session state and a separate reviewer certificate must be added; 2026 holiday markers must be replaced for 2027 or the collector fails closed.
- Secondary current S&P CSV is **not** official effective-dated S&P DJI index licensing or point-in-time membership. Never feed it directly into approved GEM selections.

The workflow fails and produces blocked freshness records on a 403/429, unexpected content type, bad identity or missing published markers. Schedule executions can be delayed or dropped by GitHub; **watchdog needed** to flag jobs older than 36h and retain raw bytes durably in separate GEM-only Neon/blob storage. Repeated fetching does NOT certify input, and this workflow does not modify a database.

## Full refresh/reliability matrix (NOT YET CONNECTED)

| GEM source | Target collection | Blockers / incremental activation |
|---|---|---|
| NYSE calendar | Public official schedule **daily**, compare completed last close / emergency notices each session | Source raw file acquired Oct 12; schedule draft only; persist durable source, review emergencies and signed QA |
| S&P membership | Secondary public surveillance **daily**; official effective-dated authoritative snapshot on change | S&P DJI official license or independently acceptable original dated evidence unavailable; no trading eligibility |
| Daily prices | **Every completed session** for five owned names, SPY and selected watchlist; **full current eligible universe at month-end** | Paid Marketstack v2 returns null close/adjusted close June 9/10/15 2026; vendor repair, adjusted corporate-action validation and persisted account-wide credit budget required. Daily polling ~500 stocks x 21 sessions can exceed 10,000 monthly symbol credits; don't configure it. |
| SEC six-quarter facts | Daily submissions accession-change discovery and original XBRL fact retrieval with issuer/CIK mapping; full month-end reconciliation | Approved `SEC_USER_AGENT` org+contact identity, compliant SEC rate limiting, 10-Q and 10-Q/A quarter-context parser, history availability evidence, full-member and signed QA missing |
| Corporate actions | Daily ex/pay-date, splits, mergers, spinoffs and delistings with original issuer records | Full-universe provider or qualified issuer/SEC action collector, independent adjustments and ownership cash audit missing |
| SPY total return | SPY EOD each completed session plus distribution records and reconciled cash economics | Separate SPY distribution/action feed, source parity and full historical benchmark proof missing |

## Operating and security rules

1. Ingest only to **GEM-only** write identity and dedicated durable tables/object storage; no shared Dual Momentum database, no stored credentials in logs/artifacts.
2. Each receipt contains `collected_at`, last **completed exchange session** `as_of`, `source_uri`, response SHA, parsed coverage and deadline. Avoid conflating `collected_at` with trading-session `as_of`.
3. Statuses: `CONNECTED` when actual data fetched, `FRESH` only when within class deadline, `COMPLETE` after entire needed universe/dates pass, `VERIFIED` only after independent cryptographic QA; blocked/stale on any uncertainty.
4. Freeze monthly signal snapshot at independently verified NYSE last close; reject if any of six sources unavailable or stale, or if any competing eligible stock lacks valid price or filing evidence. No automatic BUY/SELL authorization.
5. Poll frequency does not override source contract. Stop on Marketstack null close; do not fabricate/bar-fill. Set durable Marketstack account-wide symbol-credit ledger and halt before paid overage.
6. Make recurring runner reliable, monitored, and idempotent before treating it as connected. GitHub scheduled jobs are best-effort; supplement with watchdog and controlled retries. Never add a paid Render Cron without explicit cost approval.
