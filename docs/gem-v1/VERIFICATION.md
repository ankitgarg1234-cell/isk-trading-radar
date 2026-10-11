# Verification findings — 2026-10-11

## Source branch and isolation

GitHub branch listing and recursive tree verified `research/gem-2025-2026-validation-2026-10-11` at full SHA `d59b93d3d9a87d582045b4ae71ff9a6f696a48be`. Local isolated clone was checked out from that exact commit. Recorded `main` at `e33024472a35c060e4e36cf3246bcfe5153418d1`.

The frozen engine/spec/config hashes pass the read-only verifier. The original audit states `pit_certified=false`, `all_signals_certified=false`; accounting reproduction is not full point-in-time certification. Selected 1,638 qualifying input uses previously passed the narrower same-accession/value/time audit, but missing competitors, primary universe lineage and action/payable economics remain unresolved.

Only new `gem_paper/`, `tests/gem_paper/`, `docs/gem-v1/` and one offline-test workflow belong to A. B adds only its own research folder, tests and offline-test workflow. No existing file is edited. Existing `app/`, deployment files, workflows, source engines and original research artifacts stay identical to the pinned snapshot. No deployed endpoint or account database was accessed; live position balances were not independently inspected. The assurance is the additive code/branch scope and absence of any operational mutation, not a claimed live-account reconciliation.

## A evidence

Local Python 3.14.4:

```text
python3 -m unittest discover -s tests/gem_paper -v
23 tests passed
```

22 synthetic control tests plus one SHA-pinned observed-feature regression. The latter matches original archived top-five signals on all 21 unique 2025–2026 dates (with overlapping independent/continuous account signal consistency), from already-derived passing features. It assumes upstream price eligibility and uses fixture identities. It does not validate raw SEC quarter derivation/freshness, complete historical universe or price/action history, nor full order-path parity.

Tested controls: digest drift; strict thresholds/stable ties; unknown-competing-member hold; prior New York day SEC cutoff and amendments; future/naive/malformed temporal evidence; expired/incomplete/unbound QA; forged release still denied; fixed costs/whole shares/sell financing; preview timing/reconciliation; identical/conflicting/concurrent retries; ambiguous durable-write acknowledgement; symlink/tamper/partial-tail/anchored-truncation rejection. Review corrections for amendments, local-date cutoff and publication chronology were made before final evidence.

`authorize_purchase()` returns false unconditionally; there is no simulator submission/apply-fill API, configuration unlock, scheduler or broker adapter. Pure preview calculations and temporary fixture audit events are not purchases. QA envelope validation does not authenticate its input claims. Local audit is tamper-evident with a separately trusted checkpoint, not WORM. Those limits are explicit in code/README and release gates.

## B evidence and interpretation

The exact 943 case IDs span 111 tickers and 21 dates. Initial contemporaneous priority counts:137 above the observed selected cutoff,147 unknown momentum,3 able to fill archived cash slots,656 below cutoff under fixed archived prices/selected candidates. April 30, 2025 had only 3 selected names. All cases remain evidence-required until complete primary proof and independent review.

B independently rechecks cached value/accession/period/time proof rather than copying prior status labels, preserves missing inputs and source hashes, and reports conditional slot changes with a 0 lower bound. Conditional scenario upper sums are 29 target slots across dates for observed momentum and 92 when unknowns may outrank observations. These sums are not unique stocks, probabilities, actual displacements or return bounds. Return impact is unavailable until corrected eligibility and price/action/path evidence is complete.

B independently passed 27 offline tests (50 total with A). Queue and primary-report reproduction, raw-source hashes, CIKs, periods, consolidated contexts, units and AWK values were independently checked. Three original SEC headers plus AWK's original XBRL instance were acquired with successful and failed acquisition metadata retained. LLY/AWK acceptance timestamps differ conditionally under a declared New York timezone interpretation; literal EST sensitivity and unproved first-public-availability are explicit. AWK's regulated-revenue concept explains two distinct period discrepancies across four cached uses; complete filing selection and semantic certification remain outstanding. The [B report](https://github.com/ankitgarg1234-cell/isk-trading-radar/blob/research/gem-competitor-certification-2026-10-11/research_5x/gem_competitor_certification/REPORT.md) and [independent QA review](https://github.com/ankitgarg1234-cell/isk-trading-radar/blob/research/gem-competitor-certification-2026-10-11/research_5x/gem_competitor_certification/QA_REVIEW.md) retain those limits. No new case is described as strictly certified without retained original documents, publication/context/units, full eligible filing set, historical identity/universe/price proof and independent reviewers. The backlog remains 943 for strict certification.

## Release verdict

**Ready for review as a disabled offline development scaffold; not ready for paper purchases.** G1 raw data/parity, authenticated independent QA, immutable storage/transactional simulator, genuine shadow/dry-run operational evidence and explicit user signoff remain outstanding. No historical return is newly certified. No user release artifact is populated and no automatic paper purchase begins.

CI workflows run only offline tests with read-only GitHub permissions, no secrets and no deployment/trading commands; existing scheduled/workflow files are unchanged. CI results must be verified separately after publication. Both draft PRs target the research base, not main; no merge or deployment is performed.

## Published review artifacts

- [Forward draft PR #63](https://github.com/ankitgarg1234-cell/isk-trading-radar/pull/63), dedicated `research/gem-forward-safety-2026-10-11`.
- [Historical draft PR #64](https://github.com/ankitgarg1234-cell/isk-trading-radar/pull/64), dedicated `research/gem-competitor-certification-2026-10-11`.
- Both bases are `research/gem-2025-2026-validation-2026-10-11`, verified at full `d59b93d3d9a87d582045b4ae71ff9a6f696a48be`; neither targets main.
- Initial forward GitHub CI passed on Python 3.12 and 3.14: [PR run](https://github.com/ankitgarg1234-cell/isk-trading-radar/actions/runs/38170188867). Historical final-head CI also passed on both Python versions: [PR run](https://github.com/ankitgarg1234-cell/isk-trading-radar/actions/runs/38170526993). Forward final-head CI is recorded in the PR checks after the final documentation commit.
- [Milestone roadmap and six created issues](ROADMAP.md) track all remaining release and certification work.

Raw SEC bytes are preserved exactly, including original whitespace. Git blob hashes were compared byte-for-byte during historical publication. Generated CSV retains deterministic CSV line endings. Whitespace checks exclude raw acquired documents and recognize CSV carriage-return line endings; source/code/document whitespace checks pass.
