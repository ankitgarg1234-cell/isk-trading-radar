# Global backtest master status

**Current continuation:** user-approved current-GICS exploratory admission is
implemented;both readiness modes remain blocked. See the continuation table
andlatest final report below. The earlier phase table records the strict
checkpoint,not a requirement to obtain historical GICS for exploratory mode.

Updated 10 October 2026 (Europe/Stockholm). Branch `research/eodhd-acwi-imi-setup`.
Target: 1 October 2023–30 September 2026, $10,000, unchanged five-stock rules.
Global configuration: **SPGM HISTORICAL ETF HOLDINGS PROXY**, SEC-only lagged
portfolios; SPY and the original eleven U.S. sector ETFs remain the references.

| Task | Current status | Evidence | Dependencies | Next action | Completion criteria |
|---|---|---|---|---|---|
| Phase 0: verify prior work | COMPLETE | Branch head544e5fd; all six requested documents and three strategy modules present; 71 research tests passed;21 cached portfolios/48 universes present | None | Preserve original caches and live modules | Repository state verified, no repeated downloads |
| Phase 1: isolated historical engine | COMPLETE | Offline pinned pure-rule kernel, international event/FX/action adapters and reconciled metrics;16 new unit tests passed | Real input validation remains Phase6 | Run full replay parity | Signals, execution, stops, valuation and audits validated without live imports |
| Phase 2: parity | COMPLETE | SP500_PARITY_REPORT.md:89 research and16 existing paper-trial tests pass; synthetic replay matches six categories | No matching historical five-stock performance oracle exists locally | Preserve honest code/synthetic scope | Code/synthetic parity passes; historical parity not asserted without records |
| Phase 3: exact-time SEC-only universe | COMPLETE |48 exact-time SEC-only universes frozen;128,469 confirmed security-months;36 target month ends plus prelaunch September29 2023; two calendar/status regressions pass | Sector/listing/tradability still unresolved | Inventory and apply global data gates | Prior-public SEC-only membership frozen at every decision |
| Phase 4: historical sectors/listings | BLOCKED | HISTORICAL_DATA_BLOCKERS.md; SEC-only GICS/listings0% over128,469 observations; country/sector/priority matrices saved; licensed manuals require login | Rights-permitted dated GICS and global security-master extract with knowledge timing | Import an authorized historical extract; never substitute current sectors | Existing98% country/sector coverage gates met without imputation |
| Phase 5: historical price/FX assembly | BLOCKED | HISTORICAL_PRICE_INVENTORY.md;539 staged/14 EODHD raw series; max211 prelaunch bars; references/FX missing; three cache-resumption/quota regressions pass | Verified mappings, sufficient existing history entitlement and observable FX | Supply permitted historical exports; resume only missing costed partitions under current confirmed quota | Warm-up, complete used OHLC/TR/actions/calendars/FX |
| Phase 6: readiness | COMPLETE |16 formal checks:7 pass,9 fail;104 research tests pass; fresh six-category synthetic parity passes | Historical input requirements remain external | Import complete evidence bundles and run the cache-only automatic resume entrypoint | Gate evaluated honestly; historical execution remains blocked |
| Phase 7: historical comparison | BLOCKED | No validated complete input bundle | Phase6 passes | Automatically run A/B once ready | Same dates/capital/reference/cost conventions; reproducible audits |
| Phase 8: attribution | BLOCKED | No qualifying historical results | Phase7 | Analyze actual results only | Requested metrics/2023–26 diagnostics supported by trades |
| Phase 9: final outputs | COMPLETE | GLOBAL_BACKTEST_FINAL_REPORT.md, final readiness, input schema and ignored machine-readable blocked checkpoint | Historical performance remains externally blocked | Resume automatically after complete input admission | OUTCOME B documented without manufactured performance |

Last successful phase6 Git commit: `716599e`; phase5 `2efe712`; phase4 `07c03d0`; phase3 `017320c`; phase2 `3347462`; phase1 `74ba9bc`; pre-task `544e5fd` (pushed).
Backtest readiness: **FAIL**; no real historical performance run authorized by a
passing gate yet. No real trades. One new EODHD account HTTP check, zero cost
units; no price/split/symbol/FX requests. Account usage date is stale, so current
remaining allowance is treated as unknown.

Next executable action: supply rights-permitted dated classifications/listings,
S&P historical membership, long-history prices/actions/calendars and observable
FX; refresh parity and run `python -m research.global_backtest_pipeline --resume`.
The runner automatically executes both configurations after input admission.
See `HISTORICAL_INPUT_BUNDLE_FORMAT.md` for the exact ignored manifest schema.
Independent ECB preparation has an offline parser and three regressions, but
public downloads failed with proxy403. A saved additive environment draft
includes the two ECB domains; publication and rights/timing checks remain open.

