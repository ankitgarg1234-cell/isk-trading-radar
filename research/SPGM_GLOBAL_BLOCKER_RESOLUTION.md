# Global five-stock strategy: input blockers and implementation proposal

**Dataset: SPGM historical ETF holdings proxy — not official MSCI ACWI IMI constituents.**

Audit: 10 October 2026, branch `research/eodhd-acwi-imi-setup`. The two existing research commits (`ebba8e0`, `947dc47`) were pushed first and the remote branch head was verified as `947dc47318e04421d2670c8f9285e31946dcece1`. Only research code, documentation, tests and small manually verified evidence were in those commits. Downloads, generated security-level exports and credentials remain outside Git. This follow-up changes research tooling and documentation only; no strategy was executed, no trading rules were modified and no EODHD requests were made.

## Decision

**Not ready for an exploratory backtest that faithfully implements the five-stock sector-aware strategy.** Ready for offline membership, identifier and data-adapter diagnostics. A momentum-only simulation or a U.S.-heavy mapped subset would answer a different question. Neither would resolve the required global sector breadth, allocation caps or historically available listing inputs.

The holdings evidence supports all 48 month-end reconstructions. It does not establish tradability or security-level historical GICS. Prior-public membership is a disclosed ETF sampling and stale-portfolio approximation, not monthly MSCI membership. The report's proposed thresholds are research acceptance gates, **not changes to the strategy's thresholds**. Passing them would support an exploratory proxy backtest, not prove full-index completeness.

## Quantified completeness

The reproducible [48-month completeness matrix](SPGM_STRATEGY_COMPLETENESS.md) and priority-company matrix audit **106,463 eligible security-month observations**. Denominators include the entire confirmed equity subset at each cutoff, rather than only names for which prices are easy to obtain.

| Input | Measured coverage | Consequence |
|---|---:|---|
| At least one valid typed ISIN/CUSIP/SEDOL | 106,463 / 106,463 (100%) | Checksum validity supports joins; it does not prove issuer, venue or instrument equivalence |
| Prior-public ticker observation | 28,141 / 106,463 (26.43%) | 78,322 missing observations; 18 early months have none |
| Dated, verified exchange listing with ticker, MIC and currency | 0 / 106,463 | A bare ticker is not a verified execution/price symbol |
| Historical security-level GICS | 0 / 106,463 | All 48 sector regimes and concentration calculations blocked |
| Valid source issuer LEI | 79,879 / 106,463 (75.03%) | 26,584 gaps; LEI is issuer evidence, not necessarily ultimate-parent identity |
| Observed ambiguous ticker, conflicting exact ID/LEI, ambiguous resolved issuer | 0 each | No conflicts detected in available metadata; missing evidence is not proven unambiguous |
| Provisional instrument coverage | 12 / 48 months affected | 1,798–2,027 provisional instruments per workbook month |

All confirmed rows have usable typed identifiers and no recorded invalid-alternate flags. The parser's exclusions and the provisional pool remain outside that 100% denominator; this does not certify all downloaded positions. Duplicate exposures were collapsed with original row evidence retained. Distinct share classes and depositary receipts remain distinct securities. Exact company counts remain unavailable: reported company groups partly use historical normalized names. A company's multiple listings must not acquire two identities merely because its ticker differs.

The confirmed workbook subsets contain 938–979 securities and **92.86–93.56% U.S. issuer-country representation**, versus roughly 32–35% in SEC-based months. This is an identifier/classification bias. Resolve the international workbook joins or explicitly choose the separately disclosed, older SEC-only universe (2,403–2,910 equities), consistently across all 48 months. Do not switch sources after seeing returns. Source portfolio ages of 13–123 days and the absence of between-snapshot membership events remain even after mapping fixes. Issuer organization country is not MSCI risk country, listing venue or trading currency.

### Resolution priorities

