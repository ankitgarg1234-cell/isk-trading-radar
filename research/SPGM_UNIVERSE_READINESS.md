# Point-in-time global universe audit

**Dataset: SPGM historical ETF holdings proxy — not official MSCI ACWI IMI constituents.**
Checked on 10 October 2026 (Europe/Stockholm), branch `research/eodhd-acwi-imi-setup`.

## Readiness finding

The holdings support a reproducible **48-date, prior-public membership study**. They do **not** support a faithful global execution of the existing five-stock sector-aware risk-adjusted momentum strategy yet. No strategy was run or modified. No EODHD or other external API requests were made in this audit.

Confirmed common-equity membership ranges from **938 to 2,899 securities** per month. Estimated issuer/company groups range from **936 to 2,884**; exact unique-company counts remain unknown because issuer crosswalks are incomplete. Portfolio ages range from **13 to 123 calendar days**.

The latest-public workbook is the selected source in **12 months**. Those months have only **938–979 confirmed securities**, while **1,798–2,027 unclassified instruments** remain separate. This is a metadata-driven coverage collapse, not evidence of mass ETF sales. Using the strict subset would materially distort global country/sector breadth and rankings.

A separately reported **SEC-only lagged alternative** preserves explicit stock types across all 48 dates, with **2,403–2,910 securities**. It uses an older portfolio when a workbook is newer. It remains an approximation with stale membership and incomplete sectors/listings, not a silently substituted universe.

## Construction policy

All 21 cached portfolios enter the audit: 19 target-period observations and two earlier warm-ups. For each calendar month-end, the cutoff is **23:59:59 UTC**, retained from the prior availability report. Only source information with a known-public/availability timestamp **strictly earlier** than that cutoff can be used. This is a research cutoff; a historical exchange-close decision must use its exact earlier timestamp instead.

Choose the latest portfolio date already public; a later publication of an older portfolio does not displace a newer portfolio. Amendments are versioned by publication time. For archive workbooks the original publication date remains blank/unknown, with capture time used as the conservative availability bound. Portfolio dates are never relabeled as release dates. The source filing, URL, raw-response hash and original row numbers remain in every derived security record.

**Eligible means an identifiable, positive-unit common-equity holding, not a momentum-qualified or executable trade.** Public SEC `EC` rows qualify structurally. Preferred shares, derivatives and short-term investment funds do not; non-positive/invalid units or missing valid typed identifiers are excluded. Common equity can include an ADR/GDR or REIT classified as EC. No guessed primary-market conversion or ordinary-share/ADR substitution is performed.

Workbooks lack asset-type fields. A workbook row qualifies only where an exact, valid security-identifier join finds a previously public SEC EC classification. The latest applicable public classification is used; conflicting classifications remain provisional. Other identifiable positive-unit workbook rows are **provisional unclassified instruments**, potentially including cash or derivatives, not asserted to be stocks. A ticker, SEDOL, weight or company name alone is insufficient to establish common-equity type.

Duplicate instrument exposures within a source are collapsed for membership counting, retaining every original position row reference. Distinct share classes, ADRs and ordinary shares remain distinct securities, even when they share an issuer LEI. This audit does not introduce a new one-security-per-company strategy rule.

Country and company-LEI metadata may be resolved through exact identifiers using only prior-public source rows, with field-level dates/row citations recorded. Original values remain separately preserved. Current constituents, current ticker masters, future filing metadata, currency and security-name guesses never fill membership or country gaps. Sector values remain unfilled.

## Monthly membership and quality report

`Companies est.` uses source LEIs where valid and otherwise exact normalized historical issuer-name groups. `LEI issuers` is the directly identified subset; it is not a complete company count or ultimate-parent map. Missing/ambiguous ticker counts use **only point-in-time source tickers**. Every listing venue remains unverified, including rows with a ticker. `Sector gaps` counts missing historical security-level classifications.

