# Catalyst, valuation and qualification audit — 5 October 2026

## Observed failures

The 19:21 screenshot shows an older Credo analysis with Catalyst 5/15. The
previous factual-sentence repair is already deployed: a subsequent captured
analysis awards 8/15 for the asserted revenue-growth event. Credo's valuation
remains 3/10 for Finnhub trailing P/E 76.3393. The existing growth bonus requires
annual revenue growth above 25% **and** P/E below 45; Credo fails the latter test.
Forward P/E is unavailable while Yahoo quoteSummary returns HTTP 401. No forward
earnings estimate has been invented or substituted.

The 20:04 Microsoft screenshot exposes a different problem. Classification
still admitted Core at 68 while the canonical paper account requires 70.
Dashboard shortlisting also omitted the mandatory Analyst 75 gate and used
rounded R/R instead of target/stop geometry. Raw BUY text could bypass failed
qualification in the display's system-signal fallback.

Microsoft's factual headline “Melius Research upgrades Microsoft stock to Buy,
$665 target” was discarded by the stock-picking-opinion regex. That loses 1.5
News points. A broker action remains News evidence, not a business catalyst;
Analyst confirmation independently uses the provider recommendation mix.

## Corrections

- Exempt the destination rating phrase from the opinion filter for an asserted
  broker action. Questions and speculative modal language still block credit.
- Restore existing acquisition/merger, clinical-trial and analyst-day catalyst
  categories to explicit event rules. Do not infer an acquisition from an
  insider share purchase or credit another company's event.
- Only positive factual business events earn bullish Catalyst categories and
  event bonuses. Negative/mixed events remain available to risk/thesis overrides,
  but cannot raise bullish targets or verify an Explosive catalyst.
- Independent identified broker actions are not deduplicated as one earnings
  release merely because they occur within 36 hours. Same-URL/title duplicates
  still count once.
- Select the first positive finite P/E: forward, then trailing. Invalid forward
  values can no longer mask valid trailing evidence. Keep the existing bands,
  growth bonus, component weights and neutral missing-data treatment.
- Apply deterministic 70, Analyst 75 and unrounded target/stop R/R 0.4 to Core
  qualification and dashboard shortlisting. One shared entry check powers paper
  signals/fill rechecks, new-position actions, optimizer buy selection and alerts.
  The paper adapter still separately enforces exchange-quote freshness,
  market-open checks, subsequent-observation fills and frozen signal levels.
- Share completed-session breakout/chase geometry with the paper adapter.
  Today's changing close cannot continuously raise its own breakout hurdle.
- Failed gates cannot be overridden by raw buy-language labels. Existing
  holdings remain available for thesis/exit management; failing a new-entry gate
  does not initiate a sale. Paper allocation bands, trial dates and account
  identity remain unchanged.
- Expose Catalyst and Valuation formulas, input basis/source/date, precise score
  values and explicit qualification/trigger status in symbol analysis. Preserve
  all 15 audited headline groups when compacting the new news version.

## Same-input replay

Captured full production analyses were replayed with identical prices, filings,
recommendation counts, headlines and price/sector histories. Headline evidence
and author assessments were reconstructed from the audited source records.

| Symbol | Previous score | Corrected score | Catalyst | Valuation | R/R | Entry result |
|---|---:|---:|---:|---:|---:|---|
| MSFT | 69.1 | 70.6 | 5/15 | 7/10, trailing P/E 28.7325 | 0.426883 | Numerical qualification passes; waits for entry trigger |
| CRDO | 67.5 | 67.5 | 8/15 | 3/10, trailing P/E 76.3393 | 0.237806 | Score and R/R fail |

These are same-input diagnostic comparisons, not executed orders or promised
future live scores. A qualifying score does not by itself create an entry.

## Validation

The final focused regression run passes 357 tests with 4 known legacy dashboard/
allocator failures deselected. Those four also failed before this change; an
inclusive regression run confirmed the same failure IDs, with no new failures.
The initial whole-repository attempt ended before producing a summary, so no
whole-repository pass is claimed. Existing historical full-suite output records
27 unrelated/legacy failures.

Coverage includes production headline/P/E fixtures; opinion, negation, company
scope, negative-event and duplicate controls; valuation boundaries and invalid
basis fallback; exact 70/75/0.4 boundaries including forged display R/R;
completed-session breakout parity; persisted alert deduplication; existing
holdings/exits; frozen paper fills, fees, risk/cash/whole-share limits and trial
account continuity. Templates render the new formulas and gate status. No
trading threshold was lowered to manufacture candidates.
