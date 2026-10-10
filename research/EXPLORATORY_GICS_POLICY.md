# Sector admission: strict and approved exploratory modes

The user explicitly approved current-GICS fallback for the first exploratory
October2023–September2026 comparison. Strategy formulas and the original
eleven sector ETFs remain unchanged. Only sector metadata admission changes.

`STRICT_PIT` is the default and retains historical GICS effective/publication
verification. `EXPLORATORY_CURRENT_GICS` prefers verified historical labels;
otherwise it requires an exact `instrument_key`-matched `current_gics` source.
No name/business/SIC/NAICS inference or unreferenced staged label is admitted.
Both modes preserve historical membership, listing/currency/MIC verification,
price/FX/action/calendar coverage and portfolio-accounting requirements.

Each current record must contain `instrument_key`, `sector_scheme: GICS`, one
of the original eleven sector labels, `source_url`, `evidence_file`, `sha256`,
`retrieved_at`, `classification_asof`, and `taxonomy_version`. Source evidence
files are checksummed in executable bundles and the offline overlay auditor.
Use source metadata that explicitly identifies GICS; do not relabel a vendor's
proprietary taxonomy as GICS. Rights-permitted evidence is still required.

Optional `historical_gics_corrections` use the same evidence fields plus
`effective_from`, optional exclusive `effective_to`, `available_at` and
`verification`. Effective-date corrections take precedence over current labels.
Overlapping corrections fail. A correction is historically verified only when
its evidence establishes a prior-public available time; later-known historical
facts remain `RETROSPECTIVE_CORRECTION` approximations. Current fallback always
remains `CURRENT_GICS_BACKFILL`, never historically verified. The original row
is preserved and resolved copies retain both sources and approximation status.

Coverage requires≥98% each cutoff and≥95% in each material country (≥1% of
securities). Every admitted usable member has a resolved sector; no Unknown
risk bucket is executed. All unresolved securities retain their denominator
and reason. Report historical/current/retrospective counts separately.

Before executable admission the static classification audit records source/
country/sector coverage and uncertain counts. Before each monthly order is
queued, exact original selection and sector-cap functions quantify decision
sensitivity: baseline versus eleven joint stresses assigning all approximate
rows to each sector, plus any source-documented individual alternatives. Report
selected names, weights, caps, regimes and maximum absolute weight changes.
These are uncertainty stresses, not probabilities or exhaustive historical
assignments. Large sensitivity is disclosed; no unsupported truth is invented
to make it zero. Performance/rank sensitivity is unavailable without prices.

The current cache has128,469 SEC-only security-months and no eligible sourced
current overlays: both modes have0% admitted sector coverage. The503 staged
labels are undated and lack complete source/identity/GICS provenance. This
policy change removes mandatory historical GICS in exploratory mode; it does
not manufacture replacement labels or unblock missing prices.

Commands (offline):

```bash
python -m research.classification_audit
python -m research.classification_audit --records research/eodhd_output/spgm_proxy/historical_backtest/classification_records.json
python -m research.parity_harness
python -m research.global_backtest_pipeline --mode STRICT_PIT --resume
python -m research.global_backtest_pipeline --mode EXPLORATORY_CURRENT_GICS --resume
```

Both configurations must explicitly declare matching `admission_mode`. Mode
outputs stay separate under ignored `historical_backtest/admission/<mode>/`
and `results/<mode>/`. Metrics include classification coverage/sensitivity;
exploratory outputs must be labeled as a current-GICS approximation. Never
claim a current-classified replay is a fully point-in-time sector backtest.
