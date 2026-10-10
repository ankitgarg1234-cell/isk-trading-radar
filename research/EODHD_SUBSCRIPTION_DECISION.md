# EODHD subscription purchase decision

**Decision: the $19.99 plan is a useful long-history price acquisition product, not a complete backtest-readiness solution. Do not purchase automatically.** A purchase cannot presently be justified by a verified forecast of fully ready securities; the verified post-recovery count remains zero.

## Verified official plan and entitlement

Checked October 10, 2026 against the provider's current official pages, preserved with source hashes in ignored `recovery_316/public_sources/`.

| Capability | Existing Free | $19.99 personal plan |
|---|---|---|
| Exact plan | Free Package / API account `free` | **Historian — EOD Historical All-World** |
| Monthly USD price | $0 | **$19.99**, billed monthly; personal use, minimum one month; tax/currency checkout can differ |
| Advertised history | Past year | **30+ years** advertised, actual symbol-specific depth varies |
| Daily budget | **20 API units**; current account also has **500** extra credits | **100,000 API units/day**, reset midnight GMT |
| Rate | Pricing table lists **20 requests/minute** for Free | **1,000 requests/minute** advertised; honor actual response headers/Retry-After |
| OHLCV + adjusted close | One year, except explicitly documented demo symbols | US and international EOD, includes FOREX; stock history can precede listing changes under renamed symbols |
| Dividends/splits | One-year history, support activation may be required | Included, one unit each per symbol/query |
| Current GICS/General fundamentals | Demo access is not general account entitlement | **Excluded**: Fundamentals Data Feed or All-in-One required for general access |
| ID mapping | Official ID Mapping docs include Free | Included, **one unit/request**, current mapping is not a historical listing database |
| Trading-hours/holiday endpoint | Not listed in the endpoint's included plans | **Excluded** per endpoint documentation: EOD+Intraday All-World Extended or All-in-One |
| Delisted prices | Free time-depth restriction applies | Regular EOD endpoints support found delisted symbols, without a guarantee for every historical security |
| Complete merger/delisting payout ledger, historical GICS and point-in-time FX clocks | Not established | **Not guaranteed by this plan** |

The live account shows 14 daily units remaining and 500 extra credits after the bounded six-unit experiment. Extra credits are quota, not permission to access paid datasets or expand the free historical window. The official limits page explains that a prior-day usage timestamp persists until the first charged request after midnight; our first SPY probe reset the counter and the final usage check confirms today's counters. The official limits article's generic 1,000/minute wording differs from the pricing table's Free 20/minute; use the lower Free rate and live headers rather than assuming the paid ceiling.

No configured-account Fundamentals, holiday, technical or intraday paid request was attempted. Public-demo Apple/Amazon/Tesla General and EOD histories are a narrowly documented exception, not a general free-account coverage claim.

## Markets, identifiers, FX and delistings

The exchange-list documentation advertises **70 supported exchanges as of August 2026**. The separate v2 calendar documentation refers to **73** exchange-details codes; these are different APIs and do not prove 73 EOD price markets. US is a composite suffix covering venues, not a MIC. Current US active/deleted catalogues and previously cached KO/TW lists confirm native Korean/Taiwanese naming; operating MIC and current currency need effective-date evidence before historical use. All other required primary-market mappings remain to be verified against exchange catalogues rather than inferred from issuer country.

Among the original 316, **313 have provider-reported exact-ISIN candidates**, **306 single signatures**, seven multiple signatures; three unmatched identifiers are Carnival, DuPont and Exxon Mobil. Among all **4,236** historical lines, **2,072** match the sampled US/KO/TW catalogues (1,952 single signatures, 120 multiple). These counts do not establish symbol-specific long-history price coverage, independently correct ADR identifiers, corporate-event completeness or subscription access to other APIs. Targeted ISIN queries for the three priority catalogue misses find only non-US alternatives: Carnival CVC1.F/STU, DuPont 6D81.F/XETRA/STU and Exxon Mobil 0R1M.LSE/XONA.XETRA/F/STU/XXON.TO. They supply neither verified historical primary-market dates nor currency/representation equivalence, so no foreign tape is substituted for CCL/DD/XOM. Counting those query results gives 316/316 priority identifier candidates and 2,075/4,236 sampled provider identifier candidates; none is a full-price or backtest-readiness count. The unqueried native markets may cover many of the unmatched 2,164 catalogue identifiers; no provider-wide coverage percentage is invented.