| Selection month | Eligible securities | Companies est. | LEI issuers | Portfolio date | Public filing / archive bound | Age | Missing tickers | Ambiguous tickers | Sector gaps | Provisional instruments |
|---|---:|---:|---:|---|---|---:|---:|---:|---:|---:|
| 2022-10 | 2403 | 2388 | 1719 | 2022-06-30 | 2022-08-26 | 123 | 2403 | 0 | 2403 | 0 |
| 2022-11 | 2499 | 2484 | 1785 | 2022-09-30 | 2022-11-28 | 61 | 2499 | 0 | 2499 | 0 |
| 2022-12 | 2499 | 2484 | 1785 | 2022-09-30 | 2022-11-28 | 92 | 2499 | 0 | 2499 | 0 |
| 2023-01 | 2499 | 2484 | 1785 | 2022-09-30 | 2022-11-28 | 123 | 2499 | 0 | 2499 | 0 |
| 2023-02 | 2424 | 2408 | 1761 | 2022-12-31 | 2023-02-28 | 59 | 2424 | 0 | 2424 | 0 |
| 2023-03 | 2424 | 2408 | 1761 | 2022-12-31 | 2023-02-28 | 90 | 2424 | 0 | 2424 | 0 |
| 2023-04 | 2424 | 2408 | 1761 | 2022-12-31 | 2023-02-28 | 120 | 2424 | 0 | 2424 | 0 |
| 2023-05 | 2483 | 2467 | 1829 | 2023-03-31 | 2023-05-30 | 61 | 2483 | 0 | 2483 | 0 |
| 2023-06 | 2483 | 2467 | 1829 | 2023-03-31 | 2023-05-30 | 91 | 2483 | 0 | 2483 | 0 |
| 2023-07 | 2483 | 2467 | 1829 | 2023-03-31 | 2023-05-30 | 122 | 2483 | 0 | 2483 | 0 |
| 2023-08 | 2505 | 2489 | 1823 | 2023-06-30 | 2023-08-28 | 62 | 2505 | 0 | 2505 | 0 |
| 2023-09 | 2505 | 2489 | 1823 | 2023-06-30 | 2023-08-28 | 92 | 2505 | 0 | 2505 | 0 |
| 2023-10 | 2505 | 2489 | 1823 | 2023-06-30 | 2023-08-28 | 123 | 2505 | 0 | 2505 | 0 |
| 2023-11 | 2648 | 2632 | 1897 | 2023-09-30 | 2023-11-28 | 61 | 2648 | 0 | 2648 | 0 |
| 2023-12 | 2648 | 2632 | 1897 | 2023-09-30 | 2023-11-28 | 92 | 2648 | 0 | 2648 | 0 |
| 2024-01 | 2648 | 2632 | 1897 | 2023-09-30 | 2023-11-28 | 123 | 2648 | 0 | 2648 | 0 |
| 2024-02 | 2665 | 2648 | 1920 | 2023-12-31 | 2024-02-27 | 60 | 2665 | 0 | 2665 | 0 |
| 2024-03 | 2665 | 2648 | 1920 | 2023-12-31 | 2024-02-27 | 91 | 2665 | 0 | 2665 | 0 |
| 2024-04 | 938 | 936 | 765 | 2024-04-04 | 2024-04-07 (archive bound) | 26 | 2 | 0 | 938 | 1806 |
| 2024-05 | 946 | 944 | 776 | 2024-04-04 | 2024-04-07 (archive bound) | 57 | 2 | 0 | 946 | 1798 |
| 2024-06 | 946 | 944 | 776 | 2024-04-04 | 2024-04-07 (archive bound) | 87 | 2 | 0 | 946 | 1798 |
| 2024-07 | 946 | 944 | 776 | 2024-04-04 | 2024-04-07 (archive bound) | 118 | 2 | 0 | 946 | 1798 |
| 2024-08 | 2569 | 2553 | 1901 | 2024-06-30 | 2024-08-28 | 62 | 1663 | 0 | 2569 | 0 |
| 2024-09 | 2569 | 2553 | 1901 | 2024-06-30 | 2024-08-28 | 92 | 1663 | 0 | 2569 | 0 |
| 2024-10 | 2569 | 2553 | 1901 | 2024-06-30 | 2024-08-28 | 123 | 1663 | 0 | 2569 | 0 |
| 2024-11 | 2653 | 2637 | 1939 | 2024-09-30 | 2024-11-25 | 61 | 1767 | 0 | 2653 | 0 |
| 2024-12 | 2653 | 2637 | 1939 | 2024-09-30 | 2024-11-25 | 92 | 1767 | 0 | 2653 | 0 |
| 2025-01 | 2653 | 2637 | 1939 | 2024-09-30 | 2024-11-25 | 123 | 1767 | 0 | 2653 | 0 |
| 2025-02 | 2692 | 2676 | 1980 | 2024-12-31 | 2025-02-27 | 59 | 1835 | 0 | 2692 | 0 |
| 2025-03 | 962 | 959 | 768 | 2025-03-05 | 2025-03-06 (archive bound) | 26 | 1 | 0 | 962 | 1911 |
| 2025-04 | 962 | 959 | 768 | 2025-03-05 | 2025-03-06 (archive bound) | 56 | 1 | 0 | 962 | 1911 |
| 2025-05 | 2807 | 2792 | 2070 | 2025-03-31 | 2025-05-28 | 61 | 1810 | 0 | 2807 | 0 |
| 2025-06 | 2807 | 2792 | 2070 | 2025-03-31 | 2025-05-28 | 91 | 1810 | 0 | 2807 | 0 |
| 2025-07 | 2807 | 2792 | 2070 | 2025-03-31 | 2025-05-28 | 122 | 1810 | 0 | 2807 | 0 |
| 2025-08 | 2756 | 2740 | 2057 | 2025-06-30 | 2025-08-28 | 62 | 1811 | 0 | 2756 | 0 |
| 2025-09 | 2756 | 2740 | 2057 | 2025-06-30 | 2025-08-28 | 92 | 1811 | 0 | 2756 | 0 |
| 2025-10 | 2756 | 2740 | 2057 | 2025-06-30 | 2025-08-28 | 123 | 1811 | 0 | 2756 | 0 |
| 2025-11 | 2887 | 2870 | 2172 | 2025-09-30 | 2025-11-26 | 61 | 1968 | 0 | 2887 | 0 |
| 2025-12 | 2887 | 2870 | 2172 | 2025-09-30 | 2025-11-26 | 92 | 1968 | 0 | 2887 | 0 |
| 2026-01 | 2887 | 2870 | 2172 | 2025-09-30 | 2025-11-26 | 123 | 1968 | 0 | 2887 | 0 |
| 2026-02 | 2899 | 2884 | 2226 | 2025-12-31 | 2026-02-26 | 59 | 2005 | 0 | 2899 | 0 |
| 2026-03 | 2899 | 2884 | 2226 | 2025-12-31 | 2026-02-26 | 90 | 2005 | 0 | 2899 | 0 |
| 2026-04 | 970 | 968 | 819 | 2026-04-16 | 2026-04-17 (archive bound) | 14 | 0 | 0 | 970 | 2027 |
| 2026-05 | 979 | 977 | 839 | 2026-04-16 | 2026-04-17 (archive bound) | 45 | 0 | 0 | 979 | 2018 |
| 2026-06 | 979 | 977 | 839 | 2026-04-16 | 2026-04-17 (archive bound) | 75 | 0 | 0 | 979 | 2018 |
| 2026-07 | 979 | 977 | 839 | 2026-04-16 | 2026-04-17 (archive bound) | 106 | 0 | 0 | 979 | 2018 |
| 2026-08 | 970 | 967 | 847 | 2026-08-18 | 2026-08-20 (archive bound) | 13 | 0 | 0 | 970 | 1995 |
| 2026-09 | 970 | 967 | 847 | 2026-08-18 | 2026-08-20 (archive bound) | 43 | 0 | 0 | 970 | 1995 |

### Country distribution for every selection date

Numbers are counts of confirmed securities, not portfolio weights or companies. SEC Form N-PORT Item C.5 distinguishes issuer organization country from risk/economic exposure; this cache's `invCountry` supplies organization-country information. No `invOtherCountry` values were found in the 17 cached XML files. These fields do **not** establish MSCI country of classification, primary exchange, or global revenue exposure. Offshore codes such as KY and BM remain unchanged. `XX` is retained in original observations but treated as unspecified (`UNKNOWN`), never assigned from an ISIN prefix.

For workbooks the original country field is absent. Countries below are available only for the identifier-matched strict subset via older public SEC evidence; unmapped provisional rows are not counted as known-country equities. The apparent U.S. concentration is therefore partly a crosswalk bias, not the fund's complete geographical exposure.

