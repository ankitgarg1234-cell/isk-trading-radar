# Fast-track validation plan

Forward paper trading remains the most realistic test, but we do not need to wait two months doing nothing else.

## Track A — Live shadow paper test
Run the $10,000 optimizer portfolio every U.S. trading day and compare with SPY total return. Review weekly, but do not change ranking parameters mid-test.

Minimum checkpoint: 8 trading weeks. A two-month result is an early checkpoint, not proof by itself.

## Track B — Walk-forward historical replay in parallel
Use only point-in-time inputs that can be reconstructed without look-ahead. Do not backfill a historical day with today's fundamentals, analyst view or news. Run multiple disjoint windows rather than tuning one year until it wins.

Recommended windows: at least 3 years, with rolling/anchored out-of-sample periods. Report absolute return, SPY excess return, max drawdown, turnover, cash utilization, number of holdings and sector concentration.

## Track C — Shadow A/B comparison
Store three parallel series from the same dates:
1. Current production dashboard signals.
2. New Top-20 / 5–7 optimizer paper portfolio.
3. SPY total return benchmark.

This isolates whether improvement comes from candidate selection/allocation rather than market direction.

## Promotion gate
Do not set `OPTIMIZER_LIVE_GATING=true` unless evidence is robust across multiple windows. Suggested minimums:
- Out-of-sample excess return vs SPY is meaningful, not a rounding error (target at least ~3 percentage points annualized/full-year equivalent).
- Maximum drawdown <= 15% and preferably no worse than SPY.
- Excess return is positive in multiple independent subperiods, not driven by one stock/sector.
- Results survive reasonable changes to thresholds/position count/transaction friction.
- No look-ahead inputs.
- Forward paper behavior is consistent with the historical walk-forward result.

If these gates are not met, keep optimizer in SHADOW and continue using it only as research evidence.
