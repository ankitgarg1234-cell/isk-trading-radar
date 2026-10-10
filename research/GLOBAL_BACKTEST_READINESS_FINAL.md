# Global backtest final readiness

**EXTERNALLY_BLOCKED**. Period October1 2023–September30 2026; $10,000.

**SPGM HISTORICAL ETF HOLDINGS PROXY**; SEC-only lagged membership; unchanged SPY/11 U.S. sector ETF references.

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

The classifications/listings fail the≥98% monthly minimum,≥95% material-country gates and100% usable-signal/held-position requirements. No source gaps are imputed. Price coverage fails before any ranking can be considered complete. Unknown sectors are not an executable concentration bucket. Missing high-momentum securities cannot be assumed irrelevant.

Synthetic and code-level parity passes, but no original historical five-stock performance oracle exists locally. No real A/B result is published while critical failures remain.

Re-run `python -m research.global_backtest_pipeline --resume` after supplying `historical_backtest/input_bundle_manifest.json` and its rights-supported data/evidence files. The loader recomputes metadata timing, exact selection membership, calendar/FX/price validity, signal coverage and accounting reconciliation; a boolean ready flag cannot bypass those checks. A failed admission/replay leaves the comparison blocked.

Machine-readable readiness, price inventory, input hashes, synthetic audit and account/request ledger stay ignored. No costed data requests are made by this runner.
