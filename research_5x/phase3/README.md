# Phase 3 — accounting quality and validation

Open `research_report.html` first. It answers Q1–Q7, preserves the prior portfolio comparisons and explains why new strategy tests stop at Gate1. Source-reviewed positive-cash failures reject sufficiency, not the potential incremental usefulness of cash conversion. No independent strategy conclusion is Validated.

`validation/portable_reproduction.json` records a clean-parent-checkout, offline reproduction: all 37 core outputs matched byte for byte, all 30 regression tests passed and all 105 prior publication files retained their hashes. This validates reproducibility and accounting safeguards, not future investment performance.

Parent commit: `4ea44011e3911227f9be2266d5dcb6c078b8722a`. Research branch: `research/phase3-accounting-quality-validation`. No production/paper/broker/trade/deployment changes.

## Reproduce offline

Use Python3.12 with pandas/numpy/lxml. Matplotlib is required only to rebuild figures/report. Tests use the Python standard-library unittest runner. In a checkout of the research branch, run:

```bash
python3 research_5x/phase3/code/unpack_sources.py
python3 research_5x/phase3/code/build_cohorts.py
python3 research_5x/phase3/code/stage_accounting.py
python3 research_5x/phase3/code/cohort_uncertainty.py
python3 research_5x/phase3/code/build_phase3.py
python3 research_5x/phase3/code/verify_phase3.py
```

`source_bundles/` retains exact raw SEC/issuer snapshots and long inline-XBRL intermediate files in hashed archives. Extraction refuses to overwrite changed files. All source-relative paths are restored before source packet tests run. Current-page downloads are snapshots of dated original documents, not proof of an independent historical web archive. Failed downloads remain in the inventories.

Issuer packet scripts rebuild manually source-reviewed financial schedules; automated arithmetic checks do not independently re-read every webpage. Read each packet README for its extraction and source checks. `retrieve_sec.py` is an optional append-only **new discovery run**, not part of frozen reproduction. It may fetch different current API content; never overwrite raw snapshots or use a later revision at an old entry. The initial CIK map and frozen acceptance comparator are supplied in this directory, so offline accounting staging does not need a production import.

`frozen_inputs/all_qualified.csv` supplies all379 Phase2 observations. Prior source copies are SHA-verified; `retention/prior_phase2/` contains the immutable prior summaries/accounts/full daily NAVs/orders. Source lineage, periods, YTD subtraction operands, missingness and original/revised/Q4 scopes are explicit. Broad API staging remains uncertified for predictors. No quality-return regression or new policy account is created.

The preservation verifier additionally checks all105 parent-publication files in the full repository. If using only this directory, run `test_phase3.py` and the issuer test scripts directly; the parent105-file check requires the parent research files. The existing `validation/phase2_preservation.json` records the completed check, rather than implying unavailable files were freshly rechecked.

## Scientific state

Gate1 is Blocked by incomplete cohort-wide original release/index/scope certification and weak historical industry/size controls. Gate2 is untested; B/C new policies are untested under the mandated stop rule. Independent-period validation is Blocked by the incomplete historical universe/terminal proceeds and reused development sample. A prospective protocol is a document only, not an active paper account or automation.

For local HTML visual QA use `code/qa_phase3.cjs` with Playwright and Chrome. `PLAYWRIGHT_MODULE` and `CHROME_PATH` can override installed runtime paths. Figures are standard Matplotlib artifacts and embedded in the standalone report. Python package versions used: Python3.12.14, pandas2.2.3, numpy2.3.5, Matplotlib3.11.2 and lxml (version in runtime record).
