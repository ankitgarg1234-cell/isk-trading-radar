# ISK Radar — Decision Dashboard + Risk Management Patch

Incremental patch for the existing deployed V1. Do not replace the full repository.

## What this adds

- Decision-first Radar table with visible System signal: STRONG BUY / BUY / STARTER BUY / WAIT / WATCH / HOLD / TAKE PROFIT / SELL / STRONG SELL.
- Active buy/exit level visible on the dashboard without opening Details.
- Distance to the next actionable level (NOW, % lower, % higher).
- Target, stop/invalidation, risk/reward and analyst view on the main Radar.
- Search by ticker or company name.
- Client-side filters for action, category, stock-risk band, and owned/new.
- Sort by actionability, AI score, system score, trigger distance, or expected return.
- Expandable Radar rows with immediate rationale, expected return, sizing reason and "what changed" state.
- Four target portfolio risk profiles: Low, Medium, High, Aggressive.
- Risk profile persists in the database.
- Risk profile changes sizing/suitability only; it never changes the stock's deterministic or AI score.
- Account-level risk score (0-100) with concentration, sector, speculative exposure, cash buffer and event exposure components.
- Current risk vs selected target risk and a visible risk gap.
- Deterministic suggested position size based on cash, reserve cash, stop distance, portfolio risk budget and max-position cap.
- Whole-share sizing for the current Avanza-style portfolio flow.
- Risk-fit labels: GOOD FIT / STRETCH / ABOVE TARGET.
- Projected account risk after the suggested purchase.
- FX conversion support for mixed USD/SEK portfolio sizing using a cached Yahoo FX chart lookup; if FX is unavailable, the engine withholds the size rather than inventing one.
- "What changed" action-state comparison from the previous analysis snapshot.
- New summary cards for actionable buys, portfolio actions, deployable cash and account risk.

## Files to replace/add

Replace:
- `app/db.py`
- `app/market.py`
- `app/main.py`
- `app/templates/dashboard.html`
- `app/static/style.css`
- `app/static/app.js`
- `tests/test_webapp.py`

Add:
- `app/portfolio_engine.py`
- `tests/test_portfolio_engine.py`

## Database note

The patch adds the `portfolio_preferences` table. Existing positions, trades, snapshots, cash and alerts are untouched. The app's existing `Base.metadata.create_all()` creates the new table automatically on deployment.

## Safety behavior

- A risk preference does not manipulate the research score.
- `ABOVE TARGET` under Low/Medium risk can result in 0 suggested shares even when the stock itself remains a BUY.
- WAIT/WATCH rows may show a *planned* size at the trigger; they do not present it as a buy-now instruction.
- Position sizing is withheld if price, stop, cash, or required FX conversion is unavailable.
