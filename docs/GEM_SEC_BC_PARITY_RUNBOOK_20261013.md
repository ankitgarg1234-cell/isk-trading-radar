# GEM V1 manual-live: original SEC B/C parity runbook (2026-10-13)

**Scope:** offline, read-only verification only. Strategy frozen at `d59b93d3d9a87d582045b4ae71ff9a6f696a48be`; authoritative PIT selector source sha256 `521d6327ba932bde5e548b1b44cc2469afbb69c31e0428f13e2260678468b6d8`. Manual broker execution only. No status upgrades, source approvals, automated orders, paid providers, merges or production deploys here.

## Evidence available versus certified

- GEM-only Neon `gem_forward` has 500 distinct CIK ZIP-member originals for each of **submissions** and **companyfacts** at 2026-10-13 read-only query. This reflects original-receipt *presence* for the current secondary-universe cohort, not certified index membership, accession-specific financial semantics or approved quarterly facts.
- The GEM ranking/QA tables contained 0 forward signals and 0 independent signal reviews at the same checkpoint.
- The current release plan remains fail-closed and requires six independently qualified source categories plus complete-universe monthly ranking review. No owner or reviewer has authorized a manual-live release.

## Automated parity diagnostic (new in PR #103 review branch)

`gem_data/gem_sec_frozen_parity.py` takes two **original SEC ZIP-member receipts**. It hashes/decompresses the original JSON, validates source URI, CIK and accession publication dates, recognizes 10-Q and 10-Q/A, selects direct 60–125-day quarter facts, and reconstructs eligible Q2/Q3 quarter dollars only when both required same-FY cumulative observations can be proven from the original evidence. It replays the exact SHA-pinned original `PITFundamentals` selection and separately recomputes quarter precedence and growth/margin gates.

The output retains original source hashes, amendment and quarterly reporting periods, selected accession IDs, source operands and calculations. Status is **MATCHED_DIAGNOSTIC_NOT_CERTIFIED** or **HOLD**. The former is **not** an independent issuer-source or portfolio QA certificate: the frozen engine accepted upstream `derived_quarterly_value` of unproven historical lineage, and the current original companyfacts archive may not carry every issuer-specific Inline XBRL concept. Keep unproven contextual, revised or nonstandard facts on HOLD.

Run bounded read-only diagnostic batches in an approved operator environment with the existing restricted GEM read-only Neon role (no deployment required):

```bash
# Never print or commit the connection string; set it securely.
python scripts/gem_sec_frozen_parity_cli.py --signal-day 2026-09-30 --limit 10 --offset 0
python scripts/gem_sec_frozen_parity_cli.py --signal-day 2026-09-30 --limit 10 --offset 10
```

Do not run as the source-ingestion/admin database role. The tool enforces the `gem_web_readonly` DSN prefix and a read-only transaction, bounded to 1–25 CIKs. The CLI prints a JSON issuer report and exits nonzero for empty batches/errors; it cannot issue or authorize GEM selections. Batch results are intended as review artifacts; no database modifications occur.

**Review and exception controls:** Assign each missing/ambiguous issuer to one of `MISSING_SOURCE`, `UNKNOWN_CONCEPT`, `COMPETING_CONTEXT`, `AMENDMENT_CONFLICT`, `UNPROVEN_DERIVATION` or `MISMATCH` in a separate external review log. Do not label a missing issuer `FAIL_GATE` unless a valid frozen disqualification is actually proven. Independently verify compressed source SHA, the exact original accession-specific Inline XBRL context, and relevant derived operands before any final issuer PASS.

## Required automated next steps

1. Replay all 500 paired SEC originals, bounded, with deterministic as-of cutoff and immutable SHA of each source plus code version. Report each current quarterly gate as MATCH/HOLD; do not blanket certify a source based on a preliminary scan.
2. Extend factual coverage: EDGAR Inline XBRL accession-specific XML/HTML (including issuer-specific and amended tags), source-operands checks and same-issuer fiscal-calendar variation. The original normalized upstream Valuein derivation cannot be assumed to equal SEC derived YTD differences.
3. Compare only accurately proven source quarters to the frozen engine's numeric thresholds. Recompute full S&P effective-dated universe, adjustment-parity price momentum/liquidity, corporate actions, calendar and SPY independently.
4. Separate verifier and author credentials. Produce signed, attributable reviewer records for all six sources and ranking decision; require code reviewer different from the contributor to approve PR #103.
5. Obtain a true new month-end, shadow/reconciliation evidence and an explicitly approved manual-only release policy. No real-money or paper tickets without source-and-rank certification.

