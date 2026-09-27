# ISK Trading Radar — V1 Full Functional Prototype

A private US-equity research/radar dashboard built with FastAPI, Jinja, SQLAlchemy and a continuous background scanner.

## What V1 now includes

- Dashboard with live-refreshing Radar candidates and alerts
- Manual **Analyze Any Symbol** workflow
- Current-position ledger with manual add/update/delete
- Screenshot import for existing positions
  - optional server-side AI vision when `OPENAI_API_KEY` is configured
  - free in-browser Tesseract OCR fallback when AI vision is not configured
  - mandatory confirmation/edit step before saving
- Trade ledger
- Cash + strategic reserve tracking
- Portfolio deployment / rotation proposals
- Deterministic score /100 with component breakdown
- Analyst-consensus score when data is available
- Explainable AI/context score with structured adjustments
- Analyst vs deterministic vs AI expected-yield / holding-period presentation
- News sentiment, materiality, credibility and priced-in-recency heuristic
- Strong-fundamental gate for **Explosive Runner** classification
- Buy zone / Better Buy / Breakout Buy / Do-Not-Chase / Stop / Target levels
- Position-aware decisions:
  - New: BUY NOW / WAIT MORE / BREAKOUT BUY / DON'T CHASE / AVOID / WATCH
  - Existing: ADD / HOLD / HOLD-DON'T-ADD / TAKE PARTIAL PROFIT / REDUCE / EXIT
- Continuous regular-session scanner while the Render process is awake
- Cross-sector broad discovery through the free V1 provider
- Analysis snapshots, Radar candidates and alerts persisted to the configured database
- Login capability via environment variables
- Health endpoint at `/health`

## Important V1 data/infrastructure boundary

The included no-key market provider is suitable for prototyping, **not** an exchange-grade guaranteed real-time feed. It may be delayed, throttled or incomplete. The provider interface is isolated so a production market/news source can replace it without redesigning the dashboard.

Render Free may sleep when there is no inbound traffic. Therefore the application logic supports continuous market-session scanning, but **free hosting cannot guarantee uninterrupted unattended scanning**.

## Deployment to the existing Render service

Your existing service can be updated from GitHub.

1. Back up your current repository/branch if desired.
2. Replace the repository contents with this release, preserving the files at repository root.
3. Commit/push to `main`.
4. Render should auto-deploy. If not: **Manual Deploy → Deploy latest commit**.

Use:

```text
Build command:
pip install -r requirements.txt

Start command:
uvicorn app.main:app --host 0.0.0.0 --port $PORT

Health check:
/health
```

### Environment variables

Recommended immediately:

```text
SESSION_SECRET=<long random value>
APP_USERNAME=admin
APP_PASSWORD=<your private password>
```

Optional for server-side AI explanations / screenshot vision:

```text
OPENAI_API_KEY=<key>
OPENAI_MODEL=gpt-5-mini
```

Without an OpenAI key, deterministic analysis and explainable heuristic AI continue to work, and screenshot import falls back to free browser OCR.

### Persistent ledger

If `DATABASE_URL` is absent, the app uses local SQLite. This is fine for local development but **not durable on Render Free**.

For the trade ledger/positions/history to survive redeploys and service filesystem replacement, set `DATABASE_URL` to a persistent PostgreSQL database.

The app accepts standard `postgresql://...` / `postgres://...` URLs and converts them to the psycopg driver automatically.

## Tests

See `TEST_RESULTS.md` and `REQUIREMENTS_MATRIX.md`.

Latest release result:

```text
25 passed
0 failed
73% overall Python coverage
```

Run locally:

```bash
pip install -r requirements-dev.txt
pytest --cov=app --cov-report=term --cov-report=xml:coverage.xml --junitxml=test-results.xml -q
```

## Architecture

```text
Browser
  ↓
FastAPI + Jinja dashboard
  ├─ Position / trade ledger
  ├─ Manual symbol analysis
  ├─ Screenshot import
  ├─ Live alerts API
  └─ Portfolio optimizer
  ↓
RadarService background scanner
  ↓
Market provider → deterministic engine → contextual AI layer
  ↓
SQLAlchemy → SQLite / PostgreSQL
```

## Deferred after V1

- IBKR read-only synchronization
- IBKR order tickets / execution
- Automatic brokerage execution
- Paid exchange-grade live market feed
- Truly exhaustive full-US-universe tick scanning
- Dedicated production news feed
- Exchange holiday / early-close calendar
- External push notifications
- Programmatic eToro signal integration

These are intentionally separated from V1 so the decision logic and portfolio workflow can be validated before broker execution is introduced.
