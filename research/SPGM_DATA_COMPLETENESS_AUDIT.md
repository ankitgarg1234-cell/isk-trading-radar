# SPGM data completeness audit

**SPGM historical ETF holdings proxy — not official MSCI ACWI IMI constituents.**

Offline audit of the latest cached research state. No data requests, trades or backtest execution. All 48 frozen SEC-only universes are checksum-checked; the inventory denominator is the 36 monthly universes from October 2023 through September 2026. September 2023 prelaunch membership remains outside this denominator; the October experiment would additionally require its September 29 signal inputs.

**4,236 distinct security lines**, 98,838 security-month observations. Original instrument keys: 4,237. Deduplication uses only co-observed valid ISIN/CUSIP/SEDOL aliases. Issuer LEIs, names and tickers never collapse share classes or ordinary/ADR lines. Conflicting identifier components are quarantined.

| Primary status | Securities |
|---|---:|
| BACKTEST_READY | 0 |
| PARTIALLY_READY | 316 |
| IDENTITY_UNRESOLVED | 2,784 |
| NO_USABLE_PRICE_DATA | 1,136 |

Resolved candidate instrument identities: **1,452**. Securities with identity-linked valid bars overlapping observed membership months: **316**. Securities with any ticker-linked price candidates: **319**. Identifier conflicts: **0**; ticker ambiguities: **22**.

A resolved identity means a unique archived exact-ID ticker line or current exact-ISIN exchange record. It does not prove the venue, currency or listing effective interval for every historical selection. PARTIALLY_READY requires such a resolved line and at least some valid cached bars during an observed membership month; it makes no claim of adequate history. Unresolved identity takes priority over price availability; resolved identities without overlapping usable bars are NO_USABLE_PRICE_DATA.

## Requirement coverage

| Requirement | Pass | Fail |
|---|---:|---:|
| listing | 0 | 4,236 |
| ohlcv | 0 | 4,236 |
| adjustment | 0 | 4,236 |
| corporate_actions | 0 | 4,236 |
| gics | 0 | 4,236 |
| calendar_timezone | 0 | 4,236 |
| fx | 1,145 | 3,091 |
| pit_membership | 4,236 | 0 |

Pass flags are independent and fail closed. No complete dated listing bundle, 2021 seed history, validated full-period split/TR tape, complete action ledger or calendar/time-zone bundle is present. Without verified listing-start/delisting evidence, a shorter history cannot receive an IPO or delisting exemption. No verified FX tape exists; USD identity conversion passes only for uniquely resolved USD lines, with the currency evidence recorded separately. A position currency alone does not establish trading currency.

Sector labels in the legacy cache are undated. The cached current S&P 500 GICS table has source provenance but no approved exact-security overlay. Ticker-only current-sector candidates are recorded separately, never treated as historically verified or admitted GICS. The existing STRICT_PIT and EXPLORATORY_CURRENT_GICS policies and coverage thresholds are unchanged. 298 security lines have unadmitted current sector candidates; 8 have adjusted-close candidates, 30 have partial split lists and 244 have partial dividend lists. None of these counts establishes full requirement coverage.

Membership passes only for checksum-valid non-conflicting identifiers, confirmed SEC holdings, a source filing and timezone-aware publication strictly before the actual selection cutoff. This verifies observed ETF proxy membership, not continuous ownership between portfolios or official index membership.

## Country and sector coverage

