# Point-in-time validation — 11 October 2026

**Decision: Insufficient data. Strategy validation is BLOCKED.** This is a completed archive/data-readiness audit, not the requested completed 2022–2025 backtest. No new strategy simulations were run. Approximately 80% sustainable annual growth and repeatable 5× growth are not established.

Read `validation_report.html`, `data_quality_audit.md`, `strategy_recovery.md`, `failure_attribution.md`, and `adaptive_strategy_review.md`. `config.json` records all six requested strategies without replacing missing rules. `validation_status.json` lists 13 blocking gates.

## Reproduce this milestone

Python 3.12; standard library only; no network or credentials required:

```sh
python research_5x/point_in_time_validation/validate_archive.py --strict
python research_5x/point_in_time_validation/test_validation.py
python research_5x/point_in_time_validation/build_report.py
```

The first command intentionally exits **2** after generating artifacts because strategy validation is blocked. Exit 0 without `--strict` means artifact generation completed; it never means the strategy passed. The gate program is an evidence auditor, not an executable six-strategy simulator. The archived trading engines are preserved as evidence and are not imported or run.

## Output semantics

- `annual_comparison.csv`: 30 requested account records (six strategies × four independent calendar years plus one continuous account). Every performance field is blank and status is `NOT_RUN_BLOCKED`. Blank is unavailable, not zero.
- `monthly_leadership.csv`: 288 strategy/month status records for all 48 requested months. Rankings, data-availability timestamps, allocations and decisions are blank because certified signals were not computed.
- `drawdown_analysis.csv`: 30 blocked account records. No invented peak, trough or recovery dates.
- `stock_selection_audit.csv`, `trades.csv`, `daily_portfolio_nav.csv`, `holdings.csv`: schema-only files with no simulated observations. They are not complete portfolio histories. Cash balances cannot be reconstructed for accounts that were never run.
- `archived_annual_diagnostics.csv`: inherited annual slices of continuous 2024–October 2026 accounts, explicitly separated from the requested results. These are not independently reset calendar-year simulations; 2026 is incomplete.
- `archived_retention_recheck.csv`: new aggregation of 264 archived, overlapping annual holding accounts, with all six holding policies at two cost levels. They are retrospective and uncertified.
- `archived_winner_recheck.json`, `archived_winner_nav.csv`: new cash/share/NAV arithmetic checks of one archived June 2025–June 2026 account. Quoted prices and trade quantities are inherited inputs; no independent selection, price authenticity or publication-time validation is claimed.
- `archived_experiment_registry.json`: 48 prior continuous scenarios, each marked as inherited and not newly executed.
- `source_manifest.json`: exact Git commit/blob provenance, SHA-256 and bytes for 27 read source snapshots. All match Git blob hashes. This does not reverify the full original 1,144-file ZIP, which is not mounted here.

Earlier research is inherited unchanged from the phase-2 branch. This directory alone is added on a dedicated branch. There are no changes to application code, deployed paper trading, brokers, workflows or deployment configuration.

## Unblocking the requested research

Recover the exact original A source/configuration and trade/NAV/input archive. Acquire and audit broad pre-2022 and 2022–2025 historical membership/security identifiers, raw prices and full corporate-action proceeds, payable-date dividends, accession/release-vintage fundamentals with actual availability timestamps, and historical industry classifications. Omit analyst-expectation rules unless historical consensus vintages become available. Develop D/E on separate chronological training data, resolve C's retention variant, freeze all execution/rules, then run the 30 requested accounts and controlled stresses. The already examined 2022–2025 interval remains retrospective even after these repairs; an untouched prospective period is still required.
