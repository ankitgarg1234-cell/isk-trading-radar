# Test plan and acceptance criteria

## Current reproducible checks

The implementation-specific commands and results are in `VERIFICATION.md` and the package READMEs. The safe suite uses standard-library fixtures and pinned artifacts; it must not import the live application, read its environment/configuration, call trading endpoints, reset accounts or execute the old scanner. Tests that calculate hypothetical quantities are distinct from simulated purchase events. Output must explicitly label fixture/offline previews.

Tests must fail on an actual broken control rather than merely echo implementation fields. Independent QA reviews the suite and implementation. Preserve failing cases as regression fixtures after repair. Report local runtime and CI runtime separately.

## Required coverage before release

| Layer | Adversarial scenarios | Acceptance |
| --- | --- | --- |
| Freeze/isolation | Engine/spec/config digest edited; missing pin; wrong base/version; import of app/broker; production endpoint/account/unknown mode; inherited env flag enabled | Block every drift; no deployed file changed; execution unavailable in prototype |
| Universe/identity | Add/remove effective exactly at boundary, rename/SATS-ECHO, same issuer multiple classes, reused ticker, delisted names, absent competitor | Complete disposition and raw primary lineage; any unresolved ranking-changing case holds whole cycle |
| Calendar/prices | Holiday/month-end, early close, DST gap/fold, delayed/missing bars, 126 vs 127 observations, split/reverse split, zero/negative/NaN/inf, stale vendor correction | Exact completed session/units; no guessed timestamps or silently filled gaps |
| SEC timing | Prior day/signal day, acceptance before dissemination, late first observation, missing/naive timestamp, timezone conflict, wrong accession, later restatement | Frozen prior-day filing rule plus independently proved availability; unknown held |
| Facts | Derived YTD arithmetic/context, Q1 fallback, 10-Q/A ordering, later-derived vs earlier-direct, 210-day boundary, 310/420 comparator, equidistant years, independent NI period, operating periods aligned to revenue | Pinned code semantics; all derivation components traced; no 10-K/Q4 or pretax fallback |
| Gates/rank | Exactly 20%/slightlyabove; exactly 3pp/above; current NI 0/prior≤0; r63 0/positive; stable ties; fewer than5; missing higher competitor; injected forward label | Same decisions as frozen engine; missing data holds evidence; forbidden labels cannot enter selection |
| Plan | Next open unknown at signal, sell financing, price gaps, fee rounding, unaffordable share, held member removed, oversell, duplicate target | Contingent vs observed preview distinguished; floor shares; fixed20 bps; sells first; no negative cash/leverage |
| QA/authorization | Fake self-declared PASS, same reviewer/author, stale hash/state/plan, missing check, revoked/expired release, wrong account/environment, tampered certificate, reused nonce | Closed on every failure; prototype denies even apparently valid approvals |
| Journal/ledger | Identical retry, conflicting retry, concurrent writer, partial/truncated append, content/hash/sequence tamper, replay, valid-looking rollback vs trusted checkpoint, fsync failure | No duplicates; fail on corruption; checkpoint detects rollback; no authorization when audit unavailable |
| Simulator future integration | Lost ack before/after committed fill, worker crash at intent/reservation/outbox/fill, partial fill, correction/cancellation, clock skew | Query same key, no new ID retry, atomic postings and independently reconciled recovery |
| Reconciliation | Cash/share/basis/P&L/NAV corruption, costs omitted, dividends double counted, split/spinoff units, provisional stale marks, mixed economic/model cash | Exact shares; declared monetary tolerance≤$0.01; missing data cannot yield certified state |
| Operations | Source timeout/429, missed handoff/window, expired lease, storage full, backup restore, kill switch during execution, credentials/environment drift | Holds remain closed; bounded retries; evidence and alerts preserved; verified restore before resume |
| B certification | Duplicate/lost case, cutoff match/tie, unknown prices, < 5 selected cash-slot risk, same-accession wrong tag/unit/period, after-cutoff fact, disagreement/revocation, future-return field injected | All943 cases retained with stable IDs; no outcomes used in priority; certification requires independent proof |
| Impact replay | Shared accession corrections across dates, corrected eligibility below/above cutoff, cash slot vs displacement, repeated path-dependent rotations, missing action/delisting return | Unchanged rules; original and corrected full histories; conditional bounds labeled; no fabricated NAV delta |

## Acceptance by workstream

A now: additive isolated code/docs only; frozen files unchanged; all offline tests pass; independent review has no unresolved high-severity defect in shipped safety scope; no purchase/execution adapter or scheduler; explicit readiness gaps and user release absent. This accepts a development scaffold, not G1/G4.

A later: all 21 retrospective signal dates reproduce exact rankings/target decisions from pinned engines **when supplied identical pinned inputs**; whole-share/cost accounting parity and independently verified prospective sources complete; shadow/dry-run durations/drills pass; authenticated identity and immutable storage proven; every Q01–Q18 pass; explicit user signoff. Source corrections may change historical targets under the same algorithm and must be reported in B's separate original-versus-corrected data replay; do not force the adapter to reproduce a wrong fact to match an archived target. Any policy safety hold may suppress execution but may not silently alter canonical GEM rankings or V1 accounting. Record source quirks (including possible NaN/missing-bar paths) as uncertified differences and block authorization.

B now: validate943 unique cases and 21dates, deterministic queue sorted by contemporaneous displacement/cash-slot risk, independent cached value/time recheck with honest limits, machine-readable unresolved dependencies and impact-risk report. A triage classification is not completed certification.

B final: every case is independently certified eligible/ineligible or remains explicitly unresolved with quantified uncertainty; all potentially ranking-changing unknowns resolved before claiming top-five certification; underlying historical membership, price/actions and publication-time proofs complete; locked correction set independently replayed through unchanged GEM V1; exact account/benchmark differences and accounting reconciled. Finishing943 case reviews alone does not certify the entire backtest if global universe/action blockers remain.

No return target, including80%, is an acceptance gate. No threshold or execution convention is selected from the later realized results. Performance evaluations use pre-registered dates and preserve all incidents, held cycles and unfavorable outcomes.
