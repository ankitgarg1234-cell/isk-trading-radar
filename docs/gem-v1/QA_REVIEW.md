# GEM V1 independent QA review

Review date: 2026-10-11. Scope: new isolated research controls and historical-certification scaffolding based on `d59b93d`; no deployment or order execution. **Initial verdict: PURCHASES BLOCKED; not production ready.** Read-only source review and offline controls are useful evidence, but they cannot establish point-in-time completeness, independent authenticated approval, operational readiness or investment performance.

## Frozen-source review

The three engine hashes match the committed `research_5x/gem_2025_2026_validation/frozen_config.json`:

| Source | SHA-256 |
|---|---|
| `research_5x/code/run_research.py` | `a46271c5436a9fdec93af55705623a270c2888b0124814cf90af873d54ecf7b5` |
| `research_5x/code/continuation_engine.py` | `bb4d9845bbc58493f8f83f7e57c171e874e0d20cbc048cf6fbb42cb6f3f686d1` |
| `scripts/wf3_offline_valuein.py` | `521d6327ba932bde5e548b1b44cc2469afbb69c31e0428f13e2260678468b6d8` |

The frozen original configuration is `growth_margin5`, `n=5`, `score=r63`, `filter=growth_margin`, cost 20 bps per side. Retention variants are outside GEM V1 prospective selection.

The following details must appear in rule mapping, independent recomputation and golden tests:

1. `prepare()` uses fundamental `asof = signal_date - 1 calendar day`. Signal-day filings remain excluded even if known before market close. Publication evidence is an additional safety check, not permission to change that cutoff.
2. `PITFundamentals.quarter()` accepts forms beginning with `10-Q`, including amendments. For each period the winning record rank is `(filing_date, accepted_at string, quality)`. Quality is direct raw duration 60–125 days = 3; derived quarter = 2; Q1 raw fallback = 1. A later derived record may supersede an earlier direct record. “Prefer direct” is not a global priority above publication ordering.
3. Revenue and net-income freshness suppression is strictly `filing age > 210 days`; operating income has no independent freshness suppression. Revenue and net-income latest quarters can differ.
4. Comparator periods are 310–420 days earlier inclusive, closest to 365 days. Ties retain earliest period in the sorted series. Margin uses latest revenue period and its revenue comparator, with operating-income facts at those same periods; it does not use independently latest operating-income periods.
5. Revenue growth is strictly greater than 20%. Current net income must be positive and either comparator nonpositive or growth strictly greater than 20%. Revenue denominators must be positive. Operating-margin improvement is strictly greater than 3 percentage points; r63 must be strictly positive.
6. Price frames drop nonpositive open/close observations before return calculations. r126 must be nonmissing (126 prior observations plus signal observation); raw nominal close must be at least $5; archived trailing 20-observation liquidity is vendor close × volume, at least $10 million. Do not silently replace this with nominal close × volume or 126 calendar days.
7. Ranking is only r63 descending with stable sort. Original feature construction traverses sorted symbols, so equal momentum retains that symbol order. Gates are not score factors and current sectors are not a GEM selection input.
8. Five slots use 20% target each; empty slots stay cash. Whole-share desired quantities include the 20-bps purchase cost denominator. Execution computes equity at the next SPY-calendar session open, sells reductions first, then buys in candidate order with affordability capped by cash. The original has no rank retention, daily 25% cap, stop-loss or regime filter.
9. The inherited preparation routine calculates future labels for separate research. They cannot appear in prospective signal artifacts or be read by GEM decisions. Execution/outcome observations collected after a decision must be isolated from its input evidence.
10. Legacy execution can skip trades on a missing security bar and use a preceding mark for sizing. Prospective safety must block uncertified fill pricing/halts and record the blocked divergence. It must not silently carry stale prices into an approved order.

The base `verification_results.json` explicitly reports `PASS_OFFLINE_INTEGRITY_NOT_PIT_CERTIFICATION`, `pit_certified=false`; `source_audit_summary.json` reports `all_signals_certified=false`. The claimed 943 cases are conservative ranking triage, not 943 already demonstrated displacements. Selected-fact validation cannot certify the full competing universe.

## Required pre-trade certificate

Every row is required PASS with evidence; missing, unknown or contradictory data is BLOCKED. A signed certificate must bind experiment identity, complete rule/source manifest, evidence bundle, signal, exact plan, reconciled starting state, ledger head, check schema and expiry. Independent reviewer identity must be authenticated and distinct from the producer; a user-supplied `qa_approved` Boolean or agent-name string is insufficient.