| Dimension | Value | Securities | Ready |
|---|---|---:|---:|
| country | AE | 29 | 0 |
| country | AT | 4 | 0 |
| country | AU | 137 | 0 |
| country | BE | 8 | 0 |
| country | BM | 25 | 0 |
| country | BR | 52 | 0 |
| country | BS | 1 | 0 |
| country | CA | 160 | 0 |
| country | CH | 32 | 0 |
| country | CL | 8 | 0 |
| country | CN | 256 | 0 |
| country | CO | 1 | 0 |
| country | CW | 1 | 0 |
| country | CY | 1 | 0 |
| country | DE | 46 | 0 |
| country | DK | 22 | 0 |
| country | EG | 1 | 0 |
| country | ES | 13 | 0 |
| country | FI | 14 | 0 |
| country | FR | 44 | 0 |
| country | GB | 93 | 0 |
| country | GR | 11 | 0 |
| country | HK | 23 | 0 |
| country | HU | 2 | 0 |
| country | ID | 18 | 0 |
| country | IE | 24 | 0 |
| country | IL | 29 | 0 |
| country | IN | 349 | 0 |
| country | IT | 14 | 0 |
| country | JE | 13 | 0 |
| country | JP | 300 | 0 |
| country | KR | 288 | 0 |
| country | KW | 8 | 0 |
| country | KY | 234 | 0 |
| country | LR | 1 | 0 |
| country | LU | 6 | 0 |
| country | MH | 3 | 0 |
| country | MX | 10 | 0 |
| country | MY | 45 | 0 |
| country | NL | 42 | 0 |
| country | NO | 9 | 0 |
| country | NZ | 4 | 0 |
| country | PA | 1 | 0 |
| country | PE | 1 | 0 |
| country | PH | 5 | 0 |
| country | PL | 18 | 0 |
| country | PT | 2 | 0 |
| country | RU | 7 | 0 |
| country | SA | 70 | 0 |
| country | SE | 34 | 0 |
| country | SG | 12 | 0 |
| country | TH | 71 | 0 |
| country | TR | 51 | 0 |
| country | TW | 254 | 0 |
| country | UNKNOWN | 1 | 0 |
| country | US | 1,304 | 0 |
| country | VG | 7 | 0 |
| country | ZA | 17 | 0 |
| sector | UNRESOLVED | 4,236 | 0 |

Country counts use the unique SEC issuer-country value across observed months; conflicting values are MULTIPLE and absent values UNKNOWN. These are issuer countries, not listing venues. Original per-month country, currency and identifiers remain in the inventory evidence. The breakdown CSV additionally splits each country and sector by all four readiness statuses.

## SPY and eleven sector ETFs

| Symbol | Cached | First | Last | Valid bars | Prelaunch bars / required | Ready |
|---|---|---|---|---:|---:|---|
| SPY | False |  |  | 0 | 0 / 254 | False |
| XLK | True | 2022-11-28 | 2026-10-01 | 964 | 211 / 253 | False |
| XLC | True | 2022-11-28 | 2026-10-01 | 964 | 211 / 253 | False |
| XLY | True | 2022-11-28 | 2026-10-01 | 964 | 211 / 253 | False |
| XLP | True | 2022-11-28 | 2026-10-01 | 964 | 211 / 253 | False |
| XLE | True | 2022-11-28 | 2026-10-01 | 964 | 211 / 253 | False |
| XLF | True | 2022-11-28 | 2026-10-01 | 964 | 211 / 253 | False |
| XLV | True | 2022-11-28 | 2026-10-01 | 964 | 211 / 253 | False |
| XLI | True | 2022-11-28 | 2026-10-01 | 964 | 211 / 253 | False |
| XLB | True | 2022-11-28 | 2026-10-01 | 964 | 211 / 253 | False |
| XLRE | True | 2022-11-28 | 2026-10-01 | 964 | 211 / 253 | False |
| XLU | True | 2022-11-28 | 2026-10-01 | 964 | 211 / 253 | False |

**Correction to the previous aggregate inventory:** all eleven sector ETF tapes exist under `wf3_prices.json.gz:sector_etfs`; checking only `market` incorrectly reported them absent. SPY is genuinely absent. The separate `^SP500TR` benchmark is an index and cannot substitute for SPY. The ETF tapes still fail the October 2023 warm-up and full-history/provenance requirements.

## Closest 100 security lines

Sorted by passed requirement count, resolved identity, usable cached bars and stable identifier; no return-based or strategy-based selection. These are data-resolution priorities, not an investable universe. Every missing field is listed.