| Selection month | Country code: eligible security count |
|---|---|
| 2022-10 | AE:8, AT:4, AU:98, BE:3, BM:22, BR:26, BS:1, CA:114, CH:27, CL:9, CN:121, CO:1, CW:1, DE:37, DK:9, EG:1, ES:13, FI:12, FR:36, GB:74, GR:1, HK:20, HU:2, ID:9, IE:16, IL:11, IN:112, IT:10, JE:7, JP:180, KR:110, KW:5, KY:166, LI:1, LU:4, MH:1, MX:8, MY:19, NL:28, NO:8, NZ:1, PA:1, PE:1, PH:2, PL:5, RU:8, SA:37, SE:32, SG:7, TH:29, TR:8, TW:87, UNKNOWN:1, US:831, VG:4, ZA:14 |
| 2022-11 | AE:10, AT:4, AU:101, BE:3, BM:21, BR:32, BS:1, CA:119, CH:27, CL:8, CN:136, CO:1, CW:1, DE:37, DK:9, EG:1, ES:13, FI:11, FR:36, GB:75, GR:1, HK:20, HU:2, ID:9, IE:15, IL:11, IN:115, IT:10, JE:7, JP:197, KR:125, KW:7, KY:169, LI:1, LU:4, MH:1, MX:9, MY:20, NL:29, NO:8, NZ:1, PA:1, PE:1, PH:2, PL:5, RU:8, SA:40, SE:32, SG:7, TH:35, TR:8, TW:95, UNKNOWN:1, US:839, VG:4, ZA:14 |
| 2022-12 | AE:10, AT:4, AU:101, BE:3, BM:21, BR:32, BS:1, CA:119, CH:27, CL:8, CN:136, CO:1, CW:1, DE:37, DK:9, EG:1, ES:13, FI:11, FR:36, GB:75, GR:1, HK:20, HU:2, ID:9, IE:15, IL:11, IN:115, IT:10, JE:7, JP:197, KR:125, KW:7, KY:169, LI:1, LU:4, MH:1, MX:9, MY:20, NL:29, NO:8, NZ:1, PA:1, PE:1, PH:2, PL:5, RU:8, SA:40, SE:32, SG:7, TH:35, TR:8, TW:95, UNKNOWN:1, US:839, VG:4, ZA:14 |
| 2023-01 | AE:10, AT:4, AU:101, BE:3, BM:21, BR:32, BS:1, CA:119, CH:27, CL:8, CN:136, CO:1, CW:1, DE:37, DK:9, EG:1, ES:13, FI:11, FR:36, GB:75, GR:1, HK:20, HU:2, ID:9, IE:15, IL:11, IN:115, IT:10, JE:7, JP:197, KR:125, KW:7, KY:169, LI:1, LU:4, MH:1, MX:9, MY:20, NL:29, NO:8, NZ:1, PA:1, PE:1, PH:2, PL:5, RU:8, SA:40, SE:32, SG:7, TH:35, TR:8, TW:95, UNKNOWN:1, US:839, VG:4, ZA:14 |
| 2023-02 | AE:12, AT:4, AU:96, BE:3, BM:19, BR:30, BS:1, CA:115, CH:27, CL:8, CN:130, CO:1, CW:1, DE:35, DK:8, EG:1, ES:12, FI:11, FR:36, GB:77, GR:1, HK:20, HU:2, ID:8, IE:16, IL:11, IN:122, IT:9, JE:7, JP:195, KR:116, KW:6, KY:155, LI:1, LR:1, LU:4, MH:1, MX:9, MY:19, NL:30, NO:9, NZ:1, PA:1, PE:1, PH:2, PL:5, RU:7, SA:45, SE:26, SG:7, TH:42, TR:8, TW:99, UNKNOWN:1, US:794, VG:2, ZA:14 |
| 2023-03 | AE:12, AT:4, AU:96, BE:3, BM:19, BR:30, BS:1, CA:115, CH:27, CL:8, CN:130, CO:1, CW:1, DE:35, DK:8, EG:1, ES:12, FI:11, FR:36, GB:77, GR:1, HK:20, HU:2, ID:8, IE:16, IL:11, IN:122, IT:9, JE:7, JP:195, KR:116, KW:6, KY:155, LI:1, LR:1, LU:4, MH:1, MX:9, MY:19, NL:30, NO:9, NZ:1, PA:1, PE:1, PH:2, PL:5, RU:7, SA:45, SE:26, SG:7, TH:42, TR:8, TW:99, UNKNOWN:1, US:794, VG:2, ZA:14 |
| 2023-04 | AE:12, AT:4, AU:96, BE:3, BM:19, BR:30, BS:1, CA:115, CH:27, CL:8, CN:130, CO:1, CW:1, DE:35, DK:8, EG:1, ES:12, FI:11, FR:36, GB:77, GR:1, HK:20, HU:2, ID:8, IE:16, IL:11, IN:122, IT:9, JE:7, JP:195, KR:116, KW:6, KY:155, LI:1, LR:1, LU:4, MH:1, MX:9, MY:19, NL:30, NO:9, NZ:1, PA:1, PE:1, PH:2, PL:5, RU:7, SA:45, SE:26, SG:7, TH:42, TR:8, TW:99, UNKNOWN:1, US:794, VG:2, ZA:14 |
| 2023-05 | AE:15, AT:4, AU:96, BE:3, BM:17, BR:28, BS:1, CA:112, CH:26, CL:8, CN:129, CO:1, CW:1, CY:1, DE:35, DK:10, EG:1, ES:12, FI:11, FR:36, GB:74, GR:1, HK:20, HU:2, ID:8, IE:16, IL:11, IN:124, IT:9, JE:8, JP:196, KR:120, KW:6, KY:153, LI:1, LR:1, LU:4, MH:3, MX:9, MY:18, NL:29, NO:9, NZ:1, PA:1, PE:1, PH:1, PL:5, RU:7, SA:45, SE:28, SG:7, TH:46, TR:8, TW:101, UNKNOWN:1, US:846, VG:2, ZA:14 |
| 2023-06 | AE:15, AT:4, AU:96, BE:3, BM:17, BR:28, BS:1, CA:112, CH:26, CL:8, CN:129, CO:1, CW:1, CY:1, DE:35, DK:10, EG:1, ES:12, FI:11, FR:36, GB:74, GR:1, HK:20, HU:2, ID:8, IE:16, IL:11, IN:124, IT:9, JE:8, JP:196, KR:120, KW:6, KY:153, LI:1, LR:1, LU:4, MH:3, MX:9, MY:18, NL:29, NO:9, NZ:1, PA:1, PE:1, PH:1, PL:5, RU:7, SA:45, SE:28, SG:7, TH:46, TR:8, TW:101, UNKNOWN:1, US:846, VG:2, ZA:14 |
| 2023-07 | AE:15, AT:4, AU:96, BE:3, BM:17, BR:28, BS:1, CA:112, CH:26, CL:8, CN:129, CO:1, CW:1, CY:1, DE:35, DK:10, EG:1, ES:12, FI:11, FR:36, GB:74, GR:1, HK:20, HU:2, ID:8, IE:16, IL:11, IN:124, IT:9, JE:8, JP:196, KR:120, KW:6, KY:153, LI:1, LR:1, LU:4, MH:3, MX:9, MY:18, NL:29, NO:9, NZ:1, PA:1, PE:1, PH:1, PL:5, RU:7, SA:45, SE:28, SG:7, TH:46, TR:8, TW:101, UNKNOWN:1, US:846, VG:2, ZA:14 |
| 2023-08 | AE:15, AT:4, AU:91, BE:3, BM:17, BR:28, BS:1, CA:107, CH:26, CL:8, CN:126, CO:1, CW:1, CY:1, DE:35, DK:10, EG:1, ES:12, FI:11, FR:36, GB:74, GR:1, HK:20, HU:2, ID:7, IE:17, IL:14, IN:126, IT:9, JE:8, JP:200, KR:139, KW:6, KY:154, LR:1, LU:4, MH:3, MX:9, MY:18, NL:28, NO:9, NZ:1, PA:1, PE:1, PH:1, PL:5, RU:7, SA:44, SE:28, SG:8, TH:48, TR:8, TW:103, UNKNOWN:1, US:850, VG:2, ZA:14 |
| 2023-09 | AE:15, AT:4, AU:91, BE:3, BM:17, BR:28, BS:1, CA:107, CH:26, CL:8, CN:126, CO:1, CW:1, CY:1, DE:35, DK:10, EG:1, ES:12, FI:11, FR:36, GB:74, GR:1, HK:20, HU:2, ID:7, IE:17, IL:14, IN:126, IT:9, JE:8, JP:200, KR:139, KW:6, KY:154, LR:1, LU:4, MH:3, MX:9, MY:18, NL:28, NO:9, NZ:1, PA:1, PE:1, PH:1, PL:5, RU:7, SA:44, SE:28, SG:8, TH:48, TR:8, TW:103, UNKNOWN:1, US:850, VG:2, ZA:14 |
| 2023-10 | AE:15, AT:4, AU:91, BE:3, BM:17, BR:28, BS:1, CA:107, CH:26, CL:8, CN:126, CO:1, CW:1, CY:1, DE:35, DK:10, EG:1, ES:12, FI:11, FR:36, GB:74, GR:1, HK:20, HU:2, ID:7, IE:17, IL:14, IN:126, IT:9, JE:8, JP:200, KR:139, KW:6, KY:154, LR:1, LU:4, MH:3, MX:9, MY:18, NL:28, NO:9, NZ:1, PA:1, PE:1, PH:1, PL:5, RU:7, SA:44, SE:28, SG:8, TH:48, TR:8, TW:103, UNKNOWN:1, US:850, VG:2, ZA:14 |
| 2023-11 | AE:17, AT:4, AU:90, BE:4, BM:17, BR:28, BS:1, CA:107, CH:26, CL:8, CN:123, CO:1, CW:1, CY:1, DE:35, DK:10, EG:1, ES:12, FI:10, FR:35, GB:73, GR:1, HK:20, HU:2, ID:7, IE:18, IL:15, IN:134, IT:13, JE:8, JP:212, KR:167, KW:6, KY:148, LR:1, LU:5, MH:3, MX:9, MY:19, NL:28, NO:9, NZ:4, PA:1, PE:1, PH:1, PL:5, RU:7, SA:45, SE:26, SG:8, TH:51, TR:8, TW:117, UNKNOWN:1, US:929, VG:2, ZA:13 |
| 2023-12 | AE:17, AT:4, AU:90, BE:4, BM:17, BR:28, BS:1, CA:107, CH:26, CL:8, CN:123, CO:1, CW:1, CY:1, DE:35, DK:10, EG:1, ES:12, FI:10, FR:35, GB:73, GR:1, HK:20, HU:2, ID:7, IE:18, IL:15, IN:134, IT:13, JE:8, JP:212, KR:167, KW:6, KY:148, LR:1, LU:5, MH:3, MX:9, MY:19, NL:28, NO:9, NZ:4, PA:1, PE:1, PH:1, PL:5, RU:7, SA:45, SE:26, SG:8, TH:51, TR:8, TW:117, UNKNOWN:1, US:929, VG:2, ZA:13 |
| 2024-01 | AE:17, AT:4, AU:90, BE:4, BM:17, BR:28, BS:1, CA:107, CH:26, CL:8, CN:123, CO:1, CW:1, CY:1, DE:35, DK:10, EG:1, ES:12, FI:10, FR:35, GB:73, GR:1, HK:20, HU:2, ID:7, IE:18, IL:15, IN:134, IT:13, JE:8, JP:212, KR:167, KW:6, KY:148, LR:1, LU:5, MH:3, MX:9, MY:19, NL:28, NO:9, NZ:4, PA:1, PE:1, PH:1, PL:5, RU:7, SA:45, SE:26, SG:8, TH:51, TR:8, TW:117, UNKNOWN:1, US:929, VG:2, ZA:13 |
| 2024-02 | AE:19, AT:4, AU:81, BE:5, BM:18, BR:27, BS:1, CA:103, CH:27, CL:8, CN:151, CO:1, CW:1, CY:1, DE:35, DK:10, EG:1, ES:12, FI:10, FR:35, GB:71, GR:1, HK:19, HU:2, ID:7, IE:18, IL:15, IN:159, IT:13, JE:9, JP:213, KR:164, KW:6, KY:142, LR:1, LU:5, MH:3, MX:9, MY:17, NL:28, NO:7, NZ:4, PA:1, PE:1, PH:1, PL:5, RU:7, SA:47, SE:23, SG:8, TH:48, TR:21, TW:125, UNKNOWN:1, US:899, VG:2, ZA:13 |
| 2024-03 | AE:19, AT:4, AU:81, BE:5, BM:18, BR:27, BS:1, CA:103, CH:27, CL:8, CN:151, CO:1, CW:1, CY:1, DE:35, DK:10, EG:1, ES:12, FI:10, FR:35, GB:71, GR:1, HK:19, HU:2, ID:7, IE:18, IL:15, IN:159, IT:13, JE:9, JP:213, KR:164, KW:6, KY:142, LR:1, LU:5, MH:3, MX:9, MY:17, NL:28, NO:7, NZ:4, PA:1, PE:1, PH:1, PL:5, RU:7, SA:47, SE:23, SG:8, TH:48, TR:21, TW:125, UNKNOWN:1, US:899, VG:2, ZA:13 |
| 2024-04 | BR:9, CA:3, CL:2, CO:1, CW:1, GB:1, IL:2, IN:4, KR:2, KY:32, PA:1, PE:1, PH:1, RU:3, TW:4, US:871 |
| 2024-05 | BR:9, CA:3, CL:2, CO:1, CW:1, GB:1, IL:2, IN:4, KR:2, KY:32, PA:1, PE:1, PH:1, RU:3, TW:4, US:879 |
| 2024-06 | BR:9, CA:3, CL:2, CO:1, CW:1, GB:1, IL:2, IN:4, KR:2, KY:32, PA:1, PE:1, PH:1, RU:3, TW:4, US:879 |
| 2024-07 | BR:9, CA:3, CL:2, CO:1, CW:1, GB:1, IL:2, IN:4, KR:2, KY:32, PA:1, PE:1, PH:1, RU:3, TW:4, US:879 |
| 2024-08 | AE:19, AT:4, AU:82, BE:5, BM:17, BR:30, BS:1, CA:97, CH:25, CL:8, CN:142, CO:1, CW:1, CY:1, DE:35, DK:14, ES:12, FI:10, FR:33, GB:69, GR:1, HK:19, HU:2, ID:6, IE:19, IL:14, IN:176, IT:13, JE:10, JP:205, KR:146, KW:6, KY:127, LR:1, LU:3, MH:2, MX:8, MY:17, NL:29, NO:7, NZ:4, PA:1, PE:1, PH:1, PL:5, RU:7, SA:48, SE:24, SG:8, TH:41, TR:20, TW:126, UNKNOWN:1, US:850, VG:2, ZA:13 |
| 2024-09 | AE:19, AT:4, AU:82, BE:5, BM:17, BR:30, BS:1, CA:97, CH:25, CL:8, CN:142, CO:1, CW:1, CY:1, DE:35, DK:14, ES:12, FI:10, FR:33, GB:69, GR:1, HK:19, HU:2, ID:6, IE:19, IL:14, IN:176, IT:13, JE:10, JP:205, KR:146, KW:6, KY:127, LR:1, LU:3, MH:2, MX:8, MY:17, NL:29, NO:7, NZ:4, PA:1, PE:1, PH:1, PL:5, RU:7, SA:48, SE:24, SG:8, TH:41, TR:20, TW:126, UNKNOWN:1, US:850, VG:2, ZA:13 |
| 2024-10 | AE:19, AT:4, AU:82, BE:5, BM:17, BR:30, BS:1, CA:97, CH:25, CL:8, CN:142, CO:1, CW:1, CY:1, DE:35, DK:14, ES:12, FI:10, FR:33, GB:69, GR:1, HK:19, HU:2, ID:6, IE:19, IL:14, IN:176, IT:13, JE:10, JP:205, KR:146, KW:6, KY:127, LR:1, LU:3, MH:2, MX:8, MY:17, NL:29, NO:7, NZ:4, PA:1, PE:1, PH:1, PL:5, RU:7, SA:48, SE:24, SG:8, TH:41, TR:20, TW:126, UNKNOWN:1, US:850, VG:2, ZA:13 |
| 2024-11 | AE:20, AT:4, AU:82, BE:5, BM:18, BR:28, BS:1, CA:100, CH:24, CL:8, CN:118, CO:1, CW:1, CY:1, DE:35, DK:14, ES:12, FI:10, FR:33, GB:69, GR:1, HK:19, HU:2, ID:6, IE:22, IL:16, IN:194, IT:13, JE:9, JP:217, KR:145, KW:8, KY:125, LR:1, LU:2, MH:2, MX:8, MY:25, NL:28, NO:6, NZ:4, PA:1, PE:1, PH:1, PL:7, PT:2, RU:5, SA:48, SE:23, SG:8, TH:33, TR:20, TW:150, UNKNOWN:1, US:901, VG:2, ZA:13 |
| 2024-12 | AE:20, AT:4, AU:82, BE:5, BM:18, BR:28, BS:1, CA:100, CH:24, CL:8, CN:118, CO:1, CW:1, CY:1, DE:35, DK:14, ES:12, FI:10, FR:33, GB:69, GR:1, HK:19, HU:2, ID:6, IE:22, IL:16, IN:194, IT:13, JE:9, JP:217, KR:145, KW:8, KY:125, LR:1, LU:2, MH:2, MX:8, MY:25, NL:28, NO:6, NZ:4, PA:1, PE:1, PH:1, PL:7, PT:2, RU:5, SA:48, SE:23, SG:8, TH:33, TR:20, TW:150, UNKNOWN:1, US:901, VG:2, ZA:13 |
| 2025-01 | AE:20, AT:4, AU:82, BE:5, BM:18, BR:28, BS:1, CA:100, CH:24, CL:8, CN:118, CO:1, CW:1, CY:1, DE:35, DK:14, ES:12, FI:10, FR:33, GB:69, GR:1, HK:19, HU:2, ID:6, IE:22, IL:16, IN:194, IT:13, JE:9, JP:217, KR:145, KW:8, KY:125, LR:1, LU:2, MH:2, MX:8, MY:25, NL:28, NO:6, NZ:4, PA:1, PE:1, PH:1, PL:7, PT:2, RU:5, SA:48, SE:23, SG:8, TH:33, TR:20, TW:150, UNKNOWN:1, US:901, VG:2, ZA:13 |
| 2025-02 | AE:22, AT:4, AU:82, BE:5, BM:18, BR:30, BS:1, CA:97, CH:24, CL:8, CN:130, CO:1, CW:1, CY:1, DE:33, DK:14, ES:12, FI:10, FR:35, GB:65, GR:1, HK:19, HU:2, ID:6, IE:22, IL:17, IN:209, IT:13, JE:9, JP:202, KR:131, KW:8, KY:122, LR:1, LU:3, MH:2, MX:8, MY:27, NL:28, NO:5, NZ:4, PA:1, PE:1, PH:1, PL:6, PT:2, RU:5, SA:49, SE:23, SG:9, TH:31, TR:18, TW:147, UNKNOWN:1, US:951, VG:2, ZA:13 |
| 2025-03 | BR:9, CA:5, CL:2, CO:1, CW:1, GB:1, IL:1, IN:4, KR:2, KY:28, PA:1, PE:1, PH:1, RU:1, TW:4, US:900 |
| 2025-04 | BR:9, CA:5, CL:2, CO:1, CW:1, GB:1, IL:1, IN:4, KR:2, KY:28, PA:1, PE:1, PH:1, RU:1, TW:4, US:900 |
| 2025-05 | AE:24, AT:4, AU:81, BE:5, BM:17, BR:25, BS:1, CA:104, CH:25, CL:8, CN:151, CO:1, CW:1, CY:1, DE:34, DK:14, ES:12, FI:9, FR:34, GB:61, GR:1, HK:19, HU:2, ID:6, IE:22, IL:16, IN:261, IT:13, JE:7, JP:209, KR:155, KW:8, KY:130, LR:1, LU:3, MH:2, MX:8, MY:41, NL:28, NO:5, NZ:4, PA:1, PE:1, PH:1, PL:6, PT:2, RU:5, SA:51, SE:22, SG:9, TH:31, TR:18, TW:152, UNKNOWN:1, US:939, VG:2, ZA:13 |
| 2025-06 | AE:24, AT:4, AU:81, BE:5, BM:17, BR:25, BS:1, CA:104, CH:25, CL:8, CN:151, CO:1, CW:1, CY:1, DE:34, DK:14, ES:12, FI:9, FR:34, GB:61, GR:1, HK:19, HU:2, ID:6, IE:22, IL:16, IN:261, IT:13, JE:7, JP:209, KR:155, KW:8, KY:130, LR:1, LU:3, MH:2, MX:8, MY:41, NL:28, NO:5, NZ:4, PA:1, PE:1, PH:1, PL:6, PT:2, RU:5, SA:51, SE:22, SG:9, TH:31, TR:18, TW:152, UNKNOWN:1, US:939, VG:2, ZA:13 |
| 2025-07 | AE:24, AT:4, AU:81, BE:5, BM:17, BR:25, BS:1, CA:104, CH:25, CL:8, CN:151, CO:1, CW:1, CY:1, DE:34, DK:14, ES:12, FI:9, FR:34, GB:61, GR:1, HK:19, HU:2, ID:6, IE:22, IL:16, IN:261, IT:13, JE:7, JP:209, KR:155, KW:8, KY:130, LR:1, LU:3, MH:2, MX:8, MY:41, NL:28, NO:5, NZ:4, PA:1, PE:1, PH:1, PL:6, PT:2, RU:5, SA:51, SE:22, SG:9, TH:31, TR:18, TW:152, UNKNOWN:1, US:939, VG:2, ZA:13 |
| 2025-08 | AE:25, AT:4, AU:83, BE:5, BM:17, BR:27, BS:1, CA:105, CH:26, CL:7, CN:147, CW:1, CY:1, DE:34, DK:13, ES:12, FI:9, FR:34, GB:60, GR:1, HK:19, HU:2, ID:6, IE:22, IL:16, IN:256, IT:13, JE:7, JP:210, KR:158, KW:8, KY:134, LR:1, LU:3, MH:2, MX:8, MY:37, NL:28, NO:5, NZ:4, PA:1, PE:1, PH:3, PL:6, PT:2, RU:5, SA:50, SE:21, SG:9, TH:21, TR:20, TW:142, UNKNOWN:1, US:907, VG:2, ZA:14 |
| 2025-09 | AE:25, AT:4, AU:83, BE:5, BM:17, BR:27, BS:1, CA:105, CH:26, CL:7, CN:147, CW:1, CY:1, DE:34, DK:13, ES:12, FI:9, FR:34, GB:60, GR:1, HK:19, HU:2, ID:6, IE:22, IL:16, IN:256, IT:13, JE:7, JP:210, KR:158, KW:8, KY:134, LR:1, LU:3, MH:2, MX:8, MY:37, NL:28, NO:5, NZ:4, PA:1, PE:1, PH:3, PL:6, PT:2, RU:5, SA:50, SE:21, SG:9, TH:21, TR:20, TW:142, UNKNOWN:1, US:907, VG:2, ZA:14 |
| 2025-10 | AE:25, AT:4, AU:83, BE:5, BM:17, BR:27, BS:1, CA:105, CH:26, CL:7, CN:147, CW:1, CY:1, DE:34, DK:13, ES:12, FI:9, FR:34, GB:60, GR:1, HK:19, HU:2, ID:6, IE:22, IL:16, IN:256, IT:13, JE:7, JP:210, KR:158, KW:8, KY:134, LR:1, LU:3, MH:2, MX:8, MY:37, NL:28, NO:5, NZ:4, PA:1, PE:1, PH:3, PL:6, PT:2, RU:5, SA:50, SE:21, SG:9, TH:21, TR:20, TW:142, UNKNOWN:1, US:907, VG:2, ZA:14 |
| 2025-11 | AE:25, AT:4, AU:86, BE:5, BM:19, BR:28, BS:1, CA:110, CH:27, CL:7, CN:148, CW:1, CY:1, DE:34, DK:13, ES:12, FI:9, FR:36, GB:66, GR:2, HK:20, HU:2, ID:7, IE:22, IL:16, IN:269, IT:13, JE:7, JP:216, KR:167, KW:8, KY:158, LR:1, LU:3, MH:2, MX:8, MY:37, NL:29, NO:4, NZ:4, PA:1, PE:1, PH:3, PL:6, PT:2, RU:5, SA:54, SE:22, SG:9, TH:24, TR:32, TW:148, US:935, VG:4, ZA:14 |
| 2025-12 | AE:25, AT:4, AU:86, BE:5, BM:19, BR:28, BS:1, CA:110, CH:27, CL:7, CN:148, CW:1, CY:1, DE:34, DK:13, ES:12, FI:9, FR:36, GB:66, GR:2, HK:20, HU:2, ID:7, IE:22, IL:16, IN:269, IT:13, JE:7, JP:216, KR:167, KW:8, KY:158, LR:1, LU:3, MH:2, MX:8, MY:37, NL:29, NO:4, NZ:4, PA:1, PE:1, PH:3, PL:6, PT:2, RU:5, SA:54, SE:22, SG:9, TH:24, TR:32, TW:148, US:935, VG:4, ZA:14 |
| 2026-01 | AE:25, AT:4, AU:86, BE:5, BM:19, BR:28, BS:1, CA:110, CH:27, CL:7, CN:148, CW:1, CY:1, DE:34, DK:13, ES:12, FI:9, FR:36, GB:66, GR:2, HK:20, HU:2, ID:7, IE:22, IL:16, IN:269, IT:13, JE:7, JP:216, KR:167, KW:8, KY:158, LR:1, LU:3, MH:2, MX:8, MY:37, NL:29, NO:4, NZ:4, PA:1, PE:1, PH:3, PL:6, PT:2, RU:5, SA:54, SE:22, SG:9, TH:24, TR:32, TW:148, US:935, VG:4, ZA:14 |
| 2026-02 | AE:24, AT:3, AU:91, BE:8, BM:19, BR:27, BS:1, CA:109, CH:27, CL:7, CN:146, CW:1, CY:1, DE:36, DK:20, ES:12, FI:9, FR:37, GB:67, GR:10, HK:21, HU:2, ID:7, IE:20, IL:16, IN:263, IT:13, JE:6, JP:210, KR:158, KW:8, KY:164, LR:1, LU:2, MH:2, MX:8, MY:34, NL:32, NO:4, NZ:4, PA:1, PE:1, PH:4, PL:17, PT:2, RU:5, SA:51, SE:22, SG:9, TH:23, TR:29, TW:151, US:936, VG:5, ZA:13 |
| 2026-03 | AE:24, AT:3, AU:91, BE:8, BM:19, BR:27, BS:1, CA:109, CH:27, CL:7, CN:146, CW:1, CY:1, DE:36, DK:20, ES:12, FI:9, FR:37, GB:67, GR:10, HK:21, HU:2, ID:7, IE:20, IL:16, IN:263, IT:13, JE:6, JP:210, KR:158, KW:8, KY:164, LR:1, LU:2, MH:2, MX:8, MY:34, NL:32, NO:4, NZ:4, PA:1, PE:1, PH:4, PL:17, PT:2, RU:5, SA:51, SE:22, SG:9, TH:23, TR:29, TW:151, US:936, VG:5, ZA:13 |
| 2026-04 | BR:9, CA:9, CL:2, CW:1, GB:1, IL:1, IN:4, KR:2, KY:27, PA:1, PE:1, PH:1, RU:1, TW:4, US:906 |
| 2026-05 | BR:9, CA:10, CL:2, CW:1, GB:1, IL:1, IN:4, KR:2, KY:27, PA:1, PE:1, PH:1, RU:1, TW:4, US:914 |
| 2026-06 | BR:9, CA:10, CL:2, CW:1, GB:1, IL:1, IN:4, KR:2, KY:27, PA:1, PE:1, PH:1, RU:1, TW:4, US:914 |
| 2026-07 | BR:9, CA:10, CL:2, CW:1, GB:1, IL:1, IN:4, KR:2, KY:27, PA:1, PE:1, PH:1, RU:1, TW:4, US:914 |
| 2026-08 | BR:9, CA:10, CL:2, CW:1, GB:1, IL:1, IN:4, KR:3, KY:27, PE:1, PH:1, RU:1, TW:4, US:905 |
| 2026-09 | BR:9, CA:10, CL:2, CW:1, GB:1, IL:1, IN:4, KR:3, KY:27, PE:1, PH:1, RU:1, TW:4, US:905 |