| Check | Evidence / blocker |
|---|---|
| Isolation | Dedicated research branch and separate sandbox cash, positions, orders and storage; no production imports/configuration/account credentials |
| Exact frozen rules | Full base commit, unchanged source digests, rule-to-source mapping, frozen golden outputs; no retention variant |
| Cutoff / calendar | Timezone-aware completed-session cutoff, exact prior-calendar-day filing rule; holiday/early-close handling |
| Historical universe | Membership effective and announcement timestamps, security/share-class identifiers and alias lineage; no substitution of today's constituents |
| Complete ranking | Every historically eligible candidate resolved, or independently evidenced bound proving it cannot displace the fifth candidate under tie rules; no silent missing-data exclusions |
| Accession facts | Raw source bytes and SHA-256, source location/context, taxonomy/tag, unit, period, original value and derivation; no unrelated-accession numeric matching |
| Publication time | Authoritative accession publication/acceptance evidence, original timezone and normalized UTC; forward first-observed time; ambiguity near cutoff blocks |
| Restatement / quarter derivation | Later amendments effective only from their own availability; retained earlier vintages; fiscal/YTD/53-week/context/sign handling matches frozen semantics |
| Prices / actions | Completed cutoff observations, raw/adjusted series and action-vintage provenance; no future split/dividend adjustment leakage; finite valid bars/volume/ADV |
| Independent recomputation | QA independently reconstructs eligibility, operands, r63, full rank/ties, targets and exact order plan, with predefined numeric tolerances |
| Reconciliation | Ledger replay exactly ties cash, holdings, fills, fees, actions, dividends and pending orders; no uncertain outcomes or unexplained differences |
| Order safety | Whole shares, valid IDs/prices/precision, available reserved cash, correct sell-before-buy ordering, scoped approved simulated spend and expiry |
| Authorization | Current mode enabled only by explicit human signoff after QA evidence review; distinct QA signer; all current digests match; no kill switch or unresolved material incident |
| Durable audit / concurrency | Audit write succeeds before mutation; atomic unique order/idempotency reservation and cash/state commit; current ledger head verified |

No override may waive source timing, frozen-rule integrity, independent QA, reconciliation, audit persistence or explicit human signoff. Any input, plan or state change requires new QA and approval. Signal-day or after-cutoff facts are unavailable even if their fiscal period ended earlier.

## Audit, retry and reconciliation design review

Local hash chaining is tamper-evident. True immutable history requires append-only storage permissions, independently anchored signed heads or WORM/object-lock retention, offsite backups and restore drills. A local owner can rewrite a complete chain or remove its valid suffix; startup verification against an independently trusted head must detect rollback. Documentation must not call a local JSONL chain immutable.

Order intent, cash reservation, authorization-use record, fills and state updates must be transactional with durable unique idempotency keys. Exact duplicate retries return the original receipt; conflicting key reuse blocks. Restart before commit retries safely; restart after commit replays the receipt. Ambiguous outcomes halt and reconcile instead of blindly resubmitting. Corrections append compensating events instead of editing old balances.

Order states and simulated execution policies must explicitly cover proposed/reserved/accepted/partial/filled/cancelled/rejected/expired/uncertain, supported price source, liquidity/fees/slippage, session/halts, corporate actions and cash settlement. A dry-run preview may estimate fills but must not mutate the committed experiment portfolio. These details cannot be inferred from daily-bar backtest reproduction.

## Release gates and monitoring evidence

[QA_AND_RELEASE.md](QA_AND_RELEASE.md) is the single controlling definition of gates G0–G6 and checks Q01–Q18. This review uses its numbering: G0 freeze/isolation, G1 data/rule parity, G2 shadow operations, G3 dry-run readiness, G4 user review/signoff, G5 controlled paper pilot, G6 continued trial. The current change supplies G0 prototype evidence only. G1–G5 remain blocked; G6 cannot be reached by an offline test or code/configuration flag.

Independent acceptance requires the controlling dossier and its declared observation durations: G2 at least 20 completed sessions plus a genuine new month-end; G3 at least two rehearsals with one genuine month-end and one labeled historical/synthetic cycle. One actual monthly forward cycle cannot be multiplied into independent evidence by replaying fixtures. Operational readiness does not demonstrate investment performance.

Monitoring must produce actionable incident evidence: missed run deadline; source freshness/publication ambiguity; unresolved candidates affecting top five; manifest drift; stale QA/approval; ledger-head failure/rollback; unreconciled cash/share difference at supported precision; stale reservation/uncertain order; audit/backup failure; unexpected live-account linkage; any fill while disabled. Failures block the cycle. Daily health checks should distinguish expected market closure from missed work. Performance, turnover, exposure and slippage observations must be reported without tuning GEM V1.

Incident sequence: assert experiment kill switch; preserve evidence/logs; reconcile current state; open timestamped incident; repair through reviewed research branch; rerun affected checks; obtain fresh QA and scope approval before restart. Restore drill must prove complete replay and trusted-head agreement; historical ledger events must not be edited to repair differences.

## Adversarial acceptance tests

- Zero fills and unchanged holdings when QA/signoff is missing, unknown, expired, tampered, stale, wrong-scope, same-author, invalidly signed or associated with different rule/input/plan/state hashes.
- Exact boundaries for signal-day filing exclusion, after-hours publication, date-only/naive timestamps, DST, amendments, latest-frame leakage, accession mismatch, fiscal period/YTD derivation and unavailable comparator.
- Missing higher-momentum competitor, unknown momentum, ties, index effective date, rename/ticker reuse, share classes, delisted names and spin-offs cannot be silently lost.
- Frozen ranking/gate/execution goldens, 20% empty-slot cash, cost-inclusive whole shares, independent operating periods and no future-label signal dependency.
- Duplicate and conflicting idempotency keys; duplicate fills; concurrent reservations/cycles; process interruption before/after durable commit; partial fill/restart; uncertain outcome and cancel race.
- Event mutation, complete-chain rewrite, suffix removal, rollback, missing trusted anchor and audit-write failure; distinguish expected local-chain limitation from implemented durability.
- Quote/bar failure, halt/holiday/early-close, stale marks, action/settlement ambiguity, cash/precision boundary, kill-switch race and backup/restore replay.

