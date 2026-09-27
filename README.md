# ISK Trading Radar V1

First deployable prototype for the private US-equity Radar dashboard.

## Included now
- FastAPI web app
- Dashboard shell
- Manual-symbol analysis queue
- Manual trade ledger/current positions
- SQLite fallback for local development
- PostgreSQL support through `DATABASE_URL`
- Render Blueprint (`render.yaml`)
- Health endpoint at `/health`

## Render V1 deployment
1. Create a GitHub repository, for example `isk-trading-radar`.
2. Upload/push this project to the repository root.
3. In Render choose **Web Services → New Web Service**.
4. Connect GitHub and select the repository.
5. Render should detect Python. Use:
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - Health check: `/health`
   - Instance: Free for the prototype
6. Deploy.

## Database
The app runs with SQLite when `DATABASE_URL` is absent. On Render, the filesystem is not suitable as the permanent trade ledger, so create Postgres next and set its internal connection string as `DATABASE_URL`.

For a free V1, free Render Postgres is acceptable for prototyping, but do not consider it production-grade permanent storage.

## Next development milestones
1. Authentication/login
2. Persistent PostgreSQL schema for ledger, trades, radar runs and scores
3. Live US market-data provider
4. Continuous market-session candidate scanner
5. Deterministic scoring engine
6. News/catalyst ingestion
7. Explainable AI scoring
8. Buy/better-buy/do-not-chase engine
9. Position-aware ADD/HOLD/TAKE-PROFIT/REDUCE/EXIT logic
10. Portfolio optimizer and cash reallocation proposals
11. Screenshot position import
12. Alerts/push notifications
13. IBKR read-only integration
