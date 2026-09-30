# GWRE optimizer revalidation fix

Verified against `ankitgarg1234-cell/isk-trading-radar` main commit:

`63e67817cd633ff32af425e1dd8a3e023bb6695f`

## What this fixes

The existing event path re-runs the paper optimizer when an individual ticker has a material actionable-state change. That misses this sequence:

`GWRE = BUY` → old restriction blocks it → restriction is removed → `GWRE = BUY` still → no BUY-state transition → no immediate optimizer re-run.

This patch makes **portfolio eligibility/configuration changes their own optimizer event**. On the first open-market scan after a restart/deployment, and whenever the risk profile or optimizer thresholds change, the paper engine reloads and re-ranks the current Top 20 even when every ticker stays BUY→BUY.

It also makes every visible Top-20 candidate carry an explicit portfolio decision. An actionable name can therefore show either a purchase decision or a PASS reason such as `Rank #13; Top-10 shortlist required` instead of silently remaining BUY.

## Important policy retained

- Paper trading only.
- No sector-position cap.
- No per-tier `max 2` cap.
- 5–7 position funnel remains unchanged.
- Top-20 visible / Top-10 serious-shortlist logic remains unchanged.
- Daily rotation remains slower than entry re-evaluation to avoid churn.

## Apply

From the repository root, copy `apply_gwre_optimizer_fix.py` there and run:

```bash
python apply_gwre_optimizer_fix.py
pytest tests/test_optimizer.py
```

The patcher creates `.gwre.bak` backups before changing each file. It is idempotent and stops rather than guessing if an expected source anchor no longer matches.

## Files changed

- `app/scanner.py`
- `app/portfolio_engine.py`
- `tests/test_optimizer.py`

The GitHub connector available in this chat can read the now-public repository, but repository writes are still rejected with HTTP 403, so this package does **not** modify your GitHub repo automatically.
