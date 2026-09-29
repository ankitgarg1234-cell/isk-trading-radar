# Event-driven paper-entry patch

This incremental patch changes the $10,000 shadow portfolio from a blanket 24-hour entry cadence to a two-speed model:

- New STRONG BUY / BUY / STARTER BUY signals are evaluated immediately after the scanner cycle that detects them.
- Multiple actionable changes in one scanner cycle are coalesced into one optimizer run.
- Material rank changes are bucketed to avoid re-running on tiny intraday noise.
- Thesis-gated paper EXIT / REDUCE / TAKE PARTIAL PROFIT remains immediate.
- Portfolio rotations/swaps remain daily (or manually forced) to prevent churn.
- Event-driven entries do not move the daily rotation clock.
- Paper holdings are added to scanner priority symbols so held names receive fresh thesis/risk checks.
- Neon egress is reduced: normal cycles read only current paper holdings (max 7); the Top-20 compact candidate payloads are loaded only when an optimizer event/daily rebalance is actually due.

No live broker execution and no change to the deterministic score or optimizer ranking formula.
