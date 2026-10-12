# GEMv1 historical membership research audit — 2026-10-12

**RESEARCH ONLY / NOT A CERTIFICATION / NO ORDERS / FROZEN GEMv1 UNCHANGED.**
Read-only public secondary data; do not import this artifact or modules from GEMv1 rank, order, QA-certification or paper-model code.

## Reproducible inputs

The workflow `.github/workflows/gem-public-membership-research.yml` reconstructs all explicit dates from:
- https://raw.githubusercontent.com/lawcal/sp500-components-history/main/data/components_history.csv
- https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv (current only, never historic)
- https://raw.githubusercontent.com/pierrebrunelle/sp500-historical-constituents/main/data/spyYYYYMM (dated independent *public* reconstructions; not primary official index publications)

CI run: https://github.com/ankitgarg1234-cell/isk-trading-radar/actions/runs/38249936787 (**14 tests passed; bounded public retrieval succeeded**). The CI artifact is `gem-public-membership-research-not-certified`. Its source SHA-256 hashes, timestamps, raw and screened member lists, and unresolved discrepancies form the reproducible research evidence. Public sources can change; never overwrite or silently treat current rows as historical source receipts.

## Historical ticker-era contamination

This is a non-exhaustive, evidence-linked list of **ticker corrections**, not proof of index membership. The registry uses first-listed/effective trade dates and issuer CIKs to quarantine an impossible historical ticker. It does **not** merge/collapse separate share classes or automatically replace a merger successor with predecessor prices.

