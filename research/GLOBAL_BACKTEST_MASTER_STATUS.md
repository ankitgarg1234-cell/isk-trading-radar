# Global backtest master status

Updated 10 October 2026 (Europe/Stockholm). Branch `research/eodhd-acwi-imi-setup`.
Target: 1 October 2023–30 September 2026, $10,000, unchanged five-stock rules.
Global configuration: **SPGM HISTORICAL ETF HOLDINGS PROXY**, SEC-only lagged
portfolios; SPY and the original eleven U.S. sector ETFs remain the references.

| Task | Current status | Evidence | Dependencies | Next action | Completion criteria |
|---|---|---|---|---|---|
| Phase 0: verify prior work | COMPLETE | Branch head544e5fd; all six requested documents and three strategy modules present; 71 research tests passed;21 cached portfolios/48 universes present | None | Preserve original caches and live modules | Repository state verified, no repeated downloads |
| Phase 1: isolated historical engine | IN_PROGRESS | Authoritative five-stock rules located in trial.py; rules.py and old backtest scripts use20 names/Top35/3ATR and are not the requested strategy | Read-only pure-function extraction, event replay | Build offline engine, calendar and accounting fixtures | Signals, execution, stops, valuation and audits validated without live imports |
| Phase 2: parity | NOT_STARTED | Existing tests/test_paper_trial.py found; no matching historical five-stock trade/NAV record yet located | Engine and deterministic reference fixtures | Compare against actual trial functions | Code/synthetic parity passes; historical parity not asserted without records |
| Phase 3: exact-time SEC-only universe | NOT_STARTED |17 SEC and4 workbook snapshots cached; previous48 universes used23:59:59UTC/latest-source policy | Reference calendar and exact decision timestamps | Reconstruct separately, preserve old exports | Prior-public SEC-only membership frozen at every decision |
| Phase 4: historical sectors/listings | BLOCKED | Prior audit: historical GICS0%; verified listings0% over106,463 observations | Rights-permitted dated GICS and global security-master extract | Reassess SEC-only coverage and cached public-source evidence | Existing98% country/sector coverage gates met without imputation |
| Phase 5: historical price/FX assembly | NOT_STARTED | Cached EODHD probes cover roughly one year; other staged data must be inventoried | Verified mappings, history entitlement and observable FX | Inventory all caches before any calls; prepare resumable plan | Warm-up, complete used OHLC/TR/actions/calendars/FX |
| Phase 6: readiness | NOT_STARTED | Prior global readiness failed | Validated engine/parity and input coverage | Apply gates to new universe/inventory | All critical checks pass; otherwise fail closed |
| Phase 7: historical comparison | BLOCKED | No validated complete input bundle | Phase6 passes | Automatically run A/B once ready | Same dates/capital/reference/cost conventions; reproducible audits |
| Phase 8: attribution | BLOCKED | No qualifying historical results | Phase7 | Analyze actual results only | Requested metrics/2023–26 diagnostics supported by trades |
| Phase 9: final outputs | IN_PROGRESS | Master checkpoint created | Findings from all feasible phases | Maintain final readiness and outcome reports | Completed comparison or precise externally blocked outcome |

Last successful pre-task Git commit: `544e5fd` (pushed).
Backtest readiness: **FAIL**; no real historical performance run authorized by a
passing gate yet. No real trades. No new EODHD calls at this checkpoint.

Next executable action: implement the isolated engine and synthetic parity;
then rebuild SEC-only universes and inventory cached price/FX evidence even
while historical GICS entitlements remain unavailable.