Final outcome: **OUTCOME B — EXTERNALLY BLOCKED**. All independently feasible
phases are complete.104 research tests and16 existing in-memory paper tests
pass; six-category synthetic parity passes with current program hashes.
97 original compressed universe files, holdings/snapshot inputs and16 price
inventory sources match their prior SHA256s. Historical performance remains
null. Phase7/8 can resume automatically after the input requirements pass;
see `GLOBAL_BACKTEST_FINAL_REPORT.md` and the input bundle schema.
The phase9 report commit is discoverable with `git log -1`; no report
claims its own commit hash before Git creates it.

## Approved exploratory continuation from8c3116b

The user now permits documented **current GICS** fallback with historical
corrections for the first exploratory comparison. STRICT_PIT retains all
existing historical-verification rules. Membership/listing/price/FX/action
and accounting requirements are not relaxed. Earlier outcome reports describe
the strict checkpoint; subsequent updates supersede their GICS-only blocker.

| Step | Status | Evidence | Dependencies | Next action | Completion criteria |
|---|---|---|---|---|---|
|1: verify checkpoint|COMPLETE|HEAD8c3116b, four requested documents read,104 research tests pass|None|Implement two explicit admission modes|Preserve original datasets and passing strict tests|
|2: classification policy|COMPLETE|Two modes, provenance/corrections, static48-date coverage and decision stress audits;112 research tests pass|Actual sourced GICS overlays remain unavailable|Collect permitted classification evidence|Strict unchanged; exploratory approximations explicit|
|3: US inputs|BLOCKED|US_REFERENCE_INPUTS.md;504 candidates after alias safeguard,448 current issuer-sector matches,3 new regressions pass|Announcement timing, alias reconciliation, complete OHLC/TR/reference exports|Import permitted verified history; continueIBKR investigation|Complete comparison inputs|
|4: IBKR access|BLOCKED|IBKR_ACCESS_READINESS.md;0 tools/bindings/listeners,0 requests;6 admission/quota tests pass|Authorized read-only endpoint/session and existing market-data entitlement|Connect configured interface or import permitted export|Pilot only if access and permission exist|
|5: listing maps|BLOCKED|7792 exact-ISIN current candidate security-months,0% verified historical listing;11 mapping/strict tests pass|Historical alias/MIC/currency/units/issuer intervals|Import dated security master|Preserve primary/ADR distinctions|
|6: global prices/FX|BLOCKED|539 staged/14 raw series;0 warm-up/reference/FX coverage;10 FX/quota/calendar tests pass;0 EODHD calls|Existing sufficient entitled export/interface and observable FX|Import only permitted missing partitions|Validated complete data|
|7: actions/inactive securities|BLOCKED|51 series with splits/429 with incomplete dividend records;source-driven receivable/payment adapter and45 focused tests pass|Complete ex/pay/action/merger/delisting evidence and required adapters|Import verified events; unsupported material actions fail admission|No survivor filtering/accounting gaps|
|8: readiness|COMPLETE|128 research+16 paper tests;synthetic parity6/6;STRICT7/16 andEXPLORATORY7/17 checks pass|Historical data requirements remain external|Import complete rights-permitted bundles|No hidden data failures|
|9: paired execution|BLOCKED|Explicitresume attempts in both modes returnEXTERNALLY_BLOCKED;performance=null|Exploratory10 failed requirements and complete evidence bundles|Automatically replay paired configurations after admission|Both configurations complete|
|10: comparison report|COMPLETE|Updated final report,dual-mode readiness andignored checkpoint;128+16 tests pass|Execution remains externally blocked|Import evidence andrun explicit exploratory resume|Explicit approximations and resumable checkpoint|

Continuation validation:128 research tests and16 isolated paper-trial tests
pass. Strict has9 failures; exploratory has10 (current-sector coverage and
measured classification sensitivity replace mandatory historical GICS).
Neither publishes historical performance. Source-driven dividend accounting
is now supported; material mergers/delistings without adapters fail. All
original cache hashes and production strategy files are preserved.
Latest completed action/accounting milestone:e668d7b. Readiness milestone
commit is available in Git history; next independent task is final reporting
and a resumable externally blocked checkpoint.

Step9 execution decision: no historical backtest run. Both explicit-mode
resume commands completed and correctly failed closed; they are readiness
checks,not successful investment simulations. The exact continuation is
`python -m research.parity_harness`, then
`python -m research.global_backtest_pipeline --mode EXPLORATORY_CURRENT_GICS --resume`
after importing the required ignored input manifest and evidence bundles.
Last successful readiness commit:373b365. No further data-dependent task can
execute from the currently accessible inputs; final reporting continues.