1. **U.S. and U.S.-listed leaders:** NVIDIA, Microsoft, Apple, Tesla, Micron, AMD, Broadcom, Applied Materials, Lam Research, KLA, Qualcomm, Intel and Texas Instruments. All are confirmed in 48 months. Most have 30 months of ticker observations, but none has a verified dated listing or historical GICS attached. Lam Research has 29 observed-ticker months: investigate its corporate-action/identifier transition without assigning a present ticker backward. Tesla is included as a requested ranking candidate, not automatically assigned a technology sector.
2. **International semiconductor/memory leaders:** SK Hynix, Samsung Electronics, ASML, Tokyo Electron and MediaTek are observed in 48 months but confirmed in 36, with 12 provisional workbook months. Their confirmed rows have no PIT ticker mappings. Resolve typed-ID ↔ SEDOL ↔ local share-line links, effective listing dates, ordinary/preferred distinctions, MIC, currency and price units. Treat candidate symbols `000660.KO`, `005930.KO`, `2454.TW`, `8035` and ASML's local/ADR lines as resolution targets, not historical verification. No new provider requests have been made.
3. **TSMC and other multiple-line cases:** TSMC is eligible in all 48 months through its ADR (`US8740391003`); local `TW0002330008` is separately evidenced by the June 2026 SEC filing, public August 28. Its workbook primary line is provisional in August–September. Do not substitute `2330.TW` for ADR prices or use name similarity to join generic IDs. United Microelectronics likewise needs ADR/local distinctions. NXP has 35 confirmed months, Infineon 18, ASE zero (six provisional), STMicroelectronics zero (two provisional); these are selected-source observations, not evidence of index deletion or delisting.
4. **Broader technology and breadth repair:** the audit adds ten queries using names actually observed in the cached portfolios. Adobe, Alphabet, Amazon, Meta, Oracle, Salesforce and ServiceNow are confirmed in all48 months; Alphabet retains two distinct share classes (96 security-month observations). SAP and Hon Hai are confirmed in36 months and provisional in12. Samsung Electro-Mechanics has zero confirmed and two provisional months in the selected source. These observations do not establish primary-listing coverage. Then resolve the entire equity universe across every country and all11 sectors: a technology shortlist cannot establish sector participation or veto conditions.

Priority names do not form an eligibility whitelist or a current-constituent backfill. LEIs observed for these confirmed leaders reduce issuer ambiguity but cannot validate an unresolved SEDOL/local-listing join or supply historical GICS.

## Historical GICS sources and evidentiary limits

Public documentation was retrieved independently of EODHD; HTML/PDF bodies and hashes are cached under ignored `research/eodhd_output/spgm_proxy/strategy_audit/sources/`. No company sectors were assigned from these documents.