| Security | Stable key | Status | Cached symbol | First price | Missing fields |
|---|---|---|---|---|---|
| Schlumberger NV | isin:AN8068571086 | PARTIALLY_READY | SLB | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Carnival Corp | isin:PA1436583006 | PARTIALLY_READY | CCL | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Aflac Inc | isin:US0010551028 | PARTIALLY_READY | AFL | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| AES Corp/The | isin:US00130H1059 | PARTIALLY_READY | AES | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| AT&T Inc | isin:US00206R1023 | PARTIALLY_READY | T | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Abbott Laboratories | isin:US0028241000 | PARTIALLY_READY | ABT | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| AbbVie Inc | isin:US00287Y1091 | PARTIALLY_READY | ABBV | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Adobe Inc | isin:US00724F1012 | PARTIALLY_READY | ADBE | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Advanced Micro Devices Inc | isin:US0079031078 | PARTIALLY_READY | AMD | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Agilent Technologies Inc | isin:US00846U1016 | PARTIALLY_READY | A | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Airbnb Inc | isin:US0090661010 | PARTIALLY_READY | ABNB | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Air Products and Chemicals Inc | isin:US0091581068 | PARTIALLY_READY | APD | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Albemarle Corp | isin:US0126531013 | PARTIALLY_READY | ALB | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Align Technology Inc | isin:US0162551016 | PARTIALLY_READY | ALGN | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Allstate Corp/The | isin:US0200021014 | PARTIALLY_READY | ALL | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Alphabet Inc | isin:US02079K1079 | PARTIALLY_READY | GOOG | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Alphabet Inc | isin:US02079K3059 | PARTIALLY_READY | GOOGL | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Altria Group Inc | isin:US02209S1033 | PARTIALLY_READY | MO | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Amazon.com Inc | isin:US0231351067 | PARTIALLY_READY | AMZN | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| American Airlines Group Inc | isin:US02376R1023 | PARTIALLY_READY | AAL | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| American Electric Power Co Inc | isin:US0255371017 | PARTIALLY_READY | AEP | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| American Express Co | isin:US0258161092 | PARTIALLY_READY | AXP | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| American Tower Corp | isin:US03027X1000 | PARTIALLY_READY | AMT | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Amgen Inc | isin:US0311621009 | PARTIALLY_READY | AMGN | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Amphenol Corp | isin:US0320951017 | PARTIALLY_READY | APH | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Analog Devices Inc | isin:US0326541051 | PARTIALLY_READY | ADI | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Elevance Health Inc | isin:US0367521038 | PARTIALLY_READY | ELV | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| APA Corp | isin:US03743Q1085 | PARTIALLY_READY | APA | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Apollo Global Management Inc | isin:US03769M1062 | PARTIALLY_READY | APO | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Apple Inc | isin:US0378331005 | PARTIALLY_READY | AAPL | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Applied Materials Inc | isin:US0382221051 | PARTIALLY_READY | AMAT | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| AppLovin Corp | isin:US03831W1080 | PARTIALLY_READY | APP | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Archer-Daniels-Midland Co | isin:US0394831020 | PARTIALLY_READY | ADM | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Autodesk Inc | isin:US0527691069 | PARTIALLY_READY | ADSK | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Automatic Data Processing Inc | isin:US0530151036 | PARTIALLY_READY | ADP | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Axon Enterprise Inc | isin:US05464C1018 | PARTIALLY_READY | AXON | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Baker Hughes Co | isin:US05722G1004 | PARTIALLY_READY | BKR | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Bank of America Corp | isin:US0605051046 | PARTIALLY_READY | BAC | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Bath & Body Works Inc | isin:US0708301041 | PARTIALLY_READY | BBWI | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Baxter International Inc | isin:US0718131099 | PARTIALLY_READY | BAX | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Becton Dickinson & Co | isin:US0758871091 | PARTIALLY_READY | BDX | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Biogen Inc | isin:US09062X1037 | PARTIALLY_READY | BIIB | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Blackstone Inc | isin:US09260D1072 | PARTIALLY_READY | BX | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Bloom Energy Corp | isin:US0937121079 | PARTIALLY_READY | BE | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Boeing Co/The | isin:US0970231058 | PARTIALLY_READY | BA | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Booking Holdings Inc | isin:US09857L1089 | PARTIALLY_READY | BKNG | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Boston Scientific Corp | isin:US1011371077 | PARTIALLY_READY | BSX | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Bristol-Myers Squibb Co | isin:US1101221083 | PARTIALLY_READY | BMY | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Broadcom Inc | isin:US11135F1012 | PARTIALLY_READY | AVGO | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Builders FirstSource Inc | isin:US12008R1077 | PARTIALLY_READY | BLDR | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Cboe Global Markets Inc | isin:US12503M1080 | PARTIALLY_READY | CBOE | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| CF Industries Holdings Inc | isin:US1252691001 | PARTIALLY_READY | CF | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| CH Robinson Worldwide Inc | isin:US12541W2098 | PARTIALLY_READY | CHRW | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Cigna Group/The | isin:US1255231003 | PARTIALLY_READY | CI | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| CME Group Inc | isin:US12572Q1058 | PARTIALLY_READY | CME | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| CSX Corp | isin:US1264081035 | PARTIALLY_READY | CSX | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| CVS Health Corp | isin:US1266501006 | PARTIALLY_READY | CVS | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Cadence Design Systems Inc | isin:US1273871087 | PARTIALLY_READY | CDNS | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Caesars Entertainment Inc | isin:US12769G1004 | PARTIALLY_READY | CZR | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Capital One Financial Corp | isin:US14040H1059 | PARTIALLY_READY | COF | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Carrier Global Corp | isin:US14448C1045 | PARTIALLY_READY | CARR | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Carvana Co | isin:US1468691027 | PARTIALLY_READY | CVNA | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Caterpillar Inc | isin:US1491231015 | PARTIALLY_READY | CAT | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Centene Corp | isin:US15135B1017 | PARTIALLY_READY | CNC | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Charter Communications Inc | isin:US16119P1084 | PARTIALLY_READY | CHTR | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Chevron Corp | isin:US1667641005 | PARTIALLY_READY | CVX | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Chipotle Mexican Grill Inc | isin:US1696561059 | PARTIALLY_READY | CMG | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Church & Dwight Co Inc | isin:US1713401024 | PARTIALLY_READY | CHD | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Cisco Systems Inc | isin:US17275R1023 | PARTIALLY_READY | CSCO | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Cintas Corp | isin:US1729081059 | PARTIALLY_READY | CTAS | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Citigroup Inc | isin:US1729674242 | PARTIALLY_READY | C | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Citizens Financial Group Inc | isin:US1746101054 | PARTIALLY_READY | CFG | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Clorox Co/The | isin:US1890541097 | PARTIALLY_READY | CLX | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Coca-Cola Co/The | isin:US1912161007 | PARTIALLY_READY | KO | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Cognizant Technology Solutions Corp | isin:US1924461023 | PARTIALLY_READY | CTSH | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Coherent Corp | isin:US19247G1076 | PARTIALLY_READY | COHR | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Coinbase Global Inc | isin:US19260Q1076 | PARTIALLY_READY | COIN | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Colgate-Palmolive Co | isin:US1941621039 | PARTIALLY_READY | CL | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Comfort Systems USA Inc | isin:US1999081045 | PARTIALLY_READY | FIX | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Comcast Corp | isin:US20030N1019 | PARTIALLY_READY | CMCSA | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Conagra Brands Inc | isin:US2058871029 | PARTIALLY_READY | CAG | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| ConocoPhillips | isin:US20825C1045 | PARTIALLY_READY | COP | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Constellation Energy Corp | isin:US21037T1097 | PARTIALLY_READY | CEG | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Corning Inc | isin:US2193501051 | PARTIALLY_READY | GLW | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Corteva Inc | isin:US22052L1044 | PARTIALLY_READY | CTVA | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Costco Wholesale Corp | isin:US22160K1051 | PARTIALLY_READY | COST | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| CoStar Group Inc | isin:US22160N1090 | PARTIALLY_READY | CSGP | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Crowdstrike Holdings Inc | isin:US22788C1053 | PARTIALLY_READY | CRWD | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Cummins Inc | isin:US2310211063 | PARTIALLY_READY | CMI | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| DR Horton Inc | isin:US23331A1097 | PARTIALLY_READY | DHI | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Danaher Corp | isin:US2358511028 | PARTIALLY_READY | DHR | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Datadog Inc | isin:US23804L1035 | PARTIALLY_READY | DDOG | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Deckers Outdoor Corp | isin:US2435371073 | PARTIALLY_READY | DECK | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Deere & Co | isin:US2441991054 | PARTIALLY_READY | DE | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Dell Technologies Inc | isin:US24703L2025 | PARTIALLY_READY | DELL | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Devon Energy Corp | isin:US25179M1036 | PARTIALLY_READY | DVN | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Dexcom Inc | isin:US2521311074 | PARTIALLY_READY | DXCM | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Digital Realty Trust Inc | isin:US2538681030 | PARTIALLY_READY | DLR | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Walt Disney Co/The | isin:US2546871060 | PARTIALLY_READY | DIS | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |
| Dollar General Corp | isin:US2566771059 | PARTIALLY_READY | DG | 2022-11-28 | listing;ohlcv;adjustment;corporate_actions;gics;calendar_timezone |

