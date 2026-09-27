# Entry-state decision patch

Fixes the entry engine so a stock does not revert to generic WATCH after trading below the primary buy zone.

## Runtime files to replace
- `app/analysis_engine.py`
- `app/templates/analysis.html`

## Test file to replace
- `tests/test_analysis_engine.py`

## New entry states
- PRIMARY_BUY
- BETTER_BUY
- VALUE_CORRIDOR
- DEEP_VALUE
- APPROACHING_BREAKOUT
- BREAKOUT
- DO_NOT_CHASE
- INVALIDATED

## Decision behavior
- Primary buy zone + high conviction -> BUY NOW
- Primary buy zone + adequate conviction -> CONSIDER BUYING NOW
- Primary zone + falling-risk signal -> WAIT MORE
- Price below primary zone but above better-buy zone -> CONSIDER STARTER BUY or WAIT FOR BETTER BUY depending on momentum
- Better-buy zone -> CONSIDER BUYING NOW if thesis is intact
- Existing holdings can ADD at active entry levels when evidence and conviction are adequate

Regression suite after patch: 38 passed, 0 failed.