## Historically observable company audit

The queries below use explicit name aliases observed in cached historical records, not a present-day constituent list. Names label audit results; they never create eligibility or backfill earlier membership. Absence means not observed in the selected proxy portfolio, not proof of absence from MSCI or that the issuer delisted. `Provisional` can overlap `Eligible` when a second share line is unclassified.

| Company query | Eligible months | Observed months in latest public portfolio | Provisional months |
|---|---|---|---|
| NVIDIA | 2022-10–2026-09 | 2022-10–2026-09 | none |
| Microsoft | 2022-10–2026-09 | 2022-10–2026-09 | none |
| Apple | 2022-10–2026-09 | 2022-10–2026-09 | none |
| Tesla | 2022-10–2026-09 | 2022-10–2026-09 | none |
| Micron | 2022-10–2026-09 | 2022-10–2026-09 | none |
| TSMC | 2022-10–2026-09 | 2022-10–2026-09 | 2026-08–2026-09 |
| SK Hynix | 2022-10–2024-03; 2024-08–2025-02; 2025-05–2026-03 | 2022-10–2026-09 | 2024-04–2024-07; 2025-03–2025-04; 2026-04–2026-09 |
| Broadcom | 2022-10–2026-09 | 2022-10–2026-09 | none |
| ASML | 2022-10–2024-03; 2024-08–2025-02; 2025-05–2026-03 | 2022-10–2026-09 | 2024-04–2024-07; 2025-03–2025-04; 2026-04–2026-09 |
| AMD | 2022-10–2026-09 | 2022-10–2026-09 | none |
| Samsung Electronics | 2022-10–2024-03; 2024-08–2025-02; 2025-05–2026-03 | 2022-10–2026-09 | 2024-04–2024-07; 2025-03–2025-04; 2026-04–2026-09 |
| Applied Materials | 2022-10–2026-09 | 2022-10–2026-09 | none |
| Lam Research | 2022-10–2026-09 | 2022-10–2026-09 | none |
| KLA | 2022-10–2026-09 | 2022-10–2026-09 | none |
| Qualcomm | 2022-10–2026-09 | 2022-10–2026-09 | none |
| Intel | 2022-10–2026-09 | 2022-10–2026-09 | none |
| Texas Instruments | 2022-10–2026-09 | 2022-10–2026-09 | none |
| Tokyo Electron | 2022-10–2024-03; 2024-08–2025-02; 2025-05–2026-03 | 2022-10–2026-09 | 2024-04–2024-07; 2025-03–2025-04; 2026-04–2026-09 |
| NXP | 2022-11–2024-03; 2024-08–2025-02; 2025-05–2026-03 | 2022-11–2026-09 | 2024-04–2024-07; 2025-03–2025-04; 2026-04–2026-09 |
| Infineon | 2024-08–2025-02; 2025-05–2026-03 | 2024-04–2026-09 | 2024-04–2024-07; 2025-03–2025-04; 2026-04–2026-09 |
| STMicroelectronics | none | 2026-08–2026-09 | 2026-08–2026-09 |
| MediaTek | 2022-10–2024-03; 2024-08–2025-02; 2025-05–2026-03 | 2022-10–2026-09 | 2024-04–2024-07; 2025-03–2025-04; 2026-04–2026-09 |
| United Microelectronics | 2022-10–2026-09 | 2022-10–2026-09 | none |
| ASE Technology | none | 2026-04–2026-09 | 2026-04–2026-09 |