## Selected technology and listing distinctions

| Observed security | ISIN | Status | Mapped cached symbol |
|---|---|---|---|
| AstraZeneca PLC | GB0009895292 | IDENTITY_UNRESOLVED |  |
| SK hynix Inc | KR7000660001 | PARTIALLY_READY | 000660.KO |
| ASML Holding NV | NL0010273215 | IDENTITY_UNRESOLVED |  |
| Taiwan Semiconductor Manufacturing Co Ltd | TW0002330008 | PARTIALLY_READY | 2330.TW |
| Apple Inc | US0378331005 | PARTIALLY_READY | AAPL |
| AstraZeneca PLC | US0463531089 | PARTIALLY_READY | AZN.US |
| Hon Hai Precision Industry Co Ltd | US4380908057 | IDENTITY_UNRESOLVED |  |
| Microsoft Corp | US5949181045 | PARTIALLY_READY | MSFT |
| Micron Technology Inc | US5951121038 | PARTIALLY_READY | MU |
| NVIDIA Corp | US67066G1040 | PARTIALLY_READY | NVDA |
| Samsung Electronics Co Ltd | US7960508882 | IDENTITY_UNRESOLVED |  |
| Taiwan Semiconductor Manufacturing Co Ltd | US8740391003 | NO_USABLE_PRICE_DATA |  |
| Tesla Inc | US88160R1014 | PARTIALLY_READY | TSLA |

