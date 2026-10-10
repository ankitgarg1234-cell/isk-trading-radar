# SPGM 316 targeted recovery report

**SPGM historical ETF holdings proxy; not official MSCI ACWI IMI constituents.**
Starting checkpoint: `7fd757d`. Original security cohort is fixed; no historical member is deleted, and the original full-universe audit is preserved.

**Original partial securities: 316. Fully backtest-ready after recovery: 0. Remaining partial: 316.** No portfolio backtest, subscription purchase, IBKR access or production-strategy change was performed.

## Successful repairs and remaining admission limits

- **Three complete observed price-date spans recovered:** Apple (`US0378331005`), Amazon (`US0231351067`) and Tesla (`US88160R1014`). Each public-demo EOD tape has **1,442 bars, January 4, 2021–September 30, 2026**, zero missing/unexpected XNYS-equivalent sessions and valid OHLCV/adjusted-close schema. Each has **690** bars through September 29, 2023.
- **290 current GICS backfills** prepared, spanning all eleven sectors. These are explicit `CURRENT_GICS_BACKFILL` approximations, **zero historically verified classifications**. The original resolver validates them for each observed monthly cutoff. **26** securities remain without admissible current GICS. There are **9,734 approximate security-month assignments** in the fixed cohort, only about 9.85% of the full target proxy’s 98,838 observations. This remains far below the global admission requirements. No historical correction was invented; no sourced applicable correction has been established for this recovery.
- **313/316 provider-reported exact-ISIN candidates**, including **306** with one observed listing signature and **7** with multiple signatures. Three have no match in the sampled catalogues: Carnival Corp, DuPont de Nemours Inc and Exxon Mobil Corp. Targeted one-unit ID queries return 2, 3 and 5 non-US aliases respectively; no historical US-primary equivalence is established. Thus all 316 have some provider-reported identifier candidate, not verified historical price coverage. This is metadata evidence, not proof of paid historical price depth or a historically effective listing.
- Three current demo General records independently match exact ISIN/CUSIP and explicit `GicSector`, Nasdaq and USD for Apple, Amazon and Tesla. Prelaunch SEC 10-K covers independently report their common-share tickers and Nasdaq registration: Apple filing October 28, 2022; Amazon February 3, 2023; Tesla January 31, 2023. These point observations do **not** establish all required 2021–2026 listing/effective intervals or corporate-event completeness.
- Apple dividend history adds **23** observed ex-dividend/declaration/record/payment-date records through September 2026. Its queried 2021–2026 split endpoint returns an empty list. This is a sourced vendor response, not an invented no-action ledger or independently complete merger/delisting history. Amazon/Tesla action demo endpoints were not called: the action documentation's demo footnote explicitly approves Apple.
- A EURUSD demo series adds **1,602** raw daily observations, passing raw schema. It is not an admitted FX tape: exact daily observation/publication clocks remain unverified and it supplies neither KRW/USD nor TWD/USD.

Full date-span recovery is a repaired requirement fragment. All three still lack the full evidence-backed split-only OHLC/total-return/accounting/vintage, historical listing, clock and action bundle required by the existing loader. In particular, raw Amazon/Tesla OHLC and an adjusted close cannot be mixed across splits or combined with another vendor's retrospectively adjusted OHLC without a verified share-coordinate reconciliation. No source series was stitched. The existing anomaly validator flags Amazon’s June 6, 2022 and Tesla’s August 25, 2022 raw/adjusted share-coordinate discontinuities for action-source review; it does not invent split ratios. Existing independently verified SK Hynix and Samsung Electro-Mechanics July 31, 2026 rebounds remain economic returns with zero review-required anomaly flags.

## Signal-input audit

For every original security, the CSV identifies each original/new source, earliest/latest dates, full-seed and observed-membership gaps, initial cutoff, available bars, and exact 63/126/252-session, EMA200 and ATR shortfalls. Detailed per-cutoff missing-date lists are ignored in `security_recovery_details.json`.

| Input | Required bars | Original initial gaps | Remaining initial gaps |
|---|---|---|---|
| momentum63 | 64 | 5 | 5 |
| momentum126 | 127 | 11 | 11 |
| momentum252 | 253 | 269 | 266 |
| ema200_minimum | 200 | 14 | 14 |
| atr14_minimum | 15 | 4 | 4 |

