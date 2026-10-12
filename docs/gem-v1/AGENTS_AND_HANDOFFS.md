# Agent responsibilities and handoffs

Agents may research and propose; only deterministic services with scoped identities can eventually authorize or apply an execution event. The initial implementation has no execution capability. Separate agent prompts alone do not enforce independence; release requires separate service credentials, access controls and auditable ownership.

| Role | Owns / produces | Receives / hands to | Forbidden or separation requirement |
| --- | --- | --- | --- |
| Orchestrator / release owner | Work queues, milestones, manifests, consolidated evidence, held-run status | All agents → user | Cannot override a QA failure, choose a new rule or infer user signoff |
| Universe and identity agent | Effective-dated membership and stable security/share-class mapping, all-member coverage report | Primary index announcements → data/QA | No current-universe substitution, unresolved alias guess or omission |
| Market-data agent | Price/calendar/action source bundles, exact session freshness and adjustment QA | Source bytes → signal/QA/reconciliation | No future bars, revised history overwrite or ticker-only identity |
| SEC provenance agent | Original accession facts, period/unit/context map, acceptance/dissemination/observation evidence | SEC source bundles → normalizer/QA | No later restatement backfill, guessed timezone or misleading pretax-income mapping |
| Frozen signal agent | Pure GEM V1 candidate table and canonical top-five | Sealed as-of snapshot → plan/QA | Cannot read future outcome fields, change thresholds or mark missing data as failed gates |
| Plan / simulator engineering agent | Contingent sizing, observed-open dry-run preview, idempotent journal design | Signal+isolated account digest → QA | Cannot issue own QA certificate or submit/apply unapproved orders |
| **Independent pre-trade QA agent** | Recomputed facts/universe/ranks/plans; check evidence; signed PASS/FAIL/HOLD | Independently fetched sealed raw inputs+plan → authorization/user | Different identity from signal/plan authors; no edits to reviewed evidence; no purchase permission |
| Authorization service | Future paper-only capability bound to certificate, release and reconciled state | QA+explicit user release → dedicated simulator | Default deny, no production routes/real broker credentials, no textual approval bypass |
| Reconciliation / monitoring agent | Independent cash/shares/basis/NAV, replay/checkpoint comparison, incident alerts | Events+independent marks → QA/authorization | Cannot repair ledger by edits or auto-clear holds |
| Historical certifier B1 | Case fact and publication proof, correction proposal | Pinned 943 queue+original accession evidence → B2 | No performance-derived fact selection or threshold tuning |
| Historical certifier B2 / impact reviewer | Independent agreement, locked correction set, unchanged-rule replay delta | B1+independent evidence → release owner | No single-review certification or return claim with incomplete actions/prices |

Implementation in this task used three parallel agents plus the coordinating agent: `forward_controls`, `historical_certification`, `architecture_review` (independent QA), and the root architect/release coordinator. These are development responsibilities, not deployed trading identities. The QA agent reviews code written by the other agents and publishes unresolved issues in `QA_REVIEW.md`.

## Mandatory handoff envelope

Each handoff names schema version, producer identity, run/case ID, parent artifact hashes, rule/base/code digest, account/environment, as-of and retrieval timestamps, source references, output hash, reason-coded warnings, status, reviewer and next owner/deadline. Canonical hash excludes only explicitly non-decision metadata; no silent mutable fields. Receiver validates the schema and all referenced byte hashes before acknowledgement. An acknowledgement is a ledger event, never just an agent message.

A missing acknowledgement at the cutoff generates `HANDOFF_INCOMPLETE`; no default pass. Handoffs bind to an exact version, so edits require a new artifact, review and acknowledgement. Conflicting evidence is retained on both sides and escalated with no rank or trade change until resolved. Timeouts close the current opportunity, not the safety check.

## Multi-agent review policy

QA independently recomputes from raw sealed sources, rather than checking that two agents repeated the same derived values. At least one deterministic independent implementation and one semantic/source reviewer are required for release. Separate prompts relying on a shared aggregate SEC response are correlated evidence and must be labeled accordingly. The user reviews the evidence dossier and authorizes a specific release/account/time range; ongoing per-cycle QA is still required after release.

Historical evidence corrections require B1/B2 agreement and an append-only decision event. Share accession tasks across dates to save acquisition work, while preserving individual security/date cutoffs and decisions. Historical certifiers have read-only access to A artifacts and no execution capability.

## Source and dashboard ownership

The [source register](SOURCES_AND_COLLECTION.md) assigns exact upstream evidence to universe/identity, IBKR market-data, SEC provenance, calendar/action, historical certification and independent QA roles. IBKR is the selected broker market source; no new Yahoo collector is selected. The dashboard projection owner maintains a separate read-only view of those artifacts and [the interface contract](DASHBOARD.md). Planned paper capital is USD 10,000, separate from actual broker balances. New source/API/dashboard services are not running and the user has selected the “Interactive Brokers (IBKR)” source connection; full collection/identity/market-data qualification remains pending.
