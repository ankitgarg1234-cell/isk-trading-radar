# Patch summary

**Base:** `63e67817cd633ff32af425e1dd8a3e023bb6695f` (`main`, 2026-09-30)

### Root cause
`RadarService.scan_once()` only promoted a paper optimizer run when `_paper_entry_event()` saw a material per-symbol state change. GWRE was already BUY before the old block was removed, so removing the portfolio restriction did not itself create a signal transition.

### Fix
1. Add an optimizer-policy fingerprint independent of ticker state.
2. Force one full Top-20 re-evaluation on startup/deployment and whenever risk-profile/optimizer eligibility settings change.
3. Preserve the existing event-driven ticker path and daily rotation cadence.
4. Add explicit BUY/PASS decision reasons for all visible Top-20 rows.
5. Add regression tests confirming both the sector cap and per-tier max-two cap are absent.

### Expected GWRE behavior
If GWRE remains BUY/77 after a restriction is removed, the policy invalidation fires even though `_paper_entry_event(GWRE)` itself does not change. `run_paper_cycle(..., entry_event=True)` reloads the current ranked Top 20 and GWRE receives either an optimizer-selected paper BUY or an explicit PASS reason.
