# GEM V1 offline safety prototype

This package is a research-only control scaffold. It imports only the Python
standard library and its own modules. It does not import `app`, read deployment
configuration, access credentials, start a scheduler, connect to a database or
broker, or submit simulated/real orders. **Purchase authorization always returns
`authorized: false`, including with a forged PASS bundle or signoff argument.**
No configuration flag can enable execution in this version.

## Frozen lineage

The baseline is `research/gem-2025-2026-validation-2026-10-11`, commit
`d59b93d3d9a87d582045b4ae71ff9a6f696a48be`. `frozen.py` pins SHA-256 bytes for
the exact specification, configuration, research engine, continuation adapter,
and PIT engine. `verify_frozen_artifacts(root)` reads those files without
executing them. Any changed/missing artifact fails verification. `RULES_HASH`
binds the commit and complete artifact map.

`select_frozen_features(rows, expected_member_tickers=...)` accepts typed,
already-derived contemporaneous features. It requires full coverage of the
independently supplied historical membership universe and unique stable
security identities. Missing/nonfinite/unresolved values block the whole
shadow check. This is stricter operational rejection of uncertain input, not a
new economic exclusion. Complete rows use precisely the original observable
gates: 126 prior prices, positive bars, nominal close >=5, vendor close×volume
ADV20 >=10 million, revenue growth >.2, archived earnings-improvement Boolean,
margin improvement >3 points, and r63 >0. Ranking uses descending r63 only;
ties inherit alphabetical member-symbol order from the frozen preparation
engine. Five 20% slots; unused slots remain cash.

The package does **not** derive facts, compute quarterly comparators/earnings
gates, enforce the 210-day revenue/NI freshness rule from raw filings, construct
126/63-session price histories, resolve symbols/splits, or independently prove
historical membership. It therefore cannot yet certify a prospective signal or
replace the pinned research engine. A raw-data adapter and archived-output
parity tests remain required release gates.

## Interfaces and handoff contracts

1. Data agent retains primary raw evidence and creates `SourceEvidence` objects
   with stable identity, source/content hash, observation/effective timestamp,
   original publication/acceptance timestamp, retrieval timestamp, and verifier
   identity. SEC facts additionally require SEC HTTPS URL, accession, filing
   date, raw-submission hash, and a form starting `10-Q` (including amendments,
   matching the frozen engine). `validate_evidence()` rejects future periods,
   publications, naive timestamps, unverified sources, missing primary evidence,
   and signal-day SEC inputs. It derives the previous **New York calendar day**
   from signal time; the supplied SEC cutoff must equal the end of that day,
   with DST-aware conversion. Filing-date checks use that local date, not UTC.
   Forward runs require retrieval by signal time. Explicit `retrospective=True`
   allows later acquisition of previously published historical records only;
   it must never be used as prospective evidence.
2. Signal agent supplies complete frozen `FeatureRow` records and the
   independently certified historical universe. `select_frozen_features()`
   provides a shadow ranking only. The caller retains full row/lineage hashes.
3. Order-planning agent calls `preview_orders()` **after** observing the next
   session open, with exact decimal cash/prices, whole-share initial holdings,
   stable target rank order, and a separately certified next-session calendar.
   The preview hashes initial state, targets, prices, timing, costs and final
   state. It mirrors ordinary GEM whole-share equal-slot sizing on open equity,
   fixed 20 bps per side, sells before buys, and cash affordability. It returns
   a deterministic in-memory hypothetical plan; it applies no fills and
   modifies no account. Open quotes cannot feed the earlier signal.
4. Reconciliation agent independently provides observed cash/positions to
   `reconcile()`; any exact cash or whole-share difference is a failure in this
   offline model. Live settlement/payable-date, fractional spinoff entitlement,
   market liquidity, price rounding, and corporate-action reconciliation are
   absent and blocked from operational release.
5. Independent QA agent supplies a `QAEvidence` bundle tied to exact signal,
   provenance, preview and frozen-rule hashes. Every named check requires
   `PASS` and a retained SHA-256 evidence artifact. Reviewer and producer IDs
   must differ; checks have explicit issue/expiry times. `validate_qa()` validates
   the envelope, **not the truth or authenticity of its claims**. Different ID
   strings alone do not prove organizational independence.
6. `authorize_purchase()` remains denied regardless of QA/signoff input. A future
   execution release requires separate explicit user signoff after review of QA
   evidence, authenticated identity/signatures, server-side isolation and
   capability enforcement, plus new independently reviewed implementation.
   Existing production/live/deployed-paper state is outside this package.

## Durable audit and retries

`AuditLedger(path).append(event_type, payload, idempotency_key=..., recorded_at=...)`
uses a separate POSIX exclusive lock, validates the entire existing chain,
requires canonical JSON without NaN, appends a SHA-256 linked record, fsyncs
the file and parent directory, and prevents leaf symlink redirection. Reusing a
key with identical semantic content returns the original event; changed
content fails closed. After an ambiguous acknowledgment failure, retry the
same key/content and re-read the event. Partial tail writes block new appends
and require incident handling; no automatic truncation or deletion exists.

`checkpoint()` returns sequence/head hash. `read(expected_checkpoint=...)` checks
the exact current head against a previously trusted checkpoint. Retain that
checkpoint outside the writer's trust domain. The local chain detects altered
records and partial writes, but without an external anchor it **cannot** detect
a valid prefix truncation or complete malicious rewrite. POSIX advisory locks
assume every writer cooperates and the path's parent directory is trusted.
This is a local tamper-evident prototype, **not an immutable/WORM ledger**.
Signed external checkpoints, retention-enforced storage, permissions, backup,
restore drills, clock monitoring and operational alerts remain release gates.

## Verification

Run from repository root:

```text
python3 -m unittest discover -s tests/gem_paper -v
```

The 23 tests use synthetic inputs and temporary local directories, plus one
pinned read-only archive regression. They cover frozen
artifact drift, strict gate boundaries, stable ties and top-five capacity,
future publication/retrieval and SEC cutoff errors, amendments, unresolved
coverage, forged/expired QA, permanently denied authorization, whole-share
costs/cash, sell-before-buy ordering, temporal open separation, reconciliation
drift, concurrent append/retry, content conflicts, ambiguous durable-write
acknowledgment, symlink rejection, payload tampering, partial tails, and anchored
truncation. The archive regression compares known observed gate-passing feature
rows with original recorded top-five signals on all 21 unique 2025–2026 dates;
it pins hashes for both archive files. Its upstream price eligibility and
synthetic security IDs are explicitly projection assumptions. It neither
reconstructs missing competitors nor verifies raw history, SEC freshness,
membership or feature derivation. These checks do not prove production data
quality, strategy performance, full raw feature parity, broker behavior, or
release readiness.