Final continuation outcome:OUTCOME B — EXTERNALLY BLOCKED. Steps1,2,8,10
are complete;steps3–7 have completed source/adapter investigations but remain
blocked on actual historical inputs/access. Step9 is blocked by failed gates.
128 research+16 paper tests andsix-category synthetic parity pass. No new
EODHD requests,trades,purchases,raw-data commits or production strategy edits.
Last successful execution checkpoint:65e4305. Once complete rights-permitted
inputs pass,explicit exploratory resume proceeds automatically to paired
execution andcomparison. Saved additive network/start instructions require
publication;IBKR access/entitlement remains independently unavailable.

## October 10, 2026 — audit-only checkpoint

The security-level inventory in `SPGM_DATA_COMPLETENESS_AUDIT.md` supersedes the
previous aggregate cache inventory for data-availability counts. Across the
October 2023–September 2026 monthly SEC-only universes: 4,236 distinct security
lines, 98,838 observations, zero BACKTEST_READY, 316 PARTIALLY_READY,
2,784 IDENTITY_UNRESOLVED and 1,136 NO_USABLE_PRICE_DATA. All 48 confirmed frozen
universe files were checksum-checked. The full 68,647,315-byte inventory is
ignored at `research/eodhd_output/spgm_proxy/historical_backtest/data_completeness/SPGM_DATA_COMPLETENESS_INVENTORY.csv`.

Correction: all eleven sector ETF tapes are present in the legacy cache's
`sector_etfs` section; they were missed by the earlier `market`-only scan.
They have 211 prelaunch bars and fail the required 253-bar warm-up. SPY remains
absent. Current-sector candidates, adjusted-close fields and partial action
lists are quantified without promoting them to complete or historically
verified inputs. USD identity conversions are distinguished from verified FX
tapes; no foreign FX tape is available. Original strategy and both admission
modes remain unchanged. No historical backtest or acquisition was performed.

Validation: 138 research tests passed, including ten new audit regression tests.
Inventory row/status/flag invariants and original holdings/snapshot checksums
passed. Stop at this checkpoint for the user's next decision.

## October 10, 2026 — targeted recovery and subscription-decision checkpoint

Starting from 7fd757d, the original 316 PARTIALLY_READY securities remain fixed:
zero fully ready and 316 still partial. Permitted public demos supplied complete
2021–September 2026 observed price-date spans for Apple, Amazon and Tesla, with
1,442 bars each. These are partial repairs, not admitted historical bundles.
290 exact-identifier/CIK current-GICS backfills pass the existing exploratory
classification resolver and remain rejected by STRICT_PIT; 26 remain unresolved.
No classification is newly historically verified.

Sampled catalogues report 313 priority identifier candidates and 2,072 across
the 4,236-line historical union. Three additional targeted identifier queries
return only non-US alternatives for Carnival, DuPont and Exxon: combined
identifier candidates are 316 and 2,075, without proving historical primary
listings, price depth, share representation or readiness.

SPY now has a partial 244-bar free-plan tape; all eleven sector ETFs still have
211 prelaunch bars against 253 required. Neither reference input set is ready.
The configured-account experiment used six API units over ten requests; the
final verified free-plan account has 14 daily units and 500 extra credits
remaining. Nine documented public-demo requests consumed zero account units.
No IBKR, subscriptions, real trades or portfolio backtest were accessed.

Official documentation confirms $19.99 Historian / EOD Historical All-World
provides long-history prices, FX and split/dividend APIs, while general GICS
fundamentals and exchange-calendar APIs require other products or free legal
sources. Additional fully ready securities after purchase remain unknown.
Listing/clock/adjustment/action/lifecycle/FX/calendar evidence and full-universe
breadth remain blockers; 316 is below the unchanged 450-valid-signal safeguard.

Reports: SPGM_316_RECOVERY_REPORT.md, SPGM_316_RECOVERY_INVENTORY.csv,
EODHD_SUBSCRIPTION_DECISION.md and SPGM_DATA_ACQUISITION_ROADMAP.md. All raw
responses, source documents and detailed evidence remain in ignored
research/eodhd_output/spgm_proxy/historical_backtest/recovery_316.
Validation: 150 research regression tests passed, including twelve recovery
tests; original source hashes and fixed-cohort invariants checked. Production
strategy and both admission modes are unchanged. Stop for the user's review;
do not publish an executable bundle or run the historical backtest.