The official FOREX page lists **KRW** and **TWD**, and EOD supports currency symbols/pairs. Their existence does not verify January 2021 lookback, quote direction, major-unit scaling or observable daily fixing times. A full EURUSD demo is cached but is not a substitute for KRW/USD or TWD/USD and is not an admitted execution tape. Use explicit documented pairs, preserve base/quote metadata, and validate release timing and five-day freshness at each stock open/close.

Splits cost one unit; raw EOD OHLC is unadjusted, `adjusted_close` includes splits/dividends, and volume is split-adjusted. Do not apply a split factor twice to volume. Reconcile a fixed split-only OHLC coordinate and coherent TR basis; the optional Technical `splitadjusted` endpoint costs **five** units and does not repair missing action/accounting proof by itself. Adjusted closes are recomputed when dividends arrive, so freeze/version data and document the effect of the chosen vintage.

The dividends endpoint includes ex-date plus optional declaration, record, payment dates, unadjusted amount and currency. Its own documentation says declaration/payment fields can be missing on international exchanges, particularly Korea/India. Therefore buying this feed does not guarantee the payment/knowledge timestamps needed for cash accounting. Never infer dividend events from adjustment ratios or fabricate intraday payment clocks.

Delisted discovery uses the exchange symbol endpoint with `delisted=1`, which returns **only inactive** symbols; merge with a separately obtained active list while retaining distinct identifiers/effective intervals. Documentation says delistings after 2018 can have EOD/fundamentals/dividends/splits, before 2018 EOD only; after 2021 intraday may also exist if separately entitled. This is product-level capability, not evidence for each inactive SPGM line. Rename history is US-only; a renamed series can live under the new symbol. Neither surviving adjusted prices nor a terminal vendor close proves merger consideration, recovery value or a correct delisting return.

## Other products and permissions

Current fundamentals/GICS: **Fundamentals Data Feed $59.99/month**, ten API units per request; it is a separate product and its generic Sector field is not GICS. Full EOD+fundamentals+holiday coverage is explicitly included in **All-in-One $99.99/month**. EOD+Intraday All-World Extended is **$29.99/month** and includes the documented exchange-details/holiday API but does not establish general fundamentals entitlement. Do not assume two separately priced personal products can be stacked under one key without provider confirmation. Marketplace corporate-events/news products are separately purchased and are not demonstrated replacements for a complete historical merger/delisting ledger.

Our permitted current public GICS crosswalk already recovers 290 priority names, so do not purchase fundamentals solely for those same labels. Free `exchange_calendars` plus actual exchange holiday/closure evidence may avoid purchasing a calendar endpoint. Historical issuer filings and exchange notices remain necessary even with All-in-One. Provider personal plans are for private use; commercial/professional reuse requires a separately quoted license. No raw licensed data is committed or redistributed. EODHD's own disclaimer describes aggregated/non-exchange pricing; cross-check suspicious native-market records against independent legal sources before research use.

## Incremental readiness, volume and costs

**Verified additional fully ready after a paid upgrade: unknown, not 313 or 316. Currently verified: zero.** 313 is a candidate-contract count, three have directly observed full 2021–2026 price spans, and no newly paid subscription was tested. No positive minimum ready count is justified because listing/action/clock/accounting gates still fail. The all-world product can plausibly remove history restrictions for validated mappings but cannot make this subset a faithful universe.

