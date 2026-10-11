# Pre-trade QA and release gates

**Current gate: prototype purchases permanently disabled. User release: absent.** No success reported by this document, an agent, unit test, branch push or dry-run grants permission to buy. The explicit user instruction requires signoff after QA evidence is reviewed. That signoff is a final future release step, not requested before the preparatory work is complete.

## Every proposed cycle: all checks must pass

No majority vote, warning-only bypass, waiver inferred from elapsed time or automatic approval. `UNKNOWN`, missing evidence, reviewer disagreement and stale certificates mean HOLD. Preserve the hypothetical canonical signal even if execution is held.

| ID | Independent check and exact required evidence | Failure action |
| --- | --- | --- |
| Q01 | Full base SHA and all frozen hashes match; original configuration only; execution build/runtime digest matches approved parity-tested release | Quarantine rule drift |
| Q02 | Dedicated paper-only account, cash budget, environment and restricted storage/credentials; zero route to production/live broker; kill switch clear | Deny capability |
| Q03 | Verified exchange session and close/open times including DST/holidays/early closes; new completed month-end signal; no inherited basket; execution window valid | Hold/missed cycle; no catch-up |
| Q04 | Every effective member has stable security/issuer/share-class IDs and primary effective-date lineage; adds/removals/renames/delisted histories covered | Whole-cycle hold |
| Q05 | Complete price history at exact security/session; at least 126 prior observations; positive finite OHLCV; verified units/adjustments/volume; raw/nominal price gate and vendor-close ADV recomputed | Hold unknown prices/actions |
| Q06 | No bar after cutoff enters selection; price observation before decision; forward labels denied by field whitelist; vendor corrections append versions | Quarantine temporal leakage |
| Q07 | Six required financial input uses, or exact documented shared dependencies, tied to original eligible 10-Q(/A) accession, CIK, USD/unit scale, context, 60–125-day quarter or proved frozen derivation | Hold missing/ambiguous facts |
| Q08 | Official filing date no later than signal date−1; exact publication/acceptance proof with timezone source; available by prior-day financial cutoff; forward first-observed by decision cutoff; no signal-day facts/later amendments | Hold timing ambiguity |
| Q09 | Recompute latest-period ordering, comparator (310–420 days nearest 365), 210-day revenue/income freshness, revenue-aligned operating periods; no pretax substitution | Hold semantic conflict |
| Q10 | Strict >20% revenue, >0 income, comparator/income improvement rule and >3pp margin; positive revenue denominators and r63; every member pass/fail/unknown explained | Whole-cycle hold if ranking incomplete |
| Q11 | Independent r63-only stable rank and targets equal sealed signal; at most five slots ×20%; missing slots cash; original tie order; no sector/regime/stops/retention additions | Quarantine formula mismatch |
| Q12 | Plan binds signal/account/pre-state; next-open quantities only after open observed; 20 bps each side; whole-share floors; sells before buys; affordability; no leverage/oversell/double use of cash | Hold plan |
| Q13 | Splits/spinoffs/dividends/membership exits fully reconciled; canonical ex-date model distinguished from economic receivable/cash; halted/delisted execution explicitly held | Hold action/liquidity uncertainty |
| Q14 | Independent cash, shares, basis, realized/unrealized P&L, distributions and NAV tie out; shares exact; cash/basis/NAV residual ≤$0.01 under declared rounding; marks exact-date and no unresolved orders | Hold and reconcile |
| Q15 | Full ledger chain and trusted external checkpoint verified; immutable retention healthy; no rollback, broken outbox, duplicate/conflicting key or concurrent owner | Quarantine integrity incident |
| Q16 | QA identity differs from authors; certificate authenticated, complete and unexpired; binds inputs, universe, rule/code, signal, plan, pre-state, session/account/environment; changed hash revokes it | Deny capability |
| Q17 | Explicit user release exists for reviewed evidence/release hash, exact paper account/environment/budget and effective/expiry period, no revoked generation; no real-money scope | Deny capability |
| Q18 | All monitoring heartbeats and critical controls healthy; no active incident, stale lease, unresolved dead letter or revocation; nonce/order key unused | Hold; alert owner |

If any execution-stage material changes after QA (prices, quantity, cash, corporate action, status), reseal the plan, reconcile and re-QA. Do not approve a quantity range broader than the reviewed deterministic sizing rule.

## Staged release gates and evidence

| Gate | Acceptance / dossier | Allowed action |
| --- | --- | --- |
| G0 Freeze + isolation | GitHub base verified, frozen digests recorded, no original files changed, no live imports/credentials/routes, independent review, negative authorization tests | Offline fixture checks only |
| G1 Data + rule parity | Primary prospective universe/time/action proofs; independent adapter reproduces archived decision gates/ranks and whole-share orders on all 21 available month-ends with identical pinned inputs; source-corrected historical inputs get a separately labeled impact replay; synthetic boundaries, missing cases, DST/early closes and derived facts; no unexplained discrepancy | Manual shadow data collection and sealed signals |
| G2 Shadow operations | Minimum 20 completed sessions AND at least one genuine new month-end; daily evidence/health/ledger/reconciliation reports; zero execution events; drills for gaps/rate limits/restarts/corrections/lease conflict; no open critical or high control issue | Continue shadow; produce QA dossier |
| G3 Dry-run readiness | At least two complete cycle rehearsals (one genuine month-end plus one clearly labeled historical/synthetic cycle), independently observed next-open previews, cash/cost reconciliation, crash/retry/checkpoint/restore tests, dedicated deployment isolation verified | Manual dry-run previews; no account mutation |
| G4 User review/signoff | Signed release dossier, independent QA verdict PASS, all Q01–Q18 evidence, explained accounting limits, account/start/budget/execution policy, exact code/evidence hashes, expiry and kill-switch instructions reviewed; explicit user signoff recorded | Consider enabling separate simulator implementation on research/development only |
| G5 Controlled paper pilot | Separate authenticated authorization/simulator, WORM storage, fenced transactional journal, no real routes; manual first-cycle QA and user-approved pilot scope; inspect/reconcile every fill; rollback/revocation drill passed | Only approved dedicated simulated orders |
| G6 Continued trial | Per-cycle QA remains mandatory; daily reconciliation, signed reports, monthly operational review; no unapproved rule or code/data changes | Same approved scope until expiry/revocation |

G0 prototype evidence can pass while G1–G5 are unimplemented. A safe disabled scaffold is not near-production readiness. Time goals are minimum operational observations, not statistical proof of strategy profitability. At 3/6/12 months report implementation incidents, turnover, drawdown, exposure and benchmark-relative results; a year gives one forward annual outcome, not proof of repeatability. Pre-register these observations and retain unfavorable periods.

## Dossier required for user review

Manifest and full code diff; independently reproducible signal/plan; all raw source and publication lineage; complete universe disposition; parity/boundary/fault/restore test reports; QA checks and separate identity evidence; daily shadow reports and dry-run reconciliations; open risks and incident drill results; dedicated account/permissions diagram; immutable-retention/checkpoint evidence; monitored health and release revocation procedure. Record this dossier's hash and the exact user approval reference. No approval artifact is populated in this PR.
