# Historical MSCI ACWI IMI universe: availability and completeness

Checked on 10 October 2026 for October 2022–September 2026: **48 monthly universes**.
Branch: `research/eodhd-acwi-imi-setup`. No investment-strategy changes, trades or
additional EODHD requests were made.

**Follow-up:** [SPGM historical ETF holdings proxy](SPGM_PROXY_REPORT.md) supersedes
the initial SEC/ETF coverage findings below. Importing public N-PORT filings
established 19 target-period observations (15 quarterly month-end SEC portfolios
plus four archived workbooks), with two earlier warm-up portfolios. There are
48 dates supported by a lagged public-portfolio convention, with 13–123 calendar
days of staleness; this is not contemporaneous monthly membership. Actual MSCI
membership and security-level historical GICS remain incomplete. The body below
records the initial source investigation before this import.

## Finding

The sources inspected do **not establish a complete reconstruction of actual
monthly MSCI ACWI IMI constituents**. Genuine public MSCI review-event data is
available, but a complete starting membership snapshot, the full between-review
event history, security-level identifier history and point-in-time GICS remain
missing. No full official monthly universe has been assembled or verified:
**0 of 48 months**. This is an observed completeness result for this investigation,
not proof that no other public archive exists.

An ETF-based research universe is possible in principle, but must be labeled an
**ETF holdings approximation**. The tested public archive provides four usable
intra-month SPGM snapshots, not 48 month-end portfolios. ETF changes must not be
reported as MSCI additions/deletions, and current ETF holdings must not be
projected backwards onto companies that survived until today.

## July 10 Taiwanese records: resolved exclusion

The extraordinary Taiwan exchange closure is accepted from the independently
verified information supplied by the user. The original cached observations are:

| Security | July 9 close | July 10 OHLC / adjusted close | July 10 volume | Assessment |
|---|---:|---:|---:|---|
| Hon Hai `2317.TW` | 237.5 | All 237.5 | 0 | Consistent with a carried-forward placeholder |
| ASE holding company `3711.TW` | 677 | All 677 | 0 | Consistent with a carried-forward placeholder |

Both are invalid **as trading-session bars** on a confirmed exchange closure.
The adjacent July 13 records are separate observations, so the cache supplies no
evidence of a displaced July 13 bar or another correct trading date. Neither bar
is redated. The provider's precise generation mechanism remains unconfirmed.

Original CSVs remain byte-for-byte unchanged. Derived session-filtered inputs
exclude July 10 for both securities, giving **242 rows each**, matching TSMC's
242 rows and the corrected historical session calendar. The report preserves
each excluded observation, closure evidence, action, and original/output SHA-256
hashes. Zero volume on an open day alone does not cause exclusion.

These exports are under `research/eodhd_output/asia_corporate_actions/backtest_inputs/`.
They are session-filtered **provider raw prices**, not complete split/FX-adjusted
backtest datasets. No existing strategy input path was changed. AstraZeneca's
separate split-only OHLC output remains unchanged. The Korean July 31 moves remain
verified genuine market returns, preserving their full returns and true ranges.

## Sources actually inspected

