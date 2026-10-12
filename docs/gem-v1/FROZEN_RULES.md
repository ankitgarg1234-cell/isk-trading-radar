# GEM V1 authority and exact semantics

## Authority

The controlling snapshot is full SHA `d59b93d3d9a87d582045b4ae71ff9a6f696a48be`, not a moving branch tip. Authority is the frozen configuration plus source engines and the archived specification, with ambiguity resolved by the pinned executable code. Record source SHA-256 digests and input hashes for every run. A mismatch blocks the run. Freeze the production execution implementation only after parity review; prototype helpers do not replace the archived engine.

| Source | Frozen SHA-256 |
| --- | --- |
| `research_5x/code/run_research.py` | `a46271c5436a9fdec93af55705623a270c2888b0124814cf90af873d54ecf7b5` |
| `research_5x/code/continuation_engine.py` | `bb4d9845bbc58493f8f83f7e57c171e874e0d20cbc048cf6fbb42cb6f3f686d1` |
| `scripts/wf3_offline_valuein.py` | `521d6327ba932bde5e548b1b44cc2469afbb69c31e0428f13e2260678468b6d8` |

The archived preparation computes unused future labels. A forward adapter must whitelist needed fields and must never import or run that preparation over a future-containing table. Research outcome fields belong only in a separate retrospective evaluation process after decisions are locked.

## Original configuration only

`growth_margin5`, five slots, `score=r63`, `filter=growth_margin`. No retention variant, market regime, stop loss, sector cap, inverse volatility weight, leverage, optimization, winner exclusion, analyst estimate or interest income. Five 20% targets; vacant slots stay cash. Rank by positive r63 descending using stable sorting. Preparation iterates lexicographically sorted member tickers, so ties preserve that order. Introducing a new tie-breaker changes the strategy.

Universe: reconstructed S&P 500 membership effective on the signal date, including the SATS/ECHO alias only after valid inclusion. For a prospective trial require independently documented security identities, share classes and effective membership events. Incomplete universe evidence blocks the whole monthly decision; missing competitors are not economic failures. Every reconstructed member receives a disposition, including absent-price names.

Price eligibility: 126 prior observations (127 including the signal observation), positive valid bars, nominal close at least $5, trailing 20 observation mean of **vendor close × volume** at least $10 million. r63 uses vendor close at t and t−63. Nominal close is restored with vendor split factors. Do not silently replace the archived vendor convention with nominal-dollar ADV or a different total-return series. Validate adjustment semantics and capture each event. An unresolved action prevents authorization, while the unchanged hypothetical strategy target is retained in the audit.

Quarter eligibility uses filing date through the day **before** the month-end signal. `form_type.startswith('10-Q')` includes amendments under the original rule; do not treat annual Q4 or 10-K facts as eligible. For a period, latest record wins by `(filing_date, accepted_at text, quality)`; direct 60–125 day raw quarter has quality 3, archived derived quarter quality 2, Q1 raw fallback quality 1. Quality breaks ties after filing/acceptance, not before them. Revenue and income series are suppressed if their latest filing is older than 210 days measured from signal date−1; operating income has no separate freshness suppression. Comparator is 310–420 days earlier, closest to 365; an equal-distance tie preserves the earlier period in ascending period order. Margin uses the latest revenue period and its revenue comparator, with operating income matched to those periods. Revenue and income can use independently latest eligible periods, as in the code.

Gates: revenue growth strictly greater than 0.20 with positive comparator; current income strictly positive and either prior income nonpositive or growth strictly greater than 0.20; margin improvement strictly greater than 3 percentage points with positive revenue denominators. Strict inequalities matter. Unknown facts produce an evidence hold, never an invented pass/fail. Derivation must prove all component facts, contexts, periods, units and accession availability.

## Execution/accounting

New month-end closing signal; next available market session open; sell/reduce before buy/add. Original target shares are floor of open equity × 0.20 / (nominal open × 1.002); sequential cash affordability can reduce buys. Costs are 20 bps per side (10 fee +10 slippage) on open notional. Whole shares in ordinary orders, with no borrowing. No inherited basket or December warm start. The prospective account starts with the frozen $10,000 cash at a user-approved start date and waits for the next newly generated month-end signal; changing the calendar start is a declared prospective extension, not a backdated historical account. Do not retroactively fill a missed execution session.

The archived simulator processes splits/spinoffs/dividends before monthly execution, then membership removals. Normal membership removals use the archived effective-date convention. Do not silently promote an alternative candidate after an operational hold. Record the canonical targets and held execution separately.

Cash dividends in frozen reproduction are credited on ex-date, not payable date. Preserve this declared model in the canonical V1 research ledger and separately reconcile economic receivables/payable-date cash. They cannot share spendable cash. Unresolved payable dates/actions block a purchase-capable release; substituting payable-date accounting would need a separately named execution comparison, not an edited V1 result. Archived spinoff fractional entitlements and nonstandard adjustments remain uncertified. Terminal holdings are marked without hypothetical liquidation costs.

At the signal close the next open is unknown. Store a contingent sizing rule, not a falsely known order quantity. A later offline preview may use an observed next open and must be labeled retrospective dry-run with its observation time; it is not an order generated earlier at the signal close.

## No future information / no tuning

Both publication and observation timelines must be retained. Fundamental acceptance/public availability and official filing date must satisfy the frozen prior-day rule; forward first-observed time must precede the actual decision cutoff. Prices must come from completed sessions, observed before computation. Later amendments, revised prices, constituent revisions and reconciliations append new versions; they cannot rewrite an original decision. Historical outcomes may quantify the effect of certified input corrections after evidence is locked, but cannot choose facts, thresholds, priority exclusions, costs, windows or holding rules.

The original audit's fixed `21:01 UTC` signal marker is not a verified NYSE session-close clock across DST/early closes. A verified exchange calendar and unambiguous source timezone must replace that operational marker in the prospective pipeline without changing the prior-day financial rule. Unknown times block; naive timestamps cannot default to UTC.
