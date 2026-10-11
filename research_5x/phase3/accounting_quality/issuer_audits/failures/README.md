# Experiment A fixed failure evidence packet

Read `ISSUER_AUDITS.md` for the source-backed interpretation. Seven fixed observations across six issuers are selected failure cases. They are not a representative matched sample, an independent evaluation, or a strategy backtest.

The 41 original snapshots comprise 13 dated earnings releases, 14 original quarterly/annual filings, and 14 original filing indices. `source_index.csv` records URLs, original accession/acceptance metadata, local bytes and SHA256 hashes. `download_manifest.json` preserves retrieval attempts. `raw/` contains originals plus convenience text extractions. The deliberately ineligible Deckers Q2 filing is retained for the cutoff diagnostic and must not enter an eligible-factor panel.

`case_metrics.csv` / `.json` hold analyst-reviewed original-quarter metrics, explicit scope guards, and separately joined frozen Phase 2 outcome labels. `metric_lineage.csv` provides individual metric sources, formulas and missingness. `original_inline_xbrl_facts.csv` preserves 11,500 original inline-XBRL facts with dimensions and periods; this is source staging, not an automatically certified factor panel. `annual_Q4_reconciliation.csv` separates direct Q4 income disclosure from full-year statements. `coverage.json` gives exact case coverage. `failure_attribution.csv` distinguishes observable concerns from later losses and explicitly leaves causal attribution unresolved.

Run from any working directory with Python and `lxml`:

```sh
python3 /absolute/path/to/failures/build_failure_audits.py
python3 /absolute/path/to/failures/test_failure_audits.py
```

The offline build does not fetch new financial data. It reconstructs derived ratios and original-filing checks from preserved snapshots and the frozen Phase 2 `qualified_failures.csv`. Re-downloads are separate (`download_sources.py`, `collect_filing_indices.py`) and preserve existing originals. Release clock times remain unverified; the next-session availability convention is conservative, and every selected release predates its signal cutoff by multiple sessions. Original SEC index acceptance times are used instead of current-submissions timestamps.

Final verification: 94 recorded arithmetic/cutoff/hash/annual-fact checks passed, plus seven offline integrity tests. This establishes evidence integrity within this case packet, not the broad Phase 3 scientific gate. Complete recurring-profit definitions, independent matched controls, historical expectations and broad accounting coverage remain unresolved. No later-phase strategy tests or production changes are included.
