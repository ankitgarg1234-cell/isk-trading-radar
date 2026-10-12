# GEMv1 Marketstack Basic onboarding (draft, research-only)
Date: 2026-10-12. User reports Marketstack Basic purchased for $9.99/month.

## State and boundary
- GEMv1's frozen strategy remains unchanged at d59b93d3d9a87d582045b4ae71ff9a6f696a48be.
- The currently deployed Render service dual-momentum-radar runs both the separate Paper Model and the read-only GEMv1 page. Do NOT set credentials or launch a collector there without an approved isolation/deployment plan.
- The new gem_data/marketstack_eod_probe.py only returns unverified vendor observations; it does not connect to the GEM status projection or publish trades. No key is configured or consumed by this PR.
- Membership, SEC accession facts, actions, official NYSE session calendar, SPY cash distributions and independent QA remain distinct source gates.

## Owner action (after approval of isolated test runtime)
1. Copy the Marketstack **secret access key** from the authenticated account dashboard.
2. In the newly approved GEM-only Render collector service (not GitHub, not chat, not browser URL logs), set the secret environment variable MARKETSTACK_API_KEY.
3. Keep the key out of issue comments, CI logs and the shared Paper Model app. Do not enable unattended collection until quota protection and persistence are reviewed.

## Read-only validation before full historical download
1. Confirm account entitlement via a few bounded v2/eod calls: AAPL, MSFT, NVDA, TSLA, SPY, P, HPE, PLTR, MPC, VLO, PSX.
2. Compare nominal OHLCV and vendor_adj_close with archived independent data at split/dividend dates; vendor_adj_close is *not automatically* the frozen GEM total-return series.
3. Confirm that a requested month-end closing bar appears only after the relevant completed NYSE session. Check date/time, exchange ID, duplicate dates and missing rows.
4. Check two years of history and at least 127 completed NYSE sessions; for the archived research indicators, check up to 252+ sessions including warmup when needed. Historical lookback never substitutes for effective-dated universe or SEC original filings.
5. Check tricky symbols, share classes, ticker renames/delistings, dividend and split endpoint consistency; raise a blocking coverage report for every unresolved symbol.
6. Only after the sample passes: build a full member-by-member historical backfill into GEM-only Neon with versioned raw receipts, cached deltas and a separately maintained monthly account-credit budget. Do not treat this draft per-process limit as an account-wide overage prevention mechanism.

## API budgeting and spend safety
Marketstack Basic publicly lists 10,000 ticker request credits/month. Each requested symbol consumes a credit; paginated calls and corporate action requests may add more. Overages are automatically billed, so the approved collector must maintain a durable monthly cap and stop **before** approaching 10,000. Marketstack's account portal can alert at 75%, 90% and 100%, but warnings do not prevent fees.

## Live prices
Marketstack Basic provides daily history and IEX intraday data but *does not* provide the full consolidated real-time quote service. Planned free Alpaca IEX WebSocket feed for holdings/SPY/watchlist is a separate future integration requiring its own account, entitlement and licensing verification. Its prices are indicative IEX-only observations, not guaranteed consolidated bid/ask or a broker execution quote.

## Shadow-only acceptance
These probes cannot change source status to VERIFIED. Any complete 500+ instrument ranking requires source completeness, independently checked SEC facts/action semantics, authenticated reviewer certificates, and explicit release approval. Keep the Paper Model untouched, new GEM BUY/SELL disabled, and all brokerage trades manual.