The historical Samsung and Hon Hai lines above have US security identifiers; the cached Korean Samsung ordinary and Taiwanese Hon Hai ordinary prices cannot be transferred onto these depositary-receipt lines. Both the Taiwanese ordinary and US ADR TSMC lines are preserved. AstraZeneca UK ordinary and US ADR identities remain separate; preserved US conversion normalization does not supply a UK ordinary price history.


## Complete-data securities

None. The ready-ticker CSV contains its header and zero security rows.

## Evidence, storage and reproducibility

Full inventory: `/workspace/isk-trading-radar/research/eodhd_output/spgm_proxy/historical_backtest/data_completeness/SPGM_DATA_COMPLETENESS_INVENTORY.csv` (68,647,315 bytes; 4,236 rows). It is retained in ignored research storage because its detailed per-month security-level observations are large. Git contains the audit code, tests, aggregate breakdown, ready-ticker file and this report.

Inventory SHA256: `2b660030dbf1b6abe7c2e7990788c9c1b52e515c700e92047558042804e51fb1`.

Each inventory row preserves all names and valid identifiers, observed monthly membership, original portfolio/publication timestamps, decision cutoffs, SEC accession/URL/source hashes, country and position currency, ticker crosswalk evidence, current exact-ISIN exchange records, cached price source/section/SHA256, valid/invalid/closed-session/duplicate counts and precise missing reasons. `summary.json` contains all input checksums; `source_discovery.json` enumerates scanned data files; `reference_inputs.csv` covers the reference instruments. No source prices are edited or committed.

Sources: SEC N-PORT frozen monthly confirmed holdings; prior archived SPGM identifier/ticker evidence; current cached EODHD Korean/Taiwanese exchange symbol lists; fourteen original EODHD short price samples and their preserved split/session-filtered derivatives; legacy equity/sector-ETF/benchmark cache. IBKR baseline counts have no underlying bars and supply no usable price history. Legacy fundamentals and strategy NAV/trade results are not price tapes. Synthetic parity fixtures are excluded. The repository CSV/gzip/data-container scan includes all real price sections, not just equity market. The workspace attachments, library-files, scratch and shared directories were also checked: no additional datasets were present. This audit covers locally retained checkout research datasets, not unavailable prior machines or remote accounts.

Taiwan July 10, 2026 observations are excluded from the diagnostic usable-bar count, with original observations preserved. Existing AstraZeneca split-only normalization remains untouched and is not transferred to another security ISIN. USD-labelled ADR samples are never joined to foreign ordinary holdings by issuer name. Recent adjusted-close fields and partial split/dividend lists do not prove full-period corporate-action or total-return correctness.

Reproduce offline: `python -m research.spgm_data_completeness`. Inputs are SHA256-checked after generation, including every original confirmed monthly file.

## What can legitimately be tested

Zero fully ready securities means no legitimate historical five-stock experiment can be supported by the fully ready set. Even a reduced-universe return diagnostic is blocked by SPY warm-up and the missing validated adjustment/action/calendar/classification inputs. No backtest was run.

After inputs are resolved, any reduced-universe diagnostic must intersect each historical confirmed SEC-only month with a fixed, predeclared data-admissibility rule, preserve additions/deletions and share classes, and use only portfolio publications available before the original selection cutoff. It must disclose exclusion of uncovered securities/countries/sectors and selection on later data availability (including survivorship bias). Today's constituents cannot fill gaps, and the result cannot represent the full SPGM proxy or MSCI ACWI IMI. For now, only descriptive identity/coverage diagnostics are supported.

The audit stops here. No strategy rules or admission gates were modified, no data acquired and no backtest executed.

## Validation

138 research tests passed, including ten new regression tests. Inventory uniqueness, exhaustive status counts, missing-field/pass-flag consistency, inventory SHA256 and original holdings/snapshot hashes were verified.
