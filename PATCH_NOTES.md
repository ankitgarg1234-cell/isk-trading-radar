# Radar Column Filter Patch

Incremental patch for the ISK Trading Radar dashboard.

## What changed

Every decision column on the main Radar now has a useful filter path:

- **Stock** — ticker/company search, category, owned/new.
- **Price** — minimum and maximum price.
- **System view** — action plus minimum deterministic and AI scores.
- **Active level** — Primary Buy, Better Buy, Breakout, Position action.
- **Distance** — maximum percent distance to the active trigger; `NOW` is 0%.
- **Target / Stop** — minimum expected return, minimum risk/reward, maximum downside to stop.
- **Analyst** — analyst view and minimum analyst score; supports No consensus.
- **Risk fit** — risk band, portfolio fit and maximum stock-risk score.
- **Suggested size** — has/no suggested sizing, minimum shares and minimum capital.

Additional usability changes:

- Expandable **Column filters** panel keeps the main toolbar compact.
- Active column-filter counter.
- Visible-result counter.
- More sort options: price, analyst score, stock risk, R/R and suggested capital.
- All filters continue to apply after live Radar refreshes.

## Files to replace

- `app/templates/dashboard.html`
- `app/static/app.js`
- `app/static/style.css`
- `tests/test_webapp.py` (test update; optional in production but recommended)

No database migration or environment-variable change is required.