| Source | Verified access and content | What it establishes | Completeness limit |
|---|---|---|---|
| [MSCI public review archive](https://www.msci.com/eqb/gimi/stdindex/index_review.html) | Retrieved all 32 Standard/Small Cap addition/deletion PDFs for 16 reviews, November 2022–August 2026 | Genuine MSCI constituent-change evidence, country/name lists, announcement and effective dates | Changes rather than full snapshots; no complete October 2022 baseline or all intervening events |
| [MSCI methodology](https://www.msci.com/index/methodology/latest/GIMI) | Retrieved August 2026 GIMI methodology, 192 pages; methodology landing page also offers archives | Large + Mid + Small make up IMI; quarterly maintenance, ongoing corporate events and early deletions/inclusions must be handled | Methodology is not a dated constituent/security master; latest rules cannot simply be applied retrospectively |
| [State Street SPGM](https://www.ssga.com/us/en/individual/etfs/spdr-portfolio-msci-global-stock-market-etf-spgm) | Retrieved fund page and current holdings XLSX; benchmark is MSCI ACWI IMI | Real ETF portfolio records and an appropriate IMI-tracking fund candidate | Fund portfolio is not full index membership |
| [Archived SPGM holdings](https://web.archive.org/cdx/search/cdx?url=www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spgm.xlsx&output=json&from=20221001&to=20260930&filter=statuscode:200&collapse=timestamp:6) | Four successful historical holdings captures; downloaded and inspected all four | Actual historical ETF observations, with internal holdings dates and identifiers | Four intra-month dates; no complete month-end series |
| SPDR ACWI IMI UCITS / SPYI candidate | Tested publisher page redirected to an investor-information/prospectus page; two candidate factsheet paths returned 404 | Remains a relevant fund/archive candidate to resolve | No historical UCITS holdings file verified here; URL failures do not prove that holdings are unavailable |
| [iShares ACWI](https://www.ishares.com/us/products/239600/ishares-msci-acwi-etf) | Public fund page and holdings description accessible | Another historical ETF proxy candidate | ACWI large/mid-cap exposure is not ACWI IMI; does not supply the small-cap universe |
| [SEC N-PORT datasets](https://www.sec.gov/data-research/sec-markets-data/form-n-port-data-sets), [readme](https://www.sec.gov/files/nport_readme.pdf), [form](https://www.sec.gov/files/formn-port.pdf) | Public catalog lists 16 quarterly ZIP links from 2022Q4 through 2026Q3; schema and reporting instructions retrieved | Historical public U.S.-registered fund holdings, including issuer information and nullable CUSIP/ISIN/ticker identifiers | Holdings are ETF observations, not MSCI membership; bulk files were not imported and per-fund coverage was not verified |
| [WRDS CRSP](https://wrds-www.wharton.upenn.edu/pages/about/data-vendors/center-for-research-in-security-prices-crsp/) | Public product documentation accessible; direct CRSP site remained proxy-blocked | Licensed U.S./North American historical security/return data is a candidate for identity, corporate-event and delisting work | Not a freely obtained global MSCI constituent history; no authenticated rows accessed |
| [WRDS S&P Global](https://wrds-www.wharton.upenn.edu/pages/about/data-vendors/sp-global-market-intelligence/) | Public Compustat Global catalog shows global fundamentals/prices and ISIN/SEDOL/ticker/SIC identifiers | Candidate licensed crosswalk and historical-security support | Actual table coverage, inactive-security completeness, GICS history and permissions require verification; broad catalog date ranges are not evidence of usable history |
| [WRDS ETF Global](https://wrds-www.wharton.upenn.edu/pages/about/data-vendors/etf-global/) | Catalog lists ETF Global Constituents, date range 2012-01-03–2026-10-01 | Candidate institutional route to a more extensive ETF holdings proxy | Dataset access is not established; fund-specific frequency/completeness unknown; still not MSCI membership |
| [WRDS MSCI](https://wrds-www.wharton.upenn.edu/pages/about/data-vendors/vendor-partner-msci/) | Retrieved public catalog describing historical ESG/climate/sustainability data | Genuine MSCI data products exist on WRDS | This catalog is not evidence of ACWI IMI historical index constituents; ESG rating universe must not be substituted |
| [OpenFIGI](https://www.openfigi.com/), [documentation](https://www.openfigi.com/api/documentation) | Public documentation retrieved; site describes free/open FIGI symbology and metadata | Useful security/share-class/listing identifier mapping candidate | Identifier mapping is not historical index membership, a global delisting ledger or dated GICS; no mapping API requests were made |

The MSCI modern review page embeds an `app2.msci.com` page that was blocked, but
the canonical `www.msci.com/eqb/...` public archive worked. A guessed legacy
ACWI IMI factsheet URL returned 404; that is not evidence that MSCI factsheets do
not exist. Public MSCI methodology/review data and State Street's benchmark
statistics were used instead.

## Official MSCI review evidence

Verified review pairs cover November 2022; February, May, August and November
2023–2025; and February, May and August 2026. Example documents:

- [November 2022 Standard changes](https://www.msci.com/eqb/gimi/stdindex/MSCI_Nov22_STPublicList.pdf): announced November 10, effective at the close of November 30.
- [August 2026 Standard changes](https://www.msci.com/eqb/gimi/stdindex/MSCI_Aug26_STPublicList.pdf) and [Small Cap changes](https://www.msci.com/eqb/gimi/smallcap/MSCI_Aug26_SCPublicList.pdf): announced August 12, effective at the close of August 31.

The inspected lists contain country-index headings and security names in
addition/deletion columns. None of the 32 PDFs has an ISIN or SEDOL field. GICS
appears in legal notices, **not as a per-security historical sector column**.
Security names, especially abbreviated names or share-line suffixes, are not a
safe permanent identifier.

Combining Standard and Small Cap change lists requires distinguishing a
size-segment transfer from a true IMI entry/exit. A security deleted from Small
Cap and added to Standard can remain in ACWI IMI. Also preserve the country's
historical developed/emerging classification and do not include frontier,
standalone, micro-cap or unrelated derived-index changes merely because they
appear in an archive. A deletion does not establish that a company delisted.

Quarterly changes alone do not recover October 2022 membership or mergers,
bankruptcies, spin-offs, early inclusions/deletions and security conversions that
occur between reviews. Carrying those quarterly lists forward would leave
unknown monthly membership errors. Announcements must be applied on their
effective dates, with the information-publication time retained for backtests.

## ETF archive findings

| Archive capture | File's internal holdings date | Holdings records parsed | Sector field |
|---|---|---:|---|
| 2024-04-07 | 2024-04-04 | 2,747 | `-` in every record |
| 2025-03-06 | 2025-03-05 | 2,878 | `-` in every record |
| 2026-04-17 | 2026-04-16 | 3,007 | `-` in every record |
| 2026-08-20 | 2026-08-18 | 2,975 | `-` in every record |

The records have Name, Ticker, Identifier, SEDOL, Weight, Shares Held and Local
Currency. Identifier and SEDOL are present in these parsed records, but the
generic Identifier column must be interpreted by security type; it is not an
MSCI security ID. Parsed portfolio-record counts are not validated counts of
unique ordinary-equity constituents: cash, derivatives, ADRs and duplicate share
lines require their own classification.

The current retrieved workbook is dated October 8, 2026, **outside** the target
period; it is not used as September 2026 membership. The publisher separately
reports 2,866 fund holdings as of October 8 and 8,036 benchmark holdings as of
September 30. The differing dates preclude an exact overlap calculation, but the
fund plainly does not offer a complete index constituent enumeration. Tracking
the index's return is different from holding every security in the index.

The exact holdings-URL CDX query found four capture months out of 48. A broader
publisher fund-data prefix query returned the same four holdings captures, four
NAV-history captures and four premium/discount-history captures; the latter
eight are not constituent files. The tested queries did not establish a complete
UCITS holdings archive. This is a bounded archive search, not an exhaustive
enumeration of every past publisher URL.

None of the four verified holdings dates is a month-end date. Therefore verified
complete month-end ETF proxies are also **0 of 48**, although four intra-month
proxy observations are available. Archive capture date must never be used as
the holdings as-of date. Nor should a later portfolio be used to fill an earlier
month: that would add look-ahead and survivorship bias.

## SEC and other security datasets

The retrieved Form N-PORT instructions specify that holdings for the third
month of each fund's fiscal quarter are public upon filing, while identifiable
first- and second-month reports are not intended to be public. Filing follows
the quarter with a stated deadline of 60 days. Thus 16 quarterly ZIP links do
not establish 48 public monthly portfolios for SPGM. ZIP publication periods
also do not equal holdings observation periods: September 2026 portfolios may
not yet have been publicly filed on October 10. Amendments and fund series IDs
must be resolved before counting distinct holdings dates.

The readme's FUND_REPORTED_HOLDING and IDENTIFIERS tables can support security
joins. Their nullable identifiers, issuer LEIs/CUSIPs, investment categories and
fund records are useful evidence, but investment categories are not historical
GICS sectors. Historical holdings can preserve a company that later delisted
when the fund actually held it; they do not prove all index members or a
delisting's effective date and terminal return.

CRSP, Compustat Global and broader institutional security masters can fill parts
of an identity/return/corporate-action history under an appropriate subscription.
They cannot turn a portfolio proxy into exact MSCI membership without index
membership data. The observed WRDS MSCI catalog concerns ESG data; no entitlement
to historical index files is implied. OpenFIGI helps identify instruments but
cannot manufacture past membership or classifications. Tickers should never be
used alone across exchanges, share classes, renames or ticker reuse.

## Reconstruction requirements and completeness

| Requirement | Evidence obtained | Remaining gap |
|---|---|---|
| Full starting universe at/before September 30, 2022 | No complete official snapshot | Required to establish October 2022 membership |
| Monthly actual constituents, 48 dates | 0 full verified snapshots | All 48 remain incomplete as official universes |
| Scheduled additions/deletions | 16 official Standard/Small Cap review pairs | Stable IDs and segment-transfer reconciliation still required |
| Between-review membership events | Methodology documents event handling | Complete historical event ledger not obtained |
| Delisted companies and outcomes | Public deletion names; partial historical ETF observations | Deletion reason, listing histories, delisting dates/returns and full coverage missing |
| Security identifiers | ETF generic Identifier/SEDOL; SEC nullable identifiers; OpenFIGI documentation | Dated MSCI-ID ↔ ISIN/SEDOL/FIGI/listing/share-class crosswalk not assembled |
| Sector classifications | GICS framework documented | Dated security-level GICS absent; all sampled ETF sector fields blank |
| Legal/reuse rights | Public pages, filings and archive observations accessible | Public access is not permission for a redistributed or derived full MSCI constituent database |

The MSCI review PDFs state that use of MSCI products/services/information
requires a license. No full-constituent license, paid vendor access or archive
redistribution right has been obtained or assumed. Downloaded PDFs and holdings
are retained only in Git-ignored research output; no constituent datasets were
committed or published. Do not bypass publisher access controls or copy an
unlicensed third-party list merely because it is downloadable.

For an **actual MSCI** reconstruction, obtain either licensed dated constituent
files for all 48 month ends or a complete baseline plus the full effective event
ledger. Retain permanent security and listing IDs, country/size-segment history,
historic GICS, deletions and delisted instruments. Validate counts and set
differences against independent MSCI checkpoints. Historical prices for momentum
warm-up must precede October 2022 membership observations as needed.

For an explicitly labeled **ETF proxy**, first obtain and verify all dated fund
portfolios, normalize cash/derivatives/ADRs and share classes without changing
economic exposure, and use historical rather than current security and sector
mapping. Report missing months and incomplete small-cap coverage; do not fill
them silently or call ETF turnover MSCI index turnover. No proxy has been wired
into the existing investment strategy.

## Local evidence and verification

The Git-ignored `research/eodhd_output/universe_research/` directory contains
source access logs, the 32 retrieved review PDFs and extracted text, four archived
holdings workbooks, SEC documentation, inspected provider pages, metadata and
`historical_universe_availability.json`. `monthly_universe_completeness.csv`
enumerates all 48 required months and distinguishes full membership, scheduled
review evidence and intra-month ETF observations. It asserts no fabricated
monthly constituents.

The revised Asian quality report and audit remain at
`research/eodhd_output/asia_corporate_actions/combined_data_quality_report.md`
and its JSON companion. All **28 research tests passed**, including closure-date
exclusion, raw-observation preservation, no automatic removal of open-day
zero-volume bars, genuine extreme-return classification and corporate-action
normalization. SHA-256 checks confirmed original cached price files, AstraZeneca's
prepared CSV and EODHD request ledgers were unchanged. Report generation was
tested with network connections blocked.

Research-domain additions were saved in the environment configuration draft.
Most public source reads now work in the current instance; direct CRSP and the
embedded MSCI app2 endpoint remained blocked. Review/save and publish the draft
in environment settings to retain the research access configuration for future
tasks; draft persistence is not proof of publication or new-task restoration.
