# Database Egress Optimization Patch

## Why this patch exists
The previous live dashboard polled `/api/live` every 15 seconds. Each request rebuilt dashboard state from historical `AnalysisSnapshot` rows and could deserialize hundreds of large payloads containing one-year price history and sector benchmark history. On managed Postgres this created unnecessary outbound database traffic and exhausted the free Neon network-transfer quota.

## Changes
- Adds a compact `RadarCandidate.current_json` current-state payload.
- Current state excludes one-year `history` arrays and sector-benchmark history arrays.
- Dashboard/current-position logic uses current-state rows instead of scanning historical snapshots.
- Existing databases receive additive `radar_candidates` columns automatically; no ledger tables are dropped or recreated.
- Historical snapshots now store compact payloads only.
- Snapshot writes are throttled:
  - priority symbols (holdings/watchlist/manual analysis): normal checkpoint interval defaults to 1 hour;
  - broad-market candidates: default checkpoint interval is 6 hours;
  - action changes, meaningful score changes, material-news-count changes, or thesis invalidation changes still create a snapshot immediately.
- Scanner deterioration comparison uses the compact current-state record instead of downloading the prior full historical snapshot.
- Browser live polling defaults to 60 seconds instead of 15 seconds.
- `/api/live` keeps a server-side cache and rebuilds database state after a completed scanner cycle, explicit invalidation, or safety timeout; multiple browser polls/tabs reuse the same state between scans.
- Full-analysis and alert-drill-down routes prefer compact current state and fall back to historical snapshots only for pre-migration records.
- Restores the Evidence Provenance section on the symbol analysis page so functionality is not lost.

## New defaults
- `LIVE_POLL_SECONDS=60`
- `DASHBOARD_CACHE_SECONDS=600` (scanner completion changes the cache marker, so a new completed scan is surfaced without waiting 10 minutes)
- `SNAPSHOT_INTERVAL_SECONDS=3600`
- `SNAPSHOT_SCORE_DELTA=5`

You do not need to set these variables unless you want to override the defaults.

## Database safety
The runtime migration is additive only. It adds these columns to `radar_candidates` if missing:
- `current_json`
- `previous_action`
- `last_snapshot_at`
- `last_snapshot_key`

No positions, trades, cash, alerts, preferences or historical snapshots are deleted.
