# Alert Management + No-Panic-Sell Patch

This incremental patch is based on the current ServiceNow-inline-filter build.

## Decision rule hardening
- `REDUCE` is now evidence-gated: short-term price weakness, momentum deterioration, bearish sentiment, a low deterministic score, or a technical stop break **cannot by themselves** trigger REDUCE.
- `REDUCE` requires explicit thesis/fundamental invalidation evidence, such as thesis-breaking news or verified deterioration versus the prior saved fundamental snapshot.
- `EXIT` is reserved for severe thesis invalidation.
- Technical stop/invalidation alone becomes `HOLD — THESIS REVIEW` for an existing position.
- If thesis remains intact, the engine uses HOLD / HOLD-DON'T ADD / TAKE PARTIAL PROFIT / ADD as appropriate.
- Prior snapshots are compacted to only the fields needed for deterioration detection, avoiding recursive payload growth.

## Alert queue UX
- Alert cards are clickable and open an inline drill-down.
- Drill-down shows price, System conviction, AI conviction, analyst view, active level, evidence confidence, reason, thesis state, current position, action plan, recent news, and sensitivity scenarios.
- `×` dismisses an alert from the active queue.
- `Acknowledge` marks it reviewed.
- `Snooze 1h` hides it temporarily.
- Duplicate active alerts for the same ticker + condition are refreshed instead of appended.
- New conditions supersede stale active alerts for that ticker while keeping old records acknowledged.
- Alerts are priority sorted: thesis-invalidated EXIT/REDUCE first, then actionable buys, profit/rebalance actions, then wait/review items.

## Conviction filters
- System conviction and AI conviction thresholds are now visible directly in the System View column header, rather than hidden in the secondary filter menu.

## Database migration
- Adds nullable `alerts.snoozed_until` column.
- The application performs a small additive runtime migration for existing SQLite/Postgres databases.