NVIDIA, Microsoft, Apple, Tesla, Micron and TSMC are confirmed eligible in **all 48 months**. SK Hynix is observed in all 48 but is confirmed in 36 and provisional in the 12 workbook months. The SEC-only alternative confirms SK Hynix in every month. This is an instrument-mapping gap, not a historical membership deletion.

TSMC's confirmed observations include its U.S. ADR; primary Taiwan shares are a separate unclassified workbook line in August–September 2026. `Taiwan Semiconductor Co Ltd` is a different issuer and is explicitly excluded from the TSMC query. Multiple TSMC lines are never merged as one security, and local shares are not priced using ADR units. NVIDIA is not inferred to be eligible because it is a large constituent today.

The June 2026 SEC portfolio, public August 28, also explicitly holds TSMC primary shares (`TW0002330008`) alongside its ADR (`US8740391003`). That primary line is available in the SEC-only alternative in August–September. The newer workbook reports a different generic Identifier plus SEDOL without an ISIN crosswalk; company-name similarity is not used to invent the missing security-ID join, so its primary line remains provisional in the latest-portfolio universe.

`company_appearance_evidence.csv.gz` preserves every matching eligible/provisional row, all identifiers, original portfolio/publication dates, source filing/URL, and membership/classification/ticker/country evidence. `company_appearances.csv` also records the SEC-only comparison. These files allow each monthly appearance to be checked against an actual historical source.

