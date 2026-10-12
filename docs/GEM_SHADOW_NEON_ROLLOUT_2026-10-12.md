# GEM V1 shadow preparation — 12 October 2026

## Actual state (not a trading release)

The GEM-only Neon project **gem-v1-forward-paper-isolated** was created in Frankfurt. Database `gem_forward` is not a copy/branch of an existing portfolio and has no starting positions. The `gem-v1-forward-2026-10` experiment is `SHADOW`, planned notional USD 10,000 and `execution_enabled=false` with a database CHECK forbidding enabling it. Source, signal, QA, event and shadow observation tables exist with append-only UPDATE/DELETE rejection triggers.

The current Dual Momentum Render database, the October paper-trial holdings/trades, and the existing dual-momentum model were not migrated, seeded, overwritten or moved. The GEM front-end remains read-only and its execution string permanently DISABLED.

### Read-only connection warning

The Neon API's default created role had elevated `neon_superuser` membership. It was **not** connected to Render, and was deleted. `gem_web_readonly` was created as a limited role (not a Neon admin role) with explicit SELECT rights, but **no active password has yet been provisioned**. Do not grant the web dashboard `gem_owner` or any Neon-admin credential. The web page only uses an explicitly configured `GEM_READONLY_DATABASE_URL` with this dedicated role and PostgreSQL read-only transaction settings; it does not fall back to `DATABASE_URL`. Until a secure password/least-privilege verification and source-validation setup are complete, leave GEM_READONLY_DATABASE_URL absent.

### Required data sources and readiness

| Evidence | Available starting point | Why not yet trade-ready |
|---|---|---|
| Universe | Secondary S&P index membership history/current stock list in existing Dual Momentum source | Not primary-certified announcement/effective-time membership and share-class lineage; must prove complete current set and no missing displacers |
| Daily price and volume | Existing Yahoo OHLCV loader, plus previously archived 2024–October 9, 2026 historical bars | Complete current-session feed, 126 valid prior observations for **every** eligible member, 20-day dollar volume, split adjustment vintage, actual next-open fill timing and independent cross-check missing |
| SEC 10-Q | Archived same-accession verification for selected historical GEM winners; original SEC API adapters | Prospective raw quarter computation / 210-day freshness / period matching and every candidate's accrual/publication proof not operational |
| Corporate actions | Existing vendor action events | Complete payment timing, mergers/aliases/spinoffs and primary validation not in active GEM process |
| NYSE calendar | `pandas_market_calendars` + exchange calendar code available | Session close/open scheduling integration and monitoring have not been exercised with GEM |
| SPY | Existing quote/comparator data | Adjusted price and same-period prospective benchmark parity check not yet operational |
| Independent QA | `gem_paper` offline QA prototype on `research/gem-forward-safety-2026-10-11` | Doesn't derive SEC facts, obtain full universe, independently recompute raw features, authenticate reviewers or release paper orders |
| Operational scheduler | Existing Render application runs opportunistic /trial worker | Free instance sleeping cannot guarantee GEM deadlines. Must use independent reliable scheduled collection + job health/late-cycle HOLD |

The current snapshot contains zero GEM source receipts and zero sealed GEM prospective signals. The previously certified 1,638 qualifying financial input uses describe **retrospective** selected-stock evidence; they are not a forward-ready universe. Research still has 943 historical competitor cases open.

### Frozen signal timing

The last completed month-end before today was 2026-09-30. The archive's frozen GEM fresh-account simulation does not permit late, arbitrary mid-month starts or a September warm start. **2026-10-12 is not a valid new GEM V1 buy session**. The next normal signal is after the October 30 session close with next regular opening cycle 2026-11-02, subject to exchange calendar and certified data. Today's legitimate work is collecting/verifying complete history and shadow-mode daily receipts without hypothetical portfolio fills.

### Database safety and rollout

- GEM status API is read-only SQL through a dedicated configured role. A failed connection yields UNKNOWN/disconnected, never rewrites older records or shows fabricated NAV.
- Separate per-experiment source receipts, signal hashes, independent QA review envelopes, events, and market observation tables were initialized.
- Schema CHECK prevents `execution_enabled=true` and only a separately reviewed migration can add actual GEM journal/fill operations.
- DB append-only triggers prevent ordinary UPDATE/DELETE of evidence rows. This is **not** WORM storage against DB administrators; backups, privileges and external signed checkpoints remain release gates.
- Before connecting GEM to Render, provision a credential only for `gem_web_readonly`, verify database privileges and test no write/DDL permissions. Keep secret in Render environment (merge, never replace unrelated env vars), then deploy tested feature branch.
- Before *paper buys*: integrate full sources, reproduce frozen GEM calculations against pinned fixtures, run a genuine future month-end shadow, independent QA and order-simulation/reconciliation tests, and obtain explicit user release. Do not use a UI button or environment variable as authorization.
- Existing Render free Postgres database expires 2026-11-05; its own account/data continuity is a separate urgent risk. This new Neon project does not back up or migrate that existing database.

Verification: `pytest -q tests/test_gem_dashboard.py`. Also rerun the existing /trial tests before deploying. The database was initialized through Neon with successful SQL transaction; existing Render PostgreSQL was not accessed by write operations.
