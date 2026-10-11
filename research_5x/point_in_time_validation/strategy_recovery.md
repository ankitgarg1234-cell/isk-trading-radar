# Strategy recovery and freeze status

No substitutions were made. Configuration status is separate from data quality and separate again from independent out-of-sample evidence.

## A — original 75/25 rotation

The adaptive branch contains a **reconstruction**, not the reconciled original. Its source declares 75% rotational / 25% leadership, 15/5 slots; positive multi-horizon momentum; eligible global ranks; new rotational entries in top 20; retained rotational names through rank 35; leadership from the largest 15 issuers with rank ≤100, positive 126-session return and price above EMA200; inverse percentage Wilder ATR14 sizing with empty slots left as cash; monthly resizing; ATR stops; full BEAR liquidation in its control; next-open orders and 7 bps modeled per side. Reconstructed fundamental admission requires nondeclining annual revenue and positive gross profit, with a Financials exception.

These are source observations, **not certified original rules**. `evidence/scripts/adaptive_market_state_backtest.py` lines 31–34, 369–390, 562–580, 598–667 and 722 identify the relevant implementation. The source has later overrides for adaptive variants; importing it as A would be an unsafe silent substitution.

The branch's `frozen_baseline_reconciliation.json` says BLOCKED: the claimed original 2022/2023/2024/2025 results are −17.25%, +2.91%, +50.52%, +13.05%, while its frozen-like reconstruction reports −6.89%, −3.67%, +3.40%, +9.22%. Original transaction and daily-NAV ledgers are unavailable. Neither set is admitted as the requested new A results. Fitting thresholds to these totals would not recover the original engine.

## B — growth, earnings and margin

Recovered candidate is `growth_margin5`, exactly `n=5, score=r63, filter=growth_margin`, at `evidence/research_5x/code/run_research.py:258`. Revenue YoY >20%; positive net income with YoY improvement >20% or transition from nonpositive to positive; operating-margin YoY improvement >3 percentage points; strictly positive 63-session momentum; descending 63-session ranking; monthly signals; five equal 20% slots; unfilled slots cash; whole shares; sell excess/removed names before buying; 20 bps per side in the published baseline. Fundamental snapshots are cut off one calendar day before the monthly price observation, with revenue/net-income freshness ≤210 days. Eligibility additionally requires 126-session history, ≥$10m average daily dollar volume and nominal price ≥$5.

Price observation on month-end and next-session-open execution are archived timing semantics. The user's stricter requirement of prices before the signal date needs an explicit timestamp/date definition in the common freeze; it cannot be silently relabeled retroactively. Signal-to-each-fact provenance was not retained in the monthly feature panel.

## C — retention is not a single recovered rule

The continuation adapter exposes three different choices: `retain_rank35` (retain qualified ranks ≤35), `preserve_weights` (preserve incumbents instead of equal resizing, subject to the inherited 25% monthly cap), and `retain_and_preserve` (both). The phase-2 holding experiment separately tests monthly equal, quarterly equal, untouched hold, monthly cap25 only, fundamental exit only and relative-strength exit only; these freeze an initial basket and admit no replacements. Those static-basket ablations are not a rotational C.

All variants are preserved and indexed. No preferred C was chosen after viewing their returns. Rank retention and weight preservation are two separate interventions; their combined result cannot identify either one's isolated effect.

## D/E — adaptive leadership

The market-state controller has GREEN / NARROW_LEADERSHIP / CORRECTION / SYSTEMIC_BEAR states, and an optional weekly recovery mechanism. It measures broad/mega-cap health; it does not supply the requested within-sector improving-industry ranks. The independent sector-first engine explicitly says it is not the original 75/25 engine, has no SEC fundamental gate and was specified in October 2026 after the historical years existed.

Neither supplies a certified, pre-2022-trained D/E implementation. Historical industry maps and training data are absent. No adaptive thresholds were optimized, no year exceptions were added and no artificial freeze was claimed.

## F — benchmark

The archived benchmark uses whole-share SPY at the first open, 20 bps entry cost, cash dividends on ex-date, no reinvestment and no terminal exit. It is a recovered benchmark candidate, not a completed certified 2022–2025 benchmark. The common freeze must use actual payable-date cash accounting consistently with all strategies and specify reinvestment, cash interest, first entry and terminal marks. Missing SPY inputs must not be inferred from standard index return tables.
