# GEMv1 ONLY: Render standalone read-only service setup (draft)
2026-10-12. This configuration intentionally isolates GEM's existing read-only router from the old Dual Momentum / Paper Model FastAPI app.

## Form configuration
- Repository: ankitgarg1234-cell/isk-trading-radar
- Service name: gem-v1-dashboard
- Deployment branch: draft/gem-standalone-render-20261012 **ONLY AFTER PR REVIEW**. Never choose main or dual-momentum-dashboard: the standard start command runs the old shared Paper Model.
- Runtime: Python 3
- Region: Frankfurt
- Root directory: leave empty
- Build command: \`pip install -r requirements.txt\`
- Start command: \`uvicorn gem_data.gem_standalone:app --host 0.0.0.0 --port $PORT\`
- Instance: Starter $7/month (explicit user approval needed for creation/billing)
- Render auto-deploy: OFF; use manual deploy only after review.
- Health check path: \`/health\`

## Environment (secret values in Render only, NOT GitHub or chat)
- \`GEM_DASHBOARD_USERNAME\`: choose a unique username of >=3 characters.
- \`GEM_DASHBOARD_PASSWORD\`: generate a *different*, random strong 20+-character password, store it privately; HTTP Basic Auth over HTTPS. Without these, GEM HTML/API pages return HTTP 503 (fail closed).
- \`MARKETSTACK_API_KEY\`: paid Marketstack access key; storing the key does NOT start downloads because this revision has no active collector.
- \`GEM_READONLY_DATABASE_URL\`: optional future GEM-only Neon restricted reader credential, NOT shared DATABASE_URL. Do not set until explicitly reviewed.

## Smoke check
1. \`https://gem-v1-dashboard.onrender.com/health\` shows \`mode=READ_ONLY\` and \`trading_enabled=false\`. Note the subdomain is provisional until Render confirms it.
2. Open the base service URL; it redirects to \`/gem-trial\` and asks for the GEM dashboard username/password.
3. \`/api/gem-trial/status\` returns \`execution=DISABLED\`, \`ranking_ready=false\`, with all six independently unverified.
4. \`/trial\` and \`/api/trial\` are not served; any public API without credentials returns unauthorized.
5. Existing shared \`dual-momentum-radar\` remains unchanged; never reuse its secrets, DATABASE_URL or app main.

## Important
- This is a private GEMv1 **diagnostic-only** dashboard. It does NOT yet fetch/ingest Marketstack market data, perform daily cron, stream Alpaca IEX, send notifications, enter actual fills, or issue certified buy/sell signals.
- Marketstack v2 history probe is present as draft research code; it does not run unattended or incur API credits. The production collector requires authenticated rate/credit budget storage, Neon-only GEM receipts, corporate action and adjusted-price parity, complete index/SEC/calendar/SPY data and separate reviewer QA.
- The frozen trading strategy and manual trading model must not be changed here. No new orders until independent source evidence and user approval.
- Do not merge this branch into \`dual-momentum-dashboard\` merely to deploy a separate GEM service. A dedicated production branch can be prepared after the draft is reviewed.
