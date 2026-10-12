# Frozen GEM V1: forward trial and historical certification

Status on 2026-10-11: **development prototype; not approved for paper purchases**.

The two workstreams start from `research/gem-2025-2026-validation-2026-10-11`, commit `d59b93d3d9a87d582045b4ae71ff9a6f696a48be` in [isk-trading-radar](https://github.com/ankitgarg1234-cell/isk-trading-radar). The research branch was verified against GitHub before implementation. Neither workstream certifies the reported historical returns or changes GEM parameters.

* A: `research/gem-forward-safety-2026-10-11`: architecture, controls, synthetic tests and offline previews. No scheduler, broker adapter, deployed service, production database access or purchasable account is added. The purchase authorization function remains closed even if supplied an apparent approval.
* B: `research/gem-competitor-certification-2026-10-11`: deterministic triage and independent evidence review of the pinned 943 security/date backlog. Its queue is for research acquisition priority, never for changing selection rules.

Read [architecture](ARCHITECTURE.md), [frozen rules](FROZEN_RULES.md), [agent handoffs](AGENTS_AND_HANDOFFS.md), [QA and release gates](QA_AND_RELEASE.md), [monitoring and incident runbook](OPERATIONS.md), [tests and acceptance criteria](TEST_PLAN.md), and [roadmap](ROADMAP.md). [Independent QA review](QA_REVIEW.md) records the implementation verdict. [Verification findings](VERIFICATION.md) distinguish completed checks from release blockers.

The [source register](SOURCES_AND_COLLECTION.md) assigns each collector to exact upstream sources and distinguishes the existing archive from proposed entitled feeds. The [dashboard layout and read contract](DASHBOARD.md) define the separate research review interface; neither new source services nor a dashboard is deployed.

The existing deployed Radar/paper strategy, live positions, `app/`, deployment definitions, existing workflows and frozen research inputs are outside the write scope. Both draft PRs target the pinned research branch, not `main`. No merge or deployment is authorized. No real-money trading is part of this project. Automatic paper purchases require a later explicit user signoff **after** reviewing the complete release evidence; this change cannot enable them.

The small local hash-chain ledger is tamper-evident against a retained checkpoint, not immutable storage. Authenticated independent service identities, object-lock retention, data collectors, full rule parity, calendars, corporate actions and the operational rehearsal are future release gates. Passing unit tests is not permission to purchase.

Review the published [forward draft #63](https://github.com/ankitgarg1234-cell/isk-trading-radar/pull/63) and parallel [historical draft #64](https://github.com/ankitgarg1234-cell/isk-trading-radar/pull/64). Both target the frozen research branch. All 943 full historical cases remain open; the disabled prototype is not a released paper trader.
