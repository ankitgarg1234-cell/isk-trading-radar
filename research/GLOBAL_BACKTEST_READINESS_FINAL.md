# Global backtest final readiness: two admission modes

Continuation from8c3116b. **OUTCOME B — EXTERNALLY BLOCKED**. October2023–September2026, $10,000;SEC-only SPGM HISTORICAL ETF HOLDINGS PROXY and originalSPY/11 U.S. sector ETF references.

The user-approved exploratory mode permits sourced current-GICS backfills and retrospective corrections. Historical GICS is optional in that mode; strict verification remains unchanged in STRICT_PIT. Neither mode relaxes historical membership/listings,price/FX,actions/calendars or portfolio accounting.

## STRICT_PIT

| Requirement | Status | Evidence |
|---|---|---|
| engine_validated | PASS | Pinned pure-rule kernel; independent execution/FX/action/metrics regressions |
| strategy_code_synthetic_parity | PASS | 500-stock fixture with program hashes; historical performance parity not claimed |
| membership_frozen | PASS | SEC-only at actual reference-session NY16:20; initial September29 signal |
| membership_no_lookahead | PASS | Original source portfolio/publication dates and hashes retained |
| historical_sectors | FAIL | 0% versus≥98% monthly minimum;100% usable/held/selected required |
| historical_listings | FAIL | 0% verified dated listing/MIC/currency;≥98% monthly minimum |
| price_warmup | FAIL | Both0; staged maximum211 bars versus253 required |
| reference_prices | FAIL | SPY and all11 sector ETFs absent from staged cache |
| historical_fx | FAIL | No verified timestamped FX tape |
| full_universe_actions | FAIL | AZN/Korea/Taiwan cases retained; no complete action/delisting coverage |
| global_calendars | FAIL | XNYS schedule/closure fixtures pass; complete verified venue calendars absent |
| sp500_historical_membership_sectors | FAIL | Staged2024 starting list/undated sectors do not establish2023 starting universe |
| original_strategy_preserved | PASS | No edits to live/paper modules; same SPY/XL* references and pinned formulas |
| transaction_model_documented | PASS | 7bp fills+$1/$0.005 commissions; USD base; native stops; conservative stop FX timing |
| missing_data_quantified | PASS | Monthly/country/security/priority matrices and inventory; no GICS imputations |
| unresolved_security_sensitivity | FAIL | Cannot bound Top5/rank/sector impact without missing price/classification inputs |

Passed7/16; historical performance_comparison is null.

## EXPLORATORY_CURRENT_GICS

| Requirement | Status | Evidence |
|---|---|---|
| engine_validated | PASS | Pinned pure-rule kernel; independent execution/FX/action/metrics regressions |
| strategy_code_synthetic_parity | PASS | 500-stock fixture with program hashes; historical performance parity not claimed |
| membership_frozen | PASS | SEC-only at actual reference-session NY16:20; initial September29 signal |
| membership_no_lookahead | PASS | Original source portfolio/publication dates and hashes retained |
| documented_sector_coverage | FAIL | Historical GICS optional; documented current fallback coverage audit required (no verified joins in current cache) |
| historical_listings | FAIL | 0% verified dated listing/MIC/currency;≥98% monthly minimum |
| price_warmup | FAIL | Both0; staged maximum211 bars versus253 required |
| reference_prices | FAIL | SPY and all11 sector ETFs absent from staged cache |
| historical_fx | FAIL | No verified timestamped FX tape |
| full_universe_actions | FAIL | AZN/Korea/Taiwan cases retained; no complete action/delisting coverage |
| global_calendars | FAIL | XNYS schedule/closure fixtures pass; complete verified venue calendars absent |
| sp500_historical_membership | FAIL | Prior-public September2023 membership/alias reconciliation absent; sectors may use approved documented current fallback |
| original_strategy_preserved | PASS | No edits to live/paper modules; same SPY/XL* references and pinned formulas |
| transaction_model_documented | PASS | 7bp fills+$1/$0.005 commissions; USD base; native stops; conservative stop FX timing |
| missing_data_quantified | PASS | Monthly/country/security/priority matrices and inventory; no GICS imputations |
| unresolved_security_sensitivity | FAIL | Cannot bound Top5/rank/sector impact without missing price/classification inputs |
| classification_sensitivity | FAIL | Static approximation audit and actual decision stresses required; cannot measure ranking sensitivity without prices |

Passed7/17; historical performance_comparison is null.

## Validation and continuation

128 research tests and16 in-memory paper-trial tests pass. Fresh source-matched synthetic parity passes all six categories. Original97 universe exports,holdings/snapshot inputs and16 price source hashes are preserved. No live strategy/source changes or new EODHD requests.

Classification source audits cover128,469 security-months in48 frozen decisions;0 have a fully sourced exact-identity GICS overlay. US public current-sector records provide448/504 issuer-level candidate matches,not verified global assignments. Current listing candidates cover7792 security-months (6.07%),but historical verified listing coverage remains0%. Neither candidate set can conceal missing international or inactive securities.

The pipeline can run automatically after complete bundles pass admission,using --mode EXPLORATORY_CURRENT_GICS --resume. Both bundles must declare the same mode and dividend accounting policy. Static coverage is audited before admission; sector decision stresses are measured before monthly orders. Missing price,identity,FX or material action evidence vetoes execution.

See EXPLORATORY_GICS_POLICY.md,HISTORICAL_INPUT_BUNDLE_FORMAT.md,US_REFERENCE_INPUTS.md,IBKR_ACCESS_READINESS.md,HISTORICAL_LISTING_RESOLUTION.md,GLOBAL_PRICE_FX_CONTINUATION.md andCORPORATE_ACTION_ACCOUNTING_READINESS.md for exact required sources/fields. Machine-readable gates and resumable outputs remain ignored and separated by mode.
