# GEM V1 inside the existing Dual Momentum dashboard

Feature branch: `feature/gem-trial-in-dual-dashboard-2026-10-12`
Base: `dual-momentum-dashboard` (NOT the unrelated Trading Radar `main` app).
Frozen retrospective research reference: `d59b93d3d9a87d582045b4ae71ff9a6f696a48be`.

## Delivered safe first slice

- Existing homepage, `/trial`, existing schema, portfolio engine, paper worker, trades and balances remain unchanged.
- New authenticated `/gem-trial` dashboard and read-only `/api/gem-trial/status`.
- Both existing dashboard screens link to GEM; GEM links back to them.
- GEM starts with **no account, no holdings, no NAV or returns, and no approved orders**. USD 10,000 is **planned capital**, not a fabricated DB cash balance.
- No `GEM_DATABASE_URL` is assumed, created or reused. The read-only dashboard can ingest a separately exported projection via `GEM_STATUS_SNAPSHOT_PATH`. The web app never writes this file or reads DM ledger tables. All purchases remain unconditionally disabled.
- All required sources appear as UNKNOWN until a verified projection is collected. The old Dual Momentum scanner does NOT automatically qualify as the GEM data source.

This is a **non-trading dashboard scaffold**. It is not an operating GEM data pipeline or a release-ready forward trial. Never treat a displayed QA/source claim as server-side authorization.

## Data source readiness and concrete owner

| Input | Existing capability | GEM requirement / remaining gap |
|---|---|---|
| S&P 500 membership | Dual Momentum has secondary historical component CSV + current members | Primary dated announcements, effective-time and identifiers, complete eligible universe; block if uncertain |
| Daily prices / volumes | Dual Momentum has Yahoo daily chart feed; research used archived Yahoo and other quotes | Collect 126 prior valid observations per security, r63, nominal close, 20-day volume, stable price adjustment/actions, signed source receipts, full coverage and completed-session deadlines |
| Company fundamentals | Existing application has SEC companyfacts adapters; research has same-accession SEC facts for selected winners | Independent live original accession/raw XBRL 10-Q, quarter derivations, publication/acceptance timestamps, exact GEM cutoff and complete competing universe; gross margin logic from DM is not GEM operating-margin logic |
| Calendar | pandas_market_calendars dependency and NYSE session utilities exist | Independently qualify close/next-open schedule, early closes, exchange delays and job deadlines |
| Corporate actions | Yahoo dividends/splits in existing price adapters | Full split/spinoff/merger/delisting, original adjustment vintage, dividends credited on payable date, post-action cash/holdings proofs |
| SPY comparator | SPY daily data in existing scanner/backtest | Separate GEM-specific synchronized total-return, cash timing and same inception alignment |
| Audit/QA | `gem_paper` research controls and `docs/gem-v1` on `research/gem-forward-safety-2026-10-11` | Independently implement and integrate full raw-data features, complete ranking, distinct signer, order replay, atomic GEM journal/DB and release gates; NOT included in this UI branch |
| Paper persistent storage | Dual Momentum `DATABASE_URL` and DM tables already exist | Provision a new GEM-only database or explicit isolated schema (requires explicit owner approval), least-privilege roles, migrations/backup drills; do not point at existing DM DB by default |

The chat-connected IBKR research sample is **not** a deployed data collection gateway or a credential that Render may reuse. A separate permitted read-only IBKR bridge can be evaluated, without connecting brokerage orders. Yahoo may be useful for a provisional price feed but cannot be called certified without full coverage/action checks.

## Deployment safety

1. Review and run tests. Changes should first be deployed to a preview environment or only after a known-good backup of the existing Render deployment and persistent DB. Do not alter `DATABASE_URL`, reset the DM trial, reinitialize cash, or change auto-run settings.
2. Merge into the branch **actually tracked by the existing `dual-momentum-radar` service**, not `main`; inspect Render's live branch/deploy settings first.
3. The new GET routes work even with **no GEM storage or data credentials**. They will display explicit UNKNOWN/NOT STARTED/BLOCKED states.
4. Configure GEM-only projection after independent data/QA pipelines exist. For an initial local development-only example, set `GEM_STATUS_SNAPSHOT_PATH` to a bounded, server-local JSON read model with schema `gem-dashboard-v1`, exact frozen ref, environment `shadow`, UTC `observed_at` and source status entries. Production should instead use an authenticated, read-only GEM-specific database projection; Render ephemeral disk is not a durable ledger.
5. Do not enable order workers from a web configuration toggle. They are intentionally absent. G0–G6 release/QA plan from the GEM safety branch must be satisfied before a separately designed and explicitly approved paper execution release.

## Automated tests

`pytest -q tests/test_gem_dashboard.py`

Tests cover missing/stale/wrong projection, source UNKNOWN, no fabricated P&L, and spoofed user/QA approval unable to enable execution. The tests do **not** establish complete source qualification, operational readiness, or test an external deployment.

## Separate parallel historical work

The existing 943-case research must remain on `research/gem-competitor-certification-2026-10-11`. A static 943-case archive reference is displayed with its date, not as a fabricated live progress feed. Retrospective findings never amend prospective GEM decisions.