## Strategy readiness

The strategy was inspected read-only in [`dual_momentum/trial.py`](../dual_momentum/trial.py), with supporting data semantics in [`dual_momentum/data.py`](../dual_momentum/data.py). The current execution harness is an S&P 500 paper trial and calls `current_sp500()`; it does not consume these global research exports. No strategy module was imported or executed by the universe builder.

The inspected rules use 63/126/252-session returns and volatility, 0.50/0.30/0.20 risk-adjusted ranking, EMA50/EMA200, SPY relative 63-session qualification, protected raw Top-15 incumbents, a five-session lockout, and five allocations of 30/25/20/15/10% with the existing 2% reserve. They also require sector breadth with at least 90% signal coverage, sector ETF comparisons and the existing 50% sector cap, plus 3.5× Wilder ATR stops based on prior-close data. None of these rules was altered.

| Requirement | Status | Source / approximation and remaining limitation |
|---|---|---|
| Prior-public proxy membership and provenance | Satisfied for research | 48 monthly reconstructions with strictly prior release/capture bounds and exact source records; no current-survivor backfill |
| Actual MSCI ACWI IMI membership | Not supplied | SPGM sampling, stale holdings and non-index exposures remain; cannot present the proxy as official historical constituents |
| Contemporaneous monthly membership | Approximation | Latest-public portfolios are 13–123 days old; between-observation entries/exits and exact effective dates are unknown |
| Common-equity instrument types | Partial / blocker for complete global universe | SEC EC is explicit; exact-ID historical carry-forward is disclosed; 12 workbook months leave many rows provisional and introduce a strong geographic coverage bias |
| Distinct issuer/company identities | Approximation | Dated source LEIs plus explicitly labeled historical-name grouping; no complete issuer/ultimate-parent crosswalk or reliable company-level duplicate policy |
| Country distribution | Partial approximation | SEC issuer-organization codes and disclosed stale exact-ID joins; not MSCI risk-country assignment or verified exchange country; XX and unresolved cases stay unknown |
| Security IDs | Partial | Valid ISIN/CUSIP/SEDOL retained, with duplicate audit; format/checksum validity alone does not verify issuer, listing, instrument type or the workbook generic Identifier's authority |
| Historical tickers, primary listings and currency/unit basis | Blocker | Pre-April 2024 SEC-based universes have no source tickers. Later exact-ID archive lookups cover only part; exchange MICs remain unverified. ADR/local lines and ticker changes cannot be silently substituted |
| Security-level historical GICS sectors | Blocker for every month | Zero complete monthly classifications. SEC asset categories and aggregate sector weights are not individual GICS. No approximate GICS mapping was applied |
| Sector regime/breadth and sector concentration | Blocker | Missing sectors prevent correct grouping and the 50% cap; putting every name into Unknown or dropping the sector filter would change the strategy |
| Historical sector/benchmark reference series | Not established for global test | Existing code names SPY and U.S. sector ETFs (XLK, XLC, XLY, XLP, XLE, XLF, XLV, XLI, XLB, XLRE, XLU). Keeping these is a disclosed U.S.-benchmark approximation, not verified global sector representation; full historical inputs have not been assembled |
| Prices, dividends/splits, FX and delisting outcomes | Blocker | No complete global price history was joined; the October 2022 decision needs roughly October 2021 price warm-up. Known sample corrections do not validate thousands of securities or terminal returns |
| ATR, stops, calendars and execution | Blocker | Needs compatible split-only OHLC/share units, complete local sessions, lagged FX, liquidity/tradability and historical delisting/restriction handling. Positive holdings units do not establish tradability |
| Existing execution integration | Not performed | Research outputs remain separate; the S&P-specific harness and its breadth checks were preserved |