A 252-session return needs 253 closes. Initial dates include September 29, 2023 only where the security actually appeared in the prior-public September universe; later entrants use their actual first observed cutoff. **253** original securities lacked exactly **42** observations for their initial 252-session window; four lacked the whole 253-bar window. **47** had sufficient raw dates at their later initial cutoffs. Sufficient counts are not verified total-return/ATR inputs. The recovered tapes overlap their original caches on 963 sessions each; the largest observed close difference is 0.004736%, a useful cross-source check that does not establish earlier split coordinates or event completeness. Missing sessions inside a window are checked separately, so extra older bars cannot hide holes. The original EMA implementation seeds from the first observation; meeting a 200-bar minimum does not repair a missing fixed January 2021 seed history.

Calendar-only gaps through September 2026 are shown separately from gaps through the last observed membership cutoff and within membership months. Missing dates after an unverified delisting/IPO cannot automatically be called a provider error or granted a lifecycle exemption. US dates use installed XNYS-equivalent schedules as diagnostics; historically verified MIC/time-zone and publication-clock evidence remain separate. Asian calendar diagnosis preserves the confirmed Taiwan July 10, 2026 closure; Korean national-holiday discrepancies still require venue confirmation.

## Country and sector representation

Country is historical SEC issuer country, not exchange country. The fixed cohort has **312 USD-labelled lines**, two KRW and two TWD lines; currency and venue effective intervals remain unverified. No verified non-USD FX tape is present.

| Issuer country | Priority securities | Fully ready |
|---|---|---|
| BR | 1 | 0 |
| CW | 1 | 0 |
| GB | 1 | 0 |
| KR | 2 | 0 |
| PA | 1 | 0 |
| TW | 2 | 0 |
| US | 308 | 0 |

| Current GICS sector | Approximate securities |
|---|---|
| Communication Services | 15 |
| Consumer Discretionary | 26 |
| Consumer Staples | 25 |
| Energy | 16 |
| Financials | 38 |
| Health Care | 40 |
| Industrials | 43 |
| Information Technology | 49 |
| Materials | 12 |
| Real Estate | 12 |
| UNRESOLVED | 26 |
| Utilities | 14 |

Current backfills cover 289 US issuers and one Curaçao issuer. Korean/Taiwanese native lines remain sector/FX blockers. The priority group is dominated by US listings and price availability; it is not a globally representative or approved trading universe.

## Reference instruments

| Reference | Cached bars | First | Last | Prelaunch | Required | Missing 2021 sessions | Fully ready |
|---|---|---|---|---|---|---|---|
| SPY | 244 | 2025-10-10 | 2026-09-30 | 0 | 254 | 1198 | False |
| XLB | 964 | 2022-11-28 | 2026-10-01 | 211 | 253 | 479 | False |
| XLC | 964 | 2022-11-28 | 2026-10-01 | 211 | 253 | 479 | False |
| XLE | 964 | 2022-11-28 | 2026-10-01 | 211 | 253 | 479 | False |
| XLF | 964 | 2022-11-28 | 2026-10-01 | 211 | 253 | 479 | False |
| XLI | 964 | 2022-11-28 | 2026-10-01 | 211 | 253 | 479 | False |
| XLK | 964 | 2022-11-28 | 2026-10-01 | 211 | 253 | 479 | False |
| XLP | 964 | 2022-11-28 | 2026-10-01 | 211 | 253 | 479 | False |
| XLRE | 964 | 2022-11-28 | 2026-10-01 | 211 | 253 | 479 | False |
| XLU | 964 | 2022-11-28 | 2026-10-01 | 211 | 253 | 479 | False |
| XLV | 964 | 2022-11-28 | 2026-10-01 | 211 | 253 | 479 | False |
| XLY | 964 | 2022-11-28 | 2026-10-01 | 211 | 253 | 479 | False |

SPY now has a **244-bar partial tape**, October 10, 2025–September 30, 2026, from one account-funded request asking for January 2021 onward. It has zero prelaunch bars and **1,198** missing 2021–2026 candidate sessions. The request empirically confirms the free lookback restriction. All eleven sector ETF tapes remain at 964 cached bars (including October 1, 2026 outside the target end), 211 prelaunch bars, **42 additional prelaunch sessions** needed, and **479** missing sessions in the fixed 2021 seed span. SPY also needs 254 prelaunch bars for the original two-close regime logic.

Official SSGA downloadable SPY/XLK spreadsheets were inspected. NAV histories contain Date/NAV/Shares Outstanding/Total Net Assets; the SPY premium/discount file contains Date/Premium/Discount. They do not contain daily trading OHLCV or a validated total-return stock-price tape and cannot substitute for SPY or fill ATR inputs. The S&P index and VTI were not substituted. Yahoo's published terms prohibit automated collection without express prior permission; no new Yahoo prices were requested. Stooq terms access failed, so no Stooq data was acquired under an assumed permission. Existing legacy data remains cached with unresolved new-use/adjustment provenance.