## Separate release conditions

A clean GitHub test suite proves code behavior on fixtures, **not** production issuer coverage or a valid 5-stock ranking. GitHub merge and Render deploy are separate explicit events; PR #103 remains draft and Render AutoDeploy OFF. Trading status DATA HOLD remains until all independent source/ranking checks pass and the owner explicitly authorizes the manual-live release.

## CI sources

- [Review branch PR #103](https://github.com/ankitgarg1234-cell/isk-trading-radar/pull/103)
- [Original frozen engine](https://github.com/ankitgarg1234-cell/isk-trading-radar/blob/d59b93d3d9a87d582045b4ae71ff9a6f696a48be/research_5x/code/run_research.py)
- [SEC verifier issues #73](https://github.com/ankitgarg1234-cell/isk-trading-radar/issues/73)


## Momentum-first SEC verification (approved workflow refinement)

The frozen simulator **first requires strictly positive 63-session momentum** before
the financial G/E/margin gates. Therefore detailed financial-source QA is not
needed for a constituent conclusively failing r63 on **independently reviewed**
calendar-matched frozen-adjusted prices. The complete S&P constituent universe
and all 127 required price sessions still must be accounted for.

**New standalone read-only prioritizer**:
`gem_data/gem_sec_momentum_priority.py` validates compressed Marketstack
observation hashes and computes a provisional 63-observation return at a
requested completed month-end. `vendor_adj_close` is **NOT** presumed identical
to the frozen adjusted vendor-close basis. Current secondary membership is
**NOT** proven effective-dated. Its provisional output has exactly three
non-certifying queues:

- `SEC_REVIEW_FIRST`: provisional r63>0 and intact 64-observation evidence,
  prioritized for deeper SEC original-filing diagnostics;
- `DEFER_SEC_PENDING_PRICE_QA`: provisional r63<=0; **not** a certified
  momentum exclusion, and never ignored when releasing a final ranked universe;
- `PRICE_REPAIR_FIRST`: no receipt, missing/rejected session, hash mismatch,
  invalid adjusted close or inconsistent calendar. This cannot count as a
  negative-momentum gate failure.

`gem_data/gem_monthly_signal.py` and
`gem_data/gem_source_feature_verifier.py` on PR #103 now omit the SEC
six-fact requirement **only** when the full frozen price/identity
screen has passed its existing validation and `r63<=0`. A positive or
unknown momentum stock still requires all as-of SEC quarterly facts.
Full-universe memberships, split-adjustment QA, corporate actions, calendar,
SPY and independent ranking review **continue to block release** when missing.

No code publishes a verified exclusion from a provisional Marketstack return.

### Offline operator command (restricted GEM SELECT-only role)

```bash
# Current secondary-universe September preview: no new provider requests.
python scripts/gem_sec_momentum_priority_cli.py \
  --signal-day 2026-09-30 --all --include-rows > momentum_preview.json

# Run only up to 25 provisionally positive issuers' original SEC diagnostics;
# offset is into POSITIVE candidate queue, not the full S&P universe.
python scripts/gem_sec_momentum_parity_cli.py \
  --signal-day 2026-09-30 --limit 25 --offset 0 > sec_positive_batch0.json
python scripts/gem_sec_momentum_parity_cli.py \
  --signal-day 2026-09-30 --limit 25 --offset 25 > sec_positive_batch1.json
```

The integrated runner performs a current-member price scan and then reads
only the selected SEC submissions/companyfacts ZIP member pairs for positive
provisional CIKs. Missing issuer identities or pairs remain explicit holds,
and dual-class tickers sharing an issuer CIK reuse one original receipt pair.
No SEC HTTP fetching, vendor market requests, DB writes or broker integration.

**Release implications:** even a successful 25-issuer parity batch is
`MATCHED_DIAGNOSTIC_NOT_CERTIFIED`, not a source certificate. First prove
full point-in-time membership and frozen price adjustment parity; then
definitively exclude validated negative-r63 constituents and verify SEC
financials for every still-competitive positive-r63 security. Never treat
unresolved price records as excluded or backdate a real trade to 1 October.
