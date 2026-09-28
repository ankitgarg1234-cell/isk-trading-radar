# Actionable Attention Queue Patch

Apply this patch after the latest ServiceNow-filter / alert-management / DB-egress optimization changes. It is cumulative for the files it replaces and preserves those prior changes.

## What changes

### `What needs attention now` is action-only
Monitoring states no longer enter the attention queue:
- WAIT MORE
- WAIT FOR BETTER BUY
- WATCH
- HOLD
- HOLD — DON'T ADD
- other non-actionable monitoring states

They remain visible in the main Radar.

### Buy attention ladder
A new-position entry alert is created only when price is in Primary Buy or Better Buy and the deterministic conviction meets the agreed ladder (with normal evidence/thesis safety gates):
- 85–100 + Primary/Better Buy -> STRONG BUY
- 75–84 + Primary/Better Buy -> BUY
- 68–74 + Better Buy -> STARTER BUY
- 68–74 + Primary Buy -> CONSIDER BUY
- below 68 -> no attention alert

### Portfolio actions kept
The attention queue still surfaces:
- TAKE PARTIAL PROFIT / TAKE PROFIT
- REDUCE / EXIT (only after the existing thesis/fundamental invalidation gate)
- ROTATE / SWAP candidates
- REBALANCE-compatible actions

### Swap alerts
Portfolio rotation proposals are synced into the alert lifecycle as `ROTATE` alerts. They can be drilled into, acknowledged, snoozed or dismissed like other alerts.

The swap check is intentionally low-egress: it reads only high-conviction candidate rows plus the user's holdings, not the entire U.S. Radar universe.

### Legacy alert cleanup
Old WAIT/WATCH/HOLD alerts already stored in the database are filtered out of `What needs attention now` immediately. Scanner refreshes also acknowledge stale non-actionable live alerts without deleting historical rows.

## Files
- `app/scanner.py`
- `app/main.py`
- `app/templates/dashboard.html`
- `app/static/app.js`
- `tests/conftest.py`
- `tests/test_scanner.py`
- `tests/test_webapp.py`

No database schema or environment-variable change is required.
