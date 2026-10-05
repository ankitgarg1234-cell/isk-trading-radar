# Full universe scan

`POST /api/full-scan` starts or resumes the after-hours audit. `GET /api/full-scan` returns progress and every qualified stock. `/scan-audit` displays the same live results and `/api/full-scan/results.csv` exports one row per listed symbol, including pending rows.

The regular scanner checks a rotating 200-stock slice and fully analyzes selected names, with a 48-analysis cycle ceiling. That is discovery coverage, not evidence that all listed stocks fail qualification. This audit has no per-slice candidate quota.

The frozen symbol directory is deduplicated. Every symbol receives the same one-year daily-price input and exact 20-session dollar-liquidity calculation as the scoring engine. Only explicit USD price below $5 / currency failures or liquidity below the shared $10M Core minimum bypass expensive analysis. Both lanes require that minimum. All other stocks receive the current deterministic model, analyst recommendations, fundamentals, news, targets, stops, and canonical qualification/entry checks. The contextual AI layer uses its existing heuristic because AI scores do not determine these gates. Research forecasts remain excluded from qualification.

Current-version analyses collected after the requested session's close may be reused only when the exchange quote is from that session at 15:50 New York or later and critical transient gaps are absent. Reused results are identified explicitly. Fresh analyses require the requested quote session; provider errors or mismatched sessions are reported as unresolved errors rather than economic failures. The audit is current after-hours research, not a reconstruction of what was knowable before the close.

The gates remain deterministic >=70, analyst >=75, exact target/stop R/R >=0.4, Core/Explosive quality, promotion/negative-evidence/confidence checks, USD price >=$5. Qualification and readiness at the saved quote are separate. Neither paper engine is called and no fills are backdated. Normal market-open scanning remains active; normal after-hours refreshes yield provider capacity while the audit runs. Four bounded threads perform initial checks; one thread performs expensive analysis with room reserved in the existing analyst/enrichment request budget.

`full_scan_runs` and `full_scan_results` are additive database tables. Per-symbol checkpoints survive process restarts; startup resumes active work. A lease prevents another worker from claiming an active run, and scoring-version changes halt resumption to avoid mixing models. The existing ledger and trial dates are untouched. Counts are provisional until completion, and completion with errors/missing analyst coverage/transient input gaps is labeled `completed_with_data_gaps`.

CSV exports include the eight deterministic components, scoring version, exact
fundamental-input gaps, source concepts, financial period, confidence and source
ratios expressed as percentages. The audit page shows component averages and
separate counts for incomplete financial inputs and the financial-services model
limitation. Missing exact debt does not rule out conservative liabilities-bound
credit. These diagnostics do not change qualification or scoring bands.

Validation: 400 focused checks passed, four documented preexisting legacy failures deselected. The 17 new full-scan controls cover exact 70/75/0.4 boundaries, matching price/liquidity arithmetic, all 70 synthetic eligible names analyzed beyond the ordinary 48 limit, errors separated from exclusions, no paper ledger writes, resume without duplicates, lease and model-version boundaries, cache provenance, per-gate accounting, endpoint rendering and CSV coverage. Production counts are runtime outputs, not inferred from fixtures.
