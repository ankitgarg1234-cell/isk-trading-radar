# GEM V1 — momentum-targeted EdgarTools 10-Q XBRL exception recovery

**2026-10-13, PR #103 review branch only. Not deployed.**

This is an optional SEC-document **evidence recovery** tool intended to reduce work ahead of the next GEM V1 manual-live readiness review. It is **not** a source, ranking, financial-parity or broker-order approval.

## Why not ingest every company's income statement?

- Isolated GEM Neon already retains hashed SEC ZIP submissions and companyfacts members for 500 CIKs. Re-fetching these statements duplicates existing data.
- Frozen GEM requires a strictly positive **63-session adjusted** return before financial gates; the prospective review queue can prioritize provisional positive-momentum stocks.
- A provisional *negative* Marketstack return does **not** prove a frozen-rule exclusion. Current market-adjustment QA is pending for all 489 collected price histories; price missing/rejection cases remain global ranking blockers until independently resolved.
- EdgarTools `Company(ticker).get_financials()` is not the correct historical as-of primitive. SEC accession-specific `get_by_accession_number` + `filing.xbrl().facts.to_dataframe()` preserves the original 10-Q/10-Q/A selected by the source manifest. Never retrieve an unbounded latest financials snapshot for the decision engine.

## Two-stage read-only workflow

1. Existing `scripts/gem_sec_momentum_parity_cli.py` scans current *secondary* S&P symbols using hashed Marketstack receipts, computes provisional r63 where observations permit, and reads original SEC ZIP-member facts only for positive-momentum priority candidates. Every missing-price competitor remains on HOLD.
2. `scripts/gem_sec_edgartools_fallback_cli.py` takes only those **SEC diagnostic HOLD** issuers. It reads their stored, checksum-verified *submissions* original, selects all eligible 10-Q and 10-Q/A accession versions for the two latest quarters and available YoY matches **as of signal date minus 1 day**, and emits a bounded exception retrieval plan. A same-company dual-class stock does not trigger duplicate document downloads.
3. Optional independent operator action retrieves planned XBRL facts only, retaining concept, units, context, period and accession identifiers. No inferred GAAP/custom-tag substitution, YTD-quarterly difference, or amendment precedence is accepted as VERIFIED purely because it parsed. Review compares evidence back to the pinned `PITFundamentals`, its `derived_quarterly_value` source operands, and SEC's original accession-specific facts.
4. Only missing/ambiguous source cases are sent to accounting/XBRL reviewer. QA/release remains blocked until *all potentially competitive* member identities, adjusted price histories and sources are resolved.

## Operator commands

This code is **not installed on the Render dashboard**. Use a permitted workstation/ephemeral isolated runner with the `gem_web_readonly` DSN supplied through secret management. Do not paste passwords into a shell history or GitHub.

Dry run (no SEC requests, no EdgarTools installation, no DB writes):

```bash
python scripts/gem_sec_edgartools_fallback_cli.py \
  --signal-day 2026-09-30 --limit 5 --offset 0
```

Only for a separately authorized network/reviewer trial (do not enable merely because dry-run tests pass):

```bash
python -m pip install -r requirements.txt -r requirements-gem-sec-xbrl.txt
# From your approved secret manager: GEM_READONLY_DATABASE_URL,
# EDGAR_IDENTITY (SEC contact name and email; do not commit them).
# Require an existing protected /secure/gem-sec-review directory.
GEM_SEC_XBRL_FALLBACK_ENABLED=yes \
python scripts/gem_sec_edgartools_fallback_cli.py \
  --signal-day 2026-09-30 --limit 5 --offset 0 \
  --fetch --max-filings 4 --output-dir /secure/gem-sec-review
```

Each fetch attempt is accession-checked against the saved filing date, form and issuer CIK, uses one-second pauses between documents, refuses more than eight selected accessions per run, and writes JSON evidence as a new file with a SHA256-derived unique name (no overwrite). EdgarTools itself can issue multiple SEC requests per document, so **one second per filing is not a verified per-request SEC rate limit**: control actual network rate and retry/backoff at the operator gateway.

It never sends stored prices or SEC document artifacts to a broker, places an order, modifies Neon source receipts or sets `approved_for_trading`. No DuckDB table or new data pipeline needed merely to inspect financial exceptions. The resulting parsed-fact SHA is a hash of **transformed extracted rows**, not an independently verified hash of the original Inline XBRL bytes.

## Release acceptance (NOT provided by this tool)

- Source-backed historical/effective-dated S&P 500 membership and stable issuer/security identity.
- Exact completed exchange-session manifest and fully certified adjusted 63-session price, split/action and liquidity inputs for every potentially competitive stock; nonpositive exclusions must be proven, not merely provisional.
- Attributed filing-version selection and verified direct or originally derived quarterly revenue, parent net income and operating income with reconciled periods, unit/context, and original publication cutoff.
- Exact B/C parity vs hash-pinned GEM V1 original, complete-universe ranking QA, independent human code/data reviewer, and prospectively authorized shadow/manual live policy.
- Explicit owner release authorization. No broker execution integration required because trades are manual.

**Morning status:** This document and code are a *tool to accelerate remediation*, not permission to advertise production-ready trading recommendations. PR #103 stays draft until independently reviewed and authorized; Render auto-deploy remains OFF and DATA HOLD remains enabled.