## Identity and classification method

Provider-reported checksum-valid ISIN -> current symbol -> SEC current ticker/CIK -> identical CIK in the already cached, rights-documented current S&P 500 GICS table. Only a unique active US symbol of Common Stock type is accepted. No SIC/NAICS/description inference, issuer-name-only join, historical membership substitution or current-listing-as-historical-proof occurs. Evidence includes the active listing record, SEC record, current classification row and source hashes. All backfills retain current-source observation timestamps, taxonomy-source snapshot version and approximation limitations. The underlying GICS release version is not supplied by the public table; only its explicit original eleven-sector labels are used.

Both `STRICT_PIT` and `EXPLORATORY_CURRENT_GICS` remain unchanged. Strict mode continues to reject current assignments. Current-sector sensitivity is presently **290 uncertain security classifications**; quantitative changes to rankings, weights and performance are unknown because validated inputs are incomplete and no strategy replay is authorized. Individual-current-sector and taxonomy-history corrections need sourced review before eventual execution; current labels are never called historical truth.

Across all 4,236 historical lines the sampled active/delisted US and active Korean/Taiwanese catalogues produce **2,072** exact-ISIN candidates: **1,952** single signatures and **120** multiple signatures. The other **2,164** did not match these sampled catalogues; this does not mean EODHD lacks their unqueried primary markets. Cross-listed ordinary shares and depositary receipts require provider identifier/representation verification before assigning prices. Current vendor identifier assertions are not independent share-ratio or lifecycle proof. Original ADR/ordinary identities, AstraZeneca normalization and Taiwan closure exclusions are preserved.

## Readiness and remaining actions

Every security remains PARTIALLY_READY. Per-security required actions are in `SPGM_316_RECOVERY_INVENTORY.csv`: verify historical listing/currency/representation intervals; recover warm-up/session gaps; reconcile split-only OHLC, coherent TR vintages and source clocks; obtain complete split/dividend/payment/merger/delisting evidence; source unresolved GICS and documented corrections; verify native calendars/time zones; recover timestamped native-to-USD FX where needed. Shared source/clock/adjustment/calendar/licensing adapters should be repaired before hundreds of individual downloads.

High-priority gaps remain for Microsoft, NVIDIA and Micron (2021 seed/initial 252-session warm-up plus action/accounting provenance), SK Hynix and Taiwanese TSMC (long history, sector, native FX, dated listings/calendars), and the distinct TSMC ADR line. Samsung/Hon Hai ordinary prices cannot repair SPGM's depositary-receipt lines. Apple/Amazon/Tesla price repair is not a fully ready security repair.

**No defensible faithful five-stock portfolio experiment is currently available.** Even a hypothetical fully repaired 316-security subset fails the unchanged **450-valid-stock-signal safeguard**, in addition to sampled global-universe and country/sector coverage gates. The recovery cohort cannot silently replace the 2,505–2,910-stock target monthly proxy (2,403–2,910 across all 48 months).

## Evidence and reproducibility

Offline audit: `python -m research.spgm_316_recovery`. Public demo acquisition is an explicit separate command: `python -m research.spgm_recovery_sources`; it enforces documented symbols, caches responses and caps requests. Do not run the portfolio continuation command.

Ignored evidence directory: `/workspace/isk-trading-radar/research/eodhd_output/spgm_proxy/historical_backtest/recovery_316`. It holds complete date-gap diagnostics, checksummed price/action responses, 290 sector evidence records and `classification_records.json`, current provider catalogues, SEC 10-K cover evidence, public provider/rights documentation, issuer XLSX inspections, account summaries and both request ledgers. The original completeness inventory and all original price/holding sources remain unchanged. Git includes only code/tests and the small recovery inventory/reports, with no downloaded prices, source portfolios, raw provider catalogues or credentials.

The configured-account experiment used **ten physical API requests costing six units**: SPY EOD, two shared US catalogue calls, three targeted identifier lookups and four zero-unit usage checks. Separately, nine documented public-demo requests cost **zero configured-account units**; their nominal endpoint weights are logged. Final verified account: **free, 20 units/day, 6 used, 14 daily units remaining, 500 extra credits untouched**, counter date October 10, 2026. No entitlement is inferred from extra credits.

## Regression validation

150 research regression tests passed at this checkpoint, including twelve recovery tests. Original inventory hashes and 316-row/status/requirement invariants passed. Neither strategy nor admission rules were changed.
