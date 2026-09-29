# ISK Trading Radar Mobile v0.1

Adds a cross-platform Expo/React Native client and a small mobile API patch to the existing FastAPI dashboard.

## Mobile screens
- Attention
- Radar
- Portfolio
- Stock detail
- AI Copilot: Ask / Configure / Diagnose / Fix

## Backend additions
- `/api/mobile/login`
- `/api/mobile/bootstrap`
- `/api/mobile/analyze`
- `/api/mobile/analysis/{symbol}`
- `/api/mobile/diagnostics`
- mobile alert actions
- mobile risk-profile update
- AI Copilot request + approval-gated apply endpoint

## Security
- Signed, expiring bearer token; default 30-day TTL.
- Token stored with Expo SecureStore.
- No server API keys in the app.
- Runtime AI fixes are allowlisted and approval-gated.
- Automatic source-code deployment remains disabled until a GitHub/CI connector is explicitly configured.
