# Data source audit

## Minimal decision-date reconstruction

The archive contains 539 price series from late 2022 through October 1, 2026, but only 2024+ prices are needed for these entries. The financial archive has 125,709 provider observations. No complete 2022–2023 market-wide reconstruction was demanded. Earlier financial records are used only where quarterly comparators require them. Reconstructed membership rather than current membership governs admission. Current SEC ticker data is an identity aid only. Membership changes recovered from a public historical GitHub CSV are secondary evidence, not issuer/index-provider certification; the attempted S&P announcement endpoint returned 404.

SEC companyfacts and submissions requests succeeded for 525 mapped issuer CIKs (1,050 responses), followed by 17 targeted older submission archive files. 1007 source responses are actually referenced by the used-input audit. Current companyfacts containers are filtered to the **original same accession, exact period and direct quarter**, never a later revision merely because it matches. Custom extension tags are not available from the standardized companyfacts API; unresolved fields require the original filing's XBRL instance/custom mapping. Direct facts, not silently reconstructed YTD differences, verify archived derived values where possible.

Full input-use results: {"VERIFIED_SAME_ACCESSION_QUARTER": 52562, "MISSING_SEC_DIRECT_QUARTER": 189, "VALUE_MISMATCH": 42, "ACCEPTANCE_UNVERIFIED_OR_AFTER_SIGNAL": 28}. All 1,638 qualified input uses match same-accession direct quarters and are available before their signal. This certifies those individual observations only, not membership, complete rank competition, execution or total returns. The 42 value mismatches are AWK revenue standard-tag discrepancies; a custom-tag/scope bridge is needed before declaring the provider value wrong. The 28 remaining acceptance uses belong to two Citigroup accessions (`0000831001-24-000134`, `0000831001-25-000131`); recent and targeted archived submissions did not establish their acceptance times. See unresolved input extract for exact dates.

## Timestamp findings

1002 of 1,638 qualifying input uses have provider timestamps different from SEC acceptance times, commonly a four-hour offset. The frozen original engine gates on filing date <=previous calendar day and uses acceptance text for ordering; it does **not** enforce actual acceptance timestamps. The audit independently checks SEC timestamps. Six COIN input uses at the October 31, 2025 ranking were accepted October 31 00:12:04 UTC, versus provider October 30 20:12:04+00:00. They were public before the signal but violate a literal previous-day UTC acceptance interpretation. Preserve this discrepancy; do not call the archived engine intrinsically timestamp-safe. The report's conservative signal timestamp is 21:01 UTC, after both winter/summer market closes; bars are conservatively available by 21:00 UTC.

## Prices, identifiers, actions and execution

| ticker | min | max | count |
| --- | --- | --- | --- |
| ANSS | 2025-01-31 | 2025-06-30 | 6 |
| AVB | 2025-01-31 | 2026-07-31 | 19 |
| CTRA | 2025-01-31 | 2026-04-30 | 16 |
| DAY | 2025-01-31 | 2026-01-30 | 13 |
| DFS | 2025-01-31 | 2025-04-30 | 4 |
| EA | 2025-01-31 | 2026-07-31 | 19 |
| HES | 2025-01-31 | 2025-06-30 | 6 |
| HOLX | 2025-01-31 | 2026-03-31 | 15 |
| IPG | 2025-01-31 | 2025-10-31 | 10 |
| JNPR | 2025-01-31 | 2025-06-30 | 6 |
| K | 2025-01-31 | 2025-11-28 | 11 |
| WBA | 2025-01-31 | 2025-07-31 | 7 |

The table is the **actual decision-window** missing series list, not the archive's global failure list. Some failed names were no longer eligible by 2025 and require no new history. EA recovered successfully and was added only to a separately labeled reconstruction with unchanged results. AVB recovered but has a 2.793:1 vendor event in August 2026; adjustment economics are unresolved. The ten remaining names failed both Yahoo and Stooq probes. Responses are logged. No missing stock is implicitly certified as an ineligible investment.

Only required late-period baskets, qualifying September candidates and SPY were extended through October 9 using vendor OHLC and action records. No October month-end signal is generated; original historical features stay unchanged. Daily open price +cost is a modeled fill, not proof of actual order-book execution. Prior-20 quoted dollar volume participation is in `liquidity_exposure.csv`; vendor volume convention and removed-name liquidity remain uncertified. The actual baseline accounts have no held split/spinoff during this interval, checked independently, but WDC/SNDK pre-entry price continuity and universe corporate-action treatment still need primary reconciliation.

Dividends are actual archived/vendor ex-date amounts credited early on ex-date. For certification, obtain declaration/ex/record/payable dates and model a receivable until payable; do not silently call early cash reinvestment achievable. Delisting/merger economics are essential if a restored candidate enters. Historical identifiers must distinguish corporate events from ticker changes (including P/Everpure and SATS/ECHO). Industry codes are unavailable historically, so industry P&L, concentration and strongest-industry exclusion are explicitly blocked.

## What is needed to finish and costs

1. Resolve each exact missing input use in `pit_data_coverage.csv` using its original SEC accession: original filing/XBRL custom tags, revenue scope, quarter and comparator. Recover acceptance times for the two Citigroup accessions. SEC APIs are public, with no per-call fee; this run incurred no purchase.
2. Obtain the listed removed-name daily OHLCV through each membership exit plus 126-session warmup and any actual held exit/consideration. Primary merger announcements and SEC filings can establish economics; a survivorship-complete vendor such as CRSP can supply prices, permanent identifiers, distributions and delisting returns. CRSP public documentation was recovered, but no public verified quote for the needed slice was established: **commercial price unknown / quote required**, not an invented estimate.
3. Obtain primary historical S&P additions/removals with announcement and effective timestamps, original security identifiers, historical industry assignments, and dividends/payable dates. S&P/vendor licensing may be required; no verified price was found.
4. Compare vendor bars to independent primary/action-adjusted histories, certify WDC/SNDK and AVB discontinuities, and validate auction fills/liquidity under the stated costs.

The connected FinancialDatasets SPY extension request was rejected because the connected account has zero credits. No paid request or credit purchase was authorized or performed; public Yahoo prices supplied the extension instead. No verified unit-price quote was returned. This is a provider/account limitation, not proof that commercial data cannot solve the gaps.

Reconciliation passed independently. Certified PIT portfolio experiments remain blocked. Do not confuse these statuses.

Ranking-gap triage identifies 943 security/date rows needing further competitor review after excluding observed, verified revenue/margin failures or nonpositive archived momentum. `ranking_gap_review.csv` preserves all 10,563 rows; `potentially_displacing_competitors.csv` narrows follow-up. This conservative triage is not full eligibility certification and does not require resolving every irrelevant missing bank margin. Regenerate with `python ranking_gap_review.py`.
