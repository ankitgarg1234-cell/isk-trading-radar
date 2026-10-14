# GEM V1 — rapid six-source engineering audit (2026-10-14)

This is not an independent source certificate, merged release or instruction
to trade. Frozen research authority remains d59b93d3d9a87d582045b4ae71ff9a6f696a48be.

## Why we did not finish in hours

Collection, normalization, point-in-time correctness and trading authorization
were conflated. Initial extraction can be fast; exception reconciliation is not
an automatic consequence of storing a receipt. Do not retry every issuer blindly.

Evidence from isolated GEM Neon `gem_forward`, read-only spot check, Oct 14:
- Membership: current Wikipedia and secondary GitHub datasets exist. No
  independently vetted effective-dated membership and alias ledger.
- Prices: 489 distinct Marketstack ticker receipts, **all 489** source QA
  PENDING and adjustment parity FALSE, **471** with fallback/rejections,
  **8** with fewer than 127 accepted sessions; no approved price receipts.
  The initial backfill collector's `complete` set includes every symbol with
  a persisted Marketstack receipt even if it has rejected/incomplete sessions.
  An attempted symbol is also tracked in the request-reservation journal:
  without a separate controlled repair loop, a present API key does not fix it.
- SEC: 500 distinct original submissions CIK members, 500 distinct original
  companyfacts CIK members; independent latest-per-CIK automated fact replays
  report 316 CANDIDATE_COMPLETE_NOT_CERTIFIED and 184 UNKNOWN. Their exception
  groups overlap: current/prior missing operating income each 110, ambiguous
  revenue concepts 57/58, missing parent net income 38, missing revenue 12.
  No approved independent financial fact audits. A known stale-quarter issue
  means candidate-complete does NOT imply numerical/source correctness.
- Actions: partial SEC 8-K event candidates across 500 CIKs; zero complete
  certified split/dividend economic ledgers.
- Calendar: first-party NYSE hours-calendar material stored; emergency closures,
  exact completed sessions and independent manifest QA not signed.
- SPY: official State Street ex-date/pay-date schedule present and partial
  independent price probe, but cash dividend amounts, matched benchmark price
  bars and source-verified total-return series not complete.

## Concrete rapid engineering path

1. **Membership** — keep today's full primary/secondary source captures with
   hashes and as-of timestamps; check 503-style multi-class security identities,
   issuer CIK aliases and company changes on the target month-end. Avoid re-scrape
   as a substitute for effective-date verification.
2. **Prices** — run `gem_data/gem_price_repair_plan.py` over ALL intended member
   symbols and latest stored Marketstack receipts. Separate missing, <127 valid
   bars, rejected EOD and unreviewed adjustment semantics. Prioritize missing
   source repair and the 63-session momentum window. Use licensed fallback
   or manually approved bounded vendor retry with raw response receipt and
   cost budget. No blanket re-fetch of all 489 and no false FAILED_MOMENTUM.
3. **SEC** — compute provisional r63 priority from valid observed closes,
   retain unresolved prices as BLOCKERS, then use existing original SEC ZIP
   receipts and `gem_sec_momentum_parity_cli.py` to select only positive-r63
   candidates for quarterly financial comparisons. For matching positive
   issuers on HOLD, use `gem_sec_edgartools_fallback_cli.py` accession-specific
   10-Q/A retrieval. Record original-context, units, filing version, derived
   YTD operands and thresholds; no approval from simply successful parse.
4. **Corporate actions** — bulk obtain daily split/dividend event history from
   a source consistent with price vendor adjustment rules; reconcile ex-dates,
   ratios, share-class changes, spinoffs and special distributions. EdgarTools
   original 8-Ks are exception evidence; they are NOT a complete action feed.
5. **NYSE** — derive an exact exchange session manifest from official NYSE
   source + independently cross-checked calendar, including exceptional
   closures and half-days. Compare every price series with manifest.
   The uploaded daily factor strategy derives market dates from price data;
   it is not a stand-alone NYSE calendar proof.
6. **SPY** — adapt user's dividends snippet to collect SPY unadjusted Close,
   ex-date cash Dividend and stock-split ratio on matching daily sessions.
   `gem_spy_total_return_diagnostic.py` implements a transparent ex-date
   reinvestment diagnostic and fails closed on missing sessions/splits.
   `scripts/gem_spy_fastpath_cli.py` supports offline CSV and an explicitly
   selected operator-only yfinance fetch; results are secondary provisional
   data until checked against official SPY distributions and independently
   sourced prices/returns. Do not count adjusted Close plus cash dividend twice.

## Acceptance checklist

- Each issuer/security eligible for the target month-end represented or
  conclusively excluded by **verified** frozen price and liquidity gates.
- No use of unverified Marketstack adjusted bars for a final r63 exclusion.
- Only positive-r63 candidates need detailed SEC quarterly verification AFTER
  independently certified price gate evidence; provisional triage may precede.
- Original SEC accession-specific financial facts and quarter source operands
  reproducible, reviewed separately from the developer.
- Real split/dividend economic ledger matches price return convention.
- Calendar and SPY benchmark source series complete and independently checked.
- Full monthly Top 0–5 final ranking reproducible; prospective signal,
  shadow-policy requirement and owner approval. Broker trading remains manual.

The urgent path is an **auditable no-order read-only diagnostics dashboard**,
not a fabricated certified five-stock list. No source approval, DATA HOLD
override, deployment or broker operation is implied by this document.