## Historical workstream review requirements

Verify exact 943-case inventory against committed triage and stable identity/date keys. Prioritize certified momentum above fifth-rank cutoff, then potentially competitive cases with unknown momentum/universe. Equal-r63 cases depend on frozen stable tie order. A low archived momentum estimate is not certified exclusion without source/adjustment/universe proof.

Each case requires accession-specific source evidence, publication-time proof, original context/period/units/derivation and two independent reviewers. The implemented research workflow passes through `EVIDENCE_REQUIRED`, `EVIDENCE_READY` and `REVIEW_REQUIRED`; proof-complete terminal states distinguish `CERTIFIED_INELIGIBLE`, `CERTIFIED_ELIGIBLE_NONDISPLACING` and `CERTIFIED_ELIGIBLE_DISPLACING`. Unresolved/quarantined cases stay open, and previously certified decisions can be revoked without deleting their history. Report original versus independently certified selected five and impacted signals, then unchanged-rule portfolio/return/drawdown/cost impact with missing-data bounds. Preserve unresolved denominators. Do not prioritize using later realized returns or alter rules to recover retrospective performance. Historical certificates cannot authorize forward purchases.

## Implementation review evidence

Reviewed all `gem_paper` modules, their test suite and README independently. The package uses only standard-library and local-module imports, contains no scheduler/broker/database adapter and exposes no committed fill or portfolio-mutation interface. `authorize_purchase()` is permanently denied even with an apparent PASS envelope and forged release signoff. The preview hashes initial holdings/cash, target order, open prices, timing, costs and resulting hypothetical state. QA envelope checks are explicitly distinguished from authentication and proof of source truth.

Independent execution of `python3 -m unittest discover -s tests/gem_paper -v` passed **23 tests** on 2026-10-11: 22 synthetic control tests plus one pinned observed-feature regression across all 21 archived 2025–2026 signal dates. Synthetic checks cover artifact drift, gate boundaries and ties, unresolved coverage, prior-day filing/publication cutoff and DST, amendments, source chronology, denied/expired/unbound QA, nonmutating whole-share previews/reconciliation, concurrent audit appends, duplicate/conflicting retries, ambiguous durable-write acknowledgment, symlink/tamper/partial-tail rejection and externally checkpointed truncation detection. The regression projects known passing archived rows with assumed upstream price gates and synthetic identifiers; it verifies gate/rank outputs against the archived selected symbols, not the complete raw universe. These tests do not implement or verify a transactional portfolio/executor, raw-quarter reconstruction, full archived parity, trusted source collection, WORM retention or operational release.

| Independent finding | Resolution / remaining scope |
|---|---|
| QA-01: exact `10-Q` validation excluded frozen `10-Q/A` behavior | Corrected to frozen form-prefix semantics; regression test passes |
| QA-02: UTC deadline date could admit signal-day filed dates | Corrected to derived previous New York calendar day, exact DST-aware deadline and local filing date; independent signal-day adversarial case is blocked |
| QA-03: price/SEC observation could be dated after its declared publication | Corrected kind-specific chronology; price closes and SEC periods cannot follow publication; announcement-before-effective membership/action remains allowed |
| QA-04: retained SEC cache match did not prove exact original quarter-start/context lineage | Corrected: exact direct-quarter period-start consistency required, regression test passes; raw context/derived-quarter lineage and complete case proof remain mandatory blockers regardless of cached match |

Within the shipped offline, permanently disabled scope, no unresolved high-severity purchase bypass was identified. This is a limited review conclusion, not a production safety guarantee. Required later evidence includes actual source/universe/publication certification, complete archived rule/order parity, independently authenticated QA, operational shadow/dry-run cycles, durable transactional state and anchored immutable audit, incident/restore drill and explicit user signoff.

The parallel historical implementation independently passed 27 offline tests after exact period/context, numeric-comparison and frozen earnings-rule corrections; queue and primary-source artifacts reproduce deterministically. Its [separate independent review](https://github.com/ankitgarg1234-cell/isk-trading-radar/blob/research/gem-competitor-certification-2026-10-11/research_5x/gem_competitor_certification/QA_REVIEW.md) preserves three original headers, one AWK XBRL instance, conditional timezone discrepancies and two narrow revenue-period reconciliations. All 943 full cases remain open, zero full certifications were issued and return impact remains unknown. These findings cannot unlock prospective purchases.

Official source guidance: [SEC EDGAR API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) describes facts aggregated across filings, frames using last-filed records and possible API processing delays. The conservative point-in-time requirements above are design inferences: preserve accession vintages and original observation times; do not treat a current aggregate response as standalone historical certification.
