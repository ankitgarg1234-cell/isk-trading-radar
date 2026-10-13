# GEMv1 isolated deployment — vendor-independent readiness (2026-10-13)

**Mode: read-only; paper execution disabled; real execution disabled.**

## Frozen reference
- Research branch: `research/gem-2025-2026-validation-2026-10-11`
- Original engine: `research_5x/code/run_research.py`
- Archived feature artifact: `research_5x/gem_2025_2026_validation/archived_signal_features.csv.gz`
- Original specification: `research_5x/gem_2025_2026_validation/strategy_frozen_spec.md`
- Production-side offline diagnostic: `gem_data/archive_ranking_parity.py`
- Regression tests: `tests/test_gem_archive_ranking_parity.py`

## Completed without vendor API
1. Standalone isolated dashboard and SEC ZIP source ingestion remain segregated from other Render services.
2. Archived-feature ranking parity diagnostic is now available on this isolated branch. It does **not** run on dashboard startup, connect to a broker, or certify point-in-time sources.
3. Tests cover ordinary eligibility, negative-momentum drift, and missing feature evidence.
4. Original research result remains **retrospective and uncertified**, despite archived accounting reproduction.

## Vendor dependency and outstanding work
- Complete 127-session per-member price/volume history, adjusted-versus-nominal parity, next-open prices and historical removed-member series.
- Vendor corporate-action factors and dividends; independently reconcile issuer event dates, payouts and mergers.
- Original accession-specific SEC Inline XBRL fact/context signoff, ambiguous competitors and amendments.
- Primary effective-dated S&P membership lineage, complete calendar and independently reconciled SPY total return.
- Full archived-feature report must actually run and be reconciled against `signals.csv`, `stock_selection_audit.csv` and the original simulator.
- Production monthly snapshot integration, restart and paper-account reconciliation remain **NOT IMPLEMENTED/CERTIFIED**.

## Deployment policy
Deploying this branch updates only the isolated GEMv1 diagnostic service. Do not enable paper orders, live orders, scheduled signal execution or other Render services. A green /health is only process liveness, not strategy certification.
