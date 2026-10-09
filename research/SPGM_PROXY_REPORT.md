# SPGM historical ETF holdings proxy

Research checked on 10 October 2026 (Europe/Stockholm). Target: October 2022–September 2026.
Series `S000036082`; registrant CIK `1168164`. **This is an ETF portfolio proxy, not official MSCI ACWI IMI constituents.**

## Findings

Retrieved **19 distinct target-period snapshots**: 15 public SEC N-PORT portfolios and four archived publisher workbooks. Two earlier SEC observations are retained separately for initial availability. The 21 observations contain 57,532 position records, not unique companies.

Observed portfolios cover **18/48 months**; 30 months have no direct portfolio observation. There are 15 month-end observations, all filed later. **0/48 contemporaneous month-end portfolios were verifiably public at their selection date.**

A latest-public-portfolio convention supplies **48/48 lagged selection dates**, including the June 2022 warm-up. Age is **13–123 calendar days**. With a maximum age of 31/62/93/123 days, support falls to **4/21/35/48 dates** respectively. These are date-availability counts, not claims that all security mappings, sectors or backtest inputs are ready.

All security-level historical GICS classifications remain missing. Quarterly positions and archived tickers preserve earlier holdings, but cannot reconstruct every intervening holding, actual MSCI additions/deletions, or the full set of delisted index members.

## Sources and retrieval completeness

[SEC series search](https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=S000036082&type=NPORT-P&count=100&output=atom) was queried for NPORT-P and explicitly for NPORT-P/A, including pagination support. It returned 28 original filings since 2019; the 17 filed from August 2022 through the research cutoff were retrieved and series/date validated. No additional amendment was found. Their actual portfolio dates run June 2022–June 2026. September 2026 was not publicly present at the cutoff; do not infer future publication or fill it with October holdings.

All nine linked NPORT-EX multi-fund schedules were retrieved and the SPGM section was isolated by table-of-contents anchors. They repeat existing June/December portfolio dates, so do not add snapshots. Four schedules (one warm-up and three target-period) supply 11-sector **fund aggregate weights**; these are retained separately and never assigned to individual securities.

Wayback CDX queries used all distinct captured contents, not one capture per month. The exact XLSX URL and broader publisher fund-data/URL searches found the same four holdings files. NAV and premium/discount history files were excluded because they are not holdings. This is a reproducible bounded public-source search; it does not prove that no other historical URL or archive exists.

The broader publisher fund-data query completed with 12 records (four holdings, four NAV histories and four premium/discount histories). An additional whole-domain SPGM wildcard query timed out; its failure is retained in the separate discovery manifest. It does not affect the successful filing/holdings downloads, but limits the breadth of the archive search.

All 17 XML responses, nine exhibits and four workbooks were successfully cached; retrieval failures: **0**. Raw response hashes, URLs and UTC retrieval times are recorded. The download code restricts HTTPS domains, checks redirects before following, throttles SEC requests below its fair-access ceiling, and uses no credentials or EODHD endpoint.

## Snapshot inventory

Counts include cash-equivalent funds, derivatives, preferred shares, rights and repeated instrument exposures. `EC` is the SEC common-equity category; workbook asset categories are unclassified. No raw line is dropped merely to make counts agree.

