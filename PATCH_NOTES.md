# Remove sector-cap restriction

This patch removes the portfolio-level maximum-same-sector rule from the optimizer.

## Behavior after patch
- Sector classification and sector momentum remain available as stock-level evidence.
- Sector concentration does **not** block a qualified candidate from being selected.
- The optimizer may hold 3, 4, 5, 6, or 7 stocks from the same sector if they are the strongest qualifying opportunities.
- The existing Top-20 / Top-10 / target-6 / max-7 funnel remains unchanged.
- Existing rank, entry-signal, risk-fit, cash, whole-share and portfolio-slot rules remain unchanged.
- `OPTIMIZER_MAX_SAME_SECTOR` is obsolete/ignored after this patch and may be removed from Render environment variables.

## Files changed
- `app/portfolio_engine.py`
- `app/config.py`
- `app/paper_engine.py`
- `app/main.py`
- `app/scanner.py`
- `tests/test_optimizer.py`

## Validation
79 tests passed, 0 failed.
A dedicated regression test confirms that six qualifying Technology candidates can all be selected when they are the strongest opportunities.
