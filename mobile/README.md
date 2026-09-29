# ISK Trading Radar Mobile

Cross-platform mobile client for the existing ISK Trading Radar backend.

## Platforms

Targeted at Expo SDK 57 / React Native 0.86:
- iOS 16.4+
- Android 7+

The same TypeScript codebase builds both apps.

## Included in this first mobile build

- Secure mobile login using the existing dashboard username/password.
- Signed bearer token stored in `expo-secure-store` (not a database secret or API key embedded in the app).
- **Attention** screen: actionable alerts only.
- **Radar** screen: searchable/filterable current candidates.
- **Portfolio** screen: holdings, cash/reserve, risk profile and rotation proposals.
- **Stock Detail**: deterministic score, AI score, analyst score, entry levels, target/stop, deterministic breakdown, reasons and risks.
- **AI Copilot** modes: Ask, Configure, Diagnose, Fix.
- Approval-gated runtime repairs: fresh scan, clear live cache, reanalyse symbol, change risk profile.
- 60-second-or-slower foreground refresh using the backend's compact mobile bootstrap endpoint.

## Important AI Fix boundary

This build can diagnose the running system and apply **allowlisted, reversible runtime fixes** after approval. It does **not** let an LLM silently edit production source code or deploy to Render.

A later GitHub/CI connector can extend Fix mode to:
1. generate a patch,
2. run the regression suite,
3. show the changed files,
4. require explicit approval,
5. deploy staging,
6. health-check,
7. deploy production or roll back.

Trading-policy changes should always require a separate explicit approval even after that connector is added.

## Backend update

Replace the two files from `../backend-patch/app/` in the current dashboard repo:
- `app/main.py`
- `app/config.py`

No new Python package is required. `itsdangerous` is already in the dashboard requirements.

Optional Render environment variable:

```text
MOBILE_TOKEN_TTL_SECONDS=2592000
```

Default is 30 days.

## Run locally

```bash
cd mobile
cp .env.example .env
npm install
npx expo install expo-secure-store
npx expo start
```

Open the project in Expo Go / development build on iOS or Android. Expo Go currently requires login to Expo.

## Build installable apps

After signing in to Expo/EAS:

```bash
npm install -g eas-cli
eas login
eas build:configure
eas build --platform android --profile preview
eas build --platform ios --profile preview
```

For store builds:

```bash
eas build --platform android --profile production
eas build --platform ios --profile production
```

Apple distribution requires an Apple Developer account; Google Play distribution requires a Google Play developer account.

## API URL

Default:

```text
https://isk-trading-radar.onrender.com
```

Override in `.env`:

```text
EXPO_PUBLIC_API_URL=https://your-service.example.com
```

Never place `DATABASE_URL`, Finnhub, OpenAI, SEC credentials, or Render credentials in `EXPO_PUBLIC_*` variables.