| Portfolio date | Public filing date / archive bound | Source | Records | EC rows | Missing valid ID | Duplicate key rows | Country gaps | Security-sector gaps |
|---|---|---|---:|---:|---:|---:|---:|---:|
| 2022-06-30 (warm-up) | 2022-08-26 | [SEC](https://www.sec.gov/Archives/edgar/data/1168164/000175272422197044/primary_doc.xml) | 2422 | 2412 | 1 | 9 | 0 | 2422 |
| 2022-09-30 (warm-up) | 2022-11-28 | [SEC](https://www.sec.gov/Archives/edgar/data/1168164/000175272422271210/primary_doc.xml) | 2523 | 2507 | 2 | 8 | 0 | 2523 |
| 2022-12-31 | 2023-02-28 | [SEC](https://www.sec.gov/Archives/edgar/data/1168164/000175272423046876/primary_doc.xml) | 2450 | 2432 | 0 | 8 | 0 | 2450 |
| 2023-03-31 | 2023-05-30 | [SEC](https://www.sec.gov/Archives/edgar/data/1168164/000175272423123972/primary_doc.xml) | 2511 | 2491 | 4 | 8 | 0 | 2511 |
| 2023-06-30 | 2023-08-28 | [SEC](https://www.sec.gov/Archives/edgar/data/1168164/000175272423196511/primary_doc.xml) | 2532 | 2512 | 4 | 7 | 0 | 2532 |
| 2023-09-30 | 2023-11-28 | [SEC](https://www.sec.gov/Archives/edgar/data/1168164/000175272423267652/primary_doc.xml) | 2678 | 2655 | 4 | 7 | 0 | 2678 |
| 2023-12-31 | 2024-02-27 | [SEC](https://www.sec.gov/Archives/edgar/data/1168164/000175272424043338/primary_doc.xml) | 2693 | 2673 | 4 | 7 | 0 | 2693 |
| 2024-03-31 | 2024-05-28 | [SEC](https://www.sec.gov/Archives/edgar/data/1168164/000175272424122750/primary_doc.xml) | 2717 | 2694 | 5 | 6 | 0 | 2717 |
| 2024-04-04 | 2024-04-07 (archive bound) | [archive](https://web.archive.org/web/20240407120155id_/https://www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spgm.xlsx) | 2747 | unknown | 0 | 0 | 2747 | 2747 |
| 2024-06-30 | 2024-08-28 | [SEC](https://www.sec.gov/Archives/edgar/data/1168164/000175272424196587/primary_doc.xml) | 2598 | 2575 | 5 | 6 | 0 | 2598 |
| 2024-09-30 | 2024-11-25 | [SEC](https://www.sec.gov/Archives/edgar/data/1168164/000175272424264685/primary_doc.xml) | 2682 | 2662 | 7 | 10 | 0 | 2682 |
| 2024-12-31 | 2025-02-27 | [SEC](https://www.sec.gov/Archives/edgar/data/1168164/000175272425043821/primary_doc.xml) | 2722 | 2702 | 7 | 10 | 0 | 2722 |
| 2025-03-05 | 2025-03-06 (archive bound) | [archive](https://web.archive.org/web/20250306125054id_/https://www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spgm.xlsx) | 2878 | unknown | 0 | 0 | 2878 | 2878 |
| 2025-03-31 | 2025-05-28 | [SEC](https://www.sec.gov/Archives/edgar/data/1168164/000175272425125217/primary_doc.xml) | 2840 | 2820 | 4 | 12 | 0 | 2840 |
| 2025-06-30 | 2025-08-28 | [SEC](https://www.sec.gov/Archives/edgar/data/1168164/000175272425211169/primary_doc.xml) | 2792 | 2765 | 7 | 9 | 0 | 2792 |
| 2025-09-30 | 2025-11-26 | [SEC](https://www.sec.gov/Archives/edgar/data/1168164/000141036825031932/primary_doc.xml) | 2922 | 2898 | 8 | 10 | 0 | 2922 |
| 2025-12-31 | 2026-02-26 | [SEC](https://www.sec.gov/Archives/edgar/data/1168164/000141036826020054/primary_doc.xml) | 2938 | 2910 | 10 | 9 | 0 | 2938 |
| 2026-03-31 | 2026-05-28 | [SEC](https://www.sec.gov/Archives/edgar/data/1168164/000141036826055355/primary_doc.xml) | 2950 | 2920 | 9 | 10 | 0 | 2950 |
| 2026-04-16 | 2026-04-17 (archive bound) | [archive](https://web.archive.org/web/20260417143813id_/https://www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spgm.xlsx) | 3007 | unknown | 0 | 0 | 3007 | 3007 |
| 2026-06-30 | 2026-08-28 | [SEC](https://www.sec.gov/Archives/edgar/data/1168164/000141036826089225/primary_doc.xml) | 2955 | 2922 | 8 | 13 | 0 | 2955 |
| 2026-08-18 | 2026-08-20 (archive bound) | [archive](https://web.archive.org/web/20260820073553id_/https://www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spgm.xlsx) | 2975 | unknown | 0 | 0 | 2975 | 2975 |

## Portfolio and publication dates

SEC `repPdDate` is the portfolio date; `repPdEnd` is fiscal-year end and must not be used as the holdings date. Filing date and index acceptance timestamp are preserved separately, with America/New_York acceptance converted to UTC for availability. Later filing-date bounds remain conservative. Amendments remain separate versions and cannot replace an earlier observation before they became public.

For archived workbooks, original publication dates are **unknown**. The internal `As of` date is the portfolio observation; the archive capture timestamp is a conservative upper bound on when the file was public. It must not be relabeled as its original publication date. No unknown release date is guessed.

The illustrative selection convention below is calendar month-end at 23:59:59 UTC. It chooses the newest portfolio already public then; ties use the latest public version. A backtest with an earlier exchange-close cutoff must rerun availability at that exact timestamp. This convention does not change the investment strategy.

## Monthly coverage matrix

`Obs` counts directly observed portfolios in that month, including portfolios published later. `IDs` counts missing valid security identifiers. `Tickers` counts unresolved research ticker lookups; `Future` counts lookups relying on later archives, unavailable to an earlier decision. Both are weaker than an executable listing mapping. `Country`/`Sector` count missing fields in the selected portfolio. Missing MSCI members' identities remain **unknown in every month** without full official membership.

| Selection month | Obs | Latest public portfolio | Age days | Records | IDs | Tickers | Future | Country | Sector |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 2022-10 | 0 | 2022-06-30 | 123 | 2422 | 1 | 1733 | 689 | 0 | 2422 |
| 2022-11 | 0 | 2022-09-30 | 61 | 2523 | 2 | 1818 | 705 | 0 | 2523 |
| 2022-12 | 1 | 2022-09-30 | 92 | 2523 | 2 | 1818 | 705 | 0 | 2523 |
| 2023-01 | 0 | 2022-09-30 | 123 | 2523 | 2 | 1818 | 705 | 0 | 2523 |
| 2023-02 | 0 | 2022-12-31 | 59 | 2450 | 0 | 1741 | 709 | 0 | 2450 |
| 2023-03 | 1 | 2022-12-31 | 90 | 2450 | 0 | 1741 | 709 | 0 | 2450 |
| 2023-04 | 0 | 2022-12-31 | 120 | 2450 | 0 | 1741 | 709 | 0 | 2450 |
| 2023-05 | 0 | 2023-03-31 | 61 | 2511 | 4 | 1722 | 789 | 0 | 2511 |
| 2023-06 | 1 | 2023-03-31 | 91 | 2511 | 4 | 1722 | 789 | 0 | 2511 |
| 2023-07 | 0 | 2023-03-31 | 122 | 2511 | 4 | 1722 | 789 | 0 | 2511 |
| 2023-08 | 0 | 2023-06-30 | 62 | 2532 | 4 | 1693 | 839 | 0 | 2532 |
| 2023-09 | 1 | 2023-06-30 | 92 | 2532 | 4 | 1693 | 839 | 0 | 2532 |
| 2023-10 | 0 | 2023-06-30 | 123 | 2532 | 4 | 1693 | 839 | 0 | 2532 |
| 2023-11 | 0 | 2023-09-30 | 61 | 2678 | 4 | 1753 | 925 | 0 | 2678 |
| 2023-12 | 1 | 2023-09-30 | 92 | 2678 | 4 | 1753 | 925 | 0 | 2678 |
| 2024-01 | 0 | 2023-09-30 | 123 | 2678 | 4 | 1753 | 925 | 0 | 2678 |
| 2024-02 | 0 | 2023-12-31 | 60 | 2693 | 4 | 1748 | 945 | 0 | 2693 |
| 2024-03 | 1 | 2023-12-31 | 91 | 2693 | 4 | 1748 | 945 | 0 | 2693 |
| 2024-04 | 1 | 2024-04-04 | 26 | 2747 | 0 | 40 | 2 | 2747 | 2747 |
| 2024-05 | 0 | 2024-04-04 | 57 | 2747 | 0 | 40 | 2 | 2747 | 2747 |
| 2024-06 | 1 | 2024-04-04 | 87 | 2747 | 0 | 40 | 2 | 2747 | 2747 |
| 2024-07 | 0 | 2024-04-04 | 118 | 2747 | 0 | 40 | 2 | 2747 | 2747 |
| 2024-08 | 0 | 2024-06-30 | 62 | 2598 | 5 | 1686 | 4 | 0 | 2598 |
| 2024-09 | 1 | 2024-06-30 | 92 | 2598 | 5 | 1686 | 4 | 0 | 2598 |
| 2024-10 | 0 | 2024-06-30 | 123 | 2598 | 5 | 1686 | 4 | 0 | 2598 |
| 2024-11 | 0 | 2024-09-30 | 61 | 2682 | 7 | 1737 | 57 | 0 | 2682 |
| 2024-12 | 1 | 2024-09-30 | 92 | 2682 | 7 | 1737 | 57 | 0 | 2682 |
| 2025-01 | 0 | 2024-09-30 | 123 | 2682 | 7 | 1737 | 57 | 0 | 2682 |
| 2025-02 | 0 | 2024-12-31 | 59 | 2722 | 7 | 1727 | 136 | 0 | 2722 |
| 2025-03 | 2 | 2025-03-05 | 26 | 2878 | 0 | 43 | 1 | 2878 | 2878 |
| 2025-04 | 0 | 2025-03-05 | 56 | 2878 | 0 | 43 | 1 | 2878 | 2878 |
| 2025-05 | 0 | 2025-03-31 | 61 | 2840 | 4 | 1838 | 1 | 0 | 2840 |
| 2025-06 | 1 | 2025-03-31 | 91 | 2840 | 4 | 1838 | 1 | 0 | 2840 |
| 2025-07 | 0 | 2025-03-31 | 122 | 2840 | 4 | 1838 | 1 | 0 | 2840 |
| 2025-08 | 0 | 2025-06-30 | 62 | 2792 | 7 | 1823 | 21 | 0 | 2792 |
| 2025-09 | 1 | 2025-06-30 | 92 | 2792 | 7 | 1823 | 21 | 0 | 2792 |
| 2025-10 | 0 | 2025-06-30 | 123 | 2792 | 7 | 1823 | 21 | 0 | 2792 |
| 2025-11 | 0 | 2025-09-30 | 61 | 2922 | 8 | 1932 | 68 | 0 | 2922 |
| 2025-12 | 1 | 2025-09-30 | 92 | 2922 | 8 | 1932 | 68 | 0 | 2922 |
| 2026-01 | 0 | 2025-09-30 | 123 | 2922 | 8 | 1932 | 68 | 0 | 2922 |
| 2026-02 | 0 | 2025-12-31 | 59 | 2938 | 10 | 1936 | 106 | 0 | 2938 |
| 2026-03 | 1 | 2025-12-31 | 90 | 2938 | 10 | 1936 | 106 | 0 | 2938 |
| 2026-04 | 1 | 2026-04-16 | 14 | 3007 | 0 | 48 | 1 | 3007 | 3007 |
| 2026-05 | 0 | 2026-04-16 | 45 | 3007 | 0 | 48 | 1 | 3007 | 3007 |
| 2026-06 | 1 | 2026-04-16 | 75 | 3007 | 0 | 48 | 1 | 3007 | 3007 |
| 2026-07 | 0 | 2026-04-16 | 106 | 3007 | 0 | 48 | 1 | 3007 | 3007 |
| 2026-08 | 1 | 2026-08-18 | 13 | 2975 | 0 | 48 | 0 | 2975 | 2975 |
| 2026-09 | 0 | 2026-08-18 | 43 | 2975 | 0 | 48 | 0 | 2975 | 2975 |

## Identifier, country and sector limitations

CUSIP/ISIN/SEDOL values stay strings with leading zeroes. Format/checksum failures are retained and excluded from exact crosswalk joins. Across all observations, **89 rows lack a valid typed security ID**, and **149 extra rows share an instrument key within their portfolio**. Duplicates remain separate positions for audit; they must not be counted as distinct members. An instrument ID is not a permanent company ID or a verified exchange listing.

SEC positions provide ISIN/CUSIP where supplied, company LEI and investment-country codes. **23,335 rows lack a company LEI** across all observations, including every workbook row. All SEC rows have country codes; **11,607 workbook rows lack country**. Currency, ISIN prefix and ticker are not automatically converted into MSCI risk country or exchange venue.

SEC XML has no source tickers in this sample. Workbooks supply tickers for most rows. Exact valid-ID joins add research identity lookups, retaining the mapping's portfolio/publication dates and source. **30,760 position rows remain unmapped**, and **7,093 mappings use future archive evidence**; those future mappings must never be available to an earlier decision. Prior archive mappings also require checking for subsequent symbol changes. All exchange MIC/listing mappings remain unverified; names and currency are not fuzzy-joined.

All **57,532 rows lack security-level sector/GICS**. The archive Sector column is `-`; SEC asset categories are instrument classes, not sectors. Four dated fund aggregate breakdowns are preserved in `aggregate_sector_weights.csv`, without security-level assignments. MSCI factsheet top-ten sectors are not a classification database for the remaining securities. Sector-dependent historical selection remains blocked.

Consecutive SEC portfolios produce `observed_etf_changes.csv`: first-observed/not-observed identity differences with both publication dates. These are **ETF observation changes**, not exact transaction dates, MSCI entries/exits or confirmed delistings. Identifier conversions and observation gaps can also create apparent changes. No current-survivor filter is used.

## Comparison with reported MSCI ACWI IMI counts

Seven official [MSCI ACWI IMI factsheets](https://www.msci.com/documents/10199/255599/msci-acwi-imi.pdf), including six archive captures, were retrieved and their dated counts extracted. The current September 2026 count was first verified on the research date; it is not presumed known at September month-end. Counts below are research comparisons, not universe input.

Some PDF responses have a truncated terminal EOF marker. Their index names, dates and constituent counts remain readable, and raw hashes/terminal-marker status are recorded. This validates those extracted fields, not the completeness of every PDF page. The current 8,036 count also agrees with the independently retrieved publisher benchmark statistics.

| Index observation date | Reported constituents | Verified-public bound |
|---|---:|---|
| 2024-11-29 | 8,647 | [2024-12-04](https://web.archive.org/web/20241204171541id_/https://www.msci.com/documents/10199/255599/msci-acwi-imi.pdf) |
| 2025-02-28 | 8,617 | [2025-03-20](https://web.archive.org/web/20250320020351id_/https://www.msci.com/documents/10199/255599/msci-acwi-imi.pdf) |
| 2025-09-30 | 8,300 | [2025-10-26](https://web.archive.org/web/20251026160808id_/https://www.msci.com/documents/10199/255599/msci-acwi-imi.pdf) |
| 2026-02-27 | 8,196 | [2026-03-08](https://web.archive.org/web/20260308172340id_/https://www.msci.com/documents/10199/255599/msci-acwi-imi.pdf) |
| 2026-03-31 | 8,253 | [2026-05-03](https://web.archive.org/web/20260503180413id_/https://www.msci.com/documents/10199/255599/msci-acwi-imi.pdf) |
| 2026-08-31 | 8,162 | [2026-09-16](https://web.archive.org/web/20260916220323id_/https://www.msci.com/documents/10199/255599/msci-acwi-imi.pdf) |
| 2026-09-30 | 8,036 | [2026-10-09](https://www.msci.com/documents/10199/255599/msci-acwi-imi.pdf) |

Two exact-date comparisons are possible: September 30, 2025 has **2,922 ETF records versus 8,300 index constituents (35.20%)**; March 31, 2026 has **2,950 versus 8,253 (35.74%)**. Because ETF counts include non-equities and repeated exposures, these count ratios are not constituent overlap or investment-weight coverage. The corresponding raw count gaps are 5,378 and 5,303, but the missing securities cannot be identified from counts alone.

At September 2026 selection the latest public portfolio is August 18 (2,975 records), whereas the September 30 index reports 8,036 constituents: **37.02%**, a count gap of 5,061 with differing dates. It is not a contemporaneous coverage measurement. Other comparison rows explicitly retain date gaps; no index count is interpolated across missing months.

## Reproduction and output

Run from the repository root. Default commands are cache-only and make no network requests:

```sh
python -m research.spgm_sources
python -m research.spgm_benchmarks
python -m research.spgm_proxy
/workspace/.venvs/eodhd-validation/bin/python -m unittest discover -s research -p 'test_*.py'
```

On a fresh cache, explicitly add `--fetch` to the first two commands to retrieve public SEC/Wayback/MSCI files. The parser uses the Python standard library; factsheet extraction additionally uses `pypdf`. Network destinations are `www.sec.gov`, `web.archive.org`, and `www.msci.com` (publisher redirects may also require `www.ssga.com`). Existing cloud setup provides the validation environment and PDF reader.

Security-level data and raw responses live exclusively under Git-ignored `research/eodhd_output/spgm_proxy/`: `holdings.csv`, `snapshots.csv/json`, `coverage_matrix.csv`, `coverage_summary.json`, `identifier_issues.csv`, `ticker_crosswalk.csv`, `observed_etf_changes.csv`, `benchmark_comparisons.csv`, `aggregate_sector_weights.csv`, source catalog, exhibit audit and checksum manifests. The local `coverage_report.md` is generated from those records; this reviewed aggregate report contains no security-level market-data extract.

Public SEC filings were accessed without authentication or bypassing controls. Publisher archives and MSCI factsheets were accessed through public URLs; public access does not establish redistribution rights for a holdings database or proprietary MSCI data. Raw/normalized holdings, PDFs and workbooks are not committed. This research is separate from trading, makes **zero additional EODHD requests**, and does not modify the five-stock strategy.

Validation: **47 research regression tests passed**, including 19 SPGM tests. `git diff --check` passed. Cached EODHD request ledgers and strategy files were unchanged.
