# GEM V1 independent historical competitor certification

This research module continues the exact 943-case backlog from `research/gem-2025-2026-validation-2026-10-11`, commit `d59b93d3d9a87d582045b4ae71ff9a6f696a48be`. It has no trading, production, deployment, broker, scheduler, or strategy-tuning integration. The existing frozen archive is read-only. All generated work remains in this new directory and its dedicated research branch.

## Reproduce the offline review

From the repository root, using Python 3.12+ with zoneinfo available:

```sh
python3 -m research_5x.gem_competitor_certification.certify
python3 -m research_5x.gem_competitor_certification.primary_review
python3 -m unittest discover -s tests/gem_certification -v
```

Both analyses are offline and deterministic. `frozen_inputs.lock.json` hashes nine original input files extracted and byte-compared with the frozen commit. Source drift stops analysis. `certify` does not execute the original strategy or import its preparation routine, which contains unused forward labels.

## Implemented handoffs

| Role | Deliverable | Handoff and restrictions |
| --- | --- | --- |
| Priority coordinator | Exact 943 stable case IDs and dated priority queue | Orders by contemporaneous displacement ability, incumbents outranked, momentum gap, date and ticker; no subsequent returns or winner names |
| Evidence collector | Original accession bytes, URL, response SHA-256, request/completion metadata and transport failures | No eligibility decision; bounded batches, no silent replacement, no current-data backfill |
| Independent cached-data rechecker | 1,714 field-use checks against retained same-accession facts | Rechecks identity, period start/end, form, quarter duration, value, filing cutoff and source-manifest hashes; cached consistency is not certification |
| Financial/identity certifier A | Complete filing selection, semantic concepts, historical issuer and membership proof, reproduced gates | Must reconstruct all contemporaneously available filings and frozen latest-per-period/comparator selection independently |
| Independent certifier B | Independent reproduction and every proof check | Distinct from collector and certifier A; disagreement quarantines the case |
| Impact analyst | Conditional target-slot bounds and, later, frozen replay deltas | Never tunes thresholds, filters, tie-breaks or retention rules; no P&L estimate from missing prices |
| QA/audit reviewer | Evidence decision envelope, source hashes and chain verification | All proof items and both independent certifiers must pass; envelope validator does not authenticate identities or verify primary content itself |

Source acquisition is deliberately separate and opt-in:

```sh
python3 -m research_5x.gem_competitor_certification.acquire_primary --transport system-curl --output research_5x/gem_competitor_certification/new_header_batch
python3 -m research_5x.gem_competitor_certification.acquire_primary --transport system-curl --headers-dir research_5x/gem_competitor_certification/primary_acquisition_system --output research_5x/gem_competitor_certification/new_instance_batch
```

Each invocation permits 1–3 requests, a 15-second request timeout, 2 MB per response and 0.5-second spacing; retries are disabled. Existing request records are reused after URL/accession/digest verification. A new bounded batch directory is required to retry a failed attempt. TLS verification remains enabled. Larger NEM/LLY instance documents are deferred to a reviewed bounded acquisition task; size failures are retained. HTTP 200 still requires document identity/type parsing before using its contents. The historical request records generated before the provenance correction contain `retrieved_at_utc` stamped at request start; primary review explicitly preserves that limitation. New records distinguish request, completed-response retrieval, and completion times.

## Case data contract and review gates

`cases.jsonl` is the canonical initial case envelope. Each record has schema version, frozen commit, stable case ID (commit/date/ticker hash), signal date, ticker, separately audited CIK, state, observed momentum/cutoff, original archived gate values, missing-input requirements and mandatory blockers. `priority_queue.csv` is its review index. `fact_rechecks.jsonl` preserves earlier status labels and independently computed errors without overwriting the archive. Original SEC responses are content-addressed; acquisition records preserve exact URLs and hashes.

The review state machine is `NEW -> EVIDENCE_REQUIRED -> EVIDENCE_READY -> REVIEW_REQUIRED -> CERTIFIED_*`. Missing evidence returns to `EVIDENCE_REQUIRED`; disagreement or corruption enters `QUARANTINED`. Unresolved cases can reopen. A certified case can be revoked to `QUARANTINED` or `EVIDENCE_REQUIRED` by appending a reviewed event referencing the prior decision, cause and evidence; the prior decision must remain in the audit history. Direct transitions between contradictory terminal decisions are prohibited.

Before any terminal certification, both independent certifiers must pass every item in `workflow.CHECKS`:

1. Frozen strategy/source hashes and exact inputs, with no future observations.
2. Historical issuer/share-class/ticker identity and effective membership on the signal date.
3. Complete original filing set, original accession, quarter duration/context and monetary units.
4. SEC acceptance time, official filing-date cutoff, timezone policy and publication availability; acceptance is not identical to first public observation.
5. Latest-per-period ordering, direct/derived-quarter dependencies, 210-day revenue/earnings freshness and nearest 310–420-day comparator.
6. Revenue, current/comparator net income and operating income semantics, including positive revenue denominators; pretax income cannot stand in for operating income.
7. All frozen price-history, nominal-price, 20-session dollar-volume and positive-r63 gates; original split/action and missing/removed-name lineage.
8. Stable sorted-ticker ranking and case effect versus selected candidates and available cash slots.
9. Independent reproduction and consistent eligibility/selection results, with evidence hashes and two distinct certifier identities.

`validate_certification_decision` validates this complete envelope, rejects self-review/inconsistent results and requires two proof hashes per item. It is a structural research scaffold. It cannot authenticate agent identities, prove that referenced raw documents were actually reviewed, or substitute for the independent primary-document review service. This release creates **zero terminal certification decisions**.

`audit_events.jsonl` records each initial case handoff in a deterministic sequence/hash chain; corruption verification is implemented. A local regenerated hash chain is tamper-evident within its retained anchor, not a WORM store or independently notarized append-only ledger. Release storage must append events atomically, preserve prior certified/revoked events and anchor heads in immutable external storage before claiming immutability.

## Impact and acceptance criteria

Priority uses only archived r63 and that date's candidates. A lower observed score cannot displace the fixed fifth candidate, but it can fill cash when fewer than five candidates were selected. Unknown momentum remains actionable. Stable ties follow the original engine's sorted ticker iteration and stable descending sort.

`date_impact_bounds.json` re-ranks the fixed archived selections together with all positive observed backlog momenta under the hypothetical assumption that every backlog case qualifies. A second scenario lets missing momenta outrank every observed value. The results are conditional upper bounds on changed target slots, with zero lower bounds. They are not probabilities, return bounds, certified changed decisions, or proof that the overall historical universe is correct. Removed/excluded names outside the fixed backlog and changes to selected inputs remain separate global-certification risks. `return_impact` is explicitly null.

Acceptance for this safe research release: exact 943 unique cases retained; deterministic regeneration; all original input hashes agree; source failure/timing/semantic findings retained; no automatic terminal case closure; independent checks reject future/malformed/wrong-accession/wrong-quarter data; impact cannot overcount five slots; originals and production untouched. Acceptance for final historical certification requires both independent certifiers' complete proof envelopes and frozen, auditable replay of every affected signal, order/account path and reconciled P&L with original costs, actions and dates. Strategy changes must be separate versioned experiments and cannot repair a failed GEM V1 test.

The actual findings and open tasks are in [REPORT.md](REPORT.md).
