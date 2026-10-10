"""Render checkpoint-specific recovery reports; no network or portfolio execution."""
import json,csv,gzip
from pathlib import Path
from statistics import mean

def clean_markdown(text):
    return "\n".join(line[4:] if line.startswith("    ") else line for line in text.splitlines()).rstrip()+"\n"

def main():
    P=Path('research/eodhd_output/spgm_proxy/historical_backtest/recovery_316')
    s=json.loads((P/'summary.json').read_text())
    assert (s['original_partial'],s['fully_ready'],s['remaining_partial'],s['recovered_full_session_spans'],s['current_gics_backfills']) == (316,0,316,3,290), 'Narrative checkpoint changed; review verified report facts'
    assert (s['provider_candidates']['priority316']['exact_isin_candidates'],s['provider_candidates']['all4236']['exact_isin_candidates']) == (313,2072)
    assert s['account']['quota']['remaining_units_today']==14 and s['account']['account_fields']['extraLimit']==500
    with Path('research/SPGM_316_RECOVERY_INVENTORY.csv').open()as f:rows=list(csv.DictReader(f))
    def table(headers,rs):return '\n'.join(['| '+' | '.join(headers)+' |','|'+'|'.join(['---']*len(headers))+'|']+['| '+' | '.join(str(v)for v in r)+' |'for r in rs])
    price_files=[P/'demo'/(x+'_US_eod.json')for x in ['AAPL','AMZN','TSLA']]
    raw=mean(p.stat().st_size for p in price_files);packed=mean(len(gzip.compress(p.read_bytes()))for p in price_files)
    report=f'''# SPGM 316 targeted recovery report

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

    {table(['Input','Required bars','Original initial gaps','Remaining initial gaps'],[(k,v,s['original_initial_shortfalls'][k],s['remaining_initial_shortfalls'][k])for k,v in [('momentum63',64),('momentum126',127),('momentum252',253),('ema200_minimum',200),('atr14_minimum',15)]])}

    A 252-session return needs 253 closes. Initial dates include September 29, 2023 only where the security actually appeared in the prior-public September universe; later entrants use their actual first observed cutoff. **253** original securities lacked exactly **42** observations for their initial 252-session window; four lacked the whole 253-bar window. **47** had sufficient raw dates at their later initial cutoffs. Sufficient counts are not verified total-return/ATR inputs. The recovered tapes overlap their original caches on 963 sessions each; the largest observed close difference is 0.004736%, a useful cross-source check that does not establish earlier split coordinates or event completeness. Missing sessions inside a window are checked separately, so extra older bars cannot hide holes. The original EMA implementation seeds from the first observation; meeting a 200-bar minimum does not repair a missing fixed January 2021 seed history.

    Calendar-only gaps through September 2026 are shown separately from gaps through the last observed membership cutoff and within membership months. Missing dates after an unverified delisting/IPO cannot automatically be called a provider error or granted a lifecycle exemption. US dates use installed XNYS-equivalent schedules as diagnostics; historically verified MIC/time-zone and publication-clock evidence remain separate. Asian calendar diagnosis preserves the confirmed Taiwan July 10, 2026 closure; Korean national-holiday discrepancies still require venue confirmation.

    ## Country and sector representation

    Country is historical SEC issuer country, not exchange country. The fixed cohort has **312 USD-labelled lines**, two KRW and two TWD lines; currency and venue effective intervals remain unverified. No verified non-USD FX tape is present.

    {table(['Issuer country','Priority securities','Fully ready'],[(k,v,0)for k,v in sorted(s['country_counts'].items())])}

    {table(['Current GICS sector','Approximate securities'],sorted(s['sector_counts'].items()))}

    Current backfills cover 289 US issuers and one Curaçao issuer. Korean/Taiwanese native lines remain sector/FX blockers. The priority group is dominated by US listings and price availability; it is not a globally representative or approved trading universe.

    ## Reference instruments

    {table(['Reference','Cached bars','First','Last','Prelaunch','Required','Missing 2021 sessions','Fully ready'],[(r['symbol'],r['rows'],r['first'],r['last'],r['prelaunch'],r['required_prelaunch'],r['missing_2021_sessions'],False)for r in s['reference_inputs']])}

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

    Ignored evidence directory: `{P.resolve()}`. It holds complete date-gap diagnostics, checksummed price/action responses, 290 sector evidence records and `classification_records.json`, current provider catalogues, SEC 10-K cover evidence, public provider/rights documentation, issuer XLSX inspections, account summaries and both request ledgers. The original completeness inventory and all original price/holding sources remain unchanged. Git includes only code/tests and the small recovery inventory/reports, with no downloaded prices, source portfolios, raw provider catalogues or credentials.

    The configured-account experiment used **ten physical API requests costing six units**: SPY EOD, two shared US catalogue calls, three targeted identifier lookups and four zero-unit usage checks. Separately, nine documented public-demo requests cost **zero configured-account units**; their nominal endpoint weights are logged. Final verified account: **free, 20 units/day, 6 used, 14 daily units remaining, 500 extra credits untouched**, counter date October 10, 2026. No entitlement is inferred from extra credits.
    '''
    report += '\n## Regression validation\n\n150 research regression tests passed at this checkpoint, including twelve recovery tests. Original inventory hashes and 316-row/status/requirement invariants passed. Neither strategy nor admission rules were changed.\n'
    Path('research/SPGM_316_RECOVERY_REPORT.md').write_text(clean_markdown(report))

    subscription='''# EODHD subscription purchase decision

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

    BYTE_ESTIMATE

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
    '''
    volume=f'''Observed Apple/Amazon/Tesla JSON averages **{raw:,.0f} bytes per 1,442-bar tape**, gzip **{packed:,.0f} bytes**. Extrapolating only that measured US format to 328 stock/reference tapes gives about **{raw*328/1e6:.1f} MB raw / {packed*328/1e6:.1f} MB gzip**; 4,248 tapes give **{raw*4248/1e6:.1f} MB / {packed*4248/1e6:.1f} MB**, excluding action/catalogue/metadata/FX files. These are conditional volume estimates, not promised foreign-market row counts or actual downloaded full-universe data.'''
    Path('research/EODHD_SUBSCRIPTION_DECISION.md').write_text(clean_markdown(subscription.replace('BYTE_ESTIMATE',volume)))
    roadmap=f'''# SPGM historical data acquisition roadmap

    Audit-only checkpoint following `7fd757d`. Do not start a backtest or substitute the recovery cohort for historical holdings. All original ranking, five-stock selection, sector rules, sizing/stops/exits/rotation and risk controls remain unchanged; both admission modes remain intact.

    ## Three scenarios

    {table(['Scenario','Verified fully ready','Data/identity coverage','Decision'],[
    ('A: existing + permitted free recovery','0 / original 316','3 full price-date spans; 290 approximate sectors; 313 catalogue candidates + 3 foreign-alias queries','Input research only; no faithful portfolio test'),
    ('B: $19.99 EOD Historical All-World','Unknown additional; zero demonstrated','316 provider identifier candidates; 313 catalogue paths; historical equivalence/depth unverified; 12 references to acquire','Potential price feed, not a complete readiness solution'),
    ('C: complete SEC-only proxy','0 demonstrated','4,236 union securities; sampled identifiers match 2,075 (2,072 catalogues + 3 queries); monthly 2,403–2,910','Requires full historical mapping/price/action/FX/classification/calendar work')])}

    ### Scenario A — no purchase

    Verified: three 2021–2026 tapes (Apple/Amazon/Tesla), all eleven sector ETF partial tapes, partial 244-bar SPY, 290 flagged current-GICS mappings across eleven sectors, three prelaunch SEC listing cover observations. Cohort issuer-country representation: {json.dumps(s['country_counts'],sort_keys=True)}. Current sectors cover 289 US and one Curaçao issuer; all 316 still partial. Remaining initial 252-session gaps affect 266 names; adequate raw counts do not establish validated momentum or stops. Microsoft/NVIDIA/Micron still need early dates; SK Hynix/TSMC native need long history, GICS/FX/lifecycle evidence. Samsung/Hon Hai depositary holdings are separate from cached primary prices.

    Cost **$0 new subscription**, six configured-account units used, nine no-account-quota public-demo calls. Shared adapters and evidence work remain; no honest completion time can be stated for inaccessible or unverified external sources. No faithful five-stock replay is scientifically defensible: reference inputs and accounting are incomplete, and 316 is below the original 450-valid-signal safeguard. A descriptive data-quality study is supported.

    ### Scenario B — one approved $19.99 month, not yet purchased

    313 priority securities have provider-reported candidate paths; seven have multiple signatures and three have no exact match. These are not verified paid historical coverage counts. Expected long-lookback benefit: the 2021 seed/window and SPY/ETF missing early prices, plus provider splits/dividends and native FX after contract/date checks. Observed real full-date proof remains three names. Issuer-country and sector denominators remain those above; unresolved 26 current sectors and native KR/TW inputs cannot be dropped. All foreign or inactive contracts need exact date and representation checks.

    Advertised cost **$19.99 personal/month**, conditional 986 base price/action/reference/two-FX requests for one path per 316 names; detailed estimates in `EODHD_SUBSCRIPTION_DECISION.md`. Calendar and fundamentals products are excluded. Free licensed GICS/classification crosswalks and calendars may avoid upgrades; otherwise a $59.99 fundamentals product, $29.99 EOD+Intraday alternative or $99.99 All-in-One may be relevant, without assuming stacking or sufficient historical event proof. Commercial/event/licensing costs remain unquoted. Downloading the subset alone cannot become a faithful global or even original-rule 316-stock backtest, regardless of data repair. No positive fully ready forecast is verified.

    ### Scenario C — the full historical proxy

    Preserve every confirmed historical security and original portfolio/publication/source filing, including added/deleted and inactive companies. The 4,236 security-line union represents 36 selection months with 2,505–2,910 confirmed equities per month; the 48 frozen source universes retain prelaunch/earlier history and span 2,403–2,910 equities. Current sampled US/KO/TW catalogues match 2,072 lines, including 120 multiple signatures. Other native markets remain unqueried, not proven unsupported. Even if all 2,072 sampled-catalogue union candidates had usable prices, they could not meet 95% of the smallest 2,505-stock target universe (at least 2,380 valid signals). More native catalogues/contracts are required. Country/sector completeness must be measured for every month and material country against the full universe, with original thresholds unchanged; all used instruments need resolved metadata. Public current sectors are allowed only with source, exact identity and approximation flags. Today's constituents must not replace historical membership.

    Conditional workload: 12,744 base price/action/reference requests if all securities had one listing path, before native FX, additional venues/catalogues, metadata and optional current fundamentals. Paid daily quota is unlikely to be the main blocker at this scale; legally permitted source completeness, historical contract paths, action/payment/terminal events and timestamps are the main unresolved requirements. Domestic investment-universe membership for the US comparator is also still unresolved at September 2023 and cannot be inferred from current S&P membership. No full-global cost or readiness count is verified.

    The exploratory backtest would become scientifically defensible only after the full historical proxy passes its unchanged sector/listing/price/FX/calendar/accounting gates, full-universe and material-country signal coverage and minimum breadth, and current-GICS sensitivity/limitations are reported. It would still be an ETF holdings proxy, not official MSCI ACWI IMI, and not a survivorship-filtered selection of available data.

    ## Cheapest practical ordered work

    1. **Freeze evidence and request manifest.** Original holdings, monthly dates and prices stay untouched. Keep this 316 priority queue and all 4,236 denominators. Reuse current US active/delisted and KO/TW caches; resolve the 7 ambiguous priority paths and three identifiers lacking US/KO/TW catalogue matches before paid price probes; targeted ID mapping already returns only multiple non-US aliases for them. Resolve additional native exchanges using exact identifiers, MIC, trading currency, ADR/ordinary identity and effective dates. Current mapping/IPO date alone never proves a prior-public historical interval.
    2. **Repair shared admission adapters at $0 where possible.** Validate complete native schedules and actual holidays/DST/early closes; preserve the Taiwanese closure and genuine Korean rebounds. Develop source-backed publication clocks, major-unit scaling, fixed split-only OHLC coordinates, one coherent TR vintage, dividend receivable/payment handling and material-event ledgers without inventing data. The three full demo tapes are a source-validation pilot, not a portfolio. Preserve current GICS flags and exact evidence hashes; assess current-taxonomy corrections/sensitivity before any later execution.
    3. **Resolve reference history legally.** SPY and all eleven sector ETFs need long-history stock-trading OHLCV, correct TR/actions and 2021 seed convention. Free issuer NAV/premium-discount downloads are insufficient. Authorized provider/owner-supplied histories can solve this; do not call Yahoo automatically under unsupported rights and do not use the index or VTI instead of SPY.
    4. **Conditional one-month EOD purchase decision.** Ask the owner only after contract/rights/edge-case evidence is reviewable. The minimum advertised long-EOD product is $19.99, not an automatic authorization to buy. Pilot both one US reference and native Korean/Taiwanese plus an inactive/changed-representation line after entitlement confirmation. Check full Jan2021 range, daily session equality, adjustments, action optional fields, FX base/quote and availability. Cache successes; record endpoint costs before failed requests and honor live pacing headers. Do not promise 313 ready names from a metadata match.
    5. **Fill remaining external evidence.** Source non-S&P/international current GICS without SIC/NAICS inference; consider paid explicit GicSector only if free rights-permitted exact-ID sources fail. Verify historical listing/representation and corporate events from issuer/SEC/exchange notices; source FX timing and delisted cash/merger consideration. For full global inputs, supply legally accessible all-country native listings and calendar confirmations. Subscription/marketplace depth does not replace this evidence.
    6. **Stop for review now.** No input bundle is published to the automatic runner. Do not execute `global_backtest_pipeline --resume`. A later user instruction must authorize the historical experiment after readiness, breadth and current-classification sensitivity are satisfied.

    ## Deliverables and validation

    - `SPGM_316_RECOVERY_INVENTORY.csv`: 316 rows, per-source price ranges, calendar gaps, every signal deficit, current/historical listing and GICS flags, FX/calendar gaps, remaining requirements and precise repair tasks.
    - `SPGM_316_RECOVERY_REPORT.md`: fixed-cohort counts, successful partial repairs, all twelve references and source limitations.
    - `EODHD_SUBSCRIPTION_DECISION.md`: official current entitlement/plan comparison, verified candidate counts versus unknown price/readiness counts, request/volume/time/cost calculations and exact source URLs.
    - Ignored `{P.resolve()}`: all raw histories and provider/SEC/issuer documents, current-sector overlays and complete missing-date diagnostics. No credentials, raw licensed prices or catalogue downloads are in Git.
    '''
    Path('research/SPGM_DATA_ACQUISITION_ROADMAP.md').write_text(clean_markdown(roadmap))
    print('Reports generated; recovery inventory rows',len(rows))

if __name__=='__main__':main()
