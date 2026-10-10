# Global backtest master status

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
| Phase 6: readiness | IN_PROGRESS | Engine and parity pass; membership frozen; sectors/listings/prices/FX fail | Rights-permitted validated inputs | Build formal gates and automatic resume entrypoint | All critical checks pass; otherwise fail closed |
| Phase 7: historical comparison | BLOCKED | No validated complete input bundle | Phase6 passes | Automatically run A/B once ready | Same dates/capital/reference/cost conventions; reproducible audits |
| Phase 8: attribution | BLOCKED | No qualifying historical results | Phase7 | Analyze actual results only | Requested metrics/2023–26 diagnostics supported by trades |
| Phase 9: final outputs | IN_PROGRESS | Master checkpoint created | Findings from all feasible phases | Maintain final readiness and outcome reports | Completed comparison or precise externally blocked outcome |

Last successful phase4 Git commit: `07c03d0`; phase3 `017320c`; phase2 `3347462`; phase1 `74ba9bc`; pre-task `544e5fd` (pushed).
Backtest readiness: **FAIL**; no real historical performance run authorized by a
passing gate yet. No real trades. One new EODHD account HTTP check, zero cost
units; no price/split/symbol/FX requests. Account usage date is stale, so current
remaining allowance is treated as unknown.

Next executable action: formal readiness and resumable historical A/B runner;
complete outcome reports without manufacturing performance figures. Rights-
permitted dated classification/listing and long-history price/FX exports are
the external dependencies for execution.