Potential GICS enrichment must retain the classification scheme, instrument/issuer IDs, effective dates, original publication/availability dates, source and reuse permissions. A dated historical GICS vendor table could address the blocker. Current sectors carried backwards would be an explicit retrospective approximation and cannot pass this point-in-time audit; SIC/NAICS or a classifier would be different taxonomies, not silently relabeled GICS. No such mapping was obtained or used here.

For exploratory research, the SEC-only lagged alternative avoids the workbook type-coverage collapse, but cannot cure missing sectors, listings or historical price inputs. A faithful five-stock sector-aware global backtest remains **blocked**. The next work is historical security/issuer/listing and GICS crosswalks with availability dates, then complete price/FX/corporate-action inputs and unchanged-rule verification in an isolated historical harness.

## Reproduction and local artifacts

```sh
# Repository root; both commands are entirely offline.
PYTHONPYCACHEPREFIX=/workspace/.cache/isk-trading-radar-pycache python -m research.spgm_universe
PYTHONPYCACHEPREFIX=/workspace/.cache/isk-trading-radar-pycache python -m research.spgm_universe_report
PYTHONPYCACHEPREFIX=/workspace/.cache/isk-trading-radar-pycache /workspace/.venvs/eodhd-validation/bin/python -m unittest discover -s research -p 'test_*.py'
```

Inputs are the audited `snapshots.json` and `holdings.csv` under `research/eodhd_output/spgm_proxy/`. Outputs are exclusively in ignored `point_in_time_universe/`: 48 eligible and 48 provisional compressed CSVs, monthly summary CSV/JSON, country distribution, exclusions, company appearances/evidence and an input/output hash manifest. Gzip timestamps are fixed for reproducibility. Original portfolios and their normalization are never overwritten.

Only research source, synthetic regression tests and this aggregate report are suitable for Git. Large security-level files, downloaded source data and credentials remain excluded. No trades were executed, current constituent list fetched, sector inferred or EODHD request made.

Strategy source SHA-256 inspected without modification: `b30c1ea2dc4e83286580a80aaa73e6176f74c393c8f709591ff0fe54b95282e6`.

Validation: **64 research tests passed**, including 17 universe-construction regressions. The full monthly exports were checked for strict publication cutoffs, source hashes, counts, country totals, duplicate handling and absence of retrospective tickers or sector imputations.