One full EOD/splits/dividends request per distinct verified listing is normally enough to retrieve a date range; multi-listing histories and query pagination can increase requests. Base cost formula: **3 × (L + 12) + F + 2E + M + 10G + 5T** API units, where L is actual stock listing histories, F required FX series, E newly queried active+inactive exchange catalogues, M identifier queries, G fundamentals requests under a separately entitled product, and T optional technical normalization requests. Calendar API calls, if separately entitled, add one per request. Cached catalogues should be reused. Failed symbol lookups are charged; build a validated request manifest first.

For the 313 mapped priority candidates, **977** base requests/units (3×313 + 36 references + two candidate FX pairs), assuming one listing each. For all 316 conditional paths, **986**. Adding current fundamentals for 26 still-unclassified priority names would add **260 units and 26 physical requests**, only if the product is available and those contracts are valid. Unknown native contract corrections remain extra work. At a conservative two requests/second the 986-request data-only batch is about **8.2 minutes**; at one/second **16.4 minutes**, excluding validation, retries and metadata engineering. These are planning calculations, not observed completion times.

If all 4,236 securities had one complete listing path, base EOD/action/reference requests would be **12,744** before FX/catalogues/identity queries. At two/second this is **1.77 hours**; at one/second **3.54 hours**. Hypothetically obtaining fundamentals for every security adds **42,360 units**, yielding **55,104** before other requests, within the advertised 100,000/day paid budget but requiring fundamentals entitlement. Actual L, F and available history count remain unverified; IPOs, migrations, renamed/delisted paths and missing events can alter these estimates.

Observed Apple/Amazon/Tesla JSON averages **174,496 bytes per 1,442-bar tape**, gzip **37,295 bytes**. Extrapolating only that measured US format to 328 stock/reference tapes gives about **57.2 MB raw / 12.2 MB gzip**; 4,248 tapes give **741.3 MB / 158.4 MB**, excluding action/catalogue/metadata/FX files. These are conditional volume estimates, not promised foreign-market row counts or actual downloaded full-universe data.

## Purchase recommendation

Do the free metadata/clock/calendar/action adapter work first, preserving the 290 current-GICS flags, and reconcile the three recovered tapes as a small input-validation pilot. Confirm that the required historical listing and international dividend/event evidence can be legally obtained. Then, if the owner approves, one personal **$19.99 month** is the lowest advertised EOD price product for bulk long-history acquisition; verify needed contracts and edge cases before downloading thousands of paths. It is **not sufficient on its own** to make a credible full-global backtest executable. Current GICS for the remaining international/non-S&P lines, historical listing/ADR lifecycle evidence, FX observation/release clocks, calendars, and corporate-event accounting remain external/engineering blockers. Further commercial, fundamentals or event-data costs are **unknown** until their sources/permissions are verified. No purchase was made.

## Official sources

- [Pricing and included products](https://eodhd.com/pricing).
- [EOD lookback, adjustments, symbols and demo access](https://eodhd.com/financial-apis/api-for-historical-data-and-volumes).
- [API quota, endpoint costs, reset semantics and rate limits](https://eodhd.com/financial-apis/api-limits).
- [Dividends/splits fields and international timestamp gaps](https://eodhd.com/financial-apis/api-splits-dividends).
- [Exchange/symbol lists and inactive-only behavior](https://eodhd.com/financial-apis/exchanges-api-list-of-tickers-and-trading-hours).
- [Delisted data](https://eodhd.com/financial-apis/delisted-stock-companies-data-2).
- [Fundamentals and explicit GicSector](https://eodhd.com/financial-apis/stock-etfs-fundamental-data-feeds).
- [Exchange hours/holiday API entitlements](https://eodhd.com/financial-apis/exchanges-api-trading-hours-and-stock-market-holidays).
- [FOREX symbols](https://eodhd.com/financial-apis/list-supported-forex-currencies).
- [Identifier mapping](https://eodhd.com/financial-apis/id-mapping-api-cusip-isin-figi-lei-cik-%e2%86%94-symbol).
- [Personal versus commercial use](https://eodhd.com/financial-apis/commercial-vs-personal-license-use).
- [Yahoo automated-collection restrictions](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html).
