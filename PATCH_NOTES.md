# ServiceNow-style inline Radar filter patch

This incremental patch replaces the previous expandable/bulk column-filter panel with inline filters directly inside each Radar table header.

## Changed runtime files
- `app/templates/dashboard.html`
- `app/static/app.js`
- `app/static/style.css`

## Test file
- `tests/test_webapp.py`

## UX changes
- Each surfaced Radar column has an inline `Operator + Value` filter.
- Stock supports contains / starts-with / exact / does-not-contain.
- Stock funnel adds Category and Ownership filters.
- Price supports >=, <=, >, < and exact.
- System View supports is / is-not plus System-score and AI-score thresholds in the funnel.
- Active Level supports is / is-not.
- Distance supports within %, at-least %, and `is NOW`.
- Target / Stop supports Expected Return, R/R, Stop Downside, or Target Price with numeric operators.
- Analyst supports rating is / is-not, No Consensus, and analyst-score threshold.
- Risk Fit supports fit is / is-not, plus Risk Band and stock-risk threshold.
- Suggested Size supports Shares or Capital with numeric operators plus sized/unsized state.
- Global Radar search, sorting, result count and clear-filters remain available.
- Filter header is sticky inside the Radar table; Stock remains pinned on desktop.
- Only one funnel menu is kept open at a time.

## Compatibility
No database schema, backend API, environment-variable, scanner, persistence, portfolio-risk or trade-decision changes are included in this patch.
