# Portfolio Optimizer + Paper Trading Patch

## Purpose
This patch implements the agreed market-to-portfolio funnel without promoting an unvalidated strategy to live decision gating.

### Funnel
- Full U.S. market continues to be scanned in the background.
- Main Radar displays at most **20** portfolio-priority names.
- Top **10** are the serious shortlist.
- Portfolio target is **6** positions and hard maximum is **7**.
- The optimizer never forces weak positions simply to reach five/six holdings; unused capital remains cash.
- Existing holdings count toward the 5–7 portfolio limit.
- A materially stronger candidate can become a ROTATE candidate, but rotation is treated as opportunity-cost reallocation, not thesis invalidation.

### Separate scores
- Existing deterministic stock score is unchanged.
- New `Portfolio Priority` score is a separate deterministic capital-allocation rank.
- AI and analyst scores remain independent confirmation/divergence signals and are **not blended** into Portfolio Priority.

### Shadow / validation safety
- `OPTIMIZER_LIVE_GATING=false` by default.
- Therefore optimizer ranking/paper trading can run without replacing current production BUY alerts.
- After validation, setting `OPTIMIZER_LIVE_GATING=true` promotes optimizer-approved entries/rotations to the attention queue without another source-code change.

### Paper trading
- Starts automatically on the first successful scan when `PAPER_TRADING_ENABLED=true` (default).
- Starting capital: **$10,000**.
- Whole shares only.
- Target 6 positions, maximum 7.
- Daily normal rebalance; thesis-invalidated EXIT/REDUCE can act immediately.
- Default modeled transaction friction: **10 bps per trade**.
- Benchmark: **SPY total return** using adjusted closes, including distributions.
- Stores independent paper account, positions, trades and performance snapshots. No broker orders are sent and real portfolio/trade tables are untouched.

## New environment settings (all optional)
- `OPTIMIZER_LIVE_GATING=false`
- `OPTIMIZER_VISIBLE_LIMIT=20`
- `OPTIMIZER_SHORTLIST_LIMIT=10`
- `OPTIMIZER_TARGET_POSITIONS=6`
- `OPTIMIZER_MAX_POSITIONS=7`
- `OPTIMIZER_MIN_RANK_SCORE=62`
- `OPTIMIZER_ROTATION_GAP=12`
- `OPTIMIZER_ROTATION_YIELD_GAP=8`
- `OPTIMIZER_MAX_SAME_SECTOR=2`
- `PAPER_TRADING_ENABLED=true`
- `PAPER_STARTING_CASH=10000`
- `PAPER_TRADE_COST_BPS=10`
- `PAPER_REBALANCE_SECONDS=86400`
- `PAPER_SNAPSHOT_SECONDS=1800`

## Database
New paper tables are additive and created automatically by SQLAlchemy. `radar_candidates` gets two additive compact columns: `portfolio_rank_score` and `rank_version`.