| Source | What was verified | Historical use and limitation |
|---|---|---|
| [MSCI GICS resources](https://www.msci.com/indexes/index-resources/gics) | Public global four-level taxonomy, historical structures, annual reviews and methodology links | Historical **taxonomy** is not historical company classifications; use dated versions to interpret codes, never to invent issuer assignments |
| [MSCI GICS Direct overview](https://www.msci.com/downloads/documents/indexes/gics/MSCI%20GICS%20Overview.pdf) | Joint MSCI/S&P global company-classification database; daily/monthly delivery and ongoing corporate-action reviews | Strongest source family to request a licensed historical extract; brochure does not establish the availability, announcement timestamps or full 2022–26 coverage of a historical extract |
| [MSCI GICS methodology](https://www.msci.com/index/methodology/latest/GICS) | Retrieved version April 2026; issuer activity, revenue/earnings and review procedures | Current methodology does not verify historical assignment. Classifications can change with restructurings and annual reports |
| [31 March 2022 review announcement](https://www.msci.com/downloads/documents/indexes/gics/GICS_Press_Release_31_March_2022.pdf) | GICS Direct/S&P DJI implementation after U.S. close March 17, 2023; affected-company lists offered to clients | Must version classifications across this boundary. Do not assume identical effective timing in every index product; obtain product-specific events and issuer lists |
| [WRDS S&P Global catalog](https://wrds-www.wharton.upenn.edu/pages/about/data-vendors/sp-global-market-intelligence/) | Compustat North America and Global products; `comp_global_daily` catalog entry | Candidate licensed route. Detailed [Compustat manuals](https://wrds-www.wharton.upenn.edu/pages/support/manuals-and-overviews/compustat/) redirected to login. Historical GICS fields, global small-cap/delisted coverage, effective intervals and public-knowledge timestamps remain **unverified**, not a delivered solution |
| Archived publisher holdings/fund reports with explicit GICS | Potential dated issuer-to-sector observations if source states GICS, provides stable IDs and has a prior-public release/capture bound | Existing SPGM workbooks have blank sectors; four NPORT-EX observations give aggregate sector weights only. Other ETF sources would need an independently audited historical crosswalk; another ETF's current sector map is insufficient |
| Official historical index/fund factsheets or reclassification notices | Sparse explicit classifications may be auditable for named securities at particular dates | Only a dated, exact-ID observation or authoritative event supports that date/interval. Sparse top holdings cannot classify the rest or be silently carried backward |
| Current issuer profiles, broker/Yahoo sectors, OpenFIGI, SIC/NAICS/business descriptions | Useful for identity resolution or a separately labeled research approximation | Current/inferred classifications are not historical GICS. SIC/NAICS and SEC EC asset types do not map uniquely to GICS. Name/business similarity is not authoritative assignment evidence |

**Rights are a concrete prerequisite:** retrieved MSCI documents restrict redistribution and database/analytics uses. They were consulted for source evaluation; no MSCI company-classification database was constructed or redistributed. Obtain terms permitting the intended historical research/backtest before using a vendor extract or republishing classifications. Public download access alone is insufficient. Licensed catalogs require entitlement; no login restriction was bypassed.

Required classification contract: security and issuer IDs, GICS sector code/name (prefer all four levels), taxonomy version, effective-from/to timestamps, announcement/first-known timestamp, source record and version, license scope, and historical-vs-current verification status. Preserve both effective and known dates. If a delivered history was reconstructed later and lacks knowledge timestamps, explicitly label it **historically effective, knowledge timing unverified**; it cannot satisfy a strict PIT gate. Carrying forward an old snapshot without event-completeness evidence is **inferred carry-forward**, not verified historical classification. Sector transitions require event timing, not retrospective application of today's taxonomy.

## Read-only audit of the existing implementation

Line references refer to unchanged [`dual_momentum/trial.py`](../dual_momentum/trial.py). This is a forward-only S&P 500 paper-trial harness, not a global historical engine. The complete U.S./currency input surfaces identified by static inspection are below.

| Lines / input surface | Assumption and global consequence |
|---|---|
| 1–6, 23–29, 47–59 | One-month October/November 2026 trial, fixed $10,000 cash, dedicated trial state/table. Dates and single-currency state must be parameterized for research; do not invoke its live ledger |
| 30–44 | Eleven sector ETFs: XLK/XLC/XLY/XLP/XLE/XLF/XLV/XLI/XLB/XLRE/XLU; America/New_York timezone. ETFs represent U.S. sectors, not global sectors |
| 94–106, 537–552 | Weekday-only next session; NY 16:20 completed-bar cutoff; one date applies to all symbols. Fails on different holidays, half days, extraordinary closures, overnight timezone dates and vendor availability |
| 114–146 | Requires 253 observations; 63/126/252 session returns, sample vol ×sqrt(252), EMA50/200 on total-return close; Wilder ATR on OHLC. Session counts presume one exchange calendar and prices in a consistent share/currency coordinate. Native calendars create different elapsed windows; preserve session lengths rather than silently switch to calendar-month returns |
| 149–194 | SPY current/prior signal, two-close EMA200 bear test, sector ETF EMA200 and R63>SPY; sector names must exactly match ETFS; breadth coverage≥90%. Unknown sectors are absent from regime grouping, rather than safely classified |
| 197–260 | NAV=cash+shares×close; floor sizing NAV×weight/close; holdings keyed solely by symbol. No FX or price-unit scaling. `Unknown` becomes one concentration bucket. Symbol alphabetical tiebreaks assume unique, stable U.S. symbols |
| 208–246, 273–362 | Protected raw Top-15, R63>SPY challenger screen and five-session lockout; explicit SPY-session list or weekday fallback; ranking audit text hardcodes SPY. Global symbol/country variants must not create duplicate candidates or silently change tiebreaks |
| 372–435 | $1 minimum/$0.005 per share commission, 7bp modeled slippage, integer shares and one cash balance; all buys funded after same-date sell order processing. No currency conversions, board lots or settlement distinction; initial stop floor $0.01 and ATR in same dollars as fill |
| 438–465 | Local low/open used against stored stop, open-gap fill, close-based trailing update. Stops/shares have no currency/unit or split ledger; `peak` is recorded but trailing formula actually uses close−3.5ATR, not peak−3.5ATR |
| 468–519 | Minimum 450 valid stock signals, same daily date/cutoff, SPY/XL* regime; sector market values and 0.5% NAV drift tolerance assume common currency; stored shortlist and raw marks used for sizing |
| 557–629 | Yahoo `2y` source; SPY query gates all progress; current S&P membership≥480; ETF/SPY symbols mixed with U.S. stock symbols. Historical replay would otherwise use current membership and current sectors |
| 604–658 | At least 254 SPY bars; SPY defines all completed replay sessions, lockout clock, initial benchmark and daily NAV; every held stock must have an exact same-date close. Month-end detected by next weekday instead of a holiday-aware session calendar; pending fills before stops, then marks and decision/risk stage |
| 660–689, 700–730 | Diagnostic backfills and monthly decisions slice prices by date but reuse current membership; ≥450 signal gate; SPY sessions and SPY R63 supplied to target/ranking functions |
| 734–835 | Read-only ranking refresh again calls current_sp500 with≥480 members and≥450 signals, and retrieves current `2y` histories; its sector metadata can describe current rather than historical decisions |
| 838–918, 939–949 | NY 09:45 delayed-open observation and16:20 replay switch, weekdays only, one scheduled fill date; Yahoo UTC timestamp date used as a session label. Assumes all orders share one opening and delays; unsafe for Asia/Europe and early-close sessions |
| Supporting data.py 200–220, 337–394 | Current S&P CSV sectors/CIK:symbol identity and Yahoo symbol normalization; daily OHLC+adjusted close, UTC date extraction; currency/timezone metadata and split events not validated/applied by this parser. A `PriceBar` carries no MIC/currency/price-unit contract |

The separate `data.py.sp500_at()` helper is not called by this trial. Its existence does not make the trial's membership or sectors PIT. Pure returns are invariant to a **constant** currency scaling, but time-varying FX changes ranking, volatility and EMA signals; different local currencies cannot be mixed in NAV. Source N-PORT USD valuations are not historical local price/FX data. The EMA calculation seeds from the first supplied observation and processes the entire supplied history; the current source's rolling `2y` request affects that seed. A new fixed-window or expanding-history policy can alter EMA thresholds even with identical last252 returns. Freeze the exact input-history/seed convention in parity fixtures and disclose any historical-engine extension; do not silently choose whichever window produces better results.

Additional accounting caveat: total-return adjusted closes feed signals and benchmark P&L, while the trial stock ledger marks OHLC and does not explicitly credit cash dividends or process splits/delistings. A faithful research implementation must specify whether it reproduces this modeling limitation or introduces economically complete cash-flow accounting. The latter is an explicit accounting extension, not something to conceal in a data adapter. The trial ending freezes rather than automatically liquidates; do not invent a terminal sale.

## Proposed global implementation, without changing rules now

Build a separate offline research adapter/event replay; keep the live trial and its data source untouched. Retain security-level holdings semantics: no new one-company-one-stock constraint, no liquidity/memory/technology whitelist, and no ADR/local substitutions. Keep issuer links for audits and potential future risk decisions, not to change eligibility.

**Preserve exactly:** equal-average R63/R126/R252 raw ranking; sample volatility annualization252; risk score0.50/0.30/0.20; EMA50/200; protected positive-score raw Top-15 incumbents above EMA200; qualified challengers above both EMAs with R63 above reference; five positions, five-session post-stop lockout; final risk ordering and deterministic symbol tiebreak; 30/25/20/15/10% weights, 2% reserve, regime multiplier, 50% sector cap pro-rata without redistributing freed cash; integer-share floors and insufficient-cash reductions. Preserve monthly rotation and membership-based exits, forward next-open staging, sell-before-buy funding where events actually permit it, 7bp modeled fills plus existing fee formula, prior-close3.5×Wilder ATR initial stop, gap behavior, nondecreasing close-based trailing stop, daily regime/sector review, 0.5% drift tolerance, missed-order fail-closed behavior and missing-data vetoes.

The existing regime table must remain intact:

| SPY regime | Bull sectors | Sole-sector breadth | Equity cap |
|---|---:|---|---:|
| Bull | ≥2 | any | 100% |
| Bull | 1 | >70% / 50–70% / <50% | 90% / 70% / 0% |
| Bull | 0 | any | 0% |
| Bear: below EMA200 two consecutive closes | ≥2 | any | 50% |
| Bear | 1 | ≥60% / 50–<60% / <50% | 50% / 40% / 0% |
| Bear | 0 | any | 0% |

Sector bull remains ETF above EMA200, sector R63>reference R63, breadth≥50% and signal coverage≥90%. Do not relax these gates for global data scarcity.

| Adapter / explicit policy | Proposal and fidelity boundary |
|---|---|
| Membership | Freeze a versioned proxy source before each actual signal cutoff, with original portfolio/publication dates and source filing. Current exports use month-end23:59:59UTC; regenerate for the exact chosen signal timestamp before execution research, rather than relabeling them as NY-close universes |
| Instrument identity | Immutable internal security key with dated ticker+MIC aliases. Store observed PIT symbol for secondary sorting; document ordering of collisions across venues. Renaming or choosing a primary listing can change ties and universe membership, so cannot be silently optimized |
| Sector map | Dated prior-known GICS at each signal and risk review. No `Unknown` catch-all, current map or guessed business-sector conversions in a faithful run. Hold unresolved records in denominator/audit, not silently drop them |
| Reference inputs | Closest rule-preserving variant keeps **SPY and all eleven XL* ETFs**, and is labeled “global SPGM proxy with U.S. regime reference.” Substituting SPGM/ACWI and global sector indexes preserves formulas but changes entry/regime signals; this is a distinct future strategy variant requiring explicit choice. Do not synthesize sector indexes from today's constituents |
| Base currency | USD is the closest extension to the current dollar ledger. Compute total-return signal series in USD using dated local-currency TR×USD-per-local-unit FX. Report that FX-inclusive returns are the consequence of a common investment currency, not equivalent to local-currency rankings. Alternative local-return rankings require a separate policy decision |
| ATR/stops | Use split/share-representation-normalized OHLC in **local quote units**, with the existing AZN conversion logic preserved. Do not use dividend-adjusted closes as OHLC or multiply an entire day's OHLC by one FX quote and claim true USD intraday extrema. Apply stop triggers in local units, translate realized fills/marks to USD using observable FX; transform shares/cost/stop coordinate consistently at actual actions |
| Time and calendars | Use exact exchange-local dates and UTC close/open/publication timestamps. Retain NY completed-close research reference, each instrument's latest completed local signal and native session windows; no future Asian bar. Require latest expected session, not a fabricated reference-date bar. For the closest variant keep lockout counted on SPY reference sessions; local-session lockout would be an explicit alternative |
| Execution | Fill only at each venue's first actual open after the signal and availability cutoff. Async sells cannot fund earlier Asian buys; order by timestamp and fund only with available modeled cash. Missing opens cannot be filled later without the original missed-order policy. A venue-aware ledger is essential, not a single-date batch fiction |
| Risk/NAV | Evaluate global marks and exposure at the reference decision time; closed-market last close is a labeled stale mark, not a new zero-return trading session. USD-convert exposures and all fees before applying same weights/caps/drift. Track daily stops on actual venue sessions even when SPY is closed; specify a reference-cycle daily risk review |
| U.S. count gates | 480-member/450-signal absolutes were safeguards for≈500 S&P names. They would accept severely incomplete global data. Replace only their data-validation role with the full-universe acceptance gates below, while keeping sector coverage≥90%; acknowledge this harness change explicitly |
| Currency/lot/accounting | Integer-share sizing remains; native board-lot, restricted-market access, actual country commissions/FX spread/tax and settlement are feasibility diagnostics, not silently added filters or cost rules. Price tick minimum replaces meaningless local0.01 only if explicitly agreed. Preserve original cost baseline for comparison; separate realistic-cost sensitivity. Dividend cash flows and delisting recovery need an approved accounting specification |

No global benchmark, calendar, currency, fee or issuer-deduplication policy was applied in this task. A U.S.-only fixture with identity FX, identical sessions and the same sectors must reproduce the unchanged trial's decisions/quantities/caps/stops before any global implementation can claim parity.

## Quantitative blocker-resolution gates

These are proposed **data acceptance thresholds** for an exploratory study. They are not evidence that 98% arbitrary coverage removes bias. Record denominators and failures per month, country and sector; no return-driven exclusions.

| Requirement | Exploratory acceptance gate | Current finding |
|---|---|---|
| Source timing and auditability | 100% of used rows/field evidence strictly prior-public; exact UTC cutoff; source hash/date/filing retained; all48 dates reconciled | Calendar-cutoff membership satisfied; exact execution cutoff still needs regeneration |
| Equity type / source bias | ≥98% of identifiable positive-unit equity candidates resolved with independent instrument-type evidence; ≤2% unresolved; every material country (≥1% of candidate equities)≥95%; preferred/cash not assumed stock | Workbook months fail; candidate denominator itself requires instrument resolution |
| Listing map | ≥98% of confirmed equities mapped to dated unique ticker/MIC/currency/unit; each material country≥95%; zero ambiguous mappings used in signals/orders | 0% verified |
| Historical GICS | ≥98% historically verified sector coverage each month and≥95% each material country; all candidates with valid price signals and all held/selected names 100%; unresolved sectors remain an explicit full-universe coverage veto | 0% |
| Issuer/security ambiguity | Zero contradictory typed-ID/listing/issuer joins in used data; ≥99% resolved issuer links among usable signals; 100% among holdings, raw Top15 and proposed entries | LEI gaps24.97%; other historical identifier evidence may resolve them, LEI alone is not mandatory |
| Momentum / sector breadth | ≥95% of confirmed equity universe has complete qualifying-or-disqualifying signal history each month; **each sector's original90% gate remains mandatory**, material-country coverage≥90%; explicitly disclosed IPO/history exclusions | Not measured globally; no download attempted |
| Selected/held/control inputs | 100% complete254 reference bars for two-close regime,253 stock/sector bars for momentum, ATR history, actual fill/stop OHLC and observable FX for used events; no unresolved missing active-position valuation | Not established |
| Session/action integrity | 100% used bars on actual sessions; zero unresolved representation/action discontinuities on used windows; preserve genuine extreme returns with corroboration | Existing AZN/Taiwan/Korea regressions provide examples, not all-universe coverage |
| Archive/source age | ≤125 days for chosen quarterly-lag proxy; report all ages and stale-source exposure; do not pretend it is current monthly membership | 13–123 days at existing cutoffs; passes only this explicit lagged-proxy assumption |

For a fully faithful **complete-proxy** ranking, listing/sector/price coverage must reach100% or a recorded rule-consistent reason must make a security unusable (e.g. insufficient post-IPO history). At98% a missing high-momentum name can still alter the Top5. Therefore compare missing-name bounds and rank sensitivity before making performance claims; “leader coverage100%” is necessary for diagnostics, not sufficient for global selection. Do not certify a selected Top15 from a truncated price universe. The original90% breadth gate is not permission to drop unknown sectors or entire countries.

## Historical price and FX download specification — plan only

**No downloads or provider calls are authorized by this specification alone. No EODHD calls were made.** Resolve symbol/rights contracts first; estimate endpoint costs before any separately authorized fetch. Reuse cache without altering observations.

| Deliverable | Contract |
|---|---|
| Security master | For every historically observed eligible/provisional equity, retain ISIN/CUSIP/SEDOL/LEI and source IDs; dated ticker aliases, MIC, issuer link, ordinary/preferred/ADR ratio, primary-vs-secondary status, listing/delisting and rename dates, ISO4217 currency, price scale (e.g. GBp→GBP), timezone and tick/lot units. Later-delivered maps may establish historical facts only with dated evidence; never supply future membership |
| Scope and warm-up | All historically observed confirmed equities, not just current survivors or requested leaders; price before first appearance for indicator warm-up and after source exit for existing positions. Request daily histories from **2021-01-01** through **2026-09-30**, extending to the first later venue opening only if September orders are modeled. First stored selection is Oct31 2022, not an assumed Oct1 start. Check253/254 actual sessions per required window rather than assume a calendar year suffices |
| Equity/benchmark daily records | Raw actual-date OHLCV, local session date, UTC open/close and first-available timestamp, quote currency/unit, unadjusted close and separate vendor-adjusted/TR close, status/suspension, source URL/provider ID, retrieval time, hash and revision version. Include SPY+all11XL* full histories in the closest variant. Preserve delisted companies and explicit gaps |
| Actions and adjustments | Split/consolidation/ADR/share-representation ratios, dividends (gross/net and ex/pay dates), spin-offs/mergers/tender/delisting events, effective/public times and independent corroboration. Store raw and separate split-only OHLC factors; reconcile vendor adjustment basis. Normalize OHLC consistently for ATR, use TR for momentum, never overwrite raw or “repair” a jump merely by its size |
| AZN / Korea / Taiwan acceptance cases | Preserve Feb2 2026 AZN normalization and transform old/new share coordinate consistently; preserve independently verified Jul31 Korea+26.81/+29.95/+29.92% returns; retain original Hon Hai/ASE Jul10 observations in raw cache but exclude confirmed closed sessions from derived inputs; no guessed redating. Calendars must encode the independently verified Taiwan extraordinary closure |
| FX | ISO currency per quote, **USD per one major local currency unit**, bid/ask or documented midpoint/reference fixing, exact timestamp/first-available time, source/license/revision. Include all currencies required by verified listings, not issuer countries. Need exchange-close observations for signals/marks and pre-open/execution observations for modeled fills; a daily fixing published later cannot price an earlier opening. USD/USD=1. Quote direction and pence/sen scaling have explicit tests |
| FX sources and gaps | Evaluate public central-bank reference series (e.g. ECB USD-cross derivations where available) for reproducible research; their currency coverage and publication times may not serve every local open. Otherwise obtain licensed historical timestamped FX. Cross rates require two synchronous, prior-known legs. Carry only the most recent already-public fixing through known fixing holidays, labeled stale; maximum5 calendar days for exploratory marks, never infer executable opening FX from a later fixing. Missing FX blocks that event |
| Calendars and availability | Official exchange holidays, half days, suspensions, exceptional closures and timezone/DST history. Compare source bars against actual sessions; missing-session and non-trading-bar problems distinct. Never forward-fill OHLC or returns across missing actual sessions; a held stale valuation is explicitly separate from a trading bar |
| Validation / storage | Reconcile OHLC inequalities, positivity, duplicates, price-unit/action continuity, genuine extreme returns, expected-session gaps, survivorship/delistings and adjustment factors. Retain request-cost/retrieval ledger and failures; deterministic partitioned CSV/Parquet outputs with checksums under ignored storage. Commit only tooling, synthetic tests and aggregate research reports |

A provider's present-day adjusted series is generally a retrospectively revised history. Record that limitation and avoid absolute-level signals spanning mixed adjustment vintages. Future dividends/splits must not rewrite a prior frozen decision. Freeze an as-of-consistent factor basis and test invariance of return/EMA decisions to uniform scaling; verify stop/share invariance through actual representation changes. Native ATR and FX returns require separate coordinates and accounting tests.

## Work order and validation

1. Select a consistent latest-portfolio or SEC-only lagged proxy policy before observing performance; repair security master joins and exact signal cutoffs.
2. Obtain a rights-permitted historical GICS extract or individually auditable dated publisher records; report verified/current/inferred coverage separately and keep zero-assignment gaps honest.
3. Resolve prioritized U.S., Korean, Taiwanese, European and Japanese share lines, then reach country/sector completeness gates across the full universe. Do not call leader diagnostics readiness.
4. Approve reference/currency/calendar/accounting choices, then separately authorize a budgeted historical price/FX acquisition. The current task grants no new EODHD requests.
5. Build adapter/parity fixtures without changing trial rules; test PIT publication/effective intervals, symbol changes, ADR/local non-equivalence, asynchronous cash funding, split/share stop invariance, closures, genuine extreme returns and missing-data vetoes.
6. Only after quantitative gates and parity pass, run an explicitly labeled exploratory **SPGM historical ETF holdings proxy** backtest with failure/missing-name sensitivity reports. Do not label results MSCI ACWI IMI performance.

Reproduce this audit offline:

```bash
PYTHONPYCACHEPREFIX=/workspace/.cache/isk-trading-radar-pycache \
  /workspace/.venvs/eodhd-validation/bin/python -m research.spgm_strategy_audit
PYTHONPYCACHEPREFIX=/workspace/.cache/isk-trading-radar-pycache \
  /workspace/.venvs/eodhd-validation/bin/python -m unittest discover -s research -p 'test_*.py'
```

Validation: **71 research tests passed**, including seven new regressions rejecting current/inferred/undated sectors, future publication/effective dates, expired intervals, unverified ticker/MIC combinations and conflicting identifier/issuer evidence. All97 existing compressed universe exports and the original holdings/snapshot inputs match their previously saved hashes. The48 completeness-audit inputs reconcile to106,463 security-months. Strategy files have no changes.

Ignored outputs: monthly/priority completeness CSVs, input-hash summary, generated aggregate Markdown, and public documentation cache. The committed completeness matrix is an aggregate report, not a downloaded holdings/price dataset. Its count metrics distinguish source ticker observations, checksum-valid security identifiers and actually verified listings; no source observation is upgraded by inference.
