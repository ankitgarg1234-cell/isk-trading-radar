# Install into the ISK Trading Radar repository

1. Apply the database-egress optimization and actionable-attention patches first if they are not already deployed.
2. Copy `backend-patch/app/main.py` -> `app/main.py`.
3. Copy `backend-patch/app/config.py` -> `app/config.py`.
4. Copy the `mobile/` directory to the repository root.
5. Commit and deploy the backend to Render.
6. Confirm `https://isk-trading-radar.onrender.com/health` is healthy.
7. In `mobile/`, run `npm install` and `npx expo install expo-secure-store`.
8. Start with `npx expo start` and test on an iPhone and Android device.

The mobile client uses compact API payloads and a minimum 60-second refresh interval, so it does not reintroduce the Neon egress issue that the dashboard optimization patch fixed.