| New ticker | Earlier identity / treatment | Earliest new-ticker session | Documentary evidence |
|---|---|---|---|
| ELV | ANTM | 2022-06-28 | [SEC issuer 10-K](https://www.sec.gov/Archives/edgar/data/1156039/000115603923000007/elv-20221231.htm) |
| BALL | BLL | 2022-05-10 | [SEC issuer 8-K](https://www.sec.gov/Archives/edgar/data/9389/000000938922000010/bll-20220427x8k.htm) |
| META | FB | 2022-06-09 | [SEC issuer announcement](https://www.sec.gov/Archives/edgar/data/1326801/000132680122000070/may312022-exhibit991.htm) |
| GEN | NLOK | 2022-11-08 | [SEC issuer announcement](https://www.sec.gov/Archives/edgar/data/849399/000110465922115277/tm2229813d1_ex99-01.htm) |
| PARA | VIAC | 2022-02-17 | [SEC issuer 8-K](https://www.sec.gov/Archives/edgar/data/813828/000081382822000011/viac-20220216.htm) |
| COR | ABC | 2023-08-30 | [SEC filing](https://www.sec.gov/Archives/edgar/data/1140859/000110465923096698/tm2324358d1_8k.htm) |
| FI | FISV | 2023-06-07 | [Fiserv](https://investors.fiserv.com/news-releases/news-release-details/fiserv-completes-listing-transfer-new-york-stock-exchange) |
| EG | RE | 2023-07-10 | [Everest](https://investors.everestglobal.com/news/news-details/2023/Everest-to-Rebrand-Company-Name-and-NYSE-Ticker-to-Reflect-its-Evolution-Global-Growth-and-Diversification-Strategy/default.aspx) |
| RVTY | PKI | 2023-05-16 | [SEC filing](https://www.sec.gov/Archives/edgar/data/31791/000003179123000011/pki-20230702.htm) |
| DAY | CDAY | 2024-02-01 | [Dayforce](https://investors.dayforce.com/news-and-events/press-releases/press-release-details/2024/Ceridian-to-change-ticker-symbol-to-DAY-on-NYSE-and-TSX-effective-February-1/default.aspx) |
| CPAY | FLT | 2024-03-25 | [SEC filing](https://www.sec.gov/Archives/edgar/data/1175454/000162828024010593/flt-20240307.htm) |
| DOC | PEAK | 2024-03-04 | [SEC filing](https://www.sec.gov/Archives/edgar/data/765880/000110465924029661/tm247564d1_8k.htm) |
| BNY | BK | 2026-05-21 | [BNY](https://www.bny.com/corporate/global/en/about-us/newsroom/press-release/bny-announces-planned-change-of-stock-ticker-symbol-to-bny-130465.html) |
| MRSH | MMC | 2026-01-14 | [Marsh](https://www.marsh.com/en/corp/about/news/marsh-mclennan-to-change-nyse-symbol-to-mrsh.html) |
| VMRK | Equity Residential/AvalonBay merger; **NO automatic predecessor substitution** | 2026-08-18 | [Issuer statement](https://investors.vivmarkresidential.com/news-events/press-releases/detail/113/vivmark-residential-launches-as-one-of-the-countrys-leading-real-estate-companies) |
| PSKY | Paramount merger; **NO automatic PARA substitution** | 2025-08-07 | [Nasdaq corporate action](https://m.nasdaqtrader.com/TraderNews.aspx?id=ECA2025-414) |
| SKYD | Successor merger entity; **NO historical PSKY/PARA price backfill** | 2026-10-07 | [Public market report](https://www.investopedia.com/market-update-skydance-shares-slide-after-merger-with-warner-bros-discovery-12161228) |
| SW | Merger-created Smurfit Westrock; **NO automatic WRK substitution** | 2024-07-08 | [SEC issuer release](https://www.sec.gov/Archives/edgar/data/2005951/000110465924078355/tm2418700d1_ex99-2.htm) |

**Important:** `GOOG/GOOGL`, `FOX/FOXA` and `NWS/NWSA` are retained as separate share classes despite shared issuer CIKs. **One CIK ≠ one tradable line.** Remaining CIK/share-class collisions stay unresolved until authenticated issuer security IDs and corporate actions are available.

## Raw history vs conservative ticker-era screen

These are **not** official index sizes. A reduced row count does not make the universe historically correct. Counts come from the bounded public research workflow. The January 2022 source overcount was largely caused by modern ticker names projected backward into predecessor periods.

| Snapshot | Raw history rows | Rows after documented ticker-era exclusions | Remaining research issue |
|---|---:|---:|---|
| 2022-01-31 | 522 | 505 | 17 documented future/retired ticker-era lines quarantined; true source membership still unproven |
| 2022-12-30 | 515 | 503 | Monthly public reference has future-listed `SW`, and historical true-membership confirmation is outstanding |
| 2023-06-30 | 514 | 503 | Monthly reference also contains future-recast ticker identities; historic eligibility not official |
| 2023-12-29 | 512 | 503 | Historical public comparison has post-date ticker substitutions; no primary index provenance |\n| 2024-12-31 | 509 | 503 | Historic reconciliation must be checked per stable security ID |
| 2025-09-30 | 508 | 503 | Retrospective creation/publication flags remain |
| 2026-04-30 | 507 | 503 | Differences with separate April source, including recently effective security events |
| 2026-09-30 | 504 | 502 | Under-coverage risk despite plausible raw count |

Public lawcal history includes `created_at` dates that can be later than the historical signal session. That means retroactively entered facts should never be presented as information contemporaneously observable at the 2022/2023 cutoff.

## Critical finding: the alternative public monthly list also has future symbols

For example, the *January 2022* `spy202201` file labels securities with then-unavailable ticker identities such as `COR` (Cencora), `CPAY` (Corpay), `DAY` (Dayforce), `RVTY` (Revvity), `PSKY` (Paramount Skydance), and `SW` (Smurfit Westrock). This is a **retrospective re-labelled history, not original point-in-time trading symbols**. The research pipeline now checks those monthly names against documented effective dates and separately records any name-matched future/retired ticker without manufacturing a predecessor row. Unrelated reuse of the same ticker stays marked ambiguous. The two public datasets are sensitivity inputs, not independent point-in-time certifications.

## GEM top-five selection-impact status

**UNDETERMINED — cannot responsibly claim a changed top-five yet.** Historical monthly membership snapshots alone contain no independently reconstructed 127 completed-session OHLCV bars, r63/ADV20, all competing 10-Q accession facts, corporate actions, nominal prices, or SEC publication receipts. The isolated GEM Neon database had 0 GEM signals, 0 source receipts, 6 diagnostic probes, 8 shadow observations, and 0 independent QA reviews when checked on 2026-10-12. Thus there is no completed per-month certified rank path to compare.

For every disputed security, construct two *unmodified frozen strategy* sensitivity runs:
1. **Source A as-of ticker era:** research snapshot after documented identity screens, with ambiguities tracked, not discarded from coverage proof.
2. **Source B as-of ticker era:** independent monthly snapshot, with future-listed symbols explicitly rejected and missing lines marked UNKNOWN (not force-added).

Only rerun each original historical top-five when the required full-universe price, liquidity and original SEC fact evidence exists at the signal cutoff. If a candidate's rank/eligibility is unknown, return **INDETERMINATE**, not a synthetic performance number. Preserve both per-source ranks and complete discrepancy logs.

## Other open deficiencies

- Original effective-dated constituent announcements / stable security ID and share class lineage.
- Possible holiday/session-date mismatches versus official NYSE completed-session calendar.
- Complete stocks including delisted names, 127 prior completed daily bars and adjusted/nominal OHLC vendor parity.
- All candidate and competing securities' original SEC 10-Q gate facts and publication timestamps.
- Splits, dividends, corporate mergers, delistings, successor treatment and payment/ex-date reconciliations.
- SPY aligned cash/dividend total-return benchmark evidence, sign-off, independent QA and reproduction tests.

No changes to GEMv1 strategy parameters, Paper Model, deployments, portfolio, orders or certificate statuses were made as part of this research.
