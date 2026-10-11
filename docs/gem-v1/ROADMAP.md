# Parallel milestone roadmap and task backlog

Estimates are engineering capacity assumptions, not deadlines or permission to trade. A and B can progress independently; B cannot unblock A unless its certified evidence is actually relevant to A's cutoff. Use two separate development PRs into the pinned research branch; no merge/deploy is performed here.

| Milestone | Expected effort / dependency | Deliverable and acceptance |
| --- | --- | --- |
| M0 Freeze and safe prototype | This change | Pinned authority, architecture, isolation, offline controls/tests, independent QA; purchases disabled |
| A1 Complete sources and parity | 1–3 weeks after source access | Primary universe identities, exchange calendar, original SEC context/time and price/action data; full independent frozen-rule parity; G1 |
| B1 Triage and accession batches | Initial queue in this change; 1–2 weeks acquisition start | 943 unique cases, cutoff/cash-slot risk bands, grouped source tasks, acquisition attempts/evidence; no tuning |
| A2 Shadow observation | ≥20 completed sessions and ≥1 new month-end after A1 | Zero execution events; complete sealed daily/decision evidence, monitoring and fault drills; G2 |
| B2 Two-review certification | 2–6+ weeks depending on missing archives/custom tags | High-risk cases first, disagreement queue, original facts + accepted availability proof; explicit unresolved remainder |
| A3 Dry-run and recovery | 1–2 weeks; needs A2 evidence | One genuine cycle + second rehearsal, observed-open previews, replay/reconciliation/idempotency/restore; G3 |
| B3 Impact measurement | After locked correction batches and complete price/actions | Unchanged-engine baseline/corrected path, target and NAV/drawdown/cost deltas or conditional bounds; independent review |
| A4 User release review | After all prerequisites | Complete QA dossier for explicit signoff; absent signoff means continue shadow only |
| A5 Controlled paper pilot | Later dedicated implementation after signoff | Paper-only capability/simulator, authenticated approval and WORM audit; manually supervised first cycle; no real money |
| A6 Forward evaluation | 3/6/12 month checkpoints from actual approved start | Pre-registered operational/performance reports, same rule version, matched benchmark; no tuning in trial |

## Issue-ready tasks

GitHub tracking issues were created on 2026-10-11: [primary data/parity #57](https://github.com/ankitgarg1234-cell/isk-trading-radar/issues/57), [immutable audit/authenticated QA #58](https://github.com/ankitgarg1234-cell/isk-trading-radar/issues/58), [shadow/dry-run dossier #59](https://github.com/ankitgarg1234-cell/isk-trading-radar/issues/59), [943-case certification #60](https://github.com/ankitgarg1234-cell/isk-trading-radar/issues/60), [unchanged-rule impact #61](https://github.com/ankitgarg1234-cell/isk-trading-radar/issues/61), and [independent release/isolation #62](https://github.com/ankitgarg1234-cell/isk-trading-radar/issues/62). The milestone schedule above is a documented roadmap; GitHub milestone objects were not created. Role assignments describe responsibilities and do not request review from or message a human collaborator.

| Task | Owner / dependency | Definition of done |
| --- | --- | --- |
| T1 Freeze, isolation and development QA | Release owner + independent QA; M0 | Exact base/hashes, additive files, no deployment/purchase route, test report + reviewed code, original refs recorded |
| T2 Forward primary sources and exact rule adapter | Universe/market/SEC/signal; T1 | Verified all-member lineage, session calendar, as-of raw facts, no signal-day/future inputs, all 21date parity + edge cases |
| T3 Immutable audit and authenticated approvals | Platform/security + QA; T1 | Separate identities, WORM retention, trusted checkpoint restore, release/QA signature verifier, fenced unique journal/outbox, crash/idempotency tests; no enablement before signoff |
| T4 Shadow/dry-run operations and release dossier | Plan/reconciliation/monitoring + QA; T2/T3 | G2/G3 minimum observations, complete reconciliation and incident drills, Q01–Q18 dossier, user review only after evidence ready |
| T5 Historical943 priority and original-accession certification | B1/B2; T1 | Every stable case retained, contemporaneous priority, shared accession acquisition, independent context/unit/time proof, conflicting evidence stays open |
| T6 Locked correction impact and final historical audit | Impact reviewer + independent QA; T5 + complete prices/actions | Untuned original/corrected full-path replay, target/return/DD/cost/turnover deltas, cash-slot uncertainty, matched benchmark, explicit global blockers |
| T7 Controlled paper pilot implementation | Dedicated simulator + independent QA; T4 + explicit user signoff | No real-money path; only reviewed capability can create simulated fill, first cycle supervised and reconciled; revocation/expiry proven |

## Historical case workflow

`OPEN → PRIORITIZED → EVIDENCE_ACQUIRED → PROPOSED_ELIGIBLE/PROPOSED_INELIGIBLE → INDEPENDENT_REVIEW → CERTIFIED` or `UNRESOLVED/DISPUTED`. No irreversible final label until the independent reviewer checks membership, prices/gates and required SEC facts/time. Cases may share accessions while retaining date-specific proof. Evidence corrections append versions; certification revocation invalidates dependent impact outputs.

Priority bands: unknown momentum/price where rank cannot be bounded; known momentum able to outrank/equal the fifth candidate; eligible candidates potentially filling vacant slots; then below-cutoff cases useful for proving complete ranking. Ties require original stable order. Report known-vs-unknown bands separately. Batch shared SEC accessions to minimize request volume, but never prioritize by realized profit or winner names.

Stop acquisition attempts after bounded source retries and leave an actionable missing-source request (original filing/context/time or historical identity/price/action evidence). Research is not finished merely because public APIs cannot recover a name. Progress reports show certified/failed-proof/open/disputed counts and exact top-five uncertainty, not a misleading percent of the entire strategy validated.
